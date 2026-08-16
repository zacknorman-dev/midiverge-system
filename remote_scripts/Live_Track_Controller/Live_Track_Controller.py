"""
Live Track Controller - Ableton Live Remote Script
Seeeduino XIAO RP2040 MIDI Controller

Automatic Track Memory with Save/Restore:
  - Monitors track selection changes from ANY source (CC79, mouse, arrows, etc.)
  - Saves current track's mapped parameter values before switching
  - Restores new track's saved values after switching
  - Creates persistent "memory" per track

Encoders 2-9 (CC71-CC78): Use native Ctrl+M mapping
  - All tracks respond to CCs normally (Track = ON in preferences)
  - Encoder 10 (CC79) can also use native mapping for track selection
  - Reads *_midi_map_scan.json to discover which parameters to save/restore

Button 10 (CC89): Manual rescan trigger
"""

import json
import os
import socket

import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.Task import Task

# ── Constants ────────────────────────────────────────────────────────────────

TRACK_SELECT_CC = 79          # CC reserved for track selection (encoder 10)
SAVE_RESCAN_CC = 89           # CC reserved for manual save + rescan (button 10)


class Live_Track_Controller(ControlSurface):

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._cc_mappings = {}    # {cc_int: [(track_index, lom_path_list)]}
        self._saved_values = {}   # {track_index: {lom_path_key: float}}
        self._user_mappings = {}  # {device_class: {param_tag: param_name}}
        self._previous_track_index = None  # Track the previous track for save/restore
        
        # UDP socket for overlay updates
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_enabled = True
            self.log_message('LTC: UDP socket initialized for overlay updates')
        except Exception as e:
            self._udp_socket = None
            self._udp_enabled = False
            self.log_message('LTC: Could not create UDP socket: %s' % str(e))

        self._user_mappings = self._load_user_mappings()
        self._cc_mappings = self._load_json_mappings()
        
        # Initialize previous track index
        all_tracks = (list(self.song().tracks) + list(self.song().return_tracks) + [self.song().master_track])
        try:
            self._previous_track_index = all_tracks.index(self.song().view.selected_track)
        except ValueError:
            self._previous_track_index = 0
        
        # Add listener for automatic save/restore on track change
        if not self.song().view.selected_track_has_listener(self._on_selected_track_changed):
            self.song().view.add_selected_track_listener(
                self._on_selected_track_changed)

        self.log_message('Live Track Controller loaded with auto track-change listener')
        self.request_rebuild_midi_map()

    def disconnect(self):
        # Remove listener to prevent memory leaks
        if self.song().view.selected_track_has_listener(
            self._on_selected_track_changed):
            self.song().view.remove_selected_track_listener(
                self._on_selected_track_changed)
        super().disconnect()

    # ── MIDI map ──────────────────────────────────────────────────────────────

    def build_midi_map(self, midi_map_handle):
        # Intercept CC79 (track selection) and CC89 (rescan button)
        Live.MidiMap.forward_midi_cc(
            self._c_instance.handle(), midi_map_handle, 0, TRACK_SELECT_CC)
        Live.MidiMap.forward_midi_cc(
            self._c_instance.handle(), midi_map_handle, 0, SAVE_RESCAN_CC)

        super().build_midi_map(midi_map_handle)

    # ── MIDI receive ──────────────────────────────────────────────────────────

    def receive_midi(self, midi_bytes):
        if len(midi_bytes) != 3 or midi_bytes[0] != 0xB0:
            super().receive_midi(midi_bytes)
            return

        cc, value = midi_bytes[1], midi_bytes[2]

        if cc == TRACK_SELECT_CC:
            # CC79: Track selection (relative: 1=CW, 127=CCW)
            self._handle_track_selection(value)
        elif cc == SAVE_RESCAN_CC and value == 127:  # Button press only
            self._handle_save_and_rescan()
        else:
            super().receive_midi(midi_bytes)
    
    # ── Track Selection ───────────────────────────────────────────────────────
    
    def _handle_track_selection(self, value):
        """Handle CC79 track selection: 1=next track (CW), 127=previous track (CCW)"""
        tracks = list(self.song().visible_tracks) + list(self.song().return_tracks)
        current_track = self.song().view.selected_track
        
        try:
            current_index = tracks.index(current_track)
        except ValueError:
            # Master track or track not found
            current_index = 0 if value == 1 else len(tracks) - 1
        
        # Determine direction
        if value == 1:  # Clockwise = next track
            new_index = (current_index + 1) % len(tracks)
        elif value == 127:  # Counter-clockwise = previous track
            new_index = (current_index - 1) % len(tracks)
        else:
            return
        
        # Set new track
        self.song().view.selected_track = tracks[new_index]
        self.log_message('LTC: CC79 - Selected track %d: %s' % (new_index, tracks[new_index].name))
    
    def _handle_save_and_rescan(self):
        """Handle CC89: Save project and reload mappings"""
        self.log_message('LTC: CC89 - Save and rescan triggered')
        
        # Save the project (triggers Scanner to re-run automatically)
        if self.song().file_path:
            try:
                self.song().save()
                self.log_message('LTC: Project saved, Scanner will update mappings')
                
                # Schedule reload after Scanner has time to process (1 second delay)
                self.schedule_message(60, self._reload_mappings)  # 60 ticks = ~1 second
            except Exception as e:
                self.log_message('LTC: Error saving project: %s' % str(e))
        else:
            self.log_message('LTC: Project not saved yet - save project first, then use CC89')
    
    def _reload_mappings(self):
        """Reload JSON mappings after Scanner updates"""
        self._cc_mappings = self._load_json_mappings()
        self.log_message('LTC: Mappings reloaded from JSON')
        
        # Notify overlay to reload as well
        selected_track = self.song().view.selected_track
        self._send_udp({
            'type': 'track_changed',
            'track_name': selected_track.name if selected_track else 'Unknown'
        })
        self.log_message('LTC: Sent track_changed to overlay after reload')
    
    def _get_mixer_parameter(self, track, lom_path):
        """Get mixer parameter (Volume, Pan, Sends) from track"""
        import re
        
        if not lom_path or len(lom_path) < 2:
            return None
        
        # lom_path should be: ['mixer_device', 'param <Volume>'] or similar
        if lom_path[0] != 'mixer_device':
            return None
        
        # Extract parameter name from 'param <Name>' format
        param_part = lom_path[-1]
        m = re.match(r'param <(.+)>', param_part)
        if not m:
            return None
        
        param_name = m.group(1)
        
        # Get mixer device
        if not hasattr(track, 'mixer_device'):
            return None
        
        mixer = track.mixer_device
        
        # Map common parameter names
        param_map = {
            'Volume': 'volume',
            'Pan': 'panning',
            'Track Volume': 'volume',
            'Track Pan': 'panning',
            'Cue Volume': 'cue_volume',
        }
        
        # Check direct attribute
        attr_name = param_map.get(param_name, param_name.lower().replace(' ', '_'))
        if hasattr(mixer, attr_name):
            return getattr(mixer, attr_name)
        
        # Check sends (Send A, Send B, etc.)
        if param_name.startswith('Send ') or 'send' in param_name.lower():
            if hasattr(mixer, 'sends'):
                # Try to extract send index
                send_match = re.search(r'[A-Z]', param_name)
                if send_match:
                    send_letter = send_match.group(0)
                    send_index = ord(send_letter) - ord('A')
                    if 0 <= send_index < len(mixer.sends):
                        return mixer.sends[send_index]
        
        return None
    
    # ── Track Change Listener ─────────────────────────────────────────────────
    
    def _send_udp(self, message_dict):
        """Send UDP message to overlay (port 9001)"""
        if not self._udp_enabled or not self._udp_socket:
            return
        
        try:
            message_json = json.dumps(message_dict)
            self._udp_socket.sendto(message_json.encode('utf-8'), ('127.0.0.1', 9001))
        except Exception as e:
            self.log_message('LTC: UDP send error: %s' % str(e))
    
    def _on_selected_track_changed(self):
        """Called automatically when track selection changes (any method)."""
        self.log_message('LTC: Track changed - triggering save/restore')
        
        # Save the PREVIOUS track's values (before the change)
        if self._previous_track_index is not None:
            self._save_track_by_index(self._previous_track_index)
        
        # Update the previous track index to the current track
        all_tracks = (list(self.song().tracks) + list(self.song().return_tracks) + [self.song().master_track])
        try:
            self._previous_track_index = all_tracks.index(self.song().view.selected_track)
        except ValueError:
            self._previous_track_index = None
        
        # Send track_changed message to overlay
        selected_track = self.song().view.selected_track
        self._send_udp({
            'type': 'track_changed',
            'track_name': selected_track.name if selected_track else 'Unknown'
        })
        
        # Defer the restore operation to avoid "Changes cannot be triggered by notifications" error
        self._tasks.add(lambda delta: self._restore_current_track())

    # ── Save/Restore ──────────────────────────────────────────────────────────
    
    @staticmethod
    def _lom_path_key(lom_path):
        """Generate a hashable key for an lom_path list."""
        return '|'.join(lom_path)

    def _load_json_mappings(self):
        """Load mappings from current_scan.json (written by MidiMapScanner)."""
        # Use the same fixed path that MidiMapScanner writes to
        json_path = r'C:\Users\zackn\Documents\midi overlay\current_scan.json'
        
        if not os.path.isfile(json_path):
            self.log_message('LTC: JSON not found: %s' % json_path)
            return {}
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.log_message('LTC: Failed to load JSON: %s' % str(e))
            return {}
        
        mappings = {}
        for entry in data.get('mappings', []):
            cc = entry.get('cc')
            track_idx = entry.get('track_index')
            lom_path = entry.get('lom_path', [])
            param_index = entry.get('param_index', -1)
            device_class = entry.get('device_class_name', '')
            device_name = entry.get('device_name', '')
            device_path = entry.get('device_path', [])
            
            if cc is None or track_idx is None:
                continue
            
            mappings.setdefault(cc, []).append({
                'track_idx': track_idx,
                'lom_path': lom_path,
                'param_index': param_index,
                'device_class': device_class,
                'device_name': device_name,
                'device_path': device_path
            })
        
        self.log_message('LTC: Loaded %d CCs from JSON (%d mappings)' 
                        % (len(mappings), len(data.get('mappings', []))))
        
        # DEBUG: Log what CCs were actually loaded
        for cc, entries in mappings.items():
            self.log_message('LTC: CC%d has %d track mappings' % (cc, len(entries)))
        
        return mappings
    
    def _load_user_mappings(self):
        """Load user-defined parameter name mappings from JSON file."""
        try:
            als_path = self.song().file_path
            if not als_path:
                return {}
            
            project_dir = os.path.dirname(als_path)
            user_mappings_file = os.path.join(project_dir, 'user_param_mappings.json')
            
            if not os.path.isfile(user_mappings_file):
                return {}
            
            with open(user_mappings_file, 'r') as f:
                data = json.load(f)
            
            self.log_message('LTC: Loaded %d user parameter mappings' % len(data))
            return data
        except Exception as e:
            self.log_message('LTC: Error loading user mappings: %s' % str(e))
            return {}

    def _save_track_by_index(self, track_index):
        """Save all mapped parameter values for a specific track by index."""
        all_tracks = (list(self.song().tracks)
                      + list(self.song().return_tracks)
                      + [self.song().master_track])
        
        if track_index < 0 or track_index >= len(all_tracks):
            return

        values = {}
        for cc, entries in self._cc_mappings.items():
            self.log_message('LTC: [SAVE] Checking CC%d (%d entries)' % (cc, len(entries)))
            for entry in entries:
                if entry['track_idx'] == track_index:
                    self.log_message('LTC: [SAVE] CC%d matches track %d, device=%s, param_idx=%d' 
                                   % (cc, track_index, entry['device_class'], entry['param_index']))
                    
                    # Check for mixer parameters (Volume, Pan, Sends, etc.)
                    if entry.get('is_mixer_param') or (entry['lom_path'] and entry['lom_path'][0] == 'mixer_device'):
                        mixer_param = self._get_mixer_parameter(all_tracks[entry['track_idx']], entry['lom_path'])
                        if mixer_param is not None:
                            param_name = entry.get('param_live_name', 'Mixer Param')
                            self.log_message('LTC: Saving mixer param %s = %.3f' % (param_name, mixer_param.value))
                            values[self._lom_path_key(entry['lom_path'])] = mixer_param.value
                        else:
                            self.log_message('LTC: Could not resolve mixer parameter')
                        continue  # Skip to next entry
                    
                    # Check for ChainSelector special case
                    if self._is_chain_selector_param(entry['lom_path']):
                        chain_sel = self._get_chain_selector_property(all_tracks[entry['track_idx']], entry['lom_path'])
                        if chain_sel:
                            self.log_message('LTC: [DEBUG] About to SAVE ChainSelector for track %d' % entry['track_idx'])
                            val = chain_sel['get']()
                            self.log_message('LTC: [DEBUG] Got val=%s (type=%s)' % (str(val), type(val).__name__))
                            key = self._lom_path_key(entry['lom_path'])
                            self.log_message('LTC: [DEBUG] Saving ChainSelector with key="%s", value=%d' % (key, val))
                            self.log_message('LTC: Saving ChainSelector = %d' % val)
                            values[key] = val
                            self.log_message('LTC: [DEBUG] Stored in dict, values[key]=%s (type=%s)' % (str(values[key]), type(values[key]).__name__))
                        else:
                            self.log_message('LTC: Could not resolve ChainSelector')
                    # Check for MacroControls special case
                    elif self._is_macro_control_param(entry['lom_path']):
                        macro_param = self._get_macro_control_parameter(all_tracks[entry['track_idx']], entry['lom_path'])
                        if macro_param is not None:
                            param_name = entry['lom_path'][-1] if entry['lom_path'] else '?'
                            self.log_message('LTC: Saving %s = %.3f' % (param_name, macro_param.value))
                            values[self._lom_path_key(entry['lom_path'])] = macro_param.value
                        else:
                            self.log_message('LTC: Could not resolve MacroControl')
                    else:
                        # Regular parameter - try device ID method first
                        param = None
                        if entry['param_index'] >= 0:
                            param = self._find_parameter_by_device_id(
                                all_tracks[entry['track_idx']], 
                                entry['device_class'],
                                entry['device_name'],
                                entry['device_path'],
                                entry['param_index']
                            )
                        
                        # Fallback: If param_index was -1 or device ID method failed, try LOM path navigation
                        if param is None and entry['lom_path']:
                            self.log_message('LTC: [SAVE] Trying LOM path fallback for %s' % entry['lom_path'][-1])
                            param = self._find_parameter_by_lom_path(
                                all_tracks[entry['track_idx']],
                                entry['lom_path']
                            )
                        
                        if param is not None:
                            param_name = entry['lom_path'][-1] if entry['lom_path'] else '?'
                            self.log_message('LTC: Saving %s = %.3f' % (param_name, param.value))
                            values[self._lom_path_key(entry['lom_path'])] = param.value
                        else:
                            self.log_message('LTC: Could not resolve for save: %s on %s' 
                                           % (entry['device_class'], entry['device_name']))

        if values:
            self._saved_values[track_index] = values
            self.log_message('LTC: Saved %d params for track %d' % (len(values), track_index))
            self.log_message('LTC: [DEBUG] Saved dictionary keys: %s' % str(values.keys()))

    def _save_current_track(self):
        """Save all mapped parameter values for the currently selected track."""
        selected = self.song().view.selected_track
        all_tracks = (list(self.song().tracks)
                      + list(self.song().return_tracks)
                      + [self.song().master_track])
        try:
            sel_idx = all_tracks.index(selected)
            self._save_track_by_index(sel_idx)
        except ValueError:
            return

    def _restore_current_track(self):
        """Restore saved parameter values for the currently selected track."""
        selected = self.song().view.selected_track
        all_tracks = (list(self.song().tracks)
                      + list(self.song().return_tracks)
                      + [self.song().master_track])
        try:
            sel_idx = all_tracks.index(selected)
        except ValueError:
            return

        if sel_idx not in self._saved_values:
            self.log_message('LTC: No saved values for track %d' % sel_idx)
            return

        saved = self._saved_values[sel_idx]
        self.log_message('LTC: [DEBUG] Restoring track %d, saved dictionary: %s' % (sel_idx, str(saved)))
        restored = 0
        for entries in self._cc_mappings.values():
            for entry in entries:
                if entry['track_idx'] == sel_idx:
                    key = self._lom_path_key(entry['lom_path'])
                    param_name = entry['lom_path'][-1] if entry['lom_path'] else '?'
                    self.log_message('LTC: [DEBUG] Looking for key "%s" for param %s, saved value=%s' % (key, param_name, str(saved.get(key, 'NOT FOUND'))))
                    if key not in saved:
                        self.log_message('LTC: No saved value for %s (key not in dict)' % param_name)
                        continue
                    
                    # Check for mixer parameters (Volume, Pan, Sends, etc.)
                    if entry.get('is_mixer_param') or (entry['lom_path'] and entry['lom_path'][0] == 'mixer_device'):
                        mixer_param = self._get_mixer_parameter(all_tracks[entry['track_idx']], entry['lom_path'])
                        if mixer_param is not None:
                            try:
                                old_val = mixer_param.value
                                new_val = max(mixer_param.min, min(mixer_param.max, saved[key]))
                                mixer_param.value = new_val
                                param_name_display = entry.get('param_live_name', 'Mixer Param')
                                self.log_message('LTC: Restoring mixer param %s: %.3f -> %.3f' % (param_name_display, old_val, new_val))
                                restored += 1
                            except Exception as e:
                                self.log_message('LTC: Error restoring mixer parameter: %s' % str(e))
                        else:
                            self.log_message('LTC: Could not resolve mixer parameter for restore')
                        continue  # Skip to next entry
                    
                    # Check for ChainSelector special case
                    if self._is_chain_selector_param(entry['lom_path']):
                        chain_sel = self._get_chain_selector_property(all_tracks[entry['track_idx']], entry['lom_path'])
                        if chain_sel:
                            try:
                                old_val = chain_sel['get']()
                                new_val = int(saved[key])
                                chain_sel['set'](new_val)
                                self.log_message('LTC: Restoring ChainSelector: %d -> %d' % (old_val, new_val))
                                restored += 1
                            except Exception as e:
                                self.log_message('LTC: Error restoring ChainSelector: %s' % str(e))
                        else:
                            self.log_message('LTC: Could not resolve ChainSelector for restore')
                    # Check for MacroControls special case
                    elif self._is_macro_control_param(entry['lom_path']):
                        macro_param = self._get_macro_control_parameter(all_tracks[entry['track_idx']], entry['lom_path'])
                        if macro_param is not None:
                            try:
                                old_val = macro_param.value
                                new_val = max(macro_param.min, min(macro_param.max, saved[key]))
                                macro_param.value = new_val
                                self.log_message('LTC: Restoring %s: %.3f -> %.3f' % (param_name, old_val, new_val))
                                restored += 1
                            except Exception as e:
                                self.log_message('LTC: Error restoring MacroControl: %s' % str(e))
                        else:
                            self.log_message('LTC: Could not resolve MacroControl for restore')
                    else:
                        # Regular parameter - try device ID method first
                        param = None
                        if entry['param_index'] >= 0:
                            param = self._find_parameter_by_device_id(
                                all_tracks[entry['track_idx']],
                                entry['device_class'],
                                entry['device_name'],
                                entry['device_path'],
                                entry['param_index']
                            )
                        
                        # Fallback: If param_index was -1 or device ID method failed, try LOM path navigation
                        if param is None and entry['lom_path']:
                            self.log_message('LTC: [RESTORE] Trying LOM path fallback for %s' % param_name)
                            param = self._find_parameter_by_lom_path(
                                all_tracks[entry['track_idx']],
                                entry['lom_path']
                            )
                        
                        if param is not None:
                            try:
                                old_val = param.value
                                new_val = max(param.min, min(param.max, saved[key]))
                                param.value = new_val
                                self.log_message('LTC: Restoring %s: %.3f -> %.3f' % (param_name, old_val, new_val))
                                restored += 1
                            except Exception as e:
                                self.log_message('LTC: Error restoring %s: %s' % (param_name, str(e)))
                        else:
                            self.log_message('LTC: Could not resolve for restore: %s' % param_name)
        self.log_message('LTC: Restored %d params for track %d' % (restored, sel_idx))

    def _handle_save_and_rescan(self):
        """Trigger MIDI_Map_Scanner to regenerate JSON, then reload mappings."""
        try:
            self.log_message('LTC: *** RESCAN triggered ***')
            
            # Find and trigger the MIDI_Map_Scanner
            scanner_found = False
            for cs in self.song().control_surfaces():
                if cs.__class__.__name__ == 'MidiMapScanner':
                    self.log_message('LTC: Triggering MIDI_Map_Scanner...')
                    cs._scan_and_write()
                    scanner_found = True
                    break
            
            if not scanner_found:
                self.log_message('LTC: WARNING - MIDI_Map_Scanner not found, loading stale JSON')
            
            # Reload JSON mappings (either fresh or existing)
            self._cc_mappings = self._load_json_mappings()
            self.log_message('LTC: JSON mappings reloaded')
            
            # Clear saved values to force fresh save on next track switch
            self._saved_values.clear()
            self.log_message('LTC: Saved values cleared - will resave on next track switch')
            
        except Exception as e:
            self.log_message('LTC: Error in rescan: %s' % str(e))

    def _is_chain_selector_param(self, lom_path):
        """Check if lom_path refers to a ChainSelector parameter."""
        if lom_path and len(lom_path) > 0:
            last_part = lom_path[-1]
            return 'ChainSelector' in last_part
        return False
    
    def _get_chain_selector_property(self, track, lom_path):
        """Get the chain selector property for a rack device.
        
        ChainSelector is NOT in device.parameters - it's accessed via
        device.view.selected_chain (an integer index of active chain).
        """
        try:
            # Navigate to the rack device
            obj = track
            for part in lom_path[:-1]:  # Skip last part (param <ChainSelector>)
                if part.startswith('devices['):
                    import re
                    m = re.match(r'devices\[(\d+)\]', part)
                    if m:
                        idx = int(m.group(1))
                        if idx < len(obj.devices):
                            obj = obj.devices[idx]
                        else:
                            return None
            
            # For racks, return the view.selected_chain index as a pseudo-parameter
            if hasattr(obj, 'view') and hasattr(obj.view, 'selected_chain') and hasattr(obj, 'chains'):
                # Return a dict with get/set accessors
                # selected_chain returns a Chain object, we need the index
                def get_chain_index():
                    try:
                        selected = obj.view.selected_chain
                        chains_list = list(obj.chains)
                        if selected:
                            idx = chains_list.index(selected)
                            self.log_message('LTC: [DEBUG] ChainSelector GET: selected_chain=%s, chains=%s, returning index=%d' % (selected.name if hasattr(selected, 'name') else str(selected), [c.name if hasattr(c, 'name') else str(c) for c in chains_list], idx))
                            return idx
                        self.log_message('LTC: [DEBUG] ChainSelector GET: No selected_chain, returning 0')
                        return 0
                    except (ValueError, AttributeError) as e:
                        self.log_message('LTC: [DEBUG] ChainSelector GET error: %s, returning 0' % str(e))
                        return 0
                
                def set_chain_index(index):
                    try:
                        idx = int(index)
                        chains_list = list(obj.chains)
                        self.log_message('LTC: [DEBUG] ChainSelector SET: requesting index=%d, chains=%s' % (idx, [c.name if hasattr(c, 'name') else str(c) for c in chains_list]))
                        self.log_message('LTC: [DEBUG] Device obj=%s, has view=%s, has chains=%s' % (obj, hasattr(obj, 'view'), hasattr(obj, 'chains')))
                        if 0 <= idx < len(obj.chains):
                            current_before = obj.view.selected_chain
                            self.log_message('LTC: [DEBUG] Before set: selected_chain=%s' % (current_before.name if hasattr(current_before, 'name') else str(current_before)))
                            obj.view.selected_chain = obj.chains[idx]
                            current_after = obj.view.selected_chain
                            self.log_message('LTC: [DEBUG] After set: selected_chain=%s' % (current_after.name if hasattr(current_after, 'name') else str(current_after)))
                            self.log_message('LTC: [DEBUG] ChainSelector SET: SUCCESS - set to chain %s (index %d)' % (obj.chains[idx].name if hasattr(obj.chains[idx], 'name') else str(obj.chains[idx]), idx))
                        else:
                            self.log_message('LTC: [DEBUG] ChainSelector SET: FAILED - index %d out of range (0-%d)' % (idx, len(obj.chains)-1))
                    except Exception as e:
                        self.log_message('LTC: Error setting chain index: %s' % str(e))
                
                return {
                    'get': get_chain_index,
                    'set': set_chain_index,
                    'chains': list(obj.chains)
                }
        except Exception as e:
            self.log_message('LTC: Error accessing chain selector: %s' % str(e))
        return None

    def _is_macro_control_param(self, lom_path):
        """Check if lom_path refers to a MacroControls parameter."""
        if lom_path and len(lom_path) > 0:
            last_part = lom_path[-1]
            return 'MacroControls' in last_part
        return False
    
    def _get_macro_control_parameter(self, track, lom_path):
        """Get a macro control parameter for a rack device.
        
        MacroControls are NOT in device.parameters - they're accessed via
        device.macros_mapped[index] where index comes from param tag like
        'MacroControls.2' (macro knob #2).
        """
        try:
            import re
            
            # Extract macro index from param tag like "param <MacroControls.2>"
            last_part = lom_path[-1] if lom_path else ''
            m = re.match(r'param <MacroControls\.(\d+)>', last_part)
            if not m:
                return None
            macro_index = int(m.group(1))
            
            # Navigate to the rack device
            obj = track
            for part in lom_path[:-1]:  # Skip last part (param <MacroControls.X>)
                if part.startswith('devices['):
                    m = re.match(r'devices\[(\d+)\]', part)
                    if m:
                        idx = int(m.group(1))
                        if idx < len(obj.devices):
                            obj = obj.devices[idx]
                        else:
                            return None
                elif part.startswith('chains['):
                    m = re.match(r'chains\[(\d+)\]', part)
                    if m:
                        idx = int(m.group(1))
                        if hasattr(obj, 'chains') and idx < len(obj.chains):
                            obj = obj.chains[idx]
                        else:
                            return None
            
            # For racks, macros are the first 8 parameters (indices 0-7)
            if hasattr(obj, 'parameters') and macro_index < len(obj.parameters):
                # Verify it's actually a macro by checking if macros_mapped exists
                if hasattr(obj, 'macros_mapped') and macro_index < len(obj.macros_mapped):
                    return obj.parameters[macro_index]
                else:
                    self.log_message('LTC: Device has no macros_mapped array')
                    return None
            else:
                self.log_message('LTC: Macro %d out of range on %s' % (macro_index, obj.class_name if hasattr(obj, 'class_name') else '?'))
        except Exception as e:
            self.log_message('LTC: Error accessing macro control: %s' % str(e))
        return None

    def _resolve_live_parameter(self, track, lom_path):
        """Navigate LOM path to find the live parameter object.
        
        Copied from MIDI_Map_Scanner for consistent parameter resolution.
        Returns dict with 'device', 'param', 'device_path' or None if not found.
        """
        import re
        
        obj = track
        device = None
        device_path = []
        
        for step_idx, part in enumerate(lom_path):
            if part.startswith('devices['):
                m = re.match(r'devices\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'devices'):
                        if idx < len(obj.devices):
                            obj = obj.devices[idx]
                            device = obj
                        else:
                            return None
                    else:
                        return None
                else:
                    return None
            elif part.startswith('chains['):
                m = re.match(r'chains\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'chains'):
                        if idx < len(obj.chains):
                            chain = obj.chains[idx]
                            chain_name = chain.name if hasattr(chain, 'name') else 'Chain %d' % idx
                            parent_rack_name = device.name if (device and hasattr(device, 'name')) else 'Rack'
                            device_path.append({'type': 'chain', 'index': idx, 'name': chain_name, 'parent_rack_name': parent_rack_name})
                            obj = chain
                            device = None  # Reset device context when entering chain
                        else:
                            return None
                    else:
                        return None
                else:
                    return None
            elif part.startswith('return_chains['):
                m = re.match(r'return_chains\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'return_chains') and idx < len(obj.return_chains):
                        chain = obj.return_chains[idx]
                        chain_name = chain.name if hasattr(chain, 'name') else 'Return Chain %d' % idx
                        device_path.append({'type': 'return_chain', 'index': idx, 'name': chain_name})
                        obj = chain
                    else:
                        return None
            elif part.startswith('param <'):
                m = re.match(r'param <(.+)>', part)
                if m:
                    param_tag = m.group(1)
                    
                    # Special case: ChainSelector on rack devices
                    if param_tag == 'ChainSelector' and device:
                        if hasattr(device, 'class_name') and 'GroupDevice' in device.class_name:
                            for p in device.parameters:
                                if p.original_name == 'Chain Selector' or 'chain' in p.name.lower() or p.original_name == 'ChainSelector':
                                    return {'device': device, 'param': p, 'device_path': device_path}
                    
                    # If no device context, we're at chain level
                    if device is None:
                        # Check if this is a chain mixer parameter (Volume, Pan, Activator)
                        if hasattr(obj, 'mixer_device'):
                            mixer = obj.mixer_device
                            # ChainMixerDevice: Volume and Pan are direct properties
                            if param_tag == 'Volume' and hasattr(mixer, 'volume'):
                                return {'device': mixer, 'param': mixer.volume, 'device_path': device_path}
                            elif param_tag == 'Pan' and hasattr(mixer, 'panning'):
                                return {'device': mixer, 'param': mixer.panning, 'device_path': device_path}
                            elif param_tag == 'ChainActivator' and hasattr(mixer, 'chain_activator'):
                                return {'device': mixer, 'param': mixer.chain_activator, 'device_path': device_path}
                        
                        # Search chain's devices for the parameter
                        if hasattr(obj, 'devices'):
                            for dev_idx, dev in enumerate(obj.devices):
                                # Try exact match
                                for p in dev.parameters:
                                    if p.original_name == param_tag or p.name == param_tag:
                                        return {'device': dev, 'param': p, 'device_path': device_path}
                                
                                # Try name mappings
                                name_map = {
                                    'OutputGain': ['Output Gain', 'Gain', 'Output Level', 'Level'],
                                    'DryWet': ['Dry/Wet', 'Dry', 'Mix'],
                                    'Envelope1_Decay': ['Env 1 Decay', 'Envelope 1 Decay', 'Decay'],
                                }
                                
                                search_names = name_map.get(param_tag, [param_tag])
                                if not isinstance(search_names, list):
                                    search_names = [search_names]
                                
                                # Add user mapping if available
                                dev_class_name = dev.class_name if hasattr(dev, 'class_name') else type(dev).__name__
                                if dev_class_name in self._user_mappings:
                                    if param_tag in self._user_mappings[dev_class_name]:
                                        user_mapped_name = self._user_mappings[dev_class_name][param_tag]
                                        if user_mapped_name not in search_names:
                                            search_names.insert(0, user_mapped_name)
                                
                                for search_name in search_names:
                                    for p in dev.parameters:
                                        if p.original_name == search_name or p.name == search_name:
                                            return {'device': dev, 'param': p, 'device_path': device_path}
                        return None
                    
                    # If we have a device context, search its parameters
                    if device:
                        # Try exact match first
                        for p in device.parameters:
                            if p.original_name == param_tag or p.name == param_tag:
                                return {'device': device, 'param': p, 'device_path': device_path}
                        
                        # Try name mappings
                        name_map = {
                            'OutputGain': ['Output Gain', 'Gain', 'Output Level', 'Level'],
                            'DryWet': ['Dry/Wet', 'Dry', 'Mix'],
                            'Envelope1_Decay': ['Env 1 Decay', 'Envelope 1 Decay', 'Decay'],
                        }
                        
                        search_names = name_map.get(param_tag, [param_tag])
                        if not isinstance(search_names, list):
                            search_names = [search_names]
                        
                        # Add user mapping if available
                        dev_class_name = device.class_name if hasattr(device, 'class_name') else type(device).__name__
                        if dev_class_name in self._user_mappings:
                            if param_tag in self._user_mappings[dev_class_name]:
                                user_mapped_name = self._user_mappings[dev_class_name][param_tag]
                                if user_mapped_name not in search_names:
                                    search_names.insert(0, user_mapped_name)
                        
                        # Try each alternative name
                        for search_name in search_names:
                            for p in device.parameters:
                                if p.original_name == search_name or p.name == search_name:
                                    return {'device': device, 'param': p, 'device_path': device_path}
                return None
        
        return None

    def _find_parameter_by_lom_path(self, track, lom_path):
        """Legacy wrapper - calls _resolve_live_parameter and extracts param."""
        result = self._resolve_live_parameter(track, lom_path)
        if result:
            return result['param']
        return None

    def _find_parameter_by_device_id(self, track, device_class, device_name, device_path, param_index):
        """Find a parameter by searching for device by class_name and name.
        
        Args:
            track: Live track object
            device_class: Device class_name (e.g., 'Chorus2')
            device_name: Device custom name
            device_path: Chain path for nested racks (list of dicts)
            param_index: Parameter index within the device
        """
        if not device_class or param_index < 0:
            self.log_message('LTC: [FIND] Skipping - device_class=%s, param_index=%d' 
                           % (device_class, param_index))
            return None
        
        try:
            # Start at track level
            obj = track
            
            # Navigate through device_path for nested racks
            for path_entry in device_path:
                if path_entry.get('type') == 'chain':
                    chain_name = path_entry.get('name', '')
                    if hasattr(obj, 'chains'):
                        # Find chain by name
                        found = False
                        for chain in obj.chains:
                            if hasattr(chain, 'name') and chain.name == chain_name:
                                obj = chain
                                found = True
                                break
                        if not found:
                            # Fallback to index if name doesn't match
                            idx = path_entry.get('index', -1)
                            if idx >= 0 and idx < len(obj.chains):
                                obj = obj.chains[idx]
                            else:
                                return None
                elif path_entry.get('type') == 'return_chain':
                    chain_name = path_entry.get('name', '')
                    if hasattr(obj, 'return_chains'):
                        found = False
                        for chain in obj.return_chains:
                            if hasattr(chain, 'name') and chain.name == chain_name:
                                obj = chain
                                found = True
                                break
                        if not found:
                            idx = path_entry.get('index', -1)
                            if idx >= 0 and idx < len(obj.return_chains):
                                obj = obj.return_chains[idx]
                            else:
                                return None
            
            # Search for device by class_name and name
            if hasattr(obj, 'devices'):
                for device in obj.devices:
                    # Match by class_name first (most reliable)
                    if device.class_name == device_class:
                        # If device has custom name, verify it matches
                        if device_name and device.name != device_name:
                            continue
                        # Found the device, get parameter by index
                        if param_index < len(device.parameters):
                            return device.parameters[param_index]
                        else:
                            self.log_message('LTC: param_index %d out of range on %s (max %d)' 
                                           % (param_index, device_class, len(device.parameters)-1))
                            return None
            
            self.log_message('LTC: Could not find device %s "%s"' % (device_class, device_name))
        except Exception as e:
            self.log_message('LTC: Error finding parameter: %s' % str(e))
        
        return None

    def _resolve_lom_path(self, track, lom_path, param_index=-1):
        """DEPRECATED: Legacy method for backward compat with old JSON format.
        Resolve an lom_path list (from JSON) to a Live DeviceParameter.
        """
        import re
        
        obj = track
        for step in lom_path:
            # devices[N] <DeviceName>
            m = re.match(r'devices\[(\d+)\]', step)
            if m:
                idx = int(m.group(1))
                try:
                    obj = obj.devices[idx]
                except (IndexError, AttributeError):
                    return None
                continue
            
            # chains[N]
            m = re.match(r'chains\[(\d+)\]', step)
            if m:
                idx = int(m.group(1))
                try:
                    obj = obj.chains[idx]
                except (IndexError, AttributeError):
                    return None
                continue
            
            # param <ParamName>
            m = re.match(r'param <(.+)>', step)
            if m:
                # Prefer param_index if available (reliable)
                if param_index >= 0:
                    try:
                        if param_index < len(obj.parameters):
                            return obj.parameters[param_index]
                        else:
                            self.log_message('LTC: param_index %d out of range (max %d)' 
                                           % (param_index, len(obj.parameters)-1))
                    except Exception as e:
                        self.log_message('LTC: Error using param_index: %s' % str(e))
                
                # Fallback to name matching
                param_name = m.group(1)
                return self._find_parameter(obj, param_name)
        
        return None
    
    def _find_parameter(self, device, param_name):
        """Find a parameter by name on a device."""
        # Common XML→Live API name mappings
        name_map = {
            'OutputGain': 'Gain',
            'DryWet': 'Dry/Wet',
        }
        
        # Try the mapped name first
        search_name = name_map.get(param_name, param_name)
        
        try:
            for p in device.parameters:
                if p.original_name == search_name or p.name == search_name:
                    return p
                # Also try the original unmapped name
                if p.original_name == param_name or p.name == param_name:
                    return p
            
            # Log available params if not found
            param_names = [p.original_name for p in device.parameters]
            self.log_message('LTC: Could not find "%s" or "%s" in: %s' 
                           % (param_name, search_name, str(param_names)))
        except Exception as e:
            self.log_message('LTC: Error in _find_parameter: %s' % str(e))
        return None

    # ── Track selection ───────────────────────────────────────────────────────

    def _lom_path_key(self, lom_path):
        """Convert LOM path list to a string key for dictionary storage."""
        if not lom_path:
            return ''
        return '|'.join(lom_path)

    def _select_next_track(self):
        tracks = list(self.song().visible_tracks)
        sel = self.song().view.selected_track
        try:
            idx = tracks.index(sel)
            if idx < len(tracks) - 1:
                self.song().view.selected_track = tracks[idx + 1]
        except ValueError:
            if tracks:
                self.song().view.selected_track = tracks[0]

    def _select_prev_track(self):
        tracks = list(self.song().visible_tracks)
        sel = self.song().view.selected_track
        try:
            idx = tracks.index(sel)
            if idx > 0:
                self.song().view.selected_track = tracks[idx - 1]
        except ValueError:
            if tracks:
                self.song().view.selected_track = tracks[0]
