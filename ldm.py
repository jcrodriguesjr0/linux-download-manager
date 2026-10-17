#!/usr/bin/env python3
"""Linux Download Manager - lançador da interface e CLI.

  ldm.py                         abre a interface
  ldm.py --tray                  inicia minimizado na bandeja
  ldm.py URL [URL...]            abre a interface já adicionando os links
  ldm.py add URL [--silent]      envia para a instância em execução (ou abre a interface)
  ldm.py get URL [-o PASTA] [-c CONEXÕES] [-l KB/s]   baixa pelo terminal, sem interface
  ldm.py video URL [--silent]    baixa o vídeo da página (YouTube e ~1800 sites) pelo LDM
  ldm.py install                 cria o atalho no menu de aplicativos
  ldm.py selftest                verifica GTK, yt-dlp, deno e ffmpeg
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ldm import hostenv  # noqa: E402

hostenv.install()   # programas do sistema abertos pelo LDM recebem o ambiente original


def api_call(path, payload=None):
    from ldm.config import Settings
    s = Settings()
    req = urllib.request.Request(f"http://127.0.0.1:{s['api_port']}{path}",
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json", "X-LDM-Client": "1"},
                                 method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def cli_get(args):
    from ldm import engine, net, util
    from ldm.config import Settings
    s = Settings()
    item = {"id": f"cli{int(time.time())}", "url": args.url, "filename": "",
            "save_dir": str(Path(args.output or os.getcwd()).expanduser())}
    lim = net.SpeedLimiter((args.limit or 0) * 1024)
    d = engine.Downloader(item, net.NetConfig(s), s["temp_dir"], lim, max_conn=args.connections or s["max_connections"],
                          min_segment=int(s["min_segment_kb"]) * 1024, retries=int(s["retries"]))
    d.start()
    try:
        while d.alive():
            st = d.stats()
            size = item.get("size") or -1
            pct = f"{st['downloaded'] * 100 / size:5.1f}%" if size > 0 else "  ?  "
            eta = util.fmt_eta((size - st["downloaded"]) / st["rate"]) if size > 0 and st["rate"] else ""
            print(f"\r{pct} {util.fmt_size(st['downloaded']):>10} / {util.fmt_size(size) or '?':<10} "
                  f"{util.fmt_rate(st['rate']):>12} {len(st['connections'])} conexões {eta:>8}   ", end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        d.stop()
        d.thread.join(5)
        print("\nInterrompido. Rode o mesmo comando para recomeçar (a retomada fica na interface).")
        return 1
    print()
    if item["status"] == engine.ST_COMPLETE:
        print(f"Concluído: {Path(item['save_dir']) / item['filename']}")
        return 0
    print(f"Erro: {item.get('error')}")
    return 2


def selftest():
    import shutil
    import subprocess
    ok = True

    def line(name, good, detail):
        nonlocal ok
        ok = ok and good
        print(f"[{'OK' if good else 'FALHA'}] {name}: {detail}")

    line("Python", True, sys.version.split()[0] + (f" (AppImage {os.environ.get('APPIMAGE')})" if os.environ.get("APPIMAGE") else ""))
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        line("GTK", True, f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}")
        import cairo
        line("cairo", True, cairo.version)
    except Exception as e:  # noqa: BLE001
        line("GTK", False, str(e))
    from ldm import media
    from ldm.config import Settings
    try:
        launcher, exe, v = media.Backend(Settings()).resolve()
        where = "embutido" if exe[-1] == "yt_dlp" else ("distrobox" if launcher else exe[0])
        line("yt-dlp", True, f"{v} ({where})")
    except Exception as e:  # noqa: BLE001
        line("yt-dlp", False, str(e))
    line("deno", bool(media.deno_path()), media.deno_path() or "ausente (YouTube pode falhar)")
    ff = shutil.which("ffmpeg")
    if ff:
        ver = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]
    line("ffmpeg", bool(ff), ver if ff else "ausente (mesclar vídeo/áudio e MP3 não funcionam)")
    return 0 if ok else 1


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("get", "add", "video", "install", "selftest", "-h", "--help"):
        p = argparse.ArgumentParser(prog="ldm.py", description="Linux Download Manager")
        sub = p.add_subparsers(dest="cmd")
        g = sub.add_parser("get", help="baixar pelo terminal")
        g.add_argument("url")
        g.add_argument("-o", "--output")
        g.add_argument("-c", "--connections", type=int)
        g.add_argument("-l", "--limit", type=int, help="limite em KB/s")
        a = sub.add_parser("add", help="enviar link para o LDM em execução")
        a.add_argument("url")
        a.add_argument("--silent", action="store_true", help="sem diálogo, inicia direto")
        vd = sub.add_parser("video", help="baixar o vídeo de uma página")
        vd.add_argument("url")
        vd.add_argument("--silent", action="store_true", help="sem diálogo: qualidade padrão")
        sub.add_parser("install", help="criar atalho no menu")
        sub.add_parser("selftest", help="diagnóstico dos componentes")
        args = p.parse_args(argv)
        if args.cmd == "get":
            return cli_get(args)
        if args.cmd == "selftest":
            return selftest()
        if args.cmd == "install":
            from ldm.autostart import install_menu_entry
            print(f"Atalho criado: {install_menu_entry()}")
            return 0
        if args.cmd == "video":
            try:
                api_call("/video", {"page_url": args.url, "silent": args.silent})
                return 0
            except OSError:
                argv = ["--video", args.url]
        if args.cmd == "add":
            try:
                api_call("/add", {"url": args.url, "silent": args.silent})
                return 0
            except OSError:
                argv = [args.url]
        else:
            p.print_help()
            return 0
    # Interface: força X11 (XWayland) para o ícone de bandeja e o monitor de área de transferência
    # funcionarem no KDE/Wayland (Gtk.StatusIcon usa XEmbed, convertido pelo xembedsniproxy).
    if os.environ.get("WAYLAND_DISPLAY") and "GDK_BACKEND" not in os.environ and os.environ.get("DISPLAY"):
        hostenv.remember("GDK_BACKEND")
        os.environ["GDK_BACKEND"] = "x11"
    from ldm.gui.app import main as gui_main
    return gui_main([sys.argv[0]] + argv)


if __name__ == "__main__":
    sys.exit(main())
