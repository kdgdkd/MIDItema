"""Tests for the implicit-start (passive) two-pass flow.

When MIDI clock ticks arrive without an explicit START message, handle_start
must be called on every tick while STOPPED so the two-pass logic completes:
  tick 1 → sends initial outputs, sets initial_outputs_sent, stays STOPPED
  tick 2 → transitions to PLAYING, fires playback_start
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from session import MiditemaSession

_SONG = {
    "song_name": "Implicit Start Test",
    "parts": [{"name": "A", "bars": 4}],
}


def _session():
    s = MiditemaSession()
    s.outputs_enabled = False
    s.load_song_file(data=_SONG)
    return s


# --- Two-pass handle_start behavior ---

def test_first_passive_call_stays_stopped():
    s = _session()
    s.handle_start(is_passive_start=True)
    assert s.clock_state.status == "STOPPED"


def test_first_passive_call_marks_initial_outputs_sent():
    s = _session()
    s.handle_start(is_passive_start=True)
    assert s.initial_outputs_sent is True


def test_second_passive_call_transitions_to_playing():
    s = _session()
    s.handle_start(is_passive_start=True)
    s.handle_start(is_passive_start=True)
    assert s.clock_state.status == "PLAYING"


def test_additional_passive_calls_noop_when_playing():
    s = _session()
    s.handle_start(is_passive_start=True)
    s.handle_start(is_passive_start=True)
    s.handle_start(is_passive_start=True)
    assert s.clock_state.status == "PLAYING"


def test_stop_resets_initial_outputs_flag():
    s = _session()
    s.handle_start(is_passive_start=True)
    s.handle_start(is_passive_start=True)
    s.handle_stop()
    assert s.initial_outputs_sent is False
    assert s.clock_state.status == "STOPPED"


def test_restart_after_stop_requires_two_ticks():
    s = _session()
    s.handle_start(is_passive_start=True)
    s.handle_start(is_passive_start=True)
    s.handle_stop()
    # Restart: tick 1 → still STOPPED, tick 2 → PLAYING
    s.handle_start(is_passive_start=True)
    assert s.clock_state.status == "STOPPED"
    s.handle_start(is_passive_start=True)
    assert s.clock_state.status == "PLAYING"
