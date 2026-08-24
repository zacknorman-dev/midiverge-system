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
        self.log_message('MIDI Map Scanner loaded (auto-scan mode)')
        self._c_instance = c_instance
        
        # Schedule scan after a short delay to let Ableton fully load
        self.schedule_message(3, self._scan_from_autosave)
    
    def disconnect(self):
        ControlSurface.disconnect(self)
    
    def build_midi_map(self, midi_map_handle):
        """Don't register for MIDI - causes lockup"""
        # Removed CC89 MIDI routing to prevent lockup on startup
        pass
    
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
                
                # Build LOM path
                lom_path, is_mixer = self._extract_lom_path(track_elem, km, parent_map)
                
                # Resolve parameter at runtime
                param_index = -1
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
                            
                            if hasattr(device, 'parameters'):
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
                            # Resolution failed - collect available parameters for manual matching
                            resolution_error = 'Failed to resolve LOM path: %s' % ' > '.join(lom_path)
                            available_parameters = self._get_available_parameters(live_tracks[track_idx], lom_path)
                            self.log_message('[FAILED] CC%d on track %d (%s): %s' % (cc, track_idx, live_name, resolution_error))
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
                    'param_live_name': param_live_name,
                    'device_class_name': device_class_name,
                    'device_name': device_name,
                    'device_path': [],
                    'is_mixer_param': is_mixer,
                    'lom_path': lom_path,
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
        
        for part in lom_path:
            if part.startswith('devices['):
                m = re.match(r'devices\[(\d+)\]', part)
                if m:
                    idx = int(m.group(1))
                    if hasattr(obj, 'devices') and idx < len(obj.devices):
                        obj = obj.devices[idx]
                        device = obj
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
            elif part == 'mixer_device':
                if hasattr(obj, 'mixer_device'):
                    obj = obj.mixer_device
                    device = obj
                else:
                    return None
            elif part.startswith('param <') or part.startswith('param_index['):
                # Final parameter - find it in device.parameters
                if not device or not hasattr(device, 'parameters'):
                    return None
                
                # Try to match by tag name or use index
                if part.startswith('param_index['):
                    m = re.match(r'param_index\[(\d+)\]', part)
                    if m:
                        idx = int(m.group(1))
                        if idx < len(device.parameters):
                            return {'device': device, 'param': device.parameters[idx]}
                else:
                    # Search by parameter tag (less reliable)
                    param_tag = part[7:-1]  # Extract from 'param <Tag>'
                    for param in device.parameters:
                        if param.original_name == param_tag or param.name == param_tag:
                            return {'device': device, 'param': param}
                
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
                else:
                    return []
        
        # Now collect all parameters from the device
        available = []
        if device and hasattr(device, 'parameters'):
            for idx, param in enumerate(device.parameters):
                try:
                    available.append({
                        'index': idx,
                        'name': param.name,
                        'original_name': param.original_name if hasattr(param, 'original_name') else param.name,
                        'min': param.min if hasattr(param, 'min') else 0.0,
                        'max': param.max if hasattr(param, 'max') else 1.0,
                        'value': param.value if hasattr(param, 'value') else 0.0,
                    })
                except Exception:
                    pass
        
        return available
