"""Tests para setup_devices (doble llamada) y reconfigure_clock_port."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from session import MiditemaSession


def _session():
    s = MiditemaSession()
    s.outputs_enabled = False
    return s


# --- Doble llamada a setup_devices ---

def test_second_setup_devices_updates_bus_clock_alias():
    """La segunda llamada actualiza _bus_clock_alias si cambia clock_in."""
    s = _session()
    # device_alias non-empty so setup_devices doesn't return early;
    # clock_in not in device_alias keys triggers the bus-alias path
    s.setup_devices({"device_alias": {"MySynth": "Korg"}, "clock_in": "primera_fuente"})
    assert s._bus_clock_alias == "primera_fuente"
    s.setup_devices({"device_alias": {"MySynth": "Korg"}, "clock_in": "segunda_fuente"})
    assert s._bus_clock_alias == "segunda_fuente"


def test_second_setup_devices_preserves_existing_clock_port():
    """La segunda llamada sin clock_in no borra el puerto MIDI ya abierto."""
    s = _session()
    mock_port = MagicMock()
    mock_port.closed = False
    with patch("mido.open_input", return_value=mock_port):
        s.port_registry.open_input("clock", "Mock Port")
    # Second config has no clock_in → should not touch existing "clock" input
    s.setup_devices({"device_alias": {}})
    assert s.port_registry.get_input("clock") is mock_port


def test_clock_in_not_in_device_alias_adds_to_errors():
    """clock_in no encontrado en device_alias aparece en errors[] (alias posiblemente incorrecto)."""
    s = _session()
    # device_alias non-empty but does NOT contain "typo_alias"
    errors = s.setup_devices({"device_alias": {"MySynth": "Korg"}, "clock_in": "typo_alias"})
    assert any("typo_alias" in e for e in errors)


def test_clock_in_not_in_device_alias_still_sets_bus_alias():
    """Aunque se aniade al error, el alias de bus sigue configurado para compatibilidad."""
    s = _session()
    s.setup_devices({"device_alias": {"MySynth": "Korg"}, "clock_in": "bus_source"})
    assert s._bus_clock_alias == "bus_source"


# --- reconfigure_clock_port ---

def test_reconfigure_clock_port_closes_old_port():
    s = _session()
    old_port = MagicMock()
    old_port.closed = False
    new_port = MagicMock()
    new_port.closed = False
    with patch("mido.open_input", return_value=old_port):
        s.port_registry.open_input("clock", "Old Port")
    with patch("mido.open_input", return_value=new_port):
        s.reconfigure_clock_port("New Port")
    old_port.close.assert_called_once()


def test_reconfigure_clock_port_sets_new_port():
    s = _session()
    new_port = MagicMock()
    new_port.closed = False
    with patch("mido.open_input", return_value=new_port):
        s.reconfigure_clock_port("New Port")
    assert s.port_registry.get_input("clock") is new_port


def test_reconfigure_clock_port_updates_source_name():
    s = _session()
    new_port = MagicMock()
    new_port.closed = False
    with patch("mido.open_input", return_value=new_port):
        s.reconfigure_clock_port("Korg nanoKEY2")
    assert s.clock_state.source_name == "Korg nanoKEY2"
