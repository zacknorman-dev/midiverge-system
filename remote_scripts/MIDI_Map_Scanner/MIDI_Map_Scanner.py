import gzip
import json
import os
import xml.etree.ElementTree as ET

import Live
from _Framework.ControlSurface import ControlSurface


class MidiMapScanner(ControlSurface):

    def __init__(self, c_instance):
        super(MidiMapScanner, self).__init__(c_instance)
        self.log_message('MIDI Map Scanner loaded')
        self._last_mtime = 0
        self._polling = True
        self._user_mappings = self._load_user_mappings()
        self._previous_custom_labels = self._load_previous_custom_labels(self.song().file_path) if self.song().file_path else {}
        self._scan_and_write()
        
        # Add save listener to trigger immediate re-scan
        if not self.song().is_dirty_has_listener(self._on_is_dirty_changed):
            self.song().add_is_dirty_listener(self._on_is_dirty_changed)
        
        # Poll faster for file changes (5 ticks = ~83ms)
        self.schedule_message(5, self._poll)

    def disconnect(self):
        self._polling = False
        
        # Remove save listener
        if self.song().is_dirty_has_listener(self._on_is_dirty_changed):
            self.song().remove_is_dirty_listener(self._on_is_dirty_changed)
        
        self._scan_and_write()
        super(MidiMapScanner, self).disconnect()

    def _on_is_dirty_changed(self):
        """Triggered when project save state changes (dirty -> clean means saved)"""
        # is_dirty == False means project was just saved
        if not self.song().is_dirty:
            self.log_message('MIDI Map Scanner: Save detected, scheduling re-scan')
            # Defer scan slightly to ensure file is fully written
            self.schedule_message(10, self._scan_and_write)
    
    def _poll(self):
        if not self._polling:
            return
        als_path = self.song().file_path
        if als_path:
            try:
                mtime = os.path.getmtime(als_path)
                if mtime != self._last_mtime:
                    self.log_message('MIDI Map Scanner: File change detected via polling')
                    self._scan_and_write()
            except Exception:
                pass
        # Poll every 5 ticks (~83ms) instead of 30 for faster detection
        self.schedule_message(5, self._poll)
    
    def _load_user_mappings(self):
        """Load user-defined parameter name mappings from JSON file"""
        try:
            als_path = self.song().file_path
            if not als_path:
                return {}
            
            # User mappings file in same directory as .als file
            project_dir = os.path.dirname(als_path)
            user_mappings_file = os.path.join(project_dir, 'user_param_mappings.json')
            
            if not os.path.exists(user_mappings_file):
                return {}
            
            with open(user_mappings_file, 'r') as f:
                data = json.load(f)
            
            self.log_message('MIDI Map Scanner: loaded %d user parameter mappings' % len(data))
            return data
        except Exception as e:
            self.log_message('MIDI Map Scanner: error loading user mappings: %s' % str(e))
            return {}

    def _load_previous_custom_labels(self, als_path):
        """Load custom_label and manual param_index overrides from previous JSON scan to preserve across rescans"""
        try:
            out_path = r'C:\Users\zackn\Documents\midi overlay\current_scan.json'
            if not os.path.exists(out_path):
                return {}
            
            with open(out_path, 'r') as f:
                data = json.load(f)
            
            # Build dict: {(track_name, cc): {'custom_label': str, 'manual_fix': {param_index, param_live_name, lom_path}}}
            custom_labels = {}
            for mapping in data.get('mappings', []):
                track_name = mapping.get('track_name_live', '')
                cc = mapping.get('cc', -1)
                key = (track_name, cc)
                
                custom_label = mapping.get('custom_label', '')
                if custom_label:
                    if key not in custom_labels:
                        custom_labels[key] = {}
                    custom_labels[key]['custom_label'] = custom_label
                
                # Preserve manually-fixed mappings (valid param_index with empty device_class_name indicates Manual Fix)
                param_index = mapping.get('param_index', -1)
                param_live_name = mapping.get('param_live_name', '')
                lom_path = mapping.get('lom_path', [])
                # Manual Fix signature: param_index >= 0 AND lom_path contains 'param_index[N]' format
                if param_index >= 0 and lom_path and any('param_index[' in str(p) for p in lom_path):
                    if key not in custom_labels:
                        custom_labels[key] = {}
                    custom_labels[key]['manual_fix'] = {
                        'param_index': param_index,
                        'param_live_name': param_live_name,
                        'lom_path': lom_path,
                        'device_class_name': mapping.get('device_class_name', ''),
                        'device_name': mapping.get('device_name', '')
                    }
                    self.log_message('MIDI Map Scanner: Preserving manual fix for %s CC%d (param_index %d)' % (track_name, cc, param_index))
            
            if custom_labels:
                self.log_message('MIDI Map Scanner: loaded %d custom labels from previous scan' % len(custom_labels))
            return custom_labels
        except Exception as e:
            self.log_message('MIDI Map Scanner: error loading previous custom labels: %s' % str(e))
            return {}

    def _scan_and_write(self):
        als_path = self.song().file_path
        if not als_path:
            self.log_message('MIDI Map Scanner: set not saved yet, no .als path')
            return
        try:
            self._last_mtime = os.path.getmtime(als_path)
        except Exception:
            pass

        # Reload user mappings every scan (project is now loaded)
        self._user_mappings = self._load_user_mappings()

        # Load previous JSON to preserve custom_label values
        self._previous_custom_labels = self._load_previous_custom_labels(als_path)

        try:
            with gzip.open(als_path, 'rb') as fh:
                root = ET.fromstring(fh.read())
        except Exception as e:
            self.log_message('MIDI Map Scanner: failed to open/parse .als: ' + str(e))
            return

        parent_map = {child: parent for parent in root.iter() for child in parent}

        tracks_elem = root.find('LiveSet/Tracks')
        if tracks_elem is None:
            self.log_message('MIDI Map Scanner: LiveSet/Tracks not found')
            return

        live_tracks = (list(self.song().tracks)
                       + list(self.song().return_tracks)
                       + [self.song().master_track])

        # First pass: collect ALL track names (even those with no MIDI mappings)
        all_tracks = []
        for track_idx, track_elem in enumerate(tracks_elem):
            track_type = track_elem.tag
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
                'track_type': track_type,
                'track_name_xml': xml_track_name,
                'track_name_live': live_name
            })

        # Second pass: collect MIDI mappings
        results = []
        for track_idx, track_elem in enumerate(tracks_elem):
            track_type = track_elem.tag

            name_elem = track_elem.find('.//Name[@Value]')
            xml_track_name = name_elem.get('Value', '') if name_elem is not None else ''

            live_name = ''
            if track_idx < len(live_tracks):
                try:
                    live_name = live_tracks[track_idx].name
                except Exception:
                    pass

            for km in track_elem.iter('KeyMidi'):
                is_note_elem = km.find('IsNote')
                if (is_note_elem is None
                        or is_note_elem.get('Value', 'true').lower() == 'true'):
                    continue

                cc_elem = km.find('NoteOrController')
                ch_elem = km.find('Channel')
                if cc_elem is None:
                    continue

                cc = int(cc_elem.get('Value', -1))
                channel = int(ch_elem.get('Value', -1)) if ch_elem is not None else -1

                # channel > 15 is Ableton sentinel for unmapped
                if cc < 0 or channel < 0 or channel > 15:
                    continue

                param_elem = parent_map.get(km)
                param_tag = param_elem.tag if param_elem is not None else '?'

                lom_path, is_mixer = self._extract_lom_path(track_elem, km, parent_map)
                
                # Resolve parameter and device info at runtime for reliable lookup
                param_index = -1
                param_live_name = ''
                device_class_name = ''
                device_name = ''
                device_path = []
                
                try:
                    if track_idx < len(live_tracks):
                        resolved = self._resolve_live_parameter(live_tracks[track_idx], lom_path)
                        if resolved:
                            device = resolved['device']
                            param = resolved['param']
                            
                            # ChainMixerDevice doesn't have a parameters list
                            if hasattr(device, 'parameters'):
                                param_index = list(device.parameters).index(param)
                            else:
                                param_index = -1
                            
                            # IMPORTANT: Replace 'param <Name>' with 'param_index[N]' for direct lookup
                            if param_index >= 0 and lom_path and lom_path[-1].startswith('param <'):
                                lom_path[-1] = 'param_index[%d]' % param_index
                            
                            param_live_name = param.name
                            device_class_name = device.class_name if hasattr(device, 'class_name') else 'ChainMixerDevice'
                            device_name = device.name if hasattr(device, 'name') else ''
                            device_path = resolved.get('device_path', [])
                            
                            self.log_message('[SCAN] CC%d RESOLVED: param_idx=%d, param_name="%s", device_name="%s", device_class="%s"' % (cc, param_index, param_live_name, device_name, device_class_name))
                            
                            # For ChainMixerDevice (empty device_name), build "Rack > Chain" name from device_path
                            if not device_name and device_class_name == 'ChainMixerDevice' and device_path:
                                last_chain = device_path[-1]
                                rack_name = last_chain.get('parent_rack_name', 'Rack')
                                chain_name = last_chain.get('name', 'Chain')
                                device_name = '%s > %s' % (rack_name, chain_name)
                        else:
                            # Log failed resolution
                            self.log_message('[SCAN] CC%d FAILED: track %d (%s), path: %s' 
                                           % (cc, track_idx, live_name, ' > '.join(lom_path)))
                except Exception as e:
                    self.log_message('[SCAN] CC%d ERROR: %s' % (cc, str(e)))
                
                # If Scanner failed to resolve (param_index == -1), check for manual fix override
                if param_index < 0:
                    custom_label_key = (live_name, cc)
                    if custom_label_key in self._previous_custom_labels:
                        preserved = self._previous_custom_labels[custom_label_key]
                        if 'manual_fix' in preserved:
                            manual = preserved['manual_fix']
                            param_index = manual['param_index']
                            param_live_name = manual['param_live_name']
                            device_class_name = manual['device_class_name']
                            lom_path = manual['lom_path']
                            self.log_message('MIDI Map Scanner: Using preserved manual fix for %s CC%d (param_index %d)' % (live_name, cc, param_index))
                            
                            # Always re-resolve device_name from Live API using lom_path
                            try:
                                self.log_message('DEBUG: Attempting to resolve device_name, lom_path=%s' % str(lom_path))
                                if track_idx < len(live_tracks):
                                    resolved = self._resolve_live_parameter(live_tracks[track_idx], lom_path)
                                    self.log_message('DEBUG: _resolve_live_parameter returned: %s' % ('None' if not resolved else 'data'))
                                    if resolved and 'device' in resolved:
                                        device = resolved['device']
                                        device_name = device.name if hasattr(device, 'name') else device_class_name
                                        self.log_message('MIDI Map Scanner: Resolved device_name="%s" for %s CC%d' % (device_name, live_name, cc))
                                    else:
                                        device_name = device_class_name
                                        self.log_message('DEBUG: resolved is None or no device, using class name "%s"' % device_name)
                                else:
                                    device_name = device_class_name
                                    self.log_message('DEBUG: track_idx %d >= len(live_tracks) %d' % (track_idx, len(live_tracks)))
                            except Exception as ex:
                                device_name = device_class_name
                                self.log_message('DEBUG: Exception resolving device_name: %s' % str(ex))

                result = {
                    'track_index': track_idx,
                    'track_type': track_type,
                    'track_name_xml': xml_track_name,
                    'track_name_live': live_name,
                    'cc': cc,
                    'channel': channel,
                    'param_tag': param_tag,
                    'param_index': param_index,
                    'param_live_name': param_live_name,
                    'device_class_name': device_class_name,
                    'device_name': device_name,
                    'device_path': device_path,
                    'is_mixer_param': is_mixer,
                    'lom_path': lom_path,
                }
                
                # Preserve custom_label from previous scan if it exists
                custom_label_key = (live_name, cc)
                if custom_label_key in self._previous_custom_labels:
                    preserved = self._previous_custom_labels[custom_label_key]
                    if isinstance(preserved, dict) and 'custom_label' in preserved:
                        result['custom_label'] = preserved['custom_label']
                    elif isinstance(preserved, str):
                        # Legacy format: just a string
                        result['custom_label'] = preserved
                
                results.append(result)

        results.sort(key=lambda r: (r['cc'], r['track_index']))

        out = {
            'als_file': als_path,
            'total_tracks': len(all_tracks),
            'total_mappings': len(results),
            'tracks': all_tracks,
            'mappings': results,
        }

        # Always write to fixed location for easy discovery by MIDIOverlay
        out_path = r'C:\Users\zackn\Documents\midi overlay\current_scan.json'
        try:
            # Ensure directory exists
            out_dir = os.path.dirname(out_path)
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            
            with open(out_path, 'w') as fh:
                json.dump(out, fh, indent=2)
            self.log_message(
                'MIDI Map Scanner: wrote %d tracks, %d mappings to %s'
                % (len(all_tracks), len(results), out_path))
        except Exception as e:
            self.log_message('MIDI Map Scanner: failed to write JSON: ' + str(e))

    def _extract_lom_path(self, track_elem, km, parent_map):
        param_elem = parent_map.get(km)
        if param_elem is None:
            return [], False

        ancestors = []
        cur = param_elem
        while True:
            p = parent_map.get(cur)
            if p is None or p is track_elem:
                break
            ancestors.append(cur)
            cur = p
        ancestors.reverse()

        path_parts = []
        is_mixer = False

        for node in ancestors:
            p = parent_map.get(node)
            if p is None:
                continue
            ptag = p.tag

            if ptag == 'Devices':
                idx = list(p).index(node)
                path_parts.append('devices[%d] <%s>' % (idx, node.tag))
            elif ptag == 'Branches':
                idx = list(p).index(node)
                path_parts.append('chains[%d]' % idx)
            elif ptag == 'ReturnBranches':
                idx = list(p).index(node)
                path_parts.append('return_chains[%d]' % idx)

            if node.tag == 'MixerDevice':
                is_mixer = True

        # For track-level mixer parameters, prepend 'mixer_device' so path has >= 2 elements
        if len(path_parts) == 0:
            path_parts.append('mixer_device')
            is_mixer = True

        path_parts.append('param <%s>' % param_elem.tag)
        return path_parts, is_mixer

    def _resolve_live_parameter(self, track, lom_path):
        """Navigate LOM path to find the live parameter object."""
        import re
        
        # Debug: log when resolving nested racks
        if len(lom_path) >= 5:
            self.log_message('[RESOLVE] Attempting nested rack: %s' % ' > '.join(lom_path))
        
        obj = track
        device = None
        device_path = []  # Track chain path for nested racks
        
        self.log_message('[RESOLVE] Processing %d path parts' % len(lom_path))
        for step_idx, part in enumerate(lom_path):
            self.log_message('[RESOLVE] Step %d: %s' % (step_idx, part))
            if part.startswith('devices['):
                m = re.match(r'devices\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    self.log_message('[RESOLVE] Matched devices[%d], obj type: %s' % (idx, type(obj).__name__))
                    if hasattr(obj, 'devices'):
                        if idx < len(obj.devices):
                            obj = obj.devices[idx]
                            device = obj
                            self.log_message('[RESOLVE] Successfully navigated to devices[%d]: %s' % (idx, device.name if hasattr(device, 'name') else 'Unknown'))
                        else:
                            self.log_message('[DEBUG] Step %d: devices[%d] out of bounds (has %d devices)' % (step_idx, idx, len(obj.devices)))
                            return None
                    else:
                        self.log_message('[DEBUG] Step %d: obj has no .devices attribute (obj type: %s)' % (step_idx, type(obj).__name__))
                        return None
                else:
                    self.log_message('[RESOLVE] ERROR: devices[] regex did not match part: "%s"' % part)
                    return None
            elif part.startswith('chains['):
                m = re.match(r'chains\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    self.log_message('[RESOLVE] Matched chains[%d], obj type: %s' % (idx, type(obj).__name__))
                    if hasattr(obj, 'chains'):
                        if idx < len(obj.chains):
                            chain = obj.chains[idx]
                            chain_name = chain.name if hasattr(chain, 'name') else 'Chain %d' % idx
                            self.log_message('[RESOLVE] Successfully navigated to chains[%d]: %s' % (idx, chain_name))
                            # Store chain name and parent rack name (strings only, no Live objects!)
                            parent_rack_name = device.name if (device and hasattr(device, 'name')) else 'Rack'
                            device_path.append({'type': 'chain', 'index': idx, 'name': chain_name, 'parent_rack_name': parent_rack_name})
                            obj = chain
                            device = None  # Reset device context when entering chain
                        else:
                            self.log_message('[DEBUG] Step %d: chains[%d] out of bounds (has %d chains)' % (step_idx, idx, len(obj.chains)))
                            return None
                    else:
                        self.log_message('[DEBUG] Step %d: obj has no .chains attribute (obj type: %s)' % (step_idx, type(obj).__name__))
                        return None
                else:
                    self.log_message('[RESOLVE] ERROR: chains[] regex did not match part: "%s"' % part)
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
                        self.log_message('[RESOLVE] At chain level, looking for param "%s"' % param_tag)
                        self.log_message('[RESOLVE] obj type: %s, has devices: %s' % (type(obj).__name__, hasattr(obj, 'devices')))
                        
                        # Check if this is a chain mixer parameter (Volume, Pan)
                        if hasattr(obj, 'mixer_device'):
                            mixer = obj.mixer_device
                            # ChainMixerDevice: Volume and Pan are direct properties, not in parameters list
                            if param_tag == 'Volume' and hasattr(mixer, 'volume'):
                                return {'device': mixer, 'param': mixer.volume, 'device_path': device_path}
                            elif param_tag == 'Pan' and hasattr(mixer, 'panning'):
                                return {'device': mixer, 'param': mixer.panning, 'device_path': device_path}
                            elif param_tag == 'ChainActivator' and hasattr(mixer, 'chain_activator'):
                                return {'device': mixer, 'param': mixer.chain_activator, 'device_path': device_path}
                        
                        # Search chain's devices for the parameter
                        if hasattr(obj, 'devices'):
                            self.log_message('[RESOLVE] Chain has %d devices' % len(obj.devices))
                            for dev_idx, dev in enumerate(obj.devices):
                                dev_name = dev.name if hasattr(dev, 'name') else 'Unknown'
                                self.log_message('[RESOLVE] Checking device[%d]: %s' % (dev_idx, dev_name))
                                # Try exact match
                                for p in dev.parameters:
                                    if p.original_name == param_tag or p.name == param_tag:
                                        return {'device': dev, 'param': p, 'device_path': device_path}
                                
                                # Try comprehensive name mappings
                                name_map = {
                                    'OutputGain': ['Output Gain', 'Gain', 'Output Level', 'Level', 'Output'],
                                    'DryWet': ['Dry/Wet', 'Dry', 'Mix'],
                                    'Envelope1_Attack': ['Env 1 Attack', 'Envelope 1 Attack', 'Attack'],
                                    'Envelope1_Decay': ['Env 1 Decay', 'Envelope 1 Decay', 'Decay'],
                                    'Envelope1_Sustain': ['Env 1 Sustain', 'Envelope 1 Sustain', 'Sustain'],
                                    'Envelope1_Release': ['Env 1 Release', 'Envelope 1 Release', 'Release'],
                                    'CyclingEnvelope_MidPoint': ['Cycling Envelope Mid Point', 'Cycling Env Mid Point', 'Mid Point', 'Midpoint'],
                                    'CyclingEnvelope_Hold': ['Cycling Envelope Hold', 'Cycling Env Hold', 'Hold'],
                                    'CyclingEnvelope_Rate': ['Cycling Envelope Rate', 'Cycling Env Rate', 'Rate'],
                                    'Lfo_Amount': ['LFO Amount', 'Lfo Amount', 'Amount'],
                                }
                                
                                # Handle MacroControls.X → Macro Y (where Y = X+1)
                                if param_tag.startswith('MacroControls.'):
                                    try:
                                        macro_idx = int(param_tag.split('.')[1])
                                        macro_name = 'Macro %d' % (macro_idx + 1)
                                        name_map[param_tag] = [macro_name]
                                    except:
                                        pass
                                
                                search_names = name_map.get(param_tag, [param_tag])
                                if not isinstance(search_names, list):
                                    search_names = [search_names]
                                
                                # Add user mapping if available
                                dev_class_name = dev.class_name if hasattr(dev, 'class_name') else type(dev).__name__
                                if dev_class_name in self._user_mappings:
                                    if param_tag in self._user_mappings[dev_class_name]:
                                        user_mapped_name = self._user_mappings[dev_class_name][param_tag]
                                        if user_mapped_name not in search_names:
                                            search_names.insert(0, user_mapped_name)  # Try user mapping first
                                
                                for search_name in search_names:
                                    for p in dev.parameters:
                                        if p.original_name == search_name or p.name == search_name:
                                            return {'device': dev, 'param': p, 'device_path': device_path}
                        self.log_message('[RESOLVE] Failed: param "%s" not found in chain devices' % param_tag)
                        return None
                    
                    # If we have a device context, search its parameters
                    if device:
                        self.log_message('[RESOLVE] Have device context: %s (type: %s)' % (device.name if hasattr(device, 'name') else 'Unknown', type(device).__name__))
                        self.log_message('[RESOLVE] Device has %d parameters' % len(list(device.parameters)))
                        
                        # For debugging: log all parameters for AutoFilter devices
                        dev_class_name = device.class_name if hasattr(device, 'class_name') else type(device).__name__
                        if dev_class_name == 'AutoFilter':
                            all_params = []
                            for idx, p in enumerate(device.parameters):
                                all_params.append('[%d] %s (orig: %s)' % (idx, p.name, p.original_name))
                            self.log_message('[RESOLVE] AutoFilter params: %s' % ' | '.join(all_params))
                        
                        # For debugging: log first 10 parameter names
                        if len(list(device.parameters)) > 0:
                            param_names = [p.name for p in list(device.parameters)[:10]]
                            self.log_message('[RESOLVE] First 10 param names: %s' % ', '.join(param_names))
                        
                        # For debugging: log parameters containing target words
                        if 'Envelope' in param_tag or 'Decay' in param_tag:
                            matching_params = [p.name for p in device.parameters if 'envelope' in p.name.lower() or 'decay' in p.name.lower()]
                            if matching_params:
                                self.log_message('[RESOLVE] Params with "envelope" or "decay": %s' % ', '.join(matching_params))
                            matching_original = [p.original_name for p in device.parameters if 'envelope' in p.original_name.lower() or 'decay' in p.original_name.lower()]
                            if matching_original:
                                self.log_message('[RESOLVE] Original names with "envelope" or "decay": %s' % ', '.join(matching_original))
                        
                        # Try exact match first
                        for p in device.parameters:
                            if p.original_name == param_tag or p.name == param_tag:
                                return {'device': device, 'param': p, 'device_path': device_path}
                        
                        # Try comprehensive name mappings
                        name_map = {
                            'OutputGain': ['Output Gain', 'Gain', 'Output Level', 'Level', 'Output'],
                            'DryWet': ['Dry/Wet', 'Dry', 'Mix'],
                            'Envelope1_Attack': ['Env 1 Attack', 'Envelope 1 Attack', 'Attack'],
                            'Envelope1_Decay': ['Env 1 Decay', 'Envelope 1 Decay', 'Decay'],
                            'Envelope1_Sustain': ['Env 1 Sustain', 'Envelope 1 Sustain', 'Sustain'],
                            'Envelope1_Release': ['Env 1 Release', 'Envelope 1 Release', 'Release'],
                            'CyclingEnvelope_MidPoint': ['Cycling Envelope Mid Point', 'Cycling Env Mid Point', 'Mid Point', 'Midpoint'],
                            'CyclingEnvelope_Hold': ['Cycling Envelope Hold', 'Cycling Env Hold', 'Hold'],
                            'CyclingEnvelope_Rate': ['Cycling Envelope Rate', 'Cycling Env Rate', 'Rate'],
                            'Lfo_Amount': ['LFO Amount', 'Lfo Amount', 'Amount'],
                        }
                        
                        # Handle MacroControls.X → Macro Y (where Y = X+1)
                        # MacroControls.0 → Macro 1, MacroControls.6 → Macro 7, etc.
                        if param_tag.startswith('MacroControls.'):
                            try:
                                macro_idx = int(param_tag.split('.')[1])
                                macro_name = 'Macro %d' % (macro_idx + 1)
                                name_map[param_tag] = [macro_name]
                            except:
                                pass
                        
                        # Get list of alternative names to try
                        search_names = name_map.get(param_tag, [param_tag])
                        if not isinstance(search_names, list):
                            search_names = [search_names]
                        
                        # Add user mapping if available
                        dev_class_name = device.class_name if hasattr(device, 'class_name') else type(device).__name__
                        if dev_class_name in self._user_mappings:
                            if param_tag in self._user_mappings[dev_class_name]:
                                user_mapped_name = self._user_mappings[dev_class_name][param_tag]
                                if user_mapped_name not in search_names:
                                    search_names.insert(0, user_mapped_name)  # Try user mapping first
                        
                        # Try each alternative name
                        for search_name in search_names:
                            for p in device.parameters:
                                if p.original_name == search_name or p.name == search_name:
                                    return {'device': device, 'param': p, 'device_path': device_path}
                        
                        # Log failure with available parameter names for debugging
                        param_names = [p.name for p in device.parameters if hasattr(p, 'name')][:10]
                        self.log_message('[RESOLVE] Failed: param "%s" not found in device parameters (tried: %s). Available params: %s' 
                                       % (param_tag, ', '.join(search_names), ', '.join(param_names)))
                return None
        
        return None