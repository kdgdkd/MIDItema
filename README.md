MIDItema: Live Performance Sequencer

A terminal-based, live performance song arranger and bar counter. MIDItema acts as a MIDI clock slave, stepping through song structures and broadcasting state changes via MIDI and OSC, giving you powerful, quantized control over your song's flow.

## Core Concept

In a typical linear workflow, your song arrangement is fixed to a timeline. MIDItema decouples your arrangement from the timeline. It listens to a master clock source (like a DAW, hardware sequencer, or our companion tool [MIDImaster](https://www.google.com/url?sa=E&q=https%3A%2F%2Fgithub.com%2Fpablomartin%2Fmidimaster)) but lets you decide the song's structure on the fly.

You can pre-define the sections of your song (Intro, Verse, Chorus, etc.) and then, during a live performance, jump between them, repeat them, or skip them on command. All your actions are musically quantized, ensuring every transition is perfectly in time. It's designed for improvisation, live remixing, and adding a dynamic, human element to electronic music performance.

## Features

- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source, ensuring it's always in time with the rest of your gear.
  
- **Advanced Song Structure:** Define your songs in simple, human-readable JSON files. Specify parts, their lengths, their color in the UI, and even complex repetition logic.
  
  - **Repetition Patterns:** Control exactly how parts repeat. Play a section only once, every time, or in complex patterns like "play twice, then skip twice."
- **Live Part Navigation:** The core of MIDItema. Program jumps to the next or previous part, restart the current section, or go to any specific part of the song. Actions can be stacked (e.g., pressing → three times schedules a +3 jump).
  
- **Quantized Actions:** Jumps are never jarring. They are scheduled as a **pending action** and executed with musical precision. Align your transitions to the next beat, the next bar, or the next 4, 8, 16, or 32-bar boundary.
  
- **Comprehensive TUI (Terminal User Interface):** A clean, full-screen interface provides a clear overview of the performance state:
  
  - **Part Name & Info:** Clearly displays the current part's name and its total length in bars.
    
  - **Bar & Beat Countdown:** A large, centered counter shows bars and beats remaining until the next transition point.
    
  - **Bar Counter:** A persistent Bar: XX/YY display shows your current position within the part.
    
  - **Step Sequencer:** A visual block display of the bars in the current part, showing progress and highlighting upcoming jump points.
    
  - **Status Line:** Shows clock status (PLAYING, STOPPED), elapsed time, current BPM, and the MIDI clock source.
    
  - **Action Status:** Displays the currently selected global quantization mode and details of any pending action.
    
- **Flexible Control Scheme:** Control MIDItema from your computer keyboard or via external MIDI messages.
  
  - **Keyboard Control:** Use single-key presses for both quick, fixed-quantization jumps and for navigation using a global, user-defined quantization mode.
    
  - **MIDI Control:** Map MIDI Program Change (PC) and Control Change (CC) messages from an external controller for hands-free operation. Jump to specific parts, navigate sequentially, change quantize modes, and more.
    
- **Extensive OSC Broadcasting:** Sends detailed OSC messages for deep integration with other creative software (Resolume, TouchDesigner, VCV Rack, MIDImod, etc.).
  
  - **Part Change Messages:** Broadcasts the song name, part name, part length, and index when a new part begins.
    
  - **Bar & Block Trigger Messages:** Sends messages at configurable rhythmic intervals (e.g., every bar, every 4 bars, every 8 bars), perfect for synchronizing visuals or triggering events in other applications.
    
- **MIDI Output & Forwarding:**
  
  - **Remote Transport:** Send MIDI Start/Stop commands to a master clock that accepts them, allowing you to control the entire performance from MIDItema's interface.
    
  - **Program Change:** Send a MIDI Program Change message when a part starts, allowing you to automatically change patches on external synthesizers or effects units.
    
- **External Configuration:** All MIDI ports, OSC settings, and device aliases are defined in a simple miditema.conf.json file, keeping your setup clean and portable.
  

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
  source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
  
  # Install the required packages
  pip install mido python-osc prompt-toolkit python-rtmidi
  ```
  

## Configuration

MIDItema uses two types of JSON files for configuration: a main file for hardware/software connections (miditema.conf.json) and separate files for each song's structure (located in the temas/ directory).

### 1. Main Configuration (miditema.conf.json)

This file, located in the root directory, defines all your MIDI and OSC connections. MIDItema uses partial string matching (case-insensitive) for port names, so you only need to provide a unique substring (e.g., "Clock" instead of "Arturia BeatStep Pro MIDI 1 (Clock In)").

**Full miditema.conf.json Example:**

```
{
    "clock_source": "MasterClock",
    "transport_out": "DAW_Transport_In",

    "midi_configuration": {
        "device_in": "Controller_Port",
        "device_out": "Synth_Module_1",
        "channel_out": 1
    },

    "osc_configuration": {
        "send": {
            "ip": "127.0.0.1",
            "port": 9000,
            "address": "/miditema/part/change",
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
  
  - "device_in": A substring of the MIDI input port for receiving control messages (Program Change, Control Change).
    
    - **Note:** If this is the same as "clock_source", MIDItema will use a single port for both clock and control. If it's different, it will open a dedicated second port.
  - "device_out": A substring of the MIDI output port for sending Program Change messages when a part starts.
    
  - "channel_out": The MIDI channel (1-16) on which to send the Program Change messages. Defaults to 1 if omitted.
    
- "osc_configuration": (Optional) This section configures all OSC output.
  
  - "send":
    
    - "ip": The target IP address for OSC messages. Defaults to "127.0.0.1" (for the same machine).
      
    - "port": The target port for OSC messages. This is mandatory if you want to send any OSC data.
      
    - "address": The primary OSC address for part change messages.
      
    - "address_song_end": (Optional) A specific OSC address to send a message to when the entire song sequence finishes.
      
    - "bar_triggers": (Optional) A list of rules for sending messages on rhythmic boundaries. Each rule is an object with:
      
      - "block_size" (integer): How many bars to count before sending a message.
        
      - "address" (string): The OSC address to use for this trigger.
        

### 2. Song Files (temas/*.json)

These files define the structure of a song. They must be placed in a temas/ directory in the project's root.

**Full song.json Example:**

```
{
    "song_name": "My Awesome Track",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        { "name": "Intro", "bars": 8, "color": "cyan", "repeat_pattern": false },
        { "name": "Verse", "bars": 16, "color": "blue", "repeat_pattern": true },
        { "name": "Pre-Chorus", "bars": 4, "color": "yellow" },
        { "name": "Chorus", "bars": 16, "color": "red", "repeat_pattern": [true, false] },
        { "name": "Outro", "bars": 8, "color": "magenta", "repeat_pattern": [false, true, true] }
    ]
}
```

**Parameter Breakdown:**

- "song_name": (Optional) The name displayed at the top of the UI. Defaults to the filename if omitted.
  
- "time_signature": (Optional) The time signature of the song. Defaults to "4/4". Currently, only the numerator is used to determine the number of beats in a bar.
  
- "time_division": (Optional) Defines how MIDItema interprets a "beat". Defaults to "1/4".
  
  - "1/4": A beat is a quarter note (24 MIDI clock ticks).
    
  - "1/8": A beat is an eighth note (12 MIDI clock ticks).
    
  - "1/16": A beat is a sixteenth note (6 MIDI clock ticks).
    
- "parts": (Mandatory) An array of objects, where each object is a section of your song.
  
  - "name" (string): The name of the part, displayed in the UI.
    
  - "bars" (integer): The length of the part in bars. A part with 0 bars will be skipped.
    
  - "color" (Optional, string): Sets the color of the part's title and sequencer blocks in the UI. Available colors: default, red, green, yellow, blue, magenta, cyan.
    
  - "repeat_pattern" (Optional): Controls the repetition logic across multiple passes of the song.
    
    - **Omitted or true**: The part repeats on every pass through the song structure.
      
    - **false**: The part plays only on the very first pass (pass 0) and is then skipped on all subsequent passes.
      
    - **Array (e.g., [true, false])**: The pattern is followed and looped. [true, false] means the part plays on the 1st pass, skips on the 2nd, plays on the 3rd, skips on the 4th, and so on. [false, true, true] means it skips the 1st pass, plays on the 2nd and 3rd, then repeats that pattern (skips 4th, plays 5th and 6th, etc.).
      

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

These controls are active when the MIDItema terminal window is in focus.

| Key(s) | Action | Details / Quantization |
| --- | --- | --- |
| **Global Transport** |     |     |
| Space / Enter | Send Start/Stop | Sends a MIDI Start/Stop command immediately to the port defined in "transport_out". |
| q / Ctrl+C | Quit | Exits the application cleanly. |
| **Live Navigation** |     |     |
| → / ← | Jump Next / Previous | Programs a relative jump. Uses the **global** quantize mode. Pressing multiple times accumulates the jump (e.g., → → → programs a +3 jump). |
| ↑   | Restart Part | Restarts the current part from its beginning. Uses the **global** quantize mode. |
| ↓   | Cancel Action | Immediately cancels any pending jump or restart action. |
| . or , then [num] Enter | Go to Part | Enters "Go to" mode. Type a part number (1-based, e.g., .4 for the 4th part) and press Enter to program the jump. Uses the **global** quantize mode. |
| **Quick Jumps (Fixed Quantization)** |     |     |
| 0   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next Bar**. |
| 1   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next 4 Bars**. |
| 2   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next 8 Bars**. |
| 3   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next 16 Bars**. |
| **Global Quantize Mode Selection** |     |     |
| 4   | Set Global Quantize | Sets the global mode to **Next 4 Bars**. |
| 5   | Set Global Quantize | Sets the global mode to **Next 8 Bars**. |
| 6   | Set Global Quantize | Sets the global mode to **Next 16 Bars**. |
| 7   | Set Global Quantize | Sets the global mode to **Next Bar**. |
| 9   | Set Global Quantize | Sets the global mode to **Instant**. |

### MIDI Controls

To use MIDI controls, you must configure "device_in" in miditema.conf.json.

#### Program Change (PC) Messages

- **Action:** Jump to a specific part.
  
- **Details:** Sending a Program Change message with value N will schedule a jump to the N+1-th part of the song (PC messages are 0-127, parts are 1-based). For example, PC 0 jumps to Part 1, PC 1 jumps to Part 2, etc.
  
- **Quantization:** Uses the currently active **global** quantize mode.
  

#### Control Change (CC) Messages

All control actions are mapped to **CC#0**. The action performed depends on the value of the CC message.

| CC#0 Value | Action | Details / Quantization |
| --- | --- | --- |
| **Quick Jumps (Fixed Quantization)** |     |     |
| 0   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Instant**. |
| 1   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next Bar**. |
| 2   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next 8 Bars**. |
| 3   | Quick Jump +1 | Jumps to the next valid part. **Fixed Quantization: Next 16 Bars**. |
| **Global Quantize Mode Selection** |     |     |
| 4   | Set Global Quantize | Sets the global mode to **Next 4 Bars**. |
| 5   | Set Global Quantize | Sets the global mode to **Next 8 Bars**. |
| 6   | Set Global Quantize | Sets the global mode to **Next 16 Bars**. |
| 7   | Set Global Quantize | Sets the global mode to **Next Bar**. |
| 9   | Set Global Quantize | Sets the global mode to **Instant**. |
| **Live Navigation (Global Quantization)** |     |     |
| 10  | Jump Previous | Programs a -1 relative jump. Uses the **global** quantize mode. |
| 11  | Jump Next | Programs a +1 relative jump. Uses the **global** quantize mode. |
| 12  | Restart Part | Restarts the current part from its beginning. Uses the **global** quantize mode. |
| 13  | Cancel Action | Immediately cancels any pending jump or restart action. |

## OSC Integration

This is a core feature for integrating MIDItema with other software. By sending Open Sound Control messages, MIDItema can drive visuals, trigger events in other audio applications, or synchronize with custom tools. All OSC messages are sent to the ip and port defined in miditema.conf.json.

### Part Change Message

This is the primary message, sent whenever a new part of the song begins.

- **Address:** Defined by the "address" key in miditema.conf.json.
  
- **Trigger:** Sent at the exact moment a new part becomes active.
  
- **Arguments:** The message contains four arguments:
  
  1. **Song Name** (string): The name of the currently loaded song.
    
  2. **Part Name** (string): The name of the part that is now beginning.
    
  3. **Part Bars** (integer): The total number of bars in this new part.
    
  4. **Part Index** (integer): The zero-based index of this part in the song's parts array.
    

**Example Message:**  
For a song named "Live Set" starting its second part, named "Verse" (which is 16 bars long), the OSC message might be:  
/miditema/part/change "Live Set" "Verse" 16 1

### Song End Message

An optional message sent when the song sequence finishes.

- **Address:** Defined by the "address_song_end" key.
  
- **Trigger:** Sent when the song finishes and there are no more valid parts to play in the sequence.
  
- **Arguments:**
  
  1. **Song Name** (string): The name of the song that has just ended.

**Example Message:**  
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
    

### Testing OSC

A simple Python script, test_osc_receiver.py, is included in the repository to help you test and verify that OSC messages are being sent correctly. Run it in a separate terminal to see a formatted printout of all incoming messages from MIDItema.

```
python test_osc_receiver.py
```

This will listen on 127.0.0.1:9000 by default.


## License

GNU AGPLv3 License. See LICENSE file.