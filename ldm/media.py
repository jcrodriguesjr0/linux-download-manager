"""Grabber de vídeo: extração com yt-dlp (YouTube e ~1800 sites) + download acelerado.

Equivale ao "Download this video" do IDM (IDMVMPrs.dll + painel do navegador):
  1. yt-dlp extrai título, formatos e URLs reais (roda no host ou na distrobox).
  2. Formatos HTTP diretos (ex.: YouTube vídeo + áudio separados) são baixados pelo NOSSO
     motor multi-conexão e mesclados com ffmpeg, igual ao IDM.
  3. Formatos fragmentados (HLS/DASH), conversão para MP3, legendas e playlists ficam com o
     próprio yt-dlp, com fragmentos concorrentes (-N).
"""
import importlib.util
import json
import os
import sys
import shlex
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from . import engine, hostenv, sysint
from .config import DATA_DIR
from .engine import ST_COMPLETE, ST_CONNECTING, ST_DOWNLOADING, ST_ERROR, ST_PAUSED
from .util import sanitize_filename, unique_path

VENV_YTDLP = DATA_DIR / "ytdlp" / "bin" / "yt-dlp"
VENV_PIP = DATA_DIR / "ytdlp" / "bin" / "pip"
PYLIB = DATA_DIR / "pylib"          # yt-dlp atualizado pelo usuário quando roda como AppImage (somente leitura)
DENO_LOCAL = DATA_DIR / "bin" / "deno"


def deno_path():
    if DENO_LOCAL.exists():
        return str(DENO_LOCAL)
    return sysint.find_tool("deno")


def bundled():
    """yt-dlp embutido na AppImage (mesmo interpretador do LDM)."""
    return bool(os.environ.get("LDM_APPDIR")) and importlib.util.find_spec("yt_dlp") is not None
COOKIE_DIR = DATA_DIR / "cookies"
NATIVE_PROTOCOLS = ("http", "https")
LOGIN_HINTS = ("cookies", "sign in", "log in", "logged-in", "login", "age", "confirm your age", "private", "members")
PROG = "LDMPROG"
FILE_MARK = "LDMFILE"
PROGRESS_TEMPLATE = (f"download:{PROG} %(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
                     "%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|%(info.format_id)s")


def split_cmd(cmd):
    """Divide um comando digitado pelo usuário (no Windows: caminhos com \\ e entre aspas duplas)."""
    if not sysint.IS_WIN:
        return shlex.split(cmd)
    return [x[1:-1] if len(x) > 1 and x[0] == x[-1] == '"' else x for x in shlex.split(cmd, posix=False)]


class MediaError(Exception):
    pass


# =============================================================== backend yt-dlp
class Backend:
    """Localiza o yt-dlp: comando configurado > venv local > PATH do host > venv dentro da distrobox."""

    _cache = None
    _lock = threading.Lock()

    def __init__(self, settings):
        self.s = settings

    def _works(self, cmd, launcher=()):
        try:
            r = subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=60,
                               env=self.env(list(launcher)) if launcher or cmd[0] == sys.executable else None)
            return r.returncode == 0 and r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None

    def resolve(self, refresh=False):
        """Retorna (launcher, exe, versão). launcher vazio = execução direta."""
        with Backend._lock:
            if Backend._cache and not refresh:
                return Backend._cache
            box = self.s.get("distrobox_name") or "ubuntu-24-04"
            cands = []
            if self.s.get("ytdlp_cmd"):
                cands.append(([], split_cmd(self.s["ytdlp_cmd"])))
            if sysint.IS_WIN:                       # yt-dlp.exe que vem com o instalador (ou a cópia atualizada)
                exe = sysint.find_tool("yt-dlp")
                if exe:
                    cands.append(([], [exe]))
            if bundled():
                cands.append(([], [sys.executable, "-m", "yt_dlp"]))
            if VENV_YTDLP.exists():
                cands.append(([], [str(VENV_YTDLP)]))
            if shutil.which("yt-dlp"):
                cands.append(([], ["yt-dlp"]))
            if not sysint.IS_WIN and shutil.which("distrobox") and VENV_YTDLP.exists():
                cands.append((["distrobox", "enter", box, "--"], [str(VENV_YTDLP)]))
            for launcher, exe in cands:
                v = self._works(launcher + exe, launcher)
                if v:
                    Backend._cache = (launcher, exe, v)
                    return Backend._cache
            Backend._cache = None
            raise MediaError("yt-dlp não encontrado. Use Opções > Vídeo > Instalar/atualizar yt-dlp.")

    def common_args(self):
        args = ["--no-colors", "--no-warnings" if not self.s.get("video_verbose") else "--verbose"]
        if sysint.IS_WIN:
            args += ["--encoding", "utf-8"]
        deno = deno_path()
        if deno:
            args += ["--js-runtimes", f"deno:{deno}"]
        return args

    def run_json(self, args, timeout=180):
        launcher, exe, _v = self.resolve()
        r = subprocess.run(launcher + exe + self.common_args() + ["-J"] + args, capture_output=True, text=True,
                           timeout=timeout, env=self.env(launcher))
        if r.returncode != 0 or not r.stdout.strip():
            err = [ln for ln in r.stderr.splitlines() if "ERROR" in ln] or r.stderr.strip().splitlines()[-1:]
            raise MediaError((err[-1] if err else "falha na extração").replace("ERROR: ", ""))
        return json.loads(r.stdout)

    def popen(self, args, pidfile):
        """Inicia o yt-dlp gravando o PID real (o namespace de PID da distrobox é o do host)."""
        launcher, exe, _v = self.resolve()
        if not launcher:   # execução direta: o PID do Popen já é o do yt-dlp
            p = subprocess.Popen(exe + self.common_args() + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, bufsize=1, env=self.env(launcher))
            Path(pidfile).parent.mkdir(parents=True, exist_ok=True)
            Path(pidfile).write_text(str(p.pid))
            return p
        cmd = launcher + ["sh", "-c", 'echo $$ > "$0"; exec "$@"', str(pidfile)] + exe + self.common_args() + args
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                                env=self.env(launcher))

    @staticmethod
    def env(launcher):
        """yt-dlp embutido precisa do ambiente da AppImage; distrobox/host precisam do ambiente original."""
        return hostenv.host_env() if launcher else dict(os.environ)

    def ffmpeg(self):
        exe = sysint.find_tool("ffmpeg")
        if exe:
            return [exe]
        launcher = self.resolve()[0]
        return launcher + ["ffmpeg"] if launcher else ["ffmpeg"]

    def update(self):
        """Instala/atualiza yt-dlp[default,curl-cffi] no venv (na distrobox se necessário)."""
        if sysint.IS_WIN:
            return self._update_windows()
        if bundled():
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "--target", str(PYLIB),
                                "--break-system-packages", "yt-dlp[default,curl-cffi]"],
                               capture_output=True, text=True, timeout=900)
            if r.returncode == 0:
                self.resolve(refresh=True)
                return True, "yt-dlp " + self.resolve()[2]
            return False, (r.stdout + r.stderr).strip()[-600:]
        box = self.s.get("distrobox_name") or "ubuntu-24-04"
        venv = DATA_DIR / "ytdlp"
        script = (f'[ -x "{VENV_PIP}" ] || python3 -m venv "{venv}"; '
                  f'"{VENV_PIP}" install -q -U "yt-dlp[default,curl-cffi]" && "{VENV_YTDLP}" --version')
        launcher = [] if not shutil.which("distrobox") else ["distrobox", "enter", box, "--"]
        r = subprocess.run(launcher + ["sh", "-c", script], capture_output=True, text=True, timeout=900)
        self.resolve(refresh=True) if r.returncode == 0 else None
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-600:]


    def _update_windows(self):
        """Windows: a pasta de instalação não é gravável; copia o yt-dlp.exe para os dados do usuário e roda -U."""
        user_exe = sysint.data_dir() / "bin" / "yt-dlp.exe"
        if not user_exe.exists():
            src = sysint.find_tool("yt-dlp")
            if not src:
                return False, "yt-dlp.exe não encontrado na instalação"
            user_exe.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, user_exe)
        r = subprocess.run([str(user_exe), "-U"], capture_output=True, text=True, timeout=900)
        ok = r.returncode == 0
        if ok:
            self.resolve(refresh=True)
        return ok, (r.stdout + r.stderr).strip()[-600:]


# =============================================================== cookies
def write_cookie_file(path: Path, cookies: list[dict]):
    """Cookies do navegador (objetos chrome.cookies) -> formato Netscape aceito pelo yt-dlp."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        dom = c.get("domain", "")
        host_only = c.get("hostOnly", not dom.startswith("."))
        if not host_only and not dom.startswith("."):
            dom = "." + dom
        lines.append("\t".join([dom, "FALSE" if host_only else "TRUE", c.get("path", "/"),
                                "TRUE" if c.get("secure") else "FALSE", str(int(c.get("expirationDate") or 0)),
                                c.get("name", ""), c.get("value", "")]))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def needs_login(msg: str) -> bool:
    m = msg.lower()
    return any(h in m for h in LOGIN_HINTS)


def extra_args(item, cookie_file=None):
    a = []
    if cookie_file:
        a += ["--cookies", str(cookie_file)]
    if item.get("user_agent"):
        a += ["--user-agent", item["user_agent"]]
    if item.get("referer"):
        a += ["--referer", item["referer"]]
    return a


# =============================================================== análise (probe) e opções de qualidade
def probe(backend: Backend, candidates: list[str], item: dict, cookies: list[dict] | None):
    """Tenta cada URL candidata (frame do player, página). Sem cookies primeiro; com cookies se o site exigir."""
    last = None
    cookie_file = None
    for url in [u for i, u in enumerate(candidates) if u and u not in candidates[:i]]:
        for use_cookies in ((False, True) if cookies else (False,)):
            if use_cookies:
                cookie_file = write_cookie_file(COOKIE_DIR / f"probe_{os.getpid()}.txt", cookies)
            try:
                info = backend.run_json(extra_args(item, cookie_file if use_cookies else None) + ["--no-playlist", url])
                if info.get("_type") == "playlist" and info.get("entries"):
                    info = next((e for e in info["entries"] if e), info)
                if not info.get("formats") and not info.get("url"):
                    raise MediaError("nenhum formato de vídeo encontrado")
                info["_ldm_source"] = url
                info["_ldm_cookies"] = use_cookies
                return info
            except (MediaError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
                last = str(e)
                if not use_cookies and not (cookies and needs_login(last)):
                    break
            finally:
                if cookie_file:
                    cookie_file.unlink(missing_ok=True)
                    cookie_file = None
    raise MediaError(last or "não foi possível analisar o vídeo")


def _size(f, duration):
    s = f.get("filesize") or f.get("filesize_approx")
    if not s and f.get("tbr") and duration:
        s = int(f["tbr"] * 1000 / 8 * duration)
    return int(s or 0)


def _codec(c):
    c = (c or "").lower()
    for k, v in (("avc", "H.264"), ("h264", "H.264"), ("hev", "H.265"), ("h265", "H.265"), ("vp09", "VP9"),
                 ("vp9", "VP9"), ("av01", "AV1"), ("mp4a", "AAC"), ("aac", "AAC"), ("opus", "Opus"),
                 ("vorbis", "Vorbis"), ("mp3", "MP3")):
        if c.startswith(k):
            return v
    return c.split(".")[0].upper() if c and c != "none" else ""


def build_choices(info: dict, prefer_mp4=True) -> list[dict]:
    """Opções de download no estilo do painel do IDM: uma por resolução + somente áudio."""
    dur = info.get("duration") or 0
    fmts = info.get("formats") or ([info] if info.get("url") else [])
    videos = [f for f in fmts if f.get("vcodec") != "none" and (f.get("height") or f.get("vcodec"))
              and f.get("protocol") != "mhtml"]
    audios = [f for f in fmts if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]

    direct = lambda f: 1 if f.get("protocol") in NATIVE_PROTOCOLS else 0  # noqa: E731 (multi-conexão nativa)

    def ascore(f):
        compat = 1 if (f.get("ext") == "m4a" or _codec(f.get("acodec")) == "AAC") else 0
        return ((f.get("language_preference") or 0) >= 10 or "original" in (f.get("format_note") or "").lower(),
                "drc" not in str(f.get("format_id")), compat if prefer_mp4 else 0, direct(f),
                f.get("abr") or f.get("tbr") or 0)

    best_audio = max(audios, key=ascore) if audios else None
    choices = []
    by_h: dict[int, list] = {}
    for f in videos:
        by_h.setdefault(int(f.get("height") or 0), []).append(f)
    for h in sorted(by_h, reverse=True):
        def vscore(f):
            compat = 1 if _codec(f.get("vcodec")) == "H.264" else 0
            return (compat if prefer_mp4 else 0, f.get("fps") or 0, direct(f), f.get("tbr") or 0)
        v = max(by_h[h], key=vscore)
        progressive = v.get("acodec") not in (None, "none")
        if progressive or not best_audio:
            sel, size, aud = v["format_id"], _size(v, dur), _codec(v.get("acodec"))
            ext = v.get("ext") or "mp4"
            fallback = f"b[height<={h}]" if h else "b"
        else:
            sel = f"{v['format_id']}+{best_audio['format_id']}"
            size = _size(v, dur) + _size(best_audio, dur)
            aud = _codec(best_audio.get("acodec"))
            ext = "mp4" if (_codec(v.get("vcodec")) in ("H.264", "H.265", "AV1") and aud == "AAC") else (
                "webm" if _codec(v.get("vcodec")) in ("VP9", "AV1") and aud in ("Opus", "Vorbis") else "mkv")
            fallback = f"bv*[height<={h}]+ba/b[height<={h}]" if h else "bv*+ba/b"
        label = f"{h}p" if h else "Original"
        if v.get("fps") and v["fps"] > 30:
            label += f"{int(v['fps'])}"
        choices.append({"kind": "video", "label": label, "ext": ext.upper(),
                        "codec": " + ".join(x for x in (_codec(v.get("vcodec")), aud) if x),
                        "size": size, "selector": f"{sel}/{fallback}", "merge": ext,
                        "protocols": [v.get("protocol", "")] + ([best_audio.get("protocol", "")] if not progressive and best_audio else [])})
    if best_audio:
        a = best_audio
        choices.append({"kind": "audio", "label": "Somente áudio", "ext": (a.get("ext") or "m4a").upper(),
                        "codec": _codec(a.get("acodec")), "size": _size(a, dur), "selector": f"{a['format_id']}/ba/b",
                        "merge": None, "protocols": [a.get("protocol", "")]})
        choices.append({"kind": "audio", "label": "Somente áudio", "ext": "MP3", "codec": "MP3 (convertido)",
                        "size": int(dur * 192000 / 8) if dur else 0, "selector": "ba/b", "merge": None,
                        "mp3": True, "protocols": ["ytdlp"]})
    if not choices and fmts:
        f = fmts[-1]
        choices.append({"kind": "video", "label": "Melhor", "ext": (f.get("ext") or "mp4").upper(), "codec": "",
                        "size": _size(f, dur), "selector": "bv*+ba/b", "merge": None, "protocols": [f.get("protocol", "")]})
    return choices


def default_choice(choices, max_height=0):
    vids = [c for c in choices if c["kind"] == "video"]
    if max_height:
        ok = [c for c in vids if c["label"][:-1].split("p")[0].isdigit() and int(c["label"].split("p")[0]) <= max_height]
        if ok:
            return ok[0]
    return vids[0] if vids else (choices[0] if choices else None)


# =============================================================== downloader
class VideoDownloader:
    """Mesma interface do engine.Downloader (start/stop/alive/stats/segment_map/sync)."""

    def __init__(self, item, netcfg, temp_dir, global_limiter, max_conn=8, min_segment=512 * 1024, retries=5,
                 on_finish=None, settings=None, **_):
        self.item, self.net, self.temp = item, netcfg, Path(temp_dir)
        self.glimit, self.max_conn, self.min_seg, self.retries = global_limiter, max_conn, min_segment, retries
        self.on_finish = on_finish
        self.s = settings or {}
        self.backend = Backend(self.s)
        self.stop_ev = threading.Event()
        self.thread = None
        self.proc = None
        self.pidfile = self.temp / f"{item['id']}.pid"
        self.subs: list[engine.Downloader] = []
        self.sub_done = 0
        self.phase = "analisando"
        self.mode = None         # "native" (motor LDM) ou "ytdlp"
        self._yt = {}            # progresso do yt-dlp por format_id: (baixado, total)
        self._samples = deque(maxlen=20)
        self.cookie_file = None

    # ---- interface
    def start(self):
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"video-{self.item['id']}")
        self.thread.start()

    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def stop(self):
        self.stop_ev.set()
        for d in list(self.subs):
            d.stop()
        self._interrupt()

    def downloaded(self):
        if self.mode == "native":
            return self.sub_done + sum(d.downloaded() for d in self.subs if d.item.get("status") != ST_COMPLETE)
        return sum(a for a, _t in self._yt.values())

    def stats(self):
        now = time.monotonic()
        d = self.downloaded()
        self._samples.append((now, d))
        while len(self._samples) > 2 and now - self._samples[0][0] > 5:
            self._samples.popleft()
        t0, d0 = self._samples[0]
        rate = (d - d0) / (now - t0) if now - t0 > 0.3 else 0
        conns = []
        for sd in self.subs:
            if sd.alive():
                conns += sd.stats()["connections"]
        if not conns:
            conns = [{"id": 1, "seg": self.phase, "state": self.phase, "err": ""}]
        return {"downloaded": d, "rate": max(0, rate), "connections": conns}

    def segment_map(self):
        out, off = [], 0
        for sd in self.subs:
            size = sd.item.get("size") or 0
            for a, p, b in sd.segment_map():
                if b is not None:
                    out.append((off + a, off + p, off + b))
            off += max(size, 0)
        if not out and self.item.get("size", -1) > 0:
            out = [(0, min(self.downloaded(), self.item["size"]), self.item["size"] - 1)]
        return out

    def sync(self):
        self.item["downloaded"] = self.downloaded()
        if self.subs:
            for sd in self.subs:
                sd.sync()

    # ---- execução
    def _interrupt(self):
        """Interrompe o yt-dlp; o progresso fica no .part e é retomado depois."""
        if sysint.IS_WIN:
            if self.proc and self.proc.poll() is None:
                sysint.stop_process(self.proc)
            return
        try:
            pid = int(self.pidfile.read_text().strip())
            os.kill(pid, signal.SIGINT)
        except (OSError, ValueError):
            if self.proc and self.proc.poll() is None:
                self.proc.send_signal(signal.SIGINT)

    def _run(self):
        it = self.item
        it["last_try"] = time.time()
        it["error"] = ""
        it["status"] = ST_CONNECTING
        try:
            v = it["video"]
            if v.get("cookies_list") or it.get("cookies_list"):
                self.cookie_file = write_cookie_file(COOKIE_DIR / f"{it['id']}.txt",
                                                     v.get("cookies_list") or it["cookies_list"])
            if self._can_native(v):
                try:
                    self._native()
                except MediaError as e:
                    if self.stop_ev.is_set():
                        raise
                    # URL expirada / bloqueio do servidor: o yt-dlp assume (ele trata vários casos especiais)
                    it["video"]["native_failed"] = str(e)[:200]
                    self.subs = []
                    if v.get("direct") and not it["url"].startswith(("http://", "https://")):
                        raise
                    self._ytdlp()
            else:
                self._ytdlp()
            if self.stop_ev.is_set():
                it["status"] = ST_PAUSED
            else:
                it["status"] = ST_COMPLETE
                it["completed_at"] = time.time()
                it["video"].pop("cookies_list", None)    # não guarda cookies além do necessário
                if self.cookie_file:
                    self.cookie_file.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            it["status"] = ST_PAUSED if self.stop_ev.is_set() else ST_ERROR
            it["error"] = str(e)[:300]
        finally:
            self.pidfile.unlink(missing_ok=True)
            self.sync()
            if self.on_finish:
                self.on_finish(self)

    def _can_native(self, v):
        if v.get("direct") and not v.get("native_failed"):
            return True
        return (not v.get("mp3") and not v.get("subs") and not v.get("playlist") and not v.get("force_ytdlp")
                and not v.get("native_failed") and all(p in NATIVE_PROTOCOLS for p in (v.get("protocols") or ["?"])))

    def _base_args(self):
        it, v = self.item, self.item["video"]
        a = extra_args(it, self.cookie_file if v.get("use_cookies") else None)
        a += ["--no-playlist"] if not v.get("playlist") else ["--yes-playlist"]
        return a

    # -- caminho nativo: nosso motor multi-conexão + ffmpeg
    def _native(self):
        it, v = self.item, self.item["video"]
        self.mode = "native"
        self.sub_done = 0
        self.phase = "obtendo endereços"
        if v.get("direct"):   # modo IDM: URLs capturadas no navegador, sem extrator
            info = {"title": v.get("filename") or it.get("title"), "ext": v.get("merge") or v["direct"][0]["ext"]}
            fmts = [{"format_id": f"d{i}", "url": d["url"], "ext": d["ext"], "protocol": "https",
                     "http_headers": dict(d.get("headers") or {}, **({"User-Agent": it["user_agent"]} if it.get("user_agent") else {}))}
                    for i, d in enumerate(v["direct"])]
        else:
            info = self.backend.run_json(self._base_args() + ["-f", v["selector"], it["url"]])
            fmts = info.get("requested_formats") or [info]
        if any(f.get("protocol") not in NATIVE_PROTOCOLS for f in fmts):
            raise MediaError("formato fragmentado")
        it["title"] = info.get("title") or it.get("title")
        work = self.temp / f"{it['id']}.streams"
        work.mkdir(parents=True, exist_ok=True)
        prev = {s["format_id"]: s for s in v.get("streams", [])}
        streams = []
        for i, f in enumerate(fmts):
            sub = prev.get(f["format_id"]) or {"id": f"{it['id']}_{i}", "format_id": f["format_id"], "segments": [],
                                                "size": -1}
            sub.update(url=f["url"], final_url=None, save_dir=str(work), filename=f"stream{i}.{f.get('ext', 'bin')}",
                       filename_locked=True, overwrite=True, headers=dict(f.get("http_headers") or {}),
                       user_agent=(f.get("http_headers") or {}).get("User-Agent", it.get("user_agent", "")),
                       referer=it.get("referer", ""), speed_limit_on=it.get("speed_limit_on"),
                       speed_limit_kbps=it.get("speed_limit_kbps"),
                       req_chunk=int(self.s.get("video_req_chunk_mb") or 10) * 1024 * 1024)
            if self.cookie_file and v.get("use_cookies"):
                sub["cookies"] = it.get("cookies", "")
            streams.append(sub)
        v["streams"] = streams
        total = sum(_size(f, info.get("duration")) for f in fmts)
        if total:
            it["size"] = total
        it["status"] = ST_DOWNLOADING
        files = []
        for sub in streams:
            out = work / sub["filename"]
            if sub.get("status") == ST_COMPLETE and out.exists():
                self.sub_done += out.stat().st_size
                files.append(out)
                continue
            self.phase = f"baixando stream {len(files) + 1}/{len(streams)}"
            d = engine.Downloader(sub, self.net, str(self.temp), self.glimit, max_conn=self.max_conn,
                                  min_segment=self.min_seg, retries=self.retries, set_mtime=False)
            self.subs.append(d)
            d.start()
            d.thread.join()
            if self.stop_ev.is_set():
                return
            if sub.get("status") != ST_COMPLETE:
                raise MediaError(sub.get("error") or "falha no stream")
            self.sub_done += out.stat().st_size
            files.append(out)
        known = sum(p.stat().st_size for p in files)
        it["size"] = known
        self.subs = []
        # mescla / remuxa
        self.phase = "mesclando vídeo e áudio" if len(files) > 1 else "finalizando"
        ext = (v.get("merge") or info.get("ext") or files[0].suffix.lstrip(".")).lower()
        dest = self._dest(info, ext)
        if len(files) == 1:
            shutil.move(str(files[0]), dest)
        else:
            cmd = self.backend.ffmpeg() + ["-y", "-loglevel", "error"]
            for f in files:
                cmd += ["-i", str(f)]
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c", "copy"]
            faststart = ["-movflags", "+faststart"] if ext == "mp4" else []
            r = subprocess.run(cmd + faststart + [str(dest)], capture_output=True, text=True)
            if r.returncode != 0:   # codec incompatível com o contêiner: MKV aceita tudo
                dest.unlink(missing_ok=True)
                dest = dest.with_suffix(".mkv")
                r = subprocess.run(cmd + [str(dest)], capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError("ffmpeg falhou ao mesclar: " + r.stderr[-200:])
        shutil.rmtree(work, ignore_errors=True)
        self._finish_file(dest)

    def _dest(self, info, ext):
        it = self.item
        name = it["video"].get("filename") or info.get("title") or "video"
        name = sanitize_filename(Path(name).stem if Path(name).suffix.lower().lstrip(".") in
                                 ("mp4", "mkv", "webm", "m4a", "mp3", "opus") else name)
        d = Path(it["save_dir"]).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return unique_path(d / f"{name}.{ext}")

    def _finish_file(self, path: Path):
        it = self.item
        it["filename"] = path.name
        it["save_dir"] = str(path.parent)
        it["size"] = path.stat().st_size
        it["downloaded"] = it["size"]

    # -- caminho yt-dlp: HLS/DASH, MP3, legendas, playlists
    def _ytdlp(self):
        it, v = self.item, self.item["video"]
        self.mode = "ytdlp"
        self.phase = "yt-dlp"
        save = Path(it["save_dir"]).expanduser()
        save.mkdir(parents=True, exist_ok=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        name = v.get("filename")
        tmpl = (sanitize_filename(Path(name).stem) + ".%(ext)s") if name and not v.get("playlist") else \
            "%(title).150B [%(id)s].%(ext)s"
        if v.get("playlist"):
            tmpl = "%(playlist_title).80B/%(playlist_index)03d - " + tmpl
        args = self._base_args() + [
            "-f", v["selector"], "-N", str(self.max_conn), "--newline", "--progress", "--progress-template",
            PROGRESS_TEMPLATE, "--print", f"after_move:{FILE_MARK} %(filepath)s", "-P", str(save),
            "-P", f"temp:{self.temp / (it['id'] + '.ytdlp')}", "-o", tmpl, "--no-mtime", "--continue"]
        if v.get("merge"):
            args += ["--merge-output-format", v["merge"]]
        if v.get("mp3"):
            args += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        if v.get("subs"):
            args += ["--write-subs", "--write-auto-subs", "--sub-langs", self.s.get("video_sub_langs") or "pt.*,en.*",
                     "--embed-subs", "--convert-subs", "srt"]
        kbps = it.get("speed_limit_kbps") if it.get("speed_limit_on") else (
            self.s.get("speed_limit_kbps") if self.s.get("speed_limiter_on") else 0)
        if kbps:
            args += ["-r", f"{int(kbps)}K"]
        args.append(it["url"])
        it["status"] = ST_DOWNLOADING
        self.proc = self.backend.popen(args, self.pidfile)
        errs = deque(maxlen=12)
        t = threading.Thread(target=lambda: [errs.append(ln.rstrip()) for ln in self.proc.stderr], daemon=True)
        t.start()
        last_file = None
        for ln in self.proc.stdout:
            ln = ln.rstrip("\n")
            if ln.startswith(PROG):
                self._parse_progress(ln[len(PROG) + 1:])
            elif ln.startswith(FILE_MARK):
                last_file = ln[len(FILE_MARK) + 1:].strip()
                self.phase = "concluído"
            elif "[Merger]" in ln or "[VideoRemuxer]" in ln:
                self.phase = "mesclando"
            elif "[ExtractAudio]" in ln:
                self.phase = "convertendo áudio"
        self.proc.wait()
        t.join(2)
        for pipe in (self.proc.stdout, self.proc.stderr):
            pipe.close()
        if self.stop_ev.is_set():
            return
        if self.proc.returncode != 0:
            msg = next((e for e in reversed(errs) if "ERROR" in e), errs[-1] if errs else "yt-dlp falhou")
            raise MediaError(msg.replace("ERROR: ", ""))
        if last_file and Path(last_file).exists():
            self._finish_file(Path(last_file))
        shutil.rmtree(self.temp / (it["id"] + ".ytdlp"), ignore_errors=True)

    def _parse_progress(self, data):
        try:
            status, dl, tot, est, _spd, _eta, fid = (data.split("|") + [""] * 7)[:7]
            num = lambda x: float(x) if x not in ("NA", "None", "") else 0.0  # noqa: E731
            total = num(tot) or num(est)
            self._yt[fid] = (num(dl), total)
            self.phase = "baixando" if status == "downloading" else status
            size = sum(t for _d, t in self._yt.values())
            if size > (self.item.get("size") or 0) or not self.item.get("video", {}).get("est_size"):
                self.item["size"] = int(size)
        except ValueError:
            pass


# =============================================================== criação de itens
def candidates_from(payload):
    """Ordem de tentativa: documento do player (iframe/embed), página, src direto."""
    src = payload.get("src") or ""
    out = [payload.get("frame_url"), payload.get("page_url"), payload.get("url")]
    if src.startswith(("http://", "https://")):
        out.append(src)
    return [u for i, u in enumerate(out) if u and u not in out[:i]]


def video_folder(settings, audio=False):
    if settings.get("video_folder") and not audio:
        return settings["video_folder"]
    want = "Músicas" if audio else "Vídeos"
    for c in settings["categories"]:
        if c["name"] == want:
            return c["folder"]
    return settings["general_folder"]


def add_choice(m, info, choice, payload, filename=None, folder=None, subs=False, playlist=False, start=True,
               queue_id=None):
    """Cria o item de vídeo no gerenciador a partir de uma opção de build_choices()."""
    audio = choice["kind"] == "audio"
    title = info.get("title") or "video"
    name = sanitize_filename(filename or title)
    v = {"selector": choice["selector"], "merge": choice.get("merge"), "protocols": choice.get("protocols") or [],
         "mp3": bool(choice.get("mp3")), "subs": subs, "playlist": playlist, "filename": name,
         "use_cookies": bool(info.get("_ldm_cookies")), "cookies_list": payload.get("cookies") or [],
         "est_size": choice.get("size") or 0, "thumbnail": info.get("thumbnail", ""),
         "duration": info.get("duration"), "extractor": info.get("extractor_key", ""), "quality": choice["label"]}
    extra = {"video": v, "size": choice.get("size") or -1, "title": title}
    return m.add(info["_ldm_source"], filename=f"{name}.{choice['ext'].lower()}",
                 save_dir=folder or video_folder(m.s, audio), start=start, queue_id=queue_id,
                 referer=payload.get("page_url", ""), user_agent=payload.get("user_agent", ""),
                 description=title, kind="video", category="Músicas" if audio else "Vídeos",
                 duplicate="number", extra=extra)


def add_stream(m, stream, payload, start=True, queue_id=None):
    """Stream capturado pelo navegador (HLS/DASH/arquivo) quando o yt-dlp não reconhece a página."""
    url = stream["url"]
    title = sanitize_filename(payload.get("title") or "video")
    hdr_cookies = "; ".join(f"{c['name']}={c['value']}" for c in payload.get("cookies") or [])
    if stream.get("type") in ("HLS", "DASH") or ".m3u8" in url or ".mpd" in url:
        info = {"title": title, "_ldm_source": url, "_ldm_cookies": bool(payload.get("cookies"))}
        choice = {"kind": "video", "label": "Stream", "ext": "MP4", "selector": "bv*+ba/b", "merge": "mp4",
                  "protocols": ["m3u8"], "size": stream.get("size") or 0}
        return add_choice(m, info, choice, payload, start=start, queue_id=queue_id)
    ext = (url.split("?")[0].rsplit(".", 1)[-1] if "." in url.split("?")[0].rsplit("/", 1)[-1] else "mp4")[:5]
    return m.add(url, filename=f"{title}.{ext}", save_dir=video_folder(m.s), start=start, queue_id=queue_id,
                 referer=payload.get("page_url", ""), cookies=hdr_cookies, user_agent=payload.get("user_agent", ""),
                 description=title, category="Vídeos", duplicate="number")


def best_passive(choices, max_height=0):
    """Melhor opção capturada: a do player clicado, respeitando a qualidade padrão."""
    vids = [c for c in choices if c["kind"] == "video"]
    if not vids:
        return choices[0] if choices else None
    pool = [c for c in vids if c.get("match")] or vids
    if max_height:
        ok = [c for c in pool if c["label"][:1].isdigit() and int(c["label"].split("p")[0]) <= max_height]
        if ok:
            return ok[0]
    return pool[0]


def quick_add(m, payload):
    """Sem diálogo: yt-dlp na qualidade padrão; se falhar, o melhor stream capturado (modo IDM)."""
    err = None
    try:
        if m.s.get("video_mode") == "capture":
            raise MediaError("modo só captura")
        info = probe(Backend(m.s), candidates_from(payload), payload, payload.get("cookies"))
        ch = build_choices(info, m.s.get("video_prefer_mp4", True))
        c = default_choice(ch, int(m.s.get("video_max_height") or 0))
        if c:
            return add_choice(m, info, c, payload, subs=m.s.get("video_subs", False))
    except MediaError as e:
        err = str(e)
    c = best_passive(passive_choices(payload), int(m.s.get("video_max_height") or 0))
    if c:
        return add_passive(m, c, payload)
    if sabr_only(payload):
        raise MediaError("o YouTube usou SABR (sem links reaproveitáveis) e o yt-dlp falhou: " + (err or ""))
    raise MediaError(err or "nenhum vídeo encontrado nesta página")


# =============================================================== modo IDM: streams capturados no navegador
# itag do YouTube/googlevideo -> (altura, fps, codec). Fonte: tabela pública de formatos do YouTube.
YT_ITAGS = {
    "18": (360, 30, "H.264+AAC"), "22": (720, 30, "H.264+AAC"),
    "160": (144, 30, "H.264"), "133": (240, 30, "H.264"), "134": (360, 30, "H.264"), "135": (480, 30, "H.264"),
    "136": (720, 30, "H.264"), "137": (1080, 30, "H.264"), "264": (1440, 30, "H.264"), "266": (2160, 30, "H.264"),
    "298": (720, 60, "H.264"), "299": (1080, 60, "H.264"),
    "278": (144, 30, "VP9"), "242": (240, 30, "VP9"), "243": (360, 30, "VP9"), "244": (480, 30, "VP9"),
    "247": (720, 30, "VP9"), "248": (1080, 30, "VP9"), "271": (1440, 30, "VP9"), "313": (2160, 30, "VP9"),
    "302": (720, 60, "VP9"), "303": (1080, 60, "VP9"), "308": (1440, 60, "VP9"), "315": (2160, 60, "VP9"),
    "394": (144, 30, "AV1"), "395": (240, 30, "AV1"), "396": (360, 30, "AV1"), "397": (480, 30, "AV1"),
    "398": (720, 60, "AV1"), "399": (1080, 60, "AV1"), "400": (1440, 60, "AV1"), "401": (2160, 60, "AV1"),
}
YT_AUDIO = {"139": (48, "AAC"), "140": (128, "AAC"), "141": (256, "AAC"), "249": (50, "Opus"), "250": (70, "Opus"),
            "251": (160, "Opus"), "599": (30, "AAC"), "600": (35, "Opus")}


def mime_ext(mime: str, kind="video"):
    m = (mime or "").lower()
    if "webm" in m:
        return "webm"
    if m.startswith("audio/mp4") or m == "audio/m4a":
        return "m4a"
    if "mpeg" in m and m.startswith("audio"):
        return "mp3"
    if "ogg" in m:
        return "ogg"
    if "flv" in m:
        return "flv"
    if "quicktime" in m:
        return "mov"
    return "m4a" if kind == "audio" else "mp4"


def cookie_header(cookies, url):
    """Monta o cabeçalho Cookie com os cookies do navegador que valem para a URL."""
    from urllib.parse import urlsplit
    p = urlsplit(url)
    host, path = (p.hostname or "").lower(), p.path or "/"
    out = []
    for c in cookies or []:
        dom = (c.get("domain") or "").lower()
        ok = host == dom.lstrip(".") or (not c.get("hostOnly") and host.endswith("." + dom.lstrip(".")))
        if ok and path.startswith(c.get("path") or "/") and (p.scheme == "https" or not c.get("secure")):
            out.append(f"{c.get('name')}={c.get('value')}")
    return "; ".join(out)


def _stream_headers(s, payload):
    h = {}
    sh = s.get("headers") or {}
    ref = sh.get("referer") or payload.get("page_url") or ""
    if ref:
        h["Referer"] = ref
    if sh.get("origin"):
        h["Origin"] = sh["origin"]
    ck = cookie_header(payload.get("cookies"), s.get("url", ""))
    if ck:
        h["Cookie"] = ck
    return h


def parse_mpd(text, base):
    """MPD com arquivos únicos por representação (BaseURL), como Instagram/Facebook embutem no JSON.
    Retorna (vídeos, áudios) com url, altura, banda, codec e mime."""
    import xml.etree.ElementTree as ET
    from urllib.parse import urljoin
    root = ET.fromstring(text.encode() if isinstance(text, str) else text)
    ns = lambda tag: f"{{{root.tag.split('}')[0].strip('{')}}}{tag}" if root.tag.startswith("{") else tag  # noqa: E731
    vids, auds = [], []
    mpd_base = root.findtext(ns("BaseURL")) or ""
    for period in root.iter(ns("Period")):
        pbase = urljoin(urljoin(base, mpd_base), period.findtext(ns("BaseURL")) or "")
        for aset in period.iter(ns("AdaptationSet")):
            abase = urljoin(pbase, aset.findtext(ns("BaseURL")) or "")
            amime = aset.get("mimeType") or ""
            ctype = aset.get("contentType") or amime.split("/")[0]
            for rep in aset.iter(ns("Representation")):
                b = rep.findtext(ns("BaseURL"))
                if not b:
                    continue   # SegmentTemplate/SegmentList: precisa do manifest por URL (yt-dlp/ffmpeg)
                mime = rep.get("mimeType") or amime
                kind = "audio" if (ctype == "audio" or mime.startswith("audio")) else "video"
                d = {"url": urljoin(abase, b.strip()), "mime": mime, "height": int(rep.get("height") or 0),
                     "bandwidth": int(rep.get("bandwidth") or 0), "codecs": rep.get("codecs") or "",
                     "fps": rep.get("frameRate") or ""}
                (auds if kind == "audio" else vids).append(d)
    return vids, auds


def _dur_match(s, hint):
    d = (hint or {}).get("duration") or 0
    return bool(d and s.get("dur") and abs(float(s["dur"]) - float(d)) <= 2.5)


def passive_choices(payload) -> list[dict]:
    """Opções de download a partir do que a extensão capturou (modo IDM, sem extrator)."""
    sn = [s for s in payload.get("sniffed") or [] if isinstance(s, dict)]
    hint = payload.get("video_hint") or {}
    out = []

    def direct(s, kind="video"):
        return {"url": s["url"], "ext": mime_ext(s.get("type", ""), kind), "headers": _stream_headers(s, payload)}

    # 1) googlevideo (YouTube): vídeo e áudio separados por itag, agrupados por vídeo
    groups = {}
    for s in sn:
        if str(s.get("key", "")).startswith("gv:") and s.get("url"):
            groups.setdefault(s.get("group") or "gv", []).append(s)
    for g, items in groups.items():
        match = any(_dur_match(i, hint) for i in items)
        auds = [i for i in items if i.get("kind") == "audio"]
        best_a = max(auds, key=lambda a: (YT_AUDIO.get(str(a.get("itag")), (0, ""))[1] == "AAC",
                                          YT_AUDIO.get(str(a.get("itag")), (a.get("size") or 0, ""))[0]), default=None)
        vids = [i for i in items if i.get("kind") == "video"]
        vids.sort(key=lambda v: (YT_ITAGS.get(str(v.get("itag")), (0,))[0], v.get("size") or 0), reverse=True)
        for v in vids:
            h, fps, codec = YT_ITAGS.get(str(v.get("itag")), (0, 30, ""))
            muxed = "+" in codec
            streams = [direct(v)] + ([direct(best_a, "audio")] if best_a and not muxed else [])
            vext = streams[0]["ext"]
            aext = streams[1]["ext"] if len(streams) > 1 else ""
            if not aext:
                merge = vext
            else:
                merge = "mp4" if vext == "mp4" and aext == "m4a" else ("webm" if vext == "webm" and aext == "webm" else "mkv")
            size = (v.get("size") or 0) + ((best_a.get("size") or 0) if len(streams) > 1 else 0)
            label = (f"{h}p" + (str(fps) if fps > 30 else "")) if h else f"itag {v.get('itag')}"
            if hint.get("duration") and not match and v.get("dur"):
                label += f" · outro vídeo ({int(float(v['dur'])) // 60}:{int(float(v['dur'])) % 60:02d})"   # anúncio/prévia
            out.append({"kind": "video", "source": "passive", "label": label, "ext": merge.upper(),
                        "codec": codec + (f" + {YT_AUDIO.get(str(best_a.get('itag')), (0, ''))[1]}" if len(streams) > 1 else ""),
                        "size": size, "direct": streams, "merge": merge, "match": match, "group": g})
        if best_a:
            out.append({"kind": "audio", "source": "passive", "label": "Somente áudio", "ext": direct(best_a, "audio")["ext"].upper(),
                        "codec": YT_AUDIO.get(str(best_a.get("itag")), (0, ""))[1], "size": best_a.get("size") or 0,
                        "direct": [direct(best_a, "audio")], "merge": None, "match": match, "group": g})
    # 2) MPD embutido no JSON (Instagram/Facebook) com arquivos por representação
    for s in sn:
        if s.get("manifest_text"):
            try:
                vids, auds = parse_mpd(s["manifest_text"], s.get("base") or payload.get("page_url", ""))
            except Exception:  # noqa: BLE001 - manifest malformado: ignora
                continue
            best_a = max(auds, key=lambda a: a["bandwidth"], default=None)
            for v in sorted(vids, key=lambda v: (v["height"], v["bandwidth"]), reverse=True):
                streams = [{"url": v["url"], "ext": mime_ext(v["mime"]), "headers": _stream_headers(v, payload)}]
                if best_a:
                    streams.append({"url": best_a["url"], "ext": mime_ext(best_a["mime"], "audio"),
                                    "headers": _stream_headers(best_a, payload)})
                out.append({"kind": "video", "source": "passive", "label": f"{v['height']}p" if v["height"] else "DASH",
                            "ext": "MP4", "codec": v["codecs"].split(".")[0], "size": 0, "direct": streams,
                            "merge": "mp4" if all(x["ext"] in ("mp4", "m4a") for x in streams) else "mkv",
                            "match": False, "group": "mpd"})
    # 3) manifests por URL (HLS/DASH): o yt-dlp (ou ffmpeg) baixa todos os segmentos
    mans = [s for s in sn if s.get("kind") == "manifest" and s.get("url") and not s.get("manifest_text")]
    for s in reversed(mans):   # o mais antigo primeiro: costuma ser a playlist mestre
        name = s["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1][:50]
        out.append({"kind": "video", "source": "passive", "label": f"{s.get('type', 'Stream')}: {name}", "ext": "MP4",
                    "codec": "", "size": 0, "stream": s, "match": False, "group": "manifest"})
    # 4) arquivos de mídia (inclusive remontados de fatias Range)
    for s in sn:
        k = str(s.get("key", ""))
        if (k.startswith("f:") or k.startswith("p:")) and s.get("kind") in ("video", "audio", "media") and s.get("url"):
            if hint.get("current_src") and hint["current_src"] == s["url"]:
                s["match"] = True
            name = s["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1][:50] or "mídia"
            kind = "audio" if s.get("kind") == "audio" else "video"
            out.append({"kind": kind, "source": "passive", "label": name, "ext": mime_ext(s.get("type", ""), kind).upper(),
                        "codec": s.get("type", ""), "size": s.get("size") if (s.get("size") or 0) > 0 else 0,
                        "direct": [direct(s, kind)], "merge": None, "match": bool(s.get("match")), "group": k})
    # vídeo do player clicado primeiro, depois maior qualidade/tamanho
    out.sort(key=lambda c: (not c.get("match"), c["kind"] != "video"))
    return out


def sabr_only(payload):
    """True quando o YouTube entregou o vídeo só por SABR/UMP (sem URLs reaproveitáveis)."""
    sn = payload.get("sniffed") or []
    return any(s.get("kind") == "sabr" for s in sn) and not any(str(s.get("key", "")).startswith("gv:") for s in sn)


def add_passive(m, choice, payload, filename=None, folder=None, start=True, queue_id=None):
    """Item de vídeo a partir de streams capturados: baixa direto (multi-conexão) e mescla com ffmpeg."""
    if choice.get("stream"):
        return add_stream(m, choice["stream"], payload, start=start, queue_id=queue_id)
    audio = choice["kind"] == "audio"
    title = sanitize_filename(filename or payload.get("title") or "video")
    ext = (choice.get("merge") or choice["direct"][0]["ext"]).lower()
    v = {"direct": choice["direct"], "merge": choice.get("merge"), "protocols": ["https"] * len(choice["direct"]),
         "mp3": False, "subs": False, "playlist": False, "filename": title, "use_cookies": False,
         "cookies_list": payload.get("cookies") or [], "est_size": choice.get("size") or 0, "quality": choice["label"],
         "selector": _fallback_selector(choice), "source": "navegador"}
    page = payload.get("page_url") or choice["direct"][0]["url"]
    return m.add(page, filename=f"{title}.{ext}", save_dir=folder or video_folder(m.s, audio), start=start,
                 queue_id=queue_id, referer=payload.get("page_url", ""), user_agent=payload.get("user_agent", ""),
                 description=title, kind="video", category="Músicas" if audio else "Vídeos", duplicate="number",
                 extra={"video": v, "size": choice.get("size") or -1, "title": title})


def _fallback_selector(choice):
    """Se os links capturados expirarem, o yt-dlp tenta a mesma qualidade a partir da página."""
    if choice["kind"] == "audio":
        return "ba/b"
    lb = choice.get("label", "")
    h = lb.split("p")[0] if lb[:1].isdigit() else ""
    return f"bv*[height<={h}]+ba/b[height<={h}]/b" if h.isdigit() else "bv*+ba/b"
