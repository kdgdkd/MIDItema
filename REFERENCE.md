# MIDItema Configuration Reference

Complete technical reference for configuring MIDItema files, including device setup, trigger system, song structures, and playlists.

## Glossary

Key terms used throughout this document. Skim this first if anything is unclear.

| Term | Meaning | Example |
|------|---------|---------|
| **Part** | A named section of a song with a fixed number of bars. The basic unit of sequencing. | `{"name": "Chorus", "bars": 8}` |
| **Bar** | One musical measure. Bar count drives when MIDItema advances to the next part. | A part with `"bars": 16` lasts 16 measures |
| **Cue** | A numeric label on a part used for direct jumps (e.g. from MIDI CC). | `{"cue": 3}` — jump here with CC value 3 |
| **Quantization** | How many bars to wait before a requested part change takes effect. | `next_8` waits until the next 8-bar boundary |
| **pass_count** | How many times the current part has completed its bar cycle. Used in repeat patterns. | A pattern `[true, false]` plays on pass 1, skips on pass 2, repeats |
| **repeat_pattern** | Controls what happens when a part finishes. A boolean, string action, or array of per-pass booleans. | `"repeat"` → loop forever; `[true, false]` → alternates |
| **part_loop** | A live toggle that locks the sequencer on the current part, repeating it until released. | Press `↑` to activate/deactivate |
| **Live View** | An alternative display mode showing the entire setlist as a scrolling step sequencer. Replaces the normal content area while keeping header and footer. | Press `l` to cycle: Full → Compact → Off |
| **song_mode** | All repeat patterns are ignored; the sequencer advances linearly through every part exactly once. | `--song-mode` CLI flag or `m` key |
| **loop_mode** | Repeat patterns are respected; parts loop or branch as configured. | `--loop-mode` CLI flag or `m` key |
| **Trigger** | A MIDI or OSC message sent automatically at a specific event (part change, song change, etc.). | `"part_change": [{"device": "synth", "program": 5}]` |
| **Output** | A MIDI/OSC action attached to a specific part, fired when that part becomes active. | `"output": {"program": 3}` |
| **Advanced timing** | Sending a part's output N beats *before* the actual part change, so the device is ready on time. | `"beats": 2` in a playlist fires outputs 2 beats early |
| **State-reconstruction navigation** | Ctrl+Arrow navigation that scans all parts from the start up to the destination, collapses MIDI/OSC messages by key (device + channel + type), and sends a single packet — so the destination sounds as if the set had been played from the beginning. | `Ctrl+→` instead of `→` |
| **Playlist** | A JSON file listing multiple songs to play in sequence, optionally with shared triggers. | `{"songs": [{"filepath": "song1.json"}, ...]}` |
| **Song mode / Loop mode** | The two playback modes for playlists. Song mode plays each song once; loop mode respects repeat patterns. | Set with `"mode": "song"` in playlist file |

## Table of Contents

1. [Glossary](#glossary)
2. [Quick Start - Minimal Examples](#quick-start---minimal-examples)
3. [File Types Overview](#file-types-overview)
4. [Main Configuration File](#main-configuration-file)
5. [Song Files](#song-files)
6. [Playlist Files](#playlist-files)
7. [Trigger System Reference](#trigger-system-reference)
8. [Control Message Reference](#control-message-reference)
9. [Dynamic Values Reference](#dynamic-values-reference)
10. [Command Line Options](#command-line-options)
11. [File Organization](#file-organization)
12. [Live View](#live-view)
13. [Complete Examples](#complete-examples)
14. [Important Implementation Details](#important-implementation-details)

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
  "device_alias": {"synth": "MicroKorg"},
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
    "device_alias": {
        "CLOCK":   "Port Name",                              // Clock / control MIDI ports
        "synth":   "Port Name",                              // Output MIDI ports
        "visuals": { "type": "osc", "ip": "127.0.0.1", "port": 9000 }
    },
    "clock_in": "CLOCK",          // Alias of the MIDI clock source (required)
    "transport_out": "synth",     // Optional: relay Start/Stop/Continue to this alias
    "auto_panic_on_stop": false,  // Optional: send All Notes Off on stop
    "control": [ /* Optional: custom MIDI control rules — see below */ ],
    "triggers": {
        "event_name": [ /* Action list */ ]
    }
}
```

### `device_alias`

Un diccionario plano que mapea nombres de alias a especificaciones de puerto. Cada alias se referencia por nombre en archivos de canción, triggers y reglas de control.

```json5
"device_alias": {
    "CLOCK":         "E-RM Multiclock",               // Coincidencia de substring (insensible a mayúsculas)
    "synth_A":       "Moog Minitaur",
    "synth_B":       "Roland JP-08",
    "drums":         "TR-8S",
    "lights":        "MIDI2DMX",
    "ctrl":          "APC40 mkII",                    // Control input (usar con "control" rules)
    "visuals":       { "type": "osc", "ip": "127.0.0.1", "port": 7000 },
    "touchdesigner": { "type": "osc", "ip": "192.168.1.100", "port": 8000 }
}
```

**Tipos de valor para cada alias**:

| Valor | Significado |
|---|---|
| `"string"` | Substring del nombre del puerto MIDI (insensible a mayúsculas). Se usa el primer match. |
| `{"type": "osc", "ip": ..., "port": ...}` | Destino OSC de salida |
| `{"type": "bus"}` | Fuente LocalBus (clock recibido vía bus inter-proceso desde midimod) |

**Reglas de naming**:

- Cualquier clave JSON válida; evitar espacios (usar guiones bajos)
- Case-sensitive cuando se referencia en triggers y outputs
- El mismo alias puede usarse en `clock_in` y `transport_out`

### `clock_in`

```json5
"clock_in": "CLOCK"
```

Alias (de `device_alias`) a abrir como fuente de MIDI clock. Si el alias apunta a `{"type": "bus"}` o el puerto físico no se encuentra, MIDItema se suscribe a ticks de clock vía LocalBus (publicados por midimod).

### `transport_out`

```json5
"transport_out": "synth_A"
```

Opcional. Alias al que reenviar mensajes Start/Stop/Continue. Puede apuntar al mismo alias que `clock_in`.

### `auto_panic_on_stop`

```json5
"auto_panic_on_stop": true
```

Opcional (por defecto: `false`). Cuando es `true`, envía All Notes Off a todos los outputs MIDI cada vez que se recibe un Stop.

### `control` — Reglas de control MIDI personalizadas

Lista opcional de reglas que mapean mensajes MIDI entrantes a acciones de MIDItema. Permite asignar cualquier controlador (pedal, launchpad, etc.) a comandos de navegación y modo.

```json5
"control": [
    { "device_in": "ctrl", "event": "cc", "ch": 0, "cc": 37, "value": 127, "action": "mode_toggle" },
    { "device_in": "ctrl", "event": "cc", "ch": 0, "cc": 38, "value": 127, "action": "set_quant_4" },
    { "device_in": "ctrl", "event": "cc", "ch": 0, "cc": 39, "value": 127, "action": "prev_part" },
    { "device_in": "ctrl", "event": "cc", "ch": 0, "cc": 40, "value": 127, "action": "next_part" }
]
```

Cada regla:

| Campo | Requerido | Descripción |
|---|---|---|
| `device_in` | Sí | Alias del dispositivo de control (debe estar en `device_alias`) |
| `event` | Sí | Tipo de mensaje MIDI: `"cc"`, `"note_on"`, `"pc"`, `"song_select"` |
| `ch` / `channel` | No | Canal MIDI (0-based). Omitir para coincidir con cualquier canal. |
| `cc` | Para event cc | Número de CC |
| `value` | No | Valor exacto a coincidir. Omitir para cualquier valor. |
| `action` | Sí | Acción a ejecutar (ver tabla abajo) |

**Acciones disponibles para reglas `control`**:

| Acción | Descripción |
|---|---|
| `mode_toggle` | Alternar Loop/Song Mode |
| `set_quant_4` | Fijar cuantización a Next 4 bars |
| `prev_part` | Parte anterior (cuantización global) |
| `next_part` | Parte siguiente (cuantización global) |
| `part_loop_toggle` | Activar/desactivar part loop |
| `part_restart` | Reiniciar parte actual |
| `cancel` | Cancelar acción pendiente |
| `restart_song` | Reiniciar canción desde parte 0 |

El alias `device_in` debe aparecer como clave en `device_alias`. Se abre automáticamente como input MIDI.

### Device Configuration Merging

MIDItema usa `midicore.config.deep_merge` para cargar y combinar configuraciones desde múltiples fuentes:

1. `midi.conf.json` en la raíz de `midicore/` — configuración compartida con midimod (carga primero)
2. `miditema.conf.json` — configuración específica de MIDItema (o el archivo indicado con `--conf`)
3. Secciones `device_alias` dentro de archivos de canción/playlist

El merge es recursivo: los valores de archivos con mayor prioridad sobrescriben los anteriores.

Cuando varios archivos definen `device_alias`:

1. **`midi.conf.json` carga primero** (si existe) — define los aliases compartidos
2. **El conf principal (`miditema.conf.json` o `--conf`) se fusiona encima** — añade o sobreescribe aliases
3. **El `device_alias` de la canción/playlist se fusiona encima**:
   - Los aliases nuevos se añaden
   - Los aliases duplicados sobreescriben
   - Los aliases existentes permanecen

Example:

```json5
// midi.conf.json (raíz de midicore/)
{"device_alias": {"CLOCK": "USB Uno MIDI", "synth": "Minilogue"}}

// miditema.conf.json
{"device_alias": {"synth": "MicroKorg", "drums": "TR-8"}, "clock_in": "CLOCK"}

// Result: CLOCK → USB Uno MIDI, synth → MicroKorg, drums → TR-8
```

## Song Files

### Complete Song Structure

```json5
{
    "song_name": "My Song",            // Optional: Display name
    "color": "blue",                   // Optional: Title bar color
    "time_signature": "4/4",           // Optional: Meter (default: 4/4)
    "time_division": "1/4",            // Optional: Beat division (default: 1/4)
    "device_alias": { /* Optional */ }, // Optional: Device overrides (merged with conf)
    "bus_outputs": false,              // Optional: Route outputs via LocalBus to midimod
    "triggers": { /* Optional */ },    // Optional: Song triggers
    "parts": [                         // Required: At least one part
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
"repeat_pattern": "loop_part"    // Activate manual part loop (enables Silent Mode automatically)
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
- **Purpose**: Local triggers sent in advance of the part change
- **Note**: Executes AFTER global `part_change` triggers

**Timing**: Each action fires according to `playlist.beats` (global default) unless it defines its own `bar` or `beats` field, in which case that value takes precedence. This allows sending different messages to different devices at different moments, all within the same `output` array.

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

// Per-action timing (playlist has "beats": 2)
"output": [
    {"device": "synth", "channel": 0, "program": 5},           // fires 2 beats early (playlist default)
    {"device": "synth_slow", "channel": 1, "program": 5, "bar": 2},  // fires 2 bars early
    {"device": "lights", "address": "/prepare", "beats": 4}    // fires 4 beats early
]
```

| Action has...  | Fires at                              |
| -------------- | ------------------------------------- |
| `"bar": N`     | N bars before end of part             |
| `"beats": N`   | N beats before end of part            |
| neither        | `playlist.beats` beats before end (default) |

## Playlist Files

### Complete Playlist Structure

```json5
{
    "playlist_name": "Festival Set",    // Optional: Display name
    "mode": "song",                     // Optional: Playback mode
    "device_alias": { /* Optional */ }, // Optional: Device overrides (merged with conf)
    "bus_outputs": false,               // Optional: Route outputs via LocalBus to midimod
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
- **Default**: `"song"`
- **Values**:
  - `"loop"`: Respects all repeat_pattern settings (Loop Mode)
  - `"song"`: Forces linear progression (Song Mode)
- **Effect**: Can be toggled live with 'M' key

#### beats

- **Type**: integer
- **Default**: `2`
- **Purpose**: Global default for advanced timing — how many beats before a part change to send `part_change` triggers and `output` actions that have no explicit `beats` or `bar` field
- **Example**: `"beats": 4` — fire outputs 4 beats before each transition

```json5
{
  "playlist_name": "My Set",
  "beats": 4,              // All transitions fire 4 beats early by default
  "songs": [...]
}
```

Individual actions can still override this with their own `"beats"` or `"bar"` fields.

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
- **Mode**: Default "song"

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

##### Vocabulario de campos

MIDItema acepta tanto los nombres legacy como el vocabulario semántico unificado de `midicore.output`. Esto permite copiar/pegar bloques entre midimod y miditema sin reescribir:

| Campo legacy | Campo semántico (midicore) | Sufijo `_out` (compatible midimod) | Significado |
|---|---|---|---|
| `type` | `event` | `event_out` | Tipo de mensaje MIDI |
| `control` | `cc` | `cc_out` | Número de CC |
| `program` | `pc` | `pc_out` | Número de programa |
| `note` | `note` | `note_out` | Número de nota |
| `velocity` | `velocity` | `velocity_out` | Velocidad de nota |
| `value` | `value` | `value_out` | Valor de CC / aftertouch |
| `pitch` | `pitch` | `pitch_out` | Valor de pitch bend |
| `pressure` | `pressure` | `pressure_out` | Valor de aftertouch |
| `song` | `song` | `song_out` | Número de song select |
| `channel` | `channel` / `ch` | `channel_out` / `ch_out` | Canal MIDI (0-15) |

Todas las formas son equivalentes. Internamente, `session.py:_build_mido_message` resuelve las variantes a la representación canónica. Los campos con sufijo `_out` se aceptan para facilitar el copia/pega desde configuraciones de midimod.

```json5
// Estas tres acciones son equivalentes:
{"device": "synth", "type": "control_change", "channel": 0, "control": 74, "value": 100}  // legacy
{"device": "synth", "event": "cc",            "channel": 0, "cc": 74,      "value": 100}  // semántico
{"device": "synth", "event_out": "cc",        "channel_out": 0, "cc_out": 74, "value_out": 100}  // midimod
```

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

#### Integración con MIDImod: `midimod_version` y `midimod_trigger`

Shorthands específicos para enviar comandos a midimod durante un cambio de parte. Se definen en `midicore.protocol` y pueden enviarse por OSC o por MIDI (fallback en canal 16, CCs 20-22):

```json5
// Activar la versión 3 de midimod al entrar en esta parte
"output": {"midimod_version": 3}
// → OSC: /midimod/version 3   o   MIDI CC 20 value=3 en canal 16

// Arrancar el secuenciador "intro_seq" en midimod
"output": {"midimod_trigger": "intro_seq"}
// → OSC: /midimod/seq/intro_seq/play

// Parar el secuenciador "intro_seq"
"output": {"midimod_trigger": "intro_seq", "stop": true}
// → OSC: /midimod/seq/intro_seq/stop
```

El dispositivo de destino por defecto es `"midimod"` (el alias definido en la configuración de dispositivos). Se puede sobrescribir con `"device"` explícitamente.

También pueden usarse en triggers globales:

```json5
"triggers": {
  "part_change": [
    {"midimod_version": "part_index"}  // cada parte activa su versión correspondiente
  ]
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

Fire triggers BEFORE the actual event. Supported in:
- Actions within `triggers.part_change` and `triggers.song_change`
- Actions within `parts[i].output`

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
- Send early PC to slow devices while fast devices use the playlist default

**Timing resolution**: `bar` is converted to beats using the current time signature numerator. In 4/4, `"bar": 1` equals `"beats": 4`. In 3/4, `"bar": 1` equals `"beats": 3`.

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

#### State Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        STOPPED                               │
│                   (no clock received)                        │
└──────────────────┬────────────────────┬─────────────────────┘
                   │                    │
            Press Enter          Clock START
           (playlist active)   (without Enter)
                   │                    │
                   ▼                    ▼
┌──────────────────────────┐   ┌────────────────────────────┐
│   INIT_OUTPUTS_SENT      │   │         PLAYING            │
│                          │   │                            │
│  First part outputs sent │   │  First outputs sent on     │
│  immediately (no delay)  │   │  beat 1 (timing risk)      │
└──────────────┬───────────┘   └────────────────────────────┘
               │
        Clock START received
        (outputs NOT resent)
               │
               ▼
┌──────────────────────────┐
│         PLAYING          │
│                          │
│  Perfect sync from       │
│  first beat              │
└──────────────────────────┘
```

**Recommended flow** (with advanced timing configured):

```
Load file → Press Enter → Start master clock → Performance runs
               ↑                  ↑
       outputs sent now    outputs skipped (already sent)
```

#### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| First part output fires twice | Clock arrived before Enter | Always press Enter before starting clock |
| Outputs never sent | `--no-output` active or `o` key toggled | Check output status indicator in the status bar |
| Enter doesn't start playback | Initial outputs not yet sent (first press) | Press Enter once more to start |
| Enter does nothing at all | No song loaded, or outputs disabled | Load a song file first; check `o` key |
| Wrong program at start | Did not press Enter | Press Enter after loading, before starting clock |

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

| Key     | Action              | Notes                                                                    |
| ------- | ------------------- | ------------------------------------------------------------------------ |
| `Enter` | Init / Start / Stop | 1st press sends initial outputs; 2nd press starts; subsequent presses stop |
| `Space` | Continue/Stop       | Toggles between Continue and Stop                                        |

#### Navigation Controls

| Key               | Action                               | Quantization | Requirements              |
| ----------------- | ------------------------------------ | ------------ | ------------------------- |
| `←`               | Previous Part                        | Global       | -                         |
| `→`               | Next Part                            | Global       | -                         |
| `Ctrl+←`          | Previous Part (state reconstruction) | Global       | -                         |
| `Ctrl+→`          | Next Part (state reconstruction)     | Global       | -                         |
| `PageUp`          | Previous Song                        | Global       | Playlist active           |
| `PageDown`        | Next Song                            | Global       | Playlist active           |
| `Home`            | First Song                           | Global       | Playlist active           |
| `End`             | Last Song                            | Global       | Playlist active           |
| `.` or `,`        | Go to Part...                        | Global       | Enter number + Enter      |
| `+` then `digit`  | Jump +N parts (global setlist)       | Global       | Enter digit after `+`     |
| `-` then `digit`  | Jump −N parts (global setlist)       | Global       | Enter digit after `-`     |

#### Action Controls

| Key       | Action           | Effect                                                                           |
| --------- | ---------------- | -------------------------------------------------------------------------------- |
| `↓`       | Cancel/Reset     | When playing: cancel pending action, or cancel part loop if no action pending. When stopped: reset to song 1 |
| `↑`       | Toggle Part Loop | Manual loop on current part (see below)                                          |
| `m`       | Toggle Mode      | Switch between Loop/Song Mode                                                    |
| `o`       | Toggle Outputs   | Enable/disable MIDI and OSC output sending (Silent Mode)                         |
| `l`       | Live View        | Cycle display: Full → Compact → Off (see below)                                  |
| `v`       | Setlist          | Open parts list window                                                           |
| `g`       | Clips            | Open clip-launcher screen (see below)                                            |
| `h`       | Help             | Open keyboard controls reference screen                                          |
| `r`       | Reload           | Reload current file from disk (if changed)                                       |
| `M`       | Monitor          | Open real-time MIDI/OSC event monitor                                            |
| `Ctrl+P`  | Panic            | Send All Notes Off to all MIDI outputs                                           |
| `q`       | Quit             | Exit application                                                                 |

##### Loop Part and Silent Mode

When Loop Part is activated (`↑`, CC#0 value 16, or `repeat_pattern: "loop_part"`), MIDItema automatically manages output sending:

1. **On activation**: the current output state is saved. If outputs were enabled, they are disabled automatically (no output messages will be sent during the loop).
2. **While looping**: output sending can be toggled freely with `o` as needed.
3. **On deactivation**: output state is restored to whatever it was before Loop Part was activated.

This prevents repeated output messages from being sent on every loop iteration while keeping normal playback behavior once the loop ends.

| Before Loop Part | On activation        | On deactivation       |
| ---------------- | -------------------- | --------------------- |
| Outputs ON       | Outputs forced OFF   | Outputs restored ON   |
| Outputs OFF      | Outputs stay OFF     | Outputs remain OFF    |

##### Ctrl+Arrow: State-Reconstruction Navigation

**The problem**: MIDItema's output messages are assigned only where they change, not repeated on every part. If you jump backwards from part 8 to part 3, part 3 may not carry a Program Change for a channel that was set back in part 1 — so the connected device stays in the wrong state.

**The solution**: `Ctrl+←` / `Ctrl+→` perform a *state-reconstruction jump*. Before activating the destination part, MIDItema scans all parts from the beginning of the setlist up to and including the destination, collects every output message they define, and collapses them into a single packet — one message per key (device + channel + message type, plus control number for CCs). That single packet is then sent instead of the destination part's output alone.

**Algorithm**:
1. Scan parts 0 … N (destination inclusive).
2. For each `(device, channel, type[, control/note])` key, keep the **last** value seen. The destination part participates equally — if it defines a PC on channel 0, that value wins.
3. Preserve the `bar`/`beats` timing offset of the winning message, so advanced timing still applies.
4. Send the collapsed packet via the normal trigger system, respecting quantization.

**When to use it**:
- Navigating backwards in a set where earlier parts set synth patches.
- Skipping forward several parts when intermediate parts carry state-changing messages.
- Any time you need the destination to sound exactly as it would if the set had been played from the beginning.

**Timing and quantization**: Ctrl+Arrow obeys the same global quantization setting as regular `←` / `→`. Advanced timing offsets (`bar`, `beats`) in the winning messages are respected — a message that normally fires 2 beats early will still fire 2 beats early. When the clock is stopped, the collapsed outputs are queued and sent on the first `Enter` press (initialization), just like normal outputs.

**Difference from regular navigation**:

| | `←` / `→` | `Ctrl+←` / `Ctrl+→` |
|---|---|---|
| Messages sent | Destination part's output only | Collapsed packet from parts 0 → N |
| Use case | Normal sequential playback | Jump with correct device state |
| Quantization | Global | Global |
| Advanced timing | Respected | Respected |

##### Clips Mode

Clips Mode turns MIDItema into a clip-launcher: when the current part ends it restarts instead of advancing, staying there until you manually trigger a jump.

**Activation**:

- Press `g` to open the Clips screen
- Inside the screen, press `Backspace` to toggle Clips Mode ON/OFF
- A purple `CLIPS ON` badge appears in the UI while active

**Clips screen keys**:

| Key          | Action                                                                  |
| ------------ | ----------------------------------------------------------------------- |
| `1`–`9`      | Jump to parts 1–9 (using global quantization)                          |
| `a`–`z`      | Jump to parts 10–35                                                     |
| `Backspace`  | Toggle Clips Mode ON/OFF                                                |
| `PgUp/PgDn`  | Browse previous/next song in playlist (view-only, does not jump to it) |
| `Esc`        | Close screen (Clips Mode state persists)                                |

**Behavior details**:

- Clips Mode is independent of Loop Mode / Song Mode — both remain active in the background
- Part Loop (`↑`) temporarily overrides Clips Mode (the looped part wins until loop is cancelled)
- Output triggers still fire normally on each restart
- Clips Mode is reset to OFF on stop

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

### Panic

`Ctrl+P` sends All Notes Off (CC#123 value 0), All Sound Off (CC#120 value 0), and Reset All Controllers (CC#121 value 0) to every configured MIDI output port on every channel (0–15). Use it to clear stuck notes without stopping the clock.

A feedback message `⚡ PANIC — All Notes Off` confirms the action. OSC outputs are not affected.

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
midicore/                     # Raíz del workspace compartido
├── midicore/                 # Librería compartida MIDI/OSC
│   ├── ports.py, clock.py, osc.py, ...
│   └── bus/                  # Pub/sub inter-proceso
├── midi.conf.json            # Config de dispositivos compartida (miditema + midimod)
├── midimod/                  # Aplicación MIDImod
├── miditema/                 # Aplicación MIDItema
│   ├── miditema.py           # CLI entry point y module facade
│   ├── session.py            # Motor, estado, MIDI/OSC I/O
│   ├── tui.py                # Terminal UI (Textual)
│   ├── ui_helpers.py         # Paleta de colores y utilidades de estilo
│   ├── schema_validator.py   # Validación JSON
│   ├── palettes.json         # Definiciones de color
│   ├── miditema.conf.json    # Config principal opcional
│   └── temas/                # Directorio de contenido por defecto
│       ├── song1.json
│       ├── song2.json
│       ├── live_set.json     # Archivo de playlist
│       └── festival/         # Directorio como playlist
│           ├── opener.json
│           ├── main_set.json
│           └── encore.json
└── pyproject.toml
```

### File Search Order

1. **Exact path**: Uses provided path as-is
2. **Filename only**: Searches in `temas/` directory
3. **No extension**: Tries `.json` then `.json5`
4. **Directory**: All JSON files become playlist

### Config File Priority

1. `device_alias` en archivos de canción/playlist (más alta — se fusiona encima)
2. Archivo especificado con `--conf`, o `miditema.conf.json` si no se usa `--conf`
3. `midi.conf.json` en la raíz de `midicore/` (base compartida, siempre carga primero)
4. Selección de dispositivo por UI (más baja — si no hay `clock_in` configurado)

### File Hot-Reload

MIDItema watches the loaded file for changes on disk. When a modification is detected:

- A notification appears in the feedback bar
- Press `r` to reload immediately without restarting the app
- Clock state, playlist position, and part loop state are preserved across reloads
- Useful for live editing song structures mid-performance

## Live View

Live View replaces the normal content area with a full-setlist scrolling step sequencer. The header (MIDItema, status, BPM, devices) and the status/footer bar (mode, quantize, action, key bindings) remain visible at all times.

### Activation

Press `l` to cycle through three states:

| Press | State         | Rows per line |
|-------|---------------|---------------|
| 1st   | Live Full     | 3 (visual padding, same height as normal sequencer) |
| 2nd   | Live Compact  | 1 (dense view — more parts visible simultaneously) |
| 3rd   | Off           | Returns to normal view |

### Info Bar

A black bar below the header shows the current position at a glance:

```
 {2/5} PRETES  (8/23)  06:18 / 16:45  live:FULL
```

| Field | Meaning |
|---|---|
| `{2/5}` | Current song / total songs in playlist (`{1/1}` for single-song mode) |
| `PRETES` | Active song name |
| `(8/23)` | Active part index / total parts in the current song |
| `06:18` | Song elapsed time |
| `16:45` | Set elapsed time |
| `live:FULL` | Current display mode (FULL or COMPACT) |

### Sequencer Layout

Each row represents one **8-bar chunk** of a part. Parts longer than 8 bars span multiple rows; parts shorter than 8 bars leave trailing space on their row.

```
 0  ████ ████ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░   ch0 pc7  ch9 pc0
    ████ ████ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░
                                              
 1  ████ ████ ████ ████                        ch0 pc8
    ████ ████ ████ ████
                                              
    ████ ████ ████ ████ ████ ████ ████ ████   ← continuation row (same part, bars 9–16)
    ████ ████ ████ ████ ████ ████ ████ ████
                                              
 2  [W]███ ████ ████ ████ ████ ████ ████ ████  ch0 pc9
```

- **Shortcut number** (`0`, `1`, `2` …) — appears only on the first visible row of each distinct part. Up to 10 parts (0–9) can have shortcuts in the current viewport.
- **Blocks** — each group of blocks is one bar. Within a bar, each block is one beat (4 blocks in 4/4).
- **MIDI hints** (right column) — only on the first chunk row of each part. Lists all output messages that fire when the part starts.

#### Color Coding

| Rows / blocks | Appearance |
|---|---|
| Parts before the active part | Dark gray (`#222222`) — consumed |
| Active part — consumed bars | Dark gray |
| Active part — current bar | Beat-by-beat animation (yellow at 4 bars left, red at 1 bar) |
| Active part — remaining bars | Part color |
| Parts after the active part | Part color — pending |
| First bar of the next part | **White** (or **blue** if the part's color is white) |
| First bar of a pending jump target | **White** / **blue** (overrides natural next-part highlight) |

Navigating backwards automatically re-colors parts that were previously consumed — any part ahead of the current position is shown in its part color regardless of playback history.

#### Row Shortcuts

When Live View is active, pressing `0`–`9` jumps to the part assigned to that number in the current viewport (using the global quantization setting). Shortcuts are assigned left-to-right to the first visible occurrence of each distinct part; continuation rows of the same part share the same number on its first visible row (subsequent rows show no number).

```
 0  ████ …   ← press 0 → jump to this part
    ████ …   ← (no shortcut — same part, row 2)
 1  ████ …   ← press 1 → jump to this part
 2  ████ …   ← press 2 → jump to this part
```

Pressing a shortcut key always jumps to the **start** of the part (bar 1), firing all MIDI/OSC output messages as normal.

#### MIDI Hint Format

Output messages attached to a part are summarised to the right of the sequencer row:

| Message type | Format | Example |
|---|---|---|
| Program Change | `chX pcY` | `ch0 pc5` |
| Control Change | `chX ccY` | `ch9 cc7` |
| Note On/Off | `chX ntY` | `ch0 nt60` |
| Song Select | `ssY` | `ss3` |

Multiple messages are separated by two spaces: `ch0 pc5  ch9 pc0  ss3`

### Autoscroll

The sequencer scrolls automatically during playback so the active row stays at the **second position from the top** (or the first position when at the beginning of the setlist, and the last position when at the end). When playback is stopped the view shows from the top.

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
  "device_alias": {"synth": "Minilogue"},
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
  "device_alias": {
    "clock":     "Ableton Push 2",
    "ctrl":      "APC40 mkII",
    "transport": "Ableton Live",
    "bass":      "Moog Sub 37",
    "lead":      "Nord Lead A1",
    "drums":     "TR-8S",
    "fx":        "Eventide H9",
    "resolume":  {"type": "osc", "ip": "127.0.0.1", "port": 7000},
    "lights":    {"type": "osc", "ip": "192.168.1.100", "port": 8000}
  },
  "clock_in": "clock",
  "transport_out": "transport",

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
  "mode": "song",  // Linear progression (default)

  // Add festival-specific aliases (merged with conf's device_alias)
  "device_alias": {
    "festival_lights": "GrandMA3",
    "video_wall": {"type": "osc", "ip": "192.168.2.50", "port": 9000}
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
  "device_alias": {
    "clock":     "MOTU MIDI Express",
    "fcb1010":   "FCB1010",        // Foot controller (configure via "control" rules)
    "transport": "Pro Tools",
    "guitar":    "Axe-FX III",
    "keys":      "Kronos",
    "bass":      "Helix",
    "tracks":    "MainStage",
    "mixer":     "X32",
    "lights":    {"type": "osc", "ip": "192.168.1.100", "port": 9000}
  },
  "clock_in": "clock",
  "transport_out": "transport",

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

  "device_alias": {
    "cdj":   "CDJ-3000",
    "mixer": "DJM-900NXS2"
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

  "device_alias": {
    "cv":  "Expert Sleepers ES-8",  // MIDI to CV
    "seq": "Eloquencer"
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

  "device_alias": {
    "qlc":   "QLC+",                                                       // Lighting software
    "sound": {"type": "osc", "ip": "192.168.1.10", "port": 53000},        // QLab
    "video": {"type": "osc", "ip": "192.168.1.11", "port": 53001}         // QLab video
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
| `mode`           | `"song"`                       | Playlist root    |
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
9. **Use Clips Mode (`g`)** to hold on a part and jump manually — ideal for improvised sets
10. **Use Panic (`Ctrl+P`)** when stuck notes occur without stopping the clock
11. **Use hot-reload (`r`)** to edit song files mid-performance without restarting
12. **Use Live View (`l`)** for a bird's-eye view of the entire setlist — press `0`–`9` to jump directly to any visible part
13. **Use `Ctrl+←` / `Ctrl+→`** when navigating backwards or skipping parts — it reconstructs device state so the destination sounds correct without having to replay the set from the beginning

#### Limitations

- No MIDI SysEx support
- No MIDI NRPN support  
- No direct MIDI Time Code (MTC)
- Random part selection not fully implemented
- Maximum 127 cues per playlist
- Maximum 999 bars per part