# MIDItema: Live Performance Sequencer

A terminal-based, live performance song arranger and bar counter. MIDItema acts as a MIDI clock slave, stepping through song structures and broadcasting state changes via MIDI and OSC, giving you powerful, quantized control over your song's flow.

## Core Concept

MIDItema is a master sequencer and automation hub for live performance. Its core purpose is to structure your entire set into a clear hierarchy: **Setlists** are composed of **Songs**, and Songs are composed of **Parts**.

Acting as a MIDI clock slave, it listens to an external clock source and provides clear visual feedback on your current position within the setlist. As it progresses through the song structure, its main job is to send precisely timed **MIDI events and OSC messages**. This transforms MIDItema into the central brain of your performance, allowing you to **synchronize automations** in other programs or external secuencers, trigger visual effects, change synth patches, and control lighting rigs.

It also facilitates live performance by giving you powerful, quantized navigation controls to create loops or jump between parts and songs. Furthermore, it allows you to define global **Cues**—direct access points to critical parts across your entire setlist—making complex, non-linear jumps reliable and perfectly quantized.

(You could use [MIDImod](https://github.com/kdgdkd/MIDImod) to read MIDItema's OSC messages, transform them into any kind of MIDI event, and route it to your preferred destination; you could send to your sequencer Song Select events upon song changes, and Program Change for part changes, or automate new CC values for your synth for each song or a particular part of a song.)

## Features

- **Playlist / Setlist Mode:** Structure an entire live set in multiple ways: create explicit **Playlist files** that link songs, or simply **load a directory** of song files on the fly to generate an instant playlist.
- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source.
- **Advanced Song & Playlist Structure:** Define songs and playlists in simple, human-readable `json5` files. Specify parts, lengths, colors, and time signatures.
- **Powerful Trigger System:** A unified, event-driven engine to automate your entire show. Send any MIDI or OSC message in response to in-game events like part changes, song changes, or rhythmic intervals.
- **Dynamic Flow Control:** A `repeat_pattern` system controls the action executed after a part finishes. Define simple loops, complex sequences, or conditional jumps to create dynamic, non-linear song arrangements.
- **Live Part & Song Navigation:** Manually trigger quantized jumps to the next/previous part or song, restart the current section, or go to any specific part/song on command.
- **Dual Playback Mode (Loop/Song):** Toggle between two modes on the fly. **Loop Mode** respects the `repeat_pattern` of each part. **Song Mode** overrides these patterns, forcing the arrangement to always advance linearly.
- **Quantized Actions:** All jumps are scheduled as a **pending action** and executed with musical precision on the next beat, bar, or larger musical divisions.
- **Global Cues & Dynamic Quantization:** Assign key parts across your **entire setlist** to Cues for instant, one-press access. Repeatedly trigger a pending cue to dynamically shorten its quantization for expressive, on-the-fly transitions.
- **Comprehensive TUI (Terminal User Interface):** A clean, full-screen interface provides a clear overview of the song structure, countdowns, sequencer, and pending actions.
- **Flexible Control Scheme:** Control MIDItema from your computer keyboard or external MIDI messages (Program Change, Song Select, Note On, and CCs).
- **External Configuration:** All I/O ports and triggers are defined in a single `miditema.conf.json` file.

## Installation 
MIDItema is designed to run from a terminal and requires Python 3. 
1. **Clone the repository:**
 ```bash
 git clone https://github.com/kdgdkd/miditema.git
 cd miditema 
````

2. **Install dependencies:**
 It's recommended to use a Python virtual environment.
 ```bash
 # Create and activate a virtual environment (optional but recommended)
 python3 -m venv venv
 source venv/bin/activate # On Windows, use `venv\Scripts\activate` # Install the required packages
 pip install mido python-osc prompt-toolkit python-rtmidi json5 
 ````

## Configuration

MIDItema uses `json5` files for configuration, which allows for comments and more flexible syntax. There are two types of files: a main config file (`miditema.conf.json`) and the song/playlist files located in a content directory (defaults to `temas/`).

### 1. Main Configuration (miditema.conf.json)

This file, located in the root directory, defines all your MIDI and OSC connections, as well as event-driven output actions (triggers). MIDItema uses partial string matching (case-insensitive) for port names, so you only need to provide a unique substring (e.g., "Clock" instead of "Arturia BeatStep Pro MIDI 1 (Clock In)").

**Full `miditema.conf.json` Example:**

```json
// miditema.conf.json
// Main configuration for MIDI/OSC connections and output triggers.
{
    // Defines all physical and virtual I/O ports.
    "devices": {
        "midi_in": {
            "clock": "E-RM Multiclock",
            "midi_in": "MIDItema Controller"
        },
        "midi_out": {
            "transport_out": "Ableton Live",
            "synth_A": "Moog Minitaur"
        },
        "osc_out": {
            "resolume": { "ip": "127.0.0.1", "port": 7000 }
        }
    },

    // Defines what messages are sent when specific events occur.
    "triggers": {
        "part_change": [
            {
                "device_out": "synth_A",
                "event": "program_change",
                "channel": 0,
                "program": "part_index" // This is a dynamic value
            }
        ],
        "song_change": [
            {
                "device_out": "resolume",
                "address": "/miditema/song/change",
                "args": [ "song_index", "song_name" ]
            }
        ]
    }
}
````


**Parameter Breakdown:**

#### devices Section

This section maps all the inputs and outputs MIDItema will use.

- **devices.midi_in**: Defines ports from which MIDItema **receives** MIDI messages.
  
  - "clock": (Mandatory) A unique substring of the MIDI input port that sends the master MIDI clock and transport (Start/Stop/Continue) messages.
    
  - "midi_in": (Optional) A substring of the MIDI input port for receiving control messages (CC, Notes, etc.). If this is the same as "clock", MIDItema will use a single port for both functions. If different, it will open a dedicated second port for control.
    
- **devices.midi_out**: Defines ports to which MIDItema **sends** MIDI messages. You create custom aliases (e.g., "synth_A") that you will reference in the triggers section.
  
  - "transport_out": (Special Alias) If you define this alias, MIDItema will automatically forward Start/Stop/Continue commands to this port. This is a convenient way to control a master sequencer without needing to define triggers for it.
- **devices.osc_out**: Defines destinations to which MIDItema **sends** OSC messages. You create custom aliases (e.g., "resolume") that you will reference in the triggers section. Each destination is an object with:
  
  - "ip" (string): The target IP address.
    
  - "port" (integer): The target port.
    

#### triggers Section

This section is the core automation engine. It defines what actions are executed when specific events happen within the application.

- **Structure**: The triggers object contains keys that represent **events** (e.g., "part_change"). The value for each event is a list of one or more **action objects**.
  
- **Action Objects**: Each action object specifies what message to send and where to send it.
  
  - "device_out": (Mandatory) The alias of the destination device, which must be defined in the devices section.
    
  - **For MIDI Messages**:
    
    - "event": The type of MIDI message (e.g., "program_change", "control_change", "note_on").
      
    - Other parameters depend on the event type (e.g., "channel", "program", "control", "value", "note", "velocity").
      
  - **For OSC Messages**:
    
    - "address": The OSC address path (e.g., "/miditema/part/change").
      
    - "args": A list of arguments to send with the message.
      
- **Dynamic Values**: You can use special strings that MIDItema replaces with live data. For example, in a "part_change" trigger, "program": "part_index" sends a Program Change message whose value is the index of the new part. The available dynamic values are listed in the comments of the full configuration guide.
  
- **Delayed Triggers**: An action can be scheduled to fire before its event occurs by adding "bar": N or "beats": N to the action object. This is ideal for pre-loading synth patches or visual cues.
  
**Available Trigger Events:**

- `playback_start`, `playback_stop`, `playback_continue`: Fired on transport commands.
- `part_change`: Fired when a new part begins.
- `song_change`: Fired when a new song is loaded from a playlist.
- `setlist_end`: Fired when the entire playlist finishes.
- `bar_triggers`: Fired at configurable rhythmic intervals within a part.
- `countdown_triggers`: Fired on the last few beats before a part ends or a jump occurs.
        
### 2. Song and Playlist Files

MIDItema can load content in three ways: as individual **Song files**, as **Playlist files** that arrange multiple songs, or by loading an entire **Directory** of songs as a virtual playlist.

#### Song File Example

A standard song file defines a single piece of music.

```json
// temas/my_song.json
{
    "song_name": "Genocide in Palestine",
    "color": "blue",
    "time_signature": "4/4",
    "parts": [
        // No "repeat_pattern" means it will default to "next".
        { "name": "Intro - OUR land", "bars": 8, "color": "cyan" },
        { "name": "Verse - Nazis in sheep's clothing", "bars": 16, "color": "green" },
        // This part will play twice, then jump to the last part of the song.
        {
          "name": "Chorus - Free Palestine", "bars": 16, "color": "yellow", "cue": 1,
          "repeat_pattern": ["repeat", "repeat", "last_part"]
        },
        { "name": "Outro - We'll never forget", "bars": 8, "color": "red", "repeat_pattern": "repeat" }
    ]
} 
````

**Root-Level Parameters:**

- **song_name**: (Optional) The name of the song. If omitted, the filename (without the extension) is used.
  
- **color**: (Optional) Sets the background color for the song's title bar in the UI. Available colors: default, red, green, yellow, blue, magenta, cyan.
  
- **time_signature**: (Optional) The time signature of the song (e.g., "4/4", "3/4"). Only the numerator is currently used to calculate the number of beats per bar. Defaults to "4/4".
  
- **time_division**: (Optional) Defines the "beat" of the song relative to the MIDI clock's 24 pulses per quarter note (PPQN).
  
  - "1/4": A song beat is a quarter note (24 ticks). This is the default.
    
  - "1/8": A song beat is an eighth note (12 ticks).
    
  - "1/16": A song beat is a sixteenth note (6 ticks).
    
- **parts**: (Mandatory) A list of part objects that define the structure of the song.
  

**Part-Level Parameters (within the parts list):**

- **name** (string): The name of the part (e.g., "Verse 1").
  
- **bars** (integer): The length of the part in bars. A part with 0 bars will be skipped.
  
- **color** (string, optional): Sets the color for this part's title bar and for its entry in the >> Next Part display. Uses the same color palette as the song-level color.
  
- **cue** (integer, optional): Assigns a global cue number (e.g., 1-128) to this part. This makes the part directly accessible from anywhere in the playlist via F-Keys or MIDI CC#2. Each cue number should be unique across the entire setlist.
  
- **notes** (string, optional): A short, one-line description or note for the part, displayed in the UI.
  
- **repeat_pattern** (optional): This is the core engine for controlling the song's flow. It defines the action to be executed after the part finishes playing.
  
  - **If omitted:** The default action is "next", causing the song to proceed linearly.
    
  - **As a string:** "repeat_pattern": "repeat" will cause the part to loop on itself indefinitely.
    
  - **As a list:** "repeat_pattern": ["next", "next", "repeat", { "jump_to_cue": 5 }] creates a sequence. On the first pass, it executes "next"; on the second, "next"; on the third, it "repeat"s; on the fourth, it jumps to cue 5. The sequence then repeats from the beginning on subsequent passes.
    

The following table lists all available actions:

| Action Value | Type | Description |
| --- | --- | --- |
| **Basic Navigation** |     |     |
| "next" | string | Proceeds to the next valid part according to the current playback mode (Loop/Song). This is the default behavior. |
| "prev" | string | Proceeds to the previous valid part. |
| "repeat" | string | Repeats the current part. |
| "first_part" | string | Jumps to the first valid part of the current song. |
| "last_part" | string | Jumps to the last valid part of the current song. |
| **Absolute Jumps** |     | (These actions reset the song's pass counter) |
| { "jump_to_part": N } | object | Jumps directly to the part at index N (0-based) in the current song. |
| { "jump_to_cue": N } | object | Jumps to the part marked with "cue": N in the current song. |
| { "random_part": [N, M] } | object | Jumps to a randomly chosen part from the provided list of indices. |
| **Playlist Navigation** |     | (These actions require a playlist to be active) |
| "next_song" | string | Loads the next song in the playlist. |
| "prev_song" | string | Loads the previous song in the playlist. |
| "first_song" | string | Loads the first song in the playlist. |
| "last_song" | string | Loads the last song in the playlist. |
| **Mode Control** |     |     |
| "loop_part" | string | Activates a manual loop on the current part. The part will repeat indefinitely until the user cancels it or triggers another jump. |
| "song_mode" | string | Switches the global playback mode to **Song Mode** and then proceeds to the next part. |
| "loop_mode" | string | Switches the global playback mode to **Loop Mode** and then proceeds to the next part. |

#### Playlist File Example

A playlist file arranges multiple songs. It is identified by the presence of a "songs" key.

```
// temas/my_setlist.json
{
  "playlist_name": "My Live Set",
  "mode": "loop",
  "songs": [
    // 1. External Song: Referenced from another file
    { "filepath": "my_song.json" },

    // 2. Embedded Song: Defined directly inside the playlist
    {
      "song_name": "Ambient Interlude",
      "color": "magenta",
      "parts": [
        { "name": "Pad Drone", "bars": 8, "color": "cyan", "repeat_pattern": "repeat" },
        // After this part, automatically load the next song in the playlist.
        { "name": "Riser FX", "bars": 4, "color": "yellow", "repeat_pattern": "next_song" }
      ]
    },

    // 3. Another External Song
    { "filepath": "another_track.json" }
  ]
}
```

- **playlist_name**: (Optional) The name for the playlist. Defaults to the filename.
  
- **songs**: (Mandatory) A list of song objects. Each object can be:
  
  - **An external song reference:** { "filepath": "filename.json" }. MIDItema will load this file from the same directory.
    
  - **An embedded song:** A full song object defined directly within the list, containing its own song_name, color, and parts.
    
- **mode**: (Optional) Sets the default playback mode for the playlist. Can be "loop" (respects repeat_pattern) or "song" (forces linear progression). This setting is overridden by the --loop-mode or --song-mode command-line arguments.
  
## Usage

1. **Start your master clock source.** This could be your DAW, a hardware sequencer, or a software clock. Ensure it is configured to send MIDI Clock.
  
2. **Configure `miditema.conf.json`** to listen to the correct MIDI ports for clock and control, and to send data to the correct output ports.
  
3. **Run MIDItema from your terminal.** It can be launched in several ways depending on your needs:
  
  - **Interactive Mode (No arguments):** MIDItema will show a list of all `.json` files in the content directory for you to choose from.
    
    ```bash
    python miditema.py
    ```
    
  - **File Mode (Provide a filename):** Loads a specific song or playlist file. You can provide the name with or without the `.json` extension.
    
    ```bash
    # Both of these commands work
    python miditema.py my_song_file
    python miditema.py my_setlist.json
    ```
    
  - **Directory Mode (provide a path ending in `/` or `\`):** Loads all `.json` files from the specified directory, sorted alphabetically, as a virtual playlist.
    
    ```bash
    # Loads all songs from the 'my_live_set' folder
    python miditema.py my_live_set/
    ```
    
  
  You can also combine these modes with command-line arguments for more control:
  
  ```bash
  # Launch with a specific quantization mode and force Song Mode
  python miditema.py my_setlist.json --quant 8 --song-mode
  
  # Launch using an alternative configuration file
  python miditema.py my_setlist.json --conf live_performance.conf.json
  ```
  
  - `--quant [bar|4|8|16|32|instant]`: Sets the default quantization mode on startup.
  - `--song-mode` / `--loop-mode`: Forces the initial playback mode, overriding the setting in a playlist file.
  - `--conf [filename]`: Specifies an alternative main configuration file to use.
4. **Start the master clock.** MIDItema will detect the clock, synchronize, and begin stepping through the song parts as defined.
  

## Controls

MIDItema can be controlled via computer keyboard or external MIDI messages. Most actions are scheduled as a **pending action** and executed with musical quantization.

### Keyboard Controls

| Key(s) | Action | Details / Quantization |
| --- | --- | --- |
| **Global Transport** |     |     |
| `Enter` | Toggle Start/Stop | Sends a MIDI `start` command if stopped, or `stop` if playing. |
| `Space` | Toggle Continue/Stop | Sends a MIDI `continue` command if stopped, or `stop` if playing. |
| `q` / `Ctrl`+`C` | Quit | Exits the application cleanly. |
| **Part Navigation** |     |     |
| `→` / `←` | Jump Next / Previous Part | Programs a relative jump. Uses the **global** quantize mode. |
| `↑` | Toggle Part Loop | Toggles a manual loop on the currently playing part. |
| `.` or `,` then `[num]` `Enter` | Go to Part | Jumps to a specific part number. Uses the **global** quantize mode. |
| **Playlist Navigation** |     |     |
| `PageDown` / `PageUp` | Next / Previous Song | Jumps to the next or previous song. Uses the **global** quantize mode. |
| `Home` / `End` | Go to First / Last Song | Jumps to the first or last song. Uses the **global** quantize mode. |
| **General Actions** |     |     |
| `↓` | Cancel / Reset | Cancels any pending action. If playback is stopped, it resets the entire setlist to the beginning. |
| `m` | Toggle Playback Mode | Switches between **Loop Mode** (respects part repeats) and **Song Mode** (forces linear progression). |
| `F1`-`F12` | Go to Cue 1-12 | Jumps to the part marked with the corresponding `"cue": N`. Uses **dynamic** quantization. |
| **Quick Jumps (Fixed Quantization)** |     |     |
| `0` - `3` | Quick Jump +1 | Jumps to the next part with fixed quantization (`0`:Next Bar, `1`:Next 4, `2`:Next 8, `3`:Next 16). |
| **Global Quantize Mode Selection** |     |     |
| `4` - `9` | Set Global Quantize | Sets the global mode (`4`:Next 4, `5`:Next 8, `6`:Next 16, `7`:Next Bar, `8`:End of Part, `9`:Instant). |

### MIDI Controls

To use MIDI controls, configure `"midi_in"` in the `devices` section of `miditema.conf.json`.

| Message | Action | Details / Quantization |
| --- | --- | --- |
| **Absolute Jumps** |     |     |
| **Program Change** `N` | Go to Part `N`+1 | Jumps to a specific part in the current song. Uses the **global** quantize mode. |
| **Song Select** `N` | Go to Song `N`+1 | Jumps to a specific song in the current playlist. Uses the **global** quantize mode. |
| **Relative Navigation** |     |     |
| **Note On** `125` | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| **Note On** `124` | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| **Note On** `127` | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| **Note On** `126` | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |

#### General Functions via CC #0

All actions below are triggered by sending a Control Change message on **CC #0** with a specific value.

| CC #0 Value | Action | Details / Quantization |
| --- | --- | --- |
| `0` - `3` | Quick Jump +1 | Jumps to the next part with fixed quantization (`0`:Instant, `1`:Next Bar, `2`:Next 8, `3`:Next 16). |
| `4` - `9` | Set Global Quantize | Sets the global mode (`4`:Next 4, `5`:Next 8, `6`:Next 16, `7`:Next Bar, `8`:End of Part, `9`:Instant). |
| `10` | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| `11` | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| `12` | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |
| `13` | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| `14` | Go to First Song | Jumps to the first song in the playlist. Uses the **global** quantize mode. |
| `15` | Go to Last Song | Jumps to the last song in the playlist. Uses the **global** quantize mode. |
| `16` | Toggle Part Loop | Toggles a manual loop on the currently playing part. |
| `17` | Restart Part | Restarts the current part. Uses the **global** quantize mode. |
| `18` | Cancel Action | Immediately cancels any pending action. |
| `19` | Toggle Playback Mode | Switches between Loop Mode and Song Mode. |
| `20` | Restart Song | Restarts the current song from its first part. Uses the **global** quantize mode. |

#### Global Navigation (CC #1 & Cues)

These are powerful features for navigating large setlists, allowing you to jump to any part across your entire playlist. **These features require a playlist to be active.**

| Trigger | Action | Details | Quantization |
| --- | --- | --- | --- |
| **CC #1** (Value `N`) | Go to Global Part `N` | Jumps to a part based on its absolute index in the setlist (0-127). If song 1 has 5 parts, value `5` jumps to the first part of song 2. | Global |
| **CC #2** (Value `N`) | Go to Cue `N` | Jumps to the part marked with `"cue": N`. Allows access to 128 cues. | Dynamic |

**Dynamic Quantization (for Cues only):**

This is a unique feature of Cue Jumps (triggered by `F1-F12` or `CC #2`). Repeatedly triggering the same cue while it is pending will speed up its quantization for that specific jump.

- **First Trigger:** The jump is scheduled using the current **global** quantize mode (e.g., Next 8).
- **Second Trigger:** The pending jump's quantization is halved (e.g., from Next 8 to Next 4).
- **Subsequent Triggers:** Each trigger continues to halve the quantization until it reaches the fastest level (Next Bar).
- The TUI will display the dynamic quantization in real-time.
  
## Trigger System and Automation

The `triggers` section in `miditema.conf.json` is the core automation engine of the application. It allows you to send any MIDI or OSC message in response to specific events. This is how you synchronize external gear, DAWs, visual software, and lighting.

The basic structure is an **event** (e.g., `"part_change"`) that fires a list of one or more **actions**.

### Key Concepts

- **Dynamic Values**: For most events, you can use special strings (e.g., `"part_name"`) in your action definitions. MIDItema will replace these with the current data in real-time.
- **Delayed Triggers**: You can schedule an action to fire *before* its event occurs by adding `"bar": N` or `"beats": N` to the action object. This is perfect for pre-loading synth patches or visual cues.

### Main Trigger Events

#### `part_change`

Fires at the exact moment a new part begins. This is the most commonly used trigger.

- **Dynamic Values Available**:
  - `part_index`, `part_name`, `part_bars`, `part_color`, `part_notes`, `part_cue`
  - `song_index`, `song_name`, `song_color`
  - `part_index_in_setlist` (the absolute index of the part across the entire playlist)
- **Example**:
  
  ```json
  "part_change": [
      // Send a MIDI Program Change to a synth
      {
          "device_out": "synth_A",
          "event": "program_change",
          "channel": 0,
          "program": "part_index"
      },
      // Send an OSC message to a visualizer
      {
          "device_out": "resolume",
          "address": "/visuals/scene/load",
          "args": [ "part_name", "part_color" ]
      }
  ]
  ```
  

#### `song_change`

Fires when a new song is loaded from a playlist.

- **Dynamic Values Available**: `song_index`, `song_name`, `song_color`
- **Example**:
  
  ```json
  "song_change": [
      {
          "device_out": "resolume",
          "address": "/show/song/title",
          "args": [ "song_name" ]
      }
  ]
  ```
  

#### Rhythmic Triggers: `bar_triggers` & `countdown_triggers`

These triggers fire repeatedly based on the musical grid.

- **`bar_triggers`**: Fires on repeating bar intervals within a part. Use `"each_bar": N` to set the interval.
  - **Dynamic Values**: `completed_bar`, `block_number` (e.g., the 3rd block of 4 bars).
  - **Example**: Send an OSC message every 4 bars.
    
    ```json
    "bar_triggers": [
        {
            "device_out": "resolume",
            "each_bar": 4,
            "address": "/composition/columns/4/connect",
            "args": [ "block_number" ]
        }
    ]
    ```
    
- **`countdown_triggers`**: Fires on the last few beats before a part ends or a jump occurs. Use `"each_beat": N` to specify how many beats to count down from.
  - **Dynamic Values**: `remaining_beats`, `remaining_bars`.
  - **Example**: Send the remaining beat count to an OSC display.
    
    ```json
    "countdown_triggers": [
        {
            "device_out": "touchdesigner",
            "each_beat": 4,
            "address": "/ui/countdown",
            "args": [ "remaining_beats" ]
        }
    ]
    ```
    

#### Transport & Playlist Triggers

- `playback_start`, `playback_stop`, `playback_continue`: Fired on transport commands. These do not have dynamic values.
- `setlist_end`: Fired only when the entire playlist finishes.
  - **Dynamic Values**: `playlist_name`, `playlist_song_count`, `playlist_part_count`.
    

## License

GNU AGPLv3 License. See LICENSE file.