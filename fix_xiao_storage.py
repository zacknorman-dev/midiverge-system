#!/usr/bin/env python3
"""Fix XIAO storage mount to allow host writes via serial REPL."""
import serial
import time
import sys

port = 'COM4'
baud = 115200

print(f"Connecting to {port}...")
try:
    ser = serial.Serial(port, baud, timeout=2)
    time.sleep(0.5)
    
    # Break into REPL with Ctrl-C
    print("Sending Ctrl-C to interrupt...")
    ser.write(b'\x03\x03')
    time.sleep(0.3)
    
    # Clear any output
    ser.reset_input_buffer()
    
    # Send commands to remount storage
    print("Remounting storage as host-writable...")
    ser.write(b'import storage\r\n')
    time.sleep(0.2)
    ser.write(b"storage.remount('/', readonly=True)\r\n")
    time.sleep(0.2)
    
    # Read response
    output = ser.read_all().decode('utf-8', errors='ignore')
    print("Device response:")
    print(output)
    
    ser.close()
    print("\nDone! Try copying files now.")
    
except serial.SerialException as e:
    print(f"ERROR: {e}")
    print("Make sure the XIAO is plugged in and no other program is using COM4")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
