"""
MIDIOverlay Remote Script for Ableton Live
Sends actual parameter values to the MIDI Overlay application via UDP
"""
import Live
import socket
import json
import os
import time

class MIDIOverlay:
    """Remote Script to sync Ableton parameter values with overlay"""
    
    def __init__(self, c_instance):
        self.c_instance = c_instance
        self.song = c_instance.song()
        
        # File logging to diagnose issues
        self.log_file = r"C:\Users\zackn\Documents\midi overlay\midioverlay_debug.log"
        self.file_log("=" * 60)
        self.file_log(f"MIDIOverlay __init__ started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # UDP socket for sending data to overlay
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.overlay_address = ('127.0.0.1', 9001)  # localhost:9001
        
        # Track state
        self.current_track = None
        self.current_track_index = -1
        self.parameter_listeners = []
        
        # CC mappings we care about (71-78 for encoders)
        self.target_ccs = list(range(71, 79))
        
        # Scanner JSON data - just the raw mappings, we'll traverse to find parameters
        self.scanner_data = {}
        self.scanner_file = r"C:\Users\zackn\Documents\midi overlay\current_scan.json"
        self.scanner_mtime = 0  # Track last modification time for auto-reload
        self.load_scanner_json()
        
        # Listen to track selection (Live 12 API: use song.view)
        self.song.view.add_selected_track_listener(self.on_track_changed)
        
        # Initial track setup - call immediately
        self.file_log("Calling initial on_track_changed()...")
        self.on_track_changed()
        
        msg = "MIDIOverlay Remote Script loaded!"
        self.log(msg)
        self.file_log(msg)
        self.send_message({
            'type': 'status',
            'message': 'MIDIOverlay Remote Script connected'
        })
        self.file_log("__init__ completed successfully")
    
    def disconnect(self):
        """Cleanup when script is unloaded"""
        self.log("MIDIOverlay Remote Script disconnecting...")
        self.remove_parameter_listeners()
        if self.song.view.selected_track_has_listener(self.on_track_changed):
            self.song.view.remove_selected_track_listener(self.on_track_changed)
        self.sock.close()
    
    def can_lock_to_devices(self):
        """Required by Ableton - return False since we don't lock to devices"""
        return False
    
    def suggest_input_port(self):
        """Required by Ableton - return empty string"""
        return ''
    
    def suggest_output_port(self):
        """Required by Ableton - return empty string"""
        return ''
    
    def refresh_state(self):
        """Required by Ableton - called when controls need refresh"""
        pass
    
    def log(self, message):
        """Log to Live's Log.txt"""
        self.c_instance.log_message(f"[MIDIOverlay] {message}")
    
    def file_log(self, message):
        """Log to file for debugging (independent of Ableton's log)"""
        try:
            with open(self.log_file, 'a') as f:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
        except Exception as e:
            pass  # Silent fail - don't crash if logging fails
    
    def load_scanner_json(self):
        """Load scanner JSON - we only need the raw mappings, not LOM path resolution"""
        self.file_log("load_scanner_json() called")
        try:
            if not os.path.exists(self.scanner_file):
                msg = f"WARNING: Scanner JSON not found at {self.scanner_file}"
                self.log(msg)
                self.file_log(msg)
                return
            
            # Update modification time
            self.scanner_mtime = os.path.getmtime(self.scanner_file)
            self.file_log(f"Found scanner file: {self.scanner_file}")
            
            # Load and parse JSON
            with open(self.scanner_file, 'r') as f:
                self.scanner_data = json.load(f)
            
            # Count CC 71-78 mappings
            cc_count = 0
            if 'mappings' in self.scanner_data:
                for mapping in self.scanner_data['mappings']:
                    cc = mapping.get('cc', -1)
                    if 71 <= cc <= 78:
                        cc_count += 1
            
            msg = f"Loaded scanner JSON: {cc_count} CC71-78 mappings found (will use recursive traversal to resolve)"
            self.log(msg)
            self.file_log(msg)
            
        except Exception as e:
            msg = f"Error loading scanner JSON: {e}"
            self.log(msg)
            self.file_log(msg)
    
    def send_message(self, data):
        """Send JSON message to overlay via UDP"""
        try:
            message = json.dumps(data).encode('utf-8')
            self.sock.sendto(message, self.overlay_address)
            # Log parameter_changed messages with CC info
            if data.get('type') == 'parameter_changed':
                cc = data.get('cc', 'NONE')
                param_name = data.get('param_name', 'Unknown')
                self.file_log(f"SENT: CC={cc}, param={param_name}")
        except Exception as e:
            msg = f"Error sending message: {e}"
            self.log(msg)
            self.file_log(msg)
    
    def on_track_changed(self):
        """Called when user selects a different track"""
        self.remove_parameter_listeners()
        
        track = self.song.view.selected_track
        self.current_track = track
        
        # Get track info
        track_name = track.name if hasattr(track, 'name') else 'Unknown'
        
        # Get track index (important for scanner lookup)
        try:
            self.current_track_index = list(self.song.tracks).index(track) if track in self.song.tracks else -1
        except:
            self.current_track_index = -1
        
        log_msg = f"Track changed: {track_name} (index {self.current_track_index})"
        self.log(log_msg)
        self.file_log(log_msg)
        
        # Send track change notification
        self.send_message({
            'type': 'track_changed',
            'track_name': track_name,
            'track_index': self.current_track_index
        })
        
        # Setup parameter listeners for this track
        self.setup_parameter_listeners(track)
        
        # Send initial parameter values
        self.file_log("Calling send_all_parameters()...")
        self.send_all_parameters()
        self.file_log("send_all_parameters() completed")
    
    def _find_parameter_recursive(self, track_or_device, mapping_info):
        """Recursively traverse track/device to find parameter matching scanner mapping.
        Priority:
        1. Manual mappings (user overrides)
        2. Scanner data with device/param indices
        3. LOM path fallback for failed resolutions
        4. Name-based search (last resort)
        """
        # PRIORITY 1: Check for manual mapping override
        cc = mapping_info.get('cc')
        if cc and self.manual_mappings:
            try:
                track_name = self.current_track.name if self.current_track and hasattr(self.current_track, 'name') else ''
                if track_name:
                    manual_key = f"track_{track_name.replace(' ', '_')}_cc_{cc}"
                    if manual_key in self.manual_mappings:
                        manual_cfg = self.manual_mappings[manual_key]
                        nav_path = manual_cfg.get('nav_path', [])
                        if nav_path:
                            self.file_log(f"[MANUAL] Found manual mapping for CC{cc}, nav_path={nav_path}")
                            # Navigate the path
                            obj = track_or_device
                            for step in nav_path:
                                step_type = step.get('type')
                                if step_type == 'devices':
                                    idx = step.get('index')
                                    if hasattr(obj, 'devices') and idx < len(obj.devices):
                                        obj = obj.devices[idx]
                                        self.file_log(f"[MANUAL] Navigated to devices[{idx}]")
                                    else:
                                        self.file_log(f"[MANUAL] Failed at devices[{idx}]")
                                        obj = None
                                        break
                                
                                elif step_type == 'chains':
                                    idx = step.get('index')
                                    if hasattr(obj, 'chains') and idx < len(obj.chains):
                                        obj = obj.chains[idx]
                                        self.file_log(f"[MANUAL] Navigated to chains[{idx}]")
                                    else:
                                        self.file_log(f"[MANUAL] Failed at chains[{idx}]")
                                        obj = None
                                        break
                                
                                elif step_type == 'mixer_device':
                                    if hasattr(obj, 'mixer_device'):
                                        obj = obj.mixer_device
                                        self.file_log(f"[MANUAL] Navigated to mixer_device")
                                    else:
                                        self.file_log(f"[MANUAL] No mixer_device found")
                                        obj = None
                                        break
                                
                                elif step_type == 'property':
                                    prop_name = step.get('name')
                                    if hasattr(obj, prop_name):
                                        param = getattr(obj, prop_name)
                                        self.file_log(f"[MANUAL] MATCH! Found property '{prop_name}'")
                                        return param
                                    else:
                                        self.file_log(f"[MANUAL] Property '{prop_name}' not found")
                                        obj = None
                                        break
                            
                            if obj is None:
                                self.file_log(f"[MANUAL] Navigation failed")
                        
            except Exception as e:
                self.file_log(f"[MANUAL] Manual mapping navigation failed: {e}")
        
        # PRIORITY 2: Use scanner data
        device_index = mapping_info.get('device_index', -1)
        param_index = mapping_info.get('param_index', -1)
        lom_path = mapping_info.get('lom_path', [])
        
        # Handle chain mixer specially (device_index == -3)
        if device_index == -3:
            self.file_log(f"[FIND] Using chain mixer (device_index=-3), lom_path={lom_path}")
            try:
                # Navigate lom_path to find chain mixer_device
                obj = track_or_device
                for part in lom_path:
                    if part.startswith('devices['):
                        idx = int(part.split('[')[1].split(']')[0])
                        if hasattr(obj, 'devices') and idx < len(obj.devices):
                            obj = obj.devices[idx]
                        else:
                            self.file_log(f"[FIND] Failed to navigate {part}")
                            return None
                    elif part.startswith('chains['):
                        idx = int(part.split('[')[1].split(']')[0])
                        if hasattr(obj, 'chains') and idx < len(obj.chains):
                            obj = obj.chains[idx]
                        else:
                            self.file_log(f"[FIND] Failed to navigate {part}")
                            return None
                    elif part.startswith('param <'):
                        # Found the parameter - get it from chain's mixer_device
                        if hasattr(obj, 'mixer_device'):
                            mixer = obj.mixer_device
                            param_tag = part[7:-1]  # Extract tag from 'param <Volume>'
                            if param_tag == 'Volume' and hasattr(mixer, 'volume'):
                                self.file_log(f"[FIND] CHAIN MIXER MATCH! Found chain volume")
                                return mixer.volume
                            elif param_tag == 'Panning' and hasattr(mixer, 'panning'):
                                self.file_log(f"[FIND] CHAIN MIXER MATCH! Found chain panning")
                                return mixer.panning
                        self.file_log(f"[FIND] Chain mixer parameter {part} not found")
                        return None
                
            except Exception as e:
                self.file_log(f"[FIND] Chain mixer lookup failed: {e}")
                return None
        
        # Handle track mixer specially (device_index == -2)
        if device_index == -2 and param_index >= 0:
            self.file_log(f"[FIND] Using track mixer (device_index=-2): param[{param_index}]")
            try:
                if hasattr(track_or_device, 'mixer_device'):
                    mixer = track_or_device.mixer_device
                    # Map param_index to mixer properties
                    if param_index == 0 and hasattr(mixer, 'volume'):
                        param = mixer.volume
                        self.file_log(f"[FIND] MIXER MATCH! Found '{param.name}' (Volume)")
                        return param
                    elif param_index == 1 and hasattr(mixer, 'panning'):
                        param = mixer.panning
                        self.file_log(f"[FIND] MIXER MATCH! Found '{param.name}' (Panning)")
                        return param
                    elif param_index >= 2 and hasattr(mixer, 'sends'):
                        send_idx = param_index - 2
                        if send_idx < len(mixer.sends):
                            param = mixer.sends[send_idx]
                            self.file_log(f"[FIND] MIXER MATCH! Found Send {send_idx}")
                            return param
                    else:
                        self.file_log(f"[FIND] mixer param_index {param_index} not found")
                else:
                    self.file_log(f"[FIND] track has no mixer_device")
            except Exception as e:
                self.file_log(f"[FIND] Mixer lookup failed: {e}")
            return None
        
        # Handle failed resolution with lom_path fallback (device_index == -1)
        if device_index == -1 and len(lom_path) > 0:
            self.file_log(f"[FIND] Scanner failed but we have lom_path={lom_path}, attempting navigation")
            try:
                obj = track_or_device
                # Navigate through devices/chains
                for part in lom_path:
                    if part.startswith('devices['):
                        idx = int(part.split('[')[1].split(']')[0])
                        if hasattr(obj, 'devices') and idx < len(obj.devices):
                            obj = obj.devices[idx]
                            self.file_log(f"[FIND] Navigated to device[{idx}]")
                        else:
                            self.file_log(f"[FIND] Failed to navigate {part}")
                            return None
                    elif part.startswith('chains['):
                        idx = int(part.split('[')[1].split(']')[0])
                        if hasattr(obj, 'chains') and idx < len(obj.chains):
                            obj = obj.chains[idx]
                            self.file_log(f"[FIND] Navigated to chain[{idx}]")
                        else:
                            self.file_log(f"[FIND] Failed to navigate {part}")
                            return None
                    elif part.startswith('param <'):
                        # Try to find parameter by name on current object
                        param_name = part[7:-1]  # Extract from 'param <Makeup>'
                        self.file_log(f"[FIND] Looking for parameter '{param_name}'")
                        
                        # Normalize for comparison (remove spaces, lowercase)
                        param_name_normalized = param_name.replace(' ', '').lower()
                        
                        if hasattr(obj, 'parameters'):
                            # Search by original_name first, then by name (fuzzy match)
                            for p in obj.parameters:
                                try:
                                    if hasattr(p, 'original_name'):
                                        p_orig_norm = p.original_name.replace(' ', '').lower()
                                        if p_orig_norm == param_name_normalized:
                                            self.file_log(f"[FIND] LOM PATH MATCH! Found '{p.name}' by original_name='{p.original_name}'")
                                            return p
                                    if hasattr(p, 'name'):
                                        p_name_norm = p.name.replace(' ', '').lower()
                                        if p_name_norm == param_name_normalized:
                                            self.file_log(f"[FIND] LOM PATH MATCH! Found '{p.name}' by name")
                                            return p
                                except:
                                    pass
                            
                            # Not found - log available parameters
                            self.file_log(f"[FIND] Parameter '{param_name}' not found. Available:")
                            for i, p in enumerate(obj.parameters):
                                try:
                                    self.file_log(f"[FIND]   [{i}] {p.name} (orig: {p.original_name if hasattr(p, 'original_name') else '?'})")
                                except:
                                    pass
                        
                        return None
            except Exception as e:
                self.file_log(f"[FIND] LOM path navigation failed: {e}")
                return None
        
        # Handle normal devices (device_index >= 0)
        if device_index >= 0 and param_index >= 0:
            # Use direct indices - no name matching needed!
            self.file_log(f"[FIND] Using direct indices: device[{device_index}], param[{param_index}]")
            try:
                if hasattr(track_or_device, 'devices') and device_index < len(track_or_device.devices):
                    device = track_or_device.devices[device_index]
                    if hasattr(device, 'parameters') and param_index < len(device.parameters):
                        param = device.parameters[param_index]
                        param_name = param.name if hasattr(param, 'name') else '?'
                        self.file_log(f"[FIND] INDEX MATCH! Found '{param_name}' at device[{device_index}].parameters[{param_index}]")
                        return param
                    else:
                        self.file_log(f"[FIND] param_index {param_index} out of range")
                else:
                    self.file_log(f"[FIND] device_index {device_index} out of range")
            except Exception as e:
                self.file_log(f"[FIND] Index lookup failed: {e}")
        
        # FALLBACK: Name-based search (old method, less reliable)
        param_tag = mapping_info.get('param_tag', '')
        is_mixer_param = mapping_info.get('is_mixer_param', False)
        device_path = mapping_info.get('device_path', [])
        
        self.file_log(f"[FIND] Fallback to name search: param_tag='{param_tag}', is_mixer={is_mixer_param}, device_path={device_path}")
        
        try:
            # Mixer parameters (Volume, Pan, Sends)
            if is_mixer_param:
                if hasattr(track_or_device, 'mixer_device'):
                    mixer = track_or_device.mixer_device
                    
                    if param_tag == 'Volume' and hasattr(mixer, 'volume'):
                        self.file_log(f"[FIND] MATCH! Found mixer Volume")
                        return mixer.volume
                    elif param_tag == 'Pan' and hasattr(mixer, 'panning'):
                        self.file_log(f"[FIND] MATCH! Found mixer Pan")
                        return mixer.panning
                    elif param_tag.startswith('Send') and hasattr(mixer, 'sends'):
                        # Extract send index from param_tag like "Send0", "Send1"
                        try:
                            send_idx = int(param_tag.replace('Send', ''))
                            if send_idx < len(mixer.sends):
                                self.file_log(f"[FIND] MATCH! Found mixer Send {send_idx}")
                                return mixer.sends[send_idx]
                        except:
                            pass
            
            # Device parameters - need to search devices
            if hasattr(track_or_device, 'devices'):
                # LOG EVERYTHING: Enumerate ALL devices and parameters (including chains)
                self.file_log(f"[ENUMERATE] Track has {len(track_or_device.devices)} devices:")
                for dev_idx, device in enumerate(track_or_device.devices):
                    if device and hasattr(device, 'name'):
                        self.file_log(f"[ENUMERATE]   Device[{dev_idx}]: '{device.name}' (class: {device.class_name if hasattr(device, 'class_name') else 'unknown'})")
                        if hasattr(device, 'parameters'):
                            self.file_log(f"[ENUMERATE]     Has {len(device.parameters)} parameters:")
                            for param_idx, param in enumerate(device.parameters):
                                if param:
                                    param_name = param.name if hasattr(param, 'name') else '?'
                                    param_orig = param.original_name if hasattr(param, 'original_name') else '?'
                                    self.file_log(f"[ENUMERATE]       [{param_idx}] name='{param_name}' original_name='{param_orig}'")
                        
                        # If this is a rack with chains, enumerate chain devices too
                        if hasattr(device, 'chains'):
                            self.file_log(f"[ENUMERATE]     Has {len(device.chains)} chains:")
                            for chain_idx, chain in enumerate(device.chains):
                                if chain and hasattr(chain, 'name'):
                                    chain_name = chain.name if hasattr(chain, 'name') else '?'
                                    self.file_log(f"[ENUMERATE]       Chain[{chain_idx}]: '{chain_name}'")
                                    if hasattr(chain, 'devices'):
                                        for chain_dev_idx, chain_device in enumerate(chain.devices):
                                            if chain_device and hasattr(chain_device, 'name'):
                                                self.file_log(f"[ENUMERATE]         Device[{chain_dev_idx}]: '{chain_device.name}' (class: {chain_device.class_name if hasattr(chain_device, 'class_name') else 'unknown'})")
                                                if hasattr(chain_device, 'parameters'):
                                                    self.file_log(f"[ENUMERATE]           Has {len(chain_device.parameters)} parameters:")
                                                    for param_idx, param in enumerate(chain_device.parameters):
                                                        if param:
                                                            param_name = param.name if hasattr(param, 'name') else '?'
                                                            param_orig = param.original_name if hasattr(param, 'original_name') else '?'
                                                            self.file_log(f"[ENUMERATE]             [{param_idx}] name='{param_name}' original_name='{param_orig}'")
                
                devices_to_search = []
                
                if device_path:
                    # Navigate to specific device using device_path
                    current = track_or_device
                    for step in device_path:
                        if step.startswith('devices['):
                            dev_idx = int(step.split('[')[1].split(']')[0])
                            if hasattr(current, 'devices') and dev_idx < len(current.devices):
                                current = current.devices[dev_idx]
                                self.file_log(f"[FIND] Navigated to devices[{dev_idx}]")
                            else:
                                self.file_log(f"[FIND] Failed to navigate {step}")
                                return None
                        elif step.startswith('chains['):
                            chain_idx = int(step.split('[')[1].split(']')[0])
                            if hasattr(current, 'chains') and chain_idx < len(current.chains):
                                current = current.chains[chain_idx]
                                self.file_log(f"[FIND] Navigated to chains[{chain_idx}]")
                            else:
                                self.file_log(f"[FIND] Failed to navigate {step}")
                                return None
                    devices_to_search = [current]
                else:
                    # No device_path - search ALL devices on track
                    devices_to_search = list(track_or_device.devices)
                    self.file_log(f"[FIND] Searching ALL {len(devices_to_search)} devices on track")
                
                # Search each device for matching parameter
                for device in devices_to_search:
                    if not device or not hasattr(device, 'parameters'):
                        continue
                    
                    # Special case for rack macros: MacroControls.N means parameter at index N+1
                    # (MacroControls.0 = Macro 1, MacroControls.3 = Macro 4, etc.)
                    if param_tag.startswith('MacroControls.'):
                        try:
                            macro_idx = int(param_tag.split('.')[1])
                            # Parameter index = macro_idx + 1 (Device On is at 0)
                            param_idx = macro_idx + 1
                            if param_idx < len(device.parameters):
                                param = device.parameters[param_idx]
                                if param and hasattr(param, 'original_name'):
                                    expected_macro = f"Macro {macro_idx + 1}"
                                    if param.original_name == expected_macro:
                                        self.file_log(f"[FIND] MACRO MATCH! Found '{param.name}' (index {param_idx}) at device '{device.name}'")
                                        return param
                                    else:
                                        self.file_log(f"[FIND] MACRO INDEX {param_idx} but original_name is '{param.original_name}', expected '{expected_macro}'")
                        except Exception as e:
                            self.file_log(f"[FIND] Macro lookup error: {e}")
                    
                    # Regular parameter search
                    self.file_log(f"[FIND] Searching device '{device.name}' with {len(device.parameters)} parameters")
                    
                    for param in device.parameters:
                        if not param:
                            continue
                        
                        # Try exact match on original_name
                        if hasattr(param, 'original_name') and param.original_name == param_tag:
                            param_name = param.name if hasattr(param, 'name') else param.original_name
                            self.file_log(f"[FIND] EXACT MATCH! Found '{param_name}' at device '{device.name}'")
                            return param
                        
                        # Try partial match on name
                        if hasattr(param, 'name'):
                            param_name_norm = param.name.lower().replace(' ', '').replace('-', '')
                            param_tag_norm = param_tag.lower().replace(' ', '').replace('-', '')
                            
                            if param_tag_norm in param_name_norm or param_name_norm in param_tag_norm:
                                self.file_log(f"[FIND] PARTIAL MATCH! Found '{param.name}' at device '{device.name}'")
                                return param
                    
                self.file_log(f"[FIND] No match found in {len(devices_to_search)} devices")
            
            return None
            
        except Exception as e:
            self.file_log(f"[FIND] Error: {e}")
            return None
    
    def setup_parameter_listeners(self, track):
        """Setup listeners using RECURSIVE TRAVERSAL to find all mapped parameters"""
        if not track:
            self.file_log("setup_parameter_listeners: track is None!")
            return
        
        track_idx = self.current_track_index
        if track_idx < 0:
            self.file_log("setup_parameter_listeners: invalid track index")
            return
        
        self.file_log(f"setup_parameter_listeners for track {track_idx} using recursive traversal")
        
        # Get scanner mappings for this track (CC71-78 only)
        track_cc_mappings = {}  # {cc: mapping_info}
        for mapping in self.scanner_data.get('mappings', []):
            if mapping.get('track_index') == track_idx:
                cc = mapping.get('cc')
                if cc and 71 <= cc <= 78:
                    track_cc_mappings[cc] = mapping
        
        if not track_cc_mappings:
            self.file_log(f"No CC71-78 mappings found in scanner for track {track_idx}")
            return
        
        self.file_log(f"Found {len(track_cc_mappings)} CC mappings to resolve: {list(track_cc_mappings.keys())}")
        
        # Recursively traverse ALL parameters and match against scanner data
        matched_count = 0
        for cc, mapping_info in track_cc_mappings.items():
            param = self._find_parameter_recursive(track, mapping_info)
            if param:
                # Add listener
                if hasattr(param, 'add_value_listener'):
                    listener = lambda p=param, c=cc, m=mapping_info: self.on_parameter_changed_with_cc(p, c, m, '')
                    param.add_value_listener(listener)
                    self.parameter_listeners.append((param, listener))
                    
                    param_name = param.name if hasattr(param, 'name') else 'Unknown'
                    self.file_log(f"[LISTENER] CC{cc} -> {param_name}")
                    matched_count += 1
            else:
                self.file_log(f"[WARNING] Could not find parameter for CC{cc}: {mapping_info.get('param_tag', 'Unknown')}")
        
        self.file_log(f"Added {matched_count}/{len(track_cc_mappings)} parameter listeners for track {track_idx}")
    

    def on_parameter_changed_with_cc(self, param, cc, mapping_info, lom_path_str):
        """Called when a CC-mapped parameter changes - CC number already known"""
        if not param:
            return
        
        try:
            # Get parameter value
            param_value = param.value if hasattr(param, 'value') else 0
            param_str_value = str(param) if hasattr(param, '__str__') else str(param_value)
            
            # Get parameter min/max for normalization
            param_min = param.min if hasattr(param, 'min') else 0.0
            param_max = param.max if hasattr(param, 'max') else 1.0
            
            # Calculate normalized value
            if param_max > param_min:
                normalized_value = (param_value - param_min) / (param_max - param_min)
            else:
                normalized_value = 0.0
            
            # Log and send - USE ACTUAL PARAMETER NAME FROM LIVE, NOT SCANNER TAG
            param_name = param.name if hasattr(param, 'name') else mapping_info.get('param_tag', 'Unknown')
            param_original_name = param.original_name if hasattr(param, 'original_name') else ''
            device_name = mapping_info.get('device_name', '')
            log_msg = f"[CC{cc}] {param_name}: {param_str_value}"
            self.log(log_msg)
            self.file_log(log_msg)
            
            # Send parameter update with CC number
            self.send_message({
                'type': 'parameter_changed',
                'cc': cc,
                'param_name': param_name,
                'param_original_name': param_original_name,
                'param_value': normalized_value,
                'param_value_raw': param_value,
                'param_min': param_min,
                'param_max': param_max,
                'param_str': param_str_value,
                'device_name': device_name,
                'lom_path': lom_path_str,
                'midi_min': mapping_info.get('midi_min'),
                'midi_max': mapping_info.get('midi_max')
            })
            
        except Exception as e:
            self.file_log(f"Error in on_parameter_changed_with_cc: {e}")
    
    def remove_parameter_listeners(self):
        """Remove all parameter listeners"""
        for param, listener in self.parameter_listeners:
            if param and hasattr(param, 'remove_value_listener'):
                if param.value_has_listener(listener):
                    param.remove_value_listener(listener)
        self.parameter_listeners = []
    

    def send_all_parameters(self):
        """Send current values of all CC 71-78 parameters on the current track using recursive traversal"""
        if not self.current_track or self.current_track_index < 0:
            self.file_log(f"send_all_parameters: SKIP - current_track={self.current_track}, index={self.current_track_index}")
            return
        
        try:
            # Get scanner mappings for this track (CC71-78 only)
            track_cc_mappings = {}
            for mapping in self.scanner_data.get('mappings', []):
                if mapping.get('track_index') == self.current_track_index:
                    cc = mapping.get('cc')
                    if cc and 71 <= cc <= 78:
                        track_cc_mappings[cc] = mapping
            
            self.file_log(f"send_all_parameters: Found {len(track_cc_mappings)} mappings for track {self.current_track_index}")
            
            # Find and send each parameter
            for cc, mapping_info in track_cc_mappings.items():
                self.file_log(f"send_all_parameters: Processing CC{cc}...")
                param = self._find_parameter_recursive(self.current_track, mapping_info)
                if not param:
                    self.file_log(f"send_all_parameters: CC{cc} - parameter NOT found")
                    continue
                
                # Get parameter value
                param_value = param.value if hasattr(param, 'value') else 0
                param_str = str(param) if hasattr(param, '__str__') else str(param_value)
                param_min = param.min if hasattr(param, 'min') else 0.0
                param_max = param.max if hasattr(param, 'max') else 1.0
                param_name = param.name if hasattr(param, 'name') else mapping_info.get('param_tag', 'Unknown')
                param_original_name = param.original_name if hasattr(param, 'original_name') else ''
                
                if param_max > param_min:
                    normalized_value = (param_value - param_min) / (param_max - param_min)
                else:
                    normalized_value = 0.0
                
                self.file_log(f"send_all_parameters: CC{cc} - sending {param_name}={param_str}")
                
                # Send parameter with CC number
                self.send_message({
                    'type': 'parameter_changed',
                    'cc': cc,
                    'param_name': param_name,
                    'param_original_name': param_original_name,
                    'param_value': normalized_value,
                    'param_value_raw': param_value,
                    'param_min': param_min,
                    'param_max': param_max,
                    'param_str': param_str,
                    'device_name': mapping_info.get('device_name', ''),
                    'lom_path': '',
                    'midi_min': mapping_info.get('midi_min'),
                    'midi_max': mapping_info.get('midi_max')
                })
            
        except Exception as e:
            self.log(f"Error sending all parameters: {e}")
            self.file_log(f"ERROR in send_all_parameters: {e}")
    
    def _resolve_lom_path(self, lom_path_str):
        """Navigate a LOM path string to find the parameter object"""
        if not lom_path_str or not self.current_track:
            return None
        
        try:
            path_components = lom_path_str.split('|')
            current_obj = self.current_track
            
            for component in path_components:
                component = component.strip()
                
                if component == 'mixer_device':
                    # Track-level mixer device
                    if hasattr(current_obj, 'mixer_device'):
                        current_obj = current_obj.mixer_device
                        self.file_log(f"[RESOLVE] Navigated to mixer_device")
                    else:
                        self.file_log(f"[RESOLVE] FAILED: No mixer_device on object")
                        return None
                
                elif component.startswith('devices['):
                    # Extract device index
                    idx = int(component.split('[')[1].split(']')[0])
                    if hasattr(current_obj, 'devices') and idx < len(current_obj.devices):
                        current_obj = current_obj.devices[idx]
                    else:
                        return None
                
                elif component.startswith('chains['):
                    # Extract chain index
                    idx = int(component.split('[')[1].split(']')[0])
                    if hasattr(current_obj, 'chains') and idx < len(current_obj.chains):
                        current_obj = current_obj.chains[idx]
                    else:
                        return None
                
                elif component.startswith('param_index['):
                    # NEW: Direct parameter index lookup (most reliable!)
                    # Format: param_index[15]
                    idx = int(component.split('[')[1].split(']')[0])
                    if hasattr(current_obj, 'parameters') and idx < len(current_obj.parameters):
                        param = current_obj.parameters[idx]
                        self.file_log(f"[RESOLVE] Direct index lookup: parameters[{idx}] = '{param.name if hasattr(param, 'name') else 'Unknown'}'")
                        return param
                    else:
                        self.file_log(f"[RESOLVE] FAILED: param_index[{idx}] out of bounds or no parameters")
                        return None
                
                elif component.startswith('param <'):
                    # OLD: Parameter name lookup (fallback for old scanner JSONs)
                    # Extract parameter name
                    param_name = component.split('<')[1].split('>')[0]
                    
                    # Normalize parameter name for matching (remove special chars)
                    def normalize_name(name):
                        import re
                        return re.sub(r'[^a-zA-Z0-9]', '', name).lower()
                    
                    param_name_normalized = normalize_name(param_name)
                    self.file_log(f"[RESOLVE] Looking for param '{param_name}' (normalized: '{param_name_normalized}')")
                    
                    # Check if current_obj itself is a mixer device (ChainMixerDevice)
                    # Mixer params: Volume, Pan, Sends, etc. are properties, not in parameters array
                    if param_name == 'Volume' and hasattr(current_obj, 'volume'):
                        self.file_log(f"[RESOLVE] Found Volume parameter on mixer device")
                        return current_obj.volume
                    elif param_name == 'Pan' and hasattr(current_obj, 'panning'):
                        self.file_log(f"[RESOLVE] Found Panning parameter on mixer device")
                        return current_obj.panning
                    elif param_name.startswith('Send') and hasattr(current_obj, 'sends'):
                        # Handle sends
                        for send in current_obj.sends:
                            if send and hasattr(send, 'name') and param_name in send.name:
                                self.file_log(f"[RESOLVE] Found mixer Send parameter")
                                return send
                    
                    # Fallback: Check for mixer parameters via mixer_device attribute
                    if hasattr(current_obj, 'mixer_device'):
                        mixer = current_obj.mixer_device
                        if param_name == 'Volume' and hasattr(mixer, 'volume'):
                            self.file_log(f"[RESOLVE] Found mixer Volume parameter")
                            return mixer.volume
                        elif param_name == 'Pan' and hasattr(mixer, 'panning'):
                            self.file_log(f"[RESOLVE] Found mixer Panning parameter")
                            return mixer.panning
                        elif param_name.startswith('Send') and hasattr(mixer, 'sends'):
                            # Handle sends
                            for send in mixer.sends:
                                if send and hasattr(send, 'name') and param_name in send.name:
                                    self.file_log(f"[RESOLVE] Found mixer Send parameter")
                                    return send
                    
                    # Check device parameters with normalized comparison
                    if hasattr(current_obj, 'parameters'):
                        self.file_log(f"[RESOLVE] Device has {len(current_obj.parameters)} parameters - using name matching (slow!)")
                        
                        for param in current_obj.parameters:
                            if param and hasattr(param, 'name'):
                                live_name_normalized = normalize_name(param.name)
                                # Try exact normalized match first, then substring
                                if live_name_normalized == param_name_normalized or param_name_normalized in live_name_normalized:
                                    self.file_log(f"[RESOLVE] MATCH! Found '{param.name}' for '{param_name}'")
                                    return param
                    else:
                        self.file_log(f"[RESOLVE] Current object has no 'parameters' attribute!")
                    
                    self.file_log(f"[RESOLVE] FAILED to find parameter '{param_name}'")
                    return None
            
            return None
            
        except Exception as e:
            self.log(f"Error resolving LOM path '{lom_path_str}': {e}")
            return None
    
    def build_midi_map(self, midi_map_handle):
        """Required method for MIDI Remote Scripts"""
        pass
    
    def update_display(self):
        """Called regularly by Live - check for scanner JSON updates"""
        try:
            # Check if scanner JSON has been modified
            if os.path.exists(self.scanner_file):
                current_mtime = os.path.getmtime(self.scanner_file)
                if current_mtime != self.scanner_mtime:
                    self.file_log(f"Scanner JSON updated - reloading (old mtime: {self.scanner_mtime}, new: {current_mtime})")
                    self.load_scanner_json()
                    # Reattach listeners for current track
                    if self.current_track:
                        self.setup_parameter_listeners(self.current_track)
                        self.send_all_parameters()
        except Exception as e:
            self.file_log(f"Error in update_display: {e}")
    
    def receive_midi(self, midi_bytes):
        """Called when MIDI is received"""
        pass


def create_instance(c_instance):
    """Factory function required by Live"""
    return MIDIOverlay(c_instance)
