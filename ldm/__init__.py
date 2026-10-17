"""Linux Download Manager (LDM) - gerenciador de downloads segmentado para Linux."""
import os as _os

APP_NAME = "Lunix Download Manager" if _os.name == "nt" else "Linux Download Manager"   # Windows: "Lunix"
APP_ID = _os.environ.get("LDM_APP_ID", "io.github.ldm")   # override só para testes
APPDIR = _os.environ.get("LDM_APPDIR", "")                  # definido pelo AppRun da AppImage
VERSION = "1.4.0"
