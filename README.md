# MIDItema: Live Performance Sequencer

A terminal-based, live performance song arranger and bar counter. MIDItema acts as a MIDI clock slave, stepping through song structures and broadcasting state changes via MIDI and OSC, giving you powerful, quantized control over your song's flow.

## Core Concept

MIDItema is a master sequencer and automation hub for live performance. Its core purpose is to structure your entire set into a clear hierarchy: **Setlists** are composed of **Songs**, and Songs are composed of **Parts**.

Acting as a MIDI clock slave, it listens to an external clock source and provides clear visual feedback on your current position within the setlist. As it progresses through the song structure, its main job is to send precisely timed **MIDI events and OSC messages**. This transforms MIDItema into the central brain of your performance, allowing you to **synchronize automations** in other programs or external secuencers, trigger visual effects, change synth patches, and control lighting rigs.

It also facilitates live performance by giving you powerful, quantized navigation controls to create loops or jump between parts and songs. Furthermore, it allows you to define global **Cues**—direct access points to critical parts across your entire setlist—making complex, non-linear jumps reliable and perfectly quantized.

(You could use [MIDImod](https://github.com/kdgdkd/MIDImod) to read MIDItema's OSC messages, transform them into any kind of MIDI event, and route it to your preferred destination; you could send to your sequencer Song Select events upon song changes, and Program Change for part changes, or automate new CC values for your synth for each song or a particular part of a song.)

## Features

- **Playlist / Setlist Mode:** Structure an entire live set in multiple ways: create explicit **Playlist files** that link songs, or simply **load a directory** of song files on the fly to generate an instant playlist. Navigate between songs automatically or manually.
- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source.
- **Advanced Song & Playlist Structure:** Define your songs and playlists in simple, human-readable json5 files, which allows for comments. Specify parts, lengths, colors for both songs and parts, and complex repetition logic.
 - **Repetition Patterns:** Control exactly how parts repeat within a song.
 - **Follow Actions:** Define complex, probabilistic, or conditional logic for what happens automatically after a part finishes, enabling dynamic and non-linear song arrangements.
- **Live Part & Song Navigation:** The core of MIDItema. Program quantized jumps to the next/previous part or song, restart the current section, or go to any specific part/song on command.
- **Dual Playback Mode (Loop/Song):** Toggle between two modes on the fly. **Loop Mode** respects the `repeat_pattern` of each part, allowing for loops and vamping. **Song Mode** overrides these patterns, forcing the arrangement to always advance linearly to the next part, perfect for progressing through a song's structure.
- **Quantized Actions:** All jumps are scheduled as a **pending action** and executed with musical precision on the next beat, bar, or larger musical divisions.
- **Global Cues & Dynamic Quantization:** Assign key parts across your **entire setlist** to Cues for instant, one-press access. Trigger them via F-Keys (F1-F12) or MIDI CC#2 to jump to any designated part, in any song, at any time. Repeatedly trigger a pending cue to dynamically shorten its quantization, allowing for expressive, on-the-fly transitions.
- **Comprehensive TUI (Terminal User Interface):** A clean, full-screen interface provides a clear overview:
 - **Song & Part Titles:** Clearly displays the current song and part names, with customizable colors.
 - **Playlist Status:** Shows your current position in the setlist (e.g., [2/5]).
 - **Bar & Beat Countdown:** A large counter shows bars and beats remaining until the next transition.
 - **Bar Counter:** A persistent Bar: XX/YY display shows your current position within the part.
 - **Step Sequencer:** A visual block display of the bars in the current part.
 - **Status Line:** Shows clock status, elapsed time, BPM, and MIDI source.
 - **Action Status:** Displays the global quantization mode and details of any pending action.
- **Flexible Control Scheme:** Control MIDItema from your keyboard or external MIDI messages.
 - **MIDI Control:** Map MIDI Program Change, Song Select, Note On, and Control Change messages for complete hands-free operation.
- **Extensive OSC Broadcasting:** Sends detailed OSC messages on part changes and at configurable rhythmic intervals (bar, 4-bar, 8-bar triggers).
- **MIDI Output & Forwarding:**
 - **Remote Transport:** Send MIDI Start/Stop commands to a master device.
 - **Program Change Output:** Send a PC message when a part starts.
 - **Song Select Output:** Send a Song Select message when a song starts.
- **Extensive OSC Broadcasting:**
 - **Song Change Messages:** Broadcasts the song name and index when a new song begins.
 - **Part Change Messages:** Broadcasts details of the part that is now beginning.
 - **Bar & Block Trigger Messages:** Sends messages at configurable rhythmic intervals.
- **External Configuration:** All I/O ports and OSC settings are defined in a single miditema.conf.json file. 
## Installation 
MIDItema is designed to run from a terminal and requires Python 3. 
1. **Clone the repository:**
 ```bash
 git clone https://github.com/your-username/miditema.git
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
MIDItema uses json5 files for configuration, which allows for comments and more flexible syntax. There are two types of files: a main config file (miditema.conf.json) and the song/playlist files in the `temas/` directory.
### 1. Main Configuration (miditema.conf.json)
This file, located in the root directory, defines all your MIDI and OSC connections. MIDItema uses partial string matching (case-insensitive) for port names, so you only need to provide a unique substring (e.g., "Clock" instead of "Arturia BeatStep Pro MIDI 1 (Clock In)").

**Full miditema.conf.json Example:** 
```json
// miditema.conf.json
// Configuración principal para conexiones MIDI y OSC.
{
 // --- MIDI Clock y Transporte ---
 "clock_source": "KeyStep",
 "transport_out": "TPT", 
// --- Control MIDI y Salida ---
 "midi_configuration": {
 "device_in": "MIDItema",
 "device_out": "Synth_Module_1",
 // El canal ahora se define como 0-15.
 "channel_out": 0,
 // Envía los mensajes de cambio de parte X beats antes.
 "part_change_advanced": 1
 }, 
// --- Salida OSC (Open Sound Control) ---
 "osc_configuration": {
 // "send" ahora es una LISTA de destinos. Puedes tener uno o varios.
 "send": [
 {
 // Destino 1: Aplicación principal
 "ip": "127.0.0.1",
 "port": 9000,
 "address_part_change": "/miditema/part/change",
 "address_part_change_advanced": "/miditema/part/change_advanced",
 "address_song_change": "/miditema/song/change",
 "address_song_end": "/miditema/song/end",
 "bar_triggers": [
 { "block_size": 1, "address_bar_triggers": "/miditema/trigger/bar" },
 { "block_size": 4, "address_bar_triggers": "/miditema/trigger/block4" }
 ]
 },
 {
 // Destino 2: Otra aplicación (ej. control de luces)
 "ip": "127.0.0.1",
 "port": 9001,
 "address_part_change": "/luces/escena"
 }
 ]
 }
}
````

**Parameter Breakdown:**

- "clock_source": (Mandatory) A unique substring of the MIDI input port that sends the master MIDI clock and transport (Start/Stop) messages.
  
- "transport_out": (Optional) A substring of the MIDI output port to which MIDItema will send Start/Stop commands when you use the keyboard controls (Enter/Space). This allows MIDItema to act as a remote control for your master device.
  
- "midi_configuration": (Optional) This entire section enables advanced MIDI control and output.
  
  - "device_in": A substring of the MIDI input port for receiving control messages (Program Change, Control Change, etc.).
    
    - **Note:** If this is the same as "clock_source", MIDItema will use a single port for both clock and control. If it's different, it will open a dedicated second port.
  - "device_out": A substring of the MIDI output port for sending Program Change and Song Select messages.
    
  - "channel_out": The MIDI channel (0-15) on which to send Program Change messages. Defaults to 0 if omitted.
    
  - "part_change_advanced": (Optional) An integer that specifies how many beats before the end of a part the change messages (MIDI PC, OSC part change, etc.) should be sent. If set to 1, messages are sent on the last beat. Defaults to 0 (messages are sent exactly when the new part starts).
    
- "osc_configuration": (Optional) This section configures all OSC output.
  
  - "send": (Optional) This key now holds a **list** of destination objects. You can define one or multiple destinations, and each will be handled independently. Each object in the list contains:
    
    - "ip": The target IP address for OSC messages. Defaults to "127.0.0.1".
      
    - "port": The target port for OSC messages. This is mandatory if you want to send any OSC data.
      
    - "address_part_change": (Optional) The OSC address for **part change** messages.
      
    - "address_song_change": (Optional) The OSC address for **song change** messages.
      
    - "address_part_change_advanced": (Optional) The OSC address for **advanced part change** messages, sent ahead of time according to the part_change_advanced setting.
      
    - "address_song_end": (Optional) The OSC address sent only when the entire playlist or single song playback finishes completely.
      
    - "bar_triggers": (Optional) A list of rules for sending messages on rhythmic boundaries. Each rule is an object with:
      
      - "block_size" (integer): How many bars to count before sending a message.
        
      - "address_bar_triggers" (string): The OSC address to use for this specific trigger.
        

### 2. Song and Playlist Files (temas/)

MIDItema can load content in three ways: as individual **Song files**, as **Playlist files** that arrange multiple songs, or by loading an entire **Directory** of songs as a virtual playlist.

#### Song File Example

A standard song file defines a single piece of music.

```
{
    "song_name": "Genocide in Palestine",
    "color": "blue",
    "time_signature": "4/4",
    "parts": [
        { "name": "Intro - OUR land", "bars": 8, "color": "cyan", "repeat_pattern": false },
        { "name": "Verse - Nazis in sheep's clothing", "bars": 16, "color": "green" },
        { "name": "Chorus - Free Palestine", "bars": 16, "color": "yellow", "repeat_pattern": true, "cue": 1 },
        { 
          "name": "Outro - We'll never forget", "bars": 8, "color": "red",
          "follow_action": { "action": "first_part" }
        }
    ]
}
```

**Root-Level Parameters:**

- **song_name**: (Optional) The name of the song. If omitted, the filename (without the extension) is used.
  
- **color**: (Optional) Sets the background color for the song's title bar in the UI. Available colors: default, red, green, yellow, blue, magenta, cyan.
  
- **time_signature**: (Optional) The time signature of the song (e.g., "4/4", "3/4"). Only the numerator is currently used to calculate the number of beats per bar. Defaults to "4/4".
  
- **time_division**: (Optional) Defines the "beat" of the song relative to the MIDI clock's 24 pulses per quarter note (PPQN).
  
  - "1/4": A song beat is a quarter note (24 ticks). This is the default.
    
  - "1/8": A song beat is an eighth note (12 ticks).
    
  - "1/16": A song beat is a sixteenth note (6 ticks).
    
- **parts**: (Mandatory) A list of part objects that define the structure of the song.
  

**Part-Level Parameters (within the parts list):**

- **name** (string): The name of the part (e.g., "Verse 1").
  
- **bars** (integer): The length of the part in bars. A part with 0 bars will be skipped.
  
- **color** (string, optional): Sets the color for this part's title bar and for its entry in the >> Next Part display. Uses the same color palette as the song-level color.
  
- **repeat_pattern** (optional): Controls the looping behavior of the part when in **Loop Mode**.
  
  - **true or omitted:** The part will repeat indefinitely until a jump is triggered.
    
  - **false:** The part will play only once on the first pass through the song structure.
    
  - **[true, false, true, true] (list of booleans):** Defines a complex pattern. The part will play or be skipped based on the boolean at the current pass index (pass_count % list_length).
    
- **cue** (integer, optional): Assigns a global cue number (e.g., 1-128) to this part. This makes the part directly accessible from anywhere in the playlist via F-Keys or MIDI CC#2. Each cue number should be unique across the entire setlist to avoid ambiguity.
  
- **follow_action** (object, optional): Controls what happens automatically after a part finishes playing, overriding the default linear progression. This is a powerful tool for creating dynamic arrangements.
  
  - **probability** (float, optional): A value between 0.0 and 1.0 that determines the chance of the action being executed. If the check fails, the part will repeat itself. Defaults to 1.0 (100% chance).
    
  - **action** (string or object, optional): The action to perform. Defaults to "next".
    
    | Action Value | Type | Description |
    | --- | --- | --- |
    | **Basic Navigation** | | |
    | `"next"` | string | Proceeds to the next valid part according to the current playback mode (Loop/Song). This is the default behavior. |
    | `"prev"` | string | Proceeds to the previous valid part. |
    | `"repeat"` | string | Repeats the current part. |
    | **Absolute Jumps** | | |
    | `{ "jump_to_part": N }` | object | Jumps directly to the part at index N (0-based) in the current song. |
    | `{ "jump_to_cue": N }` | object | Jumps to the part marked with `"cue": N` in the current song. |
    | `{ "random_part": [N, M] }` | object | Jumps to a randomly chosen part from the provided list of indices. |
    | **Song Navigation** | | |
    | `"first_part"` | string | Jumps to the first valid part of the current song. |
    | `"last_part"` | string | Jumps to the last valid part of the current song. |
    | **Playlist Navigation** | | (These actions require a playlist to be active) |
    | `"next_song"` | string | Loads the next song in the playlist. |
    | `"prev_song"` | string | Loads the previous song in the playlist. |
    | `"first_song"` | string | Loads the first song in the playlist. |
    | `"last_song"` | string | Loads the last song in the playlist. |
    | **Mode Control** | | |
    | `"loop_part"` | string | Activates a manual loop on the current part. The part will repeat indefinitely until the user cancels it or triggers another jump. |
    | `"song_mode"` | string | Switches the global playback mode to **Song Mode** and then proceeds to the next part. |
    | `"loop_mode"` | string | Switches the global playback mode to **Loop Mode** and then proceeds to the next part. |
    
    **Example:**
    ```json
    { 
      "name": "Verse", "bars": 8,
      "follow_action": {
        "action": { "jump_to_cue": 5 },
        "probability": 0.8 
      }
    }
    // After this part, there's an 80% chance of jumping to cue 5.
    // If not, the part repeats.
    ```

  

#### Playlist File Example

A playlist file arranges multiple songs. It is identified by the presence of a "songs" key.

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
        { "name": "Pad Drone", "bars": 8, "color": "cyan" },
        { 
          "name": "Riser FX", "bars": 4, "color": "yellow",
          "follow_action": { "action": "next_song" }
        }
      ]
    },

    // 3. Another External Song
    { "filepath": "another_track.json" }
  ]
}
```

- **playlist_name**: (Optional) The name for the playlist. Defaults to the filename.
  
- **songs**: (Mandatory) A list of song objects. Each object can be:
  
  - **An external song reference:** { "filepath": "filename.json" }. MIDItema will load this file from the temas/ directory.
    
  - **An embedded song:** A full song object defined directly within the list, containing its own song_name, color, and parts.
    
- **mode**: (Optional) Sets the default playback mode for the playlist. Can be "loop" (respects repeat_pattern) or "song" (forces linear progression). This setting is overridden by the --loop-mode or --song-mode command-line arguments.
  

## Usage

1. **Start your master clock source.** This could be your DAW, a hardware sequencer, or a software clock like [MIDImaster](https://github.com/kdgdkd/MIDImaster). Ensure it is configured to send MIDI Clock.
  
2. **Configure miditema.conf.json** to listen to the correct MIDI ports for clock and control, and to send data to the correct output ports.
  
3. **Run MIDItema from your terminal.** It can be launched in several ways depending on your needs:

    -   **Interactive Mode (No arguments):** MIDItema will show a list of all `.json` files in the `temas/` directory for you to choose from.
        ```bash
        python miditema.py
        ```

    -   **File Mode (Provide a filename):** Loads a specific song or playlist file from the `temas/` directory. You can provide the name with or without the `.json` extension.
        ```bash
        # Both of these commands work
        python miditema.py my_song_file
        python miditema.py my_setlist.json
        ```

    -   **Directory Mode (provide a path ending in `/` or `\`):** Loads all `.json` files from the specified directory, sorted alphabetically, as a virtual playlist.
        ```bash
        # Loads all songs from the 'my_live_set' folder
        python miditema.py my_live_set/
        ```
  

        You can also combine file/directory mode with command-line arguments:
        ```bash
        # Launch with a specific default quantization mode
        python miditema.py my_song_file --quant 8
        # Valid --quant values: bar, 4, 8, 16, 32, instant
        ```

4.  **Start the master clock.** MIDItema will detect the clock, synchronize, and begin stepping through the song parts as defined.

## Controls

MIDItema can be controlled via computer keyboard or external MIDI messages. Most actions are scheduled as a **pending action** and executed with musical quantization.

### Keyboard Controls

| Key(s) | Action | Details / Quantization |
| --- | --- | --- |
| **Global Transport** |     |     |
| Space / Enter | Send Start/Stop | Sends a MIDI Start/Stop command immediately. |
| q / Ctrl+C | Quit | Exits the application cleanly. |
| **Part Navigation** |     |     |
| → / ← | Jump Next / Previous Part | Programs a relative jump within the current song. Uses the **global** quantize mode. |
| ↑   | Toggle Part Loop | Toggles a loop on the currently playing part. Pressing it again on the same part cancels the loop. |
| . or , then [num] Enter | Go to Part | Jumps to a specific part number within the current song. Uses the **global** quantize mode. |
| **Playlist Navigation** |     |     |
| PageDown / PageUp | Next / Previous Song | Jumps to the next or previous song in the playlist. Uses the **global** quantize mode. |
| Home / End | Go to First / Last Song | Jumps to the first or last song in the playlist. Uses the **global** quantize mode. |
| **General Actions** |     |     |
| ↓   | Cancel Action | Immediately cancels any pending action. |
| m   | Toggle Playback Mode | Switches between Loop Mode (respects part repeats) and Song Mode (forces linear progression). |
| **Quick Jumps (Fixed Quantization)** |     |     |
| 0 - 3 | Quick Jump +1 | Jumps to the next part with fixed quantization (Next Bar, Next 4, Next 8, Next 16). |
| **Global Quantize Mode Selection** |     |     |
| 4 - 9 | Set Global Quantize | Sets the global mode (Next 4, Next 8, Next 16, Next Bar, End of Part, Instant). |

### MIDI Controls

To use MIDI controls, configure "device_in" in miditema.conf.json.

| Message | Action | Details / Quantization |
| --- | --- | --- |
| **Absolute Jumps** |     |     |
| **Program Change** N | Go to Part N+1 | Jumps to a specific part in the current song. Uses the **global** quantize mode. |
| **Song Select** N | Go to Song N+1 | Jumps to a specific song in the current playlist. Uses the **global** quantize mode. |
| **Relative Navigation** |     |     |
| **Note On** 125 | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| **Note On** 124 | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| **Note On** 127 | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| **Note On** 126 | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |

#### General Functions via CC #0

All actions below are triggered by sending a Control Change message on **CC #0** with a specific value.

| CC #0 Value | Action | Details / Quantization |
| --- | --- | --- |
| 0 - 3 | Quick Jump +1 | Jumps to the next part with fixed quantization (Instant, Next Bar, Next 8, Next 16). |
| 4 - 9 | Set Global Quantize | Sets the global mode (4:Next 4, 5:Next 8, 6:Next 16, 7:Next Bar, 8:End of Part, 9:Instant). |
| 10  | Previous Part | Jumps to the previous part. Uses the **global** quantize mode. |
| 11  | Next Part | Jumps to the next part. Uses the **global** quantize mode. |
| 12  | Previous Song | Jumps to the previous song in the playlist. Uses the **global** quantize mode. |
| 13  | Next Song | Jumps to the next song in the playlist. Uses the **global** quantize mode. |
| 14  | Go to First Song | Jumps to the first song in the playlist. Uses the **global** quantize mode. |
| 15  | Go to Last Song | Jumps to the last song in the playlist. Uses the **global** quantize mode. |
| 16  | Toggle Part Loop | Toggles a loop on the currently playing part. |
| 17  | Restart Part | Restarts the current part. Uses the **global** quantize mode. |
| 18  | Cancel Action | Immediately cancels any pending action. |
| 19  | Toggle Playback Mode | Switches between Loop Mode and Song Mode. |
| 20  | Restart Song | Restarts the current song from its first part. Uses the **global** quantize mode. |

#### Global Navigation (CC #1 & Cues)

These are powerful features for navigating large setlists, allowing you to jump to any part across your entire playlist. **These features require a playlist to be active.**

| Trigger | Action | Details | Quantization |
| --- | --- | --- | --- |
| **CC #1** (Value N) | Go to Global Part N | Jumps to a part based on its absolute index in the setlist (0-127). If song 1 has 5 parts, value 5 jumps to the first part of song 2. | Global |
| **F1-F12** | Go to Cue 1-12 | Jumps to the part marked with the corresponding "cue": N number in any song file within the playlist. | Dynamic |
| **CC #2** (Value N) | Go to Cue N | Jumps to the part marked with "cue": N. Allows access to 128 cues. | Dynamic |

**Dynamic Quantization (for Cues only):**

This is a unique feature of Cue Jumps. Repeatedly triggering the same cue while it is pending will speed up its quantization for that specific jump.

- **First Trigger:** The jump is scheduled using the current **global** quantize mode (e.g., Next 8).
  
- **Second Trigger:** The pending jump's quantization is halved (e.g., from Next 8 to Next 4).
  
- **Subsequent Triggers:** Each trigger continues to halve the quantization until it reaches the fastest level (Next Bar).
  
- The TUI will display the dynamic quantization in real-time.
  

## MIDI Output

MIDItema can send MIDI messages to control other devices in your setup.

### Program Change Output

- **Trigger:** Sent when a new **part** of a song begins.
  
- **Message:** A program_change message with the program number equal to the part's zero-based index (Part 1 sends PC 0, Part 2 sends PC 1, etc.).
  
- **Configuration:** Requires "device_out" and "channel_out" to be set in midi_configuration.
  

### Song Select Output

- **Trigger:** Sent when a new **song** from a playlist is loaded.
  
- **Message:** A song_select message with the song number equal to the song's zero-based index in the playlist.
  
- **Configuration:** Requires "device_out" to be set in midi_configuration. It is sent on the same port as Program Change messages.
  

### Remote Transport

- **Trigger:** Sent immediately when using the Space/Enter key in the TUI.
  
- **Message:** A MIDI start or stop command.
  
- **Configuration:** Requires "transport_out" to be set.
  

## OSC Integration

This is a core feature for integrating MIDItema with other software. All OSC messages are sent to the destinations defined in miditema.conf.json.

### Song Change Message

- **Address:** Defined by the "address_song_change" key.
  
- **Trigger:** Sent at the exact moment a new **song** from a playlist is loaded (or earlier if part_change_advanced is set).
  
- **Arguments:**
  
  1. **Song Name** (string): The name of the song that is about to begin.
    
  2. **Song Index** (integer): The zero-based index of this song in the playlist.
    
- **Example:** /miditema/song/change "Main Track" 1
  

### Part Change Message

- **Address:** Defined by the "address_part_change" key.
  
- **Trigger:** Sent at the exact moment a new **part** of a song becomes active.
  
- **Arguments:**
  
  1. **Song Name** (string): The name of the currently loaded song.
    
  2. **Part Name** (string): The name of the part that is now beginning.
    
  3. **Part Bars** (integer): The total number of bars in this new part.
    
  4. **Part Index** (integer): The zero-based index of this part in the song's parts array.
    
- **Example:** /miditema/part/change "Main Track" "Verse 2" 16 2
  

### Advanced Part Change Message

- **Address:** Defined by the "address_part_change_advanced" key.
  
- **Trigger:** Sent before a new part begins, according to the part_change_advanced setting in midi_configuration.
  
- **Arguments:**
  
  1. **Song Name** (string): The name of the song containing the upcoming part.
    
  2. **Part Name** (string): The name of the part that is about to begin.
    
  3. **Part Bars** (integer): The total number of bars in the upcoming part.
    
  4. **Part Index** (integer): The zero-based index of the upcoming part.
    
  5. **Advanced Beats** (integer): The number of beats of advance notice, as defined by part_change_advanced.
    
- **Example:** /miditema/part/prepare "Main Track" "Chorus" 16 2 1 (Sent 1 beat in advance)
  

### Song End Message

- **Address:** Defined by the "address_song_end" key.
  
- **Trigger:** Sent only when the entire playlist finishes or when a single song (not in a playlist) finishes. It is **not** sent during transitions between songs in a playlist.
  
- **Arguments:**
  
  1. **Song Name** (string): The name of the last song that has just ended.
- **Example:** /miditema/song/end "Outro Track"
  

### Bar & Block Trigger Messages

These are powerful, rhythmically-timed messages configured via the "bar_triggers" list.

- **Address:** Defined by the "address_bar_triggers" key within each trigger object.
  
- **Trigger:** Sent at the end of a bar, if that bar number is a multiple of the trigger's "block_size".
  
- **Arguments:** Each trigger message contains two arguments:
  
  1. **Completed Bar Number** (integer): The number of the bar that just finished within the current part (1-based).
    
  2. **Completed Block Number** (integer): The number of blocks of this size that have been completed. Calculated as Completed Bar Number / block_size.
    

**Example bar_triggers Configuration:**

```
"bar_triggers": [
    { "block_size": 1, "address_bar_triggers": "/miditema/trigger/bar" },
    { "block_size": 4, "address_bar_triggers": "/miditema/trigger/block4" }
]
```

**Resulting OSC Messages:**

- At the end of bar 1: /miditema/trigger/bar 1 1
  
- At the end of bar 2: /miditema/trigger/bar 2 2
  
- At the end of bar 3: /miditema/trigger/bar 3 3
  
- At the end of bar 4:
  
  - /miditema/trigger/bar 4 4
    
  - /miditema/trigger/block4 4 1 (This is the **1st** block of 4 bars)
    
- At the end of bar 8:
  
  - /miditema/trigger/bar 8 8
    
  - /miditema/trigger/block4 8 2 (This is the **2nd** block of 4 bars)
    

## License

GNU AGPLv3 License. See LICENSE file.