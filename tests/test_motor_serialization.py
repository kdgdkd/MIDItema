"""Tests for the event-queue motor: verifies that concurrent clock/transport
events are serialized and that playback_start fires exactly once per start cycle."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from session import MiditemaSession

_SONG = {
    "song_name": "Motor Test",
    "parts": [{"name": "A", "bars": 4}],
}


def _session_with_motor():
    s = MiditemaSession()
    s.config = {}
    s.outputs_enabled = False
    s.load_song_file(data=_SONG)
    s.start_motor()
    return s


def _drain(s, seconds=0.3):
    time.sleep(seconds)


def test_concurrent_starts_fire_playback_once():
    """Ten simultaneous START events (passive + explicit) must produce exactly
    one playback_start and leave the session in PLAYING state."""
    s = _session_with_motor()
    s.initial_outputs_sent = True  # skip the initial-outputs pass

    for _ in range(5):
        s._event_queue.put({"type": "start", "passive": True})
    for _ in range(5):
        s._event_queue.put({"type": "start", "passive": False})

    _drain(s)
    s.shutdown_flag = True

    assert s.clock_state.status == "PLAYING"
    assert s._playback_start_count == 1


def test_passive_start_two_tick_flow_via_queue():
    """Tick events (not explicit START) drive the two-pass implicit start:
    first tick → initial outputs + stay STOPPED, second tick → PLAYING."""
    s = _session_with_motor()

    s._event_queue.put({"type": "tick", "bpm": 120.0, "ts": time.time()})
    _drain(s, 0.1)
    assert s.clock_state.status == "STOPPED"
    assert s.initial_outputs_sent is True

    s._event_queue.put({"type": "tick", "bpm": 120.0, "ts": time.time()})
    _drain(s, 0.1)
    assert s.clock_state.status == "PLAYING"

    s.shutdown_flag = True


def test_stop_resets_and_restart_fires_once():
    """After a STOP, a fresh start cycle must produce exactly one
    additional playback_start (cumulative count 2 total)."""
    s = _session_with_motor()
    s.initial_outputs_sent = True

    s._event_queue.put({"type": "start", "passive": False})
    _drain(s, 0.1)
    assert s._playback_start_count == 1

    s._event_queue.put({"type": "stop"})
    _drain(s, 0.1)
    assert s.clock_state.status == "STOPPED"

    s.initial_outputs_sent = True
    s._event_queue.put({"type": "start", "passive": False})
    _drain(s, 0.1)
    assert s._playback_start_count == 2

    s.shutdown_flag = True


def test_control_processed_in_motor_thread():
    """Control messages enqueued from external threads must be processed in
    the motor thread (not before the session is in a consistent state)."""
    import mido
    s = _session_with_motor()
    s.initial_outputs_sent = True

    processed = []
    original = s.process_control_message

    def spy(msg, alias=""):
        processed.append(threading.current_thread().name)
        original(msg, alias)

    import threading
    s.process_control_message = spy

    msg = mido.Message("program_change", program=0)
    s._event_queue.put({"type": "control", "msg": msg, "alias": "test"})
    _drain(s, 0.1)

    assert processed, "Control message was never processed"
    assert processed[0] == "session-motor"

    s.shutdown_flag = True
