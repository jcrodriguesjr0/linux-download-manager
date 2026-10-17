"""Integração com o desktop: atalho no menu, início com a sessão, ícone e cópia da extensão do navegador."""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ldm.py"
ICON_SRC = ROOT / "data" / "ldm.svg"
EXT_SRC = ROOT / "browser_extension"
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
AUTOSTART_FILE = CONFIG / "autostart" / "linux-download-manager.desktop"
MENU_FILE = DATA / "applications" / "linux-download-manager.desktop"
ICON_NAME = "linux-download-manager"
ICON_FILE = DATA / "icons" / "hicolor" / "scalable" / "apps" / f"{ICON_NAME}.svg"
# Pasta que navegadores Flatpak conseguem ler (permissão xdg-documents)
EXT_EXPORT = HOME / "Documents" / "LinuxDownloadManager-extensao"


def appimage():
    return os.environ.get("APPIMAGE", "")


def exec_line(extra=""):
    if appimage():
        return f'"{appimage()}" {extra}%U'
    py = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
    return f'{py} "{LAUNCHER}" {extra}%U'


def install_icon():
    ICON_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON_SRC, ICON_FILE)


def desktop_entry(extra_args=""):
    return f"""[Desktop Entry]
Type=Application
Name=Linux Download Manager
GenericName=Gerenciador de downloads
Comment=Downloads acelerados com várias conexões, vídeos do navegador, filas e agendador
Exec={exec_line(extra_args)}
Icon={ICON_NAME}
Terminal=false
Categories=Network;FileTransfer;
MimeType=x-scheme-handler/ldm;
StartupWMClass=ldm
"""


def set_enabled(on: bool):
    if on:
        install_icon()
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(desktop_entry("--tray "))
    else:
        AUTOSTART_FILE.unlink(missing_ok=True)


def is_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def sync(want: bool):
    """Chamado ao abrir o programa: alinha o início automático com a configuração e aponta a entrada
    para o executável em uso (a AppImage pode ter mudado de pasta ou de versão)."""
    try:
        if want:
            if not is_enabled() or AUTOSTART_FILE.read_text() != desktop_entry("--tray "):
                set_enabled(True)
        elif is_enabled():
            set_enabled(False)
    except OSError:
        pass


def target() -> str:
    return appimage() or str(LAUNCHER)


def install_menu_entry():
    install_icon()
    MENU_FILE.parent.mkdir(parents=True, exist_ok=True)
    MENU_FILE.write_text(desktop_entry())
    if AUTOSTART_FILE.exists():          # mantém o início automático apontando para o executável atual
        AUTOSTART_FILE.write_text(desktop_entry("--tray "))
    return MENU_FILE


def extension_dir() -> Path:
    """Pasta da extensão para carregar no navegador. Dentro da AppImage o caminho muda a cada execução,
    então a extensão é copiada para Documentos."""
    if not appimage():
        return EXT_SRC
    return export_extension()


def export_extension() -> Path:
    src_ver = json.loads((EXT_SRC / "manifest.json").read_text())["version"]
    try:
        cur = json.loads((EXT_EXPORT / "manifest.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        cur = None
    if cur != src_ver:
        if EXT_EXPORT.exists():
            shutil.rmtree(EXT_EXPORT)
        shutil.copytree(EXT_SRC, EXT_EXPORT)
    return EXT_EXPORT
