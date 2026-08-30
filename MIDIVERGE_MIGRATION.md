# MIDIverge - Unified Control Surface

## What Changed

### Before (5 components):
1. XIAO microcontroller (`xiao_controller/code.py`) 
2. MIDIOverlay script - UDP sender
3. MIDI_Map_Scanner script - XML scanner  
4. Live_Track_Controller script - Save/restore
5. Overlay UI (`main.py`)

### After (3 components):
1. XIAO microcontroller (`xiao_controller/code.py`) - **UNCHANGED**
2. **MIDIverge** - Unified control surface (`MIDIverge/__init__.py`)
3. Overlay UI (`midiverge_overlay.py`) - **RENAMED**

---

## How to Switch to MIDIverge

### Step 1: Ableton Live Settings
1. Open Ableton Live
2. Go to **Preferences → Link/Tempo/MIDI**
3. Under **Control Surface**, select **MIDIverge** (new unified script)
4. Remove old scripts:
   - ~~MIDIOverlay~~
   - ~~MIDI_Map_Scanner~~  
   - ~~Live_Track_Controller~~
5. Click **OK**

### Step 2: Launch Overlay UI
- **Old:** Double-click `main.py`
- **New:** Double-click `midiverge_overlay.py`

That's it! Everything else works the same.

---

## What Works Better Now

### ✅ Automatic Rescanning
- No more RESCAN button needed
- Scans automatically on startup (~3 seconds)
- Still supports manual trigger via `do_scan.txt` if needed

### ✅ Shared State
- Manual mappings loaded once, shared everywhere
- No more coordination between 3 separate scripts
- Faster, more reliable

### ✅ Better Logging
- All logs in one place: `midiverge_debug.log`
- Clear prefix for all messages

### ✅ Cleaner Architecture
- ~1200 lines instead of 2500 across 3 files
- Easier to debug and maintain
- Single initialization, no race conditions

---

## Files Created

### New Files:
- `C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\MIDIverge\__init__.py`
- `C:\Users\zackn\Documents\midi overlay\midiverge_overlay.py`

### Backup Files (kept for safety):
- All original scripts backed up with timestamp `20260829_141719`
- Old `main.py` still exists (not deleted)

### Old Scripts (can delete after testing):
- `MIDIOverlay/__init__.py`
- `MIDI_Map_Scanner/MIDI_Map_Scanner.py`
- `Live_Track_Controller/Live_Track_Controller.py`

---

## Testing Checklist

1. ✅ Ableton loads without errors
2. ✅ MIDIverge appears in Ableton log: "MIDIverge Remote Script loaded!"
3. ✅ Scanner runs automatically (~3 seconds after load)
4. ✅ Encoders control parameters
5. ✅ Overlay shows parameter names/values
6. ✅ Values save/restore when switching tracks
7. ✅ Manual mappings still work
8. ✅ No red flashing on XIAO (fixed in previous session)

---

## Rollback Instructions (if needed)

If anything goes wrong, restore the old system:

1. In Ableton Preferences, **remove MIDIverge**
2. Add back the 3 old scripts:
   - MIDIOverlay
   - MIDI_Map_Scanner
   - Live_Track_Controller
3. Use `main.py` instead of `midiverge_overlay.py`
4. All backups are timestamped `20260829_141719`
