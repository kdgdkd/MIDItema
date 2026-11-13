"""Smoke test de arranque: verifica que MiditemaSession arranca y carga
una canción sintética sin hardware MIDI ni TUI real."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from session import MiditemaSession, ClockState, SongState, PlaylistState


_SONG = {
    "song_name": "Smoke Test Song",
    "time_signature": "4/4",
    "parts": [
        {"name": "Intro", "bars": 8},
        {"name": "Verso", "bars": 16, "repeat_pattern": True},
        {"name": "Coro", "bars": 8},
        {"name": "Outro", "bars": 4},
    ],
}

_PLAYLIST = {
    "playlist_name": "Smoke Playlist",
    "songs": [
        {"filepath": "intro.json", "song_name": "Intro"},
        {"filepath": "outro.json", "song_name": "Outro"},
    ],
}


def _session():
    s = MiditemaSession()
    s.outputs_enabled = False
    return s


# --- Estado inicial ---

def test_initial_clock_state():
    s = _session()
    assert s.clock_state.status == "STOPPED"
    assert s.clock_state.bpm == 0.0


def test_initial_song_state():
    s = _session()
    assert s.song_state.current_part_index == -1
    assert s.song_state.parts == []


def test_initial_playlist_state():
    s = _session()
    assert s.playlist_state.is_active is False
    assert s.playlist_state.current_song_index == -1


def test_initial_flags():
    s = _session()
    assert s.shutdown_flag is False
    assert s.pending_action is None
    assert s.repeat_override_active is True
    assert s.part_loop_active is False


# --- Carga de canción ---

def test_load_song_returns_true():
    s = _session()
    assert s.load_song_file(data=_SONG) is True


def test_load_song_sets_name():
    s = _session()
    s.load_song_file(data=_SONG)
    assert s.song_state.song_name == "Smoke Test Song"


def test_load_song_sets_parts():
    s = _session()
    s.load_song_file(data=_SONG)
    assert len(s.song_state.parts) == 4


def test_load_song_normalizes_repeat_pattern():
    s = _session()
    s.load_song_file(data=_SONG)
    verso = s.song_state.parts[1]
    assert verso["repeat_pattern"] is True


def test_load_song_builds_global_parts():
    s = _session()
    s.load_song_file(data=_SONG)
    assert s.global_parts_manager.is_initialized is True
    assert len(s.global_parts_manager.global_parts) == 4


def test_load_song_time_signature():
    s = _session()
    s.load_song_file(data=_SONG)
    assert s.song_state.time_signature_numerator == 4


def test_load_invalid_song_returns_false():
    s = _session()
    result = s.load_song_file(data={"parts": [{"bars": 4}]})
    assert result is False


def test_load_song_no_args_returns_false():
    s = _session()
    assert s.load_song_file() is False


# --- Independencia entre instancias ---

def test_two_sessions_are_independent():
    a = _session()
    b = _session()
    a.load_song_file(data=_SONG)
    assert b.song_state.parts == []
    assert b.song_state.song_name != "Smoke Test Song"


def test_reload_resets_state():
    s = _session()
    s.load_song_file(data=_SONG)
    song2 = {"song_name": "Second", "parts": [{"name": "A", "bars": 4}]}
    s.load_song_file(data=song2)
    assert s.song_state.song_name == "Second"
    assert len(s.song_state.parts) == 1
