"""Interface GTK3. Fixa as versões das bibliotecas antes de qualquer import (o host pode ter GTK4)."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
