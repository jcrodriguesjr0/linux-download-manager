#!/usr/bin/env python3
"""Gera a AppImage do Linux Download Manager.

Rodar numa distro Ubuntu 24.04 (ex.: distrobox) com: python3-gi python3-gi-cairo gir1.2-gtk-3.0
librsvg2-common libgdk-pixbuf2.0-bin python3-pip.

  python3 packaging/appimage/build_appimage.py [--work DIR] [--out DIR]

Conteúdo: Python 3.12 + PyGObject/GTK 3 (bibliotecas do Ubuntu), yt-dlp[default,curl-cffi], Deno,
ffmpeg/ffprobe estáticos e o código do LDM. Bibliotecas básicas do sistema (glibc, OpenGL, X11,
fontconfig...) ficam de fora conforme a excludelist oficial da AppImage.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from ldm import VERSION  # noqa: E402

ARCH_LIB = Path("/usr/lib/x86_64-linux-gnu")
PY = "python3.12"
URLS = {
    "excludelist": "https://raw.githubusercontent.com/AppImageCommunity/pkg2appimage/master/excludelist",
    "appimagetool": "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage",
    "ffmpeg": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "deno": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip",
}
# Usadas se a excludelist oficial não puder ser baixada
FALLBACK_EXCLUDE = """ld-linux.so.2 ld-linux-x86-64.so.2 libanl.so.1 libBrokenLocale.so.1 libcidn.so.1 libc.so.6
libdl.so.2 libm.so.6 libmvec.so.1 libnss_*.so.2 libpthread.so.0 libresolv.so.2 librt.so.1 libthread_db.so.1
libutil.so.1 libstdc++.so.6 libGL.so.1 libEGL.so.1 libGLdispatch.so.0 libGLX.so.0 libOpenGL.so.0 libdrm.so.2
libglapi.so.0 libgbm.so.1 libxcb.so.1 libX11.so.6 libX11-xcb.so.1 libasound.so.2 libfontconfig.so.1
libfreetype.so.6 libharfbuzz.so.0 libcom_err.so.2 libexpat.so.1 libgcc_s.so.1 libgpg-error.so.0 libICE.so.6
libSM.so.6 libusb-1.0.so.0 libuuid.so.1 libz.so.1 libgpg-error.so.0 libjack.so.0 libpipewire-0.3.so.0""".split()
STDLIB_SKIP = {"test", "idlelib", "tkinter", "turtledemo", "lib2to3", "ensurepip", "pydoc_data",
               "config-3.12-x86_64-linux-gnu", "__pycache__", "unittest/test"}
DIST_PACKAGES = ["gi", "cairo", "pip"]
TYPELIBS = ["GLib-2.0", "GObject-2.0", "Gio-2.0", "GioUnix-2.0", "GModule-2.0", "Gtk-3.0", "Gdk-3.0", "GdkX11-3.0",
            "GdkPixbuf-2.0", "Pango-1.0", "PangoCairo-1.0", "PangoFT2-1.0", "HarfBuzz-0.0", "cairo-1.0",
            "freetype2-2.0", "fontconfig-2.0", "Atk-1.0", "xlib-2.0", "xfixes-4.0", "xft-2.0", "xrandr-1.3",
            "GLibUnix-2.0", "Rsvg-2.0"]
ROOT_LIBS = ["libgtk-3.so.0", "libgdk-3.so.0", "libgirepository-1.0.so.1", "libpangocairo-1.0.so.0",
             "libpangoft2-1.0.so.0", "libcairo-gobject.so.2", "libharfbuzz-gobject.so.0", "librsvg-2.so.2",
             "libgdk_pixbuf-2.0.so.0", "libatk-1.0.so.0"]


def log(msg):
    print(f"==> {msg}", flush=True)


def fetch(url, dest: Path):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    log(f"baixando {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ldm-build"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.rename(dest)
    return dest


def exclude_patterns(cache: Path):
    try:
        text = fetch(URLS["excludelist"], cache / "excludelist").read_text()
        pats = [ln.split("#")[0].strip() for ln in text.splitlines()]
        pats = [p for p in pats if p]
        if len(pats) > 20:
            return pats
    except OSError:
        pass
    return FALLBACK_EXCLUDE


def ldd(path):
    out = subprocess.run(["ldd", str(path)], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        m = re.match(r"\s*(\S+) => (/\S+)", ln)
        if m:
            yield m.group(1), m.group(2)


def collect_libs(roots, excludes, dest: Path):
    seen, queue, copied = set(), list(roots), 0
    while queue:
        cur = queue.pop()
        for soname, real in ldd(cur):
            if soname in seen:
                continue
            seen.add(soname)
            if any(fnmatch.fnmatch(soname, p) for p in excludes):
                continue
            target = dest / soname
            if not target.exists():
                shutil.copy2(os.path.realpath(real), target)
                copied += 1
            queue.append(real)
    return copied


def copytree_filtered(src: Path, dst: Path, skip):
    def ignore(d, names):
        rel = Path(d).relative_to(src)
        return [n for n in names if n in skip or str(rel / n) in skip or n.endswith((".pyc", ".pyo"))]
    shutil.copytree(src, dst, ignore=ignore, symlinks=False, dirs_exist_ok=True)


APPRUN = r'''#!/bin/sh
# AppRun do Linux Download Manager: aponta Python/GTK para dentro da AppImage e guarda o ambiente
# original em LDM_ORIG_* para os programas do sistema abertos pelo LDM (ver ldm/hostenv.py).
HERE="$(dirname "$(readlink -f "$0")")"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/ldm"
for v in PATH LD_LIBRARY_PATH PYTHONHOME PYTHONPATH PYTHONDONTWRITEBYTECODE GI_TYPELIB_PATH GSETTINGS_SCHEMA_DIR \
         XDG_DATA_DIRS GIO_MODULE_DIR GDK_PIXBUF_MODULE_FILE GTK_MODULES GTK3_MODULES GTK_PATH GTK_IM_MODULE_FILE \
         SSL_CERT_FILE; do
    eval "isset=\${$v+x}"
    if [ -n "$isset" ]; then eval "export LDM_ORIG_$v=\"\$$v\""; else export "LDM_ORIG_$v=__unset__"; fi
done
export LDM_APPDIR="$HERE"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONHOME="$HERE/usr"
export PYTHONPATH="$DATA/pylib:$HERE/usr/lib/ldm-site:$HERE/usr/lib/python3/dist-packages"
export PYTHONDONTWRITEBYTECODE=1
export GI_TYPELIB_PATH="$HERE/usr/lib/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$HERE/usr/share/glib-2.0/schemas"
export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export GIO_MODULE_DIR="$HERE/usr/lib/gio/modules"
unset GTK_MODULES GTK3_MODULES GTK_PATH GTK_IM_MODULE_FILE
# O OpenSSL embutido (Ubuntu) procura certificados em /usr/lib/ssl; cada distro guarda em um lugar.
if [ -z "$SSL_CERT_FILE" ]; then
    for c in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem \
             /etc/ssl/ca-bundle.pem /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
             "$HERE/usr/lib/ldm-site/certifi/cacert.pem"; do
        if [ -r "$c" ]; then export SSL_CERT_FILE="$c"; break; fi
    done
fi
CACHE="${XDG_RUNTIME_DIR:-/tmp}/ldm-pixbuf-$(echo "$HERE" | cksum | cut -d' ' -f1).cache"
sed "s|@APPDIR@|$HERE|g" "$HERE/usr/lib/gdk-pixbuf-loaders.cache.in" > "$CACHE" 2>/dev/null
export GDK_PIXBUF_MODULE_FILE="$CACHE"
exec "$HERE/usr/bin/python3.12" -s "$HERE/usr/share/ldm/ldm.py" "$@"
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=str(PROJECT / "build" / "appimage"))
    ap.add_argument("--out", default=str(PROJECT / "dist"))
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)
    cache = work / "cache"
    appdir = work / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    usr = appdir / "usr"
    lib = usr / "lib"
    for d in (usr / "bin", lib / "girepository-1.0", lib / "gio" / "modules", usr / "share" / "ldm"):
        d.mkdir(parents=True, exist_ok=True)
    excludes = exclude_patterns(cache)

    log("Python 3.12")
    shutil.copy2(f"/usr/bin/{PY}", usr / "bin" / PY)
    os.symlink(PY, usr / "bin" / "python3")
    copytree_filtered(Path(f"/usr/lib/{PY}"), lib / PY, STDLIB_SKIP)
    (lib / PY / "EXTERNALLY-MANAGED").unlink(missing_ok=True)
    for name in DIST_PACKAGES:
        copytree_filtered(Path("/usr/lib/python3/dist-packages") / name, lib / "python3/dist-packages" / name, {"__pycache__"})

    log("yt-dlp[default,curl-cffi]")
    subprocess.run([f"/usr/bin/{PY}", "-m", "pip", "install", "-q", "--no-compile", "--break-system-packages",
                    "--target", str(lib / "ldm-site"), "yt-dlp[default,curl-cffi]"], check=True)

    log("typelibs GObject Introspection")
    for t in TYPELIBS:
        src = ARCH_LIB / "girepository-1.0" / f"{t}.typelib"
        if src.exists():
            shutil.copy2(src, lib / "girepository-1.0")

    log("gdk-pixbuf loaders")
    pix_src = ARCH_LIB / "gdk-pixbuf-2.0" / "2.10.0" / "loaders"
    pix_dst = lib / "gdk-pixbuf-2.0" / "loaders"
    shutil.copytree(pix_src, pix_dst)
    query = ARCH_LIB / "gdk-pixbuf-2.0" / "gdk-pixbuf-query-loaders"
    env = dict(os.environ, GDK_PIXBUF_MODULEDIR=str(pix_dst))
    cache_txt = subprocess.run([str(query)], capture_output=True, text=True, env=env, check=True).stdout
    (lib / "gdk-pixbuf-loaders.cache.in").write_text(cache_txt.replace(str(appdir), "@APPDIR@"))

    log("bibliotecas compartilhadas (ldd recursivo)")
    roots = [usr / "bin" / PY] + list((lib / PY / "lib-dynload").glob("*.so"))
    roots += list((lib / "python3/dist-packages").rglob("*.so")) + list(pix_dst.glob("*.so"))
    roots += [ARCH_LIB / n for n in ROOT_LIBS if (ARCH_LIB / n).exists()]
    for n in ROOT_LIBS:
        if (ARCH_LIB / n).exists() and not any(fnmatch.fnmatch(n, p) for p in excludes):
            shutil.copy2(os.path.realpath(ARCH_LIB / n), lib / n)
    log(f"{collect_libs(roots, excludes, lib)} bibliotecas copiadas")

    log("esquemas GSettings do GTK")
    schemas = usr / "share/glib-2.0/schemas"
    schemas.mkdir(parents=True)
    for x in Path("/usr/share/glib-2.0/schemas").glob("org.gtk.Settings.*.xml"):
        shutil.copy2(x, schemas)
    subprocess.run(["glib-compile-schemas", str(schemas)], check=True)

    log("ffmpeg estático")
    tar = fetch(URLS["ffmpeg"], cache / "ffmpeg-static.tar.xz")
    with tarfile.open(tar) as tf:
        for m in tf.getmembers():
            if m.isfile() and Path(m.name).name in ("ffmpeg", "ffprobe"):
                m.name = Path(m.name).name
                tf.extract(m, usr / "bin", filter="data")
    for b in ("ffmpeg", "ffprobe"):
        (usr / "bin" / b).chmod(0o755)

    log("Deno (desafios JS do YouTube)")
    import zipfile
    with zipfile.ZipFile(fetch(URLS["deno"], cache / "deno.zip")) as z:
        z.extract("deno", usr / "bin")
    (usr / "bin" / "deno").chmod(0o755)

    log("código do LDM")
    share = usr / "share" / "ldm"
    for item in ("ldm", "data", "browser_extension"):
        copytree_filtered(PROJECT / item, share / item, {"__pycache__"})
    shutil.copy2(PROJECT / "ldm.py", share / "ldm.py")
    icons = usr / "share/icons/hicolor/scalable/apps"
    icons.mkdir(parents=True)
    shutil.copy2(PROJECT / "data/ldm.svg", icons / "linux-download-manager.svg")

    log("AppRun, .desktop e ícone")
    (appdir / "AppRun").write_text(APPRUN)
    (appdir / "AppRun").chmod(0o755)
    shutil.copy2(PROJECT / "data/ldm.svg", appdir / "linux-download-manager.svg")
    shutil.copy2(PROJECT / "data/ldm.png", appdir / ".DirIcon")
    (appdir / "linux-download-manager.desktop").write_text(f"""[Desktop Entry]
Type=Application
Name=Linux Download Manager
GenericName=Download Manager
Comment=Downloads acelerados com várias conexões, vídeos do navegador, filas e agendador
Exec=ldm %U
Icon=linux-download-manager
Terminal=false
Categories=Network;FileTransfer;
StartupWMClass=ldm
X-AppImage-Version={VERSION}
""")
    # remove caches de bytecode que o pip possa ter deixado
    for p in appdir.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)

    log("appimagetool")
    tool = fetch(URLS["appimagetool"], cache / "appimagetool-x86_64.AppImage")
    tool.chmod(0o755)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"Linux_Download_Manager-{VERSION}-x86_64.AppImage"
    target.unlink(missing_ok=True)
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([str(tool), "--comp", "zstd", "--no-appstream", str(appdir), str(target)], env=env, check=True)
    size = target.stat().st_size / 1024 / 1024
    log(f"pronto: {target} ({size:.0f} MB)")
    print(json.dumps({"appimage": str(target), "mb": round(size)}))


if __name__ == "__main__":
    main()
