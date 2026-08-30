import json

scanner = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 21_midi_map_scan.json"
user_map = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json"

with open(scanner) as f:
    data = json.load(f)

with open(user_map) as f:
    user_mappings = json.load(f)

print("=== USER MAPPINGS FILE ===")
for key, value in user_mappings.items():
    print(f"{key} -> {value}")

print("\n=== CC76, CC77, CC78 IN SCANNER JSON ===")
for m in data['mappings']:
    if m['cc'] in [76, 77, 78]:
        lom = ' | '.join(m.get('lom_path', []))
        print(f"\nCC{m['cc']} - Track: {m['track_name_live']}")
        print(f"  param_live_name: {m.get('param_live_name', '')}")
        print(f"  param_tag: {m.get('param_tag', '')}")
        print(f"  device_class_name: {m.get('device_class_name', '')}")
        print(f"  lom_path: {lom}")
