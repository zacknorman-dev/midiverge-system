"""
Check if the learned parameters are in PMC Set 21 scanner JSON
"""
import json
import re

scanner_json = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 21_midi_map_scan.json"

with open(scanner_json, 'r') as f:
    data = json.load(f)

with open(r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json", 'r') as f:
    user_mappings = json.load(f)

print("=" * 80)
print("Checking if learned parameters are in PMC SET 21 scanner JSON")
print("=" * 80)

def strip_device_classes(path):
    path = re.sub(r'(devices\[\d+\])\s*<[^>]+>', r'\1', path)
    path = re.sub(r'(chains\[\d+\])\s*<[^>]+>', r'\1', path)
    return path

cc_mappings = [m for m in data['mappings'] if 71 <= m['cc'] <= 78]
print(f"\nPMC Set 21 has {len(cc_mappings)} CC71-78 mappings")

matches_found = 0

for user_key, user_value in user_mappings.items():
    print(f"\n--- '{user_value}' (saved as '{user_key}') ---")
    
    user_normalized = user_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
    user_structural = strip_device_classes(user_normalized)
    
    found = False
    for m in cc_mappings:
        lom_path = ' | '.join(m.get('lom_path', []))
        lom_normalized = lom_path.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
        lom_structural = strip_device_classes(lom_normalized)
        
        if lom_structural.endswith(user_structural):
            print(f"  [OK] Found in Set 21! CC{m['cc']} on track '{m['track_name_live']}'")
            found = True
            matches_found += 1
            break
    
    if not found:
        print(f"  [X] NOT in Set 21")

print(f"\n{'=' * 80}")
print(f"Result: {matches_found}/{len(user_mappings)} learned parameters found in Set 21")
print(f"{'=' * 80}")
