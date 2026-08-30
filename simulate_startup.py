"""
Simulate EXACT overlay startup process
"""
import json
import os
import glob
import re

project_dir = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project"
user_mappings_file = os.path.join(project_dir, "user_param_mappings.json")

print("=" * 80)
print("SIMULATING OVERLAY STARTUP")
print("=" * 80)

# STEP 1: Find mapping files (exactly as overlay does)
print("\n### STEP 1: Find mapping files ###")
pattern = os.path.join(project_dir, "*_midi_map_scan.json")
found_files = glob.glob(pattern)

if found_files:
    # Sort by modification time (newest first)
    available_mapping_files = sorted(found_files, key=os.path.getmtime, reverse=True)
    print(f"Found {len(available_mapping_files)} mapping file(s):")
    for i, filepath in enumerate(available_mapping_files):
        filename = os.path.basename(filepath)
        project_name = filename.replace('_midi_map_scan.json', '')
        mod_time = os.path.getmtime(filepath)
        import time
        mod_time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mod_time))
        marker = " <- WILL USE THIS" if i == 0 else ""
        print(f"  [{i+1}] {project_name} (modified: {mod_time_str}){marker}")
    
    # Use most recent file by default
    current_mapping_file = available_mapping_files[0]
    print(f"\nSelected: {os.path.basename(current_mapping_file)}")
else:
    print("ERROR: No mapping files found!")
    exit(1)

# STEP 2: Load user mappings
print("\n### STEP 2: Load user mappings ###")
with open(user_mappings_file, 'r') as f:
    user_mappings = json.load(f)

print(f"Loaded {len(user_mappings)} user mappings:")
for key, value in user_mappings.items():
    print(f"  '{key}' -> '{value}'")

# STEP 3: Load scanner JSON
print(f"\n### STEP 3: Load scanner JSON ###")
with open(current_mapping_file, 'r') as f:
    data = json.load(f)

print(f"Total mappings: {data['total_mappings']}")

# STEP 4: Process and apply overrides
print("\n### STEP 4: Process CC71-78 and apply user_mappings ###")

from collections import defaultdict

def strip_device_classes(path):
    path = re.sub(r'(devices\[\d+\])\s*<[^>]+>', r'\1', path)
    path = re.sub(r'(chains\[\d+\])\s*<[^>]+>', r'\1', path)
    return path

# Group by track
track_cc_map = defaultdict(lambda: defaultdict(list))

for mapping in data['mappings']:
    if 71 <= mapping['cc'] <= 78:
        track_name = mapping['track_name_live']
        cc = mapping['cc']
        
        param_info = {
            'param_name': mapping.get('param_live_name', mapping.get('param_tag', 'Unknown')),
            'lom_path': mapping.get('lom_path', []),
        }
        track_cc_map[track_name][cc].append(param_info)

# Process ALL tracks and apply user_mappings
mappings_applied = 0
total_params_checked = 0

print(f"\nChecking first 10 parameters for matches...")

for track_name in sorted(track_cc_map.keys())[:10]:  # First 10 tracks
    for cc in range(71, 79):
        if cc in track_cc_map[track_name] and track_cc_map[track_name][cc]:
            param_info = track_cc_map[track_name][cc][0]
            param_name = param_info['param_name']
            lom_path_list = param_info.get('lom_path', [])
            
            if not lom_path_list:
                continue
            
            total_params_checked += 1
            
            # Build lom_path_key (with spaces, as scanner JSON has them)
            lom_path_key = ' | '.join(lom_path_list)
            
            # THE MATCHING LOGIC (copied exactly from overlay)
            matched_param_name = None
            
            # Normalize: remove all spaces around pipes
            lom_normalized = lom_path_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
            
            # Strategy 1: Try exact match first (fast path)
            if lom_path_key in user_mappings or lom_normalized in user_mappings:
                matched_param_name = user_mappings.get(lom_path_key) or user_mappings.get(lom_normalized)
                print(f"\n[EXACT MATCH] CC{cc} {track_name}")
                print(f"  '{param_name}' -> '{matched_param_name}'")
                mappings_applied += 1
            else:
                # Strategy 2: Structural match
                lom_structural = strip_device_classes(lom_normalized)
                
                for saved_key, saved_value in user_mappings.items():
                    saved_normalized = saved_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
                    saved_structural = strip_device_classes(saved_normalized)
                    
                    if lom_structural.endswith(saved_structural):
                        matched_param_name = saved_value
                        print(f"\n[STRUCTURAL MATCH] CC{cc} {track_name}")
                        print(f"  Original: '{param_name}'")
                        print(f"  Scanner LOM: {lom_path_key}")
                        print(f"  Saved key: '{saved_key}'")
                        print(f"  Matched to: '{matched_param_name}'")
                        mappings_applied += 1
                        break

print(f"\n{'=' * 80}")
print(f"SUMMARY")
print(f"{'=' * 80}")
print(f"Checked {total_params_checked} parameters")
print(f"Applied {mappings_applied} user mapping overrides")
print(f"Success rate: {mappings_applied}/{len(user_mappings)} learned names found")

if mappings_applied == 0:
    print("\n⚠ NO MATCHES FOUND!")
    print("This means:")
    print("  1. You learned parameters AFTER the last scanner JSON was created")
    print("  2. You need to save Ableton to trigger a new scan")
elif mappings_applied < len(user_mappings):
    print(f"\n⚠ Only {mappings_applied}/{len(user_mappings)} learned names matched")
    print("The missing ones were probably learned after the last scan.")
    print("Save Ableton to update the scanner JSON.")
