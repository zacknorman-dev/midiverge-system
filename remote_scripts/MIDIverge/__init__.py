"""
MIDIverge - Unified MIDI Controller for Ableton Live
Combines scanning, UDP feedback, and track memory into one control surface

Components:
  - MIDI Map Scanner: Reads .als XML to discover CC mappings
  - UDP Sender: Broadcasts parameter updates to overlay UI
  - Track Memory: Saves/restores parameter values per track
  
Hardware: Seeeduino XIAO RP2040 with 10 encoders (CC71-79)
"""

import Live
from _Framework.ControlSurface import ControlSurface
import socket
import json
import os
import time
import gzip
import xml.etree.ElementTree as ET


def create_instance(c_instance):
    """Required factory function for Ableton to instantiate the script"""
    return MIDIverge(c_instance)


class MIDIverge(ControlSurface):
    """Unified control surface for XIAO MIDI controller"""
    
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._c_instance = c_instance
        self.song = c_instance.song()
        
        # ────────────────────────────────────────────────────────────────
        # File paths
        # ────────────────────────────────────────────────────────────────
        self._base_path = r"C:\Users\zackn\Documents\midi overlay"
        self._scanner_file = os.path.join(self._base_path, "current_scan.json")
        self._manual_mappings_file = os.path.join(self._base_path, "manual_mappings.json")
        self._trigger_file = os.path.join(self._base_path, "do_scan.txt")
        self._log_file = os.path.join(self._base_path, "midiverge_debug.log")
        
        # ────────────────────────────────────────────────────────────────
        # State - Scanner
        # ────────────────────────────────────────────────────────────────
        self._scanner_data = {}
        self._scanner_mtime = 0
        self._startup_scan_done = False
        self._update_display_count = 0
        self._was_dirty = False  # Track is_dirty state for save detection
        
        # ────────────────────────────────────────────────────────────────
        # State - UDP Sender
        # ────────────────────────────────────────────────────────────────
        self._sock = None
        self._overlay_address = ('127.0.0.1', 9001)
        self._parameter_listeners = []
        self._listener_functions = {}  # {cc: function} to store callbacks
        self._current_track = None
        self._current_track_index = -1
        self._last_sent_values = {}  # {cc: (value, str_value)} - prevent duplicate sends
        self._observed_ranges = {}  # {'track_NAME_cc_##': {'min': float, 'max': float}} - track-specific ranges
        
        # ────────────────────────────────────────────────────────────────
        # State - Track Memory
        # ────────────────────────────────────────────────────────────────
        self._cc_mappings = {}  # {cc_int: [(track_index, lom_path_list)]}
        self._saved_values = {}  # {track_index: {key: float}}
        self._previous_track_index = None
        self._pending_restore_track = None  # Track index to restore in update_display
        
        # ────────────────────────────────────────────────────────────────
        # State - Manual Mappings (shared by all modules)
        # ────────────────────────────────────────────────────────────────
        self._manual_mappings = {}
        
        # ────────────────────────────────────────────────────────────────
        # Target CCs (71-78 for encoders)
        # ────────────────────────────────────────────────────────────────
        self._target_ccs = list(range(71, 79))
        
        # ────────────────────────────────────────────────────────────────
        # Initialization
        # ────────────────────────────────────────────────────────────────
        self.file_log("=" * 80)
        self.file_log(f"MIDIverge __init__ started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize UDP socket
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.file_log("UDP socket initialized")
        except Exception as e:
            self._sock = None
            self.file_log(f"Failed to create UDP socket: {e}")
        
        # Load manual mappings (shared resource)
        self.load_manual_mappings()
        
        # Load scanner data
        self.load_scanner_json()
        
        # Setup track selection listener for automatic save/restore
        self.song.view.add_selected_track_listener(self._on_track_changed)
        
        # Initialize is_dirty state for polling in update_display
        self._was_dirty = self.song.is_dirty
        
        # Initialize previous track index for track memory
        all_tracks = self._get_all_tracks()
        try:
            self._previous_track_index = all_tracks.index(self.song.view.selected_track)
        except (ValueError, AttributeError):
            self._previous_track_index = 0
        
        # Initial track setup
        self.file_log("Calling initial track changed...")
        self._on_track_changed()
        
        msg = "MIDIverge Remote Script loaded!"
        self.log_message(msg)
        self.file_log(msg)
        self._send_udp_message({
            'type': 'status',
            'message': 'MIDIverge connected'
        })
        self.file_log("__init__ completed successfully")
    
    # ════════════════════════════════════════════════════════════════════════
    # CONTROL SURFACE INTERFACE (Required by Ableton)
    # ════════════════════════════════════════════════════════════════════════
    
    def disconnect(self):
        """Cleanup when script is unloaded"""
        self.log_message("MIDIverge disconnecting...")
        self.file_log("disconnect() called")
        
        # Remove listeners
        self._remove_parameter_listeners()
        if self.song.view.selected_track_has_listener(self._on_track_changed):
            self.song.view.remove_selected_track_listener(self._on_track_changed)
        
        # Close UDP socket
        if self._sock:
            self._sock.close()
        
        ControlSurface.disconnect(self)
    
    def can_lock_to_devices(self):
        """Required by Ableton"""
        return False
    
    def build_midi_map(self, midi_map_handle):
        """Forward CC79 for track selection"""
        script_handle = self._c_instance.handle()
        Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, 0, 79)
        self.file_log("CC79 forwarded for track selection")
    
    def receive_midi(self, midi_bytes):
        """Handle incoming MIDI - CC79 track selector"""
        if len(midi_bytes) >= 3:
            status = midi_bytes[0]
            cc = midi_bytes[1]
            value = midi_bytes[2]
            
            # Log ALL incoming MIDI
            self.file_log(f"receive_midi called: status={status}, cc={cc}, value={value}")
            
            # CC79 = track selector
            if cc == 79:
                self.file_log(f"CC79 received: value={value}")
                self._handle_track_selector(value)
    
    def _handle_track_selector(self, value):
        """Handle CC79 relative encoder for track selection"""
        all_tracks = self._get_all_tracks()
        current_idx = self._current_track_index if self._current_track_index >= 0 else 0
        
        # Relative encoder: 1 = forward, 127 = backward
        if value == 1:
            new_idx = min(current_idx + 1, len(all_tracks) - 1)
        elif value == 127:
            new_idx = max(current_idx - 1, 0)
        else:
            return
        
        if new_idx != current_idx and new_idx < len(all_tracks):
            self.song.view.selected_track = all_tracks[new_idx]
            self.file_log(f"CC79 track selector: {current_idx} -> {new_idx}")
    
    def suggest_input_port(self):
        """Required by Ableton"""
        return ''
    
    def suggest_output_port(self):
        """Required by Ableton"""
        return ''
    
    def refresh_state(self):
        """Required by Ableton"""
        pass
    
    def update_display(self):
        """Called periodically by Ableton - used for scanner triggers, save detection, and deferred restore"""
        ControlSurface.update_display(self)
        self._update_display_count += 1
        
        # Handle deferred track restore (must happen outside notification callbacks)
        if hasattr(self, '_pending_restore_track') and self._pending_restore_track is not None:
            track_idx = self._pending_restore_track
            self._pending_restore_track = None
            self.file_log(f"*** update_display: Executing deferred restore for track {track_idx} ***")
            try:
                self._restore_current_track()
            except Exception as e:
                self.file_log(f"*** update_display restore error: {e} ***")
        
        # Run startup scan once after ~3 seconds (6 calls at ~500ms each)
        if not self._startup_scan_done and self._update_display_count == 6:
            self._startup_scan_done = True
            self.log_message('[STARTUP] Running initial scan')
            self._scan_from_file()
        
        # Poll is_dirty to detect saves (is_dirty going from True to False)
        try:
            current_dirty = self.song.is_dirty
            if self._was_dirty and not current_dirty:
                self.file_log("[SAVE DETECTED] Project saved - triggering scan")
                self.log_message('[SAVE] Project saved - running scan')
                self._scan_from_file()
            self._was_dirty = current_dirty
        except Exception as e:
            self.file_log(f"Error checking is_dirty: {e}")
        
        # Check for manual trigger file (do_scan.txt)
        if os.path.exists(self._trigger_file):
            try:
                os.remove(self._trigger_file)
                self.log_message('[TRIGGER] do_scan.txt detected - starting scan')
                self._scan_from_file()
            except Exception as e:
                self.log_message(f'[TRIGGER] Error removing do_scan.txt: {e}')
        
        # Check if scanner file was updated externally (auto-reload)
        try:
            current_mtime = os.path.getmtime(self._scanner_file)
            if current_mtime > self._scanner_mtime:
                self.file_log(f"Scanner file changed (mtime: {current_mtime} > {self._scanner_mtime})")
                self.load_scanner_json()
                self.load_manual_mappings()  # Reload manual mappings too
                self._on_track_changed()  # Refresh current track with new mappings
        except FileNotFoundError:
            pass
        except Exception as e:
            self.file_log(f"Error checking scanner file mtime: {e}")
    
    # ════════════════════════════════════════════════════════════════════════
    # LOGGING UTILITIES
    # ════════════════════════════════════════════════════════════════════════
    
    def file_log(self, message):
        """Log to file for debugging"""
        try:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
        except Exception:
            pass  # Silent fail
    
    # ════════════════════════════════════════════════════════════════════════
    # SCANNER MODULE - XML Parsing
    # ════════════════════════════════════════════════════════════════════════
    
    def _scan_from_file(self):
        """Read .als file and extract MIDI mappings"""
        als_path = self.song.file_path
        
        if not als_path:
            self.log_message('[SCAN] Project not saved - cannot scan')
            return
        
        self.log_message(f'[SCAN] Reading from: {als_path}')
        
        # Parse .als file (gzipped XML)
        try:
            with gzip.open(als_path, 'rb') as fh:
                root = ET.fromstring(fh.read())
        except Exception as e:
            self.log_message(f'[SCAN] Failed to parse .als: {e}')
            return
        
        # Build parent map for tree navigation
        parent_map = {child: parent for parent in root.iter() for child in parent}
        
        # Find tracks
        tracks_elem = root.find('LiveSet/Tracks')
        if tracks_elem is None:
            self.log_message('[SCAN] LiveSet/Tracks not found')
            return
        
        # Get live track references
        live_tracks = self._get_all_tracks()
        
        # Collect all tracks
        all_tracks = []
        for track_idx, track_elem in enumerate(tracks_elem):
            name_elem = track_elem.find('.//Name[@Value]')
            xml_track_name = name_elem.get('Value', '') if name_elem is not None else ''
            
            live_name = ''
            if track_idx < len(live_tracks):
                try:
                    live_name = live_tracks[track_idx].name
                except Exception:
                    pass
            
            all_tracks.append({
                'track_index': track_idx,
                'track_type': track_elem.tag,
                'track_name_xml': xml_track_name,
                'track_name_live': live_name
            })
        
        # Collect MIDI mappings for CC71-78
        results = []
        total_keymidi = 0
        target_cc_found = 0
        
        for track_idx, track_elem in enumerate(tracks_elem):
            track_info = all_tracks[track_idx]
            
            # Find KeyMidi elements (MIDI mappings)
            for km in track_elem.iter('KeyMidi'):
                total_keymidi += 1
                is_note_elem = km.find('IsNote')
                if (is_note_elem is None or is_note_elem.get('Value', 'true').lower() == 'true'):
                    continue
                
                cc_elem = km.find('NoteOrController')
                ch_elem = km.find('Channel')
                if cc_elem is None:
                    continue
                
                cc = int(cc_elem.get('Value', -1))
                channel = int(ch_elem.get('Value', -1)) if ch_elem is not None else -1
                
                # Only process target CCs (71-78)
                if cc not in self._target_ccs:
                    continue
                
                target_cc_found += 1
                
                # channel > 15 is unmapped
                if cc < 0 or channel < 0 or channel > 15:
                    self.log_message(f'[SCAN] Skipping CC{cc} - invalid channel {channel}')
                    continue
                
                param_elem = parent_map.get(km)
                param_tag = param_elem.tag if param_elem is not None else '?'
                
                # Try to resolve the parameter
                result = self._resolve_parameter(track_idx, param_tag, km, parent_map, live_tracks)
                result['track_index'] = track_idx
                result['track_type'] = track_info['track_type']
                result['track_name_xml'] = track_info['track_name_xml']
                result['track_name_live'] = track_info['track_name_live']
                result['cc'] = cc
                result['channel'] = channel
                result['param_tag'] = param_tag
                
                results.append(result)
        
        self.log_message(f'[SCAN] Found {total_keymidi} KeyMidi elements, {target_cc_found} target CCs (71-78)')
        
        # Write to JSON file
        output_data = {'mappings': results}
        try:
            with open(self._scanner_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2)
            self._scanner_mtime = os.path.getmtime(self._scanner_file)
            self.log_message(f'[SCAN] Wrote {len(results)} mappings to {self._scanner_file}')
        except Exception as e:
            self.log_message(f'[SCAN] Failed to write JSON: {e}')
        
        # Reload the scanner data
        self.load_scanner_json()
        
        # Refresh current track with new mappings
        self._on_track_changed()
    
    def _resolve_parameter(self, track_idx, param_tag, km_elem, parent_map, live_tracks):
        """Attempt to resolve XML parameter reference to Live API path"""
        result = {
            'param_index': -1,
            'device_index': -1,
            'param_live_name': '',
            'device_class_name': '',
            'device_name': '',
            'device_path': [],
            'is_mixer_param': False,
            'lom_path': [],
            'resolution_status': 'failed',
            'resolution_error': '',
            'available_parameters': []
        }
        
        if track_idx >= len(live_tracks):
            result['resolution_error'] = 'Track index out of range'
            return result
        
        track = live_tracks[track_idx]
        
        # Try to find the device by walking up the XML tree
        current = km_elem
        device_elem = None
        while current is not None:
            parent = parent_map.get(current)
            if parent is not None and parent.tag in ('OriginalSimpler', 'MultiSampler', 'Operator', 
                                                       'LoungeLizard', 'StringStudio', 'Collision',
                                                       'InstrumentVector', 'MidiEffectVector', 
                                                       'AudioEffectVector', 'Compressor2', 'AutoFilter',
                                                       'Reverb', 'Eq8', 'PluginDevice'):
                device_elem = parent
                break
            current = parent
        
        if device_elem is None:
            result['resolution_error'] = 'Could not find device element in XML'
            return result
        
        device_name_elem = device_elem.find('.//UserName[@Value]')
        device_name_xml = device_name_elem.get('Value', '') if device_name_elem is not None else ''
        
        # Try to match device by name and find parameter
        for dev_idx, device in enumerate(track.devices):
            try:
                if device.name == device_name_xml or device.class_name in device_elem.tag:
                    # Build available parameters list
                    params = []
                    for p_idx, param in enumerate(device.parameters):
                        try:
                            params.append({
                                'index': p_idx,
                                'name': str(param.name),
                                'original_name': str(param.original_name),
                                'min': float(param.min),
                                'max': float(param.max),
                                'value': float(param.value)
                            })
                        except Exception:
                            pass
                    
                    result['available_parameters'] = params
                    
                    # Try to match parameter by tag name
                    for p_idx, param in enumerate(device.parameters):
                        try:
                            param_name = str(param.name).replace(' ', '')
                            param_orig = str(param.original_name).replace(' ', '')
                            search_tag = param_tag.replace(' ', '')
                            
                            if (search_tag.lower() in param_name.lower() or 
                                search_tag.lower() in param_orig.lower() or
                                param_name.lower() in search_tag.lower()):
                                result['param_index'] = p_idx
                                result['device_index'] = dev_idx
                                result['param_live_name'] = str(param.name)
                                result['device_class_name'] = device.class_name
                                result['device_name'] = device.name
                                result['lom_path'] = ['devices', str(dev_idx), 'parameters', str(p_idx)]
                                result['resolution_status'] = 'success'
                                return result
                        except Exception:
                            pass
                    
                    # If we found the device but not the parameter
                    if params:
                        result['device_index'] = dev_idx
                        result['device_class_name'] = device.class_name
                        result['device_name'] = device.name
                        result['resolution_error'] = f'Found device but failed to match parameter: {param_tag}'
                        return result
            except Exception as e:
                pass
        
        result['resolution_error'] = f'Could not find device: {device_name_xml}'
        return result
    
    # ════════════════════════════════════════════════════════════════════════
    # SCANNER MODULE - Data Loading
    # ════════════════════════════════════════════════════════════════════════
    
    def load_scanner_json(self):
        """Load scanner JSON with mappings"""
        try:
            with open(self._scanner_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._scanner_data = data.get('mappings', [])
                self._scanner_mtime = os.path.getmtime(self._scanner_file)
                self.file_log(f"Loaded {len(self._scanner_data)} mappings from scanner")
                
                # Build CC mappings for track memory module
                self._cc_mappings = {}
                for mapping in self._scanner_data:
                    if mapping.get('resolution_status') == 'success':
                        cc = mapping.get('cc')
                        track_idx = mapping.get('track_index')
                        lom_path = mapping.get('lom_path', [])
                        
                        if cc and track_idx is not None and lom_path:
                            if cc not in self._cc_mappings:
                                self._cc_mappings[cc] = []
                            self._cc_mappings[cc].append((track_idx, lom_path))
        
        except FileNotFoundError:
            self.file_log("Scanner file not found - will create on first scan")
            self._scanner_data = []
        except Exception as e:
            self.file_log(f"Error loading scanner JSON: {e}")
            self._scanner_data = []
    
    def load_manual_mappings(self):
        """Load manual mappings from JSON"""
        try:
            with open(self._manual_mappings_file, 'r', encoding='utf-8') as f:
                self._manual_mappings = json.load(f)
                self.file_log(f"Loaded {len(self._manual_mappings)} manual mappings")
                
                # Extract observed ranges from manual mappings (track-specific)
                for key, mapping in self._manual_mappings.items():
                    if 'observed_min' in mapping and 'observed_max' in mapping:
                        # Key format: "track_NAME_cc_##" - use entire key
                        self._observed_ranges[key] = {
                            'min': float(mapping['observed_min']),
                            'max': float(mapping['observed_max'])
                        }
                        self.file_log(f"Loaded observed range for {key}: {mapping['observed_min']} to {mapping['observed_max']}")
        except FileNotFoundError:
            self.file_log("Manual mappings file not found")
            self._manual_mappings = {}
        except Exception as e:
            self.file_log(f"Error loading manual mappings: {e}")
            self._manual_mappings = {}
    
    def save_manual_mappings(self):
        """Save manual mappings to JSON"""
        try:
            with open(self._manual_mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self._manual_mappings, f, indent=2)
                self.file_log("Saved manual mappings")
        except Exception as e:
            self.file_log(f"Error saving manual mappings: {e}")
    
    # ════════════════════════════════════════════════════════════════════════
    # TRACK MEMORY MODULE - Save/Restore
    # ════════════════════════════════════════════════════════════════════════
    
    def _resolve_mfl_path(self, mfl_path):
        """Resolve an MFL path to a parameter object
        Example: 'live_set tracks 2 devices 0 parameters 17'
        Returns the actual parameter object or None if not found
        """
        try:
            # Split the path into tokens
            tokens = mfl_path.split()
            
            # Start with the song (live_set)
            obj = self.song
            i = 0
            
            while i < len(tokens):
                token = tokens[i]
                
                if token == 'live_set':
                    # Already have the song
                    i += 1
                    continue
                
                elif token == 'tracks':
                    # Next token is the index
                    i += 1
                    if i < len(tokens):
                        track_idx = int(tokens[i])
                        all_tracks = list(self.song.tracks) + list(self.song.return_tracks)
                        if 0 <= track_idx < len(all_tracks):
                            obj = all_tracks[track_idx]
                        else:
                            self.file_log(f"MFL: Invalid track index {track_idx}")
                            return None
                        i += 1
                
                elif token == 'devices':
                    # Next token is the index
                    i += 1
                    if i < len(tokens) and hasattr(obj, 'devices'):
                        dev_idx = int(tokens[i])
                        if 0 <= dev_idx < len(obj.devices):
                            obj = obj.devices[dev_idx]
                        else:
                            self.file_log(f"MFL: Invalid device index {dev_idx}")
                            return None
                        i += 1
                
                elif token == 'chains':
                    # Next token is the index
                    i += 1
                    if i < len(tokens) and hasattr(obj, 'chains'):
                        chain_idx = int(tokens[i])
                        if 0 <= chain_idx < len(obj.chains):
                            obj = obj.chains[chain_idx]
                        else:
                            self.file_log(f"MFL: Invalid chain index {chain_idx}")
                            return None
                        i += 1
                
                elif token == 'parameters':
                    # Next token is the index
                    i += 1
                    if i < len(tokens) and hasattr(obj, 'parameters'):
                        param_idx = int(tokens[i])
                        if 0 <= param_idx < len(obj.parameters):
                            obj = obj.parameters[param_idx]
                        else:
                            self.file_log(f"MFL: Invalid parameter index {param_idx}")
                            return None
                        i += 1
                
                elif token == 'mixer_device':
                    # Get the mixer device
                    i += 1
                    if hasattr(obj, 'mixer_device'):
                        obj = obj.mixer_device
                    else:
                        self.file_log(f"MFL: No mixer_device on object")
                        return None
                
                elif token == 'volume':
                    # Get the volume parameter
                    i += 1
                    if hasattr(obj, 'volume'):
                        obj = obj.volume
                    else:
                        self.file_log(f"MFL: No volume on object")
                        return None
                
                elif token == 'panning':
                    # Get the panning parameter
                    i += 1
                    if hasattr(obj, 'panning'):
                        obj = obj.panning
                    else:
                        self.file_log(f"MFL: No panning on object")
                        return None
                
                else:
                    # Unknown token
                    self.file_log(f"MFL: Unknown token '{token}'")
                    i += 1
            
            return obj
            
        except Exception as e:
            self.file_log(f"MFL resolution error: {e}")
            return None
    
    def _save_track_by_index(self, track_index):
        """Save ALL CC-mapped parameters for a track using MFL paths"""
        self.file_log(f"*** _save_track_by_index ENTRY: track_index={track_index} ***")
        try:
            all_tracks = list(self.song.tracks) + list(self.song.return_tracks) + [self.song.master_track]
            
            if track_index < 0 or track_index >= len(all_tracks):
                self.file_log(f"_save_track_by_index: Invalid index {track_index}")
                return
            
            track = all_tracks[track_index]
            track_name = track.name if hasattr(track, 'name') else f'Track{track_index}'
            values = {}
            
            self.file_log(f"Track {track_index}: track_name = '{track_name}'")
            
            # Save ALL CC-mapped parameters using MFL paths from manual_mappings
            for cc in self._target_ccs:
                # Build possible manual mapping keys
                clean_track_name = track_name
                if '-' in clean_track_name:
                    clean_track_name = clean_track_name.split('-', 1)[1]
                
                # Also try with device name
                device_name = None
                if hasattr(track, 'devices') and len(track.devices) > 0:
                    device_name = track.devices[0].name if hasattr(track.devices[0], 'name') else None
                    if device_name:
                        device_name = device_name.replace(' ', '_')  # Match JSON key format
                
                # Try multiple key formats
                possible_keys = []
                if device_name:
                    possible_keys.append(f"track_{track_index+1}-{device_name}_cc_{cc}")
                
                # Also try with clean track name (without number prefix)
                clean_track_name = clean_track_name.replace(' ', '_')  # Match JSON key format
                possible_keys.append(f"track_{track_index+1}-{clean_track_name}_cc_{cc}")
                
                self.file_log(f"Track {track_index} CC{cc}: Trying keys: {possible_keys}")
                
                # Find the parameter using manual mapping
                param = None
                param_name = None
                
                for key in possible_keys:
                    if key in self._manual_mappings:
                        self.file_log(f"Track {track_index} CC{cc}: KEY FOUND: '{key}'")
                        mapping = self._manual_mappings[key]
                        if 'mfl_path' in mapping:
                            mfl_path = mapping['mfl_path']
                            # Resolve MFL path to get parameter
                            param = self._resolve_mfl_path(mfl_path)
                            if param and hasattr(param, 'name'):
                                param_name = param.name
                            self.file_log(f"Track {track_index}: Found CC{cc} via key '{key}'")
                            break
                        else:
                            self.file_log(f"Track {track_index} CC{cc}: Key '{key}' has no mfl_path")
                
                # If we found a parameter, save its value
                if param and hasattr(param, 'value'):
                    try:
                        value = param.value
                        values[f'cc_{cc}'] = value
                        display_name = param_name if param_name else f'CC{cc}'
                        self.file_log(f"Track {track_index}: Saved CC{cc} [{display_name}] = {value:.3f}")
                    except Exception as e:
                        self.file_log(f"Track {track_index}: Error saving CC{cc}: {e}")
            
            if values:
                self._saved_values[track_index] = values
                self.file_log(f"Track {track_index}: SAVED {len(values)} CC parameters total")
            else:
                self.file_log(f"Track {track_index}: No CC parameters to save")
                
        except Exception as e:
            self.file_log(f"_save_track_by_index error: {e}")
    
    def _execute_restore(self):
        """Execute restore - called by _tasks.add() deferred execution"""
        try:
            self.file_log("*** _execute_restore CALLED by _tasks ***")
            self.log_message("MIDIverge: _execute_restore called")
            self._restore_current_track()
        except Exception as e:
            self.file_log(f"*** _execute_restore exception: {e} ***")
            self.log_message(f"MIDIverge: _execute_restore exception: {e}")
    
    def _restore_current_track(self):
        """Restore ALL CC-mapped parameters for the current track using MFL paths"""
        self.file_log("*** _restore_current_track CALLED ***")
        self.file_log(f"*** _current_track_index = {self._current_track_index} ***")
        self.file_log(f"*** _saved_values keys = {list(self._saved_values.keys())} ***")
        try:
            all_tracks = list(self.song.tracks) + list(self.song.return_tracks) + [self.song.master_track]
            
            if not self._current_track:
                self.file_log("_restore_current_track: No current track")
                return
            
            try:
                track_index = all_tracks.index(self._current_track)
            except ValueError:
                self.file_log("_restore_current_track: Current track not in track list")
                return
            
            if track_index not in self._saved_values:
                self.file_log(f"Track {track_index}: No saved values to restore")
                return
            
            saved = self._saved_values[track_index]
            track = all_tracks[track_index]
            track_name = track.name if hasattr(track, 'name') else f'Track{track_index}'
            restored = 0
            
            # Restore ALL CC-mapped parameters using MFL paths
            for cc in self._target_ccs:
                key = f'cc_{cc}'
                if key not in saved:
                    continue
                
                # Build possible manual mapping keys to find MFL path
                clean_track_name = track_name
                if '-' in clean_track_name:
                    clean_track_name = clean_track_name.split('-', 1)[1]
                
                device_name = None
                if hasattr(track, 'devices') and len(track.devices) > 0:
                    device_name = track.devices[0].name if hasattr(track.devices[0], 'name') else None
                    if device_name:
                        device_name = device_name.replace(' ', '_')  # Match JSON key format
                
                # Try multiple key formats
                possible_keys = []
                if device_name:
                    possible_keys.append(f"track_{track_index+1}-{device_name}_cc_{cc}")
                
                # Also try with clean track name (without number prefix)
                clean_track_name = clean_track_name.replace(' ', '_')  # Match JSON key format
                possible_keys.append(f"track_{track_index+1}-{clean_track_name}_cc_{cc}")
                
                # Find the parameter using manual mapping
                param = None
                param_name = None
                
                for mapping_key in possible_keys:
                    if mapping_key in self._manual_mappings:
                        mapping = self._manual_mappings[mapping_key]
                        if 'mfl_path' in mapping:
                            mfl_path = mapping['mfl_path']
                            # Resolve MFL path to get parameter
                            param = self._resolve_mfl_path(mfl_path)
                            if param and hasattr(param, 'name'):
                                param_name = param.name
                            break
                
                # If we found the parameter, restore its value
                if param and hasattr(param, 'value'):
                    try:
                        if hasattr(param, 'min') and hasattr(param, 'max'):
                            old_val = param.value
                            new_val = max(param.min, min(param.max, saved[key]))
                            param.value = new_val
                            display_name = param_name if param_name else f'CC{cc}'
                            self.file_log(f"Track {track_index}: Restored CC{cc} [{display_name}]: {old_val:.3f} -> {new_val:.3f}")
                            restored += 1
                        else:
                            # No min/max, just set the value directly
                            old_val = param.value
                            param.value = saved[key]
                            display_name = param_name if param_name else f'CC{cc}'
                            self.file_log(f"Track {track_index}: Restored CC{cc} [{display_name}]: {old_val:.3f} -> {saved[key]:.3f}")
                            restored += 1
                    except Exception as e:
                        self.file_log(f"Track {track_index}: Error restoring CC{cc}: {e}")
            
            self.file_log(f"Track {track_index}: RESTORED {restored} CC parameters total")
            
        except Exception as e:
            self.file_log(f"_restore_current_track error: {e}")
    
    # ════════════════════════════════════════════════════════════════════════
    # UDP SENDER MODULE - Parameter Monitoring
    # ════════════════════════════════════════════════════════════════════════
    
    def _on_track_changed(self):
        """Handle track selection change - combines UDP sender and track memory"""
        self.file_log(">>> _on_track_changed ENTRY - NEW CODE RUNNING <<<")
        try:
            selected_track = self.song.view.selected_track
            all_tracks = self._get_all_tracks()
            
            try:
                new_track_index = all_tracks.index(selected_track)
            except (ValueError, AttributeError):
                new_track_index = 0
            
            # Get track name for UDP message
            track_name = selected_track.name if hasattr(selected_track, 'name') else 'Unknown'
            
            self.file_log(f"Track changed: {new_track_index} (prev: {self._previous_track_index})")
            
            # ──────────────────────────────────────────────────────────
            # TRACK MEMORY: Save previous track values
            # ──────────────────────────────────────────────────────────
            if self._previous_track_index is not None and self._previous_track_index != new_track_index:
                self.file_log(f"*** CALLING _save_track_by_index({self._previous_track_index}) ***")
                self._save_track_by_index(self._previous_track_index)
                self.file_log(f"*** RETURNED from _save_track_by_index ***")
                # Save observed ranges to disk when changing tracks
                self.save_manual_mappings()
            
            # Update current track
            self._current_track = selected_track
            self._current_track_index = new_track_index
            self._previous_track_index = new_track_index
            
            # ──────────────────────────────────────────────────────────
            # UDP: Send track changed message to overlay
            # ──────────────────────────────────────────────────────────
            self._send_udp_message({
                'type': 'track_changed',
                'track_name': track_name,
                'track_index': new_track_index
            })
            self.file_log(f"UDP sent track_changed: {track_name}")
            
            # ──────────────────────────────────────────────────────────
            # UDP SENDER: Setup parameter listeners and send initial values
            # ──────────────────────────────────────────────────────────
            self.file_log("About to setup UDP listeners and send params...")
            self._remove_parameter_listeners()
            self._setup_parameter_listeners()
            self._send_all_parameters()
            self.file_log("Finished UDP setup")
            
            # ──────────────────────────────────────────────────────────
            # TRACK MEMORY: Restore new track values (DEFERRED to avoid notification error)
            # ──────────────────────────────────────────────────────────
            # _tasks.add() callbacks never execute - use update_display() flag instead
            self.file_log(f"*** Setting _pending_restore_track = {new_track_index} ***")
            self._pending_restore_track = new_track_index
        
        except Exception as e:
            self.file_log(f"Error in _on_track_changed: {e}")
            self.log_message(f"Error in track change: {e}")
    
    def _setup_parameter_listeners(self):
        """Setup listeners for all mapped parameters on current track"""
        if not self._current_track:
            self.file_log("Setup listeners failed: no current track")
            return
        
        listener_count = 0
        for cc in self._target_ccs:
            param = self._find_parameter_for_cc(cc)
            if param:
                try:
                    # Create listener function and store it
                    listener_func = lambda p=param, c=cc: self._on_parameter_changed(c, p)
                    self._listener_functions[cc] = listener_func
                    
                    # Add listener
                    if not param.value_has_listener(listener_func):
                        param.add_value_listener(listener_func)
                    self._parameter_listeners.append((param, cc))
                    listener_count += 1
                    
                    # Debug logging for CC73
                    if cc == 73:
                        self.file_log(f"CC73 listener added for parameter: {param.name}")
                except Exception as e:
                    self.file_log(f"Failed to add listener for CC{cc}: {e}")
        
        self.file_log(f"Setup {listener_count} parameter listeners")
    
    def _remove_parameter_listeners(self):
        """Remove all parameter listeners"""
        for param, cc in self._parameter_listeners:
            try:
                listener_func = self._listener_functions.get(cc)
                if listener_func and param.value_has_listener(listener_func):
                    param.remove_value_listener(listener_func)
            except Exception:
                pass
        self._parameter_listeners = []
        self._listener_functions = {}
    

    
    def _on_parameter_changed(self, cc, param):
        """Called when a parameter value changes - with duplicate suppression"""
        try:
            value = param.value
            value_str = str(param)
            name = param.name
            
            # Only send if value actually changed
            last_sent = self._last_sent_values.get(cc)
            if last_sent and last_sent[0] == value and last_sent[1] == value_str:
                return  # Value unchanged, don't flood UDP
            
            # Cache this value
            self._last_sent_values[cc] = (value, value_str)
            
            # Get parameter range
            param_min = param.min
            param_max = param.max
            
            # Build track-specific key for observed ranges
            range_key = None
            if self._current_track:
                track_name = self._current_track.name.replace(' ', '_')
                range_key = f"track_{track_name}_cc_{cc}"
            
            # Track observed min/max for NEW parameters only (don't expand manually-set ranges)
            # Only create new observed ranges if they don't exist in manual_mappings
            if range_key and range_key not in self._manual_mappings:
                if range_key not in self._observed_ranges:
                    self._observed_ranges[range_key] = {'min': value, 'max': value}
                else:
                    # Expand observed range only if not manually configured
                    if value < self._observed_ranges[range_key]['min']:
                        self._observed_ranges[range_key]['min'] = value
                    if value > self._observed_ranges[range_key]['max']:
                        self._observed_ranges[range_key]['max'] = value
            
            # For Chain Selectors, use observed range instead of API-reported range
            # (API reports min=0, max=1 but zones can be configured as 1-10, etc.)
            if 'Chain Selector' in name or name == 'Chain':
                if range_key and range_key in self._observed_ranges:
                    # Always use observed range for Chain Selectors (API range is unreliable)
                    param_min = self._observed_ranges[range_key]['min']
                    param_max = self._observed_ranges[range_key]['max']
                    # Don't log every single change - too noisy
            
            # NOTE: We do NOT save observed ranges to manual_mappings.json
            # Observed ranges are tracked in memory only to handle Chain Selector zone configs
            # manual_mappings.json should only contain user-defined mappings
            
            # Log for debugging CC73 issue
            if cc == 73:
                self.file_log(f"CC73 parameter changed: {name} = {value} ({value_str})")
            
            self._send_udp_message({
                'type': 'cc_update',
                'cc': cc,
                'param_name': name,
                'param_value': value,
                'param_str': value_str,
                'param_min': param_min,
                'param_max': param_max,
                'device_name': ''
            })
        except Exception as e:
            self.file_log(f"_on_parameter_changed CC{cc} error: {e}")  # Log errors instead of silent fail
    
    def _send_all_parameters(self):
        """Send current values of all mapped parameters"""
        sent_count = 0
        for cc in self._target_ccs:
            param = self._find_parameter_for_cc(cc)
            if param:
                try:
                    # Get parameter range
                    param_min = param.min
                    param_max = param.max
                    
                    # Build track-specific key for observed ranges
                    range_key = None
                    if self._current_track:
                        track_name = self._current_track.name.replace(' ', '_')
                        range_key = f"track_{track_name}_cc_{cc}"
                    
                    # For Chain Selectors, use observed range if available (persisted from previous sessions)
                    if 'Chain Selector' in param.name or param.name == 'Chain':
                        if range_key and range_key in self._observed_ranges:
                            # Always use observed range for Chain Selectors (API range is unreliable)
                            param_min = self._observed_ranges[range_key]['min']
                            param_max = self._observed_ranges[range_key]['max']
                            self.file_log(f"CC{cc} Chain Selector using saved observed range: {param_min} to {param_max}")
                        else:
                            self.file_log(f"CC{cc} Chain Selector: range_key='{range_key}', NOT in observed_ranges (using API: {param_min} to {param_max})")
                    
                    # Debug logging for CC73
                    if cc == 73:
                        self.file_log(f"Sending initial CC73: {param.name} = {param.value}")
                    
                    self._send_udp_message({
                        'type': 'cc_update',
                        'cc': cc,
                        'param_name': param.name,
                        'param_value': param.value,
                        'param_str': str(param),
                        'param_min': param_min,
                        'param_max': param_max,
                        'device_name': ''
                    })
                    sent_count += 1
                except Exception as e:
                    self.file_log(f"Error sending CC{cc}: {e}")
        
        self.file_log(f"Sent {sent_count} initial parameter values")
    
    def _save_discovered_mfl_path(self, cc, track_idx, mfl_path):
        """Save an MFL path that was discovered via fuzzy search or mixer fallback"""
        try:
            track_name = self._current_track.name if hasattr(self._current_track, 'name') else f'Track{track_idx}'
            clean_track_name = track_name
            if '-' in clean_track_name:
                clean_track_name = clean_track_name.split('-', 1)[1]
            clean_track_name = clean_track_name.replace(' ', '_')
            
            # Try with device name if available
            device_name = None
            if hasattr(self._current_track, 'devices') and len(self._current_track.devices) > 0:
                device_name = self._current_track.devices[0].name if hasattr(self._current_track.devices[0], 'name') else None
                if device_name:
                    device_name = device_name.replace(' ', '_')
            
            # Build key (prefer device name)
            if device_name:
                key = f"track_{track_idx+1}-{device_name}_cc_{cc}"
            else:
                key = f"track_{track_idx+1}-{clean_track_name}_cc_{cc}"
            
            # Save MFL path
            if key not in self._manual_mappings:
                self._manual_mappings[key] = {}
            self._manual_mappings[key]['mfl_path'] = mfl_path
            self.file_log(f"CC{cc} saved MFL path to '{key}': {mfl_path}")
            self.save_manual_mappings()
        except Exception as e:
            self.file_log(f"Failed to save discovered MFL path: {e}")
    
    def _find_parameter_for_cc(self, cc):
        """Find parameter object for a given CC - checks manual mappings first, then scanner"""
        if not self._current_track:
            return None
        
        track_name = self._current_track.name.replace(' ', '_')
        manual_key = f'track_{track_name}_cc_{cc}'
        
        # PRIORITY 0: Manual mapping
        if manual_key in self._manual_mappings:
            mfl_path = self._manual_mappings[manual_key].get('mfl_path')
            if mfl_path:
                try:
                    param = self._navigate_mfl_path(self._current_track, mfl_path)
                    if param:
                        if cc == 73:
                            self.file_log(f"CC73 found via manual mapping: {param.name}")
                        return param
                except Exception as e:
                    self.file_log(f"CC{cc} manual mapping failed: {e}")
        
        # PRIORITY 1: Scanner mapping
        for mapping in self._scanner_data:
            if mapping.get('cc') == cc and mapping.get('track_index') == self._current_track_index:
                if mapping.get('resolution_status') == 'success':
                    lom_path = mapping.get('lom_path', [])
                    try:
                        param = self._navigate_lom_path(self._current_track, lom_path)
                        if param:
                            return param
                    except Exception as e:
                        self.file_log(f"CC{cc} scanner mapping failed: {e}")
                
                # PRIORITY 2: Failed resolution but param_tag suggests mixer parameter
                if mapping.get('resolution_status') == 'failed':
                    param_tag = mapping.get('param_tag', '').lower()
                    try:
                        if hasattr(self._current_track, 'mixer_device'):
                            mixer = self._current_track.mixer_device
                            
                            # Check for volume
                            if 'volume' in param_tag and hasattr(mixer, 'volume'):
                                self.file_log(f"CC{cc} found via mixer fallback: Volume")
                                # Save MFL path
                                try:
                                    all_tracks = self._get_all_tracks()
                                    track_idx = all_tracks.index(self._current_track)
                                    mfl_path = f"live_set tracks {track_idx} mixer_device volume"
                                    self._save_discovered_mfl_path(cc, track_idx, mfl_path)
                                except Exception as e:
                                    self.file_log(f"CC{cc} failed to save mixer volume MFL path: {e}")
                                return mixer.volume
                            
                            # Check for panning
                            if 'pan' in param_tag and hasattr(mixer, 'panning'):
                                self.file_log(f"CC{cc} found via mixer fallback: Panning")
                                # Save MFL path
                                try:
                                    all_tracks = self._get_all_tracks()
                                    track_idx = all_tracks.index(self._current_track)
                                    mfl_path = f"live_set tracks {track_idx} mixer_device panning"
                                    self._save_discovered_mfl_path(cc, track_idx, mfl_path)
                                except Exception as e:
                                    self.file_log(f"CC{cc} failed to save mixer panning MFL path: {e}")
                                return mixer.panning
                            
                            # Check for sends
                            if param_tag.startswith('send') and hasattr(mixer, 'sends'):
                                # Extract send index from "SendA", "SendB", etc.
                                send_letter = param_tag.replace('send', '').strip()
                                if send_letter and send_letter[0] in 'abcdefgh':
                                    send_idx = ord(send_letter[0].lower()) - ord('a')
                                    if send_idx < len(mixer.sends):
                                        self.file_log(f"CC{cc} found via mixer fallback: Send {send_letter.upper()}")
                                        # Save MFL path
                                        try:
                                            all_tracks = self._get_all_tracks()
                                            track_idx = all_tracks.index(self._current_track)
                                            mfl_path = f"live_set tracks {track_idx} mixer_device sends {send_idx}"
                                            self._save_discovered_mfl_path(cc, track_idx, mfl_path)
                                        except Exception as e:
                                            self.file_log(f"CC{cc} failed to save mixer send MFL path: {e}")
                                        return mixer.sends[send_idx]
                    except Exception as e:
                        self.file_log(f"CC{cc} mixer fallback failed: {e}")
                
                # PRIORITY 3: Failed resolution - try fuzzy parameter name search
                if mapping.get('resolution_status') == 'failed':
                    param_tag = mapping.get('param_tag', '')
                    if param_tag and hasattr(self._current_track, 'devices'):
                        self.file_log(f"CC{cc} attempting fuzzy search for '{param_tag}'")
                        param_tag_norm = param_tag.replace(' ', '').replace('.', '').lower()
                        
                        # Search all devices for matching parameter name
                        for dev_idx, device in enumerate(self._current_track.devices):
                            if hasattr(device, 'parameters'):
                                for p_idx, param in enumerate(device.parameters):
                                    try:
                                        p_name_norm = param.name.replace(' ', '').replace('.', '').lower()
                                        if param_tag_norm in p_name_norm or p_name_norm in param_tag_norm:
                                            self.file_log(f"CC{cc} FUZZY MATCH: device[{dev_idx}].parameters[{p_idx}] = {param.name}")
                                            
                                            # Derive and save MFL path for future use
                                            try:
                                                all_tracks = self._get_all_tracks()
                                                track_idx = all_tracks.index(self._current_track)
                                                mfl_path = f"live_set tracks {track_idx} devices {dev_idx} parameters {p_idx}"
                                                self._save_discovered_mfl_path(cc, track_idx, mfl_path)
                                            except Exception as e:
                                                self.file_log(f"CC{cc} failed to save fuzzy match MFL path: {e}")
                                            
                                            return param
                                    except:
                                        pass
        
        return None
    
    def _navigate_mfl_path(self, track, mfl_path):
        """Navigate MFL path string like 'live_set tracks 3 devices 1 parameters 15'"""
        try:
            parts = mfl_path.split()
            obj = self.song
            
            i = 0
            while i < len(parts):
                part = parts[i]
                
                if part == 'live_set':
                    obj = self.song
                elif part == 'tracks':
                    i += 1
                    track_idx = int(parts[i])
                    all_tracks = self._get_all_tracks()
                    obj = all_tracks[track_idx]
                elif part == 'devices':
                    i += 1
                    dev_idx = int(parts[i])
                    obj = obj.devices[dev_idx]
                elif part == 'chains':
                    i += 1
                    chain_idx = int(parts[i])
                    obj = obj.chains[chain_idx]
                elif part == 'parameters':
                    i += 1
                    param_idx = int(parts[i])
                    return obj.parameters[param_idx]
                elif part == 'mixer_device':
                    obj = obj.mixer_device
                elif part == 'volume':
                    return obj.volume
                elif part == 'panning':
                    return obj.panning
                elif part == 'sends':
                    i += 1
                    send_idx = int(parts[i])
                    return obj.sends[send_idx]
                
                i += 1
            
            return obj
        except Exception as e:
            self.file_log(f"MFL navigation error: {e}")
            return None
    
    def _navigate_lom_path(self, track, lom_path):
        """Navigate LOM path list like ['devices', '1', 'parameters', '15']"""
        try:
            obj = track
            i = 0
            
            while i < len(lom_path):
                part = lom_path[i]
                
                if part == 'devices':
                    i += 1
                    dev_idx = int(lom_path[i])
                    obj = obj.devices[dev_idx]
                elif part == 'parameters':
                    i += 1
                    param_idx = int(lom_path[i])
                    return obj.parameters[param_idx]
                elif part == 'chains':
                    i += 1
                    chain_idx = int(lom_path[i])
                    obj = obj.chains[chain_idx]
                
                i += 1
            
            return obj
        except Exception as e:
            self.file_log(f"LOM navigation error: {e}")
            return None
    
    def _send_udp_message(self, data):
        """Send UDP message to overlay"""
        if not self._sock:
            return
        
        try:
            message = json.dumps(data).encode('utf-8')
            self._sock.sendto(message, self._overlay_address)
            # Log non-parameter messages only (to avoid disk I/O flood)
            if data.get('type') not in ['cc_update', 'parameter_changed']:
                self.file_log(f"UDP sent: {data.get('type')}")
        except Exception as e:
            pass  # Silent fail in hot path
    
    # ════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ════════════════════════════════════════════════════════════════════════
    
    def _get_all_tracks(self):
        """Get all tracks including returns and master"""
        return (list(self.song.tracks) + 
                list(self.song.return_tracks) + 
                [self.song.master_track])
