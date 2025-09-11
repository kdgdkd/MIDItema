# MIDItema Configuration Reference

Complete technical reference for configuring MIDItema files, including device setup, trigger system, song structures, and playlists.

## Table of Contents

1. [Quick Start - Minimal Examples](#quick-start---minimal-examples)
2. [File Types Overview](#file-types-overview)
3. [Main Configuration File](#main-configuration-file)
4. [Song Files](#song-files)
5. [Playlist Files](#playlist-files)
6. [Trigger System Reference](#trigger-system-reference)
7. [Control Message Reference](#control-message-reference)
8. [Dynamic Values Reference](#dynamic-values-reference)
9. [Command Line Options](#command-line-options)
10. [File Organization](#file-organization)
11. [Complete Examples](#complete-examples)

## Quick Start - Minimal Examples

### Absolute Minimum (3 lines)

```json
{"parts":[{"name":"Loop","bars":16}]}
```

This is a valid MIDItema file! It creates one 16-bar part that advances to the end.

### Simple Loop (4 lines)

```json
{
  "parts": [
    {"name": "Loop", "bars": 16, "repeat_pattern": "repeat"}
  ]
}
```

This creates a 16-bar loop that repeats indefinitely.

### Two Parts with Auto-advance

```json
{
  "song_name": "My Track",
  "parts": [
    {"name": "Intro", "bars": 8},
    {"name": "Main", "bars": 16}
  ]
}
```

Plays intro once, then main once, then stops.

### Loop the Second Part

```json
{
  "parts": [
    {"name": "Intro", "bars": 8},
    {"name": "Main", "bars": 16, "repeat_pattern": "repeat"}
  ]
}
```

Plays intro once, then loops main forever.

### With MIDI Automation

```json
{
  "devices": {
    "midi_out": {"synth": "MicroKorg"}
  },
  "parts": [
    {
      "name": "A", 
      "bars": 16, 
      "output": {"device": "synth", "channel": 0, "program": 0}
    },
    {
      "name": "B", 
      "bars": 16, 
      "output": {"device": "synth", "program": 1}  // channel inherited
    }
  ]
}
```

## File Types Overview

MIDItema uses JSON5 format (JSON with comments) for all configuration files:

| File Type             | Extension             | Location           | Purpose                                  |
| --------------------- | --------------------- | ------------------ | ---------------------------------------- |
| Main Config           | `miditema.conf.json`  | Root directory     | Default device setup and global triggers |
| Song Files            | `*.json` or `*.json5` | `temas/` directory | Individual song structures               |
| Playlist Files        | `*.json` or `*.json5` | `temas/` directory | Collections of songs                     |
| Directory as Playlist | Directory name        | `temas/` directory | All JSON files become a playlist         |

### File Loading Priority

1. **No file specified**: Opens file browser in `temas/`
2. **Filename only**: Searches in `temas/` directory
3. **Path specified**: Uses exact path
4. **Directory with `/`**: Loads as playlist

## Main Configuration File

The main configuration file is **optional**. Without it, you can:

- Select MIDI devices through the UI
- Define devices in song/playlist files
- Use a different config with `--conf`

### Basic Structure

```json5
{
    "devices": {
        "midi_in": { /* Input ports */ },
        "midi_out": { /* Output ports */ },
        "osc_out": { /* OSC destinations */ }
    },
    "triggers": {
        "event_name": [ /* Action list */ ]
    }
}
```

### Devices Section

#### MIDI Input Ports

```json5
"midi_in": {
    "clock": "E-RM Multiclock",        // Required: MIDI clock source
    "midi_in": "MIDItema Controller"   // Optional: Control input
}
```

**Port Matching Rules**:

- Case-insensitive substring matching
- First matching port is selected
- Example: `"multiclock"` matches `"E-RM Multiclock MIDI 1"`

**Shared Port Configuration**:

```json5
"midi_in": {
    "clock": "Push 2",      // Both clock and control
    "midi_in": "Push 2"     // from same device
}
```

#### MIDI Output Ports

```json5
"midi_out": {
    "transport_out": "Ableton Live",   // Special: Auto-relay transport
    "synth_A": "Moog Minitaur",        // Custom alias
    "synth_B": "Roland JP-08",         // Custom alias
    "drums": "TR-8S",                  // Custom alias
    "lights": "MIDI2DMX"               // Custom alias
}
```

**Special Aliases**:

- `transport_out`: Automatically forwards Start/Stop/Continue messages

**Alias Naming**:

- Any valid JSON key name
- Avoid spaces (use underscores)
- Case-sensitive when referenced

#### OSC Output Destinations

```json5
"osc_out": {
    "resolume": { 
        "ip": "127.0.0.1",    // Required: IP address
        "port": 7000          // Required: Port number
    },
    "touchdesigner": { 
        "ip": "192.168.1.100", 
        "port": 8000 
    }
}
```

### Device Configuration Merging

When multiple files define devices:

1. **Main config loads first** (if exists)
2. **Song/playlist devices merge**: 
   - New aliases are added
   - Duplicate aliases override
   - Existing aliases remain

Example:

```json5
// miditema.conf.json
{"devices": {"midi_out": {"synth": "Minilogue"}}}

// song.json  
{"devices": {"midi_out": {"synth": "MicroKorg", "drums": "TR-8"}}}

// Result: synth → MicroKorg, drums → TR-8
```

## Song Files

### Complete Song Structure

```json5
{
    "song_name": "My Song",         // Optional: Display name
    "color": "blue",                // Optional: Title bar color
    "time_signature": "4/4",        // Optional: Meter (default: 4/4)
    "time_division": "1/4",         // Optional: Beat division (default: 1/4)
    "devices": { /* Optional */ },  // Optional: Device overrides
    "triggers": { /* Optional */ },  // Optional: Song triggers
    "parts": [                      // Required: At least one part
        {
            "name": "Part Name",     // Required: Display name
            "bars": 16,              // Required: Length (1-999)
            "color": "green",        // Optional: Part color
            "notes": "Add reverb",   // Optional: Display notes
            "cue": 5,                // Optional: Cue number (1-127)
            "repeat_pattern": false, // Optional: End behavior
            "output": []             // Optional: Local triggers
        }
    ]
}
```

### Root-Level Parameters

#### song_name

- **Type**: string
- **Default**: Filename without extension
- **Example**: `"Digital Dreams"`
- **Usage**: Displayed in UI title bar

#### color

- **Type**: string (color name or hex)
- **Default**: none (uses UI default)
- **Examples**: `"blue"`, `"#FF5733"`
- **Available Colors**: 
  - Basic: `default`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
  - Extended: `orange`, `ruby_pink`, `indigo_blue`, `purple`, `forest_green`, `ivory`
  - Neon: `bright_red`, `neon_green`, `electric_blue`, `bright_yellow`, `hot_pink`, `electric_cyan`, `electric_orange`
  - Grays: `dark_gray`, `mid_gray`, `light_gray`

#### time_signature

- **Type**: string
- **Default**: `"4/4"`
- **Format**: `"numerator/denominator"`
- **Examples**: `"3/4"`, `"7/8"`, `"5/4"`
- **Note**: Only numerator affects beat counting

#### time_division

- **Type**: string
- **Default**: `"1/4"`
- **Purpose**: Defines what constitutes a "beat"
- **Values**:
  - `"1/4"`: Quarter note = 24 MIDI clock ticks (default)
  - `"1/8"`: Eighth note = 12 MIDI clock ticks  
  - `"1/16"`: Sixteenth note = 6 MIDI clock ticks

### Parts Array

#### Required Part Parameters

```json5
{
    "name": "Verse 1",    // Any string
    "bars": 16            // Integer 1-999
}
```

#### Optional Part Parameters

##### color

- **Type**: string
- **Default**: Inherits from song or uses default
- **Purpose**: Visual identification in UI
- **Example**: `"color": "hot_pink"`

##### notes

- **Type**: string  
- **Default**: `""`
- **Purpose**: Reminder text shown below part name
- **Example**: `"notes": "Guitar solo - watch dynamics"`

##### cue

- **Type**: integer (1-127)
- **Default**: none
- **Purpose**: Direct access point via F-keys or MIDI
- **Access Methods**:
  - Keyboard: F1-F12 for cues 1-12
  - MIDI: CC#2 with value 1-127
- **Example**: `"cue": 5` (accessible via F5)

##### repeat_pattern

- **Type**: boolean, string, array, or object
- **Default**: `false` (advance to next part)
- **Purpose**: Controls flow when part ends

**Simple Patterns (Boolean/String)**:

```json5
// Boolean forms
"repeat_pattern": true        // Loop this part
"repeat_pattern": false       // Go to next part (default)

// String booleans (converted internally)
"repeat_pattern": "true"      // Converted to true
"repeat_pattern": "false"     // Converted to false

// Navigation strings
"repeat_pattern": "repeat"    // Loop this part
"repeat_pattern": "next"      // Next part (same as false)
"repeat_pattern": "prev"      // Previous part
"repeat_pattern": "first_part"   // Jump to part 0
"repeat_pattern": "last_part"    // Jump to last part

// Playlist navigation (requires active playlist)
"repeat_pattern": "next_song"    // Load next song
"repeat_pattern": "prev_song"    // Load previous song
"repeat_pattern": "first_song"   // Jump to first song
"repeat_pattern": "last_song"    // Jump to last song

// Mode changes
"repeat_pattern": "song_mode"    // Enable Song Mode, then next
"repeat_pattern": "loop_mode"    // Enable Loop Mode, then next
"repeat_pattern": "loop_part"    // Activate manual part loop
```

**Array Patterns (Loop Mode only)**:

Arrays define different behaviors for each pass through the song:

```json5
// Different each time
"repeat_pattern": [true, false, true]  
// Pass 1: play, Pass 2: skip, Pass 3: play, Pass 4: play...

// Complex sequence
"repeat_pattern": [
    "next",                  // Pass 1: continue
    "repeat",                // Pass 2: repeat this part
    {"jump_to_part": 0},     // Pass 3: back to start
    "next_song"              // Pass 4: next song
]
```

**Jump Objects**:

```json5
{"jump_to_part": 3}        // Jump to part index 3 (0-based)
{"jump_to_cue": 12}        // Find part with cue: 12
{"random_part": [2, 4, 6]} // Random choice (limited support)
```

##### output

- **Type**: object or array of objects
- **Default**: none
- **Purpose**: Local triggers when part starts
- **Note**: Executes AFTER global `part_change` triggers

```json5
// Single action
"output": {
    "device": "synth_lead",
    "channel": 0,
    "program": 5
}

// Multiple actions with inheritance
"output": [
    {"device": "synth_lead", "channel": 0, "program": 5},
    {"control": 74, "value": 100},  // Inherits device & channel
    {"device": "drums", "channel": 9, "program": 1},
    {"note": 36}  // Inherits drums & channel 9
]
```

## Playlist Files

### Complete Playlist Structure

```json5
{
    "playlist_name": "Festival Set",    // Optional: Display name
    "mode": "loop",                     // Optional: Playback mode
    "devices": { /* Optional */ },      // Optional: Device config
    "triggers": { /* Optional */ },     // Optional: Global triggers
    "songs": [                          // Required: Song list
        {
            "filepath": "song1.json",    // Reference to file
            "song_name": "Override",     // Optional override
            "color": "blue"              // Optional override
        },
        {
            "song_name": "Embedded",     // Embedded song
            "parts": [/* parts */]       // Complete definition
        }
    ]
}
```

### Playlist Parameters

#### playlist_name

- **Type**: string
- **Default**: Filename or directory name
- **Example**: `"Summer Tour 2024"`

#### mode

- **Type**: string
- **Default**: `"loop"`
- **Values**:
  - `"loop"`: Respects all repeat_pattern settings (Loop Mode)
  - `"song"`: Forces linear progression (Song Mode)
- **Effect**: Can be toggled live with 'M' key

### Songs Array

#### File Reference

References external song files:

```json5
{
    "filepath": "opener.json"      // Minimum: just the file
}

// With overrides
{
    "filepath": "opener.json",
    "song_name": "Set Opener",     // Override file's name
    "color": "bright_red"          // Override file's color
}
```

#### Embedded Song

Complete song definition within playlist:

```json5
{
    "song_name": "Quick Transition",
    "color": "dark_gray",
    "time_signature": "4/4",
    "parts": [
        {
            "name": "Ambient Bridge",
            "bars": 8,
            "repeat_pattern": "next_song"
        }
    ]
}
```

### Directory as Playlist

Load a directory as a playlist:

```bash
python miditema.py my_set/
```

This creates a playlist with:

- **Name**: Directory name
- **Songs**: All `.json` and `.json5` files in alphabetical order
- **Mode**: Default "loop"

## Trigger System Reference

### Trigger Concepts

Triggers are automated actions that fire when events occur. They consist of:

1. **Event**: When to fire (part_change, song_change, etc.)
2. **Actions**: What to send (MIDI, OSC messages)
3. **Timing**: When exactly (immediate or delayed)

### Basic Trigger Structure

```json5
"triggers": {
    "event_name": [
        {
            "device": "alias",       // Can be inherited
            // Action parameters
            "bar": 1,                // Optional: bars early
            "beats": 4               // Optional: beats early
        }
    ]
}
```

### Available Events

#### Transport Events

Fire on playback state changes:

| Event                    | When Fired              | Typical Use                  |
| ------------------------ | ----------------------- | ---------------------------- |
| `playback_start`         | Start button/message    | Reset sequences, initialize  |
| `playback_stop`          | Stop button/message     | Stop sequences, reset states |
| `playback_continue`      | Continue button/message | Resume from pause            |
| `playback_initial_start` | First start only        | One-time initialization      |

Example:

```json5
"playback_start": [
    {"device": "sequencer", "type": "start"},
    {"device": "lights", "address": "/reset"}
]
```

#### Structure Events

Fire on song structure changes:

| Event         | When Fired         | Available Context |
| ------------- | ------------------ | ----------------- |
| `part_change` | New part begins    | Part & song info  |
| `song_change` | New song loads     | Song info         |
| `setlist_end` | Playlist completes | Playlist stats    |

Example:

```json5
"part_change": [
    {
        "device": "synth",
        "channel": 0,
        "program": "part_index"    // Dynamic value
    }
]
```

#### Rhythmic Events

Fire at regular intervals:

##### bar_triggers

```json5
"bar_triggers": [
    {
        "device": "lights",
        "each_bar": 4,              // Every 4 bars
        "control": 10,
        "value": "block_number"     // 1, 2, 3...
    },
    {
        "device": "fx",
        "each_bar": 8,              // Every 8 bars
        "program": "completed_bar"  // Actual bar number
    }
]
```

##### countdown_triggers

```json5
"countdown_triggers": [
    {
        "device": "display",
        "each_beat": 8,             // Last 8 beats before change
        "address": "/countdown",
        "args": ["remaining_beats"] // 8, 7, 6, 5, 4, 3, 2, 1
    },
    {
        "device": "lights",
        "each_beat": 4,             // Last 4 beats only
        "control": 20,
        "value": "remaining_bars"   // Bars left (rounded up)
    }
]
```

### Action Object Types

#### MIDI Actions

##### Type Inference System

MIDItema automatically infers message type from parameters:

| If Present | Inferred Type    | Default Values |
| ---------- | ---------------- | -------------- |
| `note`     | `note_on`        | velocity: 127  |
| `control`  | `control_change` | value: 127     |
| `program`  | `program_change` | -              |
| `song`     | `song_select`    | -              |

##### Program Change

```json5
// Explicit type
{
    "device": "synth",
    "type": "program_change",
    "channel": 0,
    "program": 5
}

// Inferred (recommended)
{
    "device": "synth",
    "channel": 0,
    "program": 5              // Type auto-detected
}

// With dynamic value
{
    "device": "synth",
    "channel": 0,
    "program": "part_index"   // 0, 1, 2...
}

// Implicit program value
{
    "device": "synth",
    "type": "program_change",
    "channel": 0
    // program defaults to part_index
}
```

##### Control Change

```json5
// Full specification
{
    "device": "fx",
    "type": "control_change",
    "channel": 1,
    "control": 74,           // Filter cutoff
    "value": 64
}

// Inferred with default
{
    "device": "fx",
    "channel": 1,
    "control": 74            // value defaults to 127
}

// Multiple controls using inheritance
[
    {"device": "fx", "channel": 1, "control": 74, "value": 100},
    {"control": 71, "value": 60},    // Same device & channel
    {"control": 91, "value": 127}    // Still same device & channel
]
```

##### Note Messages

```json5
// Note On - Full
{
    "device": "drums",
    "type": "note_on",
    "channel": 9,
    "note": 36,              // Kick drum
    "velocity": 100
}

// Note On - Inferred with default
{
    "device": "drums",
    "channel": 9,
    "note": 36               // velocity defaults to 127
}

// Note Off (must be explicit)
{
    "device": "drums",
    "type": "note_off",      // Required for note_off
    "channel": 9,
    "note": 36,
    "velocity": 0
}
```

##### Song Select

```json5
// Explicit
{
    "device": "sequencer",
    "type": "song_select",
    "song": 3
}

// Inferred
{
    "device": "sequencer",
    "song": 3
}

// Implicit song value
{
    "device": "sequencer",
    "type": "song_select"
    // song defaults to song_index
}
```

#### OSC Actions

```json5
// Basic OSC message
{
    "device": "visuals",
    "address": "/composition/layer/1/clip",
    "args": [5]
}

// With multiple arguments
{
    "device": "lights",
    "address": "/scene/fade",
    "args": [1, "smooth", 2.5, true]
}

// With dynamic values
{
    "device": "display",
    "address": "/song/info",
    "args": ["song_name", "part_name", "part_bars"]
}

// Mixed static and dynamic
{
    "device": "controller",
    "address": "/status",
    "args": ["Now Playing:", "song_name", 1.0, true]
}
```

### Device Inheritance

**Critical feature**: The `device` parameter inherits from previous actions:

```json5
"part_change": [
    {
        "device": "synth_A",    // Set device
        "channel": 0,           // Set channel
        "program": 0
    },
    {
        // Inherits: device: "synth_A", channel: 0
        "control": 74,
        "value": 100
    },
    {
        // Still inherits both
        "control": 71,
        "value": 60
    },
    {
        "device": "synth_B",    // New device
        "channel": 1,           // New channel
        "program": 0
    },
    {
        // Now inherits: device: "synth_B", channel: 1
        "control": 74,
        "value": 127
    }
]
```

**Rules**:

1. Device persists until explicitly changed
2. Channel persists independently 
3. Inheritance works across all actions in an event
4. OSC actions don't participate in inheritance

### Delayed Triggers (Advanced Timing)

Fire triggers BEFORE the actual event:

```json5
// One bar early
{
    "device": "visuals",
    "bar": 1,
    "address": "/prepare/next"
}

// Four beats early
{
    "device": "lights",
    "beats": 4,
    "program": "part_index"
}

// Two bars early (8 beats in 4/4)
{
    "device": "fx",
    "bar": 2,
    "control": 90,
    "value": 127
}
```

**Use Cases**:

- Prepare visuals before part change
- Fade effects before transitions
- Cue lighting changes
- Trigger samples with lead time

### Output Initialization

When starting a performance, devices need to be configured with the correct initial settings. However, advanced timing can create synchronization issues at startup that MIDItema's initialization feature solves.

#### The Advanced Timing Problem

When a playlist defines advanced message sending (e.g., `"beats": 2`), these messages are normally sent before part changes during playback. However, at the very start of a performance, there is no "previous part" to send messages in advance from.

**Without initialization**: Advanced messages for the first part are sent at the first beat of playback, potentially causing timing issues or conflicts with master clock synchronization.

**Example problem**:
```json5
{
  "beats": 2,  // Send 2 beats early
  "songs": [
    {
      "parts": [
        {
          "name": "Intro",
          "output": {"device": "synth", "program": 5}
        }
      ]
    }
  ]
}
```

At startup → Program change sent on beat 1 (not 2 beats early) → Potential sync issues

#### Solution: Manual Initialization

MIDItema allows pre-sending the first part's outputs before starting the master clock:

1. **Load your playlist** in MIDItema
2. **Press Enter** - Immediately sends the `output` messages from the first part
3. **Start your master clock** - These outputs will NOT be sent again, avoiding duplication

#### Behavior Details

**Initialization sequence**:
1. Enter pressed → First part outputs sent immediately (bypasses advanced timing)
2. Master clock START received → First part outputs skipped (already sent)
3. Subsequent part changes → Normal advanced timing behavior resumes

**Integration with advanced timing**:
- Initialization bypasses `beats` and `bar` delays for the first part only
- All subsequent part changes during playback respect the configured advanced timing
- Advanced timing settings continue to work normally for all other parts

#### Output Control Integration

- Initialization respects the global output enable/disable setting
- If outputs are disabled (`--no-output` or 'o' key), initialization is skipped
- Toggle outputs during performance affects all subsequent messages but not initialization

#### Typical Workflow with Advanced Timing

```bash
# Playlist configured with "beats": 2
python miditema.py advanced_set.json

# Press Enter → First part outputs sent immediately
# Start master clock → Perfect synchronization from beat 1
# Part changes → Sent 2 beats early as configured
```

This ensures devices start in the correct state while maintaining perfect timing synchronization throughout the performance.

## Control Message Reference

### Keyboard Controls

#### Transport Controls

| Key     | Action        | Notes                             |
| ------- | ------------- | --------------------------------- |
| `Enter` | Start/Stop    | Toggles between Start and Stop    |
| `Space` | Continue/Stop | Toggles between Continue and Stop |

#### Navigation Controls

| Key        | Action        | Quantization | Requirements         |
| ---------- | ------------- | ------------ | -------------------- |
| `←`        | Previous Part | Global       | -                    |
| `→`        | Next Part     | Global       | -                    |
| `PageUp`   | Previous Song | Global       | Playlist active      |
| `PageDown` | Next Song     | Global       | Playlist active      |
| `Home`     | First Song    | Global       | Playlist active      |
| `End`      | Last Song     | Global       | Playlist active      |
| `.` or `,` | Go to Part... | Global       | Enter number + Enter |

#### Action Controls

| Key | Action           | Effect                                                |
| --- | ---------------- | ----------------------------------------------------- |
| `↓` | Cancel/Reset     | Cancel pending action OR reset to song 1 when stopped |
| `↑` | Toggle Part Loop | Manual loop on current part                           |
| `m` | Toggle Mode      | Switch between Loop/Song Mode                         |
| `o` | Toggle Outputs   | Enable/disable MIDI and OSC output sending           |
| `v` | View Parts       | Open parts list window                                |
| `q` | Quit             | Exit application                                      |

#### Cue Keys

| Key        | Cue Number | Quantization                  |
| ---------- | ---------- | ----------------------------- |
| `F1`-`F12` | 1-12       | Dynamic (speeds up on repeat) |

#### Quick Jump Keys

| Key | Action    | Fixed Quantization |
| --- | --------- | ------------------ |
| `0` | Next Part | Next Bar           |
| `1` | Next Part | Next 4 Bars        |
| `2` | Next Part | Next 8 Bars        |
| `3` | Next Part | Next 16 Bars       |

#### Set Global Quantization

| Key | Sets Mode To | Description       |
| --- | ------------ | ----------------- |
| `4` | Next 4       | 4-bar boundaries  |
| `5` | Next 8       | 8-bar boundaries  |
| `6` | Next 16      | 16-bar boundaries |
| `7` | Next Bar     | Every bar         |
| `8` | End of Part  | Part end          |
| `9` | Instant      | Immediate         |

### MIDI Control

#### Note Messages

| Note | Action        | Quantization |
| ---- | ------------- | ------------ |
| 124  | Previous Part | Global       |
| 125  | Next Part     | Global       |
| 126  | Previous Song | Global       |
| 127  | Next Song     | Global       |

#### Program Change

- **Values 0-127**: Jump to part by index (0-based)
- Uses global quantization

#### Song Select

- **Values 0-127**: Jump to song by index (0-based)
- Uses global quantization
- Requires active playlist

#### Control Change #0 (Main Control)

| Value Range | Function            | Type                |
| ----------- | ------------------- | ------------------- |
| **0-3**     | Quick Jumps         | Fixed quantization  |
| **4-9**     | Set Global Quantize | Mode change         |
| **10-15**   | Navigation          | Global quantization |
| **16-20**   | Actions             | Various             |

**Detailed CC#0 Map**:

| Value | Action                | Quantization |
| ----- | --------------------- | ------------ |
| 0     | Next Part             | Instant      |
| 1     | Next Part             | Next Bar     |
| 2     | Next Part             | Next 8       |
| 3     | Next Part             | Next 16      |
| 4     | Set Mode: Next 4      | -            |
| 5     | Set Mode: Next 8      | -            |
| 6     | Set Mode: Next 16     | -            |
| 7     | Set Mode: Next Bar    | -            |
| 8     | Set Mode: End of Part | -            |
| 9     | Set Mode: Instant     | -            |
| 10    | Previous Part         | Global       |
| 11    | Next Part             | Global       |
| 12    | Previous Song         | Global       |
| 13    | Next Song             | Global       |
| 14    | First Song            | Global       |
| 15    | Last Song             | Global       |
| 16    | Toggle Part Loop      | Immediate    |
| 17    | Restart Part          | Global       |
| 18    | Cancel Action         | Immediate    |
| 19    | Toggle Mode           | Immediate    |
| 20    | Restart Song          | Global       |

#### Control Change #1 (Global Part Jump)

- **Purpose**: Jump to any part across entire playlist
- **Value**: Global part index (0-based)
- **Example**: Value 10 = 11th part overall
- **Requires**: Active playlist

#### Control Change #2 (Cue Jump)

- **Purpose**: Jump to cue number
- **Values**: 1-127 (cue numbers)
- **Quantization**: Dynamic (speeds up on repeat)
- **Scope**: Searches entire playlist

### Quantization Modes

| Mode          | Timing            | Use Case           |
| ------------- | ----------------- | ------------------ |
| `instant`     | Immediate         | Emergency jumps    |
| `next_bar`    | Next bar line     | Quick transitions  |
| `next_4`      | Next 4-bar block  | Phrase boundaries  |
| `next_8`      | Next 8-bar block  | Section boundaries |
| `next_16`     | Next 16-bar block | Major sections     |
| `next_32`     | Next 32-bar block | Long sections      |
| `end_of_part` | When part ends    | Natural flow       |

**Dynamic Quantization** (Cues only):

- First press: Uses global quantization
- Second press: Halves the time (32→16→8→4→bar)
- Third+ press: Continues halving until bar

## Dynamic Values Reference

Dynamic values are placeholders replaced with real-time data when triggers fire.

### Universal Dynamic Values

Available in most trigger contexts:

| Value        | Type   | Description            | Example    |
| ------------ | ------ | ---------------------- | ---------- |
| `song_index` | int    | Current song (0-based) | 0, 1, 2... |
| `song_name`  | string | Song name or filename  | "My Track" |
| `song_color` | string | Song color             | "blue"     |

### Event-Specific Values

#### part_change Event

| Value                   | Type     | Description          | Example      |
| ----------------------- | -------- | -------------------- | ------------ |
| `part_index`            | int      | Part index (0-based) | 0, 1, 2...   |
| `part_name`             | string   | Part name            | "Verse 1"    |
| `part_bars`             | int      | Part length          | 16           |
| `part_color`            | string   | Part color           | "#FF5733"    |
| `part_notes`            | string   | Part notes           | "Add reverb" |
| `part_cue`              | int/null | Cue number           | 5            |
| `part_index_in_setlist` | int      | Global index         | 0-n          |

#### song_change Event

| Value        | Type   | Description    |
| ------------ | ------ | -------------- |
| `song_index` | int    | New song index |
| `song_name`  | string | New song name  |
| `song_color` | string | New song color |

#### setlist_end Event

| Value                 | Type   | Description   |
| --------------------- | ------ | ------------- |
| `playlist_name`       | string | Playlist name |
| `playlist_song_count` | int    | Total songs   |
| `playlist_part_count` | int    | Total parts   |

#### bar_triggers

| Value                | Type   | Description                  |
| -------------------- | ------ | ---------------------------- |
| `completed_bar`      | int    | Bar just completed (1-based) |
| `block_number`       | int    | Which block (for each_bar)   |
| `current_song_name`  | string | Active song                  |
| `current_part_name`  | string | Active part                  |
| `current_part_index` | int    | Active part index            |

#### countdown_triggers

| Value                | Type   | Description                |
| -------------------- | ------ | -------------------------- |
| `remaining_beats`    | int    | Beats until event          |
| `remaining_bars`     | int    | Bars until event (ceiling) |
| `current_song_name`  | string | Active song                |
| `current_part_name`  | string | Active part                |
| `current_part_index` | int    | Active part index          |

### Implicit Dynamic Values

Some values are automatically used when parameters are omitted:

```json5
// program_change without program
{
    "device": "synth",
    "type": "program_change",
    "channel": 0
    // program = part_index (automatic)
}

// song_select without song
{
    "device": "sequencer",
    "type": "song_select"
    // song = song_index (automatic)
}
```

## Command Line Options

### Basic Usage

```bash
python miditema.py [options] [file_or_directory]
```

### Arguments

| Argument   | Description        | Example                                |
| ---------- | ------------------ | -------------------------------------- |
| (none)     | Opens file browser | `python miditema.py`                   |
| filename   | Load from temas/   | `python miditema.py song.json`         |
| path/file  | Load exact path    | `python miditema.py ../sets/live.json` |
| directory/ | Load as playlist   | `python miditema.py setlist/`          |

### Options

| Option         | Description          | Example                   |
| -------------- | -------------------- | ------------------------- |
| `--conf FILE`  | Use alternate config | `--conf live.conf.json`   |
| `--quant MODE` | Initial quantization | `--quant 8`               |
| `--song-mode`  | Start in Song Mode   | Forces linear progression |
| `--loop-mode`  | Start in Loop Mode   | Respects repeat_pattern   |
| `--no-output`  | Start with outputs disabled | Disables MIDI/OSC output sending |
| `--debug`      | Console debug mode   | No UI, terminal output    |

### Quantization Values for --quant

| Value     | Result       |
| --------- | ------------ |
| `bar`     | Next bar     |
| `4`       | Next 4 bars  |
| `8`       | Next 8 bars  |
| `16`      | Next 16 bars |
| `32`      | Next 32 bars |
| `instant` | Immediate    |

### Usage Examples

```bash
# Basic usage - opens file browser
python miditema.py

# Load specific song
python miditema.py my_track.json

# Load with custom config
python miditema.py --conf studio.conf.json live_set.json

# Load directory as playlist in Song Mode
python miditema.py --song-mode festival_set/

# Debug mode with instant quantization
python miditema.py --debug --quant instant test.json

# Start with outputs disabled for setup
python miditema.py --no-output sound_check.json

# Complete live setup
python miditema.py --conf venue.conf.json --quant 8 --loop-mode setlist/
```

## File Organization

### Default Directory Structure

```
miditema/
├── miditema.py              # Main program
├── tui.py                   # Terminal UI
├── schema_validator.py      # JSON validation
├── miditema.conf.json       # Optional main config
├── requirements.txt         # Python dependencies
└── temas/                   # Default content directory
    ├── song1.json
    ├── song2.json
    ├── live_set.json        # Playlist file
    └── festival/            # Directory as playlist
        ├── opener.json
        ├── main_set.json
        └── encore.json
```

### File Search Order

1. **Exact path**: Uses provided path as-is
2. **Filename only**: Searches in `temas/` directory
3. **No extension**: Tries `.json` then `.json5`
4. **Directory**: All JSON files become playlist

### Config File Priority

1. Command line `--conf` option (highest)
2. `miditema.conf.json` in root
3. Devices in song/playlist files
4. UI device selection (lowest)

## Complete Examples

### Minimal Working Examples

#### 1. Simplest Loop (5 lines)

```json
{
  "parts": [
    {"name": "Loop", "bars": 16, "repeat_pattern": "repeat"}
  ]
}
```

#### 2. A/B Structure

```json
{
  "parts": [
    {"name": "A", "bars": 8},
    {"name": "B", "bars": 8, "repeat_pattern": "repeat"}
  ]
}
```

#### 3. With Program Changes

```json
{
  "devices": {"midi_out": {"synth": "Minilogue"}},
  "parts": [
    {"name": "A", "bars": 16, "output": {"device": "synth", "channel": 0, "program": 0}},
    {"name": "B", "bars": 16, "output": {"program": 1}}  // inherits device & channel
  ]
}
```

### Electronic Live Performance

#### Main Config (electronic_live.conf.json)

```json5
{
  "devices": {
    "midi_in": {
      "clock": "Ableton Push 2",
      "midi_in": "APC40 mkII"
    },
    "midi_out": {
      "transport_out": "Ableton Live",
      "bass": "Moog Sub 37",
      "lead": "Nord Lead A1",
      "drums": "TR-8S",
      "fx": "Eventide H9"
    },
    "osc_out": {
      "resolume": {"ip": "127.0.0.1", "port": 7000},
      "lights": {"ip": "192.168.1.100", "port": 8000}
    }
  },

  "triggers": {
    "playback_start": [
      {"device": "resolume", "address": "/composition/time/reset"},
      {"device": "lights", "address": "/blackout/off"}
    ],

    "part_change": [
      // Switch all synth patches
      {"device": "bass", "channel": 0, "program": "part_index"},
      {"device": "lead", "channel": 1, "program": "part_index"},

      // Trigger Resolume clips
      {"device": "resolume", "address": "/layer/1/clip", "args": ["part_index"]},

      // Prepare next visual 1 bar early
      {"device": "resolume", "bar": 1, "address": "/layer/2/prepare", "args": ["part_index"]}
    ],

    "bar_triggers": [
      // Flash every 4 bars
      {"device": "lights", "each_bar": 4, "address": "/strobe", "args": ["block_number"]}
    ],

    "countdown_triggers": [
      // Visual countdown last 4 beats
      {"device": "resolume", "each_beat": 4, "address": "/countdown", "args": ["remaining_beats"]}
    ]
  }
}
```

#### Track File (acid_techno.json)

```json5
{
  "song_name": "Acid Dreams",
  "color": "neon_green",
  "time_signature": "4/4",

  "parts": [
    {
      "name": "Intro",
      "bars": 32,
      "color": "dark_gray",
      "notes": "No kick, just atmosphere",
      "output": [
        {"device": "bass", "control": 74, "value": 20},  // Filter closed
        {"device": "fx", "control": 20, "value": 127}    // Max reverb
      ]
    },
    {
      "name": "Build",
      "bars": 16,
      "color": "yellow",
      "output": [
        {"device": "drums", "program": 1},  // Kick pattern
        {"device": "bass", "control": 74, "value": 60}  // Open filter
      ]
    },
    {
      "name": "Drop",
      "bars": 32,
      "color": "bright_red",
      "cue": 1,
      "repeat_pattern": ["repeat", "next"],  // Play twice then continue
      "output": [
        {"device": "drums", "program": 2},  // Full drums
        {"device": "bass", "control": 74, "value": 100},  // Filter open
        {"device": "lead", "program": 5},  // Lead sound
        {"device": "fx", "control": 20, "value": 40}  // Less reverb
      ]
    },
    {
      "name": "Break",
      "bars": 16,
      "color": "cyan",
      "repeat_pattern": "repeat",  // Manual section
      "notes": "Loop until ready",
      "output": [
        {"device": "drums", "program": 0},  // Drums off
        {"device": "fx", "control": 21, "value": 100}  // Delay on
      ]
    },
    {
      "name": "Final Drop",
      "bars": 32,
      "color": "hot_pink",
      "cue": 2,
      "repeat_pattern": "next_song",  // Go to next track
      "output": [
        {"device": "drums", "program": 3},  // Intense pattern
        {"device": "bass", "program": 10},  // Acid preset
        {"device": "lead", "program": 12}  // Screaming lead
      ]
    }
  ]
}
```

#### Setlist File (festival_set.json)

```json5
{
  "playlist_name": "Summer Festival 2024",
  "mode": "loop",  // Respects repeat_pattern

  // Override some devices for festival
  "devices": {
    "midi_out": {
      "festival_lights": "GrandMA3"
    },
    "osc_out": {
      "video_wall": {"ip": "192.168.2.50", "port": 9000}
    }
  },

  // Additional festival triggers
  "triggers": {
    "song_change": [
      {"device": "festival_lights", "program": "song_index"},
      {"device": "video_wall", "address": "/song/title", "args": ["song_name"]}
    ],

    "setlist_end": [
      {"device": "festival_lights", "program": 99},  // Finale preset
      {"device": "video_wall", "address": "/show/end"}
    ]
  },

  "songs": [
    // Opener from file
    {"filepath": "opener.json", "color": "electric_blue"},

    // Quick transition
    {
      "song_name": "Energy Build",
      "parts": [
        {"name": "Riser", "bars": 8, "repeat_pattern": "next_song"}
      ]
    },

    // Main tracks
    {"filepath": "acid_techno.json"},
    {"filepath": "deep_house.json"},

    // Interactive section
    {
      "song_name": "Crowd Control",
      "color": "yellow",
      "parts": [
        {
          "name": "Hands Up",
          "bars": 4,
          "repeat_pattern": "repeat",  // Loop for crowd
          "notes": "Wait for response",
          "output": {"device": "festival_lights", "control": 50, "value": 127}
        },
        {
          "name": "Drop Back In",
          "bars": 8,
          "repeat_pattern": "next_song"
        }
      ]
    },

    // More tracks
    {"filepath": "techno_anthem.json"},

    // Finale
    {
      "song_name": "Festival Finale",
      "color": "bright_red",
      "parts": [
        {
          "name": "All Together",
          "bars": 64,
          "cue": 10,
          "repeat_pattern": "repeat",
          "output": [
            {"device": "festival_lights", "program": 90},
            {"device": "video_wall", "address": "/effects/fireworks"}
          ]
        }
      ]
    }
  ]
}
```

### Band Setup

#### Band Config (band.conf.json)

```json5
{
  "devices": {
    "midi_in": {
      "clock": "MOTU MIDI Express",
      "midi_in": "FCB1010"  // Foot controller
    },
    "midi_out": {
      "transport_out": "Pro Tools",
      "guitar": "Axe-FX III",
      "keys": "Kronos",
      "bass": "Helix",
      "tracks": "MainStage",
      "mixer": "X32"
    },
    "osc_out": {
      "lights": {"ip": "192.168.1.100", "port": 9000}
    }
  },

  "triggers": {
    "part_change": [
      // Instrument patches
      {"device": "guitar", "channel": 0, "program": "part_index"},
      {"device": "keys", "channel": 1, "program": "part_index"},
      {"device": "bass", "channel": 2, "program": "part_index"},

      // Backing tracks
      {"device": "tracks", "channel": 15, "program": "part_index"},

      // Mixer snapshots
      {"device": "mixer", "channel": 0, "program": "part_index"}
    ]
  }
}
```

#### Song with Repeats (ballad.json)

```json5
{
  "song_name": "Power Ballad",
  "color": "purple",
  "time_signature": "4/4",

  "parts": [
    {
      "name": "Intro",
      "bars": 4,
      "output": [
        {"device": "guitar", "program": 0},  // Clean
        {"device": "keys", "program": 10}    // Piano
      ]
    },
    {
      "name": "Verse 1",
      "bars": 16,
      "cue": 1
    },
    {
      "name": "Verse 2", 
      "bars": 16
    },
    {
      "name": "Chorus",
      "bars": 16,
      "cue": 2,
      "color": "bright_red",
      "repeat_pattern": ["next", "repeat", "next"],  // 2nd time repeat
      "output": [
        {"device": "guitar", "program": 5},  // Distortion
        {"device": "keys", "program": 15}    // Strings
      ]
    },
    {
      "name": "Bridge",
      "bars": 8,
      "color": "yellow"
    },
    {
      "name": "Solo",
      "bars": 16,
      "cue": 3,
      "repeat_pattern": "repeat",  // Extended solo
      "notes": "Watch for cue",
      "output": {"device": "guitar", "program": 10}  // Lead tone
    },
    {
      "name": "Final Chorus",
      "bars": 16,
      "repeat_pattern": ["repeat", "repeat", "next"],  // Triple
      "output": {"device": "mixer", "control": 100, "value": 127}  // All up
    },
    {
      "name": "Outro",
      "bars": 8,
      "output": {"device": "guitar", "program": 0}  // Back to clean
    }
  ]
}
```

### DJ Set with Complex Flow

```json5
{
  "song_name": "DJ Tool",
  "color": "electric_blue",

  "devices": {
    "midi_out": {
      "cdj": "CDJ-3000",
      "mixer": "DJM-900NXS2"
    }
  },

  "parts": [
    {
      "name": "Loop 1",
      "bars": 8,
      "cue": 1,
      "repeat_pattern": "repeat",
      "output": {"device": "cdj", "channel": 0, "control": 20, "value": 127}
    },
    {
      "name": "Loop 2", 
      "bars": 8,
      "cue": 2,
      "repeat_pattern": "repeat",
      "output": {"device": "cdj", "control": 21, "value": 127}
    },
    {
      "name": "Loop 3",
      "bars": 16,
      "cue": 3,
      "repeat_pattern": "repeat",
      "output": {"device": "cdj", "control": 22, "value": 127}
    },
    {
      "name": "Build",
      "bars": 8,
      "cue": 4,
      "repeat_pattern": [
        {"jump_to_cue": 1},  // Back to Loop 1
        {"jump_to_cue": 2},  // To Loop 2
        "next"               // Continue
      ]
    },
    {
      "name": "Drop",
      "bars": 32,
      "cue": 5,
      "color": "bright_red",
      "repeat_pattern": "repeat"
    },
    {
      "name": "Outro Mix",
      "bars": 16,
      "cue": 6,
      "repeat_pattern": "next_song",  // Mix into next track
      "output": {"device": "mixer", "channel": 0, "control": 50, "value": 64}
    }
  ]
}
```

### Modular/Eurorack Integration

```json5
{
  "song_name": "Modular Exploration",

  "devices": {
    "midi_out": {
      "cv": "Expert Sleepers ES-8",  // MIDI to CV
      "seq": "Eloquencer"
    }
  },

  "triggers": {
    "part_change": [
      // Send CV via MIDI CC (scaled 0-127)
      {"device": "cv", "channel": 0, "control": 1, "value": "part_index"},
      {"device": "cv", "channel": 0, "control": 2},  // Gate on
      {"device": "seq", "channel": 0, "program": "part_index"}
    ],

    "bar_triggers": [
      // Trigger envelope every 2 bars
      {
        "device": "cv",
        "each_bar": 2,
        "channel": 0,
        "control": 3,
        "value": 127
      }
    ]
  },

  "parts": [
    {
      "name": "Sequence A",
      "bars": 8,
      "repeat_pattern": ["repeat", "repeat", {"jump_to_part": 2}],
      "output": [
        {"device": "cv", "control": 10, "value": 60},   // VCO pitch
        {"device": "cv", "control": 11, "value": 80},   // Filter cutoff
        {"device": "cv", "control": 12, "value": 40}    // Resonance
      ]
    },
    {
      "name": "Sequence B",
      "bars": 8,
      "repeat_pattern": ["repeat", {"jump_to_part": 0}],
      "output": [
        {"device": "cv", "control": 10, "value": 72},
        {"device": "cv", "control": 11, "value": 100},
        {"device": "cv", "control": 12, "value": 60}
      ]
    },
    {
      "name": "Chaos",
      "bars": 16,
      "cue": 1,
      "repeat_pattern": "repeat",
      "notes": "Tweak knobs!",
      "output": [
        {"device": "cv", "control": 20, "value": 127}   // S&H clock fast
      ]
    }
  ]
}
```

### Theater/Musical Cues

```json5
{
  "song_name": "Act 1 - Scene 2",
  "color": "purple",

  "devices": {
    "midi_out": {
      "qlc": "QLC+"  // Lighting software
    },
    "osc_out": {
      "sound": {"ip": "192.168.1.10", "port": 53000},  // QLab
      "video": {"ip": "192.168.1.11", "port": 53001}   // QLab video
    }
  },

  "parts": [
    {
      "name": "Blackout",
      "bars": 2,
      "cue": 100,
      "output": [
        {"device": "qlc", "channel": 0, "control": 1, "value": 0},
        {"device": "sound", "address": "/cue/100/start"}
      ]
    },
    {
      "name": "Sunrise",
      "bars": 32,
      "cue": 101,
      "notes": "Slow fade up",
      "output": [
        {"device": "qlc", "channel": 0, "program": 101},
        {"device": "video", "address": "/cue/101/start"},
        {"device": "sound", "address": "/cue/101/start"}
      ]
    },
    {
      "name": "Dialog 1",
      "bars": 64,
      "cue": 102,
      "repeat_pattern": "repeat",  // Vamp
      "notes": "Wait for actor cue"
    },
    {
      "name": "Song Intro",
      "bars": 8,
      "cue": 103,
      "output": {"device": "sound", "address": "/cue/103/start"}
    },
    {
      "name": "Song Verse",
      "bars": 32,
      "cue": 104
    },
    {
      "name": "Song Chorus",
      "bars": 16,
      "cue": 105,
      "repeat_pattern": ["next", "repeat", "next"]  // AABA form
    },
    {
      "name": "Dance Break",
      "bars": 64,
      "cue": 106,
      "output": [
        {"device": "qlc", "channel": 0, "program": 106},
        {"device": "video", "address": "/cue/106/start"}
      ]
    }
  ]
}
```

## Important Implementation Details

### Pass Counter Behavior

In Loop Mode, the system tracks passes through the song:

| Pass    | Index | Array Pattern Behavior             |
| ------- | ----- | ---------------------------------- |
| Initial | 0     | Arrays not evaluated               |
| Loop 1  | 1     | Uses array[0]                      |
| Loop 2  | 2     | Uses array[1]                      |
| Loop 3  | 3     | Uses array[2] or wraps to array[0] |

### Mode Differences

| Feature                     | Loop Mode     | Song Mode |
| --------------------------- | ------------- | --------- |
| `repeat_pattern: true`      | Loops part    | Advances  |
| `repeat_pattern: ["array"]` | Follows array | Advances  |
| Manual Part Loop            | Works         | Works     |
| Navigation commands         | Work          | Work      |

### MIDI Channel Mapping

| JSON Value | MIDI Channel | Standard Name      |
| ---------- | ------------ | ------------------ |
| 0          | 1            | Channel 1          |
| 1          | 2            | Channel 2          |
| ...        | ...          | ...                |
| 9          | 10           | Channel 10 (drums) |
| 15         | 16           | Channel 16         |

### Cue Scope

- Cues are **global** across entire playlist
- Search order: Current song first, then others
- Duplicate cues: First found is used
- Range: 1-127 (not 0-based)

### Default Values Summary

| Parameter        | Default                        | Context          |
| ---------------- | ------------------------------ | ---------------- |
| `song_name`      | Filename without extension     | Song root        |
| `playlist_name`  | Filename or directory name     | Playlist root    |
| `color`          | None (UI default)              | Song/Part        |
| `time_signature` | `"4/4"`                        | Song root        |
| `time_division`  | `"1/4"`                        | Song root        |
| `mode`           | `"loop"`                       | Playlist root    |
| `repeat_pattern` | `false` (advance)              | Part             |
| `notes`          | `""`                           | Part             |
| `velocity`       | 127                            | Note messages    |
| `value`          | 127                            | Control messages |
| `program`        | `part_index` if type specified | Program change   |
| `song`           | `song_index` if type specified | Song select      |
| `args`           | `[]`                           | OSC messages     |

### Error Handling

| Condition                | Behavior                           |
| ------------------------ | ---------------------------------- |
| No clock port            | UI prompts for selection           |
| Invalid JSON             | Shows validation errors, continues |
| Missing file in playlist | Skips to next song                 |
| Invalid part index       | Action cancelled with feedback     |
| Part with 0 bars         | Skips to next part                 |
| No parts                 | Song won't play                    |
| Cue not found            | Action cancelled with feedback     |

### Performance Tips

1. **Use device inheritance** to reduce repetition
2. **Omit type parameters** - let inference work
3. **Use defaults** - don't specify velocity: 127
4. **Embed short songs** in playlists directly
5. **Use cues** for important access points
6. **Test with --debug** before performance
7. **Keep backup config** files for different venues
8. **Use comments** in JSON5 files

#### Limitations

- No MIDI SysEx support
- No MIDI NRPN support  
- No direct MIDI Time Code (MTC)
- Random part selection not fully implemented
- Maximum 127 cues per playlist
- Maximum 999 bars per part