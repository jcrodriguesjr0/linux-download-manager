"""Testes do grabber de vídeo com um yt-dlp falso (sem rede externa)."""
import os
import shlex
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ldm import engine, media, net  # noqa: E402
from test_engine import Handler, ThreadingHTTPServer  # noqa: E402

FAKE = f"{shlex.quote(sys.executable)} {shlex.quote(str(ROOT / 'tests/fixtures/fake_ytdlp.py'))}"


class MediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        os.environ["FAKE_BASE"] = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        media.Backend._cache = None
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.s = {"ytdlp_cmd": FAKE, "video_req_chunk_mb": 1}

    def tearDown(self):
        self.tmp.cleanup()
        media.Backend._cache = None

    def test_choices(self):
        info = media.probe(media.Backend(self.s), ["https://site/v"], {}, None)
        ch = media.build_choices(info, prefer_mp4=True)
        self.assertEqual([c["label"] for c in ch], ["1080p", "720p", "480p", "Somente áudio", "Somente áudio"])
        self.assertTrue(ch[0]["selector"].startswith("137+140/"))          # H.264 + AAC sem DRC
        self.assertEqual(ch[0]["ext"], "MP4")
        self.assertTrue(ch[1]["selector"].startswith("22/"))              # progressivo (já tem áudio)
        self.assertEqual(ch[2]["protocols"], ["m3u8_native"])
        self.assertTrue(ch[4].get("mp3"))
        ch2 = media.build_choices(info, prefer_mp4=False)
        self.assertTrue(ch2[0]["selector"].startswith("248+251/"))       # melhor: VP9 + Opus
        self.assertEqual(ch2[0]["ext"], "WEBM")
        self.assertEqual(media.default_choice(ch, 720)["label"], "720p")

    def test_probe_retries_with_cookies(self):
        b = media.Backend(self.s)
        with self.assertRaises(media.MediaError):
            media.probe(b, ["https://site/nologin"], {}, None)
        info = media.probe(b, ["https://site/nologin"], {}, [{"domain": ".site", "name": "s", "value": "1"}])
        self.assertTrue(info["_ldm_cookies"])

    def test_cookie_file(self):
        p = media.write_cookie_file(self.d / "c.txt", [
            {"domain": ".youtube.com", "hostOnly": False, "path": "/", "secure": True, "expirationDate": 2e9, "name": "A", "value": "1"},
            {"domain": "www.site.com", "hostOnly": True, "path": "/x", "name": "B", "value": "2"}])
        lines = p.read_text().splitlines()
        self.assertEqual(lines[0], "# Netscape HTTP Cookie File")
        self.assertEqual(lines[1].split("\t"), [".youtube.com", "TRUE", "/", "TRUE", "2000000000", "A", "1"])
        self.assertEqual(lines[2].split("\t")[:2], ["www.site.com", "FALSE"])
        self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")

    def _item(self, choice, name="saida"):
        return {"id": "m1", "url": "https://site/v", "save_dir": str(self.d / "out"), "filename": "",
                "video": {"selector": choice["selector"], "merge": choice.get("merge"), "protocols": choice["protocols"],
                          "mp3": choice.get("mp3", False), "filename": name}}

    def _run(self, it, wait=True):
        d = media.VideoDownloader(it, net.NetConfig(), str(self.d / "tmp"), net.SpeedLimiter(0), max_conn=4,
                                  min_segment=256 * 1024, settings=self.s)
        d.start()
        if wait:
            d.thread.join(30)
        return d

    def test_native_progressive(self):
        """Formato HTTP direto: baixado pelo motor multi-conexão do LDM, sem yt-dlp no download."""
        ch = media.build_choices(media.probe(media.Backend(self.s), ["https://site/v"], {}, None))
        it = self._item(ch[1])                       # 720p progressivo (formato 22)
        d = self._run(it)
        self.assertEqual(it["status"], engine.ST_COMPLETE, it.get("error"))
        self.assertEqual(d.mode, "native")
        self.assertEqual(it["filename"], "saida.mp4")
        self.assertEqual((self.d / "out" / "saida.mp4").stat().st_size, 5 * 1024 * 1024 + 123)

    def test_ytdlp_path_and_pause(self):
        ch = media.build_choices(media.probe(media.Backend(self.s), ["https://site/v"], {}, None))
        it = self._item(ch[2])                       # HLS -> caminho yt-dlp
        d = self._run(it)
        self.assertEqual(it["status"], engine.ST_COMPLETE, it.get("error"))
        self.assertEqual(d.mode, "ytdlp")
        self.assertEqual(it["filename"], "saida.mp4")
        os.environ.update(FAKE_STEPS="100", FAKE_DELAY="0.05")
        try:
            it2 = self._item(ch[2], "pausado")
            d2 = self._run(it2, wait=False)
            time.sleep(1.2)
            self.assertGreater(d2.downloaded(), 0)
            d2.stop()
            d2.thread.join(10)
            self.assertEqual(it2["status"], engine.ST_PAUSED)
            self.assertFalse((self.d / "out" / "pausado.mp4").exists())
        finally:
            os.environ.update(FAKE_STEPS="5", FAKE_DELAY="0.05")

    def test_mp3(self):
        ch = media.build_choices(media.probe(media.Backend(self.s), ["https://site/v"], {}, None))
        it = self._item(ch[4], "musica")
        d = self._run(it)
        self.assertEqual(it["status"], engine.ST_COMPLETE, it.get("error"))
        self.assertEqual(d.mode, "ytdlp")
        self.assertEqual(it["filename"], "musica.mp3")


    def test_direct_stream(self):
        """Stream capturado baixado pelo motor do LDM, sem yt-dlp (como o IDM)."""
        base = os.environ["FAKE_BASE"]
        payload = {"page_url": base + "/pagina", "user_agent": "UA-navegador",
                   "sniffed": [{"key": f"f:{base}/video.bin", "kind": "video", "type": "video/mp4", "url": f"{base}/video.bin", "size": 5 * 1024 * 1024 + 123}]}
        c = media.passive_choices(payload)[0]
        it = {"id": "dp1", "url": payload["page_url"], "save_dir": str(self.d / "out"), "filename": "", "user_agent": "UA-navegador",
              "video": {"direct": c["direct"], "merge": None, "protocols": ["https"], "filename": "capturado", "selector": "b"}}
        d = self._run(it)
        self.assertEqual(it["status"], engine.ST_COMPLETE, it.get("error"))
        self.assertEqual(d.mode, "native")
        self.assertEqual(it["filename"], "capturado.mp4")
        self.assertEqual((self.d / "out" / "capturado.mp4").stat().st_size, 5 * 1024 * 1024 + 123)


MPD = """<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
<Period><AdaptationSet mimeType="video/mp4" contentType="video">
<Representation id="v1" height="720" bandwidth="2000000" codecs="avc1.64001f"><BaseURL>v720.mp4</BaseURL></Representation>
<Representation id="v2" height="360" bandwidth="600000" codecs="avc1.4d401e"><BaseURL>https://cdn.x.com/v360.mp4</BaseURL></Representation>
</AdaptationSet><AdaptationSet mimeType="audio/mp4" contentType="audio">
<Representation id="a1" bandwidth="128000" codecs="mp4a.40.2"><BaseURL>a128.m4a</BaseURL></Representation>
</AdaptationSet></Period></MPD>"""


class PassiveTest(unittest.TestCase):
    def gv(self, itag, mime, clen, vid="abc", dur=212.3):
        return {"key": f"gv:{vid}:{itag}", "group": f"gv:{vid}", "kind": "audio" if mime.startswith("audio") else "video",
                "type": mime, "itag": itag, "size": clen, "dur": dur,
                "url": f"https://r1.googlevideo.com/videoplayback?id={vid}&itag={itag}&clen={clen}",
                "headers": {"referer": "https://www.youtube.com/", "origin": "https://www.youtube.com"}}

    def test_youtube_groups(self):
        payload = {"page_url": "https://www.youtube.com/watch?v=x", "video_hint": {"duration": 212.0},
                   "sniffed": [self.gv("137", "video/mp4", 5000), self.gv("136", "video/mp4", 3000),
                               self.gv("140", "audio/mp4", 800), self.gv("251", "audio/webm", 900),
                               self.gv("248", "video/webm", 4500, vid="ad", dur=15)]}
        ch = media.passive_choices(payload)
        first = ch[0]
        self.assertEqual(first["label"], "1080p")
        self.assertTrue(first["match"])                                  # duração bate com o player clicado
        self.assertEqual([d["ext"] for d in first["direct"]], ["mp4", "m4a"])   # prefere AAC para MP4
        self.assertEqual(first["merge"], "mp4")
        self.assertEqual(first["size"], 5800)
        self.assertEqual(first["direct"][0]["headers"]["Origin"], "https://www.youtube.com")
        ad = [c for c in ch if c.get("group") == "gv:ad"]
        self.assertTrue(ad and not ad[0]["match"])                       # anúncio de 15 s fica para trás
        self.assertEqual(media.best_passive(ch, 720)["label"], "720p")

    def test_inline_mpd(self):
        payload = {"page_url": "https://www.instagram.com/p/1/",
                   "sniffed": [{"key": "pm:1", "kind": "manifest", "type": "DASH", "manifest_text": MPD,
                                "base": "https://cdn.x.com/dir/"}]}
        ch = media.passive_choices(payload)
        self.assertEqual([c["label"] for c in ch], ["720p", "360p"])
        self.assertEqual(ch[0]["direct"][0]["url"], "https://cdn.x.com/dir/v720.mp4")
        self.assertEqual(ch[0]["direct"][1]["url"], "https://cdn.x.com/dir/a128.m4a")

    def test_manifest_and_files(self):
        payload = {"page_url": "https://site.com/v", "video_hint": {"current_src": "https://cdn.site.com/a.mp4"},
                   "sniffed": [{"key": "m:https://s.com/master.m3u8", "kind": "manifest", "type": "HLS", "url": "https://s.com/master.m3u8"},
                               {"key": "f:https://cdn.site.com/a.mp4", "kind": "video", "type": "video/mp4", "url": "https://cdn.site.com/a.mp4", "size": 9_000_000},
                               {"key": "sabr:x", "kind": "sabr", "url": "https://r.googlevideo.com/videoplayback?sabr=1"}]}
        ch = media.passive_choices(payload)
        self.assertEqual(ch[0]["label"], "a.mp4")                        # o src do player clicado vem primeiro
        self.assertTrue(any(c.get("stream") for c in ch))
        self.assertTrue(media.sabr_only(payload))      # a parte do YouTube só veio por SABR
        self.assertTrue(media.sabr_only({"sniffed": [{"kind": "sabr", "key": "sabr:x"}]}))

    def test_cookie_header(self):
        cks = [{"domain": ".site.com", "hostOnly": False, "path": "/", "name": "a", "value": "1"},
               {"domain": "other.com", "hostOnly": True, "path": "/", "name": "b", "value": "2"},
               {"domain": "cdn.site.com", "hostOnly": True, "path": "/priv", "name": "c", "value": "3", "secure": True}]
        self.assertEqual(media.cookie_header(cks, "https://cdn.site.com/priv/x.mp4"), "a=1; c=3")
        self.assertEqual(media.cookie_header(cks, "http://cdn.site.com/priv/x.mp4"), "a=1")


if __name__ == "__main__":
    unittest.main()
