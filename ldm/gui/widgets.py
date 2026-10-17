"""Helpers GTK3 compartilhados pelos diálogos."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


def grid(spacing=8):
    g = Gtk.Grid(column_spacing=spacing, row_spacing=6, margin=10)
    return g


def row(g, r, label, widget, expand=True):
    lb = Gtk.Label(label=label, xalign=0)
    g.attach(lb, 0, r, 1, 1)
    widget.set_hexpand(expand)
    g.attach(widget, 1, r, 1, 1)
    return widget


def entry(text="", placeholder="", visibility=True):
    e = Gtk.Entry(text=text or "")
    e.set_placeholder_text(placeholder)
    e.set_visibility(visibility)
    return e


def check(label, active=False):
    return Gtk.CheckButton(label=label, active=bool(active))


def spin(value, lo, hi, step=1):
    s = Gtk.SpinButton.new_with_range(lo, hi, step)
    s.set_value(value)
    return s


def combo(options, active=None):
    """options: lista de (id, rótulo)."""
    c = Gtk.ComboBoxText()
    for oid, label in options:
        c.append(oid, label)
    if active is not None:
        c.set_active_id(active)
    if c.get_active() < 0 and options:
        c.set_active(0)
    return c


def textview(text="", height=70):
    tv = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    tv.get_buffer().set_text(text or "")
    sw = Gtk.ScrolledWindow(min_content_height=height, hexpand=True)
    sw.set_shadow_type(Gtk.ShadowType.IN)
    sw.add(tv)
    sw.tv = tv
    return sw


def tv_text(sw):
    b = sw.tv.get_buffer()
    return b.get_text(b.get_start_iter(), b.get_end_iter(), False)


def folder_entry(parent, path=""):
    """Entry + botão 'Procurar...' para pastas."""
    box = Gtk.Box(spacing=4)
    e = entry(path)
    e.set_hexpand(True)
    b = Gtk.Button(label="Procurar...")

    def pick(_):
        d = Gtk.FileChooserDialog(title="Escolher pasta", transient_for=parent,
                                  action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Selecionar", Gtk.ResponseType.OK)
        if e.get_text():
            d.set_current_folder(e.get_text())
        if d.run() == Gtk.ResponseType.OK:
            e.set_text(d.get_filename())
        d.destroy()

    b.connect("clicked", pick)
    box.pack_start(e, True, True, 0)
    box.pack_start(b, False, False, 0)
    box.entry = e
    return box


def message(parent, text, kind=Gtk.MessageType.INFO, secondary=None):
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind,
                          buttons=Gtk.ButtonsType.OK, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    d.run()
    d.destroy()


def confirm(parent, text, secondary=None, check_label=None, check_default=False):
    """Retorna (ok, check_ativo)."""
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
                          buttons=Gtk.ButtonsType.YES_NO, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    cb = None
    if check_label:
        cb = check(check_label, check_default)
        d.get_message_area().pack_start(cb, False, False, 0)
        cb.show()
    ok = d.run() == Gtk.ResponseType.YES
    val = cb.get_active() if cb else False
    d.destroy()
    return ok, val


def scrolled(child, h=150, w=-1):
    sw = Gtk.ScrolledWindow(min_content_height=h, hexpand=True, vexpand=True)
    if w > 0:
        sw.set_min_content_width(w)
    sw.set_shadow_type(Gtk.ShadowType.IN)
    sw.add(child)
    return sw


def check_list(columns):
    """TreeView com primeira coluna de checkbox. columns: lista de títulos (strings)."""
    store = Gtk.ListStore(bool, *[str] * len(columns), object)
    tv = Gtk.TreeView(model=store)
    r = Gtk.CellRendererToggle()

    def toggled(_, path):
        store[path][0] = not store[path][0]

    r.connect("toggled", toggled)
    tv.append_column(Gtk.TreeViewColumn("", r, active=0))
    for i, title in enumerate(columns, start=1):
        c = Gtk.TreeViewColumn(title, Gtk.CellRendererText(ellipsize=3), text=i)
        c.set_resizable(True)
        c.set_expand(i == 1)
        c.set_sort_column_id(i)
        tv.append_column(c)
    return tv, store
