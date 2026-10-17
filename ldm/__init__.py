"""Linux Download Manager (LDM) - gerenciador de downloads segmentado para Linux."""
import os as _os

APP_NAME = "Linux Download Manager"
APP_ID = _os.environ.get("LDM_APP_ID", "io.github.ldm")   # override só para testes
APPDIR = _os.environ.get("LDM_APPDIR", "")                  # definido pelo AppRun da AppImage
VERSION = "1.2.0"
