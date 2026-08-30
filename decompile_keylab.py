#!/usr/bin/env python3
"""Decompile KeyLab mk3 .pyc files to understand encoder handling."""
import dis
import marshal
import sys
import os

pyc_dir = r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3"

# List all .pyc files
pyc_files = [f for f in os.listdir(pyc_dir) if f.endswith('.pyc')]
print(f"Found {len(pyc_files)} .pyc files in KeyLab_mk3:\n")

# Focus on likely encoder-related files
interesting = ['midi.pyc', 'elements.pyc', 'mappings.pyc', '__init__.pyc']

for filename in interesting:
    if filename not in pyc_files:
        continue
        
    filepath = os.path.join(pyc_dir, filename)
    print(f"\n{'='*60}")
    print(f"FILE: {filename}")
    print('='*60)
    
    try:
        with open(filepath, 'rb') as f:
            # Skip magic number and timestamp (first 16 bytes in Python 3.10+)
            f.read(16)
            code = marshal.load(f)
            
        print("\nConstants that might be relevant:")
        for const in code.co_consts:
            if isinstance(const, (int, str)):
                s = str(const)
                # Look for encoder/MIDI/relative related terms
                if any(term in s.lower() for term in ['encoder', 'relative', 'cc', 'midi', '64', '66', '62', 'map']):
                    print(f"  {repr(const)}")
        
        print("\nVariable names:")
        for name in code.co_names:
            if any(term in name.lower() for term in ['encoder', 'relative', 'cc', 'midi', 'map', 'mode']):
                print(f"  {name}")
                
    except Exception as e:
        print(f"Error reading {filename}: {e}")

print("\n\nTo see full bytecode disassembly of a specific file, run:")
print("python -c \"import dis, marshal; f=open(r'path.pyc','rb'); f.read(16); dis.dis(marshal.load(f))\"")
