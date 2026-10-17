"""Site Grabber: explora páginas a partir de um endereço e coleta arquivos que casam com os filtros.

Cobre as opções principais do assistente do IDM: níveis de links, ficar no domínio/caminho base,
não subir para diretórios pais, filtros de tipos, incluir/excluir caminhos e faixa de tamanho.
"""
import fnmatch
import threading
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from . import net
from .util import ext_of, match_ext

PAGE_TYPES = ("text/html", "application/xhtml")
PAGE_EXTS = {"", "html", "htm", "php", "asp", "aspx", "jsp", "shtml", "cgi"}

# Modelos de projeto equivalentes aos "Project template" do IDM
TEMPLATES = {
    "Todos os arquivos": "*",
    "Imagens": "jpg jpeg png gif webp bmp svg",
    "Vídeos": "mp4 mkv webm avi mov flv m4v mpg mpeg wmv",
    "Áudio": "mp3 m4a aac ogg opus flac wav wma",
    "Documentos": "pdf doc docx ppt pptx xls xlsx odt epub txt",
    "Compactados": "zip rar 7z gz bz2 xz tar r0* r1*",
    "Site completo (offline)": "*",
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []   # (url, texto)
        self._a = None
        self._txt = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._a, self._txt = a["href"], []
        for key in ("src", "data-src"):
            if a.get(key) and tag in ("img", "video", "audio", "source", "embed", "iframe", "frame", "script"):
                self.links.append((a[key], ""))
        if tag == "link" and a.get("href"):
            self.links.append((a["href"], ""))

    def handle_data(self, data):
        if self._a is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.links.append((self._a, " ".join("".join(self._txt).split())))
            self._a = None


def extract_links(html: str, base: str):
    p = LinkParser()
    try:
        p.feed(html)
    except Exception:  # HTML quebrado: aproveita o que já foi lido
        pass
    out, seen = [], set()
    for href, text in p.links:
        if href.startswith(("javascript:", "mailto:", "data:", "#", "tel:")):
            continue
        u = urldefrag(urljoin(base, href.strip()))[0]
        if u.startswith(("http://", "https://", "ftp://")) and u not in seen:
            seen.add(u)
            out.append((u, text))
    return out


def _in_list(url, patterns: str) -> bool:
    for p in [x.strip() for x in patterns.replace(",", ";").split(";") if x.strip()]:
        target = url.split("://", 1)[-1]
        if fnmatch.fnmatchcase(target, p if "*" in p else p + "*") or fnmatch.fnmatchcase(urlsplit(url).hostname or "", p):
            return True
    return False


class Grabber:
    def __init__(self, start_url, netcfg: net.NetConfig, file_types="*", levels=1, external_levels=0,
                 same_domain_only=True, no_parent=True, explore_include="", explore_exclude="",
                 download_include="", download_exclude="", exclude_types="", min_size=0, max_size=0,
                 check_sizes=False, max_pages=500, threads=4, auth=None, on_progress=None):
        self.start = start_url
        self.net = netcfg
        self.types = file_types.strip() or "*"
        self.exclude_types = exclude_types
        self.levels = levels
        self.ext_levels = external_levels
        self.same_domain = same_domain_only
        self.no_parent = no_parent
        self.ex_inc, self.ex_exc = explore_include, explore_exclude
        self.dl_inc, self.dl_exc = download_include, download_exclude
        self.min_size, self.max_size = min_size, max_size
        self.check_sizes = check_sizes or bool(min_size or max_size)
        self.max_pages = max_pages
        self.threads = max(1, min(threads, 10))
        self.item = {"url": start_url, "auth_user": (auth or ("", ""))[0], "auth_pass": (auth or ("", ""))[1]}
        self.on_progress = on_progress
        self.stop_ev = threading.Event()
        self.pages = 0
        self.files: list[dict] = []
        sp = urlsplit(start_url)
        self.base_host = sp.hostname or ""
        self.base_domain = ".".join(self.base_host.split(".")[-2:])
        self.base_path = sp.path.rsplit("/", 1)[0] + "/"

    def stop(self):
        self.stop_ev.set()

    def _is_page(self, url):
        return ext_of(urlsplit(url).path.rsplit("/", 1)[-1]) in PAGE_EXTS

    def _wanted_file(self, url):
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        if self.types != "*" and not match_ext(name, self.types):
            return False
        if self.exclude_types and match_ext(name, self.exclude_types):
            return False
        if self.dl_inc and not _in_list(url, self.dl_inc):
            return False
        if self.dl_exc and _in_list(url, self.dl_exc):
            return False
        return bool(name) and not self._is_page(url) or self.types == "*"

    def _may_explore(self, url, depth_ext):
        sp = urlsplit(url)
        host = sp.hostname or ""
        internal = host == self.base_host or (not self.same_domain and host.endswith(self.base_domain))
        if not internal and depth_ext > self.ext_levels:
            return False
        if internal and self.no_parent and not sp.path.startswith(self.base_path):
            return False
        if self.ex_inc and not _in_list(url, self.ex_inc):
            return False
        if self.ex_exc and _in_list(url, self.ex_exc):
            return False
        return True

    def _fetch_page(self, url):
        with net.http_open(url, self.item, self.net) as r:
            ctype = r.headers.get("Content-Type", "")
            if not any(t in ctype for t in PAGE_TYPES):
                return None, r.geturl(), ctype, int(r.headers.get("Content-Length") or -1)
            raw = r.read(5 * 1024 * 1024)
            charset = r.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace"), r.geturl(), ctype, len(raw)

    def _size_of(self, url):
        try:
            with net.http_open(url, self.item, self.net, method="HEAD") as r:
                return int(r.headers.get("Content-Length") or -1)
        except Exception:
            return -1

    def run(self):
        """Busca em largura. Retorna lista de dicts {url, referer, text, size}."""
        seen_pages, seen_files = set(), set()
        q = deque([(self.start, 0, 0, "")])
        while q and not self.stop_ev.is_set() and self.pages < self.max_pages:
            url, depth, depth_ext, ref = q.popleft()
            if url in seen_pages:
                continue
            seen_pages.add(url)
            try:
                html, final, ctype, size = self._fetch_page(url)
            except Exception:
                continue
            self.pages += 1
            if html is None:   # o "página" era um arquivo
                if url not in seen_files and self._wanted_file(url):
                    seen_files.add(url)
                    self.files.append({"url": url, "referer": ref, "text": "", "size": size})
                continue
            for link, text in extract_links(html, final):
                if self.stop_ev.is_set():
                    break
                host = urlsplit(link).hostname or ""
                external = host != self.base_host
                if self._is_page(link):
                    nd, ne = depth + 1, depth_ext + (1 if external else 0)
                    if nd <= self.levels and self._may_explore(link, ne) and link not in seen_pages:
                        q.append((link, nd, ne, final))
                    if self.types == "*" and link not in seen_files and not external:
                        seen_files.add(link)
                        self.files.append({"url": link, "referer": final, "text": text, "size": -1})
                elif link not in seen_files and self._wanted_file(link):
                    seen_files.add(link)
                    self.files.append({"url": link, "referer": final, "text": text, "size": -1})
            if self.on_progress:
                self.on_progress(self.pages, len(self.files))
        if self.check_sizes and not self.stop_ev.is_set():
            from concurrent.futures import ThreadPoolExecutor
            todo = [f for f in self.files if f["size"] < 0]
            with ThreadPoolExecutor(self.threads) as ex:
                for f, sz in zip(todo, ex.map(lambda f: self._size_of(f["url"]), todo)):
                    f["size"] = sz
            if self.min_size or self.max_size:
                self.files = [f for f in self.files if f["size"] < 0 or (
                    f["size"] >= self.min_size and (not self.max_size or f["size"] <= self.max_size))]
        return self.files
