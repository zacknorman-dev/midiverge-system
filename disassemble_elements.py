#!/usr/bin/env python3
"""Disassemble KeyLab mk3 bytecode to understand encoder setup."""
import dis
import marshal
import sys

pyc_file = r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3\elements.pyc"
output_file = r"c:\Users\zackn\Documents\midi overlay\keylab_elements_decompiled.py"

with open(pyc_file, 'rb') as f:
    # Skip header (16 bytes for Python 3.10+)
    f.read(16)
    code = marshal.load(f)

# Write disassembly to file
with open(output_file, 'w', encoding='utf-8') as out:
    out.write("# Disassembled from KeyLab_mk3/elements.pyc\n")
    out.write(f"# Python bytecode version: {code.co_filename}\n\n")
    
    out.write("=" * 70 + "\n")
    out.write("MAIN MODULE\n")
    out.write("=" * 70 + "\n")
    out.write(f"Constants: {code.co_consts}\n")
    out.write(f"Names: {code.co_names}\n\n")
    
    # Get string representation of disassembly
    import io
    buffer = io.StringIO()
    dis.dis(code, file=buffer)
    out.write(buffer.getvalue())
    
    # Also disassemble nested code objects (functions/classes)
    out.write("\n\n" + "=" * 70 + "\n")
    out.write("NESTED FUNCTIONS/CLASSES\n")
    out.write("=" * 70 + "\n\n")
    
    for const in code.co_consts:
        if hasattr(const, 'co_code'):  # It's a code object
            out.write(f"\n{'*' * 60}\n")
            out.write(f"Function/Class: {const.co_name}\n")
            out.write(f"{'*' * 60}\n")
            out.write(f"Args: {const.co_varnames[:const.co_argcount]}\n")
            out.write(f"Constants: {const.co_consts}\n")
            out.write(f"Names: {const.co_names}\n\n")
            
            buffer = io.StringIO()
            dis.dis(const, file=buffer)
            out.write(buffer.getvalue())

print(f"Bytecode disassembly saved to: {output_file}")
print("\nNow searching for encoder-related patterns...")
"""Full disassembly of KeyLab mk3 elements.pyc to see encoder setup."""
import dis
import marshal

pyc_path = r"C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\KeyLab_mk3\elements.pyc"

with open(pyc_path, 'rb') as f:
    # Skip header (16 bytes for Python 3.10+)
    f.read(16)
    code = marshal.load(f)

print("="*80)
print("FULL DISASSEMBLY OF KeyLab_mk3/elements.pyc")
print("="*80)
print()

# Disassemble main module
dis.dis(code)

# Look for create_encoder function specifically
print("\n" + "="*80)
print("SEARCHING FOR create_encoder FUNCTION")
print("="*80)

for const in code.co_consts:
    if hasattr(const, 'co_name') and 'encoder' in const.co_name.lower():
        print(f"\n\nFunction: {const.co_name}")
        print("-"*60)
        dis.dis(const)
