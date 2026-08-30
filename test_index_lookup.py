"""
Test script to validate device_index/param_index lookups
Run this as a temporary Remote Script to test without breaking production code
"""
import Live
import json
import os
from datetime import datetime

class TestIndexLookup:
    def __init__(self, c_instance):
        self.c_instance = c_instance
        self.song = c_instance.song()
        
        # Output file
        self.output_file = r"c:\Users\zackn\Documents\midi overlay\test_lookup_results.txt"
        
        # Run test after short delay
        self.c_instance.schedule_message(2, self.run_test)
    
    def log(self, msg):
        """Write to output file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.output_file, 'a') as f:
            f.write(f"[{timestamp}] {msg}\n")
    
    def run_test(self):
        """Test all mappings from scanner JSON"""
        self.log("=" * 80)
        self.log("INDEX-BASED LOOKUP TEST")
        self.log("=" * 80)
        
        # Load scanner JSON
        scanner_file = r"c:\Users\zackn\Documents\midi overlay\current_scan.json"
        
        try:
            with open(scanner_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.log(f"ERROR: Could not load scanner file: {e}")
            return
        
        self.log(f"Loaded scanner file with {len(data.get('mappings', []))} mappings")
        self.log("")
        
        # Test each mapping
        success_count = 0
        fail_count = 0
        
        for mapping in data.get('mappings', []):
            track_idx = mapping.get('track_index', -1)
            cc = mapping.get('cc')
            param_tag = mapping.get('param_tag', '?')
            device_index = mapping.get('device_index', -1)
            param_index = mapping.get('param_index', -1)
            track_name = mapping.get('track_name_live', '?')
            
            # Only test CC71-78
            if not (71 <= cc <= 78):
                continue
            
            self.log(f"Track {track_idx} ({track_name}), CC{cc}: param_tag='{param_tag}'")
            
            # Check if we have indices
            if device_index < 0 or param_index < 0:
                self.log(f"  ❌ SKIP - No indices (device_index={device_index}, param_index={param_index})")
                fail_count += 1
                self.log("")
                continue
            
            # Get track
            try:
                if track_idx >= 0 and track_idx < len(self.song.tracks):
                    track = self.song.tracks[track_idx]
                else:
                    self.log(f"  ❌ FAIL - Invalid track_index {track_idx}")
                    fail_count += 1
                    self.log("")
                    continue
            except Exception as e:
                self.log(f"  ❌ FAIL - Could not get track: {e}")
                fail_count += 1
                self.log("")
                continue
            
            # Try index-based lookup
            try:
                self.log(f"  → Trying device[{device_index}].parameters[{param_index}]...")
                
                if not hasattr(track, 'devices') or device_index >= len(track.devices):
                    self.log(f"  ❌ FAIL - device_index {device_index} out of range (track has {len(track.devices) if hasattr(track, 'devices') else 0} devices)")
                    fail_count += 1
                    self.log("")
                    continue
                
                device = track.devices[device_index]
                device_name = device.name if hasattr(device, 'name') else '?'
                
                if not hasattr(device, 'parameters') or param_index >= len(device.parameters):
                    self.log(f"  ❌ FAIL - param_index {param_index} out of range (device '{device_name}' has {len(device.parameters) if hasattr(device, 'parameters') else 0} parameters)")
                    fail_count += 1
                    self.log("")
                    continue
                
                param = device.parameters[param_index]
                param_name = param.name if hasattr(param, 'name') else '?'
                param_value = param.value if hasattr(param, 'value') else '?'
                
                self.log(f"  ✓ SUCCESS - Found '{param_name}' in device '{device_name}'")
                self.log(f"    Current value: {param_value}")
                self.log(f"    Scanner expected: '{param_tag}'")
                
                if param_name != param_tag:
                    self.log(f"    ⚠️  WARNING: Name mismatch! (Live='{param_name}' vs Scanner='{param_tag}')")
                
                success_count += 1
                
            except Exception as e:
                self.log(f"  ❌ FAIL - Exception during lookup: {e}")
                fail_count += 1
            
            self.log("")
        
        # Summary
        self.log("=" * 80)
        self.log(f"TEST COMPLETE: {success_count} SUCCESS, {fail_count} FAIL")
        self.log("=" * 80)
        
        if fail_count > 0 and all(m.get('device_index', -1) < 0 for m in data.get('mappings', [])):
            self.log("")
            self.log("⚠️  ALL MAPPINGS MISSING device_index - Scanner needs to be reloaded!")
            self.log("   Toggle MIDI_Map_Scanner off/on in Ableton preferences to regenerate scan data")
