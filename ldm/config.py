"""Caminhos XDG, configurações padrão e categorias (espelham os padrões do IDM 6.43)."""
import json
import os
import secrets
import threading
from pathlib import Path

from . import sysint

HOME = Path.home()
CONFIG_DIR = sysint.config_dir()
DATA_DIR = sysint.data_dir()
SETTINGS_FILE = CONFIG_DIR / "settings.json"
DOWNLOADS_FILE = DATA_DIR / "downloads.json"
QUEUES_FILE = DATA_DIR / "queues.json"
GRABBER_DIR = DATA_DIR / "grabber_projects"


DOWNLOAD_ROOT = sysint.download_dir()

# Extensões padrão por categoria (as mesmas que os gerenciadores de download clássicos usam).
DEFAULT_CATEGORIES = [
    {"name": "Compactados", "exts": "zip rar r0* r1* arj gz sit sitx sea ace bz2 7z xz zst tar tgz", "sites": "", "folder": str(DOWNLOAD_ROOT / "Compressed")},
    {"name": "Documentos", "exts": "doc pdf ppt pps docx pptx xls xlsx odt ods odp epub txt", "sites": "", "folder": str(DOWNLOAD_ROOT / "Documents")},
    {"name": "Músicas", "exts": "mp3 wav wma mpa ram ra aac aif m4a tsa flac opus ogg", "sites": "", "folder": str(DOWNLOAD_ROOT / "Music")},
    {"name": "Programas", "exts": "exe msi deb rpm appimage flatpakref run sh bin apk", "sites": "", "folder": str(DOWNLOAD_ROOT / "Programs")},
    {"name": "Vídeos", "exts": "avi mpg mpe mpeg asf wmv mov qt rm mp4 flv m4v webm ogv mkv ts tsv 3gp", "sites": "", "folder": str(DOWNLOAD_ROOT / "Video")},
]

# Lista de tipos capturados automaticamente do navegador (string do IDMan.exe).
DEFAULT_CAPTURE_EXTS = ("3GP 7Z AAC ACE AIF APK ARJ ASF AVI BIN BZ2 DEB DOC DOCX EXE FLV GZ GZIP IMG ISO LZH M4A M4V "
                        "MKV MOV MP3 MP4 MPA MPE MPEG MPG MSI MSU OGG OGV PDF PLJ PPS PPT QT R0* R1* RA RAR RM RMVB "
                        "RPM SEA SIT SITX TAR TIF TIFF WAV WEBM WMA WMV XZ Z ZIP APPIMAGE")

DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

DEFAULTS = {
    "language": "pt",
    "dark_mode": True,                 # identidade "Fluxo Segmentado": escuro primeiro
    "identity_version": 2,
    "launch_on_startup": False,
    "monitor_clipboard": True,
    "tray_icon": True,
    "browser_capture": True,
    "api_port": 9614,
    "api_token": "",
    "capture_exts": DEFAULT_CAPTURE_EXTS,
    "capture_min_size_kb": 51200,      # abaixo de 50 MB o navegador baixa
    "capture_any_type": True,          # a partir do mínimo, o LDM captura qualquer tipo de arquivo
    "settings_version": 3,
    "exception_sites": "",
    "exception_addresses": "",
    "show_file_info_dialog": True,
    "ext_prompt": True,                # aviso "instale a extensão" ao abrir (até a extensão conectar)
    "ext_seen": False,                 # a extensão já falou com este LDM
    "show_complete_dialog": True,
    "show_progress_dialog": True,
    "start_immediately_while_info": False,
    "duplicate_action": "ask",          # ask | number | overwrite | resume
    "user_agent": DEFAULT_UA,
    "general_folder": str(DOWNLOAD_ROOT),
    "remember_last_folder": False,
    "temp_dir": str(DATA_DIR / "temp"),
    "categories": DEFAULT_CATEGORIES,
    "max_connections": 8,
    "min_segment_kb": 512,
    "retries": 5,
    "timeout": 30,
    "speed_limiter_on": False,
    "speed_limit_kbps": 1024,
    "speed_limiter_on_startup": False,
    "proxy_mode": "none",               # none | system | manual
    "proxy_http": "",
    "proxy_https": "",
    "proxy_bypass": "localhost 127.0.0.1",
    "ftp_passive": True,
    "site_logins": [],                  # [{"server": "*.exemplo.com/path", "user": "", "password": ""}]
    "virus_scanner": "",
    "virus_args": "[File]",
    "sound_complete": True,
    "sound_failed": True,
    "set_server_mtime": True,
    "window": {"width": 1180, "height": 640, "paned": 200},
    # Grabber de vídeo (yt-dlp)
    "distrobox_name": "ubuntu-24-04",
    "ytdlp_cmd": "",                    # comando manual do yt-dlp (vazio = detectar)
    "video_prefer_mp4": True,           # H.264/AAC em MP4 quando disponível (máxima compatibilidade)
    "video_max_height": 1080,           # qualidade pré-selecionada / usada sem diálogo
    "video_subs": False,
    "video_sub_langs": "pt.*,en.*",
    "video_show_dialog": True,
    "video_mode": "auto",               # auto = yt-dlp + captura do navegador | capture = só captura (modo IDM)
    "video_req_chunk_mb": 10,
    "video_folder": "",                 # vazio = pasta da categoria Vídeos
    # Captura do navegador (modo IDM)
    "capture_prevent_key": "alt",       # tecla(s) + clique: o navegador baixa
    "capture_force_key": "ctrl+alt",    # tecla(s) + clique: força o LDM em qualquer link
    "page_rules": {},                   # sobrepõe as regras do page_hook.js (scan_url, keys, media_ext, ignore_url)
    "columns_visible": ["name", "size", "status", "time_left", "rate", "last_try", "description"],
}


class Settings:
    """Configurações persistidas em JSON; thread-safe para leitura/escrita simples."""

    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        saved = {}
        if path.exists():
            try:
                saved = json.loads(path.read_text())
                self.data.update(saved)
            except Exception:
                pass
        changed = False
        if not self.data.get("api_token"):
            self.data["api_token"] = secrets.token_urlsafe(24)
            changed = True
        if saved and saved.get("settings_version", 1) < 3:   # 1.4.0: LDM preferido a partir de 50 MB
            self.data["settings_version"] = 3
            if not saved.get("capture_min_size_kb"):
                self.data["capture_min_size_kb"] = 51200
            changed = True
        if saved and saved.get("identity_version", 1) < 2:   # nova identidade visual: liga o modo escuro uma vez
            self.data["identity_version"] = 2
            self.data["dark_mode"] = True
            changed = True
        if changed:
            self.save()

    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)

    def save(self):
        with self._lock:
            atomic_write_json(self.path, self.data)


def atomic_write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.replace(tmp, path)
