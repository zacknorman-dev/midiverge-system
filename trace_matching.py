"""
Trace exactly what happens when overlay loads mappings
"""
import json
import os

print("=" * 80)
print("OVERLAY LOAD SIMULATION - EXACT TRACE")
print("=" * 80)

# Paths
project_dir = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project"
user_mappings_file = os.path.join(project_dir, "user_param_mappings.json")
scanner_json = os.path.join(project_dir, "PMC Set 20_midi_map_scan.json")

# Step 1: Load user mappings (happens FIRST in __init__)
print("\n### STEP 1: Load user_param_mappings.json ###")
if os.path.exists(user_mappings_file):
    with open(user_mappings_file, 'r') as f:
        user_mappings = json.load(f)
    print(f"Loaded {len(user_mappings)} user mappings:")
    for key, value in user_mappings.items():
        print(f"  '{key}' -> '{value}'")
else:
    print("ERROR: user_param_mappings.json not found!")
    user_mappings = {}

# Step 2: Load scanner JSON
print("\n### STEP 2: Load scanner JSON ###")
with open(scanner_json, 'r') as f:
    data = json.load(f)

print(f"Total mappings in JSON: {data['total_mappings']}")

# Step 3: Process CC71-78 mappings
print("\n### STEP 3: Process CC71-78 mappings ###")
cc_mappings = [m for m in data['mappings'] if 71 <= m['cc'] <= 78]
print(f"Found {len(cc_mappings)} CC71-78 mappings")

# Group by track
from collections import defaultdict
track_cc_map = defaultdict(lambda: defaultdict(list))

for mapping in cc_mappings:
    track_name = mapping['track_name_live']
    cc = mapping['cc']
    
    param_info = {
        'param_name': mapping.get('param_live_name', mapping.get('param_tag', 'Unknown')),
        'device_name': mapping.get('device_name', ''),
        'param_tag': mapping.get('param_tag', ''),
        'device_class_name': mapping.get('device_class_name', ''),
        'lom_path': mapping.get('lom_path', []),
    }
    track_cc_map[track_name][cc].append(param_info)

# Step 4: Apply user_mappings overrides (THIS IS THE CRITICAL PART)
print("\n### STEP 4: Apply user_mappings overrides ###")
print("\nTesting matching logic on first 5 tracks with CC71-78:")

track_mappings = {}
mappings_applied = 0

for track_name in sorted(track_cc_map.keys())[:5]:  # First 5 tracks
    print(f"\n--- Track: {track_name} ---")
    track_mappings[track_name] = {}
    
    for cc in range(71, 79):
        encoder_idx = cc - 71
        
        if cc in track_cc_map[track_name] and track_cc_map[track_name][cc]:
            param_info = track_cc_map[track_name][cc][0]
            param_name = param_info['param_name']
            lom_path_list = param_info.get('lom_path', [])
            
            if lom_path_list:
                # This is EXACTLY what the overlay does
                lom_path_key = ' | '.join(lom_path_list)
                
                print(f"\n  Encoder {encoder_idx + 1} (CC{cc}):")
                print(f"    Original param_name: '{param_name}'")
                print(f"    LOM path: '{lom_path_key}'")
                
                # THE MATCHING LOGIC (copied from overlay - WITH STRUCTURAL MATCHING)
                matched_param_name = None
                
                if lom_path_key:
                    # Normalize: remove all spaces around pipes for matching
                    lom_normalized = lom_path_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
                    print(f"    LOM normalized: '{lom_normalized}'")
                    
                    # Strategy 1: Try exact match first
                    if lom_path_key in user_mappings or lom_normalized in user_mappings:
                        matched_param_name = user_mappings.get(lom_path_key) or user_mappings.get(lom_normalized)
                        print(f"    [OK] EXACT MATCH: '{matched_param_name}'")
                    else:
                        # Strategy 2: Structural match - strip device class names
                        import re
                        
                        def strip_device_classes(path):
                            """Remove <ClassName> from device references"""
                            path = re.sub(r'(devices\[\d+\])\s*<[^>]+>', r'\1', path)
                            path = re.sub(r'(chains\[\d+\])\s*<[^>]+>', r'\1', path)
                            return path
                        
                        lom_structural = strip_device_classes(lom_normalized)
                        print(f"    LOM structural: '{lom_structural}'")
                        
                        # Check if any saved key matches structurally
                        for saved_key, saved_value in user_mappings.items():
                            saved_normalized = saved_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
                            saved_structural = strip_device_classes(saved_normalized)
                            
                            # Check if structural paths match as suffixes
                            if lom_structural.endswith(saved_structural):
                                matched_param_name = saved_value
                                print(f"    [OK] STRUCTURAL MATCH:")
                                print(f"      Saved key: '{saved_key}'")
                                print(f"      Saved structural: '{saved_structural}'")
                                print(f"      Result: '{matched_param_name}'")
                                break
                        
                        if not matched_param_name:
                            print(f"    X NO MATCH")
                
                if matched_param_name:
                    param_name = matched_param_name
                    mappings_applied += 1
                    print(f"    → FINAL LABEL: '{param_name}' (OVERRIDDEN)")
                else:
                    print(f"    → FINAL LABEL: '{param_name}' (original)")

print(f"\n{'=' * 80}")
print(f"SUMMARY: Applied {mappings_applied} user mapping overrides out of {len(user_mappings)} saved")
print(f"{'=' * 80}")

if mappings_applied == 0 and len(user_mappings) > 0:
    print("\n⚠ WARNING: NO MAPPINGS APPLIED!")
    print("This means the matching logic is failing.")
    print("\nDEBUG: Let's check one specific case in detail...")
    
    # Take first user mapping and first scanner mapping and compare
    first_user_key = list(user_mappings.keys())[0]
    first_user_val = user_mappings[first_user_key]
    
    print(f"\nUser mapping: '{first_user_key}' -> '{first_user_val}'")
    print(f"Normalized: '{first_user_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')}'")
    
    print(f"\nFirst few scanner LOM paths:")
    for i, m in enumerate(cc_mappings[:3]):
        lom_path = ' | '.join(m.get('lom_path', []))
        lom_norm = lom_path.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
        print(f"  {i+1}. '{lom_norm}'")
