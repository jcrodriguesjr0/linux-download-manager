"""Utilitários: formatação, nomes de arquivo, curingas, download em lote e import/export (.ef2 / .txt)."""
import fnmatch
import os
import re
import shutil
import string
import threading
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urlsplit


def fmt_size(n) -> str:
    if n is None or n < 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024


def fmt_rate(bps) -> str:
    return f"{fmt_size(bps)}/s" if bps and bps > 0 else ""


def fmt_eta(sec) -> str:
    if sec is None or sec < 0 or sec == float("inf"):
        return ""
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s" if m else f"{s}s"


_BAD = re.compile(r'[\x00-\x1f/\\:*?"<>|]')


def sanitize_filename(name: str) -> str:
    name = _BAD.sub("_", name).strip(" .")
    return name[:240] or "download"


def filename_from_headers(url: str, headers) -> str:
    cd = headers.get("Content-Disposition") if headers else None
    if cd:
        m = Message()
        m["content-disposition"] = cd
        fn = m.get_filename()
        if fn:
            return sanitize_filename(unquote(os.path.basename(fn)))
    path = urlsplit(url).path
    base = unquote(os.path.basename(path.rstrip("/"))) if path else ""
    return sanitize_filename(base or urlsplit(url).hostname or "download")


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def match_ext(name: str, patterns: str) -> bool:
    """patterns: 'zip rar r0*' (separados por espaço/vírgula); suporta curinga como no IDM."""
    ext = ext_of(name)
    if not ext:
        return False
    for p in re.split(r"[\s,;]+", patterns.lower()):
        if p and fnmatch.fnmatchcase(ext, p.lstrip(".")):
            return True
    return False


def match_site(url_or_host: str, patterns: str) -> bool:
    """Casa host/endereço com lista de padrões com '*' (ex.: '*.google.com youtube.com')."""
    target = url_or_host.lower()
    host = urlsplit(target).hostname or target if "://" in target else target
    for p in re.split(r"[\s;]+", patterns.lower()):
        if not p:
            continue
        if "/" in p or "://" in p:
            if fnmatch.fnmatchcase(target, p if "*" in p else p + "*"):
                return True
        elif fnmatch.fnmatchcase(host, p) or host == p or host.endswith("." + p.lstrip("*.")):
            return True
    return False


def unique_path(path: Path) -> Path:
    """Gera 'arquivo_2.ext', 'arquivo_3.ext'... como a opção 'numbered file name' do IDM."""
    if not path.exists():
        return path
    stem, suf = path.stem, path.suffix
    i = 2
    while True:
        p = path.with_name(f"{stem}_{i}{suf}")
        if not p.exists():
            return p
        i += 1


_CLAIM_LOCK = threading.Lock()


def claim_path(path: Path, overwrite=False) -> Path:
    """Reserva o nome final criando o arquivo vazio de forma atômica, para dois downloads com o mesmo
    nome que terminam juntos não gravarem um por cima do outro."""
    with _CLAIM_LOCK:
        p = path if overwrite else unique_path(path)
        while True:
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o644)
                os.close(fd)
                return p
            except FileExistsError:
                if overwrite:
                    return p
                p = unique_path(p)


def move_into(src, dest):
    """Move substituindo o destino (inclusive o arquivo reservado); funciona no Linux e no Windows."""
    try:
        os.replace(src, dest)
    except OSError:                   # outro disco/partição
        shutil.copy2(src, dest)
        os.remove(src)


def category_for(name: str, url: str, categories) -> dict | None:
    for c in categories:
        if c.get("sites") and not match_site(url, c["sites"]):
            continue
        if match_ext(name, c.get("exts", "")):
            return c
    return None


# ---------- Download em lote (Tasks -> Add batch download) ----------

def batch_urls(pattern: str, start: str, end: str, width: int = 0) -> list[str]:
    """Substitui o '*' do padrão por uma sequência numérica (com zeros à esquerda) ou de letras a..z."""
    if "*" not in pattern:
        return [pattern]
    if start.isdigit() and end.isdigit():
        a, b = int(start), int(end)
        step = 1 if b >= a else -1
        return [pattern.replace("*", str(i).zfill(width), 1) for i in range(a, b + step, step)]
    if len(start) == 1 and len(end) == 1 and start.isalpha() and end.isalpha():
        letters = string.ascii_lowercase if start.islower() else string.ascii_uppercase
        a, b = letters.index(start), letters.index(end)
        return [pattern.replace("*", letters[i], 1) for i in range(a, b + 1)]
    raise ValueError("Intervalo inválido: use números (1..100) ou letras (a..z)")


# ---------- Exportar / importar (formato .ef2 do IDM e texto puro) ----------

def export_ef2(items, path):
    """Formato observado em CUrlExporter::WriteInELFFile: blocos '<' url / referer: / cookie: / User-Agent: '>'."""
    lines = []
    for it in items:
        lines += ["<", it["url"]]
        if it.get("referer"):
            lines.append(f"referer: {it['referer']}")
        if it.get("cookies"):
            lines.append(f"cookie: {it['cookies']}")
        if it.get("user_agent"):
            lines.append(f"User-Agent: {it['user_agent']}")
        lines.append(">")
    Path(path).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def import_ef2(path) -> list[dict]:
    out, cur = [], None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line == "<":
            cur = {}
        elif line == ">":
            if cur and cur.get("url"):
                out.append(cur)
            cur = None
        elif cur is not None:
            low = line.lower()
            if low.startswith("referer:"):
                cur["referer"] = line[8:].strip()
            elif low.startswith("cookie:"):
                cur["cookies"] = line[7:].strip()
            elif low.startswith("user-agent:"):
                cur["user_agent"] = line[11:].strip()
            elif line and "url" not in cur:
                cur["url"] = line
    return out


def export_txt(items, path):
    Path(path).write_text("\n".join(it["url"] for it in items) + "\n", encoding="utf-8")


URL_RE = re.compile(r"(?:https?|ftp)://[^\s'\"<>]+", re.I)


def import_txt(path) -> list[dict]:
    return [{"url": u} for u in URL_RE.findall(Path(path).read_text(encoding="utf-8", errors="replace"))]


def looks_like_url(text: str) -> bool:
    return bool(text) and bool(re.fullmatch(r"(?:https?|ftp)://\S+", text.strip(), re.I))
