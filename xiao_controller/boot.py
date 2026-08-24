import usb_midi
import usb_cdc
import storage
import usb_hid

# Enable MIDI (keep default ports)
# This is already enabled by default, but we're explicit to be safe

# Enable HID for volume control (encoder 1)
usb_hid.enable((usb_hid.Device.CONSUMER_CONTROL,))

# Keep serial console enabled for debugging
usb_cdc.enable(console=True, data=False)

# Keep CIRCUITPY writable from Windows host
# (readonly=True for the MCU side makes USB host writes available)
storage.remount("/", readonly=True)
