"""Tests de integración para MIDItemaValidator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema_validator import MIDItemaValidator


def _valid_song():
    return {
        "parts": [
            {"name": "Intro", "bars": 8},
            {"name": "Verso", "bars": 16},
        ]
    }


def _valid_playlist():
    return {
        "playlist_name": "Test Set",
        "songs": [
            {"filepath": "intro.json"},
            {"filepath": "outro.json"},
        ],
    }


# --- Song validation ---

def test_valid_minimal_song():
    errors = MIDItemaValidator.validate_data(_valid_song())
    assert errors == []


def test_song_missing_parts():
    errors = MIDItemaValidator.validate_data({})
    assert any("parts" in str(e).lower() or "required" in str(e).lower() for e in errors)


def test_song_part_missing_name():
    data = {"parts": [{"bars": 4}]}
    errors = MIDItemaValidator.validate_data(data)
    assert errors


def test_song_part_missing_bars():
    data = {"parts": [{"name": "A"}]}
    errors = MIDItemaValidator.validate_data(data)
    assert errors


def test_song_part_bars_zero_is_invalid():
    data = {"parts": [{"name": "A", "bars": 0}]}
    errors = MIDItemaValidator.validate_data(data)
    assert errors


def test_song_with_valid_trigger():
    data = {
        "parts": [{"name": "A", "bars": 4}],
        "triggers": {
            "part_change": [{"device": "synth", "type": "program_change", "program": 5, "channel": 0}]
        }
    }
    errors = MIDItemaValidator.validate_data(data)
    assert errors == []


def test_song_trigger_invalid_type():
    data = {
        "parts": [{"name": "A", "bars": 4}],
        "triggers": {
            "part_start": [{"device": "synth", "type": "unknown_type", "program": 5}]
        }
    }
    errors = MIDItemaValidator.validate_data(data)
    assert errors


def test_song_with_cue():
    data = {
        "parts": [
            {"name": "A", "bars": 4, "cue": 1},
            {"name": "B", "bars": 4, "cue": 2},
        ]
    }
    errors = MIDItemaValidator.validate_data(data)
    assert errors == []


def test_song_duplicate_cues_are_invalid():
    data = {
        "parts": [
            {"name": "A", "bars": 4, "cue": 1},
            {"name": "B", "bars": 4, "cue": 1},
        ]
    }
    errors = MIDItemaValidator.validate_data(data)
    assert errors


def test_song_dynamic_value_in_program():
    data = {
        "parts": [{"name": "A", "bars": 4}],
        "triggers": {
            "part_change": [{"device": "d", "type": "program_change", "program": "part_index", "channel": 0}]
        }
    }
    errors = MIDItemaValidator.validate_data(data)
    assert errors == []


# --- Playlist validation ---

def test_valid_playlist():
    errors = MIDItemaValidator.validate_data(_valid_playlist())
    assert errors == []


def test_playlist_missing_songs():
    errors = MIDItemaValidator.validate_data({"playlist_name": "X"})
    assert errors


def test_playlist_song_missing_filepath():
    data = {"playlist_name": "X", "songs": [{"color": "red"}]}
    errors = MIDItemaValidator.validate_data(data)
    assert errors
