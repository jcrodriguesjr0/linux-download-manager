"""Identidade visual do LDM: paleta "Fluxo Segmentado", fontes embutidas, ícones próprios e CSS do GTK.

A base é o Adwaita (embutido em todo GTK 3), então a aparência não depende do tema instalado no sistema.
"""
import ctypes
import ctypes.util
import sys
from pathlib import Path

from gi.repository import Gdk, Gtk

DATA = Path(__file__).resolve().parents[2] / "data"
LOGO = str(DATA / "ldm.svg")
TRAY = str(DATA / "ldm-tray.png")

# Paleta (identidade_visual/nova_identidade_visual/paleta.json)
PRIMARY = "#F43F5E"
PRIMARY_LIGHT = "#FB7185"
PRIMARY_DARK = "#E11D48"
VIDEO = "#F59E0B"
VIDEO_HOVER = "#FBBF24"
SUCCESS = "#22C55E"
ERROR = "#EF4444"
DARK = {"base": "#141316", "surface": "#1E1A1E", "elevated": "#272228", "border": "#382229",
        "text": "#F1F5F9", "muted": "#94A3B8", "channel": "#232025", "divider": "#141316"}
LIGHT = {"base": "#FFFFFF", "surface": "#F8FAFC", "elevated": "#FFFFFF", "border": "#E2E8F0",
         "text": "#0F172A", "muted": "#64748B", "channel": "#E9E4E7", "divider": "#FFFFFF"}

UI_FONT = "Inter, Segoe UI, Noto Sans, Cantarell, sans-serif"
MONO_FONT = "JetBrains Mono, Consolas, Hack, DejaVu Sans Mono, monospace"

_provider = None
_dark = True


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def tokens():
    return DARK if _dark else LIGHT


def is_dark():
    return _dark


def register_fonts():
    """Disponibiliza Inter e JetBrains Mono só para este processo, sem instalar no sistema."""
    fonts = sorted((DATA / "fonts").glob("*.ttf"))
    try:                     # Pango ≥ 1.56: funciona em qualquer backend (fontconfig, Windows/DirectWrite)
        from gi.repository import PangoCairo
        fm = PangoCairo.FontMap.get_default()
        if hasattr(fm, "add_font_file"):
            for f in fonts:
                fm.add_font_file(str(f))
            return
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        try:
            for f in fonts:  # FR_PRIVATE: só este processo enxerga a fonte
                ctypes.windll.gdi32.AddFontResourceExW(str(f), 0x10, 0)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("fontconfig") or "libfontconfig.so.1")
        lib.FcConfigAppFontAddDir.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.FcConfigAppFontAddDir(None, str(DATA / "fonts").encode())
    except OSError:
        pass


def install_icons():
    Gtk.IconTheme.get_default().append_search_path(str(DATA / "icons"))


def icon(name):
    """Ícone próprio (data/icons/ldm-<name>.svg)."""
    return f"ldm-{name}"


def _css(t):
    return f"""
* {{ font-family: {UI_FONT}; }}
.ldm-mono, .ldm-mono * {{ font-family: {MONO_FONT}; font-feature-settings: "tnum"; }}

window.background, dialog.background, notebook > stack {{
  background-color: {t['base']}; color: {t['text']};
}}
headerbar {{
  background: {t['surface']}; border-bottom: 1px solid {t['border']}; box-shadow: none;
  min-height: 46px; padding: 4px 8px;
}}
headerbar button {{ min-height: 30px; }}
.ldm-title {{ font-weight: 700; font-size: 15px; color: {t['text']}; }}
.ldm-subtitle {{ color: {t['muted']}; font-size: 12px; }}
.ldm-muted {{ color: {t['muted']}; }}

/* botões da marca: vermelho = download, âmbar = vídeo */
button.suggested-action, button.ldm-primary {{
  background-image: linear-gradient(to bottom, {PRIMARY_LIGHT}, {PRIMARY});
  color: #ffffff; border: 1px solid {PRIMARY_DARK}; box-shadow: none; text-shadow: none;
  font-weight: 600; border-radius: 8px; padding: 4px 14px;
}}
button.suggested-action:hover, button.ldm-primary:hover {{ background-image: linear-gradient(to bottom, #fda4af, {PRIMARY_LIGHT}); }}
button.ldm-video {{
  background-image: linear-gradient(to bottom, {VIDEO_HOVER}, {VIDEO});
  color: #1a1206; border: 1px solid #d97706; box-shadow: none; text-shadow: none;
  font-weight: 700; border-radius: 8px; padding: 4px 14px;
}}
button.ldm-video:hover {{ background-image: linear-gradient(to bottom, #fcd34d, {VIDEO_HOVER}); }}
button.ldm-ghost {{
  background: {t['elevated']}; color: {t['text']}; border: 1px solid {t['border']};
  box-shadow: none; border-radius: 8px; padding: 4px 12px;
}}
button.ldm-ghost:hover {{ border-color: {PRIMARY}; }}
button.ldm-ghost:checked {{ border-color: {PRIMARY}; color: {PRIMARY}; }}

/* lateral */
.ldm-sidebar, .ldm-sidebar treeview.view {{ background-color: {t['surface']}; color: {t['text']}; }}
.ldm-sidebar {{ border-right: 1px solid {t['border']}; }}
.ldm-sidebar treeview.view {{ padding: 2px 0; }}
.ldm-sidebar treeview.view:selected {{ background-color: alpha({PRIMARY}, 0.16); color: {t['text']}; }}

/* lista de downloads */
.ldm-list treeview.view {{ background-color: {t['base']}; color: {t['text']}; }}
.ldm-list treeview.view:selected {{ background-color: alpha({PRIMARY}, 0.14); color: {t['text']}; }}
.ldm-list treeview.view:hover {{ background-color: alpha({t['text']}, 0.03); }}
.ldm-list treeview.view header button {{
  background: {t['base']}; color: {t['muted']}; border: none; border-bottom: 1px solid {t['border']};
  box-shadow: none; font-size: 11px; font-weight: 600; letter-spacing: 1px; padding: 6px 8px;
}}

/* rodapé */
.ldm-footer {{ background-color: {t['surface']}; border-top: 1px solid {t['border']}; padding: 8px 14px; }}
.ldm-stat-label {{ color: {t['muted']}; font-size: 10px; letter-spacing: 1px; }}
.ldm-stat-speed {{ color: {PRIMARY}; font-size: 18px; font-weight: 700; }}
.ldm-stat-value {{ color: {t['text']}; font-size: 18px; font-weight: 700; }}

/* entradas, abas, barras */
entry {{ background: {t['elevated']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 8px; }}
entry:focus {{ border-color: {PRIMARY}; box-shadow: 0 0 0 1px alpha({PRIMARY}, 0.4); }}
notebook header {{ background: {t['surface']}; border-color: {t['border']}; }}
notebook tab:checked {{ color: {PRIMARY}; box-shadow: inset 0 -2px {PRIMARY}; }}
progressbar progress {{ background-image: linear-gradient(to right, {PRIMARY_LIGHT}, {PRIMARY}); border: none; border-radius: 6px; }}
progressbar trough {{ background: {t['channel']}; border: none; border-radius: 6px; min-height: 8px; }}
checkbutton check:checked, radiobutton radio:checked {{ background-image: none; background-color: {PRIMARY}; border-color: {PRIMARY_DARK}; color: #fff; }}
switch:checked {{ background-color: {PRIMARY}; border-color: {PRIMARY_DARK}; }}
scale highlight {{ background-color: {PRIMARY}; border-color: {PRIMARY}; }}
.ldm-video-accent {{ color: {VIDEO}; }}
treeview.view:selected {{ background-color: alpha({PRIMARY}, 0.18); color: {t['text']}; }}
.ldm-videolist treeview.view:selected {{ background-color: alpha({VIDEO}, 0.22); color: {t['text']}; }}
menu menuitem:hover {{ background-color: alpha({PRIMARY}, 0.85); color: #ffffff; }}
"""


def apply(dark: bool):
    """Aplica o tema: Adwaita (claro/escuro) como base + CSS da identidade do LDM."""
    global _provider, _dark
    _dark = bool(dark)
    st = Gtk.Settings.get_default()
    st.props.gtk_theme_name = "Adwaita"
    st.props.gtk_application_prefer_dark_theme = _dark
    screen = Gdk.Screen.get_default()
    if _provider is None:
        _provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _provider.load_from_data(_css(tokens()).encode())


def style(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.add_class(c)
    return widget


def rounded_rect(cr, x, y, w, h, r):
    import math
    r = max(0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def draw_segments(cr, x, y, w, h, segs, total, color=PRIMARY, done_full=False):
    """Mapa de conexões: canal escuro + um bloco por conexão (assinatura visual do LDM)."""
    t = tokens()
    cr.set_source_rgb(*rgb(t["channel"]))
    rounded_rect(cr, x, y, w, h, h / 2)
    cr.fill()
    if done_full:
        cr.set_source_rgb(*rgb(color))
        rounded_rect(cr, x, y, w, h, h / 2)
        cr.fill()
        return
    if not segs:
        return
    total = total if total and total > 0 else max(b for _a, _p, b in segs) + 1
    k = w / total
    cr.save()
    rounded_rect(cr, x, y, w, h, h / 2)
    cr.clip()
    light = rgb(PRIMARY_LIGHT if color == PRIMARY else VIDEO_HOVER)
    base = rgb(color)
    for i, (a, p, _b) in enumerate(segs):
        sx, sw = x + a * k, max(1.5, (p - a) * k)
        if p <= a:
            continue
        cr.set_source_rgb(*(light if i % 3 == 1 else base))
        cr.rectangle(sx, y, sw, h)
        cr.fill()
        cr.set_source_rgb(*rgb(t["divider"]))   # divisor entre conexões
        cr.rectangle(sx, y, 1.2, h)
        cr.fill()
    cr.restore()
