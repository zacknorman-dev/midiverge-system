# KeyLab mk3 bytecode analysis
# Constants and names extracted from .pyc files


======================================================================
FILE: elements.pyc
======================================================================

Module names: ('functools', 'partial', 'ableton.v3.control_surface', 'MIDI_NOTE_TYPE', 'ElementsBase', 'MapMode', 'create_button', 'create_encoder', 'create_matrix_identifiers', 'create_sysex_sending_button', 'ableton.v3.control_surface.elements', 'CachingSendMessageGenerator', 'DisplayLineElement', 'TouchElement', '', 'midi', 'display', 'Line1Text', 'Line2Text', 'ScreenId', 'create_rgb_button', 'create_rgb_pad', 'create_continuous_control', 'Elements')

Constants (first level):
  0
  1
  [Code object: create_rgb_button]
    - Args: ('identifier', 'name')
    - Names used: ('create_sysex_sending_button', 'midi', 'LED_HEADER', 'BUTTON_ID_TO_SYSEX_ID')
    - Constants: ['is_rgb', True]
  [Code object: create_rgb_pad]
    - Args: ('identifier', 'name')
    - Names used: ('create_sysex_sending_button', 'midi', 'LED_HEADER', 'PAD_ID_TO_SYSEX_ID', 'MIDI_NOTE_TYPE')
    - Constants: [True]
  [Code object: create_continuous_control]
    - Args: ('identifier', 'name')
    - Names used: ('create_encoder', 'MapMode', 'Absolute', 'LinearBinaryOffset')
    - Constants: ['map_mode', 105]
  [Code object: Elements]
  'Elements'


======================================================================
FILE: midi.pyc
======================================================================

Module names: ('ableton.v3.control_surface.midi', 'SYSEX_END', 'SYSEX_START', 'display', 'BUTTON_TYPES', 'Color', 'Icon', 'ScreenId', 'SYSEX_HEADER', 'LED_HEADER', 'DISPLAY_HEADER', 'make_connection_message', 'CONNECTION_MESSAGE', 'DISCONNECTION_MESSAGE', 'BUTTON_ID_TO_SYSEX_ID', 'PAD_ID_TO_SYSEX_ID', 'ENCODER_TOUCH_IDS', 'FADER_TOUCH_IDS', 'make_parameter_screen', 'WHITE', 'NONE', 'make_button_segment', 'make_two_line_screen', 'make_popup_screen', 'make_line_bytes')

Constants (first level):
  0
  1
  32
  107
  127
  66
  [Code object: <lambda>]
  7
  6
  5
  4
  8
  9
  10
  11
  15
  14
  13
  12
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  [Code object: make_parameter_screen]
  'icon'
  [Code object: make_button_segment]
  [Code object: make_two_line_screen]
  [Code object: make_popup_screen]
  [Code object: make_line_bytes]


======================================================================
FILE: mappings.pyc
======================================================================

Module names: ('ableton.v3.control_surface.mode', 'ImmediateBehaviour', 'create_mappings')

Constants (first level):
  0
  [Code object: create_mappings]
    - Args: ('_',)
    - Names used: ('dict', 'ImmediateBehaviour')
    - Constants: ['play_button', 'stop_button', 'metronome_button', 'loop_button', 'tap_button', 'rewind_button', 'fastforward_button', 'save_button', 'Transport', 'record_button', 'View_Based_Recording', 'undo_button', 'redo_button', 'Undo_Redo', 'quantize_button', 'Clip_Actions', 'context_button_2', 'context_button_3', 'display_encoder', 'View_Control', 'context_button_4', 'context_button_5', 'context_button_6', 'fader_8', 'encoder_8', 'Mixer', 'pads', 'Session', 'context_button_7', 'Scene_Launch', 'parameter_touch_elements', 'Active_Parameter', 'context_button_0', 'context_button_1', 'Mode_Buttons', 'Device', 'continuous_controls', 'Device_Navigation', 'display_encoder_with_context_button_0', 'faders', 'encoders', 'display_encoder_with_context_button_1', 'Continuous_Control_Modes']

