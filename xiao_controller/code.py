"""
XIAO RP2040 USB MIDI Controller
10 Rotary Encoders + 10 Buttons via 4x MCP23008 GPIO Expanders
Native USB MIDI with INTERRUPT-DRIVEN reading
v2.0
"""

import board
import busio
import digitalio
import neopixel
import usb_midi
import usb_hid
import adafruit_midi
from adafruit_midi.control_change import ControlChange
import time

# Onboard RGB LED
_np_power = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
_np_power.direction = digitalio.Direction.OUTPUT
_np_power.value = True
rgb = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3)
rgb[0] = (0, 0, 0)  # Off by default

# MCP23008 I2C addresses
U2_ADDR = 0x20
U3_ADDR = 0x21
U4_ADDR = 0x22
U5_ADDR = 0x23

# MCP23008 Registers
MCP_IODIR = 0x00
MCP_IPOL = 0x01
MCP_GPINTEN = 0x02
MCP_DEFVAL = 0x03
MCP_INTCON = 0x04
MCP_IOCON = 0x05
MCP_GPPU = 0x06
MCP_INTF = 0x07
MCP_INTCAP = 0x08
MCP_GPIO = 0x09

# Encoder configurations: (chip_addr, pin_a, pin_b, button_chip, button_pin, cc_enc, cc_btn)
ENCODERS = [
    # Enc1: U2, cross-chip switch - REVERSED (HID Volume/Mute - CC not used)
    (U2_ADDR, 4, 3, U2_ADDR, 6, 60, 61),
    # Enc2: U2 - Button sends CC81 (virtual encoder, toggles 10<->117)
    (U2_ADDR, 2, 1, U2_ADDR, 7, 71, 81),
    # Enc3: U3, cross-chip switch on U2 - REVERSED
    (U3_ADDR, 6, 5, U2_ADDR, 5, 72, 82),
    # Enc4: U3 - REVERSED
    (U3_ADDR, 4, 3, U3_ADDR, 7, 73, 83),
    # Enc5: U3
    (U3_ADDR, 2, 1, U3_ADDR, 0, 74, 84),
    # Enc6: U4 - REVERSED
    (U4_ADDR, 6, 5, U4_ADDR, 7, 75, 85),
    # Enc7: U4 - REVERSED
    (U4_ADDR, 4, 3, U4_ADDR, 0, 76, 86),
    # Enc8: U4, cross-chip switch on U5 - REVERSED
    (U4_ADDR, 2, 1, U5_ADDR, 0, 77, 87),
    # Enc9: U5 - REVERSED
    (U5_ADDR, 6, 5, U5_ADDR, 1, 78, 88),
    # Enc10: U5 - REVERSED
    (U5_ADDR, 4, 3, U5_ADDR, 2, 79, 89),
]

MIDI_CH = 1

# Encoder state
class Encoder:
    def __init__(self):
        self.last_encoded = 0
        self.value = 64
        self.last_dir = 0
        self.last_time = 0
        self.buffer_count = 0  # Accumulate transitions
        self.last_send_time = 0  # When we last sent MIDI

class Button:
    def __init__(self):
        self.last_state = True
        self.toggle = False  # False = off (0), True = on (127)

# Initialize all encoders and buttons
encoders = [Encoder() for _ in range(10)]
buttons = [Button() for _ in range(10)]

# Auto-scan mode state
auto_scan_mode = False

# Setup I2C at 400kHz (fast mode) for faster encoder polling
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

# Setup USB MIDI - single port
midi = adafruit_midi.MIDI(midi_out=usb_midi.ports[1], out_channel=MIDI_CH-1)

# Setup USB HID Consumer Control for Encoder 1 volume control
try:
    from adafruit_hid.consumer_control import ConsumerControl
    from adafruit_hid.consumer_control_code import ConsumerControlCode
    consumer_control = ConsumerControl(usb_hid.devices)
    print("HID Consumer Control initialized")
except Exception as e:
    print(f"Failed to initialize HID (audio dependencies may be missing): {e}")
    consumer_control = None
    ConsumerControlCode = None

# I2C helper functions
def write_reg(addr, reg, val):
    """Write to MCP23008 register"""
    while not i2c.try_lock():
        pass
    try:
        i2c.writeto(addr, bytes([reg, val]))
    finally:
        i2c.unlock()

def read_reg(addr, reg):
    """Read from MCP23008 register"""
    while not i2c.try_lock():
        pass
    try:
        result = bytearray(1)
        i2c.writeto(addr, bytes([reg]))
        i2c.readfrom_into(addr, result)
        return result[0]
    finally:
        i2c.unlock()

def process_encoder(enc, gpio, pin_a, pin_b, cc_num):
    """Process encoder with quadrature decoding"""
    a = (gpio >> pin_a) & 1
    b = (gpio >> pin_b) & 1
    encoded = (b << 1) | a
    sum_val = (enc.last_encoded << 2) | encoded

    direction = 0
    if sum_val in (0b0001, 0b0111, 0b1000, 0b1110):
        direction = 1
    elif sum_val in (0b0010, 0b0100, 0b1011, 0b1101):
        direction = -1

    now = time.monotonic()
    if direction != 0:
        # Debounce: same direction or >70ms since last
        valid = (direction == enc.last_dir) or (now - enc.last_time > 0.07)
        if valid:
            enc.value = max(0, min(127, enc.value + direction))
            midi.send(ControlChange(cc_num, enc.value))
            print(f"CC{cc_num}={enc.value}")
            enc.last_dir = direction
            enc.last_time = now

    enc.last_encoded = encoded

def process_encoder_relative(enc, gpio, pin_a, pin_b, cc_num):
    """Process encoder with buffering - accumulate transitions and send larger increments for fast turns."""
    a = (gpio >> pin_a) & 1
    b = (gpio >> pin_b) & 1
    encoded = (b << 1) | a
    sum_val = (enc.last_encoded << 2) | encoded

    direction = 0
    if sum_val in (0b0001, 0b0111, 0b1000, 0b1110):
        direction = 1
    elif sum_val in (0b0010, 0b0100, 0b1011, 0b1101):
        direction = -1

    now = time.monotonic()
    
    if direction != 0:
        # Direction change - flush buffer if switching direction
        if (enc.buffer_count > 0 and direction != enc.last_dir) or (now - enc.last_send_time > 0.015):
            # Send accumulated value
            if enc.buffer_count != 0:
                value = 64 + (enc.buffer_count * 2) if enc.last_dir == 1 else 64 - (enc.buffer_count * 2)
                value = max(1, min(127, value))  # Clamp to MIDI range
                midi.send(ControlChange(cc_num, value))
                enc.buffer_count = 0
                enc.last_send_time = now
        
        # Accumulate this transition
        enc.buffer_count += 1
        enc.last_dir = direction
    
    # Also flush if buffer gets large or timeout
    elif enc.buffer_count > 0 and (now - enc.last_send_time > 0.015):
        value = 64 + (enc.buffer_count * 2) if enc.last_dir == 1 else 64 - (enc.buffer_count * 2)
        value = max(1, min(127, value))
        midi.send(ControlChange(cc_num, value))
        enc.buffer_count = 0
        enc.last_send_time = now

    enc.last_encoded = encoded

def process_encoder_relative_127(enc, gpio, pin_a, pin_b, cc_num):
    """Process encoder for track selection, sending 1=CW or 127=CCW (for Live_Track_Controller)."""
    a = (gpio >> pin_a) & 1
    b = (gpio >> pin_b) & 1
    encoded = (b << 1) | a
    sum_val = (enc.last_encoded << 2) | encoded

    direction = 0
    if sum_val in (0b0001, 0b0111, 0b1000, 0b1110):
        direction = 1
    elif sum_val in (0b0010, 0b0100, 0b1011, 0b1101):
        direction = -1

    if direction != 0 and encoded != 0b11:
        enc.last_dir = direction

    if encoded == 0b11 and enc.last_dir != 0:
        value = 1 if enc.last_dir == 1 else 127
        midi.send(ControlChange(cc_num, value))
        print(f"CC{cc_num} rel={'CW' if enc.last_dir == 1 else 'CCW'}")
        enc.last_dir = 0

    enc.last_encoded = encoded

def process_encoder_accel(enc, gpio, pin_a, pin_b, cc_num):
    """Process encoder with acceleration: fires once per detent.
    Slow turn -> magnitude 1, faster turns -> 2, 4.
    CW: sends 1/2/4. CCW: sends 127/126/124.
    Python decodes via: delta = val if val < 64 else val - 128."""
    a = (gpio >> pin_a) & 1
    b = (gpio >> pin_b) & 1
    encoded = (b << 1) | a
    sum_val = (enc.last_encoded << 2) | encoded

    direction = 0
    if sum_val in (0b0001, 0b0111, 0b1000, 0b1110):
        direction = 1
    elif sum_val in (0b0010, 0b0100, 0b1011, 0b1101):
        direction = -1

    if direction != 0 and encoded != 0b11:
        enc.last_dir = direction

    if encoded == 0b11 and enc.last_dir != 0:
        now = time.monotonic()
        dt = now - enc.last_time
        enc.last_time = now

        # Acceleration based on time between detents
        if dt < 0.05:       # < 50ms  — very fast
            accel = 4
        elif dt < 0.15:     # < 150ms — medium
            accel = 2
        else:               # slow / first tick
            accel = 1

        value = accel if enc.last_dir == 1 else 128 - accel
        midi.send(ControlChange(cc_num, value))
        print(f"CC{cc_num} rel={'CW' if enc.last_dir == 1 else 'CCW'} accel={accel}")
        enc.last_dir = 0

    enc.last_encoded = encoded

def process_button(btn, gpio, pin, cc_num):
    """Process button: alternates 1/127 like bidirectional encoder."""
    state = bool((gpio >> pin) & 1)
    if state != btn.last_state:
        btn.last_state = state
        if not state:  # Only fire on press (LOW = pressed)
            btn.toggle = not btn.toggle
            value = 1 if btn.toggle else 127  # Alternate like encoder
            midi.send(ControlChange(cc_num, value))
            print(f"CC{cc_num}={'1' if btn.toggle else '127'}")

def process_encoder_volume(enc, gpio, pin_a, pin_b):
    """Process encoder 1 as HID volume control"""
    a = (gpio >> pin_a) & 1
    b = (gpio >> pin_b) & 1
    encoded = (b << 1) | a
    sum_val = (enc.last_encoded << 2) | encoded
    
    direction = 0
    if sum_val in (0b0001, 0b0111, 0b1000, 0b1110):
        direction = 1
    elif sum_val in (0b0010, 0b0100, 0b1011, 0b1101):
        direction = -1
    
    now = time.monotonic()
    if direction != 0:
        # Debounce: same direction or >70ms since last
        valid = (direction == enc.last_dir) or (now - enc.last_time > 0.07)
        if valid:
            if consumer_control:
                if direction == 1:
                    consumer_control.send(ConsumerControlCode.VOLUME_INCREMENT)
                    print("Volume UP")
                else:
                    consumer_control.send(ConsumerControlCode.VOLUME_DECREMENT)
                    print("Volume DOWN")
            enc.last_dir = direction
            enc.last_time = now
    
    enc.last_encoded = encoded

def process_button_mute(btn, gpio, pin):
    """Process button 1 as HID mute toggle"""
    state = bool((gpio >> pin) & 1)
    if state != btn.last_state:
        btn.last_state = state
        if not state:  # LOW=pressed
            if consumer_control:
                consumer_control.send(ConsumerControlCode.MUTE)
                print("MUTE Toggle")

def auto_scan_midi_mappings():
    """Send CC89 to trigger Ableton scanner (reads .als file, no oscillation needed)"""
    print("Triggering MIDI map scan...")
    
    # Flash LED blue
    rgb[0] = (0, 0, 255)
    
    # Send CC89 once - scanner reads .als file directly
    midi.send(ControlChange(89, 127))
    
    # Brief LED feedback
    time.sleep(0.1)
    rgb[0] = (0, 255, 0)  # Green = done
    time.sleep(0.1)
    rgb[0] = (0, 0, 0)  # Off
    
    print("Scan triggered (check Ableton log)")

# Setup interrupt pins
print("Setting up interrupt pins...")
int_u2 = digitalio.DigitalInOut(board.D6)   # U2 INT -> P0/D6/TX (pin 7)
int_u2.direction = digitalio.Direction.INPUT
int_u2.pull = digitalio.Pull.UP

int_u3 = digitalio.DigitalInOut(board.D2)   # U3 INT -> P28/A2/D2 (pin 3)
int_u3.direction = digitalio.Direction.INPUT
int_u3.pull = digitalio.Pull.UP

int_u4 = digitalio.DigitalInOut(board.D0)   # U4 INT -> P26/A0/D0 (pin 1)
int_u4.direction = digitalio.Direction.INPUT
int_u4.pull = digitalio.Pull.UP

int_u5 = digitalio.DigitalInOut(board.D1)   # U5 INT -> P27/A1/D1 (pin 2)
int_u5.direction = digitalio.Direction.INPUT
int_u5.pull = digitalio.Pull.UP

# Configure all MCP23008 chips
print("Initializing MCP23008 chips...")
for addr in [U2_ADDR, U3_ADDR, U4_ADDR, U5_ADDR]:
    write_reg(addr, MCP_IODIR, 0xFF)     # All inputs
    write_reg(addr, MCP_GPPU, 0xFF)      # All pullups enabled
    write_reg(addr, MCP_GPINTEN, 0xFF)   # Enable interrupt on change for all pins
    # Read GPIO to clear any pending interrupts
    read_reg(addr, MCP_GPIO)

# Read initial states for all encoders
gpio_states = {}
for addr in [U2_ADDR, U3_ADDR, U4_ADDR, U5_ADDR]:
    gpio_states[addr] = read_reg(addr, MCP_GPIO)

for i, (chip, pin_a, pin_b, btn_chip, btn_pin, cc_enc, cc_btn) in enumerate(ENCODERS):
    gpio = gpio_states[chip]
    encoders[i].last_encoded = ((gpio >> pin_b) & 1) << 1 | ((gpio >> pin_a) & 1)
    
    btn_gpio = gpio_states[btn_chip]
    buttons[i].last_state = bool((btn_gpio >> btn_pin) & 1)

print("USB MIDI + HID Controller Ready!")
print("Encoder 1: HID Volume/Mute")  
print("Encoders 2-10: MIDI CC71-79")
print("Buttons 2-9: MIDI CC81-88 (virtual encoders, toggle 10<->117)")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

while True:
    # Read all GPIO states with interrupt detection
    interrupt_detected = False
    for chip_addr in [U2_ADDR, U3_ADDR, U4_ADDR, U5_ADDR]:
        intcap = read_reg(chip_addr, MCP_INTCAP)  # Clears interrupt
        if intcap != 0xFF:
            interrupt_detected = True
        gpio_states[chip_addr] = read_reg(chip_addr, MCP_GPIO)
    
    # Process encoders
    for i in range(10):
        gpio_addr, pin_a, pin_b, btn_gpio_addr, btn_pin, cc_num, cc_btn = ENCODERS[i]
        
        # Encoder processing
        if i == 0:
            process_encoder_volume(encoders[i], gpio_states[gpio_addr], pin_a, pin_b)
        elif i == 9:
            process_encoder_relative_127(encoders[i], gpio_states[gpio_addr], pin_a, pin_b, cc_num)
        else:
            process_encoder_relative(encoders[i], gpio_states[gpio_addr], pin_a, pin_b, cc_num)
        
        # Button processing
        btn_state = (gpio_states[btn_gpio_addr] >> btn_pin) & 1
        if btn_state != buttons[i].last_state and not btn_state:  # Button pressed (active low)
            if cc_btn == CC_RESCAN:
                # PERMANENTLY DISABLED - causes crash
                print(f"CC{cc_btn} disabled (use Ableton restart for fresh scan)")
            # Button 1 (index 0) is HID mute, others are MIDI
            elif i == 0:
                process_button_mute(buttons[i], btn_gpio_addr, btn_pin)
            else:
                process_button(buttons[i], btn_gpio_addr, btn_pin, cc_btn)
            buttons[i].last_state = btn_state
    
    # No sleep - run loop as fast as possible to catch fast encoder turns
print("Button 10: CC89 (rescan)")
print("Interrupt-driven mode: U2(D6), U3(D2), U4(D0), U5(D1)")

# Main loop - fully interrupt-driven
while True:
    # Check each interrupt pin (active LOW)
    if not int_u2.value:  # U2 interrupt triggered
        gpio_states[U2_ADDR] = read_reg(U2_ADDR, MCP_GPIO)
    
    if not int_u3.value:  # U3 interrupt triggered
        gpio_states[U3_ADDR] = read_reg(U3_ADDR, MCP_GPIO)
    
    if not int_u4.value:  # U4 interrupt triggered
        gpio_states[U4_ADDR] = read_reg(U4_ADDR, MCP_GPIO)
    
    if not int_u5.value:  # U5 interrupt triggered
        gpio_states[U5_ADDR] = read_reg(U5_ADDR, MCP_GPIO)
    
    # Process all encoders and buttons
    for i, (chip, pin_a, pin_b, btn_chip, btn_pin, cc_enc, cc_btn) in enumerate(ENCODERS):
        gpio = gpio_states[chip]
        
        # Encoder 1 (index 0) is HID volume control
        # Encoder 10 (index 9) sends 1/127 relative for Live_Track_Controller track selection
        # Encoders 2-9 send 66/62 relative (Binary Offset) for Ableton MIDI mapping
        if i == 0:
            process_encoder_volume(encoders[i], gpio, pin_a, pin_b)
        elif i == 9:
            process_encoder_relative_127(encoders[i], gpio, pin_a, pin_b, cc_enc)
        else:
            process_encoder_relative(encoders[i], gpio, pin_a, pin_b, cc_enc)
        
        btn_gpio = gpio_states[btn_chip]

        # Button 10 (index 9): rescan button - triggers AUTO-SCAN
        if i == 9:
            state = bool((btn_gpio >> btn_pin) & 1)
            if state != buttons[i].last_state:
                buttons[i].last_state = state
                if not state:  # press only
                    # Trigger auto-scan mode
                    auto_scan_midi_mappings()
                    print(f"CC{cc_btn} Auto-scan triggered")
        # Button 1 (index 0) is HID mute, others are MIDI
        elif i == 0:
            process_button_mute(buttons[i], btn_gpio, btn_pin)
        else:
            process_button(buttons[i], btn_gpio, btn_pin, cc_btn)
    
    time.sleep(0.0001)  # 100us - very responsive, CPU mostly idle
