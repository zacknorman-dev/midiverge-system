"""
MIDI_Map_Scanner - CC89 triggered API scan
"""
from _Framework.ControlSurface import ControlSurface
from _Framework.InputControlElement import MIDI_CC_TYPE
import Live
import json
import os
import gzip
import xml.etree.ElementTree as ET

SCAN_TRIGGER_CC = 89  # Button 10 triggers scan

class MidiMapScanner(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self.log_message('MIDI Map Scanner loaded (file-trigger mode)')
        self._c_instance = c_instance
        
        # File-based trigger instead of MIDI
        self.trigger_file = r"C:\Users\zackn\Documents\midi overlay\do_scan.txt"
        
        # Schedule scan after a short delay to let Ableton fully load
        self.schedule_message(3, self._scan_from_autosave)
        
        # Start watching for trigger file
        self.schedule_message(10, self._check_trigger_file)
    
    def _check_trigger_file(self):
        """Check if trigger file exists and run scan if found"""
        try:
            if os.path.exists(self.trigger_file):
                self.log_message('[TRIGGER] Found trigger file - starting scan')
                # Delete trigger file immediately
                try:
                    os.remove(self.trigger_file)
                except:
                    pass
                # Run scan
                self._scan_from_autosave()
        except Exception as e:
            self.log_message(f'[TRIGGER] Error checking trigger file: {e}')
        
        # Check again in 1 second
        self.schedule_message(10, self._check_trigger_file)
    
    def disconnect(self):
        ControlSurface.disconnect(self)
    
    def build_midi_map(self, midi_map_handle):
        """Register CC89 for scan trigger"""
        # Forward CC89 on channel 0 to receive_midi - same approach as Live_Track_Controller
        Live.MidiMap.forward_midi_cc(self._c_instance.handle(), midi_map_handle, 0, SCAN_TRIGGER_CC)
    
    def receive_midi(self, midi_bytes):
        """CC89 triggers scan"""
        if len(midi_bytes) >= 3:
            status, cc, value = midi_bytes[:3]
            if (status & 0xF0) == 0xB0 and cc == SCAN_TRIGGER_CC and value > 0:
                self.log_message('[TRIGGER] CC89 received - starting scan')
                self._scan_from_autosave()
    
    def _scan_from_autosave(self):
        """Read auto-save or current project file and scan"""
        # Try to get project file path
        als_path = self.song().file_path
        
        if not als_path:
            self.log_message('[SCAN] Project not saved yet - trying auto-save location')
            # Try auto-save location
            # Auto-saves are in: %APPDATA%\Ableton\Live 12.4\Cache\[project-name]\*.als
            # But project name is hard to determine without file_path
            self.log_message('[SCAN] Cannot find .als file - please save project first')
            return
        
        self.log_message('[SCAN] Reading from: %s' % als_path)
        
        # Parse .als file (it's gzipped XML)
        try:
            with gzip.open(als_path, 'rb') as fh:
                root = ET.fromstring(fh.read())
        except Exception as e:
            self.log_message('[SCAN] Failed to parse .als file: %s' % str(e))
            return
        
        # Build parent map for tree navigation
        parent_map = {child: parent for parent in root.iter() for child in parent}
        
        # Find tracks
        tracks_elem = root.find('LiveSet/Tracks')
        if tracks_elem is None:
            self.log_message('[SCAN] LiveSet/Tracks not found in XML')
            return
        
        # Get live track references
        live_tracks = (list(self.song().tracks)
                       + list(self.song().return_tracks)
                       + [self.song().master_track])
        
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
        successful_mappings = []
        failed_mappings = []
        
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
            
            # Find KeyMidi elements (MIDI mappings)
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
                
                # Only process CC71-78
                if cc < 71 or cc > 78:
                    continue
                
                # channel > 15 is unmapped
                if cc < 0 or channel < 0 or channel > 15:
                    continue
                
                param_elem = parent_map.get(km)
                param_tag = param_elem.tag if param_elem is not None else '?'
                
                # Extract MIDI controller range (Min/Max)
                midi_min = None
                midi_max = None
                if param_elem is not None:
                    midi_range = param_elem.find('MidiControllerRange')
                    if midi_range is not None:
                        min_elem = midi_range.find('Min')
                        max_elem = midi_range.find('Max')
                        if min_elem is not None:
                            try:
                                midi_min = float(min_elem.get('Value', '0'))
                            except:
                                pass
                        if max_elem is not None:
                            try:
                                midi_max = float(max_elem.get('Value', '1'))
                            except:
                                pass
                
                # Build LOM path
                lom_path, is_mixer = self._extract_lom_path(track_elem, km, parent_map)
                
                # Resolve parameter at runtime
                param_index = -1
                device_index = -1
                param_live_name = ''
                device_class_name = ''
                device_name = ''
                resolution_status = 'failed'
                resolution_error = ''
                available_parameters = []
                
                try:
                    if track_idx < len(live_tracks):
                        resolved = self._resolve_live_parameter(live_tracks[track_idx], lom_path)
                        if resolved:
                            device = resolved['device']
                            param = resolved['param']
                            device_index = resolved.get('device_index', -1)
                            
                            # MixerDevice needs special param_index handling (no parameters list)
                            if type(device).__name__ == 'MixerDevice':
                                # Map mixer parameters to indices
                                param_name = param.name if hasattr(param, 'name') else ''
                                if param_name == 'Volume' or param_tag == 'Volume':
                                    param_index = 0
                                elif param_name == 'Panning' or param_tag == 'Panning':
                                    param_index = 1
                                elif 'Send' in param_name or 'Send' in param_tag:
                                    # Extract send number - param could be like "Send A" or param_tag "Send 0"
                                    param_index = 2  # Start at index 2 for sends
                                else:
                                    param_index = -1
                            elif hasattr(device, 'parameters'):
                                param_index = list(device.parameters).index(param)
                            else:
                                param_index = -1
                            
                            # Replace 'param <Name>' with 'param_index[N]'
                            if param_index >= 0 and lom_path and lom_path[-1].startswith('param <'):
                                lom_path[-1] = 'param_index[%d]' % param_index
                            
                            param_live_name = param.name
                            device_class_name = device.class_name if hasattr(device, 'class_name') else 'ChainMixerDevice'
                            device_name = device.name if hasattr(device, 'name') else ''
                            resolution_status = 'success'
                        else:
                            # Resolution failed - try Live API fallback
                            resolution_error = 'Failed to resolve LOM path: %s' % ' > '.join(lom_path)
                            self.log_message('[FAILED] CC%d on track %d (%s): %s' % (cc, track_idx, live_name, resolution_error))
                            self.log_message('[FALLBACK] Querying Live API for CC%d mapping...' % cc)
                            
                            fallback_result = self._query_live_midi_mapping(cc, channel, track_idx)
                            if fallback_result:
                                # Success! Use the Live API result
                                device = fallback_result['device']
                                param = fallback_result['param']
                                device_index = fallback_result['device_index']
                                param_index = fallback_result['param_index']
                                lom_path = fallback_result['lom_path']
                                
                                param_live_name = param.name
                                device_class_name = device.class_name if hasattr(device, 'class_name') else ''
                                device_name = device.name if hasattr(device, 'name') else ''
                                resolution_status = 'success'
                                resolution_error = ''
                                self.log_message('[FALLBACK] SUCCESS! Found %s.%s at device[%d].parameters[%d]' % 
                                    (device_name, param_live_name, device_index, param_index))
                            else:
                                # Fallback also failed - collect available parameters
                                available_parameters = self._get_available_parameters(live_tracks[track_idx], lom_path)
                                self.log_message('[FALLBACK] FAILED - could not find CC%d mapping in Live' % cc)
                                self.log_message('[FAILED]   Available parameters (%d total):' % len(available_parameters))
                                for p in available_parameters:
                                    self.log_message('[FAILED]     [%d] %s (original: %s)' % (p['index'], p['name'], p['original_name']))
                except Exception as e:
                    resolution_error = str(e)
                    self.log_message('[FAILED] CC%d on track %d (%s): %s' % (cc, track_idx, live_name, resolution_error))
                
                result = {
                    'track_index': track_idx,
                    'track_type': track_type,
                    'track_name_xml': xml_track_name,
                    'track_name_live': live_name,
                    'cc': cc,
                    'channel': channel,
                    'param_tag': param_tag,
                    'param_index': param_index,
                    'device_index': device_index,
                    'param_live_name': param_live_name,
                    'device_class_name': device_class_name,
                    'device_name': device_name,
                    'device_path': [],
                    'is_mixer_param': is_mixer,
                    'lom_path': lom_path,
                    'midi_min': midi_min,
                    'midi_max': midi_max,
                    'resolution_status': resolution_status,
                    'resolution_error': resolution_error,
                    'available_parameters': available_parameters if available_parameters else [],
                }
                results.append(result)
                
                # Track success/failure
                if resolution_status == 'success':
                    successful_mappings.append('CC%d -> %s on track "%s"' % (cc, param_live_name, live_name))
                else:
                    failed_mappings.append('CC%d on track "%s" (%s)' % (cc, live_name, resolution_error[:50]))
        
        # Log summary
        self.log_message('=' * 80)
        self.log_message('SCAN SUMMARY:')
        self.log_message('  Total mappings found: %d' % len(results))
        self.log_message('  Successful: %d' % len(successful_mappings))
        self.log_message('  Failed: %d' % len(failed_mappings))
        self.log_message('=' * 80)
        
        if successful_mappings:
            self.log_message('SUCCESSFUL MAPPINGS:')
            for mapping in successful_mappings:
                self.log_message('  ✓ %s' % mapping)
        
        if failed_mappings:
            self.log_message('FAILED MAPPINGS:')
            for mapping in failed_mappings:
                self.log_message('  ✗ %s' % mapping)
        
        self.log_message('=' * 80)
        
        # Write JSON
        output = {
            'als_file': als_path,
            'total_tracks': len(all_tracks),
            'total_mappings': len(results),
            'successful_mappings': len(successful_mappings),
            'failed_mappings': len(failed_mappings),
            'tracks': all_tracks,
            'mappings': results,
        }
        
        out_path = r'C:\Users\zackn\Documents\midi overlay\current_scan.json'
        try:
            out_dir = os.path.dirname(out_path)
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            
            with open(out_path, 'w') as fh:
                json.dump(output, fh, indent=2)
            
            self.log_message('[SCAN] JSON written to: %s' % out_path)
            self.log_message('[SCAN] %d tracks, %d successful, %d failed' % (len(all_tracks), len(successful_mappings), len(failed_mappings)))
        except Exception as e:
            self.log_message('[SCAN] Failed to write JSON: %s' % str(e))
    
    def _extract_lom_path(self, track_elem, km, parent_map):
        """Build LOM path from XML hierarchy"""
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
                path_parts.append('devices[%d]' % idx)
            elif ptag == 'Branches':
                idx = list(p).index(node)
                path_parts.append('chains[%d]' % idx)
            elif ptag == 'ReturnBranches':
                idx = list(p).index(node)
                path_parts.append('return_chains[%d]' % idx)
            
            if node.tag == 'MixerDevice':
                is_mixer = True
        
        # For mixer params, prepend 'mixer_device'
        if len(path_parts) == 0:
            path_parts.append('mixer_device')
            is_mixer = True
        
        path_parts.append('param <%s>' % param_elem.tag)
        return path_parts, is_mixer
    
    def _resolve_live_parameter(self, track, lom_path):
        """Navigate LOM path to find parameter object"""
        import re
        
        obj = track
        device = None
        device_index = -1
        
        for part in lom_path:
            if part.startswith('devices['):
                m = re.match(r'devices\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'devices') and idx < len(obj.devices):
                        obj = obj.devices[idx]
                        device = obj
                        device_index = idx  # Capture device index
                    else:
                        return None
            elif part.startswith('chains['):
                m = re.match(r'chains\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'chains') and idx < len(obj.chains):
                        obj = obj.chains[idx]
                        # Check if this is a chain mixer parameter access
                        # If next part is a param, we need to navigate to mixer_device
                        part_idx = lom_path.index(part)
                        if part_idx + 1 < len(lom_path):
                            next_part = lom_path[part_idx + 1]
                            if next_part.startswith('param <'):
                                # Chain mixer parameter - navigate to mixer_device
                                if hasattr(obj, 'mixer_device'):
                                    device = obj.mixer_device
                                    device_index = -3  # Special marker for chain mixer_device
                                else:
                                    return None
                    else:
                        return None
            elif part == 'mixer_device':
                if hasattr(obj, 'mixer_device'):
                    obj = obj.mixer_device
                    device = obj
                    device_index = -2  # Special marker for mixer_device
                else:
                    return None
            elif part.startswith('param <') or part.startswith('param_index['):
                # Final parameter - find it in device.parameters
                if not device:
                    return None
                
                # MixerDevice is special - use named properties instead of parameters list
                device_type = type(device).__name__
                if device_type in ('MixerDevice', 'ChainMixerDevice'):
                    param_tag = part[7:-1] if part.startswith('param <') else None
                    if param_tag == 'Volume' and hasattr(device, 'volume'):
                        return {'device': device, 'param': device.volume, 'device_index': device_index}
                    elif param_tag == 'Panning' and hasattr(device, 'panning'):
                        return {'device': device, 'param': device.panning, 'device_index': device_index}
                    elif param_tag and param_tag.startswith('Send ') and hasattr(device, 'sends'):
                        send_idx = int(param_tag.split(' ')[1])
                        if send_idx < len(device.sends):
                            return {'device': device, 'param': device.sends[send_idx], 'device_index': device_index}
                    return None
                
                if not hasattr(device, 'parameters'):
                    return None
                
                try:
                    params_list = list(device.parameters)
                except Exception:
                    return None
                
                # Try to match by tag name or use index
                if part.startswith('param_index['):
                    m = re.match(r'param_index\[(\d+)\]', part)
                    if m:
                        idx = int(m.group(1))
                        if idx < len(params_list):
                            return {'device': device, 'param': params_list[idx], 'device_index': device_index}
                else:
                    # Search by parameter tag (match original_name from XML)
                    param_tag_search = part[7:-1]  # Extract from 'param <Tag>'
                    
                    # Transform MacroControls.N -> Macro N+1 (Live's original_name format)
                    if param_tag_search.startswith('MacroControls.'):
                        macro_num = int(param_tag_search.split('.')[1]) + 1
                        param_tag_search = f'Macro {macro_num}'
                    
                    for param in params_list:
                        try:
                            original_name = param.original_name if hasattr(param, 'original_name') else param.name
                            # Match exact original_name
                            if original_name == param_tag_search:
                                return {'device': device, 'param': param, 'device_index': device_index}
                        except Exception:
                            continue
                
                return None
        
        return None
    
    def _get_available_parameters(self, track, lom_path):
        """Get all available parameters on the device specified by lom_path for manual matching"""
        import re
        
        # Navigate to the device (not the parameter)
        device_path = [p for p in lom_path if not p.startswith('param')]
        
        obj = track
        device = None
        
        for part in device_path:
            if part.startswith('devices['):
                m = re.match(r'devices\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'devices') and idx < len(obj.devices):
                        obj = obj.devices[idx]
                        device = obj
                    else:
                        return []
            elif part.startswith('chains['):
                m = re.match(r'chains\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'chains') and idx < len(obj.chains):
                        obj = obj.chains[idx]
                    else:
                        return []
            elif part == 'mixer_device':
                if hasattr(obj, 'mixer_device'):
                    obj = obj.mixer_device
                    device = obj
                    self.log_message('[DEBUG] Found mixer_device: %s' % type(device))
                else:
                    self.log_message('[DEBUG] Track has no mixer_device attribute')
                    return []
        
        # Now collect all parameters from the device
        available = []
        self.log_message('[DEBUG] About to check device: %s, has device=%s' % (type(device) if device else 'None', device is not None))
        if device:
            # MixerDevice is special - doesn't expose parameters list, uses named properties
            if type(device).__name__ == 'MixerDevice':
                self.log_message('[DEBUG] MixerDevice detected - using named properties')
                # Build parameters list from known mixer properties
                try:
                    idx = 0
                    if hasattr(device, 'volume'):
                        available.append({'index': idx, 'name': 'Volume', 'original_name': 'Volume'})
                        idx += 1
                    if hasattr(device, 'panning'):
                        available.append({'index': idx, 'name': 'Panning', 'original_name': 'Panning'})
                        idx += 1
                    if hasattr(device, 'sends'):
                        for send_idx, send in enumerate(device.sends):
                            available.append({'index': idx, 'name': 'Send %d' % send_idx, 'original_name': 'Send %d' % send_idx})
                            idx += 1
                    if hasattr(device, 'track_activator'):
                        available.append({'index': idx, 'name': 'Track Activator', 'original_name': 'Track Activator'})
                        idx += 1
                    self.log_message('[DEBUG] MixerDevice built %d parameters' % len(available))
                except Exception as e:
                    self.log_message('[DEBUG] Failed to build MixerDevice parameters: %s' % str(e))
                return available
            
            # Regular devices with parameters attribute
            if not hasattr(device, 'parameters'):
                self.log_message('[DEBUG] Device has no parameters attribute')
                return []
            try:
                params_list = list(device.parameters)
                self.log_message('[DEBUG] Device has %d parameters' % len(params_list))
                for idx, param in enumerate(params_list):
                    try:
                        available.append({
                            'index': idx,
                            'name': param.name,
                            'original_name': param.original_name if hasattr(param, 'original_name') else param.name,
                            'min': param.min if hasattr(param, 'min') else 0.0,
                            'max': param.max if hasattr(param, 'max') else 1.0,
                            'value': param.value if hasattr(param, 'value') else 0.0,
                        })
                    except Exception as e:
                        self.log_message('[DEBUG] Failed to read param %d: %s' % (idx, str(e)))
            except Exception as e:
                self.log_message('[DEBUG] Failed to list parameters: %s' % str(e))
        
        return available
    
    def _query_live_midi_mapping(self, cc, channel, track_idx):
        """Query Live API to find which parameter is mapped to the given CC.
        This is a fallback when XML-based resolution fails.
        Returns dict with device, param, device_index, param_index, lom_path or None if not found.
        """
        try:
            live_tracks = self.song().tracks
            if track_idx >= len(live_tracks):
                return None
            
            track = live_tracks[track_idx]
            self.log_message('[QUERY] Searching track %d (%s) for CC%d mapping' % (track_idx, track.name, cc))
            
            # Check track mixer parameters first
            if hasattr(track, 'mixer_device'):
                mixer = track.mixer_device
                # Check volume, panning, sends
                for param_name in ['volume', 'panning']:
                    if hasattr(mixer, param_name):
                        param = getattr(mixer, param_name)
                        if self._is_param_mapped_to_cc(param, cc, channel):
                            self.log_message('[QUERY] Found mapping: track mixer.%s' % param_name)
                            return {
                                'device': mixer,
                                'param': param,
                                'device_index': -2,
                                'param_index': 0 if param_name == 'volume' else 1,
                                'lom_path': ['mixer_device', param_name]
                            }
                
                # Check sends
                if hasattr(mixer, 'sends'):
                    for send_idx, send_param in enumerate(mixer.sends):
                        if self._is_param_mapped_to_cc(send_param, cc, channel):
                            self.log_message('[QUERY] Found mapping: track mixer.sends[%d]' % send_idx)
                            return {
                                'device': mixer,
                                'param': send_param,
                                'device_index': -2,
                                'param_index': 2 + send_idx,
                                'lom_path': ['mixer_device', 'sends[%d]' % send_idx]
                            }
            
            # Check all devices on the track
            if hasattr(track, 'devices'):
                for device_idx, device in enumerate(track.devices):
                    # Check device parameters
                    if hasattr(device, 'parameters'):
                        for param_idx, param in enumerate(device.parameters):
                            if self._is_param_mapped_to_cc(param, cc, channel):
                                self.log_message('[QUERY] Found mapping: device[%d].parameters[%d] = %s' % 
                                    (device_idx, param_idx, param.name))
                                
                                # Build MFL path via canonical_parent
                                lom_path = self._build_mfl_path(param)
                                
                                return {
                                    'device': device,
                                    'param': param,
                                    'device_index': device_idx,
                                    'param_index': param_idx,
                                    'lom_path': lom_path
                                }
                    
                    # Check chain mixer parameters if this is a rack device
                    if hasattr(device, 'chains'):
                        for chain_idx, chain in enumerate(device.chains):
                            if hasattr(chain, 'mixer_device'):
                                mixer = chain.mixer_device
                                for param_name in ['volume', 'panning']:
                                    if hasattr(mixer, param_name):
                                        param = getattr(mixer, param_name)
                                        if self._is_param_mapped_to_cc(param, cc, channel):
                                            self.log_message('[QUERY] Found mapping: device[%d].chains[%d].mixer_device.%s' % 
                                                (device_idx, chain_idx, param_name))
                                            return {
                                                'device': mixer,
                                                'param': param,
                                                'device_index': -3,
                                                'param_index': -1,
                                                'lom_path': ['devices[%d]' % device_idx, 'chains[%d]' % chain_idx, 'param <%s>' % param_name.capitalize()]
                                            }
            
            return None
            
        except Exception as e:
            self.log_message('[QUERY] Error querying Live MIDI mappings: %s' % str(e))
            import traceback
            self.log_message(traceback.format_exc())
            return None
    
    def _is_param_mapped_to_cc(self, param, cc, channel):
        """Check if a parameter is MIDI-mapped to the specified CC."""
        try:
            # Check if parameter has MIDI mapping
            # Live API doesn't directly expose CC mappings, so we check value_has_listener
            # and other indicators. This is a best-effort check.
            # Actually, we can't reliably detect MIDI mappings through the API.
            # The only way is to check if the parameter changes when we send the CC.
            # For now, return False - this means we need a different approach.
            # TODO: Find a way to detect MIDI mappings
            return False
        except:
            return False
    
    def _build_mfl_path(self, param):
        """Build MFL path by walking canonical_parent chain.
        Returns list like ['devices[2]', 'parameters[3]']
        """
        path_parts = []
        obj = param
        depth = 0
        
        while hasattr(obj, 'canonical_parent') and depth < 20:
            parent = obj.canonical_parent
            
            # Check if obj is in parameters list
            if hasattr(parent, 'parameters'):
                try:
                    params_list = list(parent.parameters)
                    if obj in params_list:
                        idx = params_list.index(obj)
                        path_parts.insert(0, 'parameters[%d]' % idx)
                except:
                    pass
            
            # Check if obj is in devices list
            if hasattr(parent, 'devices'):
                try:
                    devices_list = list(parent.devices)
                    if obj in devices_list:
                        idx = devices_list.index(obj)
                        path_parts.insert(0, 'devices[%d]' % idx)
                except:
                    pass
            
            # Check if obj is in tracks list
            if hasattr(parent, 'tracks'):
                try:
                    tracks_list = list(parent.tracks)
                    if obj in tracks_list:
                        idx = tracks_list.index(obj)
                        path_parts.insert(0, 'tracks[%d]' % idx)
                except:
                    pass
            
            obj = parent
            depth += 1
        
        return path_parts
