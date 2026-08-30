import json

# Load the scanner JSON
with open(r'C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 20_midi_map_scan.json') as f:
    data = json.load(f)

# Find some CC71-78 mappings
cc_mappings = [m for m in data['mappings'] if 71 <= m['cc'] <= 78][:5]

print(f"Found {len(cc_mappings)} sample CC71-78 mappings:\n")

for m in cc_mappings:
    print(f"CC{m['cc']} - Track: {m['track_name_live']}")
    print(f"  Param: {m.get('param_live_name', 'NONE')}")
    print(f"  Tag: {m.get('param_tag', 'NONE')}")
    print(f"  LOM Path: {' | '.join(m.get('lom_path', []))}")
    print()

# Load user mappings
print("\n=== USER MAPPINGS ===")
try:
    with open(r'C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json') as f:
        user_maps = json.load(f)
    for key, value in user_maps.items():
        print(f"  '{key}' -> '{value}'")
except FileNotFoundError:
    print("  No user mappings file found")

# Find mappings with Volume or Output parameters that should match
print("\n=== LOOKING FOR VOLUME/OUTPUT PARAMETERS ===")
volume_mappings = [m for m in data['mappings'] if 
                   (71 <= m['cc'] <= 78) and 
                   (m.get('param_tag', '') in ['Volume', 'Output'] or 
                    'Volume' in m.get('param_live_name', '') or 
                    'Output' in m.get('param_live_name', ''))][:5]

for m in volume_mappings:
    lom_path_full = ' | '.join(m.get('lom_path', []))
    lom_normalized = lom_path_full.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
    
    print(f"\nCC{m['cc']} - Track: {m['track_name_live']}")
    print(f"  Param: {m.get('param_live_name', 'NONE')}")
    print(f"  Tag: {m.get('param_tag', 'NONE')}")
    print(f"  Normalized LOM: {lom_normalized}")
    
    # Check match
    matched = False
    for saved_key, saved_value in user_maps.items():
        saved_normalized = saved_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
        if lom_normalized.endswith(saved_normalized):
            print(f"    ✓ MATCHES: '{saved_key}' -> '{saved_value}'")
            matched = True
            break
    if not matched:
        print(f"    ✗ No match")

# Test matching WITH NORMALIZATION
print("\n=== MATCHING TEST (WITH NORMALIZATION) ===")
for m in cc_mappings[:3]:
    lom_path_full = ' | '.join(m.get('lom_path', []))
    lom_normalized = lom_path_full.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
    
    print(f"\nFull LOM Path: {lom_path_full}")
    print(f"Normalized: {lom_normalized}")
    
    # Check if any user mapping key matches as suffix (with normalization)
    matched = False
    for saved_key, saved_value in user_maps.items():
        saved_normalized = saved_key.replace(' | ', '|').replace('| ', '|').replace(' |', '|')
        if lom_normalized.endswith(saved_normalized):
            print(f"  ✓ MATCHES saved key: '{saved_key}' -> '{saved_value}'")
            matched = True
            break
    if not matched:
        print(f"  ✗ No match found")
