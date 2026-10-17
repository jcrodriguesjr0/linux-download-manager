"""Camada de rede: requisições HTTP(S)/FTP com Range, proxy, logins por site e limitador de velocidade."""
import base64
import fnmatch
import ftplib
import io
import ssl
import threading
import time
import urllib.request
import zipfile
from urllib.parse import unquote, urlsplit

_SSL = ssl.create_default_context()


class SpeedLimiter:
    """Token bucket. rate_bps=0 desliga. Compartilhável entre threads (global) ou por arquivo."""

    def __init__(self, rate_bps: int = 0):
        self.rate = rate_bps
        self._tokens = 0.0
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def set_rate(self, rate_bps: int):
        with self._lock:
            self.rate = max(0, int(rate_bps))
            self._tokens = 0.0

    def consume(self, n: int, stop: threading.Event | None = None):
        while True:
            with self._lock:
                if self.rate <= 0:
                    return
                now = time.monotonic()
                self._tokens = min(self.rate, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= n or self._tokens >= self.rate:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self.rate
            if stop is not None and stop.wait(min(wait, 0.25)):
                return
            if stop is None:
                time.sleep(min(wait, 0.25))


class NetConfig:
    """Snapshot das configurações de rede usadas pelo motor."""

    def __init__(self, settings=None):
        def g(k, d=None):
            v = settings.get(k) if settings is not None else None
            return d if v is None else v
        self.timeout = g("timeout", 30)
        self.proxy_mode = g("proxy_mode", "none")
        self.proxy_http = g("proxy_http", "")
        self.proxy_https = g("proxy_https", "")
        self.proxy_bypass = g("proxy_bypass", "")
        self.ftp_passive = g("ftp_passive", True)
        self.site_logins = g("site_logins", []) or []
        self.user_agent = g("user_agent", "")

    def login_for(self, url: str):
        p = urlsplit(url)
        target = f"{p.hostname or ''}{p.path}".lower()
        for lg in self.site_logins:
            pat = lg.get("server", "").lower().split("://")[-1]
            if pat and (fnmatch.fnmatchcase(target, pat + "*") or fnmatch.fnmatchcase(p.hostname or "", pat)):
                return lg.get("user", ""), lg.get("password", "")
        return None

    def opener(self):
        handlers = [urllib.request.HTTPSHandler(context=_SSL)]
        if self.proxy_mode == "none":
            handlers.append(urllib.request.ProxyHandler({}))
        elif self.proxy_mode == "manual":
            proxies = {}
            if self.proxy_http:
                proxies["http"] = self.proxy_http if "://" in self.proxy_http else "http://" + self.proxy_http
            if self.proxy_https:
                proxies["https"] = self.proxy_https if "://" in self.proxy_https else "http://" + self.proxy_https
            handlers.append(urllib.request.ProxyHandler(proxies))
        # "system": ProxyHandler padrão lê http_proxy/https_proxy/no_proxy do ambiente
        return urllib.request.build_opener(*handlers)


def build_headers(item: dict, net: NetConfig, start: int | None = None, end: int | None = None) -> dict:
    h = {"User-Agent": item.get("user_agent") or net.user_agent or "Mozilla/5.0", "Accept": "*/*",
         "Accept-Encoding": "identity"}
    if item.get("referer"):
        h["Referer"] = item["referer"]
    if item.get("cookies"):
        h["Cookie"] = item["cookies"]
    auth = (item.get("auth_user"), item.get("auth_pass")) if item.get("auth_user") else net.login_for(item["url"])
    if auth and auth[0]:
        h["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    for k, v in (item.get("headers") or {}).items():
        h[k] = v
    if start is not None:
        h["Range"] = f"bytes={start}-" + ("" if end is None else str(end))
    return h


def http_open(url: str, item: dict, net: NetConfig, start=None, end=None, method="GET"):
    req = urllib.request.Request(url, headers=build_headers(item, net, start, end), method=method)
    if item.get("post_data") and method == "GET":
        req.data = item["post_data"].encode() if isinstance(item["post_data"], str) else item["post_data"]
    return net.opener().open(req, timeout=net.timeout)


# ---------- FTP ----------

class FtpStream:
    """Fluxo FTP binário com REST (retomada/segmentos)."""

    def __init__(self, url: str, item: dict, net: NetConfig, start: int = 0):
        p = urlsplit(url)
        user = unquote(p.username) if p.username else None
        pwd = unquote(p.password) if p.password else None
        if not user:
            lg = (item.get("auth_user"), item.get("auth_pass")) if item.get("auth_user") else net.login_for(url)
            user, pwd = (lg if lg and lg[0] else ("anonymous", "ldm@localhost"))
        self.ftp = ftplib.FTP(timeout=net.timeout)
        self.ftp.connect(p.hostname, p.port or 21)
        self.ftp.login(user, pwd or "")
        self.ftp.set_pasv(net.ftp_passive)
        self.ftp.voidcmd("TYPE I")
        self.path = unquote(p.path)
        try:
            self.size = self.ftp.size(self.path)
        except ftplib.all_errors:
            self.size = None
        self.conn = self.ftp.transfercmd(f"RETR {self.path}", rest=start or None)
        self.status = 206 if start else 200
        self.headers = {}

    def read(self, n: int) -> bytes:
        return self.conn.recv(n)

    def geturl(self):
        return None

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.ftp.close()
        except Exception:
            pass


def open_stream(url: str, item: dict, net: NetConfig, start=None, end=None):
    """Abre um fluxo (HTTP/FTP) já posicionado. Retorna objeto com read/close/status/headers/geturl."""
    if url.lower().startswith("ftp://"):
        return FtpStream(url, item, net, start or 0)
    return http_open(url, item, net, start, end)


# ---------- Prévia de ZIP remoto (Downloads -> Zip preview) ----------

class RemoteFile(io.RawIOBase):
    """Arquivo somente-leitura e seekable sobre HTTP Range; permite zipfile listar sem baixar tudo."""

    def __init__(self, url, item, net, size):
        self.url, self.item, self.net, self.size, self.pos = url, item, net, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.size, self.pos + len(b)) - 1
        with http_open(self.url, self.item, self.net, self.pos, end) as r:
            data = r.read(end - self.pos + 1)
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def zip_preview(url: str, item: dict, net: NetConfig, size: int):
    with zipfile.ZipFile(io.BufferedReader(RemoteFile(url, item, net, size), 256 * 1024)) as z:
        return [(i.filename, i.file_size, i.compress_size) for i in z.infolist()]
