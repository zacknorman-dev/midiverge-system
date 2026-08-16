# Ableton MIDI Overlay System

Complete MIDI controller system for Ableton Live with automatic track parameter memory and visual feedback.

## System Overview

Three-component architecture for seamless MIDI control with track-aware parameter management:

1. **XIAO RP2040 MIDI Controller** - Hardware with 10 encoders + 10 buttons
2. **Ableton Remote Scripts** - Track memory and parameter scanning
3. **Visual Overlay** - Real-time parameter display

## Components

### 1. XIAO RP2040 MIDI Controller (`xiao_controller/`)

**Hardware:** Seeeduino XIAO RP2040 with 3× PCA9555 I/O expanders
- **10 Encoders:** CC71-79 (8 track controls + 1 track selector)
- **10 Buttons:** CC81-89 (encoder presses + 1 rescan trigger)
- **Encoder 10 (CC79):** Relative MIDI track selection (1=CW, 127=CCW)
- **Button 10 (CC89):** Save project + reload mappings

**Firmware:** CircuitPython
- `code.py` - Main firmware with encoder/button scanning

### 2. Ableton Remote Scripts (`remote_scripts/`)

#### Live_Track_Controller

**Automatic Track Memory System** - Saves/restores parameter values per track

**Features:**
- Intercepts CC79 for programmatic track selection
- Listens for ANY track change (CC79, mouse, arrows, etc.)
- Saves previous track's parameter values before switching
- Restores new track's saved values after switching
- Supports ALL parameter types:
  - Device parameters (instruments, effects)
  - Mixer parameters (Volume, Pan, Sends)
  - MacroControls (Racks)
  - ChainSelector (Instrument/Effect Racks)

**CC89 Button:** Triggers save → Scanner re-parse → reload mappings

**Installation:**
```
Copy to: C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\Live_Track_Controller\
```

#### MIDI_Map_Scanner

**Automatic Parameter Discovery** - Parses .als project files to discover MIDI mappings

**Features:**
- Parses gzipped .als XML on every save
- Resolves parameters via Live API
- Writes JSON mapping: CC → track/device/parameter
- Triggers immediately on project save (is_dirty listener)
- Fast polling (5 ticks = ~83ms) for file change detection

**Output:** `current_scan.json` with mapping data for LTC and Overlay

**Installation:**
```
Copy to: C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\MIDI_Map_Scanner\
```

### 3. Visual Overlay (`main.py`)

**Real-time Parameter Display** - Always-on-top window with track-aware parameter names

**Features:**
- 2560×75px window with 8 encoder displays
- Reads `current_scan.json` for parameter names
- Receives UDP on port 9001 for value updates
- Shows parameter name and current value per CC
- Track-aware: Updates when track selection changes

**Requirements:**
```bash
pip install -r requirements.txt
```

**Run:**
```bash
python main.py
```

## System Workflow

### Setup
1. Map MIDI CC to parameters in Ableton using Ctrl+M
2. Save project (Ctrl+S)
3. Scanner automatically parses .als and writes JSON
4. LTC loads mappings and monitors track changes
5. Overlay reads JSON and displays parameter names

### Operation
1. Turn encoder → Changes parameter value
2. Switch tracks (CC79/mouse/arrows) → **Auto saves previous track, restores new track**
3. Add new mapping → Press CC89 → **Instant reload without restart**

### Track Memory Example
- Map CC72 to Filter Freq on Track 1
- Map CC72 to Reverb Mix on Track 2
- Adjust filter on Track 1
- Switch to Track 2 → **Filter setting saved**
- Adjust reverb on Track 2
- Switch back to Track 1 → **Both filter AND reverb restored!**

## Technical Details

### Communication
- **MIDI:** USB MIDI from XIAO to Ableton
- **UDP:** Remote Script → Overlay (port 9001, 127.0.0.1)
- **JSON:** Scanner → LTC + Overlay (`current_scan.json`)

### Ableton Live API
- Track selection listener: `add_selected_track_listener`
- Save detection: `is_dirty_listener` 
- Parameter access: `track.devices[N].parameters[M]`
- Mixer parameters: `track.mixer_device.volume`, `.panning`, `.sends[N]`

### File Format (current_scan.json)
```json
{
  "als_file": "project.als",
  "total_tracks": 6,
  "total_mappings": 8,
  "mappings": [
    {
      "track_index": 0,
      "cc": 72,
      "param_index": 2,
      "param_live_name": "Filter Reso",
      "device_class_name": "InstrumentGroupDevice",
      "device_name": "4 OSC",
      "is_mixer_param": false,
      "lom_path": ["devices[0]", "param_index[2]"]
    }
  ]
}
```

## Installation

### 1. XIAO RP2040 Setup
1. Install CircuitPython on XIAO RP2040
2. Copy `xiao_controller/code.py` to CIRCUITPY drive
3. Install required libraries: `adafruit_pcf8575`, `adafruit_midi`

### 2. Ableton Remote Scripts
```powershell
# Copy to Ableton's MIDI Remote Scripts directory
$scriptsDir = "C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts"

Copy-Item -Recurse "remote_scripts\Live_Track_Controller" "$scriptsDir\"
Copy-Item -Recurse "remote_scripts\MIDI_Map_Scanner" "$scriptsDir\"

# Clear Python cache after any updates
Remove-Item -Recurse -Force "$scriptsDir\Live_Track_Controller\__pycache__"
Remove-Item -Recurse -Force "$scriptsDir\MIDI_Map_Scanner\__pycache__"
```

### 3. Overlay Application
```bash
cd "C:\Users\zackn\Documents\midi overlay"
pip install -r requirements.txt
python main.py
```

### 4. Ableton Setup
1. Preferences → Link/Tempo/MIDI
2. Enable "Track" ON for XIAO RP2040 device
3. Control Surface: Select "Live_Track_Controller" + "MIDI_Map_Scanner"
4. Restart Ableton

## Development Notes

### Debugging
- **Ableton Log:** `C:\Users\zackn\AppData\Roaming\Ableton\Live 12.4\Preferences\Log.txt`
- Search for: `LTC:`, `MIDI Map Scanner:`, `[CC79]`, `[CC89]`

### Python Cache Issue
Ableton caches `.pyc` bytecode even with newer source files. After editing remote scripts:
```powershell
# Close Ableton FIRST, then:
Remove-Item -Recurse -Force "C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\*\__pycache__"
```

### Scanner Triggers
- **Project save (Ctrl+S):** Immediate re-scan via `is_dirty_listener`
- **CC89 button:** LTC saves project → Scanner detects → re-scans
- **File polling:** Every 5 ticks (~83ms) as fallback

## Supported Parameter Types

✅ **Device Parameters** - Instruments, audio effects, MIDI effects  
✅ **Mixer Parameters** - Volume, Pan, Sends, Cue Volume  
✅ **MacroControls** - Instrument/Audio/Effect Rack macros  
✅ **ChainSelector** - Rack chain selection (integer values)

## Key Features

- **Zero-latency track changes** - CC79 programmatic selection
- **Automatic memory** - No manual save/restore needed
- **100% parameter coverage** - All Ableton parameter types supported
- **Instant mapping updates** - CC89 button or save → immediate reload
- **Visual feedback** - Always-on-top overlay with parameter names/values
- **No restart required** - Save or CC89 → instant mapping updates

## Project Status

**Working:**
- ✅ CC79 track selection (relative encoder)
- ✅ Automatic track change listener (any selection method)
- ✅ Save/restore for all parameter types
- ✅ CC89 instant rescan
- ✅ Mixer parameter support (Volume, Pan, Sends)
- ✅ Scanner immediate save detection

**Future Enhancements:**
- Enumerate-all approach (query Live API for all params vs XML parsing)
- Stable parameter IDs (handle runtime device changes)

## Version History

**2026-08-15** - Mixer parameter support, instant save detection  
**2026-08-14** - Automatic track memory system  
**2026-08-13** - Initial CC79 implementation

## License

MIT License - Free to use and modify

## Author

Built for live performance with Ableton Live 12.4
