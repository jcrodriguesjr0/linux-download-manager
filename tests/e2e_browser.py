"""Teste ponta a ponta: Chromium real + extensão LDM + API do LDM (sem interface) + yt-dlp.

Roda dentro da distrobox com Playwright:
  PLAYWRIGHT_BROWSERS_PATH=<...>/browsers <venv>/bin/python tests/e2e_browser.py [--youtube]

Cenários:
  1. Página local com <video>: passar o mouse mostra o painel, clicar baixa o vídeo (yt-dlp genérico + motor LDM).
  2. Sniffer: o stream de mídia da aba aparece na lista da extensão.
  3. Captura de download: clicar num link .zip faz o LDM baixar no lugar do navegador.
  4. Player MSE (blob:) com HLS montado em JavaScript: yt-dlp não reconhece a página, o stream capturado
     pelo sniffer é usado automaticamente.
  5. (--youtube) YouTube real: painel sobre o player -> download completo.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = Path.home() / ".local/share/ldm"
TMP = Path(tempfile.mkdtemp(prefix="ldm-e2e-"))
os.environ["XDG_CONFIG_HOME"] = str(TMP / "cfg")
os.environ["XDG_DATA_HOME"] = str(TMP / "data")
(TMP / "data/ldm").mkdir(parents=True)
for sub in ("ytdlp", "bin"):          # reaproveita o yt-dlp/deno já instalados
    os.symlink(REAL_DATA / sub, TMP / "data/ldm" / sub)
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from ldm import config  # noqa: E402
from ldm.manager import Manager  # noqa: E402
from ldm.server import Api  # noqa: E402

WEB = TMP / "web"
OUT = TMP / "out"
WEB.mkdir()
subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=20:size=640x360:rate=25",
                "-f", "lavfi", "-i", "sine=duration=20", "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "800k",
                "-c:a", "aac", "-shortest", str(WEB / "clip.mp4")], check=True)
(WEB / "arquivo.zip").write_bytes(os.urandom(2 * 1024 * 1024))
(WEB / "page.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Página de teste LDM</title></head><body style="margin:40px">
<h1>Teste</h1><video id="v" src="clip.mp4" controls width="640" height="360" preload="auto"></video>
<p><a id="zip" href="arquivo.zip">baixar zip</a></p></body></html>""")
(WEB / "hls").mkdir()
subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(WEB / "clip.mp4"), "-c", "copy", "-f", "hls", "-hls_time", "2",
                "-hls_playlist_type", "vod", str(WEB / "hls" / "stream.m3u8")], check=True)
(WEB / "mse.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Player MSE proprietário</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.20/dist/hls.min.js"></script></head><body style="margin:40px">
<video id="v" controls muted width="640" height="360"></video>
<script>const parts = ["h", "ls/str", "eam.m", "3u8"]; const u = parts.join("");
const v = document.getElementById("v"); const h = new Hls(); h.loadSource(u); h.attachMedia(v);
h.on(Hls.Events.MANIFEST_PARSED, () => v.play());</script></body></html>""")


# ---- cenários do modo IDM
subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(WEB / "clip.mp4"), "-an", "-c", "copy", str(WEB / "v.mp4")], check=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(WEB / "clip.mp4"), "-vn", "-c", "copy", str(WEB / "a.m4a")], check=True)
(WEB / "arquivo2.zip").write_bytes(os.urandom(1024 * 1024))
(WEB / "api").mkdir()
# 1) vídeo escondido numa API JSON: a página nunca pede o vídeo, só a API (URL com barras escapadas)
(WEB / "api.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Vídeo na API</title></head><body>
<video id="v" width="640" height="360" poster="data:image/gif;base64,R0lGODlhAQABAAAAACw="></video>
<script>fetch("api/player.json").then(r => r.json()).then(j => { window.cfg = j; });</script></body></html>""")
# 2) MPD embutido em JSON (estilo Instagram/Facebook), com vídeo e áudio separados
MPD_INLINE = ('<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static"><Period>'
              '<AdaptationSet contentType="video" mimeType="video/mp4"><Representation id="v" height="360" bandwidth="800000" '
              'codecs="avc1.42c01e"><BaseURL>../v.mp4</BaseURL></Representation></AdaptationSet>'
              '<AdaptationSet contentType="audio" mimeType="audio/mp4"><Representation id="a" bandwidth="128000" '
              'codecs="mp4a.40.2"><BaseURL>../a.m4a</BaseURL></Representation></AdaptationSet></Period></MPD>')
(WEB / "ig.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Post com vídeo</title></head><body>
<video id="v" width="640" height="360"></video>
<script>const x = new XMLHttpRequest(); x.open("GET", "api/graphql"); x.send();</script></body></html>""")
# 3) fatias range= no estilo googlevideo: o player pede pedaços de vídeo e áudio separados
(WEB / "gv.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Player fatiado</title></head><body>
<video id="v" width="640" height="360"></video>
<script>
const V = "videoplayback?id=t1&itag=134&mime=video%2Fmp4&dur=20.000&clen=__VLEN__";
const A = "videoplayback?id=t1&itag=140&mime=audio%2Fmp4&dur=20.000&clen=__ALEN__";
(async () => { for (const u of [V, A]) for (const r of ["0-65535", "65536-131071"]) await fetch(u + "&rn=1&range=" + r); })();
Object.defineProperty(document.getElementById("v"), "duration", { get: () => 20 });
</script></body></html>""".replace("__VLEN__", str((WEB / "v.mp4").stat().st_size)).replace("__ALEN__", str((WEB / "a.m4a").stat().st_size)))
# 4) teclas
(WEB / "keys.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Teclas</title></head><body>
<a id="z2" href="arquivo2.zip">zip</a> <a id="pg" href="pagina.html">página comum</a></body></html>""")
(WEB / "pagina.html").write_text("<html><body>ok</body></html>")


class RangeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        u = urlsplit(self.path)
        if u.path == "/api/player.json":
            body = ('{"data":{"video":{"title":"x","hls_url":"' + BASE.replace("/", "\\/") + '\\/hls\\/stream.m3u8"}}}').encode()
            return self._raw(200, "application/json", body)
        if u.path == "/api/graphql":
            import json as _j
            body = _j.dumps({"data": {"shortcode_media": {"video_dash_manifest": MPD_INLINE}}}).encode()
            return self._raw(200, "application/json", body)
        if u.path == "/videoplayback":
            q = parse_qs(u.query)
            data = (WEB / ("a.m4a" if q.get("itag") == ["140"] else "v.mp4")).read_bytes()
            ctype = "audio/mp4" if q.get("itag") == ["140"] else "video/mp4"
            rq = (q.get("range") or [None])[0]
            rh = self.headers.get("Range")
            if rq:
                a, b = map(int, rq.split("-"))
                return self._raw(200, ctype, data[a:b + 1])
            if rh:
                a, b = re.match(r"bytes=(\d*)-(\d*)", rh).groups()
                a = int(a or 0)
                b = min(int(b) if b else len(data) - 1, len(data) - 1)
                return self._raw(206, ctype, data[a:b + 1], {"Content-Range": f"bytes {a}-{b}/{len(data)}"})
            return self._raw(200, ctype, data)
        return super().do_GET()

    def _raw(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a, b = re.match(r"bytes=(\d*)-(\d*)", rng).groups()
        a = int(a or 0)
        b = min(int(b) if b else size - 1, size - 1)
        f = open(path, "rb")
        f.seek(a)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.send_header("Content-Length", str(b - a + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._remaining = b - a + 1
        return f

    def copyfile(self, src, dst):
        n = getattr(self, "_remaining", None)
        try:
            if n is None:
                return super().copyfile(src, dst)
            while n > 0:
                buf = src.read(min(65536, n))
                if not buf:
                    break
                dst.write(buf)
                n -= len(buf)
        except (BrokenPipeError, ConnectionResetError):
            pass   # o navegador cancelou (normal ao capturar downloads)


web = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
threading.Thread(target=web.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{web.server_port}"

s = config.Settings()
# LDM_E2E_PORT: roda o teste ao lado de um LDM já aberto (a extensão é copiada com a porta trocada)
PORT = int(os.environ.get("LDM_E2E_PORT", "9614"))
s.data.update(api_port=PORT, general_folder=str(OUT), temp_dir=str(TMP / "tmp"), video_folder=str(OUT / "video"),
              video_max_height=360, capture_exts="ZIP MP4", show_complete_dialog=False)
s["categories"] = [c | {"folder": str(OUT / c["name"])} for c in s["categories"]]
m = Manager(s)
m.run()
api = Api(m)
api.start()

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASSOU " if ok else "FALHOU ") + name + (f" — {detail}" if detail else ""), flush=True)


def wait_item(pred, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for it in list(m.items.values()):
            if pred(it):
                if it["status"] in ("complete", "error"):
                    return it
        time.sleep(0.5)
    return next((it for it in m.items.values() if pred(it)), None)


def hover_and_click_panel(page, selector="video"):
    box = page.locator(selector).first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(300)
    page.mouse.move(box["x"] + box["width"] / 2 + 5, box["y"] + box["height"] / 2 + 5)
    page.wait_for_function("() => { const h = document.querySelector('ldm-video-panel');"
                           " return h && h.style.display === 'block'; }", timeout=8000)
    hb = page.evaluate("() => { const r = document.querySelector('ldm-video-panel').getBoundingClientRect();"
                       " return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
    if os.environ.get("LDM_E2E_SHOT") and not os.path.exists(os.environ["LDM_E2E_SHOT"]):
        page.mouse.move(hb["x"] + hb["w"] / 2, hb["y"] + hb["h"] / 2)
        page.wait_for_timeout(400)
        page.screenshot(path=os.environ["LDM_E2E_SHOT"], clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], 300)})
    page.mouse.click(hb["x"] + hb["w"] / 2, hb["y"] + hb["h"] / 2)
    return hb


ext = str(ROOT / "browser_extension")
if PORT != 9614:
    shutil.copytree(ext, TMP / "ext", dirs_exist_ok=True)
    bg = TMP / "ext" / "background.js"
    bg.write_text(bg.read_text().replace("const DEFAULT_PORT = 9614;", f"const DEFAULT_PORT = {PORT};"))
    ext = str(TMP / "ext")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(TMP / "profile"), channel="chromium", headless=True, accept_downloads=True,
        args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--autoplay-policy=no-user-gesture-required"])
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
    check("extensão carregada (service worker ativo)", "background.js" in sw.url, sw.url)
    page = ctx.new_page()

    # 1 + 2: página local com vídeo
    page.goto(BASE + "/page.html")
    page.evaluate("document.getElementById('v').play()")
    page.wait_for_timeout(1500)
    try:
        hb = hover_and_click_panel(page)
        check("painel 'Baixar este vídeo' aparece sobre o player", hb["w"] > 50, f"{hb}")
    except Exception as e:  # noqa: BLE001
        check("painel 'Baixar este vídeo' aparece sobre o player", False, str(e)[:200])
    it = wait_item(lambda i: i.get("kind") == "video" and "127.0.0.1" in i["url"], 90)
    ok = bool(it) and it["status"] == "complete" and (Path(it["save_dir"]) / it["filename"]).exists()
    check("vídeo da página local baixado (yt-dlp genérico + LDM)", ok,
          f"{it and it['status']} {it and it.get('error')} {it and it['filename']}")
    page.wait_for_timeout(500)
    tab_media = sw.evaluate("async () => { const s = await chrome.storage.session.get(null);"
                            " return Object.values(s).flat().map(m => m.url); }")
    check("sniffer registrou o stream da aba", any("clip.mp4" in u for u in tab_media), str(tab_media)[:200])

    # 3: captura de download
    page.click("#zip")
    it = wait_item(lambda i: i["filename"] == "arquivo.zip", 60)
    check("download de .zip capturado do navegador", bool(it) and it["status"] == "complete",
          f"{it and it['status']} {it and it.get('error')}")

    # 4: player MSE com HLS escondido em JavaScript
    mse = ctx.new_page()
    mse.goto(BASE + "/mse.html")
    try:
        mse.wait_for_function("() => { const v = document.getElementById('v');"
                              " return v.currentSrc.startsWith('blob:') && v.currentTime > 0.5; }", timeout=20000)
        check("player MSE tocando via blob:", True)
        hover_and_click_panel(mse)
    except Exception as e:  # noqa: BLE001
        check("player MSE tocando via blob:", False, str(e)[:200])
    it = wait_item(lambda i: i.get("kind") == "video" and "m3u8" in i["url"], 90)
    ok = bool(it) and it["status"] == "complete"
    check("vídeo MSE/HLS baixado pelo stream capturado", ok,
          f"{it and it['status']} {it and it.get('error')} {it and it['filename']} {it and it.get('size')}")
    mse.close()

    # ---------------- modo IDM ----------------
    def idm_case(name, path, pred, check_streams=False, timeout=90):
        before = set(m.items)
        pred0 = pred
        pred = lambda i: i["id"] not in before and pred0(i)  # noqa: E731
        pg = ctx.new_page()
        pg.goto(BASE + path)
        pg.wait_for_timeout(2500)          # a página faz as requisições/APIs
        try:
            hover_and_click_panel(pg)
        except Exception as e:  # noqa: BLE001
            check(name, False, "painel: " + str(e)[:150])
            pg.close()
            return
        it = wait_item(pred, timeout)
        ok = bool(it) and it["status"] == "complete"
        detail = f"{it and it['status']} {it and it.get('error')} {it and it['filename']} {it and it.get('size')}"
        if ok and check_streams:
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                 str(Path(it["save_dir"]) / it["filename"])], capture_output=True, text=True)
            ok = "video" in pr.stdout and "audio" in pr.stdout
            detail += " | " + pr.stdout.replace("\n", " ")
        check(name, ok, detail)
        pg.close()

    idm_case("modo IDM: HLS escondido numa API JSON", "/api.html",
             lambda i: i.get("kind") == "video" and "stream.m3u8" in i["url"])
    idm_case("modo IDM: MPD embutido no JSON (vídeo+áudio mesclados)", "/ig.html",
             lambda i: i.get("kind") == "video" and "ig.html" in i["url"], check_streams=True)
    idm_case("modo IDM: fatias range= remontadas e mescladas", "/gv.html",
             lambda i: i.get("kind") == "video" and "gv.html" in i["url"], check_streams=True)

    kp = ctx.new_page()
    kp.goto(BASE + "/keys.html")
    kp.wait_for_timeout(800)
    try:
        with kp.expect_download(timeout=8000) as dl:
            kp.click("#z2", modifiers=["Alt"])
        browser_got = dl.value is not None
    except Exception:  # noqa: BLE001
        browser_got = False
    kp.wait_for_timeout(2500)
    captured = any(i["filename"] == "arquivo2.zip" for i in m.items.values())
    check("Alt+clique: o navegador baixa e o LDM não captura", browser_got and not captured,
          f"navegador={browser_got} ldm={captured}")
    kp.click("#pg", modifiers=["Control", "Alt"])
    it = wait_item(lambda i: i["url"].endswith("/pagina.html"), 20)
    check("Ctrl+Alt+clique: força o LDM até numa página comum", bool(it), f"{it and it['status']}")
    kp.close()

    if "--youtube-sim" in sys.argv:
        # URLs reais do googlevideo (obtidas pelo yt-dlp só para montar o teste); a página as pede em fatias
        # range= como o player do YouTube faz, e o LDM (modo só captura) precisa remontar, baixar e mesclar.
        import json as _json
        ytdlp = str(REAL_DATA / "ytdlp/bin/yt-dlp")
        deno = str(REAL_DATA / "bin/deno")
        out = subprocess.run([ytdlp, "--js-runtimes", f"deno:{deno}", "-J", "-f", "bv*[height<=240][ext=mp4]+ba[ext=m4a]",
                                           "https://www.youtube.com/watch?v=jNQXAC9IVRw"], capture_output=True, text=True)
        info = _json.loads(out.stdout) if out.stdout.strip() else None
        if not info:
            print("PULADO YouTube simulado — o YouTube recusou o yt-dlp (" + (out.stderr.strip().splitlines() or ["?"])[-1][:120] + ")")
    if "--youtube-sim" in sys.argv and info:
        urls = [f["url"] for f in info["requested_formats"]]
        dur = info.get("duration") or 19
        (WEB / "gvreal.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Me at the zoo (simulado)</title></head>
<body><video id="v" width="640" height="360"></video><script>
const U = __URLS__;
(async () => { for (const u of U) for (const r of ["0-65535", "65536-131071"]) { try { await fetch(u + "&range=" + r, {mode: "no-cors"}); } catch (e) {} } })();
Object.defineProperty(document.getElementById("v"), "duration", { get: () => __DUR__ });
</script></body></html>""".replace("__URLS__", _json.dumps(urls)).replace("__DUR__", str(dur)))
        m.s["video_mode"] = "capture"
        idm_case("YouTube (googlevideo real) remontado sem yt-dlp", "/gvreal.html",
                 lambda i: i.get("kind") == "video" and "gvreal.html" in i["url"], check_streams=True, timeout=120)
        m.s["video_mode"] = "auto"

    if "--youtube-passive" in sys.argv:
        from ldm import media as _media
        m.s["ytdlp_cmd"] = "false"               # yt-dlp "quebrado": só a captura passiva pode salvar
        _media.Backend._cache = None
        before = set(m.items)
        yp = ctx.new_page()
        yp.goto("https://www.youtube.com/watch?v=jNQXAC9IVRw", wait_until="domcontentloaded")
        try:
            yp.wait_for_selector("video", timeout=30000)
            yp.evaluate("() => { const v = document.querySelector('video'); v.muted = true; v.play(); }")
            yp.wait_for_timeout(9000)
            media_list = sw.evaluate("async () => { const s = await chrome.storage.session.get(null);"
                                     " return Object.entries(s).filter(([k]) => k.startsWith('media_'))"
                                     ".flatMap(([, v]) => v).map(x => x.key + ' ' + (x.size||'')); }")
            print("   capturado no YouTube:", media_list[:12], flush=True)
            hover_and_click_panel(yp)
        except Exception as e:  # noqa: BLE001
            check("YouTube passivo (sem yt-dlp)", False, str(e)[:200])
        it = wait_item(lambda i: i["id"] not in before and i.get("kind") == "video", 120)
        ok = bool(it) and it["status"] == "complete"
        detail = f"{it and it['status']} {it and it.get('error')} {it and it['filename']} {it and it.get('size')}"
        if ok:
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,height", "-of", "csv=p=0",
                                 str(Path(it["save_dir"]) / it["filename"])], capture_output=True, text=True)
            ok = "video" in pr.stdout and "audio" in pr.stdout
            detail += " | " + pr.stdout.replace("\n", " ")
        check("YouTube passivo (sem yt-dlp): links do player remontados", ok, detail)
        m.s["ytdlp_cmd"] = ""
        _media.Backend._cache = None
        yp.close()

    # 5: YouTube real
    if "--youtube" in sys.argv:
        yt = ctx.new_page()
        yt.goto("https://www.youtube.com/watch?v=jNQXAC9IVRw", wait_until="domcontentloaded")
        try:
            yt.wait_for_selector("video", timeout=30000)
            yt.wait_for_timeout(4000)
            hover_and_click_panel(yt)
            check("painel sobre o player do YouTube", True)
        except Exception as e:  # noqa: BLE001
            yt.screenshot(path=str(TMP / "youtube.png"))
            check("painel sobre o player do YouTube", False, str(e)[:200] + f" (screenshot {TMP}/youtube.png)")
        it = wait_item(lambda i: i.get("kind") == "video" and "youtube.com" in i["url"], 180)
        ok = bool(it) and it["status"] == "complete"
        check("vídeo do YouTube baixado", ok, f"{it and it['status']} {it and it.get('error')} "
                                               f"{it and it['filename']} {it and it.get('size')}")
        if ok:
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,height",
                                 "-of", "csv=p=0", str(Path(it["save_dir"]) / it["filename"])],
                                capture_output=True, text=True)
            check("arquivo do YouTube tem vídeo + áudio", "video" in pr.stdout and "audio" in pr.stdout,
                  pr.stdout.replace("\n", " "))
    ctx.close()

api.stop()
m.shutdown()
web.shutdown()
fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} cenários passaram")
if not fails:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fails else 0)
