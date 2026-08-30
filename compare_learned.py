import json

scanner = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 21_midi_map_scan.json"
user_map = r"C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json"

with open(scanner) as f:
    data = json.load(f)

with open(user_map) as f:
    user_mappings = json.load(f)

print("=== USER MAPPINGS ===")
for key, value in user_mappings.items():
    print(f"{key} -> {value}")

print("\n=== ALL CC MAPPINGS ON TRACK '1 Vibra Piano' ===")
for m in data['mappings']:
    if '1 Vibra Piano' in m['track_name_live'] and 71 <= m['cc'] <= 78:
        lom = ' | '.join(m.get('lom_path', []))
        print(f"\nCC{m['cc']}: {m.get('param_live_name', 'EMPTY')} (tag: {m.get('param_tag', 'EMPTY')})")
        print(f"  {lom}")

print("\n=== CHECKING: Is 'Dry/Wet' in user_mappings? ===")
drywet_found = any('DryWet' in key or 'Dry/Wet' in value for key, value in user_mappings.items())
print(f"  {drywet_found}")

print("\n=== CHECKING: Is 'Output' or 'OutputGain' in user_mappings? ===")
output_found = [f"{key} -> {value}" for key, value in user_mappings.items() if 'Output' in key or 'Output' in value]
for o in output_found:
    print(f"  {o}")
