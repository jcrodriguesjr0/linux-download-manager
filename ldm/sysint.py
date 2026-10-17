"""Integração com o sistema operacional (Linux e Windows) num lugar só.

Todo o resto do LDM chama estas funções em vez de xdg-open, systemctl, canberra, notify-send etc.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"
HOME = Path.home()
# No Windows, processos filhos não abrem janela de console
NO_WINDOW = 0x08000000 if IS_WIN else 0


def config_dir() -> Path:
    if os.environ.get("LDM_CONFIG_DIR"):          # testes e instalações portáteis
        return Path(os.environ["LDM_CONFIG_DIR"])
    if IS_WIN:
        return Path(os.environ.get("APPDATA", HOME / "AppData/Roaming")) / "LDM"
    return Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "ldm"


def data_dir() -> Path:
    if os.environ.get("LDM_DATA_DIR"):
        return Path(os.environ["LDM_DATA_DIR"])
    if IS_WIN:
        return Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local")) / "LDM"
    return Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "ldm"


def download_dir() -> Path:
    if IS_WIN:
        try:   # pasta Downloads real (pode ter sido movida pelo usuário)
            return _known_folder_downloads() or HOME / "Downloads"
        except Exception:  # noqa: BLE001
            return HOME / "Downloads"
    try:
        out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=2).stdout.strip()
        if out and out != str(HOME):
            return Path(out)
    except Exception:  # noqa: BLE001
        pass
    return HOME / "Downloads"


def _known_folder_downloads():
    """SHGetKnownFolderPath(FOLDERID_Downloads)."""
    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    u = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")
    g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
        return None
    try:
        return Path(p.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(p)


def popen(cmd, **kw):
    """subprocess.Popen sem janela de console no Windows."""
    if IS_WIN:
        kw["creationflags"] = kw.get("creationflags", 0) | NO_WINDOW
    return subprocess.Popen(cmd, **kw)


def open_path(p):
    p = str(p)
    if IS_WIN:
        os.startfile(p)  # noqa: S606 - abre com o programa associado
        return
    subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_folder(p):
    """Abre a pasta destacando o arquivo (Explorer /select ou FileManager1 do freedesktop)."""
    p = Path(p)
    if IS_WIN:
        if p.exists():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            open_path(p.parent)
        return
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                      "org.freedesktop.FileManager1", "ShowItems",
                      GLib.Variant("(ass)", ([Gio.File.new_for_path(str(p)).get_uri()], "")),
                      None, Gio.DBusCallFlags.NONE, 3000, None)
    except Exception:  # noqa: BLE001
        open_path(p.parent)


def power_off(force=False):
    if IS_WIN:
        popen(["shutdown", "/s", "/t", "0"] + (["/f"] if force else []))
    else:
        subprocess.Popen(["systemctl", "poweroff"] + (["-i"] if force else []))


def play_sound(event_id):
    """event_id: 'complete' ou 'dialog-error' (nomes do tema de sons freedesktop)."""
    if IS_WIN:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND if "error" in event_id else winsound.MB_OK)
        except Exception:  # noqa: BLE001
            pass
        return
    exe = shutil.which("canberra-gtk-play")
    if exe:
        subprocess.Popen([exe, "-i", event_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(app_name, icon, title, body):
    """Notificação do sistema. No Windows usa um balão da bandeja via PowerShell (sem dependências)."""
    if IS_WIN:
        ps = ("[void][Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
              "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
              "$n.Visible=$true;$n.ShowBalloonTip(5000,$env:LDM_T,$env:LDM_B,'Info');Start-Sleep 6;$n.Dispose()")
        env = dict(os.environ, LDM_T=title[:60], LDM_B=body[:200])
        try:
            popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], env=env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
        return
    exe = shutil.which("notify-send")
    if exe:
        subprocess.Popen([exe, "-a", app_name, "-i", icon, title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_process(proc):
    """Interrompe um processo filho de forma que ele salve o progresso (yt-dlp retoma o .part depois)."""
    if IS_WIN:
        proc.terminate()
    else:
        import signal
        proc.send_signal(signal.SIGINT)


def exe_name(name):
    return name + ".exe" if IS_WIN else name


def app_bin_dirs():
    """Pastas com ferramentas que vão junto com o programa (Windows: <instalação>\\bin; AppImage: usr/bin)."""
    dirs = [data_dir() / "bin"]                      # cópias atualizadas pelo usuário têm prioridade
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "bin")
    if os.environ.get("LDM_APPDIR"):
        dirs.append(Path(os.environ["LDM_APPDIR"]) / "usr" / "bin")
    return dirs


def find_tool(name):
    """yt-dlp, ffmpeg, deno...: pastas do LDM primeiro, depois o PATH."""
    for d in app_bin_dirs():
        p = d / exe_name(name)
        if p.is_file():
            return str(p)
    return shutil.which(name)


def install_windows_defaults():
    """Windows: processos filhos sem janela de console e com saída de texto em UTF-8."""
    if not IS_WIN:
        return
    orig_init = subprocess.Popen.__init__

    def init(self, *args, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | NO_WINDOW
        if (kw.get("text") or kw.get("universal_newlines")) and not kw.get("encoding"):
            kw["encoding"], kw["errors"] = "utf-8", "replace"
        env = kw.get("env")
        kw["env"] = dict(env if env is not None else os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        orig_init(self, *args, **kw)

    subprocess.Popen.__init__ = init
