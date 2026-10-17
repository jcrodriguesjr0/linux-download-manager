"""Gerenciador: lista de downloads persistente, filas, agendador, limitador global e eventos para a UI."""
import json
import queue as _queue
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import net, sysint
from .config import DOWNLOADS_FILE, QUEUES_FILE, Settings, atomic_write_json
from .engine import (ST_COMPLETE, ST_CONNECTING, ST_DOWNLOADING, ST_ERROR, ST_PAUSED, ST_QUEUED,
                     Downloader)
from .hls import HlsDownloader
from .media import VideoDownloader
from .util import category_for, claim_path, move_into, sanitize_filename, unique_path

ACTIVE = (ST_CONNECTING, ST_DOWNLOADING)
MAIN_QUEUE = "main"
PERSIST_SKIP = {"_fatal"}


def new_queue(qid, name):
    return {"id": qid, "name": name, "items": [], "parallel": 1, "retries": 3, "running": False,
            "start_on_startup": False, "on_done": "none", "open_file": "",
            "schedule": {"enabled": False, "start_time": "02:00", "days": list(range(7)), "once": False,
                         "stop_enabled": False, "stop_time": "08:00", "repeat_minutes": 0}}


class Manager:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.items: dict[str, dict] = {}
        self.runtime: dict[str, dict] = {}
        self.active: dict[str, object] = {}
        self.queues: dict[str, dict] = {}
        self.events: _queue.Queue = _queue.Queue()
        self.lock = threading.RLock()
        self.limiter = net.SpeedLimiter(0)
        self._dirty = False
        self._last_save = 0.0
        self._last_minute = None
        self._retry_count: dict[str, int] = {}
        self._stop = threading.Event()
        self.load()
        self.apply_speed_limit(self.s["speed_limiter_on"] or self.s["speed_limiter_on_startup"])
        self._tick_thread = threading.Thread(target=self._loop, daemon=True, name="ldm-tick")

    # ---------- persistência ----------
    def load(self):
        if DOWNLOADS_FILE.exists():
            try:
                for it in json.loads(DOWNLOADS_FILE.read_text()):
                    if it.get("status") in ACTIVE:
                        it["status"] = ST_PAUSED
                    self.items[it["id"]] = it
            except Exception:
                pass
        if QUEUES_FILE.exists():
            try:
                self.queues = {q["id"]: q for q in json.loads(QUEUES_FILE.read_text())}
            except Exception:
                pass
        if MAIN_QUEUE not in self.queues:
            self.queues[MAIN_QUEUE] = new_queue(MAIN_QUEUE, "Fila principal")
        for q in self.queues.values():
            q["running"] = False
            q["items"] = [i for i in q["items"] if i in self.items]

    def save(self):
        with self.lock:
            for d in self.active.values():
                d.sync()
            data = [{k: v for k, v in it.items() if k not in PERSIST_SKIP} for it in self.items.values()]
            atomic_write_json(DOWNLOADS_FILE, data)
            atomic_write_json(QUEUES_FILE, list(self.queues.values()))
            self._dirty = False
            self._last_save = time.time()

    def mark_dirty(self):
        self._dirty = True

    # ---------- ciclo ----------
    def run(self):
        for q in self.queues.values():
            if q.get("start_on_startup"):
                self.start_queue(q["id"])
        self._tick_thread.start()

    def shutdown(self):
        self._stop.set()
        for d in list(self.active.values()):
            d.stop()
        for d in list(self.active.values()):
            if d.thread:
                d.thread.join(5)
        self.save()

    def _loop(self):
        while not self._stop.wait(0.5):
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001
                self.events.put(("log", f"erro no ciclo: {e}"))

    def _tick(self):
        with self.lock:
            for iid, d in list(self.active.items()):
                st = d.stats()
                it = self.items.get(iid)
                if not it:
                    continue
                size = it.get("size") or -1
                rate = st["rate"]
                eta = (size - st["downloaded"]) / rate if rate > 0 and size > 0 else None
                self.runtime[iid] = {"rate": rate, "eta": eta, "downloaded": st["downloaded"],
                                     "connections": st["connections"]}
        self._process_queues()
        self._scheduler()
        if self._dirty or (self.active and time.time() - self._last_save > 10):
            if time.time() - self._last_save > 3:
                self.save()

    # ---------- itens ----------
    def find_by_url(self, url):
        for it in self.items.values():
            if it["url"] == url:
                return it
        return None

    def resolve_target(self, url, filename):
        cat = category_for(filename, url, self.s["categories"])
        folder = cat["folder"] if cat else self.s["general_folder"]
        return (cat["name"] if cat else "Geral"), folder

    def add(self, url, filename=None, save_dir=None, start=True, queue_id=None, referer="", cookies="",
            user_agent="", description="", auth_user="", auth_pass="", category=None, kind=None,
            headers=None, post_data=None, filename_locked=None, duplicate=None, max_conn=None, extra=None):
        url = url.strip()
        dup = self.find_by_url(url)
        action = duplicate or self.s["duplicate_action"]
        if dup and action == "resume":
            if dup["status"] != ST_COMPLETE and start:
                self.start(dup["id"])
            self.events.put(("duplicate", dup["id"]))
            return dup
        fn = sanitize_filename(filename) if filename else sanitize_filename(
            Path(url.split("?")[0].rstrip("/")).name or "download")
        cat_name, folder = self.resolve_target(url, fn)
        if category:
            cat = next((c for c in self.s["categories"] if c["name"] == category), None)
            cat_name, folder = category, (cat["folder"] if cat else self.s["general_folder"])
        if save_dir:
            folder = save_dir
        if kind is None and ".m3u8" in url.lower().split("?")[0]:
            kind = "hls"
        it = {
            "id": uuid.uuid4().hex[:12], "url": url, "filename": fn,
            "filename_locked": bool(filename) if filename_locked is None else filename_locked,
            "save_dir": str(Path(folder).expanduser()), "category": cat_name,
            "size": -1, "downloaded": 0, "status": ST_QUEUED if queue_id else ST_PAUSED,
            "resumable": None, "referer": referer, "cookies": cookies, "user_agent": user_agent,
            "description": description, "auth_user": auth_user, "auth_pass": auth_pass,
            "added": time.time(), "last_try": None, "error": "", "kind": kind or "http",
            "headers": headers or {}, "post_data": post_data, "max_conn": max_conn,
            "overwrite": action == "overwrite",
        }
        if extra:
            it.update(extra)
        if action == "number" and dup:
            p = unique_path(Path(it["save_dir"]) / fn)
            it["filename"] = p.name
        with self.lock:
            self.items[it["id"]] = it
            if queue_id:
                self.queues.setdefault(queue_id, new_queue(queue_id, queue_id))["items"].append(it["id"])
        self.mark_dirty()
        self.events.put(("added", it["id"]))
        if start:
            self.start(it["id"])
        return it

    def update(self, iid, **kw):
        with self.lock:
            self.items[iid].update(kw)
        self.mark_dirty()
        self.events.put(("changed", iid))

    def _make_downloader(self, it):
        cls = {"hls": HlsDownloader, "video": VideoDownloader}.get(it.get("kind"), Downloader)
        return cls(it, net.NetConfig(self.s), self.s["temp_dir"], self.limiter, settings=self.s,
                   max_conn=self.s["max_connections"], min_segment=int(self.s["min_segment_kb"]) * 1024,
                   retries=int(self.s["retries"]), on_finish=self._on_finish,
                   set_mtime=self.s["set_server_mtime"])

    def start(self, iid):
        with self.lock:
            it = self.items.get(iid)
            if not it or iid in self.active or it["status"] == ST_COMPLETE:
                return
            d = self._make_downloader(it)
            self.active[iid] = d
            it["status"] = ST_CONNECTING
            d.start()
        self.events.put(("changed", iid))

    def pause(self, iid):
        d = self.active.get(iid)
        if d:
            d.stop()
        elif iid in self.items and self.items[iid]["status"] == ST_QUEUED:
            self.items[iid]["status"] = ST_PAUSED
        self.events.put(("changed", iid))

    def start_all(self):
        for iid, it in list(self.items.items()):
            if it["status"] not in (ST_COMPLETE,) + ACTIVE:
                self.start(iid)

    def pause_all(self):
        for iid in list(self.active):
            self.pause(iid)

    def remove(self, iid, delete_file=False):
        d = self.active.get(iid)
        if d:
            d.stop()
            if d.thread:
                d.thread.join(5)
        with self.lock:
            it = self.items.pop(iid, None)
            self.runtime.pop(iid, None)
            for q in self.queues.values():
                if iid in q["items"]:
                    q["items"].remove(iid)
        if it:
            tmp = Path(self.s["temp_dir"]) / f"{iid}.part"
            if not delete_file and it["status"] != ST_COMPLETE and tmp.exists() and tmp.stat().st_size:
                # o usuário quis guardar a parte baixada: vai para o destino como "nome.part"
                dest_dir = Path(it["save_dir"]).expanduser()
                dest_dir.mkdir(parents=True, exist_ok=True)
                move_into(str(tmp), claim_path(dest_dir / (it["filename"] + ".part")))
            tmp.unlink(missing_ok=True)
            for suffix in (".hls", ".streams", ".ytdlp"):
                shutil.rmtree(Path(self.s["temp_dir"]) / f"{iid}{suffix}", ignore_errors=True)
            from .media import COOKIE_DIR
            (COOKIE_DIR / f"{iid}.txt").unlink(missing_ok=True)
            if delete_file and it["status"] == ST_COMPLETE:
                (Path(it["save_dir"]) / it["filename"]).unlink(missing_ok=True)
        self.mark_dirty()
        self.events.put(("removed", iid))

    def delete_completed(self):
        for iid, it in list(self.items.items()):
            if it["status"] == ST_COMPLETE:
                self.remove(iid)

    def redownload(self, iid):
        it = self.items[iid]
        self.pause(iid)
        d = self.active.get(iid)
        if d and d.thread:
            d.thread.join(5)
        (Path(self.s["temp_dir"]) / f"{iid}.part").unlink(missing_ok=True)
        it.update(status=ST_PAUSED, segments=[], downloaded=0, size=-1, resumable=None, error="")
        self.start(iid)

    def temp_path(self, iid) -> Path:
        """Onde os dados ficam durante o download (movidos para o destino ao concluir)."""
        base = Path(self.s["temp_dir"]).expanduser()
        for name in (f"{iid}.part", f"{iid}.streams", f"{iid}.ytdlp", f"{iid}.hls"):
            if (base / name).exists():
                return base / name
        return base

    def file_path(self, iid) -> Path:
        it = self.items[iid]
        return Path(it["save_dir"]).expanduser() / it["filename"]

    def _on_finish(self, d):
        it = d.item
        iid = it["id"]
        with self.lock:
            self.active.pop(iid, None)
            rt = self.runtime.get(iid)
            if rt:
                rt.update(rate=0, eta=None, connections=[])
        self.mark_dirty()
        if it["status"] == ST_COMPLETE:
            self._retry_count.pop(iid, None)
            self._after_complete(it)
            self.events.put(("completed", iid))
        elif it["status"] == ST_ERROR:
            self._play("dialog-error", self.s["sound_failed"])
            self.events.put(("failed", iid))
        else:
            self.events.put(("changed", iid))

    def _after_complete(self, it):
        self._play("complete", self.s["sound_complete"])
        scanner = (self.s["virus_scanner"] or "").strip()
        if scanner:
            path = str(Path(it["save_dir"]) / it["filename"])
            args = (self.s["virus_args"] or "[File]")
            cmd = shlex.split(scanner) + [a.replace("[File]", path) for a in shlex.split(args)]
            if "[File]" not in args:
                cmd.append(path)
            it["scan_status"] = "verificando"
            def scan():
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                    it["scan_status"] = "limpo" if r.returncode == 0 else f"ALERTA (código {r.returncode})"
                except Exception as e:  # noqa: BLE001
                    it["scan_status"] = f"erro: {e}"
                self.events.put(("scanned", it["id"]))
            threading.Thread(target=scan, daemon=True).start()

    @staticmethod
    def _play(event_id, enabled):
        if not enabled:
            return
        sysint.play_sound(event_id)

    # ---------- limitador de velocidade ----------
    def apply_speed_limit(self, on: bool, kbps: int | None = None):
        if kbps is not None:
            self.s["speed_limit_kbps"] = int(kbps)
        self.s["speed_limiter_on"] = bool(on)
        self.limiter.set_rate(int(self.s["speed_limit_kbps"]) * 1024 if on else 0)
        self.s.save()

    def set_item_limit(self, iid, on: bool, kbps: int):
        it = self.items[iid]
        it["speed_limit_on"], it["speed_limit_kbps"] = on, kbps
        d = self.active.get(iid)
        if d and hasattr(d, "flimit"):
            d.flimit.set_rate(kbps * 1024 if on else 0)
        self.mark_dirty()

    # ---------- filas e agendador ----------
    def add_queue(self, name):
        qid = uuid.uuid4().hex[:8]
        self.queues[qid] = new_queue(qid, name)
        self.mark_dirty()
        return self.queues[qid]

    def delete_queue(self, qid):
        if qid != MAIN_QUEUE:
            self.queues.pop(qid, None)
            self.mark_dirty()

    def queue_of(self, iid):
        return next((q for q in self.queues.values() if iid in q["items"]), None)

    def add_to_queue(self, iid, qid):
        with self.lock:
            for q in self.queues.values():
                if iid in q["items"]:
                    q["items"].remove(iid)
            self.queues[qid]["items"].append(iid)
            if self.items[iid]["status"] not in (ST_COMPLETE,) + ACTIVE:
                self.items[iid]["status"] = ST_QUEUED
        self.mark_dirty()
        self.events.put(("changed", iid))

    def remove_from_queue(self, iid):
        q = self.queue_of(iid)
        if q:
            q["items"].remove(iid)
            self.mark_dirty()

    def move_in_queue(self, qid, iid, delta):
        lst = self.queues[qid]["items"]
        i = lst.index(iid)
        j = max(0, min(len(lst) - 1, i + delta))
        lst.insert(j, lst.pop(i))
        self.mark_dirty()

    def start_queue(self, qid):
        q = self.queues.get(qid)
        if not q:
            return
        q["running"] = True
        for iid in q["items"]:
            it = self.items.get(iid)
            if it and it["status"] in (ST_PAUSED, ST_ERROR):
                it["status"] = ST_QUEUED
                self.events.put(("changed", iid))
            self._retry_count.pop(iid, None)
        self.events.put(("queue", qid))

    def stop_queue(self, qid):
        q = self.queues.get(qid)
        if not q:
            return
        q["running"] = False
        for iid in q["items"]:
            if iid in self.active:
                self.pause(iid)
        self.events.put(("queue", qid))

    def _process_queues(self):
        for q in list(self.queues.values()):
            if not q["running"]:
                continue
            ids = [i for i in q["items"] if i in self.items]
            running = [i for i in ids if i in self.active]
            pending = []
            for i in ids:
                it = self.items[i]
                if i in self.active or it["status"] == ST_COMPLETE:
                    continue
                if it["status"] == ST_ERROR and self._retry_count.get(i, 0) >= q["retries"]:
                    continue
                pending.append(i)
            slots = int(q["parallel"]) - len(running)
            for i in pending[:max(0, slots)]:
                if self.items[i]["status"] == ST_ERROR:
                    self._retry_count[i] = self._retry_count.get(i, 0) + 1
                self.start(i)
            if not running and not pending:
                q["running"] = False
                rep = int((q.get("schedule") or {}).get("repeat_minutes") or 0)
                if rep and q["schedule"].get("enabled"):
                    q["next_start"] = time.time() + rep * 60   # sincronização periódica
                self.events.put(("queue_done", q["id"]))

    def _scheduler(self):
        now = datetime.now()
        minute = now.strftime("%Y-%m-%d %H:%M")
        if minute == self._last_minute:
            return
        self._last_minute = minute
        hm = now.strftime("%H:%M")
        for q in list(self.queues.values()):
            sc = q.get("schedule") or {}
            if not sc.get("enabled"):
                continue
            day_ok = now.weekday() in sc.get("days", range(7))
            if sc.get("once"):
                day_ok = sc.get("date", now.strftime("%Y-%m-%d")) == now.strftime("%Y-%m-%d")
            if day_ok and sc.get("start_time") == hm and not q["running"]:
                self.start_queue(q["id"])
                self.events.put(("log", f"Fila '{q['name']}' iniciada pelo agendador"))
            if q.get("next_start") and time.time() >= q["next_start"] and not q["running"]:
                q.pop("next_start")
                self.start_queue(q["id"])
            if sc.get("stop_enabled") and sc.get("stop_time") == hm and q["running"]:
                self.stop_queue(q["id"])
                self.events.put(("log", f"Fila '{q['name']}' parada pelo agendador"))

    # ---------- ações de energia (opções ao concluir) ----------
    @staticmethod
    def power_off(force=False):
        sysint.power_off(force)
