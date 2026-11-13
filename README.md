# MIDItema

A MIDI-clock-slaved bar counter and part sequencer for live performance. Reads MIDI Clock from a master device and advances through song sections automatically — sending program changes, CCs, or OSC messages at each part transition.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)

## Quick Start

**Install dependencies:**

```bash
# 1. Install midicore first (editable mode)
pip install -e ../

# 2. Install miditema-specific dependencies
pip install textual
```

**Run without a file (file browser opens):**

```bash
python miditema.py
```

**Run with a song file:**

```bash
python miditema.py mysong
# Looks for temas/mysong.json
```

**Run with a playlist or directory:**

```bash
python miditema.py setlist.json
python miditema.py temas/setfolder/
```

## Minimal song file (`temas/mysong.json`)

```json
{
  "parts": [
    { "name": "Intro",  "bars": 8  },
    { "name": "Verse",  "bars": 16, "repeat_pattern": "repeat" },
    { "name": "Chorus", "bars": 8  }
  ]
}
```

## Key controls

| Key           | Action                              |
|---------------|-------------------------------------|
| `Enter`       | Init outputs → start → stop         |
| `← →`         | Previous / next part                |
| `Ctrl+← →`    | Previous / next part with state reconstruction |
| `↑` / `↓`     | Toggle loop-part / cancel action    |
| `PgUp/Dn`     | Previous / next song                |
| `m`         | Song mode / Loop mode toggle        |
| `o`         | Toggle outputs on/off               |
| `l`         | Live view (cycle: full → compact → off) |
| `v`         | Setlist view                        |
| `g`         | Session view (part launcher)        |
| `h`         | Help / key reference                |
| `q`         | Quit                                |
| `Esc`       | Close modal / clear sticky message  |

## CLI options

```
python miditema.py [file] [--conf FILE] [--quant bar|4|8|16|32|instant]
                           [--debug] [--no-output]
                           [--song-mode | --loop-mode]
```

## Device setup (`miditema.conf.json`)

```json5
{
  "devices": {
    "midi_in":  { "clock": "Ableton" },
    "midi_out": { "synth": "MicroKorg" },
    "osc_out":  { "live": { "ip": "127.0.0.1", "port": 9000 } }
  }
}
```

Device aliases can be shared with midimod via `midi.conf.json` at the `midicore/` root level — both files are merged automatically using `deep_merge` (midicore).

MIDItema depends on `midicore` for port management, MIDI clock synchronization, OSC networking, transport control, configuration loading, and the inter-process LocalBus.

## Full documentation

See [REFERENCE.md](REFERENCE.md) for the complete reference: triggers, playlists, dynamic values, repeat patterns, and advanced timing.
