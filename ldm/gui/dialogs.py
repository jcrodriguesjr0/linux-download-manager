"""Diálogos de download: adicionar URL, informações do arquivo, progresso, conclusão, propriedades,
lote, todos os links, prévia ZIP, duplicado e limitador de velocidade."""
import shutil
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import net, sysint  # noqa: E402
from . import theme  # noqa: E402
from ..engine import ST_COMPLETE, ST_CONNECTING, ST_DOWNLOADING  # noqa: E402
from ..util import (batch_urls, ext_of, filename_from_headers, fmt_eta, fmt_rate, fmt_size,  # noqa: E402
                    looks_like_url, match_ext)
from .widgets import (check, check_list, combo, confirm, entry, folder_entry, grid, message, raise_popup, row,  # noqa: E402
                      scrolled, spin)


def queue_options(m):
    return [(q["id"], q["name"]) for q in m.queues.values()]


# ---------------------------------------------------------------- Adicionar URL
class AddUrlDialog(Gtk.Dialog):
    def __init__(self, parent, clip=""):
        super().__init__(title="Digite o novo endereço para baixar", transient_for=parent, modal=True)
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(560, -1)
        g = grid()
        self.url = row(g, 0, "Endereço:", entry(clip if looks_like_url(clip) else ""))
        self.url.set_activates_default(True)
        self.use_auth = check("Usar autorização")
        g.attach(self.use_auth, 0, 1, 2, 1)
        self.user = row(g, 2, "Usuário:", entry())
        self.pwd = row(g, 3, "Senha:", entry(visibility=False))
        for w in (self.user, self.pwd):
            w.set_sensitive(False)
        self.use_auth.connect("toggled", lambda b: [w.set_sensitive(b.get_active()) for w in (self.user, self.pwd)])
        self.get_content_area().add(g)
        self.show_all()

    def get(self):
        ok = self.run() == Gtk.ResponseType.OK
        res = None
        if ok and self.url.get_text().strip():
            res = {"url": self.url.get_text().strip()}
            if self.use_auth.get_active():
                res.update(auth_user=self.user.get_text(), auth_pass=self.pwd.get_text())
        self.destroy()
        return res


# ---------------------------------------------------------------- Informações do arquivo
class FileInfoDialog(Gtk.Dialog):
    """Equivalente ao 'Download File Info' do IDM: categoria, Salvar como, descrição, iniciar/baixar depois."""

    def __init__(self, win, payload):
        super().__init__(title="Informações do arquivo para download", transient_for=win, modal=False)
        self.w, self.m, self.p = win, win.m, dict(payload)
        self.set_default_size(620, -1)
        url = self.p["url"]
        fname = self.p.get("filename") or filename_from_headers(url, None)
        g = grid()
        self.url = row(g, 0, "URL:", entry(url))
        cats = [("Geral", "Geral")] + [(c["name"], c["name"]) for c in self.m.s["categories"]]
        cat_name, folder = self.m.resolve_target(url, fname)
        self.cat = row(g, 1, "Categoria:", combo(cats, cat_name))
        self.path = row(g, 2, "Salvar como:", entry(str(Path(folder) / fname)))
        b = Gtk.Button(label="...")
        b.connect("clicked", self._browse)
        g.attach(b, 2, 2, 1, 1)
        self.desc = row(g, 3, "Descrição:", entry(self.p.get("description", "")))
        self.size_lbl = Gtk.Label(label="Tamanho: verificando...", xalign=0)
        g.attach(self.size_lbl, 0, 4, 3, 1)
        self.queue = row(g, 5, "Fila (baixar depois):", combo(queue_options(self.m), "main"))
        self.cat.connect("changed", self._cat_changed)
        self.get_content_area().add(g)
        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        self.add_button("Baixar depois", 2)
        start = self.add_button("Iniciar download", Gtk.ResponseType.OK)
        start.get_style_context().add_class("suggested-action")
        self.connect("response", self._response)
        raise_popup(self)
        threading.Thread(target=self._probe, daemon=True).start()

    def _probe(self):
        size, name = -1, None
        try:
            s = net.open_stream(self.p["url"], self.p, net.NetConfig(self.m.s), start=0, end=0)
            try:
                h = getattr(s, "headers", None) or {}
                cr = h.get("Content-Range", "") if h else ""
                if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                    size = int(cr.rsplit("/", 1)[1])
                elif h and (h.get("Content-Length") or "").isdigit() and getattr(s, "status", 0) == 200:
                    size = int(h["Content-Length"])
                elif isinstance(s, net.FtpStream):
                    size = s.size or -1
                if h and not self.p.get("filename"):
                    name = filename_from_headers(s.geturl() or self.p["url"], h)
                resumable = getattr(s, "status", 0) == 206
            finally:
                s.close()
            GLib.idle_add(self._probed, size, name, resumable)
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(self.size_lbl.set_text, f"Tamanho: desconhecido ({str(e)[:80]})")

    def _probed(self, size, name, resumable):
        self.size_lbl.set_text(f"Tamanho: {fmt_size(size) or 'desconhecido'}   ·   Retomada: {'Sim' if resumable else 'Não'}")
        if name:
            p = Path(self.path.get_text())
            self.path.set_text(str(p.with_name(name)))
            cat_name, _ = self.m.resolve_target(self.p["url"], name)
            self.cat.set_active_id(cat_name)

    def _cat_changed(self, c):
        cid = c.get_active_id()
        folder = self.m.s["general_folder"]
        for cat in self.m.s["categories"]:
            if cat["name"] == cid:
                folder = cat["folder"]
        self.path.set_text(str(Path(folder) / Path(self.path.get_text()).name))

    def _browse(self, _):
        d = Gtk.FileChooserDialog(title="Salvar como", transient_for=self, action=Gtk.FileChooserAction.SAVE)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Salvar", Gtk.ResponseType.OK)
        p = Path(self.path.get_text())
        if p.parent.exists():
            d.set_current_folder(str(p.parent))
        d.set_current_name(p.name)
        if d.run() == Gtk.ResponseType.OK:
            self.path.set_text(d.get_filename())
        d.destroy()

    def _response(self, _, resp):
        if resp in (Gtk.ResponseType.OK, 2):
            p = Path(self.path.get_text()).expanduser()
            kw = {k: self.p.get(k, "") for k in ("referer", "cookies", "user_agent", "auth_user", "auth_pass")}
            it = self.m.add(self.url.get_text().strip(), filename=p.name, save_dir=str(p.parent),
                            description=self.desc.get_text(), start=resp == Gtk.ResponseType.OK,
                            queue_id=self.queue.get_active_id() if resp == 2 else None,
                            category=self.cat.get_active_id(), kind=self.p.get("kind"),
                            headers=self.p.get("headers"), duplicate=self.w.ask_duplicate(self.url.get_text().strip()),
                            **kw)
            if resp == Gtk.ResponseType.OK and self.m.s["show_progress_dialog"]:
                self.w.open_progress(it["id"])
        self.destroy()


# ---------------------------------------------------------------- Duplicado
def ask_duplicate(parent, settings):
    d = Gtk.Dialog(title="Link de download duplicado", transient_for=parent, modal=True)
    d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
    box = d.get_content_area()
    box.set_spacing(6)
    box.set_border_width(10)
    box.add(Gtk.Label(label="Este endereço já está na lista de downloads.", xalign=0))
    r1 = Gtk.RadioButton.new_with_label(None, "Adicionar o duplicado com nome numerado")
    r2 = Gtk.RadioButton.new_with_label_from_widget(r1, "Adicionar o duplicado e sobrescrever o arquivo existente")
    r3 = Gtk.RadioButton.new_with_label_from_widget(r1, "Se o arquivo estiver completo, mostrar; senão, retomar")
    remember = check("Lembrar a escolha e não perguntar de novo")
    for w in (r1, r2, r3, remember):
        box.add(w)
    d.show_all()
    ok = d.run() == Gtk.ResponseType.OK
    choice = "number" if r1.get_active() else "overwrite" if r2.get_active() else "resume"
    if ok and remember.get_active():
        settings["duplicate_action"] = choice
        settings.save()
    d.destroy()
    return choice if ok else None


# ---------------------------------------------------------------- Mapa de segmentos
class SegmentMap(Gtk.DrawingArea):
    """Barra com os trechos de cada conexão ('Start positions and download progress by connections')."""

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, 16)
        self.segs, self.total = [], 0
        self.connect("draw", self._draw)

    def update(self, segs, total):
        self.segs, self.total = segs, total
        self.queue_draw()

    def _draw(self, w, cr):
        a = w.get_allocation()
        theme.draw_segments(cr, 0, 0, a.width, a.height, self.segs, self.total)


# ---------------------------------------------------------------- Progresso
class ProgressWindow(Gtk.Window):
    def __init__(self, win, iid):
        super().__init__(title="Progresso do download", transient_for=None)
        self.w, self.m, self.iid = win, win.m, iid
        self.set_default_size(580, -1)
        try:
            self.set_icon_from_file(theme.LOGO)
        except GLib.Error:
            self.set_icon_name("folder-download")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        self.add(outer)
        self.head_name = Gtk.Label(xalign=0, ellipsize=3)
        self.head_name.get_style_context().add_class("ldm-title")
        self.head_status = theme.style(Gtk.Label(xalign=0), "ldm-subtitle")
        outer.pack_start(self.head_name, False, False, 0)
        outer.pack_start(self.head_status, False, False, 0)
        nb = Gtk.Notebook()
        outer.pack_start(nb, True, True, 0)

        g = grid()
        self.lbl = {}
        for r, (k, t) in enumerate([("url", "URL"), ("status", "Status"), ("size", "Tamanho"),
                                    ("done", "Baixado"), ("rate", "Velocidade"), ("eta", "Tempo restante"),
                                    ("resume", "Retomada")]):
            self.lbl[k] = row(g, r, t + ":", Gtk.Label(xalign=0, ellipsize=3, selectable=True))
            if k != "url":
                theme.style(self.lbl[k], "ldm-mono")
        self.bar = Gtk.ProgressBar(show_text=True)
        g.attach(self.bar, 0, 8, 2, 1)
        self.segmap = SegmentMap()
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.details.pack_start(theme.style(Gtk.Label(label="MAPA DO MOTOR MULTI-CONEXÃO", xalign=0), "ldm-stat-label", "ldm-mono"),
                                False, False, 0)
        self.details.pack_start(self.segmap, False, False, 0)
        self.conn_store = Gtk.ListStore(str, str, str)
        tv = Gtk.TreeView(model=self.conn_store)
        for i, t in enumerate(["N.", "Início do trecho", "Informação"]):
            tv.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        self.details.pack_start(scrolled(tv, 110), True, True, 0)
        g.attach(self.details, 0, 9, 2, 1)
        nb.append_page(g, Gtk.Label(label="Status do download"))

        it = self.m.items[iid]
        lim = grid()
        self.lim_on = check("Usar limitador de velocidade", it.get("speed_limit_on"))
        lim.attach(self.lim_on, 0, 0, 2, 1)
        self.lim_val = row(lim, 1, "Velocidade máxima (KB/s):", spin(it.get("speed_limit_kbps") or 512, 1, 10 ** 6, 16))
        apply_b = Gtk.Button(label="Aplicar")
        apply_b.connect("clicked", lambda _: self.m.set_item_limit(iid, self.lim_on.get_active(), int(self.lim_val.get_value())))
        lim.attach(apply_b, 1, 2, 1, 1)
        nb.append_page(lim, Gtk.Label(label="Limitador de velocidade"))

        done = grid()
        self.show_done = check("Mostrar diálogo de download concluído", not it.get("no_complete_dialog"))
        self.open_done = check("Abrir o arquivo ao concluir", it.get("open_when_done"))
        self.exit_done = check("Sair do LDM ao concluir", it.get("exit_when_done"))
        self.off_done = check("Desligar o computador ao concluir", it.get("shutdown_when_done"))
        for i, w in enumerate((self.show_done, self.open_done, self.exit_done, self.off_done)):
            done.attach(w, 0, i, 1, 1)
            w.connect("toggled", self._save_done_opts)
        nb.append_page(done, Gtk.Label(label="Opções ao concluir"))

        bb = Gtk.Box(spacing=6)
        self.hide_b = Gtk.Button(label="<< Ocultar detalhes")
        self.hide_b.connect("clicked", self._toggle_details)
        self.pause_b = theme.style(Gtk.Button(label="Pausar"), "ldm-ghost")
        self.pause_b.connect("clicked", self._pause_resume)
        cancel_b = theme.style(Gtk.Button(label="Cancelar"), "ldm-ghost")
        cancel_b.connect("clicked", lambda _: (self.m.pause(iid), self.destroy()))
        bb.pack_start(self.hide_b, False, False, 0)
        bb.pack_end(cancel_b, False, False, 0)
        bb.pack_end(self.pause_b, False, False, 0)
        outer.pack_start(bb, False, False, 0)
        self.timer = GLib.timeout_add(500, self.tick)
        self.connect("destroy", lambda *_: GLib.source_remove(self.timer))
        raise_popup(self)
        self.tick()

    def _save_done_opts(self, *_):
        self.m.update(self.iid, no_complete_dialog=not self.show_done.get_active(),
                      open_when_done=self.open_done.get_active(), exit_when_done=self.exit_done.get_active(),
                      shutdown_when_done=self.off_done.get_active())

    def _toggle_details(self, _):
        vis = not self.details.get_visible()
        self.details.set_visible(vis)
        self.hide_b.set_label("<< Ocultar detalhes" if vis else "Mostrar detalhes >>")
        self.resize(560, 1)

    def _pause_resume(self, _):
        it = self.m.items.get(self.iid)
        if not it:
            return
        if self.iid in self.m.active:
            self.m.pause(self.iid)
        else:
            self.m.start(self.iid)

    def tick(self):
        it = self.m.items.get(self.iid)
        if not it:
            self.destroy()
            return False
        rt = self.m.runtime.get(self.iid, {})
        size = it.get("size") or -1
        done = rt.get("downloaded", it.get("downloaded", 0)) if self.iid in self.m.active else it.get("downloaded", 0)
        self.set_title(f"{int(done * 100 / size) if size > 0 else 0}% {it['filename']}")
        self.head_name.set_text(it["filename"])
        conns = len(rt.get("connections", [])) if self.iid in self.m.active else 0
        self.head_status.set_text(self.w.status_text(it) + (f" · {conns} conexões simultâneas ativas" if conns > 1 else ""))
        self.lbl["url"].set_text(it["url"])
        self.lbl["status"].set_text(self.w.status_text(it))
        self.lbl["size"].set_text(fmt_size(size) or "(desconhecido)")
        self.lbl["done"].set_text(f"{fmt_size(done)}" + (f" ({done * 100 / size:.2f}%)" if size > 0 else ""))
        self.lbl["rate"].set_text(fmt_rate(rt.get("rate")) if self.iid in self.m.active else "")
        self.lbl["eta"].set_text(fmt_eta(rt.get("eta")) if self.iid in self.m.active else "")
        res = it.get("resumable")
        self.lbl["resume"].set_text("(desconhecido)" if res is None else "Sim" if res else "Não")
        if size > 0:
            self.bar.set_fraction(min(1, done / size))
            self.bar.set_text(f"{done * 100 / size:.1f}%")
        else:
            self.bar.pulse() if self.iid in self.m.active else None
        d = self.m.active.get(self.iid)
        if d:
            self.segmap.update(d.segment_map(), size if size > 0 else 0)
            self.conn_store.clear()
            for i, c in enumerate(rt.get("connections", []), 1):
                self.conn_store.append([str(i), fmt_size(c["seg"]) if isinstance(c["seg"], int) else str(c["seg"]),
                                        c["state"] + (f" ({c['err']})" if c.get("err") else "")])
        else:
            segs = [(a, p, b) for a, b, p in it.get("segments") or [] if b is not None]
            self.segmap.update(segs, size if size > 0 else 0)
            self.conn_store.clear()
        self.pause_b.set_label("Pausar" if it["status"] in (ST_CONNECTING, ST_DOWNLOADING) else "Retomar")
        if it["status"] == ST_COMPLETE:
            self.destroy()
            return False
        return True


# ---------------------------------------------------------------- Concluído
class CompleteDialog(Gtk.Dialog):
    def __init__(self, win, iid):
        super().__init__(title="Download concluído", transient_for=win)
        self.w, self.m, self.iid = win, win.m, iid
        it = self.m.items[iid]
        path = self.m.file_path(iid)
        g = grid()
        row(g, 0, "Endereço:", Gtk.Label(label=it["url"], xalign=0, ellipsize=3, selectable=True))
        row(g, 1, "Arquivo salvo como:", Gtk.Label(label=str(path), xalign=0, ellipsize=3, selectable=True))
        row(g, 2, "Tamanho:", Gtk.Label(label=fmt_size(it.get("size")), xalign=0))
        if it.get("scan_status"):
            row(g, 3, "Antivírus:", Gtk.Label(label=it["scan_status"], xalign=0))
        self.dont = check("Não mostrar este diálogo novamente")
        g.attach(self.dont, 0, 4, 2, 1)
        self.get_content_area().add(g)
        for label, fn in (("Abrir", self._open), ("Abrir com...", self._open_with), ("Abrir pasta", self._folder)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            self.get_action_area().pack_start(b, False, False, 0)
        self.add_button("Fechar", Gtk.ResponseType.CLOSE)
        self.connect("response", self._close)
        self.set_default_size(520, -1)
        raise_popup(self)

    def _close(self, *_):
        if self.dont.get_active():
            self.m.s["show_complete_dialog"] = False
            self.m.s.save()
        self.destroy()

    def _open(self, _):
        open_path(self.m.file_path(self.iid))
        self._close()

    def _open_with(self, _):
        d = Gtk.AppChooserDialog.new_for_content_type(self, Gtk.DialogFlags.MODAL,
                                                      Gtk.content_type_guess(str(self.m.file_path(self.iid)), None)[0])
        if d.run() == Gtk.ResponseType.OK:
            from gi.repository import Gio

            from ..hostenv import apply_to_launch_context
            app = d.get_app_info()
            if app:
                ctx = apply_to_launch_context(Gio.AppLaunchContext())
                app.launch([Gio.File.new_for_path(str(self.m.file_path(self.iid)))], ctx)
        d.destroy()
        self._close()

    def _folder(self, _):
        open_folder(self.m.file_path(self.iid))
        self._close()


open_path = sysint.open_path
open_folder = sysint.open_folder        # destaca o arquivo (Explorer /select, Dolphin/Nautilus)


# ---------------------------------------------------------------- Propriedades
class PropertiesDialog(Gtk.Dialog):
    def __init__(self, win, iid):
        super().__init__(title="Propriedades do arquivo", transient_for=win, modal=True)
        self.m, self.iid = win.m, iid
        it = self.m.items[iid]
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        self.set_default_size(620, -1)
        g = grid()
        row(g, 0, "Tipo:", Gtk.Label(label=it.get("content_type") or ext_of(it["filename"]).upper(), xalign=0))
        row(g, 1, "Status:", Gtk.Label(label=win.status_text(it), xalign=0))
        row(g, 2, "Tamanho:", Gtk.Label(label=fmt_size(it.get("size")) or "(desconhecido)", xalign=0))
        self.name = row(g, 3, "Nome do arquivo:", entry(it["filename"]))
        self.dir = row(g, 4, "Salvar em:", folder_entry(self, it["save_dir"]))
        self.url = row(g, 5, "Endereço:", entry(it["url"]))
        self.desc = row(g, 6, "Descrição:", entry(it.get("description", "")))
        self.ref = row(g, 7, "Página de origem (referer):", entry(it.get("referer", "")))
        self.user = row(g, 8, "Usuário:", entry(it.get("auth_user", "")))
        self.pwd = row(g, 9, "Senha:", entry(it.get("auth_pass", ""), visibility=False))
        lt = it.get("last_try")
        row(g, 10, "Última tentativa:", Gtk.Label(label=time.strftime("%d/%m/%Y %H:%M", time.localtime(lt)) if lt else "-", xalign=0))
        row(g, 11, "Resultado:", Gtk.Label(label=it.get("error") or win.status_text(it), xalign=0, wrap=True))
        editable = it["status"] not in (ST_CONNECTING, ST_DOWNLOADING)
        for w in (self.name, self.dir, self.url):
            w.set_sensitive(editable)
        self.get_content_area().add(g)
        self.show_all()

    def run_and_apply(self):
        if self.run() == Gtk.ResponseType.OK:
            it = self.m.items[self.iid]
            kw = dict(description=self.desc.get_text(), referer=self.ref.get_text(),
                      auth_user=self.user.get_text(), auth_pass=self.pwd.get_text())
            if it["status"] not in (ST_CONNECTING, ST_DOWNLOADING):
                new_name, new_dir = self.name.get_text().strip(), self.dir.entry.get_text().strip()
                if it["status"] == ST_COMPLETE and (new_name != it["filename"] or new_dir != it["save_dir"]):
                    src = self.m.file_path(self.iid)
                    dst = Path(new_dir) / new_name
                    if src.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(src, dst)
                kw.update(filename=new_name, save_dir=new_dir, url=self.url.get_text().strip(),
                          filename_locked=new_name != it["filename"] or it.get("filename_locked"))
            self.m.update(self.iid, **kw)
        self.destroy()


# ---------------------------------------------------------------- Lote
class BatchDialog(Gtk.Dialog):
    def __init__(self, win, pattern=""):
        super().__init__(title="Download em lote", transient_for=win, modal=True)
        self.w, self.m = win, win.m
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        self.set_default_size(620, -1)
        g = grid()
        g.attach(Gtk.Label(label="É possível adicionar um grupo de arquivos sequenciais como img001.jpg ... img100.jpg.\n"
                                 "Use o asterisco (*) no lugar da parte variável. Ex.: https://site.com/fotos/img*.jpg",
                           xalign=0, wrap=True), 0, 0, 2, 1)
        self.pattern = row(g, 1, "Endereço:", entry(pattern))
        self.kind = row(g, 2, "Substituir * por:", combo([("num", "Números"), ("let", "Letras")], "num"))
        self.a = row(g, 3, "De:", entry("1"))
        self.b = row(g, 4, "Até:", entry("10"))
        self.width = row(g, 5, "Tamanho do curinga (zeros à esquerda):", spin(0, 0, 10))
        self.prev = Gtk.Label(xalign=0, selectable=True)
        g.attach(self.prev, 0, 6, 2, 1)
        self.queue = row(g, 7, "Adicionar à fila:", combo(queue_options(self.m), "main"))
        self.start_q = check("Iniciar o processamento da fila agora")
        g.attach(self.start_q, 0, 8, 2, 1)
        for w in (self.pattern, self.a, self.b):
            w.connect("changed", self._preview)
        self.width.connect("value-changed", self._preview)
        self.kind.connect("changed", self._kind)
        self.get_content_area().add(g)
        self.show_all()
        self._preview()

    def _kind(self, c):
        if c.get_active_id() == "let":
            self.a.set_text("a")
            self.b.set_text("z")
        else:
            self.a.set_text("1")
            self.b.set_text("10")

    def _urls(self):
        return batch_urls(self.pattern.get_text().strip(), self.a.get_text().strip(), self.b.get_text().strip(),
                          int(self.width.get_value()))

    def _preview(self, *_):
        try:
            u = self._urls()
            self.prev.set_text(f"Primeiro: {u[0]}\nSegundo: {u[1] if len(u) > 1 else '-'}\nÚltimo: {u[-1]}\nTotal: {len(u)} arquivos")
        except Exception as e:  # noqa: BLE001
            self.prev.set_text(str(e))

    def run_and_apply(self):
        while self.run() == Gtk.ResponseType.OK:
            try:
                urls = self._urls()
            except Exception as e:  # noqa: BLE001
                message(self, str(e), Gtk.MessageType.ERROR)
                continue
            qid = self.queue.get_active_id()
            for u in urls:
                self.m.add(u, start=False, queue_id=qid, duplicate="number")
            if self.start_q.get_active():
                self.m.start_queue(qid)
            break
        self.destroy()


# ---------------------------------------------------------------- Todos os links
class LinksDialog(Gtk.Window):
    """'Download All Links with IDM': lista links de uma página, com filtro e seleção."""

    def __init__(self, win, links, page=""):
        super().__init__(title="Baixar todos os links com o LDM")
        self.w, self.m, self.page = win, win.m, page
        self.set_default_size(780, 480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        self.add(box)
        box.pack_start(Gtk.Label(label="Marque os links que deseja adicionar à lista do LDM.", xalign=0), False, False, 0)
        fl = Gtk.Box(spacing=6)
        self.filter = entry(placeholder="Filtrar por extensões (ex.: zip mp4 pdf) e Enter")
        self.filter.connect("activate", self._apply_filter)
        self.hide_html = check("Ocultar páginas HTML", True)
        self.hide_html.connect("toggled", self._apply_filter)
        self.desc = check("Usar texto do link como descrição", True)
        fl.pack_start(self.filter, True, True, 0)
        fl.pack_start(self.hide_html, False, False, 0)
        fl.pack_start(self.desc, False, False, 0)
        box.pack_start(fl, False, False, 0)
        self.tv, self.store = check_list(["Arquivo", "Tipo", "Descrição", "Endereço"])
        box.pack_start(scrolled(self.tv, 300), True, True, 0)
        self.links = []
        seen = set()
        for ln in links:
            u = ln["url"] if isinstance(ln, dict) else ln
            if u in seen:
                continue
            seen.add(u)
            self.links.append({"url": u, "text": (ln.get("text", "") if isinstance(ln, dict) else "")})
        bb = Gtk.Box(spacing=6)
        for label, val in (("Marcar todos", True), ("Desmarcar todos", False)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _, v=val: [r.__setitem__(0, v) for r in self.store])
            bb.pack_start(b, False, False, 0)
        self.queue = combo(queue_options(self.m), "main")
        bb.pack_start(Gtk.Label(label="Fila:"), False, False, 0)
        bb.pack_start(self.queue, False, False, 0)
        ok = Gtk.Button(label="Adicionar à fila")
        ok.connect("clicked", lambda _: self._add(False))
        now = Gtk.Button(label="Baixar agora")
        now.get_style_context().add_class("suggested-action")
        now.connect("clicked", lambda _: self._add(True))
        bb.pack_end(now, False, False, 0)
        bb.pack_end(ok, False, False, 0)
        box.pack_start(bb, False, False, 0)
        self._apply_filter()
        raise_popup(self)

    def _apply_filter(self, *_):
        pat = self.filter.get_text().strip()
        self.store.clear()
        for ln in self.links:
            name = ln["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            ext = ext_of(name)
            if self.hide_html.get_active() and ext in ("", "html", "htm", "php", "asp", "aspx"):
                continue
            if pat and not match_ext(name, pat):
                continue
            self.store.append([bool(pat), name, ext.upper(), ln["text"], ln["url"], ln])

    def _add(self, start_now):
        qid = self.queue.get_active_id()
        n = 0
        for r in self.store:
            if r[0]:
                ln = r[5]
                self.m.add(ln["url"], referer=self.page, description=ln["text"] if self.desc.get_active() else "",
                           start=False, queue_id=qid, duplicate="number")
                n += 1
        if n and start_now:
            self.m.start_queue(qid)
        self.destroy()


# ---------------------------------------------------------------- Prévia ZIP
def zip_preview_dialog(win, iid):
    m = win.m
    it = m.items[iid]
    dlg = Gtk.Dialog(title=f"Prévia ZIP - {it['filename']}", transient_for=win)
    dlg.add_button("Fechar", Gtk.ResponseType.CLOSE)
    dlg.set_default_size(620, 420)
    store = Gtk.ListStore(str, str, str)
    tv = Gtk.TreeView(model=store)
    for i, t in enumerate(["Arquivo", "Tamanho", "Compactado"]):
        c = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
        c.set_expand(i == 0)
        tv.append_column(c)
    status = Gtk.Label(label="Lendo o diretório central do ZIP remoto...", xalign=0)
    dlg.get_content_area().pack_start(status, False, False, 4)
    dlg.get_content_area().pack_start(scrolled(tv, 350), True, True, 0)
    dlg.connect("response", lambda d, _: d.destroy())
    dlg.show_all()

    def work():
        try:
            size = it.get("size") or -1
            if size <= 0:
                s = net.open_stream(it["url"], it, net.NetConfig(m.s), start=0, end=0)
                cr = s.headers.get("Content-Range", "")
                s.close()
                size = int(cr.rsplit("/", 1)[1])
            entries = net.zip_preview(it.get("final_url") or it["url"], it, net.NetConfig(m.s), size)
            GLib.idle_add(fill, entries)
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(status.set_text, f"Não foi possível ler o ZIP (o servidor precisa aceitar Range): {e}")

    def fill(entries):
        for name, sz, csz in entries:
            store.append([name, fmt_size(sz), fmt_size(csz)])
        status.set_text(f"{len(entries)} itens")

    threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------- Limitador de velocidade
def speed_limiter_dialog(win):
    m = win.m
    d = Gtk.Dialog(title="Configurações do limitador de velocidade", transient_for=win, modal=True)
    d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
    g = grid()
    val = row(g, 0, "Velocidade máxima de download (KB/s):", spin(m.s["speed_limit_kbps"], 1, 10 ** 7, 64))
    on_start = check("Sempre ligar o limitador ao iniciar o LDM", m.s["speed_limiter_on_startup"])
    g.attach(on_start, 0, 1, 2, 1)
    d.get_content_area().add(g)
    d.show_all()
    if d.run() == Gtk.ResponseType.OK:
        m.s["speed_limiter_on_startup"] = on_start.get_active()
        m.apply_speed_limit(m.s["speed_limiter_on"], int(val.get_value()))
    d.destroy()


def confirm_delete(win, n, has_complete, has_incomplete=False):
    if has_complete and has_incomplete:
        label = "Apagar também os arquivos do disco (concluídos e incompletos)"
    elif has_incomplete:
        label = "Apagar também o arquivo incompleto"
    else:
        label = "Apagar também os arquivos concluídos do disco"
    secondary = None
    if has_incomplete:
        secondary = ("Se não apagar, a parte já baixada é guardada na pasta de destino como \"nome.part\" "
                     "(pode estar incompleta e não abrir).")
    return confirm(win, f"Excluir {n} download(s) da lista do LDM?", secondary=secondary,
                   check_label=label, check_default=has_incomplete and not has_complete)
