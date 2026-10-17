"""API HTTP local (127.0.0.1) para a extensão do navegador e para a CLI.

Substitui o par IDMMsgHost.exe (native messaging) + named pipe do IDM: os navegadores do SteamOS são
Flatpak e não conseguem executar um host nativo, mas compartilham a rede local.

Segurança: só aceita requisições com Origin de extensão (chrome-extension:// ou moz-extension://,
que páginas web não conseguem forjar) ou com o cabeçalho X-LDM-Token (CLI local).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, VERSION
from .util import ext_of, match_ext, match_site

EXT_ORIGINS = ("chrome-extension://", "moz-extension://", "extension://")


def should_capture(settings, payload) -> bool:
    """Regras de 'Options -> File types' do IDM: tipos capturados, sites/endereços de exceção, tamanho mínimo."""
    if not settings["browser_capture"]:
        return False
    url = payload.get("url", "")
    name = payload.get("filename") or url.split("?")[0].rsplit("/", 1)[-1]
    if settings["exception_sites"] and (match_site(url, settings["exception_sites"]) or
                                        match_site(payload.get("referer", ""), settings["exception_sites"])):
        return False
    if settings["exception_addresses"] and match_site(url, settings["exception_addresses"]):
        return False
    size = int(payload.get("size") or -1)
    min_bytes = int(settings["capture_min_size_kb"] or 0) * 1024
    if size >= 0 and size < min_bytes:
        return False                      # pequeno: fica com o navegador
    if size >= 0 and min_bytes > 0 and settings["capture_any_type"]:
        return True                       # grande o bastante: o LDM assume qualquer tipo de arquivo
    # tamanho desconhecido (ou sem tamanho mínimo): decide pela lista de tipos
    return match_ext(name, settings["capture_exts"]) or (not ext_of(name) and payload.get("mime", "").startswith(
        ("application/octet-stream", "application/x-", "video/", "audio/")))


class Api:
    def __init__(self, manager, ui=None):
        self.m = manager
        self.ui = ui            # objeto com on_add(payload), on_links(payload), show() — opcional
        self.httpd = None

    def start(self):
        port = int(self.m.s["api_port"])
        api = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _origin_ok(self):
                o = self.headers.get("Origin", "")
                if o.startswith(EXT_ORIGINS):
                    return True
                # Sem Origin: só com cabeçalho próprio. Páginas web não enviam cabeçalho customizado
                # sem preflight, e o preflight de origens não-extensão é recusado em do_OPTIONS.
                return not o and (self.headers.get("X-LDM-Client") == "1" or
                                  self.headers.get("X-LDM-Token") == api.m.s["api_token"])

            def _send(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                o = self.headers.get("Origin", "")
                if o.startswith(EXT_ORIGINS):
                    self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                o = self.headers.get("Origin", "")
                if not o.startswith(EXT_ORIGINS):
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-LDM-Client")
                self.end_headers()

            def do_GET(self):
                if not self._origin_ok():
                    return self._send(403, {"error": "forbidden"})
                if self.path == "/ping":
                    return self._send(200, {
                        "app": "ldm", "name": APP_NAME, "version": VERSION, "capture": api.m.s["browser_capture"], "video": True,
                        "keys": {"prevent": api.m.s["capture_prevent_key"], "force": api.m.s["capture_force_key"]},
                        "rules": api.m.s["page_rules"] or None})
                if self.path == "/status":
                    rows = []
                    for iid, it in list(api.m.items.items()):
                        rt = api.m.runtime.get(iid, {})
                        rows.append({"id": iid, "name": it["filename"], "status": it["status"], "size": it["size"],
                                     "done": rt.get("downloaded", it.get("downloaded", 0)), "rate": rt.get("rate", 0)})
                    return self._send(200, rows[-50:])
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                if not self._origin_ok():
                    return self._send(403, {"error": "forbidden"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    payload = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)) or b"{}")
                except Exception:
                    return self._send(400, {"error": "json inválido"})
                try:
                    return self._send(200, api.dispatch(self.path, payload))
                except Exception as e:  # noqa: BLE001
                    return self._send(500, {"error": str(e)})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="ldm-api").start()

    def dispatch(self, path, p):
        if path == "/capture":
            if not should_capture(self.m.s, p):
                return {"accepted": False}
            self._add(p)
            return {"accepted": True}
        if path == "/add":
            if not p.get("url"):
                raise ValueError("url obrigatória")
            self._add(p, force_silent=p.get("silent", False))
            return {"ok": True}
        if path == "/links":
            if self.ui:
                self.ui.on_links(p)
            else:
                for ln in p.get("links", []):
                    self.m.add(ln["url"], referer=p.get("page", ""), start=False, queue_id="main")
            return {"ok": True}
        if path == "/video":
            if not (p.get("page_url") or p.get("url")):
                raise ValueError("page_url obrigatória")
            if self.ui and self.m.s["video_show_dialog"] and not p.get("silent"):
                self.ui.on_video(p)
            else:
                threading.Thread(target=self._quick_video, args=(p,), daemon=True).start()
            return {"ok": True}
        if path == "/stream":
            from .media import add_stream
            st = p.get("stream") or {}
            if not st.get("url"):
                raise ValueError("stream.url obrigatória")
            it = add_stream(self.m, st, p)
            if self.ui:
                self.ui.on_started(it["id"])
            return {"ok": True}
        if path == "/show":
            if self.ui:
                self.ui.show()
            return {"ok": True}
        raise ValueError("rota desconhecida")

    def _add(self, p, force_silent=False):
        if self.ui and not force_silent:
            self.ui.on_add(p)
        else:
            self.m.add(p["url"], filename=p.get("filename") or None, referer=p.get("referer", ""),
                       cookies=p.get("cookies", ""), user_agent=p.get("user_agent", ""),
                       description=p.get("description", ""), kind=p.get("kind"), headers=p.get("headers"),
                       start=p.get("start", True))

    def _quick_video(self, p):
        from .media import MediaError, quick_add
        try:
            quick_add(self.m, p)
        except MediaError as e:
            self.m.events.put(("log", f"vídeo: {e}"))

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
