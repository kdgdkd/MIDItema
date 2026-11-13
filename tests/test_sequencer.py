"""Tests unitarios para funciones puras del sequencer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from miditema import (
    _find_next_valid_part_index,
    normalize_repeat_pattern,
    SongState,
    PlaylistState,
)


# --- normalize_repeat_pattern ---

def test_normalize_true_string():
    assert normalize_repeat_pattern("true") is True

def test_normalize_false_string():
    assert normalize_repeat_pattern("false") is False

def test_normalize_passthrough_list():
    assert normalize_repeat_pattern([1, 2, 3]) == [1, 2, 3]

def test_normalize_passthrough_string():
    assert normalize_repeat_pattern("next") == "next"

def test_normalize_passthrough_bool():
    assert normalize_repeat_pattern(True) is True


# --- _find_next_valid_part_index helpers ---

def _make_parts(*bars_list):
    return [{"name": f"P{i}", "bars": b} for i, b in enumerate(bars_list)]


# --- Forward navigation ---

def test_find_next_forward_from_start():
    parts = _make_parts(4, 8, 16)
    idx, pc = _find_next_valid_part_index(parts, "+1", -1, 0, False)
    assert idx == 0 and pc == 0

def test_find_next_forward_from_middle():
    parts = _make_parts(4, 8, 16)
    idx, pc = _find_next_valid_part_index(parts, "+1", 1, 0, False)
    assert idx == 2 and pc == 0

def test_find_next_skips_zero_bar_parts():
    # Part 1 has 0 bars → skip to part 2
    parts = _make_parts(4, 0, 8)
    idx, pc = _find_next_valid_part_index(parts, "+1", 0, 0, False)
    assert idx == 2 and pc == 0


# --- Backward navigation ---

def test_find_next_backward_simple():
    parts = _make_parts(4, 8, 16)
    idx, pc = _find_next_valid_part_index(parts, "-1", 2, 0, False)
    assert idx == 1 and pc == 0

def test_find_next_backward_from_first_wraps():
    parts = _make_parts(4, 8, 16)
    # From index 0 going backwards wraps to the last part
    idx, pc = _find_next_valid_part_index(parts, "-1", 0, 0, False)
    assert idx == 2  # wraps to last

# --- Edge cases ---

def test_find_next_empty_parts():
    idx, pc = _find_next_valid_part_index([], "+1", -1, 0, False)
    assert idx is None and pc is None

def test_find_next_all_zero_bars():
    parts = _make_parts(0, 0, 0)
    idx, pc = _find_next_valid_part_index(parts, "+1", -1, 0, False)
    assert idx is None and pc is None

def test_find_next_single_part():
    parts = _make_parts(4)
    # Only one part; forward from -1 → index 0
    idx, pc = _find_next_valid_part_index(parts, "+1", -1, 0, False)
    assert idx == 0 and pc == 0


# --- Song mode (repeat_override=True) ---

def test_song_mode_stops_at_last_part():
    # In song mode, wrap past the last part returns None
    parts = _make_parts(4, 4, 4)
    idx, pc = _find_next_valid_part_index(parts, "+1", 2, 0, True)
    assert idx is None and pc is None

def test_song_mode_backward_stops_at_first():
    parts = _make_parts(4, 4, 4)
    idx, pc = _find_next_valid_part_index(parts, "-1", 0, 0, True)
    assert idx is None and pc is None


# --- Loop mode without repeat_pattern ---

def test_loop_mode_no_repeat_pattern_returns_none_after_wrap():
    # Parts without repeat_pattern are invalid in loop cycles (pass_count > 0)
    parts = _make_parts(4, 4, 4)
    idx, pc = _find_next_valid_part_index(parts, "+1", 2, 0, False)
    assert idx is None and pc is None


# --- repeat_pattern = True ---

def test_repeat_pattern_true_loops_forever():
    parts = [{"name": "A", "bars": 4, "repeat_pattern": True}]
    # Wrap from index 0 → pass_count=1; repeat_pattern=True → valid
    idx, pc = _find_next_valid_part_index(parts, "+1", 0, 0, False)
    assert idx == 0 and pc == 1

def test_repeat_pattern_repeat_string_loops():
    parts = [{"name": "A", "bars": 4, "repeat_pattern": "repeat"}]
    idx, pc = _find_next_valid_part_index(parts, "+1", 0, 0, False)
    assert idx == 0 and pc == 1


# --- repeat_pattern array ---

def test_repeat_pattern_array_true_at_first_cycle():
    # [True] → first cycle is valid
    parts = [{"name": "A", "bars": 4, "repeat_pattern": [True]}]
    idx, pc = _find_next_valid_part_index(parts, "+1", 0, 0, False)
    assert idx == 0 and pc == 1

def test_repeat_pattern_array_false_skips_cycle():
    # [False] → first loop cycle is skipped → None (max 2 iterations with 1 part)
    parts = [{"name": "A", "bars": 4, "repeat_pattern": [False]}]
    idx, pc = _find_next_valid_part_index(parts, "+1", 0, 0, False)
    assert idx is None and pc is None


# --- State equality ---

def test_song_state_equal_fresh():
    a, b = SongState(), SongState()
    assert a == b

def test_song_state_not_equal_part_index():
    a, b = SongState(), SongState()
    b.current_part_index = 2
    assert a != b

def test_song_state_not_equal_song_name():
    a, b = SongState(), SongState()
    b.song_name = "Nueva"
    assert a != b

def test_song_state_not_equal_remaining_beats():
    a, b = SongState(), SongState()
    b.remaining_beats_in_part = 16
    assert a != b

def test_song_state_not_equal_parts():
    a, b = SongState(), SongState()
    b.parts = [{"name": "X", "bars": 4}]
    assert a != b

def test_song_state_not_equal_wrong_type():
    assert SongState() != "not a state"
    assert SongState() != None

def test_playlist_state_equal_fresh():
    a, b = PlaylistState(), PlaylistState()
    assert a == b

def test_playlist_state_not_equal_song_index():
    a, b = PlaylistState(), PlaylistState()
    b.current_song_index = 3
    assert a != b

def test_playlist_state_not_equal_active():
    a, b = PlaylistState(), PlaylistState()
    b.is_active = True
    assert a != b

def test_playlist_state_not_equal_elements():
    a, b = PlaylistState(), PlaylistState()
    b.playlist_elements = [{"filepath": "song.json"}]
    assert a != b

def test_playlist_state_not_equal_wrong_type():
    assert PlaylistState() != {}
