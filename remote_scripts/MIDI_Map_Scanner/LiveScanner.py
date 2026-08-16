# Live MIDI Mapping Detector
# Instead of parsing XML, this directly queries Live's parameter state

def scan_track_midi_mappings(track, track_idx):
    """
    Scan all parameters on a track and attempt to detect MIDI mappings.
    Returns a list of mappings with actual Live parameter names.
    """
    mappings = []
    
    if not track or not hasattr(track, 'devices'):
        return mappings
    
    # Check mixer device first
    if hasattr(track, 'mixer_device'):
        mixer = track.mixer_device
        if hasattr(mixer, 'volume'):
            # Volume parameter
            mappings.append({
                'device': mixer,
                'device_name': 'Mixer',
                'device_class': 'MixerDevice',
                'device_index': -1,
                'param': mixer.volume,
                'param_name': mixer.volume.name,
                'param_original_name': mixer.volume.original_name if hasattr(mixer.volume, 'original_name') else mixer.volume.name,
                'param_index': -1,  # Mixer params don't have index
            })
    
    # Iterate through all devices
    for dev_idx, device in enumerate(track.devices):
        if not hasattr(device, 'parameters'):
            continue
        
        device_name = device.name if hasattr(device, 'name') else 'Unknown'
        device_class = device.class_name if hasattr(device, 'class_name') else type(device).__name__
        
        # Get all parameters with their indices
        for param_idx, param in enumerate(device.parameters):
            if not param:
                continue
            
            param_name = param.name if hasattr(param, 'name') else 'Unknown'
            param_original = param.original_name if hasattr(param, 'original_name') else param_name
            
            mappings.append({
                'device': device,
                'device_name': device_name,
                'device_class': device_class,
                'device_index': dev_idx,
                'param': param,
                'param_name': param_name,
                'param_original_name': param_original,
                'param_index': param_idx,
            })
    
    return mappings


def log_all_track_parameters(track, track_idx, log_func):
    """Log all parameters on a track for debugging"""
    mappings = scan_track_midi_mappings(track, track_idx)
    
    log_func('=' * 60)
    log_func('Track %d: %s' % (track_idx, track.name if hasattr(track, 'name') else 'Unknown'))
    log_func('Total parameters found: %d' % len(mappings))
    log_func('=' * 60)
    
    for m in mappings:
        log_func('[Dev %d] %s (%s) | [Param %d] %s (orig: %s)' % (
            m['device_index'],
            m['device_name'],
            m['device_class'],
            m['param_index'],
            m['param_name'],
            m['param_original_name']
        ))
