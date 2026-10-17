"""Motor de download multi-conexão com segmentação dinâmica (comportamento central do IDM).

Fluxo:
  1. A primeira conexão pede `Range: bytes=0-`. Resposta 206 => servidor aceita retomada.
  2. Essa mesma conexão vira o segmento 0 (nada é baixado duas vezes).
  3. Conexões extras "roubam" metade do maior trecho restante (divisão dinâmica),
     e cada conexão que termina repete o roubo até não haver trecho >= 2 * min_segment.
  4. Tudo é gravado com pwrite num único arquivo .part pré-alocado; ao concluir é movido ao destino.
"""
import email.utils
import os
import re
import shutil
import threading
import time
from collections import deque
from pathlib import Path

from . import net
from .util import filename_from_headers, unique_path

CHUNK = 64 * 1024

ST_QUEUED, ST_CONNECTING, ST_DOWNLOADING, ST_PAUSED, ST_COMPLETE, ST_ERROR = (
    "queued", "connecting", "downloading", "paused", "complete", "error")


class DownloadError(Exception):
    pass


class Segment:
    __slots__ = ("start", "end", "pos", "worker")

    def __init__(self, start, end, pos=None):
        self.start, self.end = start, end
        self.pos = start if pos is None else pos
        self.worker = None

    def remaining(self):
        return None if self.end is None else self.end - self.pos + 1

    def done(self):
        return self.end is not None and self.pos > self.end


class Downloader:
    """Executa um item de download em threads. Interface: start(), stop(), stats(), sync()."""

    def __init__(self, item: dict, netcfg: net.NetConfig, temp_dir: str, global_limiter: net.SpeedLimiter,
                 max_conn: int = 8, min_segment: int = 512 * 1024, retries: int = 5, on_finish=None,
                 set_mtime: bool = True, **_):
        self.item = item
        self.net = netcfg
        self.temp_dir = Path(temp_dir)
        self.glimit = global_limiter
        self.flimit = net.SpeedLimiter(int(item.get("speed_limit_kbps") or 0) * 1024 if item.get("speed_limit_on") else 0)
        self.max_conn = max(1, int(item.get("max_conn") or max_conn))
        self.min_seg = max(64 * 1024, min_segment)
        self.retries = retries
        self.on_finish = on_finish
        self.set_mtime = set_mtime
        self.lock = threading.RLock()
        self.stop_ev = threading.Event()
        self.segments: list[Segment] = []
        self.workers: dict[int, dict] = {}
        self.streams = set()
        self.fd = None
        self.thread = None
        self._samples = deque(maxlen=20)
        self._wid = 0
        self.final_url = item.get("final_url") or item["url"]
        # Tamanho máximo por requisição Range (0 = sem limite). Servidores como o googlevideo
        # reduzem a velocidade de requisições longas; blocos de ~10 MB mantêm a velocidade máxima.
        self.req_chunk = int(item.get("req_chunk") or 0)

    # ---------- API pública ----------
    def start(self):
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self._run, name=f"dl-{self.item['id']}", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()
        with self.lock:
            for s in list(self.streams):
                try:
                    s.close()
                except Exception:
                    pass

    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def downloaded(self):
        with self.lock:
            return sum(s.pos - s.start for s in self.segments)

    def stats(self):
        """Velocidade (média móvel ~5s), bytes baixados e conexões ativas."""
        now = time.monotonic()
        d = self.downloaded()
        self._samples.append((now, d))
        while len(self._samples) > 2 and now - self._samples[0][0] > 5:
            self._samples.popleft()
        t0, d0 = self._samples[0]
        rate = (d - d0) / (now - t0) if now - t0 > 0.3 else 0
        with self.lock:
            conns = [{"id": wid, "seg": w["seg"], "state": w["state"], "err": w.get("err", "")}
                     for wid, w in self.workers.items()]
        return {"downloaded": d, "rate": max(0, rate), "connections": conns}

    def segment_map(self):
        """Lista (start, pos, end) para desenhar o mapa de conexões como no diálogo de progresso do IDM."""
        with self.lock:
            return [(s.start, s.pos, s.end) for s in self.segments]

    def sync(self):
        """Copia o estado interno para o dict persistível do item."""
        with self.lock:
            self.item["segments"] = [[s.start, s.end, s.pos] for s in self.segments]
            self.item["downloaded"] = sum(s.pos - s.start for s in self.segments)

    # ---------- internos ----------
    def _set(self, **kw):
        with self.lock:
            self.item.update(kw)

    def _temp_path(self):
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self.temp_dir / f"{self.item['id']}.part"

    def _run(self):
        it = self.item
        it["last_try"] = time.time()
        it["error"] = ""
        it.pop("_fatal", None)
        self._set(status=ST_CONNECTING)
        try:
            self._prepare_and_download()
            if self.stop_ev.is_set():
                self.sync()
                self._set(status=ST_PAUSED)
            else:
                self._finalize()
        except Exception as e:  # noqa: BLE001 - qualquer falha vira estado de erro visível na UI
            self.sync()
            self._set(status=ST_PAUSED if self.stop_ev.is_set() else ST_ERROR, error=str(e)[:300])
        finally:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None
            if self.on_finish:
                self.on_finish(self)

    def _prepare_and_download(self):
        it = self.item
        tmp = self._temp_path()
        segs = it.get("segments") or []
        can_resume = bool(segs) and tmp.exists() and (it.get("resumable") or (it.get("size") or 0) <= 0)
        first_stream = None

        if can_resume and it.get("resumable") and it.get("size"):
            # Retomada: valida se o servidor ainda aceita Range e se o tamanho não mudou.
            self.segments = [Segment(a, b, p) for a, b, p in segs]
            pending = [s for s in self.segments if not s.done()]
            if not pending:
                return
            probe_seg = pending[0]
            first_stream = self._open(probe_seg)
            total = self._total_from(first_stream)
            if first_stream.status != 206 or (total and total != it["size"]):
                first_stream.close()
                first_stream = None
                self.segments = []
                can_resume = False
        else:
            can_resume = False

        if not can_resume:
            if tmp.exists():
                tmp.unlink()
            s = net.open_stream(it["url"], it, self.net, start=0)
            self._track(s)
            self.final_url = s.geturl() or it["url"]
            it["final_url"] = self.final_url
            headers = getattr(s, "headers", {}) or {}
            total = self._total_from(s)
            resumable = getattr(s, "status", 200) == 206 or (it["url"].lower().startswith("ftp://") and total)
            if not it.get("filename_locked"):
                fn = filename_from_headers(self.final_url, headers) if headers else os.path.basename(it["url"])
                if fn and fn != it.get("filename"):
                    it["filename"] = fn
            it["size"] = total if total else -1
            it["resumable"] = bool(resumable and total)
            it["content_type"] = headers.get("Content-Type", "") if headers else ""
            it["last_modified"] = headers.get("Last-Modified", "") if headers else ""
            self.segments = [Segment(0, total - 1 if total else None)]
            first_stream = s
            probe_seg = self.segments[0]

        self.fd = os.open(self._temp_path(), os.O_RDWR | os.O_CREAT, 0o644)
        if it.get("size", -1) > 0 and it.get("resumable"):
            os.ftruncate(self.fd, it["size"])
        self._set(status=ST_DOWNLOADING)
        if self.req_chunk and it.get("resumable") and first_stream is not None and \
                getattr(first_stream, "_ldm_end", None) is None:
            self._untrack(first_stream)     # sonda aberta sem limite: reabre em blocos
            first_stream = None

        # Lança a primeira conexão (reaproveitando o fluxo da sondagem) + conexões extras.
        threads = [self._spawn(probe_seg, first_stream)]
        if it.get("resumable"):
            for seg in [s for s in self.segments if not s.done() and s is not probe_seg and s.worker is None]:
                if len(threads) >= self.max_conn:
                    break
                threads.append(self._spawn(seg))
            while len(threads) < self.max_conn and not self.stop_ev.is_set():
                seg = self._steal()
                if seg is None:
                    break
                threads.append(self._spawn(seg))
        # Trechos de uma conexão que falhou de vez ficam órfãos e são adotados pelas outras via _steal().
        for t in threads:
            t.join()
        if self.stop_ev.is_set():
            return
        bad = [s for s in self.segments if not s.done() and s.end is not None]
        if bad:
            raise DownloadError(self.item.pop("_fatal", None) or "Download incompleto: conexões falharam")

    @staticmethod
    def _total_from(s):
        h = getattr(s, "headers", None)
        if isinstance(s, net.FtpStream):
            return s.size
        if not h:
            return None
        cr = h.get("Content-Range")
        if cr:
            m = re.search(r"/(\d+)", cr)
            if m:
                return int(m.group(1))
        cl = h.get("Content-Length")
        if cl and cl.isdigit() and getattr(s, "status", 200) == 200:
            return int(cl)
        return None

    def _track(self, s):
        with self.lock:
            self.streams.add(s)

    def _untrack(self, s):
        with self.lock:
            self.streams.discard(s)
        try:
            s.close()
        except Exception:
            pass

    def _open(self, seg: Segment):
        end = seg.end if self.item.get("resumable") else None
        if end is not None and self.req_chunk:
            end = min(end, seg.pos + self.req_chunk - 1)
        s = net.open_stream(self.final_url, self.item, self.net, start=seg.pos, end=end)
        s._ldm_end = end if self.req_chunk else None
        self._track(s)
        if seg.pos > 0 and getattr(s, "status", 200) != 206:
            self._untrack(s)
            raise DownloadError("O servidor não aceita retomada (Range) para este arquivo")
        return s

    def _steal(self) -> Segment | None:
        """Divide o maior trecho restante ao meio (segmentação dinâmica)."""
        with self.lock:
            best = None
            for s in self.segments:
                r = s.remaining()
                if r is not None and r >= 2 * self.min_seg and (best is None or r > best.remaining()):
                    best = s
            if best is None:
                orphan = next((s for s in self.segments if not s.done() and s.worker is None), None)
                if orphan:
                    orphan.worker = -1
                return orphan
            mid = best.pos + best.remaining() // 2
            new = Segment(mid, best.end)
            best.end = mid - 1
            new.worker = -1
            self.segments.append(new)
            self.segments.sort(key=lambda x: x.start)
            return new

    def _spawn(self, seg: Segment, stream=None):
        with self.lock:
            self._wid += 1
            wid = self._wid
            seg.worker = wid
            self.workers[wid] = {"seg": seg.start, "state": "conectando"}
        t = threading.Thread(target=self._worker, args=(wid, seg, stream), daemon=True)
        t.start()
        return t

    def _worker(self, wid, seg: Segment, stream):
        attempts = 0
        try:
            while not self.stop_ev.is_set():
                try:
                    if stream is None:
                        if not self.item.get("resumable") and seg.pos > 0:
                            # Sem retomada: recomeça do zero.
                            with self.lock:
                                seg.pos = 0
                            os.ftruncate(self.fd, 0)
                        stream = self._open(seg)
                    with self.lock:
                        self.workers[wid]["state"] = "recebendo"
                    self._pump(seg, stream)
                    req_end = getattr(stream, "_ldm_end", None)
                    self._untrack(stream)
                    stream = None
                    if self.stop_ev.is_set():
                        return
                    if req_end is not None and not seg.done() and seg.pos > req_end:
                        attempts = 0      # bloco da requisição concluído: pede o próximo
                        continue
                    if seg.end is None or seg.done():
                        if seg.end is None:
                            with self.lock:
                                seg.end = seg.pos - 1
                                if self.item.get("size", -1) <= 0:
                                    self.item["size"] = seg.pos
                        # Terminou: tenta roubar mais trabalho (o "pulo" de conexão do IDM).
                        if not self.item.get("resumable"):
                            return
                        nxt = self._steal()
                        if nxt is None:
                            return
                        with self.lock:
                            seg.worker = None
                            seg = nxt
                            seg.worker = wid
                            self.workers[wid]["seg"] = seg.start
                        attempts = 0
                        continue
                    raise DownloadError("Conexão encerrada antes do fim do trecho")
                except Exception as e:  # noqa: BLE001
                    if stream is not None:
                        self._untrack(stream)
                        stream = None
                    if self.stop_ev.is_set():
                        return
                    attempts += 1
                    with self.lock:
                        self.workers[wid].update(state="erro, tentando de novo", err=str(e)[:120])
                    if isinstance(e, DownloadError) and "Range" in str(e) or attempts > self.retries:
                        self.item["_fatal"] = str(e)
                        return
                    self.stop_ev.wait(min(2 ** attempts, 30))
        finally:
            with self.lock:
                if seg.worker == wid:
                    seg.worker = None
                self.workers.pop(wid, None)

    def _pump(self, seg: Segment, stream):
        read = stream.read
        while not self.stop_ev.is_set():
            data = read(CHUNK)
            if not data:
                return
            with self.lock:
                if seg.end is not None:
                    allowed = seg.end - seg.pos + 1
                    if allowed <= 0:
                        return
                    if len(data) > allowed:
                        data = data[:allowed]
                pos = seg.pos
            os.pwrite(self.fd, data, pos)
            with self.lock:
                seg.pos = pos + len(data)
                done = seg.end is not None and seg.pos > seg.end
            self.flimit.consume(len(data), self.stop_ev)
            self.glimit.consume(len(data), self.stop_ev)
            if done:
                return

    def _finalize(self):
        it = self.item
        self.sync()
        if self.fd is not None:
            os.fsync(self.fd)
            os.close(self.fd)
            self.fd = None
        dest_dir = Path(it["save_dir"]).expanduser()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / it["filename"]
        if dest.exists() and not it.get("overwrite"):
            dest = unique_path(dest)
            it["filename"] = dest.name
        shutil.move(str(self._temp_path()), dest)
        if self.set_mtime and it.get("last_modified"):
            try:
                ts = email.utils.parsedate_to_datetime(it["last_modified"]).timestamp()
                os.utime(dest, (ts, ts))
            except Exception:
                pass
        it["size"] = dest.stat().st_size
        it["downloaded"] = it["size"]
        it["completed_at"] = time.time()
        self._set(status=ST_COMPLETE)
