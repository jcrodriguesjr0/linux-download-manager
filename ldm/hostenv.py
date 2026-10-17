"""Ambiente "limpo" para programas do sistema lançados pelo LDM.

Na AppImage, o AppRun aponta LD_LIBRARY_PATH, PYTHONHOME, GI_TYPELIB_PATH etc. para as bibliotecas
embutidas e guarda os valores originais em LDM_ORIG_<VAR>. Programas do host (xdg-open, Dolphin,
notify-send, distrobox...) precisam do ambiente original, senão carregam bibliotecas erradas.
Executáveis de dentro da AppImage (python, ffmpeg, deno) continuam com o ambiente embutido.
"""
import os
import subprocess

VARS = ("PATH", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "GI_TYPELIB_PATH",
        "GSETTINGS_SCHEMA_DIR", "XDG_DATA_DIRS", "GIO_MODULE_DIR", "GDK_PIXBUF_MODULE_FILE", "GTK_MODULES",
        "GTK3_MODULES", "GTK_PATH", "GTK_IM_MODULE_FILE", "GDK_BACKEND", "SSL_CERT_FILE")
UNSET = "__unset__"
_installed = False


def remember(var):
    """Guarda o valor original antes de o LDM alterá-lo (ex.: GDK_BACKEND)."""
    os.environ.setdefault(f"LDM_ORIG_{var}", os.environ.get(var, UNSET))


def host_env(base=None):
    env = dict(os.environ if base is None else base)
    for v in VARS:
        orig = env.get(f"LDM_ORIG_{v}")
        if orig is None:
            continue
        if orig == UNSET:
            env.pop(v, None)
        else:
            env[v] = orig
    for k in [k for k in env if k.startswith("LDM_ORIG_")] + ["LDM_APPDIR"]:
        env.pop(k, None)
    return env


def apply_to_launch_context(ctx):
    """Mesmo ajuste para apps abertos via Gio (ex.: 'Abrir com...')."""
    env = host_env()
    for v in VARS:
        if v in env:
            ctx.setenv(v, env[v])
        else:
            ctx.unsetenv(v)
    return ctx


def install():
    """Faz subprocess.Popen usar o ambiente do host por padrão para executáveis de fora da AppImage."""
    global _installed
    appdir = os.environ.get("LDM_APPDIR", "")
    if _installed:
        return
    _installed = True
    orig_init = subprocess.Popen.__init__

    def init(self, args, *a, **kw):
        if kw.get("env") is None:
            exe = args if isinstance(args, (str, bytes)) else (args[0] if args else "")
            exe = os.fsdecode(exe).split()[0] if exe else ""
            if not (appdir and exe.startswith(appdir)):
                kw["env"] = host_env()
        orig_init(self, args, *a, **kw)

    subprocess.Popen.__init__ = init
