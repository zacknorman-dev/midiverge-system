# Test script to understand KeyLab mk3 encoder behavior
# Place in: C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\KeyLab_Test\

from __future__ import absolute_import, print_function, unicode_literals
import Live

def create_instance(c_instance):
    return KeyLabTest(c_instance)

class KeyLabTest:
    """Minimal script to log KeyLab encoder MIDI values."""
    
    def __init__(self, c_instance):
        self._c_instance = c_instance
        self.log_message("KeyLab Test script loaded")
    
    def receive_midi(self, midi_bytes):
        """Log all incoming MIDI to see what KeyLab sends."""
        if len(midi_bytes) == 3:
            status, cc, value = midi_bytes
            if status == 176:  # Control Change on channel 1
                self.log_message(f"CC{cc} = {value} (0x{value:02X})")
    
    def disconnect(self):
        pass
    
    def log_message(self, msg):
        self._c_instance.log_message(str(msg))
