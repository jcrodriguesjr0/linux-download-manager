#!/usr/bin/env python3
"""Gera o Lunix Download Manager para Windows (roda no MSYS2 UCRT64; usado pelo GitHub Actions).

  python packaging/windows/build.py [--skip-tools]

Saída em build/win/:
  dist/LDM/                      programa (LDM.exe com janela, ldm-cli.exe para terminal, bin/ com yt-dlp, ffmpeg, deno)
  out/Lunix_Download_Manager-<versão>-portable.zip
O instalador .exe é gerado depois pelo Inno Setup (packaging/windows/ldm.iss).
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build" / "win"
STAGE = WORK / "stage"
CACHE = WORK / "cache"
DIST = WORK / "dist"
OUT = WORK / "out"
APP_NAME = "Lunix Download Manager"

TOOLS = {
    "yt-dlp": ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
               "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"),
    "ffmpeg": ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
               "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256"),
    "deno": ("https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
             "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip.sha256sum"),
}


def log(msg):
    print(f"==> {msg}", flush=True)


def version():
    import re
    return re.search(r'^VERSION = "([^"]+)"', (ROOT / "ldm" / "__init__.py").read_text(), re.M).group(1)


def fetch(url, dest: Path):
    if not dest.exists():
        log(f"baixando {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "ldm-build"})
        with urllib.request.urlopen(req, timeout=600) as r, open(dest.with_suffix(".tmp"), "wb") as f:
            shutil.copyfileobj(r, f)
        dest.with_suffix(".tmp").rename(dest)
    return dest


def verify(path: Path, sums_url: str):
    """Confere o SHA-256 com a lista publicada pelo próprio projeto."""
    req = urllib.request.Request(sums_url, headers={"User-Agent": "ldm-build"})
    text = urllib.request.urlopen(req, timeout=60).read().decode()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    # formatos: "hash  arquivo" (yt-dlp, BtbN) ou tabela do PowerShell Get-FileHash (Deno)
    if digest in text.lower().split():
        return
    raise SystemExit(f"checksum não confere: {path.name} ({digest})")


def tools(bin_dir: Path):
    bin_dir.mkdir(parents=True, exist_ok=True)
    url, sums = TOOLS["yt-dlp"]
    exe = fetch(url, CACHE / "yt-dlp.exe")
    verify(exe, sums)
    shutil.copy2(exe, bin_dir / "yt-dlp.exe")

    url, sums = TOOLS["ffmpeg"]
    z = fetch(url, CACHE / Path(url).name)
    verify(z, sums)
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if n.endswith(("/bin/ffmpeg.exe", "/bin/ffprobe.exe")):
                (bin_dir / Path(n).name).write_bytes(zf.read(n))

    url, sums = TOOLS["deno"]
    z = fetch(url, CACHE / Path(url).name)
    verify(z, sums)
    with zipfile.ZipFile(z) as zf:
        (bin_dir / "deno.exe").write_bytes(zf.read("deno.exe"))


def make_ico(dest: Path):
    """.ico com entradas PNG (16 a 256 px) a partir dos PNGs do logo, sem depender do Pillow."""
    logo = ROOT / "identidade_visual" / "logo"
    files = [ROOT / "identidade_visual" / "extensao" / "icon16.png", logo / "ldm_32.png",
             ROOT / "identidade_visual" / "extensao" / "icon48.png", logo / "ldm_64.png", logo / "ldm.png",
             logo / "ldm_256.png"]
    imgs = []
    for f in files:
        b = f.read_bytes()
        w, h = struct.unpack(">II", b[16:24])
        imgs.append((w, h, b))
    head = struct.pack("<HHH", 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    entries, blobs = b"", b""
    for w, h, b in imgs:
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(b), off + len(blobs))
        blobs += b
    dest.write_bytes(head + entries + blobs)


def stage_extension():
    """A extensão é a mesma do Linux; só o nome exibido muda para "Lunix"."""
    dst = STAGE / "browser_extension"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(ROOT / "browser_extension", dst)
    m = dst / "manifest.json"
    data = json.loads(m.read_text(encoding="utf-8"))
    for k in ("name", "description"):
        data[k] = data[k].replace("Linux Download Manager", APP_NAME)
    data["action"]["default_title"] = APP_NAME
    m.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-tools", action="store_true", help="não baixa yt-dlp/ffmpeg/deno (teste rápido)")
    args = ap.parse_args()
    ver = version()
    log(f"{APP_NAME} {ver}")
    for d in (STAGE, DIST, OUT):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    stage_extension()
    make_ico(STAGE / "ldm.ico")

    log("PyInstaller")
    env = dict(os.environ, LDM_STAGE=str(STAGE))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(WORK / "pyi"), str(ROOT / "packaging" / "windows" / "ldm.spec")],
                   check=True, env=env)
    app = DIST / "LDM"
    if not args.skip_tools:
        log("ferramentas (yt-dlp, ffmpeg, deno)")
        tools(app / "bin")
    shutil.copy2(ROOT / "LICENSE", app / "LICENSE.txt")
    (app / "LEIA-ME.txt").write_text(
        f"{APP_NAME} {ver}\r\n\r\nExecute LDM.exe. A extensão do navegador fica em _internal\\browser_extension\r\n"
        "(menu Ajuda > Extensão do navegador mostra o passo a passo).\r\n\r\n"
        "Componentes de terceiros: GTK 3 e PyGObject (LGPL), Python (PSF), yt-dlp (Unlicense),\r\n"
        "FFmpeg (GPL-3.0, build BtbN), Deno (MIT), fontes Inter e JetBrains Mono (SIL OFL 1.1).\r\n",
        encoding="utf-8")

    log("zip portátil")
    zpath = OUT / f"Lunix_Download_Manager-{ver}-portable.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in sorted(app.rglob("*")):
            if f.is_file():
                zf.write(f, Path("Lunix Download Manager") / f.relative_to(app))
    log(f"pronto: {zpath} ({zpath.stat().st_size // 2**20} MB)")
    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a") as f:
            f.write(f"LDM_VERSION={ver}\n")


if __name__ == "__main__":
    main()
