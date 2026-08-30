# MIDI Overlay - Recursive Parameter Discovery

## What Changed (2026-08-24)

### MIDIOverlay Remote Script
**Problem**: Scanner JSON was failing to resolve LOM paths, causing parameters to not display
**Solution**: Use recursive parameter traversal (same proven method as save/restore system)

**How it works now**:
1. Scanner still finds CC mappings in .als file (knows CC72 = Volume, CC73 = Macro 4, etc.)
2. MIDIOverlay script recursively traverses ALL parameters (track mixer, devices, chains, nested devices)
3. Matches parameters using track_index + param_tag from scanner
4. No more fragile LOM path resolution!

### New Launcher
**launch_overlay.ps1**: Starts overlay without clearing cache
- Use this for normal usage
- Only clear cache if you need to debug Ableton issues

### Files Modified
- `remote_scripts/MIDIOverlay/__init__.py`: New `_find_parameter_recursive()` method
- Deployed to: `C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\MIDIOverlay\`

### Testing
1. Restart Ableton (to load new MIDIOverlay script)
2. Run `launch_overlay.ps1` to start the display
3. Switch tracks and check if parameter names appear correctly
4. Check `midioverlay_debug.log` for "[FIND] MATCH!" messages

### Debug Log Location
`C:\Users\zackn\Documents\midi overlay\midioverlay_debug.log`

Look for:
- `[FIND] MATCH!` = parameter found successfully
- `[LISTENER] CC71 -> Parameter Name` = listener added
- `[WARNING] Could not find parameter` = needs investigation
