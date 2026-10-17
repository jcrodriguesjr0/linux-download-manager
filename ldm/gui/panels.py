"""Janelas de configuração: Opções, Agendador/Filas e Site Grabber."""
import json
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import autostart, grabber  # noqa: E402
from ..config import GRABBER_DIR, atomic_write_json  # noqa: E402
from ..engine import ST_COMPLETE  # noqa: E402
from ..net import NetConfig  # noqa: E402
from ..util import fmt_size  # noqa: E402
from .dialogs import queue_options  # noqa: E402
from .widgets import (check, check_list, combo, entry, folder_entry, grid, message, row, scrolled,  # noqa: E402
                      spin, textview, tv_text)

DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


# ================================================================ Opções
class OptionsDialog(Gtk.Dialog):
    def __init__(self, win):
        super().__init__(title="Configuração", transient_for=win, modal=True)
        self.w, self.s = win, win.m.s
        self.set_default_size(700, 520)
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        nb = Gtk.Notebook(scrollable=True)
        self.get_content_area().pack_start(nb, True, True, 0)
        s = self.s

        # --- Geral (Browser/System Integration)
        g = grid()
        self.startup = check("Iniciar automaticamente ao ligar o computador (minimizado na bandeja)", autostart.is_enabled())
        self.startup.set_tooltip_text(f"Executável: {autostart.target()}\nArquivo: {autostart.AUTOSTART_FILE}")
        self.clip = check("Iniciar downloads de URLs copiadas para a área de transferência", s["monitor_clipboard"])
        self.tray = check("Mostrar ícone na bandeja do sistema", s["tray_icon"])
        self.dark = check("Modo escuro", s["dark_mode"])
        self.capture = check("Capturar downloads do navegador (requer a extensão LDM)", s["browser_capture"])
        for i, w in enumerate((self.startup, self.clip, self.tray, self.dark, self.capture)):
            g.attach(w, 0, i, 2, 1)
        self.lang = row(g, 5, "Idioma:", combo([("pt", "Português (Brasil)"), ("en", "English")], s["language"]))
        self.port = row(g, 6, "Porta da API local:", spin(s["api_port"], 1024, 65535))
        g.attach(Gtk.Label(label="Extensão do navegador: veja Ajuda → Extensão do navegador.",
                           xalign=0, wrap=True), 0, 7, 2, 1)
        nb.append_page(g, Gtk.Label(label="Geral"))

        # --- Tipos de arquivo
        g = grid()
        g.attach(Gtk.Label(label="Iniciar automaticamente o download dos seguintes tipos de arquivo:", xalign=0), 0, 0, 2, 1)
        self.exts = textview(s["capture_exts"], 80)
        g.attach(self.exts, 0, 1, 2, 1)
        size_box = Gtk.Box(spacing=8)
        self.min_mb = spin(round(int(s["capture_min_size_kb"] or 0) / 1024), 0, 100000)
        self.any_type = check("e, a partir desse tamanho, capturar qualquer tipo de arquivo", s["capture_any_type"])
        size_box.pack_start(self.min_mb, False, False, 0)
        size_box.pack_start(self.any_type, False, False, 0)
        row(g, 2, "Tamanho mínimo para captura (MB):", size_box)
        self.min_mb.set_tooltip_text("Arquivos menores que isso ficam com o navegador. 0 = sem mínimo.\n"
                                     "Com tamanho desconhecido, vale a lista de tipos acima.")
        g.attach(Gtk.Label(label="Não capturar downloads dos seguintes sites (separe por espaço, aceita *):", xalign=0), 0, 3, 2, 1)
        self.exc_sites = textview(s["exception_sites"], 60)
        g.attach(self.exc_sites, 0, 4, 2, 1)
        g.attach(Gtk.Label(label="Não capturar downloads dos seguintes endereços:", xalign=0), 0, 5, 2, 1)
        self.exc_addr = textview(s["exception_addresses"], 60)
        g.attach(self.exc_addr, 0, 6, 2, 1)
        keys = [("", "Nenhuma"), ("alt", "Alt"), ("shift", "Shift"), ("ctrl+alt", "Ctrl+Alt"), ("alt+shift", "Alt+Shift"),
                ("ctrl+shift", "Ctrl+Shift")]
        self.k_prevent = row(g, 7, "Tecla + clique num link: deixar o NAVEGADOR baixar", combo(keys, s["capture_prevent_key"]))
        self.k_force = row(g, 8, "Tecla + clique num link: FORÇAR o LDM (qualquer link)", combo(keys, s["capture_force_key"]))
        nb.append_page(g, Gtk.Label(label="Tipos de arquivo"))

        # --- Downloads
        g = grid()
        self.show_info = check("Mostrar o diálogo de início de download (informações do arquivo)", s["show_file_info_dialog"])
        self.show_prog = check("Mostrar o diálogo de progresso", s["show_progress_dialog"])
        self.show_done = check("Mostrar o diálogo de download concluído", s["show_complete_dialog"])
        self.mtime = check("Definir a data do arquivo conforme informada pelo servidor", s["set_server_mtime"])
        for i, w in enumerate((self.show_info, self.show_prog, self.show_done, self.mtime)):
            g.attach(w, 0, i, 2, 1)
        self.dup = row(g, 4, "Se um link duplicado for adicionado:", combo(
            [("ask", "Perguntar"), ("number", "Adicionar com nome numerado"), ("overwrite", "Sobrescrever"),
             ("resume", "Mostrar/retomar o existente")], s["duplicate_action"]))
        self.ua = row(g, 5, "User-Agent para downloads manuais:", entry(s["user_agent"]))
        self.av = row(g, 6, "Antivírus (programa):", entry(s["virus_scanner"], "ex.: clamscan --no-summary"))
        self.av_args = row(g, 7, "Parâmetros do antivírus:", entry(s["virus_args"]))
        g.attach(Gtk.Label(label="[File] é substituído pelo caminho do arquivo baixado.", xalign=0), 1, 8, 1, 1)
        self.snd_ok = check("Tocar som ao concluir", s["sound_complete"])
        self.snd_err = check("Tocar som em caso de erro", s["sound_failed"])
        g.attach(self.snd_ok, 0, 9, 2, 1)
        g.attach(self.snd_err, 0, 10, 2, 1)
        nb.append_page(g, Gtk.Label(label="Downloads"))

        # --- Salvar em (categorias)
        g = grid()
        self.gen = row(g, 0, "Pasta da categoria Geral:", folder_entry(self, s["general_folder"]))
        self.tmp = row(g, 1, "Pasta temporária:", folder_entry(self, s["temp_dir"]))
        self.cat_store = Gtk.ListStore(str, str, str, str)
        for c in s["categories"]:
            self.cat_store.append([c["name"], c["exts"], c.get("sites", ""), c["folder"]])
        tv = Gtk.TreeView(model=self.cat_store)
        for i, t in enumerate(["Categoria", "Extensões", "Somente sites", "Pasta"]):
            r = Gtk.CellRendererText(editable=True)
            r.connect("edited", lambda _r, path, text, col=i: self.cat_store.__getitem__(path).__setitem__(col, text))
            c = Gtk.TreeViewColumn(t, r, text=i)
            c.set_resizable(True)
            c.set_expand(i == 1)
            tv.append_column(c)
        g.attach(scrolled(tv, 220), 0, 2, 2, 1)
        bb = Gtk.Box(spacing=6)
        add = Gtk.Button(label="Nova categoria")
        add.connect("clicked", lambda _: self.cat_store.append(["Nova", "ext", "", s["general_folder"]]))
        rem = Gtk.Button(label="Remover")
        rem.connect("clicked", lambda _: self._remove_sel(tv))
        bb.pack_start(add, False, False, 0)
        bb.pack_start(rem, False, False, 0)
        bb.pack_start(Gtk.Label(label="(clique duas vezes numa célula para editar)"), False, False, 0)
        g.attach(bb, 0, 3, 2, 1)
        nb.append_page(g, Gtk.Label(label="Salvar em"))

        # --- Conexão
        g = grid()
        self.maxc = row(g, 0, "Número máximo de conexões por download:", spin(s["max_connections"], 1, 32))
        self.minseg = row(g, 1, "Tamanho mínimo de trecho (KB):", spin(s["min_segment_kb"], 64, 65536, 64))
        self.retries = row(g, 2, "Tentativas por conexão:", spin(s["retries"], 0, 100))
        self.timeout = row(g, 3, "Tempo limite (s):", spin(s["timeout"], 5, 600))
        nb.append_page(g, Gtk.Label(label="Conexão"))

        # --- Proxy
        g = grid()
        self.px_none = Gtk.RadioButton.new_with_label(None, "Sem proxy")
        self.px_sys = Gtk.RadioButton.new_with_label_from_widget(self.px_none, "Usar configuração do sistema (http_proxy/https_proxy)")
        self.px_man = Gtk.RadioButton.new_with_label_from_widget(self.px_none, "Configuração manual")
        {"none": self.px_none, "system": self.px_sys, "manual": self.px_man}[s["proxy_mode"]].set_active(True)
        for i, w in enumerate((self.px_none, self.px_sys, self.px_man)):
            g.attach(w, 0, i, 2, 1)
        self.px_http = row(g, 3, "Proxy HTTP (host:porta):", entry(s["proxy_http"]))
        self.px_https = row(g, 4, "Proxy HTTPS (host:porta):", entry(s["proxy_https"]))
        self.px_bypass = row(g, 5, "Não usar proxy para:", entry(s["proxy_bypass"]))
        self.pasv = check("Usar FTP em modo passivo (PASV)", s["ftp_passive"])
        g.attach(self.pasv, 0, 6, 2, 1)
        nb.append_page(g, Gtk.Label(label="Proxy"))

        # --- Logins de sites
        g = grid()
        g.attach(Gtk.Label(label="Usuários e senhas por servidor/site (aceita *). Ex.: *.exemplo.com ou ftp.site.com/pasta",
                           xalign=0, wrap=True), 0, 0, 2, 1)
        self.login_store = Gtk.ListStore(str, str, str)
        for lg in s["site_logins"]:
            self.login_store.append([lg["server"], lg["user"], lg["password"]])
        ltv = Gtk.TreeView(model=self.login_store)
        for i, t in enumerate(["Servidor/caminho", "Usuário", "Senha"]):
            r = Gtk.CellRendererText(editable=True)
            r.connect("edited", lambda _r, path, text, col=i: self.login_store.__getitem__(path).__setitem__(col, text))
            c = Gtk.TreeViewColumn(t, r, text=i) if i < 2 else Gtk.TreeViewColumn(t, r)
            if i == 2:
                c.set_cell_data_func(r, lambda col, cell, model, it, _: cell.set_property("text", "•" * len(model[it][2])))
            c.set_expand(i == 0)
            ltv.append_column(c)
        g.attach(scrolled(ltv, 200), 0, 1, 2, 1)
        bb = Gtk.Box(spacing=6)
        b1 = Gtk.Button(label="Novo")
        b1.connect("clicked", lambda _: self.login_store.append(["*.exemplo.com", "usuario", ""]))
        b2 = Gtk.Button(label="Remover")
        b2.connect("clicked", lambda _: self._remove_sel(ltv))
        bb.pack_start(b1, False, False, 0)
        bb.pack_start(b2, False, False, 0)
        g.attach(bb, 0, 2, 2, 1)
        nb.append_page(g, Gtk.Label(label="Logins de sites"))

        from .video import video_options_page
        vpage, self._apply_video = video_options_page(self, s)
        nb.insert_page(vpage, Gtk.Label(label="Vídeo"), 1)
        self.show_all()

    @staticmethod
    def _remove_sel(tv):
        model, it = tv.get_selection().get_selected()
        if it:
            model.remove(it)

    def run_and_apply(self):
        if self.run() == Gtk.ResponseType.OK:
            s = self.s
            s["launch_on_startup"] = self.startup.get_active()
            autostart.set_enabled(s["launch_on_startup"])
            s["monitor_clipboard"] = self.clip.get_active()
            s["tray_icon"] = self.tray.get_active()
            s["dark_mode"] = self.dark.get_active()
            s["browser_capture"] = self.capture.get_active()
            s["language"] = self.lang.get_active_id()
            s["api_port"] = int(self.port.get_value())
            s["capture_exts"] = " ".join(tv_text(self.exts).split())
            s["capture_min_size_kb"] = int(self.min_mb.get_value()) * 1024
            s["capture_any_type"] = self.any_type.get_active()
            s["exception_sites"] = " ".join(tv_text(self.exc_sites).split())
            s["exception_addresses"] = " ".join(tv_text(self.exc_addr).split())
            s["capture_prevent_key"] = self.k_prevent.get_active_id() or ""
            s["capture_force_key"] = self.k_force.get_active_id() or ""
            s["show_file_info_dialog"] = self.show_info.get_active()
            s["show_progress_dialog"] = self.show_prog.get_active()
            s["show_complete_dialog"] = self.show_done.get_active()
            s["set_server_mtime"] = self.mtime.get_active()
            s["duplicate_action"] = self.dup.get_active_id()
            s["user_agent"] = self.ua.get_text()
            s["virus_scanner"] = self.av.get_text().strip()
            s["virus_args"] = self.av_args.get_text().strip() or "[File]"
            s["sound_complete"] = self.snd_ok.get_active()
            s["sound_failed"] = self.snd_err.get_active()
            s["general_folder"] = self.gen.entry.get_text()
            s["temp_dir"] = self.tmp.entry.get_text()
            s["categories"] = [{"name": r[0], "exts": r[1], "sites": r[2], "folder": r[3]} for r in self.cat_store]
            s["max_connections"] = int(self.maxc.get_value())
            s["min_segment_kb"] = int(self.minseg.get_value())
            s["retries"] = int(self.retries.get_value())
            s["timeout"] = int(self.timeout.get_value())
            s["proxy_mode"] = "none" if self.px_none.get_active() else "system" if self.px_sys.get_active() else "manual"
            s["proxy_http"], s["proxy_https"] = self.px_http.get_text().strip(), self.px_https.get_text().strip()
            s["proxy_bypass"] = self.px_bypass.get_text()
            s["ftp_passive"] = self.pasv.get_active()
            s["site_logins"] = [{"server": r[0], "user": r[1], "password": r[2]} for r in self.login_store]
            self._apply_video()
            s.save()
            self.w.apply_settings()
        self.destroy()


# ================================================================ Agendador / Filas
class SchedulerWindow(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Agendador")
        self.w, self.m = win, win.m
        self.set_transient_for(win)
        self.set_default_size(820, 520)
        paned = Gtk.Paned()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        outer.pack_start(paned, True, True, 0)
        self.add(outer)

        self.qstore = Gtk.ListStore(str, str)
        self.qtv = Gtk.TreeView(model=self.qstore, headers_visible=True)
        self.qtv.append_column(Gtk.TreeViewColumn("Filas", Gtk.CellRendererText(), text=1))
        self.qtv.get_selection().connect("changed", self._select)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left.pack_start(scrolled(self.qtv, 300, 180), True, True, 0)
        nb_ = Gtk.Box(spacing=4)
        b_new = Gtk.Button(label="Nova fila")
        b_new.connect("clicked", self._new)
        b_del = Gtk.Button(label="Excluir")
        b_del.connect("clicked", self._delete)
        nb_.pack_start(b_new, True, True, 0)
        nb_.pack_start(b_del, True, True, 0)
        left.pack_start(nb_, False, False, 0)
        paned.pack1(left, False, False)

        nb = Gtk.Notebook()
        paned.pack2(nb, True, False)

        g = grid()
        self.q_name = row(g, 0, "Nome da fila:", entry())
        self.sc_on = check("Iniciar o download em horário agendado")
        g.attach(self.sc_on, 0, 1, 2, 1)
        tb = Gtk.Box(spacing=4)
        self.h = spin(2, 0, 23)
        self.mi = spin(0, 0, 59)
        tb.pack_start(self.h, False, False, 0)
        tb.pack_start(Gtk.Label(label=":"), False, False, 0)
        tb.pack_start(self.mi, False, False, 0)
        row(g, 2, "Horário de início:", tb, False)
        self.once = Gtk.RadioButton.new_with_label(None, "Uma vez, em")
        self.daily = Gtk.RadioButton.new_with_label_from_widget(self.once, "Diariamente / nos dias")
        self.date = entry(time.strftime("%Y-%m-%d"))
        ob = Gtk.Box(spacing=4)
        ob.pack_start(self.once, False, False, 0)
        ob.pack_start(self.date, False, False, 0)
        g.attach(ob, 0, 3, 2, 1)
        db = Gtk.Box(spacing=2)
        db.pack_start(self.daily, False, False, 0)
        self.days = [check(d) for d in DAYS]
        for c in self.days:
            db.pack_start(c, False, False, 0)
        g.attach(db, 0, 4, 2, 1)
        self.repeat = row(g, 5, "Repetir a cada (min, 0 = não; sincronização periódica):", spin(0, 0, 100000))
        self.stop_on = check("Parar o download às")
        sb = Gtk.Box(spacing=4)
        self.sh, self.sm = spin(8, 0, 23), spin(0, 0, 59)
        sb.pack_start(self.stop_on, False, False, 0)
        sb.pack_start(self.sh, False, False, 0)
        sb.pack_start(Gtk.Label(label=":"), False, False, 0)
        sb.pack_start(self.sm, False, False, 0)
        g.attach(sb, 0, 6, 2, 1)
        self.retries = row(g, 7, "Tentativas por arquivo se o download falhar:", spin(3, 0, 100))
        self.ondone = row(g, 8, "Ao concluir a fila:", combo([("none", "Nada"), ("exit", "Sair do LDM"),
                                                             ("shutdown", "Desligar o computador"),
                                                             ("open", "Abrir o arquivo abaixo")]))
        self.open_file = row(g, 9, "Arquivo a abrir:", entry())
        self.on_startup = check("Iniciar o download quando o LDM abrir")
        g.attach(self.on_startup, 0, 10, 2, 1)
        nb.append_page(g, Gtk.Label(label="Agendamento"))

        g2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin=8)
        pb = Gtk.Box(spacing=6)
        self.parallel = spin(1, 1, 50)
        pb.pack_start(Gtk.Label(label="Baixar"), False, False, 0)
        pb.pack_start(self.parallel, False, False, 0)
        pb.pack_start(Gtk.Label(label="arquivos ao mesmo tempo"), False, False, 0)
        g2.pack_start(pb, False, False, 0)
        self.fstore = Gtk.ListStore(str, str, str, str)
        self.ftv = Gtk.TreeView(model=self.fstore)
        for i, t in enumerate(["Arquivo", "Tamanho", "Status"]):
            c = Gtk.TreeViewColumn(t, Gtk.CellRendererText(ellipsize=3), text=i)
            c.set_expand(i == 0)
            self.ftv.append_column(c)
        g2.pack_start(scrolled(self.ftv, 280), True, True, 0)
        mb = Gtk.Box(spacing=4)
        for label, fn in (("Subir", lambda _: self._move(-1)), ("Descer", lambda _: self._move(1)),
                          ("Remover da fila", self._remove_item)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            mb.pack_start(b, False, False, 0)
        g2.pack_start(mb, False, False, 0)
        nb.append_page(g2, Gtk.Label(label="Arquivos na fila"))

        bb = Gtk.Box(spacing=6)
        for label, fn in (("Iniciar agora", self._start), ("Parar", self._stop)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            bb.pack_start(b, False, False, 0)
        close = Gtk.Button(label="Fechar")
        close.connect("clicked", lambda _: self.destroy())
        apply_b = Gtk.Button(label="Aplicar")
        apply_b.connect("clicked", lambda _: self._apply())
        bb.pack_end(close, False, False, 0)
        bb.pack_end(apply_b, False, False, 0)
        outer.pack_start(bb, False, False, 0)
        self.cur = None
        self._reload_queues()
        self.show_all()

    def _reload_queues(self, select=None):
        self.qstore.clear()
        for q in self.m.queues.values():
            self.qstore.append([q["id"], q["name"] + ("  ▶" if q["running"] else "")])
        sel = select or (self.cur or "main")
        for i, r in enumerate(self.qstore):
            if r[0] == sel:
                self.qtv.get_selection().select_path(Gtk.TreePath(i))

    def _select(self, selection):
        model, it = selection.get_selected()
        if not it:
            return
        q = self.m.queues.get(model[it][0])
        if not q:
            return
        self.cur = q["id"]
        sc = q["schedule"]
        self.q_name.set_text(q["name"])
        self.sc_on.set_active(sc["enabled"])
        h, mi = (sc["start_time"].split(":") + ["0"])[:2]
        self.h.set_value(int(h))
        self.mi.set_value(int(mi))
        (self.once if sc.get("once") else self.daily).set_active(True)
        self.date.set_text(sc.get("date") or time.strftime("%Y-%m-%d"))
        for i, c in enumerate(self.days):
            c.set_active(i in sc.get("days", []))
        self.repeat.set_value(int(sc.get("repeat_minutes") or 0))
        self.stop_on.set_active(sc.get("stop_enabled", False))
        sh, sm = (sc.get("stop_time", "08:00").split(":") + ["0"])[:2]
        self.sh.set_value(int(sh))
        self.sm.set_value(int(sm))
        self.retries.set_value(q["retries"])
        self.ondone.set_active_id(q.get("on_done", "none"))
        self.open_file.set_text(q.get("open_file", ""))
        self.on_startup.set_active(q.get("start_on_startup", False))
        self.parallel.set_value(q["parallel"])
        self._fill_files()

    def _fill_files(self):
        self.fstore.clear()
        q = self.m.queues.get(self.cur)
        for iid in q["items"] if q else []:
            it = self.m.items.get(iid)
            if it:
                self.fstore.append([it["filename"], fmt_size(it.get("size")), self.w.status_text(it), iid])

    def _apply(self):
        q = self.m.queues.get(self.cur)
        if not q:
            return
        q["name"] = self.q_name.get_text().strip() or q["name"]
        q["schedule"].update(
            enabled=self.sc_on.get_active(), start_time=f"{int(self.h.get_value()):02d}:{int(self.mi.get_value()):02d}",
            once=self.once.get_active(), date=self.date.get_text().strip(),
            days=[i for i, c in enumerate(self.days) if c.get_active()], repeat_minutes=int(self.repeat.get_value()),
            stop_enabled=self.stop_on.get_active(), stop_time=f"{int(self.sh.get_value()):02d}:{int(self.sm.get_value()):02d}")
        q.update(retries=int(self.retries.get_value()), on_done=self.ondone.get_active_id(),
                 open_file=self.open_file.get_text(), start_on_startup=self.on_startup.get_active(),
                 parallel=int(self.parallel.get_value()))
        self.m.mark_dirty()
        self._reload_queues(q["id"])
        self.w.refresh_tree()

    def _new(self, _):
        d = Gtk.Dialog(title="Nova fila", transient_for=self, modal=True)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        e = entry("Fila " + str(len(self.m.queues) + 1))
        e.set_activates_default(True)
        d.set_default_response(Gtk.ResponseType.OK)
        d.get_content_area().add(Gtk.Label(label="Nome da nova fila:"))
        d.get_content_area().add(e)
        d.show_all()
        if d.run() == Gtk.ResponseType.OK and e.get_text().strip():
            q = self.m.add_queue(e.get_text().strip())
            self._reload_queues(q["id"])
            self.w.refresh_tree()
        d.destroy()

    def _delete(self, _):
        if self.cur == "main":
            message(self, "A fila principal não pode ser excluída.")
            return
        self.m.delete_queue(self.cur)
        self.cur = "main"
        self._reload_queues()
        self.w.refresh_tree()

    def _sel_item(self):
        model, it = self.ftv.get_selection().get_selected()
        return model[it][3] if it else None

    def _move(self, delta):
        iid = self._sel_item()
        if iid:
            self.m.move_in_queue(self.cur, iid, delta)
            self._fill_files()

    def _remove_item(self, _):
        iid = self._sel_item()
        if iid:
            self.m.remove_from_queue(iid)
            self._fill_files()

    def _start(self, _):
        self._apply()
        self.m.start_queue(self.cur)
        self._reload_queues()

    def _stop(self, _):
        self.m.stop_queue(self.cur)
        self._reload_queues()


# ================================================================ Site Grabber
class GrabberWindow(Gtk.Window):
    def __init__(self, win, start_url="", project=None):
        super().__init__(title="LDM Site Grabber")
        self.w, self.m = win, win.m
        self.set_default_size(860, 620)
        self.g = None
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        self.add(outer)
        g = grid()
        self.name = row(g, 0, "Nome do projeto:", entry("Projeto " + time.strftime("%Y-%m-%d %H%M")))
        self.url = row(g, 1, "Página inicial/endereço:", entry(start_url))
        self.tpl = row(g, 2, "Modelo:", combo([(k, k) for k in grabber.TEMPLATES], "Todos os arquivos"))
        self.types = row(g, 3, "Baixar os tipos de arquivo:", entry("*"))
        self.ex_types = row(g, 4, "Não baixar os tipos:", entry(""))
        lv = Gtk.Box(spacing=6)
        self.levels = spin(1, 0, 20)
        self.ext_levels = spin(0, 0, 5)
        lv.pack_start(Gtk.Label(label="Níveis de links no site base:"), False, False, 0)
        lv.pack_start(self.levels, False, False, 0)
        lv.pack_start(Gtk.Label(label="em outros sites:"), False, False, 0)
        lv.pack_start(self.ext_levels, False, False, 0)
        g.attach(lv, 0, 5, 2, 1)
        ob = Gtk.Box(spacing=10)
        self.no_parent = check("Não explorar diretórios pais", True)
        self.same_host = check("Somente o mesmo host (desmarcado: todo o domínio principal)", True)
        ob.pack_start(self.no_parent, False, False, 0)
        ob.pack_start(self.same_host, False, False, 0)
        g.attach(ob, 0, 6, 2, 1)
        self.inc = row(g, 7, "Explorar somente (caminhos/domínios, ';'):", entry())
        self.exc = row(g, 8, "Não explorar (caminhos/domínios, ';'):", entry())
        sz = Gtk.Box(spacing=6)
        self.min_kb, self.max_kb = spin(0, 0, 10 ** 8), spin(0, 0, 10 ** 8)
        for w in (Gtk.Label(label="Tamanho do arquivo: mín. (KB)"), self.min_kb, Gtk.Label(label="máx. (KB, 0 = sem limite)"), self.max_kb):
            sz.pack_start(w, False, False, 0)
        g.attach(sz, 0, 9, 2, 1)
        au = Gtk.Box(spacing=6)
        self.user, self.pwd = entry(placeholder="usuário"), entry(placeholder="senha", visibility=False)
        au.pack_start(Gtk.Label(label="Autorização:"), False, False, 0)
        au.pack_start(self.user, True, True, 0)
        au.pack_start(self.pwd, True, True, 0)
        g.attach(au, 0, 10, 2, 1)
        self.tpl.connect("changed", lambda c: self.types.set_text(grabber.TEMPLATES[c.get_active_id()]))
        outer.pack_start(g, False, False, 0)

        ab = Gtk.Box(spacing=6)
        self.go = Gtk.Button(label="Explorar")
        self.go.get_style_context().add_class("suggested-action")
        self.go.connect("clicked", self._explore)
        self.stop_b = Gtk.Button(label="Parar")
        self.stop_b.connect("clicked", lambda _: self.g and self.g.stop())
        self.status = Gtk.Label(xalign=0)
        for label, fn in (("Salvar projeto", self._save), ("Carregar projeto", self._load)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            ab.pack_end(b, False, False, 0)
        ab.pack_start(self.go, False, False, 0)
        ab.pack_start(self.stop_b, False, False, 0)
        ab.pack_start(self.status, True, True, 0)
        outer.pack_start(ab, False, False, 0)

        self.tv, self.store = check_list(["Arquivo", "Tamanho", "Descrição", "Endereço"])
        outer.pack_start(scrolled(self.tv, 220), True, True, 0)
        bb = Gtk.Box(spacing=6)
        for label, val in (("Marcar todos", True), ("Desmarcar todos", False)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _, v=val: [r.__setitem__(0, v) for r in self.store])
            bb.pack_start(b, False, False, 0)
        self.queue = combo(queue_options(self.m), "main")
        bb.pack_start(Gtk.Label(label="Fila:"), False, False, 0)
        bb.pack_start(self.queue, False, False, 0)
        self.folder = folder_entry(self, str(Path(self.m.s["general_folder"]) / "grabber"))
        bb.pack_start(self.folder, True, True, 0)
        add_b = Gtk.Button(label="Adicionar marcados à fila e iniciar")
        add_b.connect("clicked", self._add)
        bb.pack_end(add_b, False, False, 0)
        outer.pack_start(bb, False, False, 0)
        if project:
            self._apply_project(project)
        self.show_all()

    def _params(self):
        return {"name": self.name.get_text(), "url": self.url.get_text().strip(), "types": self.types.get_text(),
                "ex_types": self.ex_types.get_text(), "levels": int(self.levels.get_value()),
                "ext_levels": int(self.ext_levels.get_value()), "no_parent": self.no_parent.get_active(),
                "same_host": self.same_host.get_active(), "inc": self.inc.get_text(), "exc": self.exc.get_text(),
                "min_kb": int(self.min_kb.get_value()), "max_kb": int(self.max_kb.get_value()),
                "folder": self.folder.entry.get_text()}

    def _apply_project(self, p):
        self.name.set_text(p.get("name", ""))
        self.url.set_text(p.get("url", ""))
        self.types.set_text(p.get("types", "*"))
        self.ex_types.set_text(p.get("ex_types", ""))
        self.levels.set_value(p.get("levels", 1))
        self.ext_levels.set_value(p.get("ext_levels", 0))
        self.no_parent.set_active(p.get("no_parent", True))
        self.same_host.set_active(p.get("same_host", True))
        self.inc.set_text(p.get("inc", ""))
        self.exc.set_text(p.get("exc", ""))
        self.min_kb.set_value(p.get("min_kb", 0))
        self.max_kb.set_value(p.get("max_kb", 0))
        if p.get("folder"):
            self.folder.entry.set_text(p["folder"])

    def _explore(self, _):
        p = self._params()
        if not p["url"]:
            return
        self.store.clear()
        self.go.set_sensitive(False)
        self.g = grabber.Grabber(
            p["url"], NetConfig(self.m.s), file_types=p["types"], exclude_types=p["ex_types"], levels=p["levels"],
            external_levels=p["ext_levels"], same_domain_only=p["same_host"], no_parent=p["no_parent"],
            explore_include=p["inc"], explore_exclude=p["exc"], min_size=p["min_kb"] * 1024,
            max_size=p["max_kb"] * 1024, auth=(self.user.get_text(), self.pwd.get_text()),
            on_progress=lambda pg, f: GLib.idle_add(self.status.set_text, f"Páginas processadas: {pg} · arquivos: {f}"))

        def work():
            files = self.g.run()
            GLib.idle_add(self._done, files)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, files):
        self.go.set_sensitive(True)
        for f in files:
            name = f["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1] or f["url"]
            self.store.append([True, name, fmt_size(f["size"]), f["text"], f["url"], f])
        self.status.set_text(f"Concluído: {self.g.pages} páginas, {len(files)} arquivos encontrados")

    def _add(self, _):
        qid = self.queue.get_active_id()
        folder = self.folder.entry.get_text()
        n = 0
        for r in self.store:
            if r[0]:
                f = r[5]
                self.m.add(f["url"], referer=f["referer"], description=f["text"], save_dir=folder, start=False,
                           queue_id=qid, duplicate="number")
                n += 1
        if n:
            self.m.start_queue(qid)
            self.status.set_text(f"{n} arquivos adicionados à fila")

    def _save(self, _):
        p = self._params()
        GRABBER_DIR.mkdir(parents=True, exist_ok=True)
        fn = GRABBER_DIR / (p["name"].replace("/", "_") + ".json")
        atomic_write_json(fn, p)
        self.status.set_text(f"Projeto salvo em {fn}")
        self.w.refresh_tree()

    def _load(self, _):
        d = Gtk.FileChooserDialog(title="Carregar projeto", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Abrir", Gtk.ResponseType.OK)
        GRABBER_DIR.mkdir(parents=True, exist_ok=True)
        d.set_current_folder(str(GRABBER_DIR))
        if d.run() == Gtk.ResponseType.OK:
            try:
                self._apply_project(json.loads(Path(d.get_filename()).read_text()))
            except Exception as e:  # noqa: BLE001
                message(self, f"Projeto inválido: {e}", Gtk.MessageType.ERROR)
        d.destroy()


def completed_items(m):
    return [it for it in m.items.values() if it["status"] == ST_COMPLETE]
