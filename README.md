# MIDItema

A terminal-based bar counter and song arranger, broadcasting song-part changes via OSC.



## Core Concept

MIDItema listens to an external master clock (like a DAW, hardware sequencer, or our companion tool midimaster) and uses that timing information to step through a pre-defined song structure.

It will show a bar-countdown for the current part of the song, allowing the user to know in advance when the next change in the song is ocurring.

Changes are also broadcast with OSC, so they can be read by other applications.



## Features

- **Bar-countdown:** Shows the number of bars left in the current part of the song.
- **MIDI Clock Slave:** Synchronizes perfectly to any standard MIDI clock source.
  
- **JSON-based Song Structure:** Define your entire song structure, parts, and lengths in simple, human-readable JSON files.
  
- **Advanced Repetition Logic:** Control exactly when parts repeat using flexible patterns (e.g., "play only once," "play every other time," "play twice, then skip twice").
  
- **Visual TUI:** A clean, full-screen terminal interface provides a clear overview of the current state.
    
- **OSC Broadcasting:** Sends detailed OSC messages on every part change, allowing for easy integration with other creative software (Resolume, TouchDesigner, VCV Rack, etc.).
  
- **Remote Transport Control:** Can send Start/Stop commands to a master device, allowing you to control your entire setup from one terminal (best integrated with MIDImaster).
  
- **Configurable:** All I/O ports and OSC settings are defined in a simple configuration file.
  

## How It Works

1. **Listen:** MIDItema connects to a MIDI input port and listens for MIDI Clock messages.
  
2. **Count:** It uses the incoming clock ticks to count beats and bars according to the loaded song file's structure.
  
3. **Sequence:** When a part finishes, it determines the next part to play based on the defined repeat_pattern logic.
  
4. **Broadcast:** As soon as a new part begins, it sends an OSC message with the new part's details to a configurable IP address and port.
  
5. **Control (Optional):** It can also send Start/Stop messages to a separate MIDI output port to remotely control the master clock source.
  

## Installation

1. Clone this repository.
  
2. Ensure you have Python 3 installed.
  
3. Install the required dependencies:
  

  
  ```
  pip install mido python-osc prompt-toolkit python-rtmidi
  ```
  

  
  Note: python-rtmidi is a recommended backend for mido on most systems.
  

## Configuration

MIDItema is controlled by two types of JSON files.

### 1. Main Configuration (MIDItema.conf.json)

This file, located in the root directory, defines the MIDI and OSC connections.



```
{
    "clock_source_alias": "CLOCK",
    "remote_control_alias": "TPT",
    "osc_configuration": {
        "send": {
            "ip": "127.0.0.1",
            "port": 9000,
            "address": "/MIDItema/part/change"
        }
    }
}
```



- clock_source_alias: A substring of the MIDI input port name that sends the clock.
  
- remote_control_alias: A substring of the MIDI output port name to send transport commands to.
  
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

1. Configure your master clock source (e.g., midimaster, Ableton Live, a hardware synth) to send MIDI clock.
  
2. Configure MIDItema.conf.json to listen to the correct ports.
  
3. Run MIDItema from your terminal:
  

  
  ```
  # Run and select a song from the interactive list
  python miditema.py
  
  # Or, specify a song file directly (without the .json extension)
  python miditema.py my_song_file
  ```


  

### Controls

- Space / Enter: Send Start/Stop MIDI command to the remote control port.
  
- q / Ctrl+C: Quit the application.
  

## OSC Integration

This is the core feature for integrating MIDItema with other software.

When a new part starts, MIDItema sends an OSC message to the configured IP, port, and address. The message contains four arguments:

1. **Song Name** (string): The name of the currently loaded song.
  
2. **Part Name** (string): The name of the part that is now beginning.
  
3. **Part Bars** (int): The total number of bars in this new part.
  
4. **Part Index** (int): The zero-based index of this part in the song's parts array.
  

#### Testing OSC

A simple Python script, osc_receiver.py, is provided in this repository to help you test and verify that OSC messages are being sent correctly. Run it in a separate terminal to see incoming messages.

## License

This project is licensed under the MIT License.