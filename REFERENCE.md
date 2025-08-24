# MIDItema Configuration Reference

Complete technical reference for configuring MIDItema files, including device setup, trigger system, song structures, and playlists.

## Table of Contents

1. [File Types Overview](#file-types-overview)
2. [Main Configuration File](#main-configuration-file)
3. [Song Files](#song-files)
4. [Playlist Files](#playlist-files)
5. [Trigger System Reference](#trigger-system-reference)
6. [Control Message Reference](#control-message-reference)
7. [Dynamic Values Reference](#dynamic-values-reference)
8. [Complete Examples](#complete-examples)

## File Types Overview

MIDItema uses JSON5 format (JSON with comments) for all configuration files:

- **Main Configuration** (`miditema.conf.json`): Device connections and global triggers
- **Song Files** (`*.json` in content directory): Individual song definitions
- **Playlist Files** (`*.json` in content directory): Collections of songs with playlist-specific settings

## Main Configuration File (Optional)

The main configuration file (`miditema.conf.json`) is **optional**. You can define devices and triggers directly in song/playlist files, or use a different config file with `--conf filename.json`.

Use a main config when you have a fixed setup you want to reuse across multiple songs/playlists. Skip it if you prefer to embed everything in individual files.

### Basic Structure

```json
{
    "devices": {
        "midi_in": { /* MIDI input ports */ },
        "midi_out": { /* MIDI output ports */ },
        "osc_out": { /* OSC destinations */ }
    },
    "triggers": {
        "event_name": [ /* list of action objects */ ]
    }
}
```

### Devices Section

#### MIDI Input Ports

```json
"midi_in": {
    "clock": "E-RM Multiclock",        // Required: MIDI clock source
    "midi_in": "MIDItema Controller"   // Optional: Control messages
}
```

- **`clock`** (Required): Unique substring of MIDI input port name that provides MIDI Clock and transport (Start/Stop/Continue) messages
- **`midi_in`** (Optional): Port for control messages (CC, Program Change, Notes). Can be the same as clock port

**Port Name Matching**: Uses case-insensitive substring matching. "multiclock" would match "E-RM Multiclock MIDI 1".

#### MIDI Output Ports

```json
"midi_out": {
    "transport_out": "Ableton Live",   // Special: Auto-forwards transport
    "synth_A": "Moog Minitaur",        // Custom alias
    "synth_B": "Roland JP-08",         // Custom alias
    "drums": "Arturia DrumBrute",      // Custom alias
    "lights": "MIDI2DMX Pro"           // Custom alias
}
```

- **`transport_out`** (Special Alias): If defined, MIDItema automatically forwards Start/Stop/Continue commands to this port
- **Custom Aliases**: Create any aliases you want to reference in triggers

#### OSC Output Destinations

```json
"osc_out": {
    "resolume": { "ip": "127.0.0.1", "port": 7000 },
    "touchdesigner": { "ip": "192.168.1.100", "port": 8000 },
    "lighting": { "ip": "10.0.0.5", "port": 9000 }
}
```

Each destination requires:

- **`ip`**: Target IP address (string)
- **`port`**: Target port number (integer)

### Complete Device Configuration Example

```json
{
    "devices": {
        "midi_in": {
            "clock": "Push 2",
            "midi_in": "APC40"
        },
        "midi_out": {
            "transport_out": "Ableton Live",
            "synth_lead": "Minilogue",
            "synth_bass": "Sub 37",
            "drums": "Tempest",
            "fx_unit": "Eventide H9"
        },
        "osc_out": {
            "visuals": { "ip": "127.0.0.1", "port": 7000 },
            "lights": { "ip": "192.168.1.10", "port": 8000 }
        }
    }
}
```

## Song Files

Song files define individual pieces of music with their structure, timing, and automation.

### Basic Song Structure

```json
{
    "song_name": "My Song",
    "color": "blue",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        // Array of part objects
    ]
}
```

### Root-Level Parameters

#### song_name (Optional)

The display name for the song. If omitted, uses the filename without extension.

```json
"song_name": "Interstellar Journey"
```

#### color (Optional)

Background color for the song's title bar in the UI.

**Available Colors:**
`default`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `orange`, `ruby_pink`, `indigo_blue`, `purple`, `forest_green`, `ivory`, `bright_red`, `neon_green`, `electric_blue`, `bright_yellow`, `hot_pink`, `electric_cyan`, `electric_orange`, `dark_gray`, `mid_gray`, `light_gray`, `white`

**Custom Hex Colors:**

```json
"color": "#FF5733"
```

#### time_signature (Optional)

The time signature of the song. Only the numerator is currently used for beat calculations.

```json
"time_signature": "4/4"    // Default
"time_signature": "3/4"
"time_signature": "7/8"
```

#### time_division (Optional)

Defines what constitutes a "beat" in the song relative to MIDI Clock's 24 PPQN.

```json
"time_division": "1/4"     // Quarter note = 24 ticks (default)
"time_division": "1/8"     // Eighth note = 12 ticks
"time_division": "1/16"    // Sixteenth note = 6 ticks
```

### Parts Array

The `parts` array contains the actual song structure. Each part is an object with the following properties:

#### Required Part Parameters

```json
{
    "name": "Verse 1",     // Display name
    "bars": 16             // Length in bars
}
```

#### Optional Part Parameters

##### color (Optional)

Sets the color for this part's display elements.

```json
"color": "green"
"color": "#42A5F5"
```

##### notes (Optional)

Short description displayed in the UI.

```json
"notes": "Add reverb on vocal"
```

##### cue (Optional)

Assigns a global cue number (1-127) for direct access via F-keys or MIDI CC#2.

```json
"cue": 5    // Accessible via F5 or CC#2 value 5
```

##### repeat_pattern (Optional)

Controls what happens when this part finishes. This is the core of MIDItema's dynamic flow control.

**Basic Patterns:**

```json
"repeat_pattern": "repeat"     // Loop this part
"repeat_pattern": "next"       // Go to next part (default)
"repeat_pattern": false        // Go to next part (explicit)
```

**Navigation Patterns:**

```json
"repeat_pattern": "prev"           // Go to previous part
"repeat_pattern": "first_part"     // Go to first part of song
"repeat_pattern": "last_part"      // Go to last part of song
```

**Playlist Navigation:**

```json
"repeat_pattern": "next_song"      // Load next song in playlist
"repeat_pattern": "prev_song"      // Load previous song
"repeat_pattern": "first_song"     // Load first song
"repeat_pattern": "last_song"      // Load last song
```

**Mode Control:**

```json
"repeat_pattern": "song_mode"      // Switch to Song Mode, then next
"repeat_pattern": "loop_mode"      // Switch to Loop Mode, then next
"repeat_pattern": "loop_part"      // Activate manual part loop
```

**Complex Patterns (Arrays):**

```json
// Play this pattern: next, next, repeat, jump to part 0
"repeat_pattern": ["next", "next", "repeat", {"jump_to_part": 0}]

// Random selection from parts 2, 4, or 6 on each pass
"repeat_pattern": [{"random_part": [2, 4, 6]}]

// Mix of actions
"repeat_pattern": [
    "next",
    "repeat", 
    {"jump_to_cue": 5},
    "next_song"
]
```

**Jump Objects:**

```json
{"jump_to_part": 3}        // Jump to part index 3 (0-based)
{"jump_to_cue": 12}        // Jump to part with "cue": 12
// Note: random_part is not fully implemented in current version
```

##### output (Optional)

Local triggers that fire when this part begins. Can be a single action object or an array.

```json
// Single action
"output": {
    "device": "synth_lead",
    "program": 5
}

// Multiple actions
"output": [
    {"device": "synth_lead", "program": 5},
    {"device": "lights", "channel": 0, "control": 10, "value": 127}
]
```

### Complete Song Example

```json
{
    "song_name": "Digital Dreams",
    "color": "electric_blue",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        {
            "name": "Ambient Intro",
            "bars": 8,
            "color": "dark_gray",
            "notes": "Soft pad entrance",
            "output": {
                "device": "synth_pad",
                "program": 12
            }
        },
        {
            "name": "Beat Drop",
            "bars": 4,
            "color": "bright_red",
            "notes": "Kick comes in",
            "output": [
                {"device": "drums", "program": 1},
                {"device": "visuals", "address": "/scene/beat_start"}
            ]
        },
        {
            "name": "Main Groove",
            "bars": 16,
            "color": "neon_green",
            "cue": 1,
            "repeat_pattern": ["repeat", "repeat", "next"],
            "output": {
                "device": "synth_bass",
                "program": 3
            }
        },
        {
            "name": "Break",
            "bars": 8,
            "color": "yellow",
            "repeat_pattern": "repeat",
            "notes": "Manual break section"
        },
        {
            "name": "Final Drop",
            "bars": 32,
            "color": "hot_pink",
            "cue": 2,
            "repeat_pattern": ["repeat", "next_song"],
            "output": [
                {"device": "synth_lead", "program": 8},
                {"device": "fx_unit", "control": 20, "value": 100}
            ]
        }
    ]
}
```

## Playlist Files

Playlist files organize multiple songs into setlists with global settings.

### Basic Playlist Structure

```json
{
    "playlist_name": "Live Set 2024",
    "mode": "loop",
    "devices": { /* Optional device overrides */ },
    "triggers": { /* Optional global triggers */ },
    "songs": [
        // Array of song references or embedded songs
    ]
}
```

### Playlist Parameters

#### playlist_name (Optional)

Display name for the playlist. Defaults to filename.

```json
"playlist_name": "Summer Festival Set"
```

#### mode (Optional)

Default playbook mode for the playlist.

```json
"mode": "loop"    // Respects repeat_pattern (default)
"mode": "song"    // Forces linear progression
```

#### devices (Optional)

Override or extend device configurations from the main config file. If no main config exists, this defines all devices.

```json
"devices": {
    "midi_out": {
        "special_synth": "Prophet 6"  // Adds to existing devices or creates new ones
    }
}
```

**Note**: Any song or playlist file can include a `devices` section. This allows each file to be completely self-contained without requiring a main config file.

#### triggers (Optional)

Additional triggers specific to this playlist, merged with global triggers.

```json
"triggers": {
    "song_change": [
        {
            "device": "lights",
            "address": "/playlist/song_title",
            "args": ["song_name"]
        }
    ]
}
```

### Songs Array

The songs array can contain two types of entries:

#### External Song References

References to separate song files in the same directory.

```json
{
    "filepath": "song1.json",
    "song_name": "Override Name",    // Optional override
    "color": "blue"                  // Optional override
}
```

#### Embedded Songs

Complete song definitions within the playlist.

```json
{
    "song_name": "Interlude",
    "color": "purple",
    "parts": [
        {"name": "Ambient", "bars": 16, "repeat_pattern": "repeat"}
    ]
}
```

### Self-Contained Playlist Example

This playlist file includes everything needed without requiring a main config:

```json
{
    "playlist_name": "Self-Contained Set",
    "mode": "loop",

    // Complete device setup in this file
    "devices": {
        "midi_in": {
            "clock": "Push 2",
            "midi_in": "APC40"
        },
        "midi_out": {
            "transport_out": "Ableton Live",
            "synth_A": "Minilogue",
            "drums": "DrumBrute"
        },
        "osc_out": {
            "visuals": { "ip": "127.0.0.1", "port": 7000 }
        }
    },

    // Complete triggers in this file
    "triggers": {
        "part_change": [
            {
                "device": "synth_A",
                "program": "part_index"
            }
        ]
    },

    "songs": [
        // ... song definitions
    ]
}
```

```json
{
    "playlist_name": "Electronic Set - December 2024",
    "mode": "loop",

    "devices": {
        "midi_out": {
            "venue_lights": "DMX Controller"
        }
    },

    "triggers": {
        "song_change": [
            {
                "device": "venue_lights",
                "control": 1,
                "value": "song_index"
            }
        ],
        "setlist_end": [
            {
                "device": "visuals",
                "address": "/show/end"
            }
        ]
    },

    "songs": [
        // External song file
        {
            "filepath": "opener.json",
            "color": "electric_blue"
        },

        // Embedded transition
        {
            "song_name": "Transition A",
            "color": "dark_gray",
            "parts": [
                {
                    "name": "Ambient Bridge", 
                    "bars": 8, 
                    "repeat_pattern": "next_song"
                }
            ]
        },

        // Another external song
        {
            "filepath": "main_track.json"
        },

        // Final embedded piece
        {
            "song_name": "Finale",
            "color": "bright_red",
            "parts": [
                {
                    "name": "Build Up", 
                    "bars": 16, 
                    "cue": 10,
                    "output": [
                        {"device": "venue_lights", "program": 50}
                    ]
                },
                {
                    "name": "Drop", 
                    "bars": 32, 
                    "repeat_pattern": "repeat"
                }
            ]
        }
    ]
}
```

## Trigger System Reference

The trigger system is MIDItema's automation engine, sending MIDI and OSC messages in response to events.

### Trigger Structure

```json
"triggers": {
    "event_name": [
        {
            "device": "device_alias",
            // MIDI or OSC parameters
            // Optional timing parameters
        }
    ]
}
```

### Available Events

#### Transport Events

- **`playback_start`**: Fired when playback begins
- **`playback_stop`**: Fired when playback stops  
- **`playback_continue`**: Fired when playback resumes
- **`playback_initial_start`**: Fired only on the very first start (not on continue)

#### Structure Events

- **`part_change`**: Fired when a new part begins
- **`song_change`**: Fired when a new song loads
- **`setlist_end`**: Fired when playlist completes

#### Rhythmic Events

- **`bar_triggers`**: Fired at regular bar intervals
- **`countdown_triggers`**: Fired on beats before transitions

### Action Object Types

#### MIDI Actions

**Program Change:**

```json
{
    "device": "synth_A",
    "type": "program_change",    // Optional if "program" is present
    "channel": 0,
    "program": 5
}

// Shorthand (type inferred)
{
    "device": "synth_A",
    "channel": 0,
    "program": 5
}
```

**Control Change:**

```json
{
    "device": "fx_unit", 
    "type": "control_change",    // Optional if "control" is present
    "channel": 1,
    "control": 20,
    "value": 127
}

// Shorthand
{
    "device": "fx_unit",
    "channel": 1,
    "control": 20,
    "value": 127
}
```

**Note On/Off:**

```json
{
    "device": "sampler",
    "type": "note_on",          // Optional if "note" is present
    "channel": 9,
    "note": 36,
    "velocity": 100
}

// Note Off
{
    "device": "sampler",
    "type": "note_off",
    "channel": 9,
    "note": 36,
    "velocity": 0
}

// Shorthand (defaults to note_on, velocity 127)
{
    "device": "sampler",
    "channel": 9,
    "note": 36
}
```

**Song Select:**

```json
{
    "device": "sequencer",
    "type": "song_select",       // Optional if "song" is present
    "song": 3
}

// Shorthand
{
    "device": "sequencer",
    "song": 3
}
```

#### OSC Actions

```json
{
    "device": "visuals",
    "address": "/composition/scene/trigger",
    "args": [1, "fade", 2.5, true]
}

// With dynamic values
{
    "device": "lights",
    "address": "/miditema/part",
    "args": ["part_name", "part_color", "part_bars"]
}
```

#### Delayed Triggers

Add timing parameters to schedule actions before their triggering event:

```json
// Fire 1 bar before part change
{
    "device": "synth_lead",
    "program": "part_index",
    "bar": 1
}

// Fire 8 beats before part change  
{
    "device": "visuals",
    "address": "/prepare",
    "args": ["part_name"],
    "beats": 8
}
```

### Rhythmic Trigger Parameters

#### bar_triggers

```json
"bar_triggers": [
    {
        "device": "lights",
        "each_bar": 4,               // Fire every 4 bars
        "control": 10,
        "value": "block_number"      // 1, 2, 3, etc.
    }
]
```

#### countdown_triggers

```json
"countdown_triggers": [
    {
        "device": "display",
        "each_beat": 8,              // Fire on last 8 beats
        "address": "/countdown",
        "args": ["remaining_beats"]   // 8, 7, 6, 5, 4, 3, 2, 1
    }
]
```

### Device Inheritance

If you don't specify a device in an action, it inherits from the last action that did specify one:

```json
"part_change": [
    {
        "device": "synth_A",         // Device specified
        "program": "part_index"
    },
    {
        // Uses "synth_A" from previous action
        "control": 20,
        "value": 127
    },
    {
        "device": "lights",          // New device
        "program": 1
    },
    {
        // Uses "lights" from previous action
        "control": 5, 
        "value": 0
    }
]
```

## Control Message Reference

### Keyboard Controls

| Key(s)                 | Action                            | Quantization |
| ---------------------- | --------------------------------- | ------------ |
| **Transport**          |                                   |              |
| `Enter`                | Toggle Start/Stop                 | Immediate    |
| `Space`                | Toggle Continue/Stop              | Immediate    |
| **Navigation**         |                                   |              |
| `←` / `→`              | Previous/Next Part                | Global       |
| `PageUp` / `PageDown`  | Previous/Next Song                | Global       |
| `Home` / `End`         | First/Last Song                   | Global       |
| `.` or `,` then number | Go to Part N                      | Global       |
| **Control**            |                                   |              |
| `↓`                    | Cancel Action / Reset             | Immediate    |
| `↑`                    | Toggle Part Loop                  | Immediate    |
| `m`                    | Toggle Loop/Song Mode             | Immediate    |
| **Cues**               |                                   |              |
| `F1`-`F12`             | Go to Cue 1-12                    | Dynamic      |
| **Quick Jumps**        |                                   |              |
| `0`-`3`                | Next part with fixed quantization | Fixed        |
| **Global Quantize**    |                                   |              |
| `4`-`9`                | Set global quantize mode          | Immediate    |

### MIDI Controls

#### Note Messages

| Note | Action        | Quantization |
| ---- | ------------- | ------------ |
| 124  | Previous Part | Global       |
| 125  | Next Part     | Global       |
| 126  | Previous Song | Global       |
| 127  | Next Song     | Global       |

#### Program Change

- **Value N**: Go to Part N+1 (Global quantization)

#### Song Select

- **Value N**: Go to Song N+1 (Global quantization)

#### Control Change Messages

##### CC #0 (Main Control)

| Value                        | Action                  | Quantization |
| ---------------------------- | ----------------------- | ------------ |
| **Quick Jumps**              |                         |              |
| 0                            | Next Part               | Instant      |
| 1                            | Next Part               | Next Bar     |
| 2                            | Next Part               | Next 8       |
| 3                            | Next Part               | Next 16      |
| **Global Quantize Settings** |                         |              |
| 4                            | Set Global: Next 4      | Immediate    |
| 5                            | Set Global: Next 8      | Immediate    |
| 6                            | Set Global: Next 16     | Immediate    |
| 7                            | Set Global: Next Bar    | Immediate    |
| 8                            | Set Global: End of Part | Immediate    |
| 9                            | Set Global: Instant     | Immediate    |
| **Navigation**               |                         |              |
| 10                           | Previous Part           | Global       |
| 11                           | Next Part               | Global       |
| 12                           | Previous Song           | Global       |
| 13                           | Next Song               | Global       |
| 14                           | First Song              | Global       |
| 15                           | Last Song               | Global       |
| **Actions**                  |                         |              |
| 16                           | Toggle Part Loop        | Immediate    |
| 17                           | Restart Part            | Global       |
| 18                           | Cancel Action           | Immediate    |
| 19                           | Toggle Mode             | Immediate    |
| 20                           | Restart Song            | Global       |

##### CC #1 (Global Part Jump)

- **Value N**: Go to global part index N across entire playlist (Global quantization)

##### CC #2 (Cue Jump)

- **Value N**: Go to Cue N (Dynamic quantization)

### Quantization Modes

| Mode            | Behavior                        |
| --------------- | ------------------------------- |
| **instant**     | Execute immediately             |
| **next_bar**    | Execute on next bar boundary    |
| **next_4**      | Execute on next 4-bar boundary  |
| **next_8**      | Execute on next 8-bar boundary  |
| **next_16**     | Execute on next 16-bar boundary |
| **next_32**     | Execute on next 32-bar boundary |
| **end_of_part** | Execute when current part ends  |

**Dynamic Quantization**: Only for cues. Repeatedly triggering the same cue progressively halves the quantization time (Next 8 → Next 4 → Next Bar).

## Dynamic Values Reference

Dynamic values are special strings that MIDItema replaces with live data when sending messages.

### Part Change Event

| Value                   | Type    | Description                              |
| ----------------------- | ------- | ---------------------------------------- |
| `part_index`            | integer | 0-based index of the new part            |
| `part_name`             | string  | Name of the new part                     |
| `part_bars`             | integer | Length of part in bars                   |
| `part_color`            | string  | Color name or hex value                  |
| `part_notes`            | string  | Notes text for the part                  |
| `part_cue`              | integer | Cue number (if assigned)                 |
| `part_index_in_setlist` | integer | Global part index across entire playlist |
| `song_index`            | integer | 0-based index of current song            |
| `song_name`             | string  | Name of current song                     |
| `song_color`            | string  | Color of current song                    |

### Song Change Event

| Value        | Description                   |
| ------------ | ----------------------------- |
| `song_index` | 0-based index of the new song |
| `song_name`  | Name of the new song          |
| `song_color` | Color of the new song         |

### Setlist End Event

| Value                 | Description                            |
| --------------------- | -------------------------------------- |
| `playlist_name`       | Name of the completed playlist         |
| `playlist_song_count` | Total number of songs                  |
| `playlist_part_count` | Total number of parts across all songs |

### Bar Triggers Event

| Value                | Description                                  |
| -------------------- | -------------------------------------------- |
| `completed_bar`      | Number of the completed bar (1-based)        |
| `block_number`       | Number of the block (for each_bar intervals) |
| `current_song_name`  | Name of current song                         |
| `current_part_name`  | Name of current part                         |
| `current_part_index` | Index of current part                        |

### Countdown Triggers Event

| Value                | Description                      |
| -------------------- | -------------------------------- |
| `remaining_beats`    | Beats remaining until transition |
| `remaining_bars`     | Bars remaining until transition  |
| `current_song_name`  | Name of current song             |
| `current_part_name`  | Name of current part             |
| `current_part_index` | Index of current part            |

### Usage Examples

```json
// Send part index as Program Change
{
    "device": "synth_A",
    "program": "part_index"
}

// Send multiple dynamic values via OSC
{
    "device": "visuals",
    "address": "/miditema/part_info",
    "args": ["part_name", "part_bars", "part_color"]
}

// Mix dynamic and static values
{
    "device": "display",
    "address": "/show/status",
    "args": ["Now Playing:", "song_name", "part_name", 1.0]
}
```

## Complete Examples

### Electronic Live Set Configuration

**miditema.conf.json:**

```json
{
    "devices": {
        "midi_in": {
            "clock": "Ableton Push 2",
            "midi_in": "APC40 mkII"
        },
        "midi_out": {
            "transport_out": "Ableton Live",
            "moog_bass": "Moog Sub 37",
            "nord_lead": "Nord Lead A1", 
            "drum_machine": "Arturia DrumBrute",
            "fx_send": "Eventide H9"
        },
        "osc_out": {
            "resolume": { "ip": "127.0.0.1", "port": 7000 },
            "lighting": { "ip": "192.168.1.50", "port": 8000 }
        }
    },

    "triggers": {
        "playback_start": [
            {
                "device": "resolume",
                "address": "/composition/time/reset"
            },
            {
                "device": "lighting",
                "address": "/show/start"
            }
        ],

        "part_change": [
            // Switch bass synth presets
            {
                "device": "moog_bass",
                "channel": 0,
                "program": "part_index"
            },
            // Switch lead synth presets  
            {
                "device": "nord_lead",
                "channel": 1,
                "program": "part_index"
            },
            // Trigger video clips in Resolume
            {
                "device": "resolume",
                "address": "/composition/layers/1/clips/trigger",
                "args": ["part_index"]
            },
            // Pre-load next visual 1 bar early
            {
                "device": "resolume",
                "address": "/composition/layers/2/clips/prepare",
                "args": ["part_name"],
                "bar": 1
            }
        ],

        "song_change": [
            // Reset FX unit between songs
            {
                "device": "fx_send",
                "channel": 0,
                "control": 127,
                "value": 0
            },
            // Update lighting scene
            {
                "device": "lighting",
                "address": "/scene/load",
                "args": ["song_index"]
            }
        ],

        "bar_triggers": [
            // Flash lights every 4 bars
            {
                "device": "lighting",
                "each_bar": 4,
                "address": "/effects/strobe/trigger",
                "args": ["block_number"]
            }
        ],

        "countdown_triggers": [
            // Countdown display on last 4 beats
            {
                "device": "resolume",
                "each_beat": 4,
                "address": "/ui/countdown",
                "args": ["remaining_beats"]
            }
        ],

        "setlist_end": [
            {
                "device": "lighting", 
                "address": "/show/finale"
            }
        ]
    }
}
```

**Song Example (electronic_anthem.json):**

```json
{
    "song_name": "Electronic Anthem",
    "color": "electric_blue",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        {
            "name": "Ambient Intro",
            "bars": 16,
            "color": "dark_gray",
            "notes": "Soft pad entry, no drums",
            "output": [
                {
                    "device": "moog_bass",
                    "control": 1,  // Modulation wheel
                    "value": 0     // Start with no modulation
                }
            ]
        },
        {
            "name": "Beat Drop",
            "bars": 8,
            "color": "bright_red",
            "cue": 1,
            "notes": "Kick and bass enter together",
            "output": [
                {
                    "device": "drum_machine",
                    "program": 1
                },
                {
                    "device": "moog_bass",
                    "program": 2
                }
            ]
        },
        {
            "name": "Main Groove A",
            "bars": 32,
            "color": "neon_green",
            "repeat_pattern": ["repeat", "next"],
            "notes": "First main section - can repeat",
            "output": {
                "device": "nord_lead",
                "program": 3
            }
        },
        {
            "name": "Breakdown",
            "bars": 16,
            "color": "yellow",
            "repeat_pattern": "repeat",
            "notes": "Manual breakdown - stays until jumped",
            "output": [
                {
                    "device": "drum_machine",
                    "program": 0  // Minimal drums
                },
                {
                    "device": "fx_send",
                    "control": 20,  // Reverb send
                    "value": 100
                }
            ]
        },
        {
            "name": "Main Groove B", 
            "bars": 32,
            "color": "hot_pink",
            "cue": 2,
            "repeat_pattern": ["repeat", "repeat", "next"],
            "notes": "Second main section - can repeat twice",
            "output": [
                {
                    "device": "drum_machine",
                    "program": 2  // Full drums
                },
                {
                    "device": "nord_lead",
                    "program": 5
                },
                {
                    "device": "fx_send",
                    "control": 20,
                    "value": 50   // Reduce reverb
                }
            ]
        },
        {
            "name": "Outro Build",
            "bars": 16,
            "color": "orange",
            "repeat_pattern": "next_song",
            "notes": "Build to next song",
            "output": {
                "device": "fx_send",
                "control": 21,  // Delay send
                "value": 127
            }
        }
    ]
}
```

### Band Setup Configuration

**band_setup.conf.json:**

```json
{
    "devices": {
        "midi_in": {
            "clock": "MOTU MIDI Timepiece",
            "midi_in": "FCB1010"
        },
        "midi_out": {
            "transport_out": "Pro Tools HDX",
            "guitar_rig": "Axe-FX III",
            "keyboard_rig": "Kronos",
            "backing_tracks": "MainStage",
            "monitor_mix": "X32"
        },
        "osc_out": {
            "lighting_desk": { "ip": "192.168.1.100", "port": 9000 },
            "video_server": { "ip": "192.168.1.101", "port": 8080 }
        }
    },

    "triggers": {
        "part_change": [
            // Switch guitar amp models
            {
                "device": "guitar_rig",
                "channel": 0,
                "program": "part_index"
            },
            // Change keyboard sounds
            {
                "device": "keyboard_rig", 
                "channel": 1,
                "program": "part_index"
            },
            // Trigger backing track regions
            {
                "device": "backing_tracks",
                "channel": 15,
                "program": "part_index"
            },
            // Update monitor mix snapshots
            {
                "device": "monitor_mix",
                "channel": 0,
                "program": "part_index"
            }
        ],

        "song_change": [
            // Load new lighting scene
            {
                "device": "lighting_desk",
                "address": "/scene/load",
                "args": ["song_index"]
            },
            // Display song info on video wall
            {
                "device": "video_server",
                "address": "/display/song_title",
                "args": ["song_name"]
            }
        ]
    }
}
```

**Band Song Example (rock_anthem.json):**

```json
{
    "song_name": "Rock Anthem",
    "color": "bright_red",
    "time_signature": "4/4",
    "parts": [
        {
            "name": "Acoustic Intro",
            "bars": 8,
            "color": "forest_green",
            "notes": "Clean guitar, soft vocals",
            "output": [
                {
                    "device": "guitar_rig",
                    "program": 0  // Clean tone
                },
                {
                    "device": "monitor_mix",
                    "program": 0  // Vocal-forward mix
                }
            ]
        },
        {
            "name": "Verse 1",
            "bars": 16,
            "color": "blue",
            "notes": "Add light distortion",
            "output": {
                "device": "guitar_rig",
                "program": 1  // Light crunch
            }
        },
        {
            "name": "Pre-Chorus",
            "bars": 8,
            "color": "yellow",
            "notes": "Build energy",
            "output": [
                {
                    "device": "guitar_rig",
                    "program": 2  // Medium drive
                },
                {
                    "device": "keyboard_rig",
                    "program": 1  // Add strings
                }
            ]
        },
        {
            "name": "Chorus",
            "bars": 16,
            "color": "bright_red",
            "cue": 1,
            "repeat_pattern": ["repeat", "next"],
            "notes": "Full band - can repeat chorus",
            "output": [
                {
                    "device": "guitar_rig",
                    "program": 3  // High gain lead
                },
                {
                    "device": "keyboard_rig", 
                    "program": 2  // Power chords
                },
                {
                    "device": "monitor_mix",
                    "program": 1  // Full band mix
                }
            ]
        },
        {
            "name": "Verse 2",
            "bars": 16,
            "color": "blue",
            "notes": "Back to verse feel",
            "output": [
                {
                    "device": "guitar_rig",
                    "program": 1  // Light crunch again
                },
                {
                    "device": "keyboard_rig",
                    "program": 0  // Basic piano
                }
            ]
        },
        {
            "name": "Bridge",
            "bars": 8,
            "color": "purple",
            "repeat_pattern": "repeat",
            "notes": "Breakdown section - manual",
            "output": {
                "device": "guitar_rig",
                "program": 4  // Clean with effects
            }
        },
        {
            "name": "Final Chorus",
            "bars": 16,
            "color": "hot_pink",
            "cue": 2,
            "repeat_pattern": ["repeat", "repeat", "next"],
            "notes": "Big finish - can extend",
            "output": [
                {
                    "device": "guitar_rig",
                    "program": 5  // Lead boost
                },
                {
                    "device": "keyboard_rig",
                    "program": 3  // Full strings
                }
            ]
        },
        {
            "name": "Outro",
            "bars": 8,
            "color": "dark_gray",
            "notes": "Fade to acoustic",
            "output": {
                "device": "guitar_rig", 
                "program": 0  // Back to clean
            }
        }
    ]
}
```

### Complex Playlist Example

**festival_set.json:**

```json
{
    "playlist_name": "Summer Festival 2024",
    "mode": "loop",

    // Override devices for this specific set
    "devices": {
        "midi_out": {
            "festival_lights": "GrandMA Console",
            "video_wall": "disguise Media Server"
        },
        "osc_out": {
            "festival_audio": { "ip": "192.168.2.100", "port": 7777 }
        }
    },

    // Playlist-specific triggers
    "triggers": {
        "song_change": [
            {
                "device": "festival_lights",
                "program": "song_index"
            },
            {
                "device": "video_wall",
                "address": "/media/load",
                "args": ["song_name", "song_color"]
            }
        ],

        "setlist_end": [
            {
                "device": "festival_audio",
                "address": "/show/complete"
            },
            {
                "device": "festival_lights",
                "program": 99  // Special finale program
            }
        ]
    },

    "songs": [
        // Opening track from external file
        {
            "filepath": "opener.json",
            "song_name": "Festival Opener",
            "color": "electric_blue"
        },

        // Embedded transition piece
        {
            "song_name": "Crowd Interaction",
            "color": "yellow",
            "time_signature": "4/4",
            "parts": [
                {
                    "name": "Talk Section",
                    "bars": 4,
                    "repeat_pattern": "repeat",
                    "notes": "Manual talk-to-crowd section",
                    "output": {
                        "device": "festival_audio",
                        "address": "/mic/talk_mode",
                        "args": [true]
                    }
                },
                {
                    "name": "Build Back In",
                    "bars": 8,
                    "repeat_pattern": "next_song",
                    "output": {
                        "device": "festival_audio", 
                        "address": "/mic/talk_mode",
                        "args": [false]
                    }
                }
            ]
        },

        // Main set pieces
        {
            "filepath": "electronic_anthem.json"
        },
        {
            "filepath": "dance_floor_killer.json"
        },

        // Embedded finale
        {
            "song_name": "Festival Finale",
            "color": "bright_red",
            "time_signature": "4/4",
            "parts": [
                {
                    "name": "Build Up",
                    "bars": 16,
                    "cue": 10,
                    "notes": "Big festival finish",
                    "output": [
                        {
                            "device": "festival_lights",
                            "program": 50
                        },
                        {
                            "device": "video_wall",
                            "address": "/effects/pyro_ready"
                        }
                    ]
                },
                {
                    "name": "DROP",
                    "bars": 32,
                    "color": "hot_pink",
                    "cue": 11,
                    "repeat_pattern": "repeat",
                    "notes": "THE BIG MOMENT",
                    "output": [
                        {
                            "device": "festival_lights",
                            "program": 51
                        },
                        {
                            "device": "video_wall",
                            "address": "/effects/pyro_fire"
                        }
                    ]
                },
                {
                    "name": "Thank You",
                    "bars": 8,
                    "color": "white",
                    "notes": "Crowd appreciation",
                    "output": {
                        "device": "festival_lights",
                        "program": 52
                    }
                }
            ]
        }
    ]
}
```

### Advanced Repeat Pattern Examples

**Complex Flow Control:**

```json
{
    "name": "Verse",
    "bars": 16,
    // First time: next, Second time: repeat, Third time: jump to bridge
    "repeat_pattern": ["next", "repeat", {"jump_to_cue": 5}]
}

{
    "name": "Chorus", 
    "bars": 16,
    // Randomly jump to one of three different bridge sections
    "repeat_pattern": [{"random_part": [3, 5, 7]}]
}

{
    "name": "Interactive Section",
    "bars": 8,
    // Mix of different behaviors on each pass
    "repeat_pattern": [
        "repeat",           // First: repeat
        "repeat",           // Second: repeat again  
        {"jump_to_part": 0}, // Third: jump to beginning
        "next_song"         // Fourth: go to next song
    ]
}

{
    "name": "Flexible Outro",
    "bars": 4,
    // Enable manual part loop for extended jams
    "repeat_pattern": "loop_part"
}
```