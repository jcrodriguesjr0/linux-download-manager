"""Testes do motor: multi-conexão, servidor sem Range, pausa/retomada, limitador, lote e .ef2.

Rodar: python3 -m unittest discover -s tests -v   (a partir de LinuxDownloadManager/)
"""
import hashlib
import io
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldm import engine, net, util  # noqa: E402

PAYLOAD = os.urandom(5 * 1024 * 1024 + 123)
_zbuf = io.BytesIO()
with zipfile.ZipFile(_zbuf, "w") as _z:
    _z.writestr("a.txt", "ola" * 1000)
    _z.writestr("pasta/b.bin", os.urandom(5000))
ZIPDATA = _zbuf.getvalue()


class Handler(BaseHTTPRequestHandler):
    slow = 0.0
    range_requests = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/site/") or self.path.startswith("/hls/"):
            return self._static()
        data = ZIPDATA if self.path.startswith("/file.zip") else PAYLOAD
        if self.path.startswith("/norange"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        rng = self.headers.get("Range")
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "/real/arquivo%20final.bin")
            self.end_headers()
            return
        if rng:
            Handler.range_requests += 1
            a, b = re.match(r"bytes=(\d+)-(\d*)", rng).groups()
            a = int(a)
            b = int(b) if b else len(data) - 1
            chunk = data[a:b + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
            self.send_header("Content-Length", str(len(chunk)))
        else:
            chunk = data
            self.send_response(200)
            self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Content-Disposition", 'attachment; filename="teste.bin"')
        self.send_header("Last-Modified", "Wed, 01 Jan 2025 10:00:00 GMT")
        self.end_headers()
        try:
            step = 32 * 1024
            for i in range(0, len(chunk), step):
                self.wfile.write(chunk[i:i + step])
                if Handler.slow:
                    time.sleep(Handler.slow)
        except (BrokenPipeError, ConnectionResetError):
            pass


    PAGES = {
        "/site/": ("text/html", b'<a href="a.zip">Arquivo A</a> <a href="sub/p2.html">p2</a> <a href="../fora.zip">x</a>'
                                b'<img src="foto.jpg"> <a href="https://externo.com/e.zip">e</a>'),
        "/site/sub/p2.html": ("text/html", b'<a href="b.pdf">B</a><a href="c.zip">C</a>'),
        "/hls/master.m3u8": ("application/vnd.apple.mpegurl",
                             b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100,RESOLUTION=320x240\nlow.m3u8\n"
                             b"#EXT-X-STREAM-INF:BANDWIDTH=900,RESOLUTION=1280x720\nhigh.m3u8\n"),
        "/hls/high.m3u8": ("application/vnd.apple.mpegurl",
                           b"#EXTM3U\n#EXTINF:2.0,\ns0.ts\n#EXTINF:2.0,\ns1.ts\n#EXTINF:2.0,\ns2.ts\n#EXT-X-ENDLIST\n"),
    }

    def _static(self):
        path = self.path.split("?")[0]
        if path in self.PAGES:
            ctype, body = self.PAGES[path]
        elif path.startswith("/hls/s"):
            ctype, body = "video/mp2t", (path[-4:-3] * 1000).encode()
        else:
            ctype, body = "application/octet-stream", b"x" * 10
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        Handler.slow = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def run_item(self, url, max_conn=8, limiter=None, wait=True):
        item = {"id": "t1", "url": url, "save_dir": str(self.dir / "out"), "filename": ""}
        d = engine.Downloader(item, net.NetConfig(), str(self.dir / "tmp"), limiter or net.SpeedLimiter(0),
                              max_conn=max_conn, min_segment=256 * 1024, retries=2)
        d.start()
        if wait:
            d.thread.join(30)
        return item, d

    def test_multiconnection(self):
        Handler.range_requests = 0
        item, _ = self.run_item(self.base + "/x.bin")
        self.assertEqual(item["status"], engine.ST_COMPLETE, item.get("error"))
        self.assertEqual(item["filename"], "teste.bin")
        out = self.dir / "out" / "teste.bin"
        self.assertEqual(hashlib.sha256(out.read_bytes()).digest(), hashlib.sha256(PAYLOAD).digest())
        self.assertGreater(Handler.range_requests, 1, "deveria usar várias conexões")
        self.assertEqual(int(out.stat().st_mtime), 1735725600)

    def test_no_range_server(self):
        item, _ = self.run_item(self.base + "/norange/arquivo.dat")
        self.assertEqual(item["status"], engine.ST_COMPLETE, item.get("error"))
        self.assertFalse(item["resumable"])
        self.assertEqual((self.dir / "out" / "arquivo.dat").read_bytes(), PAYLOAD)

    def test_redirect_filename(self):
        item, _ = self.run_item(self.base + "/redirect")
        self.assertEqual(item["status"], engine.ST_COMPLETE, item.get("error"))
        self.assertTrue(item["final_url"].endswith("/real/arquivo%20final.bin"))

    def test_pause_resume(self):
        Handler.slow = 0.08
        item, d = self.run_item(self.base + "/x.bin", max_conn=4, wait=False)
        time.sleep(1.0)
        d.stop()
        d.thread.join(10)
        self.assertEqual(item["status"], engine.ST_PAUSED)
        got = item["downloaded"]
        self.assertGreater(got, 0)
        self.assertLess(got, len(PAYLOAD))
        Handler.slow = 0.0
        d2 = engine.Downloader(item, net.NetConfig(), str(self.dir / "tmp"), net.SpeedLimiter(0), max_conn=4,
                               min_segment=256 * 1024)
        d2.start()
        d2.thread.join(30)
        self.assertEqual(item["status"], engine.ST_COMPLETE, item.get("error"))
        self.assertEqual((self.dir / "out" / "teste.bin").read_bytes(), PAYLOAD)

    def test_speed_limiter(self):
        lim = net.SpeedLimiter(2 * 1024 * 1024)  # 2 MB/s -> ~2.5 s para 5 MB
        t0 = time.monotonic()
        item, _ = self.run_item(self.base + "/x.bin", limiter=lim)
        self.assertEqual(item["status"], engine.ST_COMPLETE)
        self.assertGreater(time.monotonic() - t0, 1.8)

    def test_zip_preview(self):
        entries = net.zip_preview(self.base + "/file.zip", {"url": ""}, net.NetConfig(), len(ZIPDATA))
        self.assertEqual([e[0] for e in entries], ["a.txt", "pasta/b.bin"])
        self.assertEqual(entries[0][1], 3000)


    def test_grabber(self):
        from ldm.grabber import Grabber
        # Como no IDM: "não explorar pais" vale para páginas; arquivos linkados entram,
        # salvo restrição em "baixar somente de caminhos/domínios".
        g = Grabber(self.base + "/site/", net.NetConfig(), file_types="zip pdf", levels=1)
        names = sorted(f["url"].rsplit("/", 1)[-1] for f in g.run())
        self.assertEqual(names, ["a.zip", "b.pdf", "c.zip", "e.zip", "fora.zip"])
        host = self.base.split("://")[1]
        g = Grabber(self.base + "/site/", net.NetConfig(), file_types="zip pdf", levels=1,
                    download_include=f"{host}/site/*")
        names = sorted(f["url"].rsplit("/", 1)[-1] for f in g.run())
        self.assertEqual(names, ["a.zip", "b.pdf", "c.zip"])
        g = Grabber(self.base + "/site/", net.NetConfig(), file_types="zip", levels=0)
        self.assertNotIn("c.zip", [f["url"].rsplit("/", 1)[-1] for f in g.run()])  # nível 0 não entra em p2

    def test_hls(self):
        from ldm import hls
        item = {"id": "h1", "url": self.base + "/hls/master.m3u8", "save_dir": str(self.dir / "out"), "filename": "video.mp4"}
        old = hls.shutil.which
        hls.shutil.which = lambda *_: None   # força o caminho sem ffmpeg (.ts concatenado)
        try:
            d = hls.HlsDownloader(item, net.NetConfig(), str(self.dir / "tmp"), net.SpeedLimiter(0), max_conn=3)
            d.start()
            d.thread.join(20)
        finally:
            hls.shutil.which = old
        self.assertEqual(item["status"], engine.ST_COMPLETE, item.get("error"))
        self.assertEqual(item["hls_variant"], "1280x720")
        self.assertEqual((self.dir / "out" / item["filename"]).read_bytes(), b"0" * 1000 + b"1" * 1000 + b"2" * 1000)


class UtilTest(unittest.TestCase):
    def test_batch(self):
        self.assertEqual(util.batch_urls("http://a/img*.jpg", "1", "3", 3),
                         ["http://a/img001.jpg", "http://a/img002.jpg", "http://a/img003.jpg"])
        self.assertEqual(util.batch_urls("http://a/*.txt", "a", "c"), ["http://a/a.txt", "http://a/b.txt", "http://a/c.txt"])

    def test_ef2_roundtrip(self):
        items = [{"url": "http://a/b.zip", "referer": "http://a/", "cookies": "x=1", "user_agent": "UA"},
                 {"url": "ftp://c/d.iso"}]
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "l.ef2"
            util.export_ef2(items, p)
            self.assertEqual(util.import_ef2(p), items)

    def test_match(self):
        self.assertTrue(util.match_ext("a.r01", "zip r0*"))
        self.assertFalse(util.match_ext("a.html", "zip r0*"))
        self.assertTrue(util.match_site("https://dl.google.com/x", "*.google.com"))
        self.assertTrue(util.match_site("https://youtube.com/x", "youtube.com"))
        self.assertFalse(util.match_site("https://example.com/x", "*.google.com"))


if __name__ == "__main__":
    unittest.main()
