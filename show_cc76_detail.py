import json

scanner = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 21_midi_map_scan.json"
user_map = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json"

with open(scanner) as f:
    data = json.load(f)

with open(user_map) as f:
    user_mappings = json.load(f)

# Find CC76 on track "1 Vibra Piano"
cc76 = [m for m in data['mappings'] if m['cc'] == 76 and '1 Vibra Piano' in m['track_name_live']]

if cc76:
    m = cc76[0]
    lom = ' | '.join(m.get('lom_path', []))
    lom_normalized = lom.replace(' | ', '|')
    
    print("CC76 - Track: 1 Vibra Piano")
    print(f"\nSCANNER JSON:")
    print(f"  param_live_name: '{m.get('param_live_name', '')}'")
    print(f"  param_tag: '{m.get('param_tag', '')}'")
    print(f"  lom_path: {lom}")
    print(f"  lom_normalized: {lom_normalized}")
    
    print(f"\nUSER MAPPINGS - checking for match:")
    import re
    def strip_device_classes(path):
        path = re.sub(r'(devices\[\d+\])\s*<[^>]+>', r'\1', path)
        return path
    
    lom_structural = strip_device_classes(lom_normalized)
    print(f"  lom_structural: {lom_structural}")
    
    matched = False
    for key, value in user_mappings.items():
        key_norm = key.replace(' | ', '|')
        key_struct = strip_device_classes(key_norm)
        if lom_structural.endswith(key_struct):
            print(f"\n  MATCH FOUND: '{key}' -> '{value}'")
            matched = True
    
    if not matched:
        print(f"\n  NO MATCH in user_mappings")
        print(f"  Will use param_live_name: '{m.get('param_live_name', '')}'")
