"""MIDIverge aftertouch and wheel controller for the dedicated XIAO RP2040.

Target UID: 4250305539333102; CircuitPython 10.3.1.
A0 / GP26: existing aftertouch pressure sensor.
A2 / GP28: pitch wheel, sent as MIDI pitch bend.
A1 / GP27: modulation wheel, sent as MIDI CC1.
"""

import time

import analogio
import board
import usb_midi


MIDI_CHANNEL = 1

AFTERTOUCH_RELEASED_RAW = 65140
AFTERTOUCH_DEAD_ZONE_RAW = 1200
AFTERTOUCH_FULL_PRESSURE_RAW = 11875

# Initial endpoints: pitch is now connected to A2; modulation is on A1.
PITCH_MIN_RAW = 21137
PITCH_MAX_RAW = 44660
MODULATION_MIN_RAW = 21785
MODULATION_MAX_RAW = 44976

PITCH_CENTER_RAW = (PITCH_MIN_RAW + PITCH_MAX_RAW) // 2
PITCH_CENTER_DEAD_ZONE_RAW = 100
PITCH_SMOOTHING = 0.25
CONTROL_SMOOTHING = 0.25
SAMPLE_INTERVAL = 0.005
AFTERTOUCH_REFRESH_INTERVAL = 1.0
CONTROL_REFRESH_INTERVAL = 0.1


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def pressure_to_midi(raw):
    onset = AFTERTOUCH_RELEASED_RAW - AFTERTOUCH_DEAD_ZONE_RAW
    if AFTERTOUCH_FULL_PRESSURE_RAW >= onset:
        raise ValueError("Invalid aftertouch calibration")
    pressure = round(
        (onset - raw) * 127 / (onset - AFTERTOUCH_FULL_PRESSURE_RAW)
    )
    return clamp(pressure, 0, 127)


def modulation_to_midi(raw):
    if MODULATION_MAX_RAW <= MODULATION_MIN_RAW:
        raise ValueError("Invalid modulation wheel calibration")
    return clamp(
        round((MODULATION_MAX_RAW - raw) * 127 /
              (MODULATION_MAX_RAW - MODULATION_MIN_RAW)),
        0,
        127,
    )


def pitch_to_midi(raw):
    if not PITCH_MIN_RAW < PITCH_CENTER_RAW < PITCH_MAX_RAW:
        raise ValueError("Invalid pitch wheel calibration")
    # Reverse the physical wheel direction while keeping center at 8192.
    raw = PITCH_MIN_RAW + PITCH_MAX_RAW - raw
    if abs(raw - PITCH_CENTER_RAW) <= PITCH_CENTER_DEAD_ZONE_RAW:
        return 8192
    if raw < PITCH_CENTER_RAW:
        value = round((raw - PITCH_MIN_RAW) * 8192 /
                      (PITCH_CENTER_RAW - PITCH_MIN_RAW))
    else:
        value = 8192 + round((raw - PITCH_CENTER_RAW) * 8191 /
                             (PITCH_MAX_RAW - PITCH_CENTER_RAW))
    return clamp(value, 0, 16383)


def send_channel_pressure(midi_out, value):
    midi_out.write(bytearray((0xD0 | (MIDI_CHANNEL - 1), value)))


def send_pitch_bend(midi_out, value):
    midi_out.write(bytearray((
        0xE0 | (MIDI_CHANNEL - 1),
        value & 0x7F,
        (value >> 7) & 0x7F,
    )))


def send_modulation(midi_out, value):
    midi_out.write(bytearray((0xB0 | (MIDI_CHANNEL - 1), 1, value)))


def run_controller():
    if not 1 <= MIDI_CHANNEL <= 16:
        raise ValueError("MIDI channel must be 1 through 16")

    sensors = [
        analogio.AnalogIn(board.A0),
        analogio.AnalogIn(board.A2),
        analogio.AnalogIn(board.A1),
    ]
    midi_out = usb_midi.ports[1]
    aftertouch, pitch_wheel, modulation_wheel = sensors

    filtered_aftertouch = sum(aftertouch.value for sample in range(32)) / 32
    filtered_pitch = sum(pitch_wheel.value for sample in range(32)) / 32
    filtered_modulation = sum(modulation_wheel.value for sample in range(32)) / 32

    last_pressure = 0
    last_pitch = 8192
    last_modulation = modulation_to_midi(filtered_modulation)
    now = time.monotonic()
    last_aftertouch_send = now
    last_pitch_send = now
    last_modulation_send = now
    last_log = now

    send_channel_pressure(midi_out, 0)
    send_pitch_bend(midi_out, 8192)
    send_modulation(midi_out, last_modulation)

    print("MIDIverge AFTERTOUCH + WHEELS, MIDI channel", MIDI_CHANNEL)
    print("A0 aftertouch; A2 pitch bend; A1 modulation CC1")
    print("Initial wheel calibration:", PITCH_MIN_RAW, PITCH_CENTER_RAW,
          PITCH_MAX_RAW, MODULATION_MIN_RAW, MODULATION_MAX_RAW)

    try:
        while True:
            raw_pressure = sum(aftertouch.value for sample in range(8)) / 8
            raw_pitch = sum(pitch_wheel.value for sample in range(8)) / 8
            raw_modulation = sum(modulation_wheel.value for sample in range(8)) / 8

            filtered_aftertouch += 0.25 * (raw_pressure - filtered_aftertouch)
            filtered_pitch += PITCH_SMOOTHING * (raw_pitch - filtered_pitch)
            filtered_modulation += CONTROL_SMOOTHING * (
                raw_modulation - filtered_modulation
            )

            if raw_pressure >= AFTERTOUCH_RELEASED_RAW - AFTERTOUCH_DEAD_ZONE_RAW:
                pressure = 0
                filtered_aftertouch = raw_pressure
            else:
                pressure = pressure_to_midi(filtered_aftertouch)

            pitch = pitch_to_midi(filtered_pitch)
            modulation = modulation_to_midi(filtered_modulation)
            now = time.monotonic()

            if (abs(pressure - last_pressure) >= 2 or
                    (pressure == 0 and last_pressure != 0) or
                    now - last_aftertouch_send >= AFTERTOUCH_REFRESH_INTERVAL):
                send_channel_pressure(midi_out, pressure)
                last_pressure = pressure
                last_aftertouch_send = now

            pitch_endpoint_changed = (
                pitch in (0, 16383) and pitch != last_pitch
            )
            if (abs(pitch - last_pitch) >= 8 or pitch_endpoint_changed or
                    now - last_pitch_send >= CONTROL_REFRESH_INTERVAL):
                send_pitch_bend(midi_out, pitch)
                last_pitch = pitch
                last_pitch_send = now

            if (abs(modulation - last_modulation) >= 1 or
                    now - last_modulation_send >= CONTROL_REFRESH_INTERVAL):
                send_modulation(midi_out, modulation)
                last_modulation = modulation
                last_modulation_send = now

            if now - last_log >= 0.2:
                print("A0=%5d AT=%3d | A2=%5d PB=%5d | A1=%5d CC1=%3d" % (
                    raw_pressure, pressure,
                    raw_pitch, pitch,
                    raw_modulation, modulation,
                ))
                last_log = now

            time.sleep(SAMPLE_INTERVAL)
    finally:
        send_channel_pressure(midi_out, 0)
        send_pitch_bend(midi_out, 8192)
        for sensor in sensors:
            sensor.deinit()


if __name__ == "__main__":
    run_controller()