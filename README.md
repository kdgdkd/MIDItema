MIDItema: Live Performance Sequencer

A terminal-based, live performance song arranger and bar counter. MIDItema acts as a MIDI clock slave, stepping through song structures and broadcasting state changes via MIDI and OSC, giving you powerful, quantized control over your song's flow.

## Core Concept

In a typical linear workflow, your song arrangement is fixed to a timeline. MIDItema decouples your arrangement from the timeline. It listens to a master clock source (like a DAW, hardware sequencer, or our companion tool [MIDImaster](https://www.google.com/url?sa=E&q=https%3A%2F%2Fgithub.com%2Fpablomartin%2Fmidimaster)) but lets you decide the song's structure on the fly.

You can pre-define the sections of your song (Intro, Verse, Chorus, etc.) and then, during a live performance, jump between them, repeat them, or skip them on command. All your actions are musically quantized, ensuring every transition is perfectly in time. It's designed for improvisation, live remixing, and adding a dynamic, human element to electronic music performance.

## Features

- **Playlist / Setlist Mode:** Structure an entire live set by creating playlists that link multiple song files or even contain embedded song sections. Navigate between songs automatically or manually.
  
- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source.
  
- **Advanced Song & Playlist Structure:** Define your songs and playlists in simple, human-readable json5 files, which allows for comments. Specify parts, lengths, colors for both songs and parts, and complex repetition logic.
  

  - **Repetition Patterns:** Control exactly how parts repeat within a song.

- **Live Part & Song Navigation:** The core of MIDItema. Program quantized jumps to the next/previous part or song, restart the current section, or go to any specific part/song on command.
  
- **Dual Playback Mode (Loop/Song):** Toggle between two modes on the fly. **Loop Mode** respects the `repeat_pattern` of each part, allowing for loops and vamping. **Song Mode** overrides these patterns, forcing the arrangement to always advance linearly to the next part, perfect for progressing through a song's structure.
  
- **Quantized Actions:** All jumps are scheduled as a **pending action** and executed with musical precision on the next beat, bar, or larger musical divisions.

- **Cue Jumps & Dynamic Quantization:** Assign key parts to Cues for instant, one-press access via F-Keys (F1-F12) or MIDI CC#2. Repeatedly trigger a pending cue to dynamically shorten its quantization, allowing for expressive, on-the-fly transitions from a long musical phrase down to the next bar.
  
- **Comprehensive TUI (Terminal User Interface):** A clean, full-screen interface provides a clear overview:
  

  - **Song & Part Titles:** Clearly displays the current song and part names, with customizable colors.

  - **Playlist Status:** Shows your current position in the setlist (e.g., [2/5]).

  - **Bar & Beat Countdown:** A large counter shows bars and beats remaining until the next transition.

  - **Bar Counter:** A persistent Bar: XX/YY display shows your current position within the part.

  - **Step Sequencer:** A visual block display of the bars in the current part.

  - **Status Line:** Shows clock status, elapsed time, BPM, and MIDI source.

  - **Action Status:** Displays the global quantization mode and details of any pending action.

- **Flexible Control Scheme:** Control MIDItema from your keyboard or external MIDI messages.

  - **MIDI Control:** Map MIDI Program Change, Song Select, Note On, and Control Change messages for complete hands-free operation.

- **Extensive OSC Broadcasting:** Sends detailed OSC messages on part changes and at configurable rhythmic intervals (bar, 4-bar, 8-bar triggers).
  
- **MIDI Output & Forwarding:**
  

  - **Remote Transport:** Send MIDI Start/Stop commands to a master device.

  - **Program Change Output:** Send a PC message when a part starts.

  - **Song Select Output:** Send a Song Select message when a song starts.

- **Extensive OSC Broadcasting:**

  - **Song Change Messages:** Broadcasts the song name and index when a new song begins.

  - **Part Change Messages:** Broadcasts details of the part that is now beginning.

  - **Bar & Block Trigger Messages:** Sends messages at configurable rhythmic intervals.

- **External Configuration:** All I/O ports and OSC settings are defined in a single miditema.conf.json file.

## Installation

MIDItema is designed to run from a terminal and requires Python 3.

1. **Clone the repository:**

  ```

  git clone https://github.com/your-username/miditema.git

  cd miditema

  ```

2. **Install dependencies:**  

  It's recommended to use a Python virtual environment.

  ```

  # Create and activate a virtual environment (optional but recommended)

  python3 -m venv venv

  source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

  # Install the required packages

  pip install mido python-osc prompt-toolkit python-rtmidi json5

  ```

## Configuration

MIDItema uses json5 files for configuration, which allows for comments and more flexible syntax. There are two types of files: a main config file (miditema.conf.json) and the song/playlist files in the temas/ directory.

### 1. Main Configuration (miditema.conf.json)

This file, located in the root directory, defines all your MIDI and OSC connections. MIDItema uses partial string matching (case-insensitive) for port names, so you only need to provide a unique substring (e.g., "Clock" instead of "Arturia BeatStep Pro MIDI 1 (Clock In)").

**Full miditema.conf.json Example:**

```
// miditema.conf.json

// Main configuration for MIDI and OSC connections.

// JSON5 format allows for comments and trailing commas.

{

    // --- MIDI Clock and Transport ---

    "clock_source": "MasterClock",

    "transport_out": "DAW_Transport_In",



    // --- MIDI Control and Output ---

    "midi_configuration": {

        "device_in": "Controller_Port",

        "device_out": "Synth_Module_1",

        "channel_out": 1

    },



    // --- OSC (Open Sound Control) Output ---

    "osc_configuration": {

        "send": {

            "ip": "127.0.0.1",

            "port": 9000,

            "address": "/miditema/part/change",

            "address_song_change": "/miditema/song/change",

            "address_song_end": "/miditema/song/end",

            "bar_triggers": [

                { "block_size": 1, "address": "/miditema/trigger/bar" },

                { "block_size": 4, "address": "/miditema/trigger/block4" }

            ]

        }

    }

}
```

**Parameter Breakdown:**

- "clock_source": (Mandatory) A unique substring of the MIDI input port that sends the master MIDI clock and transport (Start/Stop) messages.
  
- "transport_out": (Optional) A substring of the MIDI output port to which MIDItema will send Start/Stop commands when you use the keyboard controls (Enter/Space). This allows MIDItema to act as a remote control for your master device.
  
- "midi_configuration": (Optional) This entire section enables advanced MIDI control and output.
  

  - "device_in": A substring of the MIDI input port for receiving control messages (Program Change, Control Change, etc.).

    - **Note:** If this is the same as "clock_source", MIDItema will use a single port for both clock and control. If it's different, it will open a dedicated second port.

  - "device_out": A substring of the MIDI output port for sending Program Change and Song Select messages.

  - "channel_out": The MIDI channel (1-16) on which to send Program Change messages. Defaults to 1 if omitted.

- "osc_configuration": (Optional) This section configures all OSC output.

  - "send":

    - "ip": The target IP address for OSC messages. Defaults to "127.0.0.1" (for the same machine).

    - "port": The target port for OSC messages. This is mandatory if you want to send any OSC data.

    - "address": The OSC address for **part change** messages.

    - "address_song_change": (Optional) The OSC address for **song change** messages, sent when a new song from a playlist is loaded.

    - "address_song_end": (Optional) The OSC address sent when a song finishes (either at the end of a single song, or before transitioning to the next one in a playlist).

    - "bar_triggers": (Optional) A list of rules for sending messages on rhythmic boundaries. Each rule is an object with:

      - "block_size" (integer): How many bars to count before sending a message.

      - "address" (string): The OSC address to use for this trigger.

### 2. Song and Playlist Files (temas/)

You can load two types of files: individual **Song files** or **Playlist files** that arrange multiple songs.

#### Song File Example

A standard song file defines a single piece of music.

```
// temas/my_song.json

{

    "song_name": "My Awesome Track",

    "color": "blue", // Optional: sets the color for the song title bar

    "time_signature": "4/4",

    "parts": [

        { "name": "Intro", "bars": 8, "color": "cyan", "repeat_pattern": false },

        { "name": "Verse", "bars": 16, "color": "green" },

        { "name": "Chorus", "bars": 16, "color": "red", "repeat_pattern": true }

    ]

}
```

- **color (at root level):** (Optional) Sets the background color for the song's title bar in the UI. Available colors: default, red, green, yellow, blue, magenta, cyan. If omitted, a default grey style is used.
  
- (El resto de parámetros de canción son correctos como están en tu versión actual).
  

#### Playlist File Example

A playlist file arranges multiple songs. It is identified by the presence of a "songs" key.

```
// temas/my_setlist.json

{

  "playlist_name": "My Live Set",

  "songs": [

    // 1. External Song: Referenced from another file

    { "filepath": "my_song.json" },



    // 2. Embedded Song: Defined directly inside the playlist

    {

      "song_name": "Ambient Interlude",

      "color": "magenta",

      "parts": [

        { "name": "Pad Drone", "bars": 8, "color": "cyan" },

        { "name": "Riser FX", "bars": 4, "color": "yellow" }

      ]

    },



    // 3. Another External Song

    { "filepath": "another_track.json" }

  ]

}
```

- **playlist_name**: (Optional) The name for the playlist. Defaults to the filename.
  
- **songs**: (Mandatory) A list of song objects. Each object can be:
  

  - **An external song reference:** { "filepath": "filename.json" }. MIDItema will load this file from the temas/ directory.

  - **An embedded song:** A full song object defined directly within the list, containing its own song_name, color, and parts.

- **mode**: (Optional) Sets the default playback mode for the playlist. Can be `"loop"` (respects `repeat_pattern`) or `"song"` (forces linear progression). This setting is overridden by the `--loop-mode` or `--song-mode` command-line arguments.

## Usage

1. **Start your master clock source.** This could be your DAW (e.g., Ableton Live, Logic Pro), a hardware sequencer, or a software clock like [MIDImaster](https://www.google.com/url?sa=E&q=https%3A%2F%2Fgithub.com%2Fpablomartin%2Fmidimaster). Ensure it is configured to send MIDI Clock.
  
2. **Configure miditema.conf.json** to listen to the correct MIDI ports for clock and control, and to send data to the correct output ports.
  
3. **Run MIDItema from your terminal.** You can either launch it and select a song from an interactive list, or specify a song file directly.
  

  ```

  # Run and select a song from the interactive list

  python miditema.py

  # Or, specify a song file directly (without the .json extension)

  python miditema.py my_song_file

  # Or, launch with a specific default quantization mode

  python miditema.py my_song_file --quant 8

  # Valid --quant values: bar, 4, 8, 16, 32, instant

  ```

4. **Start the master clock.** MIDItema will detect the clock, synchronize, and begin stepping through the song parts as defined in your JSON file.

## Controls

MIDItema can be controlled via computer keyboard or external MIDI messages. Most actions are scheduled as a **pending action** and executed with musical quantization.

### Keyboard Controls


| Key(s) | Action | Details / Quantization |
| --- | --- | --- |
| **Global Transport** |     |     |
| Space / Enter | Send Start/Stop | Sends a MIDI Start/Stop command immediately. |
| q / Ctrl+C | Quit | Exits the application cleanly. |
| **Part Navigation** |     |     |
| → / ← | Jump Next / Previous Part | Programs a relative jump within the current song. Uses the **global** quantize mode. |
| ↑   | Restart Part | Restarts the current part. Uses the **global** quantize mode. |
| . or , then [num] Enter | Go to Part | Jumps to a specific part number within the current song. Uses the **global** quantize mode. |
| **Playlist Navigation** |     |     |
| PageDown / PageUp | Next / Previous Song | Jumps to the next or previous song in the playlist. Uses the **global** quantize mode. |
| Home / End | Go to First / Last Song | Jumps to the first or last song in the playlist. Uses the **global** quantize mode. |
| **General Actions** |     |     |
| ↓   | Cancel Action | Immediately cancels any pending action. |
| r   | Toggle Playback Mode | Switches between Loop Mode (respects part repeats) and Song Mode (forces linear progression). |
| **Quick Jumps (Fixed Quantization)** |     |     |
| 0 - 3 | Quick Jump +1 | Jumps to the next part with fixed quantization (Next Bar, Next 4, Next 8, Next 16). |
| **Global Quantize Mode Selection** |     |     |
| 4 - 9 | Set Global Quantize | Sets the global mode (Next 4, Next 8, Next 16, Next Bar, End of Part, Instant). |

### MIDI Controls

To use MIDI controls, configure "device_in" in miditema.conf.json.

| Message | Action | Details / Quantization |
| --- | --- | --- |
| **Absolute Jumps** |     |     |
| **Program Change** N | Go to Part N+1 | Jumps to a specific part in the current song. Uses the **global** quantize mode. |
| **Song Select** N | Go to Song N+1 | Jumps to a specific song in the current playlist. Uses the **global** quantize mode. |
| **Relative Navigation** |     |     |
| **Note On** 125 | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| **Note On** 124 | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| **Note On** 127 | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| **Note On** 126 | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |

#### General Functions via CC #0

All actions below are triggered by sending a Control Change message on **CC #0** with a specific value.

| CC #0 Value | Action | Details / Quantization |
| --- | --- | --- |
| 0 - 3 | Quick Jump +1 | Jumps to the next part with fixed quantization (Instant, Next Bar, Next 8, Next 16). |
| 4 - 9 | Set Global Quantize | Sets the global mode (`4`:Next 4, `5`:Next 8, `6`:Next 16, `7`:Next Bar, `8`:End of Part, `9`:Instant). |
| 10  | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| 11  | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| 12  | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |
| 13  | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| 14  | Go to First Song | Jumps to the first song in the playlist. Uses the **global** quantize mode. |
| 15  | Go to Last Song | Jumps to the last song in the playlist. Uses the **global** quantize mode. |
| 16  | Restart Song | Restarts the current song from its first part. Uses the **global** quantize mode. |
| 17  | Restart Part | Restarts the current part. Uses the **global** quantize mode. |
| 18  | Cancel Action | Immediately cancels any pending action. |
| 19  | Toggle Playback Mode | Switches between Loop Mode and Song Mode. |

#### Global Part Jumps (CC #1)

This is a powerful feature for navigating large setlists. It allows you to jump to any part across your entire playlist with a single message.

- **Action:** Jump to a specific part in the entire setlist.
- **Details:** The `value` of the CC #1 message (0-127) corresponds to the global, zero-based index of the part you want to jump to. MIDItema calculates which song and part this index corresponds to. - `CC #1, Value 0`: Jumps to the first part of the first song. - `CC #1, Value 1`: Jumps to the second part of the first song (if it exists). - If the first song has 5 parts, `CC #1, Value 5` will jump to the first part of the *second* song. - **Quantization:** Uses the currently active **global** quantize mode.

### Cue Jumps (F1-F12 and CC #2)

Cues provide a fast and expressive way to jump to pre-defined key parts of your song. This system also introduces **dynamic quantization**, allowing you to accelerate a jump on the fly.

- **Action:** Jump to a specific part marked as a "Cue".
  
- **Defining Cues:** In your song file, add a "cue": N key-value pair to any part you want to access directly. N is the cue number.
  
  ```
  "parts": [
    { "name": "Verse", "bars": 16, "cue": 1 },
    { "name": "Chorus", "bars": 16, "cue": 2 },
    { "name": "Drop", "bars": 32, "cue": 100 }
  ]
  ```
  
- **Triggering Cues:**
  
  - **F-Keys:** Pressing F1 through F12 on your keyboard will trigger cue: 1 through cue: 12.
    
  - **MIDI CC #2:** Sending a Control Change message on **CC #2** with a value of N will trigger cue: N. This allows access to up to 128 cues per song.
    

#### Dynamic Quantization

This is a unique feature of Cue Jumps. Repeatedly triggering the same cue while it is pending will speed up its quantization.

- **First Trigger:** The jump is scheduled using the current **global** quantize mode (e.g., Next 8).
  
- **Second Trigger:** The pending jump's quantization is halved (e.g., from Next 8 to Next 4).
  
- **Subsequent Triggers:** Each trigger continues to halve the quantization until it reaches the fastest level (Next Bar).
  
- **This change is temporary** and only affects the current pending cue jump. The global quantize mode remains unchanged. The TUI will display the dynamic quantization in real-time.

## MIDI Output

MIDItema can send MIDI messages to control other devices in your setup.

### Program Change Output

- **Trigger:** Sent when a new **part** of a song begins.
  
- **Message:** A program_change message with the program number equal to the part's zero-based index (Part 1 sends PC 0, Part 2 sends PC 1, etc.).
  
- **Configuration:** Requires "device_out" and "channel_out" to be set in midi_configuration.
  

### Song Select Output

- **Trigger:** Sent when a new **song** from a playlist is loaded.
  
- **Message:** A song_select message with the song number equal to the song's zero-based index in the playlist.
  
- **Configuration:** Requires "device_out" to be set in midi_configuration. It is sent on the same port as Program Change messages.
  

### Remote Transport

- **Trigger:** Sent immediately when using the Space/Enter key in the TUI.
  
- **Message:** A MIDI start or stop command.
  
- **Configuration:** Requires "transport_out" to be set.
  

#### OSC Integration

This is a core feature for integrating MIDItema with other software. All OSC messages are sent to the ip and port defined in miditema.conf.json.

### Song Change Message

- **Address:** Defined by the "address_song_change" key.
  
- **Trigger:** Sent at the exact moment a new **song** from a playlist is loaded.
  
- **Arguments:**
  

  1. **Song Name** (string): The name of the song that is about to begin.

  2. **Song Index** (integer): The zero-based index of this song in the playlist.

- **Example:** /miditema/song/change "Main Track" 1

### Part Change Message

- **Address:** Defined by the "address" key.
  
- **Trigger:** Sent at the exact moment a new **part** of a song becomes active.
  
- **Arguments:**
  

  1. **Song Name** (string): The name of the currently loaded song.

  2. **Part Name** (string): The name of the part that is now beginning.

  3. **Part Bars** (integer): The total number of bars in this new part.

  4. **Part Index** (integer): The zero-based index of this part in the song's parts array.

- **Example:** /miditema/part/change "Main Track" "Verse 2" 16 2

### Song End Message

- **Address:** Defined by the "address_song_end" key.
  
- **Trigger:** Sent when the entire playlist finishes.
  
- **Arguments:**
  

  1. **Song Name** (string): The name of the last song that has just ended.

- **Example:** /miditema/song/end "Outro Track"

  /miditema/song/end "Live Set"

### Bar & Block Trigger Messages

These are powerful, rhythmically-timed messages configured via the "bar_triggers" list in miditema.conf.json. They allow you to synchronize external events to the beat grid of your song.

- **Address:** Defined by the "address" key within each trigger object.
  
- **Trigger:** Sent at the end of a bar, if that bar number is a multiple of the trigger's "block_size".
  
- **Arguments:** Each trigger message contains two arguments:
  

  1. **Completed Bar Number** (integer): The number of the bar that just finished within the current part (1-based).

  2. **Completed Block Number** (integer): The number of blocks of this size that have been completed. Calculated as Completed Bar Number / block_size.

**Example bar_triggers Configuration:**

```
"bar_triggers": [

    { "block_size": 1, "address": "/miditema/trigger/bar" },

    { "block_size": 4, "address": "/miditema/trigger/block4" }

]
```

**Resulting OSC Messages:**

- At the end of bar 1: /miditema/trigger/bar 1 1
  
- At the end of bar 2: /miditema/trigger/bar 2 2
  
- At the end of bar 3: /miditema/trigger/bar 3 3
  
- At the end of bar 4:
  

  - /miditema/trigger/bar 4 4

  - /miditema/trigger/block4 4 1 (This is the **1st** block of 4 bars)

- At the end of bar 8:

  - /miditema/trigger/bar 8 8

  - /miditema/trigger/block4 8 2 (This is the **2nd** block of 4 bars)

## License

GNU AGPLv3 License. See LICENSE file.