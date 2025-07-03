# MIDItema

A terminal-based, live-performance song arranger and bar counter, broadcasting song-part changes via OSC.

## Core Concept

MIDItema listens to an external master clock (like a DAW, hardware sequencer, or our companion tool MIDImaster) and uses that timing information to step through a pre-defined song structure, or jump dynamically between parts on command.

It will show a bar-countdown for the current part of the song, allowing the user to know in advance when the next change in the song is occurring.

Changes are also broadcast with OSC, so they can be read by other applications (for example, with MIDImod).

## Features

- **Dynamic Part Jumping:** The core feature for live performance. Program jumps to the next/previous part, restart the current section, or go to any specific part of the song.
  
- **Quantized Actions:** Jumps are not immediate. They are scheduled as a **pending action** and executed with musical precision, aligned to the next bar, to the next 8-bar/16-bar section, or even instantly on the next beat.
  
- **Flexible Control Scheme:** Use single-key presses for both fixed actions (e.g., "jump to the next part, quantized to the bar") and global-mode actions.
  
- **Bar-countdown:** Shows the number of bars left in the current part of the song, so you can prepare for changes.
  
- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source.
  
- **JSON-based Song Structure:** Define your entire song structure, parts, and lengths in simple, human-readable JSON files.
  
- **... including Advanced Repetition Logic:** Control exactly when parts repeat using flexible patterns (e.g., "play the Intro only once," "play every other time," "play twice, then skip twice").
  
- **Visual TUI:** A clean, full-screen terminal interface provides a clear overview of the current state and information on the part, including a moving step sequencer showing the bars in the current part, elapsed time, the active quantization mode and any pending action.
  
- **OSC Broadcasting:** Sends detailed OSC messages on every part change, allowing for easy integration with other creative software (MIDImod, Resolume, TouchDesigner, VCV Rack, etc.).

- **MIDI Program Change Output:** Sends a MIDI Program Change message on every part change, allowing you to automatically change patches on external synthesizers or effects units.
  
- **Remote Transport Control:** Can send Start/Stop commands to a master clock (that receives transport signals), allowing you to control the song performance from the single terminal.
  
- **Configurable:** All I/O ports and OSC settings are defined in a simple configuration file.
  

## Installation

1. Clone this repository.
  
2. Ensure you have Python 3 installed.
  
3. Install the required dependencies:
  
  ```
  pip install mido python-osc prompt-toolkit python-rtmidi
  ```
  

## Configuration

MIDItema is controlled by two types of JSON files.

### 1. Main Configuration (miditema.conf.json)

This file, located in the root directory, defines the MIDI and OSC connections.

```
{
    "clock_source": "CLOCK_IN",
    "transport_out": "TRANSPORT_OUT",
    "midi_configuration": {
        "device_out": "Synth_Port",
        "channel_out": 1
    },
    "osc_configuration": {
        "send": {
            "ip": "127.0.0.1",
            "port": 9000,
            "address": "/miditema/part/change"
        }
    }
}
```

- clock_source: A substring of the MIDI input port name that sends the clock.
  
- transport_out: A substring of the MIDI output port name to send transport commands to (the port on which the master clock would listen to transport signals).

- midi_configuration: (Optional) Block to configure Program Change output.

  - device_out: A substring of the MIDI output port to send Program Change messages to (e.g., the name of your synthesizer).
  
  - channel_out: The MIDI channel (1-16) on which to send the Program Change messages. Defaults to 1.
  
- osc_configuration.send:
  
  - ip: The target IP address for OSC messages (127.0.0.1 for the same machine).
    
  - port: The target port for OSC messages.
    
  - address: The OSC address path for the message.
    

### 2. Song Files (temas/*.json)

These files define the structure of a song. They must be placed in a temas/ directory.

```
{
    "song_name": "My Awesome Track",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        { "name": "Intro", "bars": 8, "repeat_pattern": false },
        { "name": "Verse", "bars": 16, "repeat_pattern": true },
        { "name": "Chorus", "bars": 16, "repeat_pattern": [true, false] }
    ]
}
```

- song_name: (Optional) The name displayed in the UI. Defaults to the filename.
  
- time_signature: (Optional) Defaults to "4/4".
  
- time_division: (Optional) How to interpret a "beat". Defaults to "1/4" (quarter note). Can be "1/8" or "1/16".
  
- parts: An array of a song's sections.
  
  - name: The name of the part.
    
  - bars: The length of the part in bars.
    
  - repeat_pattern: (Optional) Controls repetition logic.
    
    - **Omitted or true**: The part repeats on every pass.
      
    - **false**: The part plays only on the very first pass and is then skipped.
      
    - **[true, false]**: Plays on the 1st pass, skips on the 2nd, plays on the 3rd, etc.
      
    - **[false, true, true]**: Skips on the 1st pass, plays on the 2nd and 3rd, skips on the 4th, etc.
      

## Usage

1. Configure your master clock source (e.g., Ableton Live, a hardware sequencer, a sw clock like MIDImaster).
  
2. Configure miditema.conf.json to listen to the correct ports.
  
3. Run MIDItema from your terminal:
  
  ```
  # Run and select a song from the interactive list
  python miditema.py
  
  # Or, specify a song file directly (without the .json extension)
  python miditema.py my_song_file
  ```
  

### Controls

MIDItema features a powerful control scheme for live performance. Most actions are scheduled as a **pending action** and executed with quantization.

| Key(s) | Action | Details / Quantization |
| --- | --- | --- |
| **Global Transport** |     |     |
| Space / Enter | Send Start/Stop | Sends a MIDI Start/Stop command immediately. |
| q / Ctrl+C | Quit | Exits the application. |
| **Live Navigation** |     |     |
| → / ← | Jump Next / Previous | Programs a jump. Uses the **global** quantize mode. Pressing multiple times accumulates the jump (e.g., → → → programs a +3 jump). |
| ↑   | Restart Part | Restarts the current part from its beginning. Uses the **global** quantize mode. |
| ↓   | Cancel Action | Immediately cancels any pending action. |
| . or , then [num] Enter | Go to Part | Enters "Go to" mode. Type a part number (e.g., .12) and press Enter to program the jump to the 12th part ahead in the song (considering repeats). Uses the **global** quantize mode. |
| **Quick Jumps** |     |     |
| 0   | Quick Jump +1 | Jumps to the next part. **Fixed Quantization: Instant** (next beat). |
| 1   | Quick Jump +1 | Jumps to the next part. **Fixed Quantization: Next Bar**. |
| 2   | Quick Jump +1 | Jumps to the next part. **Fixed Quantization: Next 8 Bars**. |
| 3   | Quick Jump +1 | Jumps to the next part. **Fixed Quantization: Next 16 Bars**. |
| **Quantize Mode Selection** |     |     |
| 4   | Set Global Quantize | Sets the global mode used by arrows and "Go to" to **Next 8 Bars**. |
| 5   | Set Global Quantize | Sets the global mode to **Next 16 Bars**. |
| 6   | Set Global Quantize | Sets the global mode to **Next 32 Bars**. |

## OSC Integration

This is the core feature for integrating MIDItema with other software.

When a new part starts, MIDItema sends an OSC message to the configured IP, port, and address. The message contains four arguments:

1. **Song Name** (string): The name of the currently loaded song.
  
2. **Part Name** (string): The name of the part that is now beginning.
  
3. **Part Bars** (int): The total number of bars in this new part.
  
4. **Part Index** (int): The zero-based index of this part in the song's parts array.
  

## MIDI Program Change Integration

In addition to OSC, MIDItema can send a MIDI Program Change message every time a new part begins. This is ideal for controlling external hardware like synthesizers or effects pedals.

The value of the Program Change message corresponds to the **zero-based index** of the new part in the song's `parts` array.

- If the song transitions to the **first** part in the list (index 0), it will send `Program Change 0`.
- If it transitions to the **third** part (index 2), it will send `Program Change 2` on the configured MIDI channel.


#### Testing OSC

A simple Python script, osc_receiver.py, can be used to help you test and verify that OSC messages are being sent correctly. Run it in a separate terminal to see incoming messages.

## License

This project is licensed under the MIT License.