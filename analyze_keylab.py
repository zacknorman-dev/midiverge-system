#!/usr/bin/env python3
"""Extract readable info from KeyLab mk3 bytecode."""
import marshal

pyc_files = {
    'elements': r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3\elements.pyc",
    'midi': r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3\midi.pyc",
    'mappings': r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3\mappings.pyc",
}

output_file = r"c:\Users\zackn\Documents\midi overlay\keylab_elements_decompiled.py"

with open(output_file, 'w', encoding='utf-8') as out:
    out.write("# KeyLab mk3 bytecode analysis\n")
    out.write("# Constants and names extracted from .pyc files\n\n")
    
    for name, pyc_file in pyc_files.items():
        out.write("\n" + "=" * 70 + "\n")
        out.write(f"FILE: {name}.pyc\n")
        out.write("=" * 70 + "\n\n")
        
        try:
            with open(pyc_file, 'rb') as f:
                f.read(16)  # Skip header
                code = marshal.load(f)
            
            out.write(f"Module names: {code.co_names}\n\n")
            
            out.write("Constants (first level):\n")
            for i, const in enumerate(code.co_consts):
                if const is None:
                    continue
                if isinstance(const, (int, str, float)):
                    out.write(f"  {repr(const)}\n")
                elif hasattr(const, 'co_name'):
                    out.write(f"  [Code object: {const.co_name}]\n")
                    # Extract function details
                    if 'encoder' in const.co_name.lower() or 'create' in const.co_name.lower():
                        out.write(f"    - Args: {const.co_varnames[:const.co_argcount]}\n")
                        out.write(f"    - Names used: {const.co_names}\n")
                        out.write(f"    - Constants: {[c for c in const.co_consts if isinstance(c, (int, str, float))]}\n")
            
            out.write("\n")
            
        except Exception as e:
            out.write(f"Error: {e}\n\n")

print(f"Analysis saved to: {output_file}")
