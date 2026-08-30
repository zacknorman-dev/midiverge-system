"""
Debug: Are the learned parameters even in the current scanner JSON?
"""
import json
import os
import re

project_dir = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project"
user_mappings_file = os.path.join(project_dir, "user_param_mappings.json")
scanner_json = os.path.join(project_dir, "PMC Set 20_midi_map_scan.json")

# Load user mappings
with open(user_mappings_file, 'r') as f:
    user_mappings = json.load(f)

# Load scanner JSON
with open(scanner_json, 'r') as f:
    data = json.load(f)

print("=" * 80)
print("QUESTION: Are the learned parameters in the current scanner JSON?")
print("=" * 80)

print("\n### USER LEARNED THESE PARAMETERS ###")
for key, value in user_mappings.items():
    print(f"'{key}' -> '{value}'")

print("\n### SEARCHING SCANNER JSON FOR MATCHING STRUCTURES ###")

def strip_device_classes(path):
    """Remove <ClassName> from device references"""
    path = re.sub(r'(devices\[\d+\])\s*<[^>]+>', r'\1', path)
    path = re.sub(r'(chains\[\d+\])\s*<[^>]+>', r'\1', path)
    return path

# Get all CC71-78 mappings
cc_mappings = [m for m in data['mappings'] if 71 <= m['cc'] <= 78]

# For each user mapping, search for a structural match in scanner JSON
for user_key, user_value in user_mappings.items():
    print(f"\n--- Looking for match for: '{user_value}' ---")
    print(f"Saved key: '{user_key}'")
    
    user_normalized = user_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
    user_structural = strip_device_classes(user_normalized)
    print(f"Structural pattern: '{user_structural}'")
    
    found_matches = []
    for m in cc_mappings:
        lom_path = ' | '.join(m.get('lom_path', []))
        lom_normalized = lom_path.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
        lom_structural = strip_device_classes(lom_normalized)
        
        # Check if it matches
        if lom_structural.endswith(user_structural):
            found_matches.append({
                'track': m['track_name_live'],
                'cc': m['cc'],
                'param_name': m.get('param_live_name', ''),
                'param_tag': m.get('param_tag', ''),
                'lom_path': lom_path,
                'lom_structural': lom_structural
            })
    
    if found_matches:
        print(f"  [OK] Found {len(found_matches)} potential matches:")
        for match in found_matches:
            print(f"    CC{match['cc']} on track '{match['track']}'")
            print(f"      Current name: '{match['param_name'] or match['param_tag']}'")
            print(f"      LOM: {match['lom_path']}")
    else:
        print(f"  [FAIL] NO MATCHES FOUND in scanner JSON!")
        print(f"  This means the parameter was removed or changed since you learned it.")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("If all learned parameters show '[FAIL] NO MATCHES', that means:")
print("  1. The scanner JSON is old (from before you did the MIDI learning)")
print("  2. OR the track/device structure changed")
print("  3. You need to save Ableton to generate a new scanner JSON")
