"""Janela "Baixar vídeo": análise da página com yt-dlp, escolha de qualidade e streams capturados."""
import threading
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

from .. import APP_NAME, media  # noqa: E402
from ..util import fmt_eta, fmt_size, looks_like_url  # noqa: E402
from .dialogs import queue_options  # noqa: E402
from .widgets import check, combo, entry, folder_entry, message, scrolled  # noqa: E402

VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "twitch.tv", "tiktok.com", "instagram.com",
               "facebook.com", "fb.watch", "x.com", "twitter.com", "reddit.com", "bilibili.com", "soundcloud.com",
               "kick.com", "rumble.com", "odysee.com", "globo.com", "streamable.com", "vk.com", "ok.ru")


def is_video_page(url: str) -> bool:
    from urllib.parse import urlsplit
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)


class VideoDialog(Gtk.Window):
    def __init__(self, win, payload):
        super().__init__(title=f"Baixar vídeo - {APP_NAME}")
        self.w, self.m, self.p = win, win.m, dict(payload)
        self.info = None
        self.folder_touched = False
        self.set_default_size(760, 560)
        self.set_icon_name("ldm-video-x-generic")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.add(outer)

        head = Gtk.Box(spacing=12)
        self.thumb = Gtk.Image.new_from_icon_name("ldm-video-x-generic", Gtk.IconSize.DIALOG)
        self.thumb.set_size_request(192, 108)
        head.pack_start(self.thumb, False, False, 0)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.title_lbl = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.title_lbl.set_markup(f"<b>{GLib.markup_escape_text(self.p.get('title') or 'Analisando...')}</b>")
        self.meta_lbl = Gtk.Label(xalign=0, wrap=True)
        url = self.p.get("page_url") or self.p.get("url") or ""
        self.url_lbl = Gtk.Label(label=url, xalign=0, ellipsize=3, selectable=True)
        self.url_lbl.get_style_context().add_class("dim-label")
        st = Gtk.Box(spacing=6)
        self.spinner = Gtk.Spinner(active=True)
        self.status = Gtk.Label(label="Analisando o vídeo com yt-dlp...", xalign=0, wrap=True)
        st.pack_start(self.spinner, False, False, 0)
        st.pack_start(self.status, True, True, 0)
        for w_ in (self.title_lbl, self.meta_lbl, self.url_lbl, st):
            tb.pack_start(w_, False, False, 0)
        head.pack_start(tb, True, True, 0)
        outer.pack_start(head, False, False, 0)

        # árvore de opções: grupo -> opções
        self.store = Gtk.TreeStore(str, str, str, str, object)
        self.tv = Gtk.TreeView(model=self.store)
        for i, t in enumerate(["Qualidade", "Formato", "Codec", "Tamanho"]):
            c = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), markup=i) if i == 0 else \
                Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            c.set_expand(i == 0)
            self.tv.append_column(c)
        self.tv.get_selection().connect("changed", self._on_select)
        self.tv.connect("row-activated", lambda *_: self._go(True))
        sw = scrolled(self.tv, 230)
        sw.get_style_context().add_class("ldm-videolist")
        outer.pack_start(sw, True, True, 0)

        opts = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.name = entry(self.p.get("title") or "")
        opts.attach(Gtk.Label(label="Nome do arquivo:", xalign=0), 0, 0, 1, 1)
        opts.attach(self.name, 1, 0, 3, 1)
        self.name.set_hexpand(True)
        self.folder = folder_entry(self, media.video_folder(self.m.s))
        self.folder.entry.connect("changed", lambda *_: setattr(self, "folder_touched", True))
        opts.attach(Gtk.Label(label="Salvar em:", xalign=0), 0, 1, 1, 1)
        opts.attach(self.folder, 1, 1, 3, 1)
        self.subs = check(f"Baixar legendas ({self.m.s.get('video_sub_langs') or 'pt.*,en.*'}) embutidas",
                          self.m.s.get("video_subs"))
        self.playlist = check("Baixar a playlist inteira")
        self.playlist.set_no_show_all(True)
        if "list=" in url:
            self.playlist.show()
        opts.attach(self.subs, 0, 2, 2, 1)
        opts.attach(self.playlist, 2, 2, 2, 1)
        outer.pack_start(opts, False, False, 0)

        bb = Gtk.Box(spacing=6)
        self.queue = combo(queue_options(self.m), "main")
        later = Gtk.Button(label="Baixar depois")
        later.connect("clicked", lambda _: self._go(False))
        self.go_b = Gtk.Button(label="Baixar agora")
        self.go_b.get_style_context().add_class("ldm-video")   # âmbar = vídeo
        self.go_b.connect("clicked", lambda _: self._go(True))
        cancel = Gtk.Button(label="Cancelar")
        cancel.connect("clicked", lambda _: self.destroy())
        bb.pack_start(Gtk.Label(label="Fila:"), False, False, 0)
        bb.pack_start(self.queue, False, False, 0)
        bb.pack_end(self.go_b, False, False, 0)
        bb.pack_end(later, False, False, 0)
        bb.pack_end(cancel, False, False, 0)
        outer.pack_start(bb, False, False, 0)
        self.go_b.set_sensitive(False)

        self._add_sniffed()
        self.show_all()
        self.present()
        threading.Thread(target=self._probe, daemon=True).start()

    # ---------------------------------------------------------------- análise
    def _probe(self):
        if self.m.s.get("video_mode") == "capture":
            GLib.idle_add(self._fill, None, "modo só captura (modo IDM) ativado em Opções → Vídeo")
            return
        try:
            info = media.probe(media.Backend(self.m.s), media.candidates_from(self.p), self.p, self.p.get("cookies"))
            GLib.idle_add(self._fill, info, None)
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(self._fill, None, str(e))

    def _fill(self, info, err):
        self.spinner.stop()
        self.spinner.hide()
        if err:
            n = len(getattr(self, "passive", []))
            self.status.set_text(f"yt-dlp não reconheceu esta página: {err}" +
                                 (f"\nUse uma das {n} opções capturadas do navegador (★ = o vídeo que você clicou)." if n else ""))
            best = media.best_passive(getattr(self, "passive", []), int(self.m.s.get("video_max_height") or 0))
            self._select_choice(best) if best else self._select_first()
            return
        self.info = info
        title = info.get("title") or "video"
        self.title_lbl.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        if not self.name.get_text().strip() or self.name.get_text() == self.p.get("title"):
            self.name.set_text(title)
        meta = [info.get("extractor_key") or "", info.get("uploader") or info.get("channel") or "",
                fmt_eta(info.get("duration")) if info.get("duration") else ""]
        self.meta_lbl.set_text(" · ".join(x for x in meta if x))
        self.status.set_text("Escolha a qualidade." + ("  (usando cookies do navegador)" if info.get("_ldm_cookies") else ""))
        choices = media.build_choices(info, self.m.s.get("video_prefer_mp4", True))
        gv = self.store.prepend(None, ["<b>Vídeo</b>", "", "", "", None])
        ga = None
        for c in choices:
            parent = gv
            if c["kind"] == "audio":
                ga = ga or self.store.insert_after(None, gv, ["<b>Somente áudio</b>", "", "", "", None])
                parent = ga
            size = ("~" + fmt_size(c["size"])) if c.get("size") else ""
            speed = " ⚡" if all(p in media.NATIVE_PROTOCOLS for p in c.get("protocols") or ["?"]) and not c.get("mp3") else ""
            self.store.append(parent, [GLib.markup_escape_text(c["label"]) + speed, c["ext"], c["codec"], size, c])
        self.tv.expand_all()
        default = media.default_choice(choices, int(self.m.s.get("video_max_height") or 0))
        self._select_choice(default)
        thumbs = [t for t in info.get("thumbnails") or [] if t.get("url")]
        jpgs = [t for t in thumbs if t["url"].split("?")[0].lower().endswith((".jpg", ".jpeg", ".png"))]
        pick = max(jpgs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0) or t.get("preference") or 0,
                   default=None) if jpgs else None
        url = (pick or {}).get("url") or info.get("thumbnail")
        if url:
            threading.Thread(target=self._load_thumb, args=(url,), daemon=True).start()

    def _add_sniffed(self):
        """Grupo 'Capturado do navegador (modo IDM)': streams que o player pediu, prontos para baixar."""
        self.passive = media.passive_choices(self.p)
        if not self.passive:
            if media.sabr_only(self.p):
                self.store.append(None, ["<i>YouTube entregou o vídeo por SABR: só o yt-dlp consegue baixar</i>",
                                         "", "", "", None])
            return
        g = self.store.append(None, ["<b>Capturado do navegador (modo IDM)</b>", "", "", "", None])
        for c in self.passive:
            size = fmt_size(c["size"]) if c.get("size") else ""
            star = " ★" if c.get("match") else ""
            self.store.append(g, [GLib.markup_escape_text(c["label"]) + star, c["ext"], c.get("codec", ""), size, c])
        self.tv.expand_all()

    def _select_choice(self, choice):
        def walk(it):
            while it:
                if self.store[it][4] is choice:
                    self.tv.get_selection().select_iter(it)
                    self.tv.scroll_to_cell(self.store.get_path(it), None, False, 0, 0)
                    return True
                if walk(self.store.iter_children(it)):
                    return True
                it = self.store.iter_next(it)
            return False
        if choice is not None:
            walk(self.store.get_iter_first())

    def _select_first(self):
        it = self.store.get_iter_first()
        while it:
            child = self.store.iter_children(it)
            if child:
                self.tv.get_selection().select_iter(child)
                return
            it = self.store.iter_next(it)

    def _on_select(self, sel):
        model, it = sel.get_selected()
        ch = model[it][4] if it else None
        self.go_b.set_sensitive(ch is not None)
        if ch and not self.folder_touched and ch.get("kind") in ("audio", "video"):
            self.folder.entry.set_text(media.video_folder(self.m.s, ch["kind"] == "audio"))
            self.folder_touched = False

    def _load_thumb(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read(4 * 1024 * 1024)
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pb = loader.get_pixbuf()
            w_, h_ = pb.get_width(), pb.get_height()
            k = min(192 / w_, 108 / h_)
            pb = pb.scale_simple(max(1, int(w_ * k)), max(1, int(h_ * k)), GdkPixbuf.InterpType.BILINEAR)
            GLib.idle_add(self.thumb.set_from_pixbuf, pb)
        except Exception:  # noqa: BLE001 - miniatura é opcional
            pass

    # ---------------------------------------------------------------- download
    def _go(self, now):
        model, it = self.tv.get_selection().get_selected()
        ch = model[it][4] if it else None
        if not ch:
            return
        qid = None if now else self.queue.get_active_id()
        try:
            if ch.get("source") == "passive":
                item = media.add_passive(self.m, ch, self.p, filename=self.name.get_text().strip() or None,
                                         folder=self.folder.entry.get_text().strip() or None, start=now, queue_id=qid)
            else:
                item = media.add_choice(self.m, self.info, ch, self.p, filename=self.name.get_text().strip() or None,
                                        folder=self.folder.entry.get_text().strip() or None,
                                        subs=self.subs.get_active(), playlist=self.playlist.get_active(),
                                        start=now, queue_id=qid)
        except Exception as e:  # noqa: BLE001
            message(self, f"Não foi possível adicionar: {e}", Gtk.MessageType.ERROR)
            return
        if now and self.m.s["show_progress_dialog"]:
            self.w.open_progress(item["id"])
        self.destroy()


def ask_video_url(win):
    """Tarefas -> Baixar vídeo de uma página."""
    clip = win.clipboard.wait_for_text() or ""
    d = Gtk.Dialog(title="Baixar vídeo de uma página", transient_for=win, modal=True)
    d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Analisar", Gtk.ResponseType.OK)
    d.set_default_response(Gtk.ResponseType.OK)
    d.set_default_size(560, -1)
    box = d.get_content_area()
    box.set_spacing(6)
    box.set_border_width(10)
    box.add(Gtk.Label(label="Endereço da página do vídeo (YouTube, Vimeo, Instagram, qualquer site com vídeo):", xalign=0))
    e = entry(clip.strip() if looks_like_url(clip) else "")
    e.set_activates_default(True)
    box.add(e)
    d.show_all()
    url = e.get_text().strip() if d.run() == Gtk.ResponseType.OK else ""
    d.destroy()
    if url:
        VideoDialog(win, {"page_url": url})


def video_options_page(dialog, s):
    """Aba 'Vídeo' do diálogo de opções. Retorna (widget, função_aplicar)."""
    g = Gtk.Grid(column_spacing=8, row_spacing=6, margin=10)
    status = Gtk.Label(label="Verificando yt-dlp...", xalign=0, wrap=True, selectable=True)
    g.attach(status, 0, 0, 2, 1)
    upd = Gtk.Button(label="Instalar / atualizar yt-dlp")
    g.attach(upd, 0, 1, 1, 1)
    note = Gtk.Label(label="Atualize sempre que um site parar de funcionar: o YouTube muda com frequência.",
                     xalign=0, wrap=True)
    g.attach(note, 1, 1, 1, 1)

    def check_backend(refresh=False):
        try:
            launcher, exe, v = media.Backend(s).resolve(refresh=refresh)
            where = f"na distrobox '{launcher[2]}'" if launcher else "no host"
            deno = "deno ok" if media.deno_path() else "sem deno (YouTube pode falhar)"
            where = "embutido na AppImage" if media.bundled() and not launcher and exe[-1] == "yt_dlp" else where
            GLib.idle_add(status.set_text, f"yt-dlp {v} {where} · {deno}")
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(status.set_text, str(e))

    def do_update(_):
        upd.set_sensitive(False)
        status.set_text("Atualizando yt-dlp... (pode levar alguns minutos)")

        def work():
            ok, out = media.Backend(s).update()
            GLib.idle_add(status.set_text, ("Atualizado: " if ok else "Falhou: ") + out.splitlines()[-1] if out else "")
            GLib.idle_add(upd.set_sensitive, True)
            if ok:
                check_backend(True)
        threading.Thread(target=work, daemon=True).start()

    upd.connect("clicked", do_update)
    threading.Thread(target=check_backend, daemon=True).start()

    show = check("Mostrar a janela de escolha de qualidade (desmarcado: baixa direto na qualidade padrão)",
                 s["video_show_dialog"])
    vmode = combo([("auto", "yt-dlp + captura do navegador (recomendado)"),
                   ("capture", "Só captura do navegador (modo IDM, sem yt-dlp)")], s["video_mode"])
    mp4 = check("Preferir MP4 H.264/AAC (máxima compatibilidade com players e TVs)", s["video_prefer_mp4"])
    subs = check("Baixar legendas por padrão", s["video_subs"])
    for i, w_ in enumerate((show, mp4, subs), start=2):
        g.attach(w_, 0, i, 2, 1)
    hmax = combo([(str(h), f"{h}p" if h else "Melhor disponível") for h in (0, 2160, 1440, 1080, 720, 480, 360)],
                 str(s["video_max_height"]))
    g.attach(Gtk.Label(label="Modo:", xalign=0), 0, 10, 1, 1)
    g.attach(vmode, 1, 10, 1, 1)
    g.attach(Gtk.Label(label="Qualidade padrão:", xalign=0), 0, 5, 1, 1)
    g.attach(hmax, 1, 5, 1, 1)
    langs = entry(s["video_sub_langs"])
    g.attach(Gtk.Label(label="Idiomas das legendas:", xalign=0), 0, 6, 1, 1)
    g.attach(langs, 1, 6, 1, 1)
    folder = folder_entry(dialog, s["video_folder"] or media.video_folder(s))
    g.attach(Gtk.Label(label="Pasta dos vídeos:", xalign=0), 0, 7, 1, 1)
    g.attach(folder, 1, 7, 1, 1)
    box = entry(s["distrobox_name"])
    g.attach(Gtk.Label(label="Distrobox do yt-dlp:", xalign=0), 0, 8, 1, 1)
    g.attach(box, 1, 8, 1, 1)
    cmd = entry(s["ytdlp_cmd"], "vazio = detectar automaticamente")
    g.attach(Gtk.Label(label="Comando do yt-dlp (avançado):", xalign=0), 0, 9, 1, 1)
    g.attach(cmd, 1, 9, 1, 1)
    folder.set_hexpand(True)

    def apply():
        s["video_show_dialog"] = show.get_active()
        s["video_mode"] = vmode.get_active_id() or "auto"
        s["video_prefer_mp4"] = mp4.get_active()
        s["video_subs"] = subs.get_active()
        s["video_max_height"] = int(hmax.get_active_id() or 0)
        s["video_sub_langs"] = langs.get_text().strip() or "pt.*,en.*"
        f = folder.entry.get_text().strip()
        s["video_folder"] = "" if f == media.video_folder({**s.data, "video_folder": ""}) else f
        if box.get_text().strip() != s["distrobox_name"] or cmd.get_text().strip() != s["ytdlp_cmd"]:
            s["distrobox_name"] = box.get_text().strip() or "ubuntu-24-04"
            s["ytdlp_cmd"] = cmd.get_text().strip()
            media.Backend._cache = None
    return g, apply
