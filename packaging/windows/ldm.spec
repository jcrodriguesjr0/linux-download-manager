# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: dois executáveis na mesma pasta (LDM.exe com janela, ldm-cli.exe para o terminal).
# Rodado por build.py, que define LDM_STAGE (extensão com o nome "Lunix" + ldm.ico).
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
STAGE = Path(os.environ["LDM_STAGE"])

a = Analysis(
    [str(ROOT / "ldm.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "data"), "data"), (str(STAGE / "browser_extension"), "browser_extension")],
    hiddenimports=["gi.repository.Gtk", "gi.repository.Gdk", "gi.repository.GdkPixbuf", "gi.repository.Gio",
                   "gi.repository.GLib", "gi.repository.GObject", "gi.repository.Pango",
                   "gi.repository.PangoCairo", "cairo", "winreg", "winsound"],
    hooksconfig={"gi": {"icons": ["Adwaita", "hicolor"], "themes": ["Adwaita"],
                        "languages": ["pt_BR", "en_US"], "module-versions": {"Gtk": "3.0", "Gdk": "3.0"}}},
    excludes=["tkinter", "test", "pydoc"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(STAGE / "ldm.ico")
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LDM", console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ldm-cli", console=True, icon=icon)
COLLECT(gui, cli, a.binaries, a.datas, name="LDM")
