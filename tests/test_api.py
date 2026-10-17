"""Testes da API local: regras de captura, bloqueio de páginas web e fila/gerenciador sem interface."""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = TMP + "/cfg"
os.environ["XDG_DATA_HOME"] = TMP + "/data"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldm import config  # noqa: E402
from ldm.manager import Manager  # noqa: E402
from ldm.server import Api, should_capture  # noqa: E402
from test_engine import Handler, PAYLOAD, ThreadingHTTPServer  # noqa: E402
import threading  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        s = config.Settings()
        s["api_port"] = 19614
        s["general_folder"] = TMP + "/dl"
        s["temp_dir"] = TMP + "/tmp"
        s["categories"] = []
        cls.m = Manager(s)
        cls.m.run()
        cls.api = Api(cls.m)
        cls.api.start()

    @classmethod
    def tearDownClass(cls):
        cls.api.stop()
        cls.m.shutdown()
        cls.srv.shutdown()

    def req(self, path, payload=None, headers=None):
        r = urllib.request.Request("http://127.0.0.1:19614" + path,
                                   data=json.dumps(payload).encode() if payload is not None else None,
                                   headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read())

    def test_blocks_web_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req("/add", {"url": "http://x/y.zip"}, {"Origin": "https://evil.example"})
        self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError):
            self.req("/ping")  # sem cabeçalho próprio

    def test_extension_origin_and_capture(self):
        h = {"Origin": "chrome-extension://abc"}
        self.assertEqual(self.req("/ping", headers=h)["app"], "ldm")
        self.assertFalse(self.req("/capture", {"url": "http://x/pagina.html"}, h)["accepted"])
        r = self.req("/capture", {"url": self.base + "/arq.zip", "filename": "arq.zip"}, h)
        self.assertTrue(r["accepted"])
        it = self.m.find_by_url(self.base + "/arq.zip")
        for _ in range(100):
            if it["status"] == "complete":
                break
            time.sleep(0.1)
        self.assertEqual(it["status"], "complete", it.get("error"))
        self.assertEqual((Path(it["save_dir"]) / it["filename"]).read_bytes(), PAYLOAD)

    def test_capture_rules(self):
        s = {"browser_capture": True, "capture_exts": "zip mp4", "exception_sites": "*.google.com",
             "exception_addresses": "", "capture_min_size_kb": 100}
        self.assertTrue(should_capture(s, {"url": "https://a.com/x.zip"}))
        self.assertFalse(should_capture(s, {"url": "https://dl.google.com/x.zip"}))
        self.assertFalse(should_capture(s, {"url": "https://a.com/x.zip", "size": 1000}))
        self.assertTrue(should_capture(s, {"url": "https://a.com/dl?id=1", "mime": "application/octet-stream"}))

    def test_queue(self):
        q = self.m.add_queue("teste")
        q["parallel"] = 2
        ids = [self.m.add(self.base + f"/q{i}.bin", start=False, queue_id=q["id"])["id"] for i in range(3)]
        self.m.start_queue(q["id"])
        for _ in range(200):
            if all(self.m.items[i]["status"] == "complete" for i in ids) and not q["running"]:
                break
            time.sleep(0.1)
        self.assertTrue(all(self.m.items[i]["status"] == "complete" for i in ids))
        self.assertFalse(q["running"])
        names = sorted(self.m.items[i]["filename"] for i in ids)
        self.assertEqual(len(set(names)), 3, names)  # mesmo nome do servidor -> numerados


if __name__ == "__main__":
    unittest.main()
