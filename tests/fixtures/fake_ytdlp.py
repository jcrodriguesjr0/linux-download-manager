#!/usr/bin/env python3
"""yt-dlp falso para testes: --version, -J (JSON) e download com progresso no formato do LDM."""
import json, os, signal, sys, time
a = sys.argv[1:]
if "--version" in a:
    print("2099.01.01"); sys.exit(0)
base = os.environ.get("FAKE_BASE", "http://127.0.0.1:1")
if "-J" in a:
    url = a[-1]
    if "nologin" in url and "--cookies" not in a:
        print("ERROR: [site] This video requires you to sign in", file=sys.stderr); sys.exit(1)
    fmts = [
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "ext": "mp4", "tbr": 4000, "protocol": "https", "filesize": 1000},
        {"format_id": "248", "vcodec": "vp9", "acodec": "none", "height": 1080, "ext": "webm", "tbr": 5000, "protocol": "https", "filesize": 900},
        {"format_id": "22", "vcodec": "avc1", "acodec": "mp4a.40.2", "height": 720, "ext": "mp4", "tbr": 2000, "protocol": "https", "filesize": 700},
        {"format_id": "hls-480", "vcodec": "avc1", "acodec": "mp4a", "height": 480, "ext": "mp4", "tbr": 900, "protocol": "m3u8_native"},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 128, "protocol": "https", "filesize": 200},
        {"format_id": "140-drc", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 129, "protocol": "https", "filesize": 200},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "ext": "webm", "abr": 160, "protocol": "https", "filesize": 210},
    ]
    info = {"title": "Vídeo de Teste", "id": "abc", "duration": 60, "extractor_key": "Fake", "formats": fmts, "ext": "mp4"}
    if "-f" in a:
        sel = a[a.index("-f") + 1].split("/")[0]
        info["requested_formats"] = [{"format_id": fid, "url": f"{base}/{fid}.bin", "protocol": "https",
                                      "ext": "mp4" if fid != "140" else "m4a", "http_headers": {"User-Agent": "UA-test"}}
                                     for fid in sel.split("+")]
    print(json.dumps(info)); sys.exit(0)
# modo download
save = next(a[i + 1] for i, x in enumerate(a) if x == "-P" and not a[i + 1].startswith("temp:"))
tmpl = a[a.index("-o") + 1]
out = os.path.join(save, tmpl.replace("%(ext)s", "mp3" if "-x" in a else "mp4").replace("%(title).150B [%(id)s]", "Vídeo de Teste [abc]"))
stop = {"v": False}
signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))
steps = int(os.environ.get("FAKE_STEPS", "5"))
for i in range(1, steps + 1):
    if stop["v"]:
        sys.exit(1)
    print(f"LDMPROG downloading|{i * 100}|{steps * 100}|NA|1000|1|137", flush=True)
    time.sleep(float(os.environ.get("FAKE_DELAY", "0.05")))
print("[Merger] Merging formats", flush=True)
open(out, "wb").write(b"v" * steps * 100)
print(f"LDMFILE {out}", flush=True)
