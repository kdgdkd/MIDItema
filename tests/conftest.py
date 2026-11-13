"""
Stubs para dependencias de I/O que no necesitamos en tests unitarios.
Se cargan antes que cualquier import de miditema para evitar ModuleNotFoundError
en entornos CI sin MIDI hardware ni display Textual.
"""
import sys
from unittest.mock import MagicMock

_STUBS = [
    "mido",
    "tui",
    "pythonosc",
    "pythonosc.udp_client",
    "pythonosc.osc_message_builder",
    "textual",
    "textual.color",
    "textual.app",
    "textual.containers",
    "textual.widgets",
    "textual.screen",
    "textual.events",
    "textual.binding",
    "textual.command",
    "textual.reactive",
    "textual.timer",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Color stub necesita ser callable y devolver algo con .hex
import types
_color_mod = types.ModuleType("textual.color")
_color_mod.Color = MagicMock()
sys.modules["textual.color"] = _color_mod
