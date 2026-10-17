"""Download de streams HLS (.m3u8) -> .mp4, equivalente aos esquemas hlstoidm:// do IDM.

Sem criptografia: baixa os segmentos em paralelo, concatena e remuxa com ffmpeg (se houver).
Com EXT-X-KEY (AES-128 etc.): delega ao ffmpeg, que trata a chave.
"""
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from . import net, sysint
from .engine import ST_COMPLETE, ST_CONNECTING, ST_DOWNLOADING, ST_ERROR, ST_PAUSED
from .util import sanitize_filename, unique_path


def fetch_text(url, item, netcfg):
    with net.http_open(url, item, netcfg) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def parse_master(text, base):
    """Retorna variantes [(bandwidth, resolution, url)] ordenadas da melhor para a pior."""
    out, lines = [], text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF"):
            bw = int((re.search(r"BANDWIDTH=(\d+)", ln) or [0, 0])[1])
            res = (re.search(r"RESOLUTION=(\d+x\d+)", ln) or [None, ""])[1]
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    out.append((bw, res, urljoin(base, nxt.strip())))
                    break
    return sorted(out, reverse=True)


def parse_media(text, base):
    segs, encrypted, dur = [], False, 0.0
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("#EXT-X-KEY") and "METHOD=NONE" not in ln:
            encrypted = True
        elif ln.startswith("#EXTINF:"):
            try:
                dur += float(ln[8:].split(",")[0])
            except ValueError:
                pass
        elif ln and not ln.startswith("#"):
            segs.append(urljoin(base, ln))
    return segs, encrypted, dur


class HlsDownloader:
    def __init__(self, item, netcfg, temp_dir, global_limiter, max_conn=8, on_finish=None, **_):
        self.item, self.net, self.glimit = item, netcfg, global_limiter
        self.temp = Path(temp_dir) / f"{item['id']}.hls"
        self.max_conn = max(1, min(int(max_conn), 16))
        self.on_finish = on_finish
        self.stop_ev = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.proc = None
        self.done_bytes = 0
        self.total_segs = 0
        self.done_segs = 0
        self._samples = deque(maxlen=20)

    def start(self):
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def downloaded(self):
        return self.done_bytes

    def stats(self):
        now = time.monotonic()
        self._samples.append((now, self.done_bytes))
        while len(self._samples) > 2 and now - self._samples[0][0] > 5:
            self._samples.popleft()
        t0, d0 = self._samples[0]
        rate = (self.done_bytes - d0) / (now - t0) if now - t0 > 0.3 else 0
        return {"downloaded": self.done_bytes, "rate": max(0, rate),
                "connections": [{"id": 1, "seg": self.done_segs, "state": f"segmento {self.done_segs}/{self.total_segs}", "err": ""}]}

    def segment_map(self):
        if not self.total_segs:
            return []
        return [(0, self.done_segs, self.total_segs - 1)]

    def sync(self):
        self.item["downloaded"] = self.done_bytes

    def _run(self):
        it = self.item
        it["last_try"] = time.time()
        it["error"] = ""
        it["status"] = ST_CONNECTING
        try:
            self._download()
            if self.stop_ev.is_set():
                it["status"] = ST_PAUSED
            else:
                it["status"] = ST_COMPLETE
                it["completed_at"] = time.time()
        except Exception as e:  # noqa: BLE001
            it["status"] = ST_PAUSED if self.stop_ev.is_set() else ST_ERROR
            it["error"] = str(e)[:300]
        finally:
            self.sync()
            if self.on_finish:
                self.on_finish(self)

    def _dest(self, ext):
        it = self.item
        name = sanitize_filename(Path(it.get("filename") or "video").stem) + ext
        d = Path(it["save_dir"]).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return unique_path(d / name)

    def _download(self):
        it = self.item
        text, base = fetch_text(it["url"], it, self.net)
        if "#EXT-X-STREAM-INF" in text:
            variants = parse_master(text, base)
            if not variants:
                raise RuntimeError("Playlist mestre sem variantes")
            text, base = fetch_text(variants[0][2], it, self.net)
            it["hls_variant"] = variants[0][1] or str(variants[0][0])
        segs, encrypted, dur = parse_media(text, base)
        if not segs:
            raise RuntimeError("Playlist HLS vazia")
        self.total_segs = len(segs)
        it["duration"] = dur
        ffmpeg = sysint.find_tool("ffmpeg")
        it["status"] = ST_DOWNLOADING
        if encrypted:
            if not ffmpeg:
                raise RuntimeError("Stream criptografado: instale o ffmpeg para baixar")
            return self._via_ffmpeg(ffmpeg, base)

        self.temp.mkdir(parents=True, exist_ok=True)

        def fetch(i_url):
            i, url = i_url
            p = self.temp / f"{i:06d}.ts"
            if p.exists():
                with self.lock:
                    self.done_bytes += p.stat().st_size
                    self.done_segs += 1
                return
            for attempt in range(5):
                if self.stop_ev.is_set():
                    return
                data = bytearray()
                try:
                    with net.http_open(url, it, self.net) as r:
                        while chunk := r.read(64 * 1024):
                            if self.stop_ev.is_set():
                                return
                            data += chunk
                            self.glimit.consume(len(chunk), self.stop_ev)
                            with self.lock:
                                self.done_bytes += len(chunk)
                    tmp = p.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, p)
                    with self.lock:
                        self.done_segs += 1
                    return
                except Exception:  # noqa: BLE001
                    with self.lock:
                        self.done_bytes -= len(data)
                    self.stop_ev.wait(2 ** attempt)
            raise RuntimeError(f"Falha no segmento {i}")

        with ThreadPoolExecutor(self.max_conn) as ex:
            list(ex.map(fetch, enumerate(segs)))
        if self.stop_ev.is_set():
            return
        joined = self.temp / "all.ts"
        with open(joined, "wb") as out:
            for i in range(len(segs)):
                with open(self.temp / f"{i:06d}.ts", "rb") as f:
                    shutil.copyfileobj(f, out)
        if ffmpeg:
            dest = self._dest(".mp4")
            r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(joined), "-c", "copy",
                                "-bsf:a", "aac_adtstoasc", str(dest)], capture_output=True, text=True)
            if r.returncode != 0:
                dest = self._dest(".ts")
                shutil.move(str(joined), dest)
        else:
            dest = self._dest(".ts")
            shutil.move(str(joined), dest)
        shutil.rmtree(self.temp, ignore_errors=True)
        it["filename"] = dest.name
        it["size"] = dest.stat().st_size

    def _via_ffmpeg(self, ffmpeg, url):
        it = self.item
        dest = self._dest(".mp4")
        hdr = "".join(f"{k}: {v}\r\n" for k, v in net.build_headers(it, self.net).items()
                      if k not in ("Accept-Encoding", "User-Agent"))
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-progress", "pipe:1", "-user_agent",
               net.build_headers(it, self.net)["User-Agent"]]
        if hdr:
            cmd += ["-headers", hdr]
        cmd += ["-i", url, "-c", "copy", str(dest)]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for ln in self.proc.stdout:
            if ln.startswith("total_size="):
                try:
                    self.done_bytes = int(ln.split("=")[1])
                except ValueError:
                    pass
            elif ln.startswith("out_time_ms=") and it.get("duration"):
                try:
                    self.done_segs = int(int(ln.split("=")[1]) / 1e6 / it["duration"] * self.total_segs)
                except ValueError:
                    pass
        self.proc.wait()
        if self.stop_ev.is_set():
            dest.unlink(missing_ok=True)
            return
        if self.proc.returncode != 0:
            raise RuntimeError("ffmpeg falhou: " + self.proc.stderr.read()[-200:])
        it["filename"] = dest.name
        it["size"] = dest.stat().st_size
