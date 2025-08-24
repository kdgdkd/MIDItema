# MIDItema: Live Performance Sequencer

MIDItema is a terminal-based sequencer that acts as a MIDI clock slave, stepping through song structures and sending automated MIDI and OSC messages. It's designed for live electronic music performance where you need to coordinate multiple devices with perfect timing.

## What It Does

MIDItema reads your song structure from JSON files and follows along with your master clock. When parts change, it automatically sends MIDI program changes, control messages, and OSC data to your connected gear. Instead of manually triggering patches and effects during performance, you program the automations once and MIDItema handles them.

You can jump between parts and songs with musical quantization, create loops, and access any part of your set instantly via cues. All while maintaining sync with your master clock.

## Core Concepts

**Songs** are made of **Parts**. Each part has a length in bars and defines what happens when it ends via `repeat_pattern`. Parts can loop, jump to other sections, or advance linearly.

**Playlists** organize multiple songs for an entire set. You can jump between songs or let them flow automatically.

**Triggers** are the automation engine. When events happen (part changes, song changes, etc.), MIDItema sends whatever MIDI or OSC messages you've configured.

## Live Techno Performance Setup

Here's how a typical live techno setup works with MIDItema:

### Hardware Coordination
Your Ableton Live or hardware sequencer provides the master clock. MIDItema follows along and coordinates your other gear:
- **Drum machines**: Program changes switch between patterns
- **Synthesizers**: Patch changes for different song sections  
- **Effects units**: Parameter changes via CC messages
- **Lighting**: OSC messages to control visual scenes
- **Modular gear**: CV control via MIDI-to-CV interfaces

### Song Structure Example
```json
{
  "song_name": "Acid Techno Track",
  "parts": [
    {
      "name": "Intro", 
      "bars": 32,
      "output": {"device": "tb303", "program": 1}
    },
    {
      "name": "Main Drop", 
      "bars": 64, 
      "repeat_pattern": ["repeat", "next"],
      "output": [
        {"device": "drumbrute", "program": 2},
        {"device": "tb303", "program": 5}
      ]
    },
    {
      "name": "Breakdown", 
      "bars": 32, 
      "repeat_pattern": "repeat",
      "output": {"device": "reverb_unit", "control": 20, "value": 127}
    }
  ]
}
```

The "Main Drop" will play twice then advance. The "Breakdown" loops until you manually jump to another section.

### Live Control
During performance, you can:
- Jump to the next/previous part with arrow keys or MIDI controller
- Access specific parts instantly via F-key cues
- Create manual loops on any section
- Switch between songs in your playlist
- All jumps are quantized to musical boundaries (bars, beats, etc.)

### Typical Workflow
1. Program your song structures with part lengths and automation triggers
2. Connect MIDItema to your master clock source and all your gear
3. Start your set - MIDItema follows the clock and sends automation
4. Use keyboard or MIDI controller to navigate between sections as needed
5. Focus on performance while MIDItema handles the technical coordination

## Configuration

Two types of files:

**Main config** (`miditema.conf.json`): Defines your MIDI/OSC connections and what messages to send when events happen.

**Song/Playlist files**: Define your music structure, part lengths, and local automation triggers.

## Installation & Usage

Requires Python 3. Install dependencies:
```bash
git clone https://github.com/kdgdkd/miditema.git
cd miditema
pip install -r requirements.txt
```

Launch with a song or playlist:
```bash
python miditema.py my_techno_set.json
```

MIDItema will sync to your master clock and step through your arrangement, sending the programmed automation messages.

## Control Options

**Keyboard**: Full control from your laptop keyboard
**MIDI Controller**: Program any controller to send the right CC/PC/Note messages  
**Hybrid**: Keyboard for setup, dedicated controller for performance

## License

GNU AGPLv3 - See LICENSE file