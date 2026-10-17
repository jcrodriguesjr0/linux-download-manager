"""Janela principal do LDM (GTK3), na identidade "Fluxo Segmentado":
barra de título com as ações principais + menu, lateral de categorias/filas, lista com o mapa de conexões
ao vivo e rodapé com a velocidade global."""
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import APP_ID, APP_NAME, VERSION, sysint, util  # noqa: E402
from ..engine import ST_COMPLETE, ST_CONNECTING, ST_DOWNLOADING, ST_ERROR, ST_PAUSED, ST_QUEUED  # noqa: E402
from ..i18n import _, set_language  # noqa: E402
from ..manager import Manager  # noqa: E402
from ..server import Api  # noqa: E402
from . import dialogs as D  # noqa: E402
from . import theme  # noqa: E402
from . import video as V  # noqa: E402
from .live import SegmentCell, Sparkline  # noqa: E402
from .panels import GrabberWindow, OptionsDialog, SchedulerWindow  # noqa: E402
from .widgets import confirm, message  # noqa: E402

ICON = theme.LOGO
STATUS_TXT = {ST_QUEUED: "Na fila", ST_CONNECTING: "Conectando", ST_DOWNLOADING: "Baixando",
              ST_PAUSED: "Pausado", ST_COMPLETE: "Concluído", ST_ERROR: "Erro"}
# colunas da ListStore
(C_ID, C_ICON, C_NAME, C_SIZE, C_STATUS, C_ETA, C_RATE, C_LAST, C_DESC, C_SIZE_N, C_ADDED, C_PROG, C_LAST_N,
 C_RATE_N, C_ETA_N, C_MARKUP) = range(16)
N_COLS = 16
COLUMNS = [("name", "Arquivo / nome", C_NAME, C_NAME), ("size", "Tamanho", C_SIZE, C_SIZE_N),
           ("status", "Progresso", C_STATUS, C_PROG), ("time_left", "Tempo restante", C_ETA, C_ETA_N),
           ("rate", "Velocidade", C_RATE, C_RATE_N), ("last_try", "Última tentativa", C_LAST, C_LAST_N),
           ("description", "Descrição", C_DESC, C_DESC)]


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        self.m: Manager = app.m
        self.s = self.m.s
        self.rows: dict[str, Gtk.TreeIter] = {}
        self.progress_windows: dict[str, Gtk.Window] = {}
        self.filter_key = "all"
        self.search_text = ""
        self.last_clip = ""
        self.tree_rows: dict[str, Gtk.TreeIter] = {}
        set_language(self.s["language"])
        try:
            self.set_icon_from_file(ICON)
        except GLib.Error:
            self.set_icon_name("folder-download")
        wcfg = self.s["window"]
        self.set_default_size(wcfg.get("width", 1000), wcfg.get("height", 600))
        theme.style(self, "ldm")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        self.set_titlebar(self._build_header())
        self.searchbar = Gtk.SearchBar(show_close_button=True)
        self.search = Gtk.SearchEntry(placeholder_text=_("Pesquisar por nome, descrição ou endereço"), width_chars=40)
        self.search.connect("search-changed", self._on_search)
        self.searchbar.add(self.search)
        self.searchbar.connect_entry(self.search)
        vbox.pack_start(self.searchbar, False, False, 0)
        self.paned = Gtk.Paned()
        self.paned.set_position(max(250, wcfg.get("paned", 250)))
        vbox.pack_start(self.paned, True, True, 0)
        self.paned.pack1(self._build_tree(), False, False)
        self.paned.pack2(self._build_list(), True, False)
        vbox.pack_start(self._build_footer(), False, False, 0)
        self._spark_t = 0.0

        # Arrastar e soltar links (o "drop target" do IDM)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY | Gdk.DragAction.LINK)
        self.drag_dest_add_uri_targets()
        self.drag_dest_add_text_targets()
        self.connect("drag-data-received", self._on_drop)

        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard.connect("owner-change", self._on_clipboard)
        self.connect("delete-event", self._on_close)
        for it in self.m.items.values():
            self._append_row(it)
        self.apply_settings(initial=True)
        GLib.timeout_add(500, self._tick)

    # ------------------------------------------------------------------ construção
    def _mi(self, menu, label, cb=None, accel=None):
        item = Gtk.MenuItem.new_with_mnemonic(_(label))
        if cb:
            item.connect("activate", lambda *_: cb())
        if accel:
            key, mod = Gtk.accelerator_parse(accel)
            item.add_accelerator("activate", self.accel, key, mod, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        return item

    def _submenu(self, bar, label):
        top = Gtk.MenuItem.new_with_mnemonic(_(label))
        menu = Gtk.Menu()
        top.set_submenu(menu)
        bar.append(top)
        return menu

    def _build_menu(self):
        self.accel = Gtk.AccelGroup()
        self.add_accel_group(self.accel)
        bar = Gtk.Menu()                      # aberto pelo botão ⋮ da barra de título
        t = self._submenu(bar, "_Tarefas")
        self._mi(t, "Adicionar URL", self.add_url, "<Control>n")
        self._mi(t, "Baixar vídeo de uma página", lambda: V.ask_video_url(self), "<Control><Shift>v")
        self._mi(t, "Adicionar download em lote", self.batch)
        self._mi(t, "Adicionar lote a partir da área de transferência", self.batch_from_clipboard)
        self._mi(t, "Executar Site Grabber", self.grabber)
        t.append(Gtk.SeparatorMenuItem())
        exp = Gtk.Menu()
        e = self._mi(t, "Exportar")
        e.set_submenu(exp)
        self._mi(exp, "Para arquivo de exportação (.ef2)", lambda: self.export("ef2"))
        self._mi(exp, "Para arquivo de texto", lambda: self.export("txt"))
        imp = Gtk.Menu()
        i = self._mi(t, "Importar")
        i.set_submenu(imp)
        self._mi(imp, "De arquivo de exportação (.ef2)", lambda: self.import_("ef2"))
        self._mi(imp, "De arquivo de texto", lambda: self.import_("txt"))
        t.append(Gtk.SeparatorMenuItem())
        self._mi(t, "Sair", self.quit, "<Control>q")

        f = self._submenu(bar, "_Arquivo")
        self._mi(f, "Baixar agora", self.resume_sel)
        self._mi(f, "Parar download", self.stop_sel)
        self._mi(f, "Baixar novamente", self.redownload_sel)
        self._mi(f, "Remover", self.delete_sel, "Delete")
        self._mi(f, "Abrir", lambda: self.open_sel(False))
        self._mi(f, "Abrir pasta", lambda: self.open_sel(True))
        self._mi(f, "Propriedades", self.properties_sel)

        d = self._submenu(bar, "_Downloads")
        self._mi(d, "Pausar todos", self.m.pause_all)
        self._mi(d, "Retomar todos", self.m.start_all)
        self._mi(d, "Excluir concluídos", self.delete_completed)
        self._mi(d, "Pesquisar", self._toggle_search, "<Control>f")
        d.append(Gtk.SeparatorMenuItem())
        self._mi(d, "Agendador", self.scheduler)
        self._mi(d, "Iniciar fila", lambda: self.m.start_queue(self._current_queue()))
        self._mi(d, "Parar fila", lambda: self.m.stop_queue(self._current_queue()))
        d.append(Gtk.SeparatorMenuItem())
        self.limiter_item = Gtk.CheckMenuItem(label=_("Limitador de velocidade ligado"), active=self.s["speed_limiter_on"])
        self.limiter_item.connect("toggled", lambda w: self.set_limiter(w.get_active()))
        d.append(self.limiter_item)
        self._mi(d, "Configurar limitador...", lambda: D.speed_limiter_dialog(self))
        d.append(Gtk.SeparatorMenuItem())
        self._mi(d, "Opções", self.options)

        v = self._submenu(bar, "_Exibir")
        self.hide_cats = Gtk.CheckMenuItem(label="Ocultar categorias")
        self.hide_cats.connect("toggled", lambda w: self.tree_box.set_visible(not w.get_active()))
        v.append(self.hide_cats)
        self.dark_item = Gtk.CheckMenuItem(label=_("Modo escuro"), active=self.s["dark_mode"])
        self.dark_item.connect("toggled", self._toggle_dark)
        v.append(self.dark_item)
        cols = Gtk.Menu()
        c = self._mi(v, "Colunas")
        c.set_submenu(cols)
        self.col_items = {}
        for key, title, *_cols in COLUMNS:
            ci = Gtk.CheckMenuItem(label=_(title), active=key in self.s["columns_visible"])
            ci.connect("toggled", self._toggle_column, key)
            cols.append(ci)
        lang = Gtk.Menu()
        lg = self._mi(v, "Idioma")
        lg.set_submenu(lang)
        self._mi(lang, "Português (Brasil)", lambda: self._set_lang("pt"))
        self._mi(lang, "English", lambda: self._set_lang("en"))

        h = self._submenu(bar, "Aj_uda")
        self._mi(h, "Extensão do navegador...", self.browser_extension)
        from .. import autostart
        if autostart.can_install_menu():
            self._mi(h, "Adicionar ao menu de aplicativos", self.install_menu)
        h.append(Gtk.SeparatorMenuItem())
        self._mi(h, "Sobre o LDM", self.about)
        bar.show_all()
        return bar

    def _button(self, label, cb, css, icon=None, tip=None):
        b = Gtk.Button(label=_(label)) if label else Gtk.Button()
        if icon:
            b.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            b.set_always_show_image(True)
        b.set_tooltip_text(_(tip or label))
        b.connect("clicked", lambda *_: cb())
        theme.style(b, css)
        return b

    def _build_header(self):
        hb = Gtk.HeaderBar(show_close_button=True)
        hb.set_title("")
        hb.set_decoration_layout(":minimize,maximize,close")   # o logo já está na barra
        brand = Gtk.Box(spacing=8)
        try:
            from gi.repository import GdkPixbuf
            brand.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(ICON, 28, 28)), False, False, 0)
        except Exception:  # noqa: BLE001
            pass
        brand.pack_start(theme.style(Gtk.Label(label="LDM"), "ldm-title"), False, False, 0)
        brand.pack_start(theme.style(Gtk.Label(label=APP_NAME), "ldm-subtitle"), False, False, 0)
        hb.pack_start(brand)

        has = Gtk.IconTheme.get_default().has_icon
        self.menu_btn = Gtk.MenuButton(popup=self._build_menu(), tooltip_text=_("Menu"))
        if has("open-menu-symbolic"):
            self.menu_btn.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        else:
            self.menu_btn.set_label("⋮")
        theme.style(self.menu_btn, "ldm-ghost")
        hb.pack_end(self.menu_btn)
        self.search_btn = Gtk.ToggleButton(tooltip_text=_("Pesquisar (Ctrl+F)"))
        if has("system-search-symbolic"):
            self.search_btn.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        else:
            self.search_btn.set_label("🔍")
        self.search_btn.connect("toggled", lambda b: self.searchbar.set_search_mode(b.get_active()))
        theme.style(self.search_btn, "ldm-ghost")
        hb.pack_end(self.search_btn)
        self.limiter_btn = Gtk.ToggleButton(tooltip_text=_("Limitador de velocidade"), active=self.s["speed_limiter_on"])
        self.limiter_btn.set_image(Gtk.Image.new_from_icon_name(theme.icon("speedometer"), Gtk.IconSize.BUTTON))
        self.limiter_btn.connect("toggled", lambda b: self.set_limiter(b.get_active()))
        theme.style(self.limiter_btn, "ldm-ghost")
        hb.pack_end(self.limiter_btn)
        hb.pack_end(self._button("Pausar tudo", self.m.pause_all, "ldm-ghost", tip="Pausar todos os downloads"))
        hb.pack_end(self._button("★ Vídeo", lambda: V.ask_video_url(self), "ldm-video",
                                 tip="Baixar o vídeo de uma página (Ctrl+Shift+V)"))
        hb.pack_end(self._button("+ URL", self.add_url, "ldm-primary", tip="Adicionar URL (Ctrl+N)"))
        hb.show_all()
        return hb

    def _toggle_search(self):
        self.search_btn.set_active(not self.search_btn.get_active())
        if self.search_btn.get_active():
            self.search.grab_focus()

    def _build_footer(self):
        box = theme.style(Gtk.Box(spacing=22), "ldm-footer")
        self.spark = Sparkline()
        box.pack_start(self.spark, True, True, 0)

        def stat(title, css):
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
            v.pack_start(theme.style(Gtk.Label(label=_(title).upper(), xalign=0), "ldm-stat-label", "ldm-mono"), False, False, 0)
            val = theme.style(Gtk.Label(xalign=0), css, "ldm-mono")
            v.pack_start(val, False, False, 0)
            box.pack_start(v, False, False, 0)
            return val

        self.stat_speed = stat("Velocidade global", "ldm-stat-speed")
        self.stat_conns = stat("Conexões totais", "ldm-stat-value")
        self.stat_count = stat("Downloads ativos", "ldm-stat-value")
        return box

    def _build_tree(self):
        self.tstore = Gtk.TreeStore(str, str, str, str)   # chave, rótulo, ícone, contador
        self.ttv = Gtk.TreeView(model=self.tstore, headers_visible=False, activate_on_single_click=True)
        col = Gtk.TreeViewColumn()
        ri = Gtk.CellRendererPixbuf(xpad=4)
        rt = Gtk.CellRendererText(ypad=5, ellipsize=3)
        rc = Gtk.CellRendererText(xalign=1, xpad=8, font=theme.MONO_FONT.split(",")[0] + " 9")
        col.set_expand(True)
        col.pack_start(ri, False)
        col.pack_start(rt, True)
        col.pack_start(rc, False)
        col.add_attribute(ri, "icon-name", 2)
        col.add_attribute(rt, "text", 1)
        col.add_attribute(rc, "text", 3)
        col.set_cell_data_func(rt, self._tree_cell_color)
        col.set_cell_data_func(rc, self._tree_count_color)
        self.ttv.append_column(col)
        self._tree_sel_handler = self.ttv.get_selection().connect("changed", self._on_tree_sel)
        self.refresh_tree()
        self.tree_sw = Gtk.ScrolledWindow(min_content_width=240, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.tree_sw.add(self.ttv)
        self.tree_box = theme.style(Gtk.Box(), "ldm-sidebar")
        self.tree_box.pack_start(self.tree_sw, True, True, 0)
        return self.tree_box

    @staticmethod
    def _tree_cell_color(_col, cell, model, it, _data):
        cell.set_property("foreground", theme.VIDEO if model[it][0] == "videos" else None)

    @staticmethod
    def _tree_count_color(_col, cell, model, it, _data):
        key = model[it][0]
        color = {"videos": theme.VIDEO, "finished": theme.SUCCESS, "unfinished": theme.PRIMARY}.get(key, theme.tokens()["muted"])
        cell.set_property("foreground", color)

    def refresh_tree(self):
        sel = self.ttv.get_selection()
        sel.handler_block(self._tree_sel_handler)     # reconstruir não pode mudar o filtro nem abrir o Grabber
        try:
            self._fill_tree()
        finally:
            sel.handler_unblock(self._tree_sel_handler)

    def _fill_tree(self):
        self.tstore.clear()
        self.tree_rows = {}
        cats = [c["name"] for c in self.s["categories"]]
        for key, label, icon in (("all", "Todos os downloads", "folder"), ("unfinished", "Em andamento", "folder-download"),
                                 ("finished", "Concluídos", "folder-documents")):
            parent = self.tree_rows[key] = self.tstore.append(None, [key, _(label), theme.icon(icon), ""])
            for c in cats:
                self.tstore.append(parent, [f"{key}:{c}", _(c), theme.icon("folder"), ""])
            self.tstore.append(parent, [f"{key}:Geral", _("Geral"), theme.icon("folder"), ""])
        self.tree_rows["videos"] = self.tstore.append(None, ["videos", _("Vídeos capturados"), theme.icon("video-x-generic"), ""])
        qp = self.tree_rows["queues"] = self.tstore.append(None, ["queues", _("Filas"), theme.icon("view-list-symbolic"), ""])
        for q in self.m.queues.values():
            self.tstore.append(qp, [f"queue:{q['id']}", q["name"] + ("  ▶" if q["running"] else ""), theme.icon("view-list"), ""])
        self.tstore.append(None, ["grabber", _("Projetos do Grabber"), theme.icon("network-server"), ""])
        self.ttv.expand_row(Gtk.TreePath(4), False)
        self._update_counts()
        self._select_tree_key(self.filter_key)

    def _select_tree_key(self, key):
        def visit(model, path, it):
            if model[it][0] == key:
                if path.get_depth() > 1:
                    parent = path.copy()
                    parent.up()
                    self.ttv.expand_to_path(parent)
                self.ttv.get_selection().select_iter(it)
                return True
            return False
        self.tstore.foreach(visit)

    def _update_counts(self):
        items = list(self.m.items.values())
        counts = {"all": len(items), "unfinished": sum(1 for i in items if i["status"] != ST_COMPLETE),
                  "finished": sum(1 for i in items if i["status"] == ST_COMPLETE),
                  "videos": sum(1 for i in items if i.get("kind") in ("video", "hls")),
                  "queues": sum(len(q["items"]) for q in self.m.queues.values())}
        for key, n in counts.items():
            row = self.tree_rows.get(key)
            if row is not None and self.tstore.get_value(row, 3) != str(n):
                self.tstore.set_value(row, 3, str(n))

    def _build_list(self):
        self.store = Gtk.ListStore(str, str, str, str, str, str, str, str, str, float, float, int, float, float, float, str)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self._visible)
        self.sorted = Gtk.TreeModelSort(model=self.filtered)
        self.tv = Gtk.TreeView(model=self.sorted)
        self.tv.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tv.set_rubber_banding(True)
        self.tv.connect("row-activated", self._on_activate)
        self.tv.connect("button-press-event", self._on_button)
        self.columns = {}
        mono = theme.MONO_FONT.split(",")[0] + " 9.5"
        for key, title, text_col, sort_col in COLUMNS:
            if key == "status":
                r = SegmentCell(self.segment_info)
                c = Gtk.TreeViewColumn(_(title).upper(), r)
                c.add_attribute(r, "iid", C_ID)
                c.set_min_width(200)
                c.set_expand(True)
            elif key == "name":
                c = Gtk.TreeViewColumn(_(title).upper())
                ri, rt = Gtk.CellRendererPixbuf(xpad=6), Gtk.CellRendererText(ellipsize=3, ypad=6)
                ri.set_property("stock-size", Gtk.IconSize.LARGE_TOOLBAR)
                c.pack_start(ri, False)
                c.pack_start(rt, True)
                c.add_attribute(ri, "icon-name", C_ICON)
                c.add_attribute(rt, "markup", C_MARKUP)
                c.set_expand(True)
                c.set_min_width(260)
            else:
                r = Gtk.CellRendererText(ellipsize=3, font=mono, xpad=6)
                c = Gtk.TreeViewColumn(_(title).upper(), r, text=text_col)
                c.set_cell_data_func(r, self._rate_color if key == "rate" else self._muted_color if key == "last_try" else None)
                if key == "size":
                    c.set_min_width(175)
            c.set_resizable(True)
            c.set_sort_column_id(sort_col)
            c.set_visible(key in self.s["columns_visible"])
            self.columns[key] = c
            self.tv.append_column(c)
        self.sorted.set_sort_column_id(C_ADDED, Gtk.SortType.ASCENDING)
        sw = Gtk.ScrolledWindow()
        sw.add(self.tv)
        return theme.style(sw, "ldm-list")

    @staticmethod
    def _muted_color(_col, cell, _model, _tit, _data):
        cell.set_property("foreground", theme.tokens()["muted"])

    def _rate_color(self, _col, cell, model, tit, _data):
        it = self.m.items.get(model[tit][C_ID], {})
        cell.set_property("foreground", theme.VIDEO if it.get("kind") in ("video", "hls") else theme.PRIMARY)

    def segment_info(self, iid):
        """Dados da linha viva: (segmentos, total, cor, completo, rótulo, percentual)."""
        it = self.m.items.get(iid)
        if not it:
            return None
        size = it.get("size") or -1
        video = it.get("kind") in ("video", "hls")
        color = theme.VIDEO if video else theme.PRIMARY
        st = it["status"]
        if st == ST_COMPLETE:
            return [], size, theme.SUCCESS, True, _("Concluído"), "100%"
        d = self.m.active.get(iid)
        try:
            segs = d.segment_map() if d else [(a, p, b) for a, b, p in it.get("segments") or [] if b is not None]
        except Exception:  # noqa: BLE001
            segs = []
        done = self.m.runtime.get(iid, {}).get("downloaded", it.get("downloaded", 0)) if d else it.get("downloaded", 0)
        if not segs and size > 0 and done:
            segs = [(0, min(done, size), size - 1)]
        pct = f"{done * 100 / size:.1f}%" if size > 0 else ""
        if st == ST_ERROR:
            return segs, size, theme.ERROR, False, self.status_text(it)[:70], pct
        if d:
            conns = len(self.m.runtime.get(iid, {}).get("connections", []))
            label = _("Conectando...") if st == ST_CONNECTING else (f"{conns} " + _("conexões ativas") if conns > 1 else _("Baixando"))
        else:
            label = STATUS_TXT.get(st, st)
        return segs, size, color, False, label, pct

    # ------------------------------------------------------------------ linhas
    @staticmethod
    def status_text(it):
        st = it["status"]
        if st == ST_ERROR:
            return "Erro: " + (it.get("error") or "")[:60]
        return STATUS_TXT.get(st, st)

    @staticmethod
    def _icon_for(name):
        ctype, _u = Gio.content_type_guess(name, None)
        return Gio.content_type_get_generic_icon_name(ctype) or "text-x-generic"

    def _row_values(self, it):
        iid = it["id"]
        active = iid in self.m.active
        rt = self.m.runtime.get(iid, {}) if active else {}
        size = it.get("size") or -1
        done = rt.get("downloaded", it.get("downloaded", 0))
        if it["status"] == ST_COMPLETE:
            prog, status = 100, "Concluído"
        elif size > 0:
            prog = int(min(100, done * 100 / size))
            status = f"{done * 100 / size:.2f}%" if active else f"{self.status_text(it)} ({done * 100 / size:.1f}%)"
        else:
            prog, status = 0, (util.fmt_size(done) if active and done else self.status_text(it))
        if active and it["status"] == ST_CONNECTING:
            status = "Conectando..."
        lt = it.get("last_try") or it.get("completed_at") or 0
        eta = rt.get("eta")
        size_txt = util.fmt_size(size)
        if active and size > 0:
            size_txt = f"{util.fmt_size(done)} / {size_txt}"
        return {C_ICON: self._icon_for(it["filename"]), C_NAME: it["filename"], C_SIZE: size_txt,
                C_STATUS: status, C_ETA: util.fmt_eta(eta) if active else "",
                C_RATE: util.fmt_rate(rt.get("rate")) if active else "",
                C_LAST: time.strftime("%d/%m/%Y %H:%M", time.localtime(lt)) if lt else "",
                C_DESC: it.get("description", ""), C_SIZE_N: float(size), C_ADDED: float(it.get("added", 0)),
                C_PROG: prog, C_LAST_N: float(lt), C_RATE_N: float(rt.get("rate") or 0),
                C_ETA_N: float(eta if eta is not None else 1e12), C_MARKUP: self._name_markup(it, rt)}

    def _name_markup(self, it, rt):
        esc = GLib.markup_escape_text
        host = urlparse(it.get("url", "")).hostname or ""
        parts = [host.removeprefix("www.")] if host else []
        video = it.get("kind") in ("video", "hls")
        if video:
            parts.append(_("Vídeo") + (f" · {it['video'].get('quality')}" if isinstance(it.get("video"), dict) and it["video"].get("quality") else ""))
        conns = len(rt.get("connections", [])) if rt else 0
        if conns > 1:
            parts.append(f"{conns} " + _("conexões ativas"))
        if it.get("description") and not video:
            parts.append(it["description"][:60])
        color = theme.SUCCESS if it["status"] == ST_COMPLETE else (theme.VIDEO if video else theme.tokens()["muted"])
        dot = f'<span foreground="{theme.VIDEO}">●</span> ' if video else ""
        return (f"{dot}<b>{esc(it['filename'])}</b>\n"
                f'<span size="small" foreground="{color}">{esc(" • ".join(parts))}</span>')

    def _append_row(self, it):
        vals = self._row_values(it)
        row = [it["id"]] + [vals[i] for i in range(1, N_COLS)]
        self.rows[it["id"]] = self.store.append(row)

    def _update_row(self, iid):
        it = self.m.items.get(iid)
        tit = self.rows.get(iid)
        if not it or tit is None:
            return
        vals = self._row_values(it)
        cols, values = [], []
        for k, v in vals.items():
            if self.store.get_value(tit, k) != v:
                cols.append(k)
                values.append(v)
        if cols:
            self.store.set(tit, cols, values)

    def _remove_row(self, iid):
        tit = self.rows.pop(iid, None)
        if tit is not None:
            self.store.remove(tit)

    def _visible(self, model, tit, _data):
        iid = model[tit][C_ID]
        it = self.m.items.get(iid)
        if not it:
            return False
        if self.search_text:
            hay = " ".join((it["filename"], it.get("description", ""), it["url"], it.get("referer", ""))).lower()
            if self.search_text not in hay:
                return False
        key = self.filter_key
        if key.startswith("queue:"):
            q = self.m.queues.get(key[6:])
            return bool(q) and iid in q["items"]
        if key == "videos":
            return it.get("kind") in ("video", "hls")
        if key in ("queues", "grabber"):
            return key == "grabber" and bool(it.get("grabber"))
        base, _sep, cat = key.partition(":")
        if base == "unfinished" and it["status"] == ST_COMPLETE:
            return False
        if base == "finished" and it["status"] != ST_COMPLETE:
            return False
        return not cat or it.get("category", "Geral") == cat

    # ------------------------------------------------------------------ ciclo
    def _tick(self):
        while not self.m.events.empty():
            ev, arg = self.m.events.get_nowait()
            if ev == "added" and arg in self.m.items and arg not in self.rows:
                self._append_row(self.m.items[arg])
            elif ev == "removed":
                self._remove_row(arg)
            elif ev == "completed":
                self._on_completed(arg)
            elif ev == "failed":
                it = self.m.items.get(arg)
                if it:
                    self.notify("Falha no download", f"{it['filename']}: {it.get('error', '')}")
            elif ev == "queue_done":
                self._on_queue_done(arg)
                self.refresh_tree()
            elif ev == "queue":
                self.refresh_tree()
            elif ev == "duplicate":
                it = self.m.items.get(arg)
                if it and it["status"] == ST_COMPLETE:
                    D.CompleteDialog(self, arg)
            if arg in self.rows:
                self._update_row(arg)
        for iid in list(self.m.active):
            self._update_row(iid)
        self.filtered.refilter() if self.search_text or self.filter_key != "all" else None
        total_rate = sum(r.get("rate", 0) for i, r in self.m.runtime.items() if i in self.m.active)
        conns = sum(len(r.get("connections", [])) for i, r in self.m.runtime.items() if i in self.m.active)
        lim = f"  (≤ {self.s['speed_limit_kbps']} KB/s)" if self.s["speed_limiter_on"] else ""
        self.stat_speed.set_text((util.fmt_rate(total_rate) or "0 B/s") + lim)
        self.stat_conns.set_text(f"{conns} " + _("conexões"))
        self.stat_count.set_text(f"{len(self.m.active)} " + _("de") + f" {len(self.m.items)}")
        now = time.monotonic()
        if now - self._spark_t >= 1:
            self._spark_t = now
            self.spark.push(total_rate)
            self._update_counts()
        self.tv.queue_draw()
        if self.app.tray:
            self.app.tray.set_tooltip_text(f"{APP_NAME}\n{len(self.m.active)} ativos · {util.fmt_rate(total_rate) or '0 B/s'}")
        return True

    def _on_completed(self, iid):
        it = self.m.items.get(iid)
        if not it:
            return
        self._update_row(iid)
        self.notify("Download concluído", it["filename"])
        if it.get("open_when_done"):
            D.open_path(self.m.file_path(iid))
        if it.get("shutdown_when_done"):
            self.shutdown_countdown()
        elif it.get("exit_when_done"):
            self.quit()
        elif self.s["show_complete_dialog"] and not it.get("no_complete_dialog") and not self.m.queue_of(iid):
            D.CompleteDialog(self, iid)

    def _on_queue_done(self, qid):
        q = self.m.queues.get(qid)
        if not q:
            return
        self.notify("Fila concluída", f"A fila '{q['name']}' terminou.")
        act = q.get("on_done", "none")
        if act == "exit":
            self.quit()
        elif act == "shutdown":
            self.shutdown_countdown()
        elif act == "open" and q.get("open_file"):
            D.open_path(q["open_file"])

    def shutdown_countdown(self, secs=30):
        d = Gtk.MessageDialog(transient_for=self, modal=False, message_type=Gtk.MessageType.WARNING,
                              buttons=Gtk.ButtonsType.NONE, text="Desligando o computador")
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Desligar agora", Gtk.ResponseType.OK)
        left = [secs]

        def tick():
            if left[0] <= 0:
                d.destroy()
                self.m.shutdown()
                self.m.power_off()
                return False
            d.format_secondary_text(f"O LDM concluiu os downloads. O computador será desligado em {left[0]} s.")
            left[0] -= 1
            return True

        src = GLib.timeout_add(1000, tick)

        def resp(_d, r):
            GLib.source_remove(src)
            d.destroy()
            if r == Gtk.ResponseType.OK:
                self.m.shutdown()
                self.m.power_off()

        d.connect("response", resp)
        tick()
        d.show_all()

    def notify(self, title, body):
        sysint.notify(APP_NAME, ICON, title, body)

    # ------------------------------------------------------------------ seleção
    def selected_ids(self):
        model, paths = self.tv.get_selection().get_selected_rows()
        return [model[p][C_ID] for p in paths]

    def _current_queue(self):
        return self.filter_key[6:] if self.filter_key.startswith("queue:") else "main"

    def _on_tree_sel(self, sel):
        model, it = sel.get_selected()
        if it:
            self.filter_key = model[it][0]
            self.filtered.refilter()
            if self.filter_key == "grabber":
                self.grabber()

    def _on_search(self, e):
        self.search_text = e.get_text().strip().lower()
        self.filtered.refilter()

    def _on_activate(self, tv, path, _col):
        iid = self.sorted[path][C_ID]
        it = self.m.items.get(iid)
        if not it:
            return
        if it["status"] == ST_COMPLETE:
            D.CompleteDialog(self, iid)
        else:
            self.open_progress(iid)

    def _on_button(self, tv, ev):
        if ev.button != 3:
            return False
        pth = tv.get_path_at_pos(int(ev.x), int(ev.y))
        if pth and not tv.get_selection().path_is_selected(pth[0]):
            tv.get_selection().unselect_all()
            tv.get_selection().select_path(pth[0])
        ids = self.selected_ids()
        if not ids:
            return True
        menu = Gtk.Menu()
        one = len(ids) == 1
        it = self.m.items.get(ids[0], {})
        if one and it.get("status") == ST_COMPLETE:
            self._mi(menu, "Abrir", lambda: self.open_sel(False))
            self._mi(menu, "Abrir com...", lambda: D.CompleteDialog(self, ids[0])._open_with(None))
        self._mi(menu, "Abrir pasta", lambda: self.open_sel(True))
        menu.append(Gtk.SeparatorMenuItem())
        self._mi(menu, "Baixar agora / Retomar", self.resume_sel)
        self._mi(menu, "Parar download", self.stop_sel)
        self._mi(menu, "Baixar novamente", self.redownload_sel)
        self._mi(menu, "Remover", self.delete_sel)
        qm = Gtk.Menu()
        qi = self._mi(menu, "Mover para a fila")
        qi.set_submenu(qm)
        for q in self.m.queues.values():
            self._mi(qm, q["name"], lambda qid=q["id"]: [self.m.add_to_queue(i, qid) for i in ids])
        self._mi(menu, "Remover da fila", lambda: [self.m.remove_from_queue(i) for i in ids])
        menu.append(Gtk.SeparatorMenuItem())
        if one and util.ext_of(it.get("filename", "")) == "zip":
            self._mi(menu, "Prévia ZIP", lambda: D.zip_preview_dialog(self, ids[0]))
        if one:
            self._mi(menu, "Mostrar progresso", lambda: self.open_progress(ids[0]))
        self._mi(menu, "Copiar endereço", lambda: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(
            "\n".join(self.m.items[i]["url"] for i in ids if i in self.m.items), -1))
        if one:
            self._mi(menu, "Propriedades", self.properties_sel)
        menu.show_all()
        menu.popup_at_pointer(ev)
        return True

    # ------------------------------------------------------------------ ações
    def add_url(self, clip=None):
        if clip is None:
            clip = self.clipboard.wait_for_text() or ""
        res = D.AddUrlDialog(self, clip).get()
        if res:
            self.handle_add(res)

    def handle_add(self, payload):
        """Ponto único para novos downloads (UI, área de transferência, navegador, CLI)."""
        if self.s["show_file_info_dialog"]:
            dlg = D.FileInfoDialog(self, payload)
            dlg.present()
        else:
            it = self.m.add(payload["url"], filename=payload.get("filename") or None,
                            referer=payload.get("referer", ""), cookies=payload.get("cookies", ""),
                            user_agent=payload.get("user_agent", ""), kind=payload.get("kind"),
                            headers=payload.get("headers"), auth_user=payload.get("auth_user", ""),
                            auth_pass=payload.get("auth_pass", ""), duplicate=self.ask_duplicate(payload["url"]))
            if self.s["show_progress_dialog"]:
                self.open_progress(it["id"])

    def ask_duplicate(self, url):
        if self.m.find_by_url(url) and self.s["duplicate_action"] == "ask":
            return D.ask_duplicate(self, self.s) or "resume"
        return None

    def open_progress(self, iid):
        w = self.progress_windows.get(iid)
        if w and w.get_visible():
            w.present()
            return
        w = D.ProgressWindow(self, iid)
        w.connect("destroy", lambda *_: self.progress_windows.pop(iid, None))
        self.progress_windows[iid] = w

    def resume_sel(self):
        for i in self.selected_ids():
            self.m.start(i)

    def stop_sel(self):
        for i in self.selected_ids():
            self.m.pause(i)

    def redownload_sel(self):
        ids = self.selected_ids()
        if ids and confirm(self, "Baixar novamente os arquivos selecionados do zero?")[0]:
            for i in ids:
                self.m.redownload(i)

    def delete_sel(self):
        ids = self.selected_ids()
        if not ids:
            return
        has_c = any(self.m.items[i]["status"] == ST_COMPLETE for i in ids if i in self.m.items)
        ok, del_files = D.confirm_delete(self, len(ids), has_c)
        if ok:
            for i in ids:
                self.m.remove(i, delete_file=del_files)

    def delete_completed(self):
        n = sum(1 for it in self.m.items.values() if it["status"] == ST_COMPLETE)
        if n and confirm(self, f"Remover {n} download(s) concluído(s) da lista? (os arquivos ficam no disco)")[0]:
            self.m.delete_completed()

    def open_sel(self, folder):
        ids = self.selected_ids()
        if ids:
            p = self.m.file_path(ids[0])
            D.open_folder(p) if folder else D.open_path(p)

    def properties_sel(self):
        ids = self.selected_ids()
        if ids:
            D.PropertiesDialog(self, ids[0]).run_and_apply()
            self._update_row(ids[0])

    def batch(self, pattern=""):
        D.BatchDialog(self, pattern).run_and_apply()

    def batch_from_clipboard(self):
        txt = self.clipboard.wait_for_text() or ""
        urls = util.URL_RE.findall(txt)
        if not urls:
            message(self, "Nenhum endereço encontrado na área de transferência.")
        elif len(urls) == 1 and "*" in urls[0]:
            self.batch(urls[0])
        else:
            D.LinksDialog(self, [{"url": u, "text": ""} for u in urls])

    def grabber(self, url=""):
        GrabberWindow(self, url)

    def scheduler(self):
        SchedulerWindow(self)

    def options(self):
        OptionsDialog(self).run_and_apply()

    def set_limiter(self, on):
        self.m.apply_speed_limit(on)
        for w in (self.limiter_btn, self.limiter_item):
            if w.get_active() != on:
                w.set_active(on)

    def export(self, fmt):
        ids = self.selected_ids() or list(self.m.items)
        d = Gtk.FileChooserDialog(title="Exportar lista", transient_for=self, action=Gtk.FileChooserAction.SAVE)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Salvar", Gtk.ResponseType.OK)
        d.set_current_name(f"ldm_lista.{fmt}")
        d.set_do_overwrite_confirmation(True)
        if d.run() == Gtk.ResponseType.OK:
            items = [self.m.items[i] for i in ids if i in self.m.items]
            (util.export_ef2 if fmt == "ef2" else util.export_txt)(items, d.get_filename())
        d.destroy()

    def import_(self, fmt):
        d = Gtk.FileChooserDialog(title="Importar lista", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Abrir", Gtk.ResponseType.OK)
        flt = Gtk.FileFilter()
        flt.set_name("Exportação IDM/LDM (*.ef2, *.ief)" if fmt == "ef2" else "Texto (*.txt)")
        for pat in (("*.ef2", "*.ief") if fmt == "ef2" else ("*.txt",)):
            flt.add_pattern(pat)
        d.add_filter(flt)
        if d.run() == Gtk.ResponseType.OK:
            entries = (util.import_ef2 if fmt == "ef2" else util.import_txt)(d.get_filename())
            d.destroy()
            if entries:
                D.LinksDialog(self, [{"url": e["url"], "text": "", **e} for e in entries])
            return
        d.destroy()

    def install_menu(self):
        from .. import autostart
        path = autostart.install_menu_entry()
        message(self, "Atalho criado no menu de aplicativos.", secondary=str(path))

    def browser_extension(self):
        from .. import autostart
        ext = autostart.extension_dir()
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.NONE, text="Extensão do navegador")
        d.format_secondary_markup(
            "1. Abra <b>chrome://extensions</b> (Chrome, Edge, Chromium, Brave).\n"
            "2. Ligue o <b>Modo do desenvolvedor</b>.\n"
            "3. Clique em <b>Carregar sem compactação</b> e escolha a pasta:\n"
            f"<tt>{GLib.markup_escape_text(str(ext))}</tt>\n\n"
            "Firefox: about:debugging → Este Firefox → Carregar extensão temporária → manifest.json.\n"
            "Edge: em edge://extensions o botão fica na barra lateral, “Modo de desenvolvedor”.")
        d.add_buttons("Abrir pasta", 1, "Abrir no Chrome", 2, "Abrir no Edge", 3, "Fechar", Gtk.ResponseType.CLOSE)
        while True:
            r = d.run()
            if r == 1:
                D.open_path(ext)
            elif r in (2, 3):
                self._open_browser_extensions("com.google.Chrome" if r == 2 else "com.microsoft.Edge",
                                              "google-chrome" if r == 2 else "microsoft-edge")
            else:
                break
        d.destroy()

    @staticmethod
    def _open_browser_extensions(flatpak_id, binary):
        url = "chrome://extensions"
        if sysint.IS_WIN:   # "start" acha o navegador pelo registro (App Paths)
            edge = binary == "microsoft-edge"
            subprocess.Popen(["cmd", "/c", "start", "", "msedge" if edge else "chrome", "edge://extensions" if edge else url])
            return
        if shutil.which(binary):
            subprocess.Popen([binary, url])
        elif shutil.which("flatpak"):
            subprocess.Popen(["flatpak", "run", flatpak_id, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def about(self):
        a = Gtk.AboutDialog(transient_for=self, modal=True, program_name=APP_NAME, version=VERSION,
                            comments="Clone para Linux das funções do Internet Download Manager 6.43:\n"
                                     "downloads multi-conexão com segmentação dinâmica, filas, agendador,\n"
                                     "limitador de velocidade, Site Grabber, captura do navegador e HLS.",
                            license_type=Gtk.License.MIT_X11, website="https://github.com/jcrodriguesjr0/linux-download-manager")
        try:
            from gi.repository import GdkPixbuf
            a.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(ICON, 112, 112))
        except Exception:  # noqa: BLE001
            pass
        a.run()
        a.destroy()

    # ------------------------------------------------------------------ eventos diversos
    def _on_drop(self, _w, _ctx, _x, _y, data, _info, _time):
        uris = data.get_uris() or []
        text = data.get_text() or ""
        urls = [u for u in uris if u.startswith(("http", "ftp"))] or util.URL_RE.findall(text)
        for u in urls[:1]:
            self.handle_add({"url": u})
        if len(urls) > 1:
            D.LinksDialog(self, [{"url": u, "text": ""} for u in urls])

    def _on_clipboard(self, cb, _ev):
        if not self.s["monitor_clipboard"]:
            return
        cb.request_text(self._clip_text)

    def _clip_text(self, _cb, text):
        text = (text or "").strip()
        if not text or text == self.last_clip or not util.looks_like_url(text):
            return
        self.last_clip = text
        if V.is_video_page(text):
            V.VideoDialog(self, {"page_url": text})
            return
        name = text.split("?")[0].rsplit("/", 1)[-1]
        if util.match_ext(name, self.s["capture_exts"]) or ".m3u8" in text:
            self.handle_add({"url": text})

    def _toggle_dark(self, w):
        self.s["dark_mode"] = w.get_active()
        self.s.save()
        self.apply_settings()

    def _toggle_column(self, w, key):
        vis = [k for k in self.s["columns_visible"] if k != key] + ([key] if w.get_active() else [])
        self.s["columns_visible"] = vis
        self.columns[key].set_visible(w.get_active())
        self.s.save()

    def _set_lang(self, lang):
        self.s["language"] = lang
        self.s.save()
        message(self, "Idioma alterado. Reinicie o LDM para aplicar em toda a interface.")

    def apply_settings(self, initial=False):
        theme.apply(self.s["dark_mode"])
        self.app.update_tray()
        self.refresh_tree()
        for it in self.m.items.values():      # cores do subtítulo dependem do tema
            self._update_row(it["id"])
        if not initial:
            self.m.apply_speed_limit(self.s["speed_limiter_on"])

    def _on_close(self, *_):
        a = self.get_allocation()
        self.s["window"] = {"width": a.width, "height": a.height, "paned": self.paned.get_position()}
        self.s.save()
        if self.app.tray and self.s["tray_icon"]:
            self.hide()
            return True
        self.quit()
        return True

    def quit(self):
        self.app.quit_all()

    # chamados pela API (threads do servidor) -> sempre via idle_add
    def on_add(self, payload):
        GLib.idle_add(lambda: (self.handle_add(payload), False)[1])

    def on_started(self, iid):
        if self.s["show_progress_dialog"]:
            GLib.idle_add(lambda: (self.open_progress(iid), False)[1])

    def on_video(self, payload):
        GLib.idle_add(lambda: (V.VideoDialog(self, payload), False)[1])

    def on_links(self, payload):
        GLib.idle_add(lambda: (D.LinksDialog(self, payload.get("links", []), payload.get("page", "")), False)[1])

    def show(self):
        GLib.idle_add(lambda: (self.present(), False)[1])


class LdmApp(Gtk.Application):
    def __init__(self):
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if sysint.IS_WIN:   # sem D-Bus no Windows; a instância única é feita pela API local (ldm.py)
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        self.m = None
        self.win = None
        self.api = None
        self.tray = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_prgname("ldm")
        theme.register_fonts()
        theme.install_icons()
        self.m = Manager()
        self.m.run()
        from .. import autostart
        autostart.sync(self.m.s["launch_on_startup"])
        self.win = MainWindow(self)
        self.api = Api(self.m, self.win)
        try:
            self.api.start()
        except OSError as e:
            self.win.notify("API local indisponível", f"Porta {self.m.s['api_port']} ocupada: {e}")
        self.hold()

    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        tray = "--tray" in args
        urls = [a for a in args if not a.startswith("--")]
        if not tray or not self.tray:
            self.win.show_all()
            self.win.present()
        for u in urls:
            if u.startswith("ldm://"):
                u = u[6:]
            if "--video" in args or V.is_video_page(u):
                V.VideoDialog(self.win, {"page_url": u})
            else:
                self.win.handle_add({"url": u})
        return 0

    def update_tray(self):
        want = self.m.s["tray_icon"]
        if want and not self.tray:
            with _no_deprecation():
                self.tray = Gtk.StatusIcon()
                try:
                    self.tray.set_from_file(theme.TRAY)
                except Exception:  # noqa: BLE001
                    self.tray.set_from_icon_name("folder-download")
                self.tray.set_title(APP_NAME)
                self.tray.connect("activate", self._tray_activate)
                self.tray.connect("popup-menu", self._tray_menu)
                self.tray.set_visible(True)
        elif not want and self.tray:
            self.tray.set_visible(False)
            self.tray = None

    def _tray_activate(self, *_):
        if self.win.is_visible() and self.win.is_active():
            self.win.hide()
        else:
            self.win.show_all()
            self.win.present()

    def _tray_menu(self, icon, button, time_):
        menu = Gtk.Menu()
        w = self.win
        for label, cb in (("Abrir o LDM", lambda: (w.show_all(), w.present())), ("Adicionar URL", w.add_url),
                          ("Baixar vídeo de uma página", lambda: V.ask_video_url(w)),
                          ("Iniciar fila principal", lambda: self.m.start_queue("main")),
                          ("Parar todos", self.m.pause_all)):
            w._mi(menu, label, cb)
        lim = Gtk.CheckMenuItem(label="Limitador de velocidade", active=self.m.s["speed_limiter_on"])
        lim.connect("toggled", lambda i: w.set_limiter(i.get_active()))
        menu.append(lim)
        menu.append(Gtk.SeparatorMenuItem())
        w._mi(menu, "Sair", self.quit_all)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time_)

    def quit_all(self):
        if self.api:
            self.api.stop()
        self.m.shutdown()
        self.release()
        self.quit()


class _no_deprecation:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", DeprecationWarning)

    def __exit__(self, *a):
        self._w.__exit__(*a)


def main(argv=None):
    app = LdmApp()
    return app.run(argv or sys.argv)
