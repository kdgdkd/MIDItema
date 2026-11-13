"""Tests del filtrado por device_in en process_control_message.

Cubre el bug 1050000: una regla con device_in declarado no debe dispararse cuando
el mensaje llega de un dispositivo diferente, incluyendo el caso device_alias=''
(puerto de clock compartido sin alias explícito).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from session import MiditemaSession


def _cc_msg(control=1, channel=0, value=127):
    msg = MagicMock()
    msg.type = "control_change"
    msg.control = control
    msg.channel = channel
    msg.value = value
    return msg


def _session_with_rules(rules):
    s = MiditemaSession()
    s.outputs_enabled = False
    s.config["control"] = rules
    return s


# --- device_in filtra correctamente ---

def test_rule_with_device_in_fires_for_matching_alias():
    s = _session_with_rules([{"event": "cc", "cc": 1, "device_in": "SynA", "action": "next_part"}])
    s._dispatch_control_action = MagicMock()
    s.process_control_message(_cc_msg(), "SynA")
    s._dispatch_control_action.assert_called_once()


def test_rule_with_device_in_does_not_fire_for_different_alias():
    s = _session_with_rules([{"event": "cc", "cc": 1, "device_in": "SynA", "action": "next_part"}])
    s._dispatch_control_action = MagicMock()
    s.process_control_message(_cc_msg(), "SynB")
    s._dispatch_control_action.assert_not_called()


def test_rule_with_device_in_does_not_fire_for_empty_alias():
    """device_alias='' (puerto de clock compartido) no debe disparar reglas con device_in."""
    s = _session_with_rules([{"event": "cc", "cc": 1, "device_in": "SynA", "action": "next_part"}])
    s._dispatch_control_action = MagicMock()
    s.process_control_message(_cc_msg(), "")
    s._dispatch_control_action.assert_not_called()


def test_rule_without_device_in_fires_for_any_alias():
    """Regla sin device_in se dispara independientemente del alias."""
    s = _session_with_rules([{"event": "cc", "cc": 1, "action": "next_part"}])
    s._dispatch_control_action = MagicMock()
    s.process_control_message(_cc_msg(), "")
    s.process_control_message(_cc_msg(), "SynA")
    assert s._dispatch_control_action.call_count == 2


def test_rule_without_device_in_fires_for_default_alias():
    """Llamada sin alias (default '') no bloquea reglas sin device_in."""
    s = _session_with_rules([{"event": "cc", "cc": 1, "action": "next_part"}])
    s._dispatch_control_action = MagicMock()
    s.process_control_message(_cc_msg())  # no alias → ""
    s._dispatch_control_action.assert_called_once()


# --- Múltiples reglas, device_in mixtos ---

def test_mixed_rules_only_matching_fires():
    """Con dos reglas (una con device_in, otra sin), solo la correcta dispara."""
    rules = [
        {"event": "cc", "cc": 1, "device_in": "SynA", "action": "next_part"},
        {"event": "cc", "cc": 2, "action": "prev_part"},
    ]
    s = _session_with_rules(rules)
    s._dispatch_control_action = MagicMock()
    # CC 1 from SynB: rule[0] filtered out (device_in mismatch), rule[1] doesn't match cc=1
    s.process_control_message(_cc_msg(control=1), "SynB")
    s._dispatch_control_action.assert_not_called()
