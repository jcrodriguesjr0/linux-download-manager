"""Widgets da "Linha de Download Viva": mapa de conexões dentro da lista e gráfico de velocidade do rodapé."""
from collections import deque

import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GObject, Gtk, Pango, PangoCairo  # noqa: E402

from . import theme  # noqa: E402


class SegmentCell(Gtk.CellRenderer):
    """Célula da coluna Progresso: rótulo de status + percentual em cima e o mapa de conexões embaixo.
    provider(iid) -> (segs, total, cor, completo, rótulo, percentual)."""
    iid = GObject.Property(type=str, default="")

    def __init__(self, provider):
        super().__init__()
        self.provider = provider
        self.set_padding(6, 7)

    def do_get_preferred_width(self, widget):
        return 160, 220

    def do_get_preferred_height(self, widget):
        return 38, 38

    def _text(self, cr, widget, text, x, y, color, mono=False, align_right_to=None, max_w=None):
        lay = widget.create_pango_layout(text)
        fd = Pango.FontDescription.from_string(("JetBrains Mono" if mono else "Inter") + " 8.5")
        lay.set_font_description(fd)
        if max_w:
            lay.set_width(int(max(10, max_w) * Pango.SCALE))
            lay.set_ellipsize(Pango.EllipsizeMode.END)
        if align_right_to is not None:
            x = align_right_to - lay.get_pixel_size()[0]
        cr.set_source_rgb(*theme.rgb(color))
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, lay)
        return lay.get_pixel_size()

    def do_render(self, cr, widget, _bg, cell, _flags):
        info = self.provider(self.props.iid)
        if not info:
            return
        segs, total, color, full, label, pct = info
        xp, yp = self.get_padding()
        x, w = cell.x + xp, cell.width - 2 * xp
        t = theme.tokens()
        pw = 0
        if pct:
            pw = self._text(cr, widget, pct, x, cell.y + yp - 1, color if color != theme.ERROR else t["muted"],
                            mono=True, align_right_to=x + w)[0]
        self._text(cr, widget, label, x, cell.y + yp - 1, theme.ERROR if color == theme.ERROR else t["muted"],
                   max_w=w - pw - 8)
        bar_h = 7
        theme.draw_segments(cr, x, cell.y + cell.height - yp - bar_h, w, bar_h, segs, total,
                            color=theme.PRIMARY if color == theme.ERROR else color, done_full=full)


class Sparkline(Gtk.DrawingArea):
    """Velocidade global dos últimos ~2 minutos (uma amostra por segundo)."""

    def __init__(self, samples=120):
        super().__init__()
        self.data = deque([0.0] * samples, maxlen=samples)
        self.set_size_request(160, 44)
        self.connect("draw", self._draw)

    def push(self, value):
        self.data.append(max(0.0, float(value)))
        self.queue_draw()

    def _draw(self, w, cr):
        a = w.get_allocation()
        W, H = a.width, a.height
        vals = list(self.data)
        top = max(vals) or 1.0
        n = len(vals)
        pts = [(i * (W - 6) / (n - 1) + 3, H - 4 - (v / top) * (H - 10)) for i, v in enumerate(vals)]
        r, g, b = theme.rgb(theme.PRIMARY)
        # área com degradê
        import cairo
        grad = cairo.LinearGradient(0, 0, 0, H)
        grad.add_color_stop_rgba(0, r, g, b, 0.35)
        grad.add_color_stop_rgba(1, r, g, b, 0.0)
        cr.move_to(pts[0][0], H)
        for px, py in pts:
            cr.line_to(px, py)
        cr.line_to(pts[-1][0], H)
        cr.close_path()
        cr.set_source(grad)
        cr.fill()
        # linha
        cr.set_line_width(2)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(*pts[0])
        for px, py in pts[1:]:
            cr.line_to(px, py)
        cr.set_source_rgb(r, g, b)
        cr.stroke()
        cr.arc(pts[-1][0], pts[-1][1], 3, 0, 6.2832)
        cr.fill()
