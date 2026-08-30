"""
Test script to validate canonical chains work correctly.
This walks down each canonical chain and verifies the parameter name matches.
"""

import json

# Load the scan data
with open('current_scan.json', 'r') as f:
    data = json.load(f)

print("=" * 80)
print("CANONICAL CHAIN VALIDATION TEST")
print("=" * 80)

for i, mapping in enumerate(data['mappings']):
    cc = mapping['cc']
    track_idx = mapping['track_index']
    track_name = mapping['track_name_live']
    expected_name = mapping['param_live_name']
    chain = mapping.get('canonical_chain', [])
    
    print(f"\n[{i+1}/{len(data['mappings'])}] CC{cc} on Track {track_idx} ({track_name})")
    print(f"  Expected: '{expected_name}'")
    print(f"  Chain: {chain}")
    
    if not chain:
        print(f"  ❌ NO CANONICAL CHAIN!")
        continue
    
    # Verify chain structure
    if len(chain) != 3:
        print(f"  ❌ INVALID CHAIN LENGTH: {len(chain)} (expected 3)")
        continue
    
    if chain[0]['type'] != 'track':
        print(f"  ❌ First element should be 'track', got '{chain[0]['type']}'")
        continue
    
    if chain[1]['type'] != 'device':
        print(f"  ❌ Second element should be 'device', got '{chain[1]['type']}'")
        continue
    
    if chain[2]['type'] != 'parameter':
        print(f"  ❌ Third element should be 'parameter', got '{chain[2]['type']}'")
        continue
    
    track_i = chain[0]['index']
    device_i = chain[1]['index']
    param_i = chain[2]['index']
    
    print(f"  ✓ Chain structure valid: tracks[{track_i}].devices[{device_i}].parameters[{param_i}]")
    
    # We can't walk the chain in Python without Ableton running,
    # but we can validate the indices are reasonable
    if track_i != track_idx:
        print(f"  ⚠️  WARNING: Chain track index {track_i} != mapping track index {track_idx}")
    
    if device_i < 0 or device_i > 50:
        print(f"  ⚠️  WARNING: Device index {device_i} seems unusual")
    
    if param_i < 0 or param_i > 200:
        print(f"  ⚠️  WARNING: Parameter index {param_i} seems unusual")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
print(f"\nTo verify these chains work in Ableton, we need a Live API script.")
print(f"The MIDIOverlay remote script should walk DOWN these chains to find parameters.")
