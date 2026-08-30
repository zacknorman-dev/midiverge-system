"""
Ableton MIDI Overlay - Simple Real-Time Display
Shows 8 encoders (CC71-78) with parameter names and values
"""

import tkinter as tk
import threading
import json
import os
import socket
import ctypes

# Make application DPI-aware
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass


class MIDIOverlay:
    def __init__(self, root):
        self.root = root
        self.root.title("Ableton MIDI Overlay")
        
        # Window configuration - fixed 2560x102, always on top
        self.root.geometry("2560x102")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)
        self.root.configure(bg='#000000')
        
        # Position at bottom of screen
        self.position_window_bottom()
        
        # State
        self.current_track = "No Track"
        self.scanner_file = r"C:\Users\zackn\Documents\midi overlay\current_scan.json"
        self.cc_mappings = {}  # {cc: {'param_name': str, 'device_name': str}}
        
        # UI elements
        self.track_label = None
        self.label_widgets = []  # Parameter name labels
        self.value_labels = []   # Value text items
        self.progress_bars = []  # Progress bar rectangles
        
        # Create UI
        self.create_ui()
        
        # Load initial mappings
        self.load_mappings()
        
        # Start UDP listener for Ableton updates
        self.running = True
        self.udp_socket = None
        self.udp_thread = None
        self.start_udp_listener()
        
        print("MIDI Overlay started - waiting for Ableton updates...")
    
    def position_window_bottom(self):
        """Position window at bottom center of screen"""
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width - 2560) // 2
        y = screen_height - 102 - 40
        
        self.root.geometry(f"2560x102+{x}+{y}")
    
    def load_mappings(self):
        """Load CC71-78 mappings for current track from JSON"""
        # Clear old mappings
        self.cc_mappings = {}
        
        if not os.path.exists(self.scanner_file):
            print(f"Scanner file not found: {self.scanner_file}")
            return
        
        try:
            with open(self.scanner_file, 'r') as f:
                data = json.load(f)
            
            # Find mappings for current track and CC71-78
            for mapping in data.get('mappings', []):
                cc = mapping.get('cc')
                track_name = mapping.get('track_name_live', '')
                
                # Only load if CC is in our range (71-78)
                if 71 <= cc <= 78 and track_name == self.current_track:
                    param_name = mapping.get('param_live_name', 'Unknown')
                    device_name = mapping.get('device_name', '')
                    
                    self.cc_mappings[cc] = {
                        'param_name': param_name,
                        'device_name': device_name
                    }
            
            # Update UI labels
            self.update_labels()
            
        except Exception as e:
            print(f"Error loading mappings: {e}")
    
    def update_labels(self):
        """Update parameter name labels from current mappings"""
        for cc in range(71, 79):
            slot_index = cc - 71
            
            if cc in self.cc_mappings:
                mapping = self.cc_mappings[cc]
                param_name = mapping['param_name']
                device_name = mapping['device_name']
                
                # Format: Device Name\nParam Name (or just param if no device)
                if device_name:
                    label_text = f"{device_name}\n{param_name}"
                else:
                    label_text = param_name
            else:
                # No mapping - show CC number
                label_text = f"CC {cc}"
            
            # Update label widget
            if slot_index < len(self.label_widgets):
                self.label_widgets[slot_index].config(text=label_text)
    
    def create_ui(self):
        """Create the visual overlay - 8 encoders with labels and progress bars"""
        # Colors
        WHITE = '#FFFFFF'
        GRAY_EDGE = '#878787'
        GRAY_HEADER = '#000000'
        DARK_GREEN = '#0a2e0a'
        BRIGHT_GREEN = '#00cc00'
        
        # Track name area (top 48px)
        track_frame = tk.Frame(self.root, bg='#1a1a1a')
        track_frame.place(x=0, y=0, width=2560, height=48)
        
        self.track_label = tk.Label(
            track_frame,
            text=self.current_track,
            bg='#1a1a1a',
            fg='#00ddff',
            font=('Arial', 19),
            anchor='e'
        )
        self.track_label.place(x=1750, y=0, width=800, height=48)
        
        # White background
        tk.Frame(self.root, bg=WHITE).place(x=0, y=48, width=2560, height=54)
        
        # Gray edge lines
        tk.Frame(self.root, bg=GRAY_EDGE).place(x=0, y=52, width=2560, height=1)
        tk.Frame(self.root, bg=GRAY_EDGE).place(x=0, y=95, width=2560, height=1)
        
        # 8 encoder sections (CC71-78)
        encoder_x_positions = [5, 325, 645, 965, 1285, 1605, 1925, 2245]
        
        for i, x in enumerate(encoder_x_positions):
            # White divider before this encoder (except first)
            if i > 0:
                tk.Frame(self.root, bg=WHITE).place(x=x-10, y=53, width=10, height=41)
            
            # LEFT: Gray area with parameter name label
            gray_area = tk.Frame(self.root, bg=GRAY_HEADER)
            gray_area.place(x=x, y=53, width=200, height=41)
            
            label = tk.Label(
                gray_area,
                text=f"CC {71+i}",
                bg=GRAY_HEADER,
                fg=WHITE,
                font=('Arial', 12),
                anchor='w'
            )
            label.place(x=5, y=0, width=190, height=41)
            self.label_widgets.append(label)
            
            # RIGHT: Progress bar with value text
            bar_x = x + 200
            bar_width = 110
            
            canvas = tk.Canvas(
                self.root,
                width=bar_width,
                height=41,
                bg=WHITE,
                highlightthickness=0
            )
            canvas.place(x=bar_x, y=53)
            
            # Dark green background (unfilled)
            canvas.create_rectangle(0, 0, bar_width, 41, fill=DARK_GREEN, outline='')
            
            # Bright green overlay (filled - starts at 0 width)
            bright_rect = canvas.create_rectangle(0, 0, 0, 41, fill=BRIGHT_GREEN, outline='')
            
            # Value text on top
            text_item = canvas.create_text(
                bar_width - 5, 20,
                text="--",
                fill=WHITE,
                font=('Arial', 12, 'bold'),
                anchor='e'
            )
            
            # Store for updates
            self.progress_bars.append((canvas, bright_rect, bar_width))
            self.value_labels.append((canvas, text_item))
    
    def update_value_display(self, slot_index, value_str, normalized_value):
        """Update value text and progress bar for an encoder"""
        if slot_index < 0 or slot_index >= 8:
            return
        
        # Update value text
        canvas, text_item = self.value_labels[slot_index]
        canvas.itemconfig(text_item, text=value_str)
        
        # Update progress bar width (normalized_value is 0.0 to 1.0)
        canvas, bright_rect, bar_width = self.progress_bars[slot_index]
        filled_width = int(bar_width * normalized_value)
        canvas.coords(bright_rect, 0, 0, filled_width, 41)
    
    def start_udp_listener(self):
        """Start UDP listener for Ableton messages"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('127.0.0.1', 9001))
            self.udp_socket.settimeout(0.1)
            
            self.udp_thread = threading.Thread(target=self.udp_listener_thread, daemon=True)
            self.udp_thread.start()
            
            print("Listening on UDP port 9001 for Ableton updates")
        except Exception as e:
            print(f"Could not start UDP listener: {e}")
    
    def udp_listener_thread(self):
        """Listen for UDP messages from Ableton"""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(65536)
                message = json.loads(data.decode('utf-8'))
                self.root.after(0, self.handle_message, message)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP listener error: {e}")
                break
    
    def handle_message(self, message):
        """Handle messages from Ableton"""
        msg_type = message.get('type')
        
        if msg_type == 'track_changed':
            # Track selection changed - update current track and reload mappings
            track_name = message.get('track_name', 'Unknown Track')
            self.current_track = track_name
            self.track_label.config(text=track_name)
            
            # Reload mappings for new track
            self.load_mappings()
            
            # Clear value displays
            for i in range(8):
                self.update_value_display(i, "--", 0.0)
            
            print(f"Track changed: {track_name}")
        
        elif msg_type == 'parameter_changed':
            # Parameter value changed - update display
            cc = message.get('cc')
            
            if cc is None or cc < 71 or cc > 78:
                return  # Ignore CCs outside our range
            
            slot_index = cc - 71
            param_str = message.get('param_str', '--')
            param_value = message.get('param_value', 0.0)
            
            # Update display for this encoder
            self.update_value_display(slot_index, param_str, param_value)
    
    def cleanup(self):
        """Cleanup on exit"""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()


if __name__ == '__main__':
    root = tk.Tk()
    app = MIDIOverlay(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()((canvas, bright_rect, bar_width))
            self.value_labels.append((canvas, text_item))
            self.progress_bars.append((canvas, bright_rect))
            self.value_labels.append((canvas, text_item))
    
    def edit_label(self, idx):
        """Allow user to double-click and edit custom encoder label"""
        if not self.current_track or self.current_track not in self.track_mappings:
            return
        
        cc = 71 + idx
        mapping_info = self.track_mappings[self.current_track].get(cc, {})
        current_label = mapping_info.get('custom_label', '')
        param_name = mapping_info.get('param_name', '')
        
        # Don't allow editing unmapped parameters
        if not param_name:
            print(f"Cannot edit label for unmapped parameter CC{71+idx}. Use MIDI learn first.")
            return
        
        # Create simple popup entry dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Custom Label - {self.current_track}")
        dialog.geometry("400x120")
        dialog.attributes('-topmost', True)
        dialog.configure(bg='#2a2a2a')
        
        # Show original parameter name
        info_label = tk.Label(
            dialog,
            text=f"Parameter: {param_name}",
            bg='#2a2a2a',
            fg='#888888',
            font=('Arial', 9)
        )
        info_label.pack(pady=(10, 0))
        
        entry = tk.Entry(dialog, font=('Arial', 12), width=35)
        entry.insert(0, current_label)
        entry.pack(pady=10, padx=10)
        entry.focus()
        entry.select_range(0, tk.END)
        
        def save_label():
            new_label = entry.get().strip()
            if new_label:
                # Save custom_label to JSON file (will reload mappings automatically)
                self.save_custom_label_to_json(self.current_track, idx, new_label)
                print(f"Saved custom label '{new_label}' for {self.current_track} CC{71+idx}")
            dialog.destroy()
        
        entry.bind('<Return>', lambda e: save_label())
        entry.bind('<Escape>', lambda e: dialog.destroy())
    
    def save_custom_label_to_json(self, track_name, encoder_idx, custom_label):
        """Save custom_label to the scanner JSON file and reload mappings"""
        try:
            if not os.path.exists(self.scanner_file):
                print(f"Cannot save custom label: scanner file not found")
                return False
            
            # Load current JSON
            with open(self.scanner_file, 'r') as f:
                data = json.load(f)
            
            # Find matching mapping and update custom_label
            cc = 71 + encoder_idx
            updated = False
            for mapping in data.get('mappings', []):
                if mapping.get('track_name_live') == track_name and mapping.get('cc') == cc:
                    mapping['custom_label'] = custom_label
                    updated = True
                    break
            
            if updated:
                # Write back to JSON file
                with open(self.scanner_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Reload mappings to reflect change
                self.load_ableton_mappings()
                if self.current_track:
                    self.select_track(self.current_track)
                
                print(f"Saved custom_label to scanner JSON")
                print(f"  Track: {track_name}, CC: {cc}, Label: '{custom_label}'")
                return True
            else:
                print(f"Warning: Could not find mapping for {track_name} CC{cc} in JSON")
                return False
                
        except Exception as e:
            print(f"Error saving custom label: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def show_management_window(self, encoder_idx):
        """Show management window for encoder configuration"""
        if not self.current_track:
            return
        
        cc = 71 + encoder_idx
        
        # Allow management window even if not in track_mappings (for broken/blank CCs)
        if self.current_track not in self.track_mappings:
            self.track_mappings[self.current_track] = {}
        
        if cc not in self.track_mappings[self.current_track]:
            # Create a placeholder for broken CCs
            self.track_mappings[self.current_track][cc] = {
                'param_name': '',
                'custom_label': '',
                'device_class_name': '',
                'param_tag': ''
            }
        
        mapping_info = self.track_mappings[self.current_track][cc]
        param_name = mapping_info.get('param_name', '')
        custom_label = mapping_info.get('custom_label', '')
        device_class_name = mapping_info.get('device_class_name', '')
        param_tag = mapping_info.get('param_tag', '')
        
        # Determine display label
        display_label = custom_label if custom_label else (param_name if param_name else f"CC {cc}")
        
        # Create management dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Manage Encoder {encoder_idx + 1}")
        dialog.geometry("400x260")
        dialog.attributes('-topmost', True)
        dialog.configure(bg='#2a2a2a')
        
        # Info section
        info_frame = tk.Frame(dialog, bg='#2a2a2a')
        info_frame.pack(pady=10, padx=10, fill='x')
        
        tk.Label(
            info_frame,
            text=f"CC {cc} - {display_label}",
            bg='#2a2a2a',
            fg='#00ddff',
            font=('Arial', 12, 'bold')
        ).pack(anchor='w')
        
        if device_class_name:
            tk.Label(
                info_frame,
                text=f"Device: {device_class_name}",
                bg='#2a2a2a',
                fg='#888888',
                font=('Arial', 9)
            ).pack(anchor='w')
        
        if param_tag:
            tk.Label(
                info_frame,
                text=f"Parameter: {param_tag}",
                bg='#2a2a2a',
                fg='#888888',
                font=('Arial', 9)
            ).pack(anchor='w')
        
        # Button frame
        button_frame = tk.Frame(dialog, bg='#2a2a2a')
        button_frame.pack(pady=10, padx=10, fill='both', expand=True)
        
        # Row 1: Rename and Default Name
        row1 = tk.Frame(button_frame, bg='#2a2a2a')
        row1.pack(fill='x', pady=5)
        
        rename_btn = tk.Button(
            row1,
            text="Rename...",
            command=lambda: self.manage_rename(encoder_idx, dialog),
            width=18,
            bg='#3a3a3a',
            fg='white',
            font=('Arial', 10),
            state='normal' if param_name else 'disabled'
        )
        rename_btn.pack(side='left', padx=5, expand=True)
        
        default_btn = tk.Button(
            row1,
            text="Default Name",
            command=lambda: self.manage_default_name(encoder_idx, dialog),
            width=18,
            bg='#3a3a3a',
            fg='white',
            font=('Arial', 10),
            state='normal' if custom_label else 'disabled'
        )
        default_btn.pack(side='left', padx=5, expand=True)
        
        # Row 2: Manual Fix button (full width) - ALWAYS enabled
        row2 = tk.Frame(button_frame, bg='#2a2a2a')
        row2.pack(fill='x', pady=5)
        
        learn_btn = tk.Button(
            row2,
            text="Manual Fix (Paste LOM Path)",
            command=lambda: self.manual_fix_mode(encoder_idx, dialog),
            width=38,
            bg='#3a5a3a',  # Green tint
            fg='white',
            font=('Arial', 10, 'bold'),
            state='normal'  # Always enabled, even for blank CCs
        )
        learn_btn.pack(padx=5, expand=True)
        
        # Close button
        close_btn = tk.Button(
            dialog,
            text="Close",
            command=dialog.destroy,
            width=20,
            bg='#3a3a3a',
            fg='white',
            font=('Arial', 10)
        )
        close_btn.pack(pady=10)
    
    def manage_rename(self, encoder_idx, dialog):
        """Trigger rename from management window"""
        dialog.destroy()
        self.edit_label(encoder_idx)
    
    def _extract_device_index(self, lom_path):
        """Extract device index from lom_path like ['devices[0] <Drift>', ...]"""
        import re
        for part in lom_path:
            match = re.search(r'devices\[(\d+)\]', str(part))
            if match:
                return int(match.group(1))
        return 0
    
    def manual_fix_mode(self, encoder_idx, management_dialog):
        """Manual fix by pasting LOM path like 'live_set tracks 4 devices 1 parameters 14'"""
        management_dialog.destroy()
        
        cc = 71 + encoder_idx
        
        # Create input dialog
        input_dialog = tk.Toplevel(self.root)
        input_dialog.title(f"Fix CC{cc} Mapping")
        input_dialog.geometry("500x200")
        input_dialog.attributes('-topmost', True)
        input_dialog.configure(bg='#2a2a2a')
        
        tk.Label(
            input_dialog,
            text=f"Fix CC{cc} Mapping",
            bg='#2a2a2a',
            fg='#00ff00',
            font=('Arial', 14, 'bold')
        ).pack(pady=10)
        
        tk.Label(
            input_dialog,
            text="Paste LOM path from Ableton Log.txt:\n(e.g., 'live_set tracks 4 devices 1 parameters 14')",
            bg='#2a2a2a',
            fg='white',
            font=('Arial', 10)
        ).pack(pady=5)
        
        entry = tk.Entry(input_dialog, width=60, font=('Arial', 10))
        entry.pack(pady=10)
        entry.focus_set()
        
        def apply_fix():
            lom_path = entry.get().strip()
            if not lom_path:
                return
            
            # Parse: "live_set tracks 4 devices 1 parameters 14"
            import re
            match = re.search(r'parameters\s+(\d+)', lom_path)
            if match:
                param_index = int(match.group(1))
                
                # Also get device index
                device_match = re.search(r'devices\s+(\d+)', lom_path)
                device_index = int(device_match.group(1)) if device_match else 1
                
                # Update scanner JSON
                try:
                    with open(self.scanner_file, 'r') as f:
                        data = json.load(f)
                    
                    # Get device class name and device name from existing mappings for this track
                    device_class = None
                    device_name_to_use = None
                    for mapping in data.get('mappings', []):
                        if mapping.get('track_name_live') == self.current_track:
                            # Prefer getting device info from other CCs on same track with same device
                            if mapping.get('device_class_name') and mapping.get('device_name'):
                                device_class = mapping.get('device_class_name')
                                device_name_to_use = mapping.get('device_name')
                                # If this is the exact device_index we're fixing, use this device name
                                mapping_device_idx = self._extract_device_index(mapping.get('lom_path', []))
                                if mapping_device_idx == device_index:
                                    break
                    
                    if not device_class:
                        device_class = 'Drift'
                    if not device_name_to_use:
                        device_name_to_use = device_class
                    
                    found = False
                    for mapping in data.get('mappings', []):
                        if mapping.get('track_name_live') == self.current_track and mapping.get('cc') == cc:
                            mapping['param_index'] = param_index
                            mapping['param_live_name'] = f"Parameter {param_index}"
                            mapping['device_class_name'] = device_class
                            mapping['device_name'] = device_name_to_use
                            mapping['lom_path'] = [
                                f"devices[{device_index}] <{device_class}>",
                                f"param_index[{param_index}]"
                            ]
                            found = True
                            break
                    
                    if not found:
                        # Create new mapping if it doesn't exist
                        data.get('mappings', []).append({
                            'track_index': next((t['track_index'] for t in data.get('tracks', []) if t['track_name_live'] == self.current_track), 0),
                            'track_type': 'MidiTrack',
                            'track_name_xml': '',
                            'track_name_live': self.current_track,
                            'cc': cc,
                            'channel': 0,
                            'param_tag': f'Parameter{param_index}',
                            'param_index': param_index,
                            'param_live_name': f'Parameter {param_index}',
                            'device_class_name': device_class,
                            'device_name': device_class,
                            'device_path': [],
                            'is_mixer_param': False,
                            'lom_path': [
                                f"devices[{device_index}] <{device_class}>",
                                f"param_index[{param_index}]"
                            ]
                        })
                    
                    with open(self.scanner_file, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    input_dialog.destroy()
                    self.load_ableton_mappings()
                    self.select_track(self.current_track)
                    
                    self.show_notification(f"Fixed CC{cc}: param_index[{param_index}]\nReload MIDIOverlay in Ableton!")
                except Exception as e:
                    print(f"Error: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                tk.Label(input_dialog, text="Invalid LOM path format", fg='red', bg='#2a2a2a').pack()
        
        tk.Button(input_dialog, text="Apply Fix", command=apply_fix, width=15, bg='#3a5a3a', fg='white', font=('Arial', 10)).pack(pady=5)
        tk.Button(input_dialog, text="Cancel", command=input_dialog.destroy, width=15, bg='#3a3a3a', fg='white', font=('Arial', 10)).pack()
    
    def start_learn_mode(self, encoder_idx, management_dialog):
        """Enter learn mode to detect correct parameter mapping"""
        if self.learning_mode:
            return  # Already learning
        
        management_dialog.destroy()
        
        cc = 71 + encoder_idx
        
        # Enter learning mode
        self.learning_mode = True
        self.learning_cc = cc
        self.learning_snapshots = {}
        
        # Create learning dialog
        self.learning_dialog = tk.Toplevel(self.root)
        self.learning_dialog.title(f"Learning CC{cc}")
        self.learning_dialog.geometry("400x150")
        self.learning_dialog.attributes('-topmost', True)
        self.learning_dialog.configure(bg='#2a2a2a')
        self.learning_dialog.protocol("WM_DELETE_WINDOW", self.cancel_learn_mode)
        
        tk.Label(
            self.learning_dialog,
            text=f"Learning CC{cc}...",
            bg='#2a2a2a',
            fg='#00ff00',
            font=('Arial', 14, 'bold')
        ).pack(pady=20)
        
        tk.Label(
            self.learning_dialog,
            text="Turn CC71 knob slowly and watch AutoFilter\nparameters in Ableton. Any parameter that\nchanges will be detected and mapped to CC71.",
            bg='#2a2a2a',
            fg='white',
            font=('Arial', 10)
        ).pack(pady=10)
        
        cancel_btn = tk.Button(
            self.learning_dialog,
            text="Cancel",
            command=self.cancel_learn_mode,
            width=15,
            bg='#3a3a3a',
            fg='white',
            font=('Arial', 10)
        )
        cancel_btn.pack(pady=10)
        
        print(f"\n=== LEARN MODE STARTED ===")
        print(f"CC{cc}: Turn the knob to detect the correct parameter")
    
    def cancel_learn_mode(self):
        """Cancel learn mode"""
        try:
            if self.learning_dialog:
                self.learning_dialog.destroy()
                self.learning_dialog = None
        except:
            pass
        
        self.learning_mode = False
        self.learning_cc = None
        self.learning_snapshots = {}
        print("\n=== LEARN MODE CANCELLED ===")
    
    def complete_learn_mode(self, cc, param_index, param_name, device_class_name):
        """Complete learn mode by updating scanner JSON"""
        try:
            # Load scanner JSON
            with open(self.scanner_file, 'r') as f:
                data = json.load(f)
            
            # Find the mapping for this CC and track
            updated = False
            for mapping in data.get('mappings', []):
                if (mapping.get('track_name_live') == self.current_track and 
                    mapping.get('cc') == cc):
                    
                    # Update param_index
                    old_index = mapping.get('param_index', -1)
                    mapping['param_index'] = param_index
                    
                    # Update lom_path to reflect new param_index
                    lom_path = mapping.get('lom_path', [])
                    if lom_path:
                        # Replace the last element (param_index[X]) with new value
                        for i, part in enumerate(lom_path):
                            if part.startswith('param_index['):
                                lom_path[i] = f'param_index[{param_index}]'
                                break
                        mapping['lom_path'] = lom_path
                    
                    print(f"\nUpdated CC{cc} mapping:")
                    print(f"  Track: {self.current_track}")
                    print(f"  Device: {device_class_name}")
                    print(f"  Parameter: {param_name}")
                    print(f"  param_index: {old_index} -> {param_index}")
                    
                    updated = True
                    break
            
            if updated:
                # Write back to JSON
                with open(self.scanner_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Show success notification
                self.show_notification(
                    f"✓ Learned CC{cc}\n"
                    f"Parameter: {param_name}\n"
                    f"Index: {param_index}\n\n"
                    f"Reloading mappings..."
                )
                
                # Reload mappings to reflect change
                self.load_ableton_mappings()
                if self.current_track:
                    self.select_track(self.current_track)
                
                print("\n=== LEARN MODE COMPLETE ===")
                print(f"Scanner JSON updated. Changes will persist.")
            else:
                print(f"\nWARNING: Could not find mapping for CC{cc} on {self.current_track}")
                self.show_notification(f"Error: Could not find mapping for CC{cc}")
        
        except Exception as e:
            print(f"Error updating scanner JSON: {e}")
            import traceback
            traceback.print_exc()
            self.show_notification(f"Error updating scanner JSON: {e}")
        
        finally:
            # Exit learn mode
            if self.learning_dialog:
                self.learning_dialog.destroy()
                self.learning_dialog = None
            self.learning_mode = False
            self.learning_cc = None
            self.learning_snapshots = {}
    
    def manage_default_name(self, encoder_idx, dialog):
        """Remove custom label and restore default name"""
        if not self.current_track or self.current_track not in self.track_mappings:
            dialog.destroy()
            return
        
        cc = 71 + encoder_idx
        mapping_info = self.track_mappings[self.current_track].get(cc, {})
        param_name = mapping_info.get('param_name', '')
        
        if not param_name:
            print(f"Cannot reset name for unmapped parameter")
            dialog.destroy()
            return
        
        # Remove custom_label from JSON
        try:
            if not os.path.exists(self.scanner_file):
                print(f"Cannot reset name: scanner file not found")
                dialog.destroy()
                return
            
            # Load current JSON
            with open(self.scanner_file, 'r') as f:
                data = json.load(f)
            
            # Find matching mapping and remove custom_label
            cc = 71 + encoder_idx
            updated = False
            for mapping in data.get('mappings', []):
                if mapping.get('track_name_live') == self.current_track and mapping.get('cc') == cc:
                    if 'custom_label' in mapping:
                        del mapping['custom_label']
                        updated = True
                    break
            
            if updated:
                # Write back to JSON file
                with open(self.scanner_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Reload mappings to reflect change
                self.load_ableton_mappings()
                if self.current_track:
                    self.select_track(self.current_track)
                
                print(f"Restored default name: {param_name}")
            
        except Exception as e:
            print(f"Error restoring default name: {e}")
            import traceback
            traceback.print_exc()
        
        dialog.destroy()
    
    def show_notification(self, message):
        """Show temporary notification overlay"""
        notif = tk.Toplevel(self.root)
        notif.title("")
        notif.geometry("500x80")
        notif.attributes('-topmost', True)
        notif.configure(bg='#2a2a2a')
        notif.overrideredirect(True)  # No window decorations
        
        # Center on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 500) // 2
        y = (screen_height - 80) // 2
        notif.geometry(f"500x80+{x}+{y}")
        
        tk.Label(
            notif,
            text=message,
            bg='#2a2a2a',
            fg='#00ff00',
            font=('Arial', 12, 'bold'),
            wraplength=480
        ).pack(expand=True)
        
        # Auto-close after 3 seconds
        notif.after(3000, notif.destroy)
    
    def update_track_display(self, track_name):
        """Update the current track name display"""
        self.current_track = track_name
        if self.track_label:
            self.track_label.config(text=track_name)
        # TODO: Load track-specific encoder mappings and labels
        # For now, this is a placeholder for future Ableton Live integration
        
    def setup_ableton_listener(self):
        """Setup UDP listener for Ableton Remote Script messages"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('127.0.0.1', 9001))
            self.udp_socket.settimeout(0.1)  # Non-blocking with timeout
            
            # Start listener thread
            self.udp_thread = threading.Thread(target=self.ableton_listener_thread, daemon=True)
            self.udp_thread.start()
            
            print("\nListening for Ableton Remote Script on UDP port 9001")
            print("   To enable: Preferences > MIDI > Control Surface > 'MIDIOverlay'\n")
            
        except Exception as e:
            print(f"Could not start Ableton listener: {e}")
    
    def ableton_listener_thread(self):
        """Listen for UDP messages from Ableton"""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(65536)
                message = json.loads(data.decode('utf-8'))
                self.root.after(0, self.handle_ableton_message, message)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:  # Only log if we're not shutting down
                    print(f"Ableton listener error: {e}")
                break
    
    def handle_ableton_message(self, message):
        """Handle messages from Ableton Remote Script"""
        msg_type = message.get('type')
        
        # Log all incoming messages to file
        try:
            with open(r"C:\Users\zackn\Documents\midi overlay\overlay_received.log", 'a') as f:
                import time
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                cc = message.get('cc', 'NONE')
                param = message.get('param_name', 'N/A')
                f.write(f"[{timestamp}] type={msg_type}, cc={cc}, param={param}\n")
                f.flush()
        except:
            pass  # Silent fail
        
        if msg_type == 'status':
            print(f"[Ableton] {message.get('message')}")
        
        elif msg_type == 'track_changed':
            track_name = message.get('track_name')
            print(f"\n[Ableton] Track selected: {track_name}")
            
            # Update display for this track
            self.select_track(track_name)
        
        elif msg_type == 'parameter_changed':
            # Get CC number - this is now the primary identifier
            cc = message.get('cc')
            
            # Check if we're in learn mode - accept ANY parameter change during learning
            if self.learning_mode and self.learning_cc is not None:
                param_index = message.get('param_index', -1)
                param_name = message.get('param_name', 'Unknown')
                device_name = message.get('device_name', '')
                
                # Learn mode active - checking parameter
                
                # Extract device class from lom_path
                lom_path = message.get('lom_path', '')
                device_class_name = ''
                if lom_path and '<' in lom_path and '>' in lom_path:
                    import re
                    match = re.search(r'<([^>]+)>', lom_path)
                    if match:
                        device_class_name = match.group(1)
                
                if param_index >= 0:
                    print(f"\n=== PARAMETER DETECTED ===")
                    print(f"CC{cc} -> {param_name} (param_index[{param_index}])")
                    print(f"Device: {device_class_name}")
                    
                    # Map this parameter to the CC we're learning
                    self.complete_learn_mode(self.learning_cc, param_index, param_name, device_class_name)
                    return
                # else: param_index invalid, cannot learn
            
            if cc is None or cc < 71 or cc > 78:
                return  # Ignore parameters without CC or outside encoder range
            
            # Direct mapping: CC71 → slot 0, CC72 → slot 1, etc.
            slot_index = cc - 71
            
            param_name = message.get('param_name', 'Unknown')
            param_str = message.get('param_str', '0')
            param_value = message.get('param_value', 0.0)
            
            # Update display
            self.update_value_display(slot_index, param_str, param_value)
    
    def update_displays_from_ableton(self):
        """Update all encoder displays with Ableton parameter values"""
        if not self.current_track or self.current_track not in self.track_mappings:
            return
        
        for encoder_idx in range(8):
            if encoder_idx not in self.track_mappings[self.current_track]:
                continue
                
            mapping_info = self.track_mappings[self.current_track][encoder_idx]
            label = mapping_info['label']
            
            # Skip empty slots
            if label == "--":
                continue
            
            # Get device and param name for cache lookup
            device_name = mapping_info.get('device_name', '')
            param_name = mapping_info.get('param_name', '')
            cache_key = f"{device_name}:{param_name}"
            
            # Check if we have this parameter in cache
            if cache_key in self.ableton_parameter_cache:
                cached_data = self.ableton_parameter_cache[cache_key]
                # Handle both old format (string only) and new format (string, value tuple)
                if isinstance(cached_data, tuple):
                    param_str, param_value = cached_data
                else:
                    param_str = cached_data
                    param_value = 0.0
                self.update_value_display(encoder_idx, param_str, param_value)
    
    def update_display_for_parameter(self, device_name, param_name, param_str, param_value, lom_path=''):
        """Update display for a specific parameter"""
        if not self.current_track or self.current_track not in self.track_mappings:
            return
        
        # Find which encoder slot uses this parameter
        for encoder_idx in range(8):
            if encoder_idx not in self.track_mappings[self.current_track]:
                continue
                
            mapping_info = self.track_mappings[self.current_track][encoder_idx]
            matched = False
            
            # Try 1: Match by lom_path (most specific - distinguishes chain volumes)
            if lom_path:
                mapping_lom_path_list = mapping_info.get('lom_path', [])
                if mapping_lom_path_list:
                    mapping_lom_path_str = '|'.join(mapping_lom_path_list)
                    if lom_path == mapping_lom_path_str:
                        matched = True
            
            # Try 2: Match by param_name alone (for unique parameters without lom_path)
            if not matched and param_name and mapping_info.get('param_name', '') == param_name:
                # Only use this if lom_path wasn't available or didn't help
                matched = True
            
            # Try 3: Match by device:param (for device-specific params)
            if not matched:
                cache_key = f"{device_name}:{param_name}"
                mapping_key = f"{mapping_info.get('device_name', '')}:{mapping_info.get('param_name', '')}"
                if cache_key == mapping_key:
                    matched = True
            
            if matched:
                self.update_value_display(encoder_idx, param_str, param_value)
                return
    
    def update_value_display(self, encoder_idx, value_str, normalized_value=None):
        """Update the value label and progress bar for an encoder with Ableton's value
        
        Args:
            encoder_idx: Index of encoder (0-7)
            value_str: Display string (e.g., "-12.3 dB", "50 %", etc.)
            normalized_value: Optional normalized value 0.0-1.0 from Ableton (most accurate)
        """
        if encoder_idx >= len(self.value_labels):
            return
            
        # Update text display (always show the actual value string)
        display_text = value_str.strip()
        try:
            canvas, text_item = self.value_labels[encoder_idx]
            canvas.itemconfig(text_item, text=display_text)
        except Exception as e:
            pass  # Silently ignore display errors
        
        # Update progress bar based on value
        if encoder_idx < len(self.progress_bars):
            canvas, bright_rect = self.progress_bars[encoder_idx]
            
            # Special case: "--" means no value, show all dark green
            if value_str.strip() == "--":
                canvas.coords(bright_rect, 0, 0, 0, 41)
            else:
                # Use normalized value if available (most accurate for all parameter types)
                # Otherwise fall back to parsing the display string
                if normalized_value is not None:
                    percentage = normalized_value * 100.0
                else:
                    percentage = self._parse_percentage(value_str)
                
                # 110px is the full bar width
                bar_width = int((percentage / 100.0) * 110)
                canvas.coords(bright_rect, 0, 0, bar_width, 41)
    
    def _parse_percentage(self, value_str):
        """Parse a percentage from various Ableton value formats"""
        try:
            value_str = value_str.strip()
            
            # Check if it's already a percentage (e.g., "84.5 %")
            if '%' in value_str:
                num_str = value_str.replace('%', '').strip()
                return float(num_str)
            
            # Check if it's a decimal value (0.0 to 1.0)
            val = float(value_str)
            if 0.0 <= val <= 1.0:
                return val * 100.0
            
            # If it's outside 0-1, assume it's already a percentage
            return max(0.0, min(100.0, val))
            
        except (ValueError, AttributeError):
            # Can't parse - default to 0%
            return 0.0
    
    def load_user_mappings(self):
        """Load user-defined parameter name mappings"""
        if not os.path.exists(self.user_mappings_file):
            print(f"No user mappings file found at: {self.user_mappings_file}")
            return {}
        
        try:
            with open(self.user_mappings_file, 'r') as f:
                data = json.load(f)
            
            # Count total mappings
            total = sum(len(params) for params in data.values() if isinstance(params, dict))
            print(f"\n=== LOADED {total} USER MAPPINGS ===")
            for device_class, params in data.items():
                if isinstance(params, dict):
                    for param_tag, custom_name in params.items():
                        print(f"  {device_class}.{param_tag} -> '{custom_name}'")
                else:
                    # Old format fallback
                    print(f"  '{device_class}' -> '{params}'")
            return data
        except Exception as e:
            print(f"Error loading user mappings: {e}")
            return {}
    
    def save_user_mappings(self):
        """Save user-defined parameter name mappings"""
        try:
            print(f"\\n[SAVE] Writing to: {self.user_mappings_file}")
            print(f"[SAVE] Data to write: {json.dumps(self.user_mappings, indent=2)}")
            with open(self.user_mappings_file, 'w') as f:
                json.dump(self.user_mappings, f, indent=2)
            print(f"[SAVE] SUCCESS - File written")
            
            # Verify the file was written by reading it back
            with open(self.user_mappings_file, 'r') as f:
                verify = json.load(f)
            print(f"[SAVE] Verified file contents: {json.dumps(verify, indent=2)}")
        except Exception as e:
            print(f"[SAVE] ERROR saving user mappings: {e}")
            import traceback
            traceback.print_exc()
    
    def on_label_click(self, encoder_idx):
        """Handle click on encoder label to enter MIDI learn mode"""
        if not self.current_track or self.current_track not in self.track_mappings:
            return
        
        if encoder_idx not in self.track_mappings[self.current_track]:
            return
        
        mapping_info = self.track_mappings[self.current_track][encoder_idx]
        
        # Allow learning for unmapped parameters OR re-learning for already mapped ones
        param_tag = mapping_info.get('param_tag', '')
        if not param_tag and not mapping_info.get('param_name', ''):
            # No parameter at all (empty slot)
            print(f"Encoder {encoder_idx + 1} has no parameter assigned")
            return
        
        # If already mapped, allow re-learning
        if mapping_info.get('param_name', ''):
            print(f"Re-learning encoder {encoder_idx + 1} (currently: {mapping_info['label']})")
        
        # Extract device class name from lom_path (or use existing device_class_name)
        device_class_name = mapping_info.get('device_class_name', '')
        if not device_class_name:
            lom_path = mapping_info.get('lom_path', [])
            for path_part in reversed(lom_path):
                if path_part.startswith('devices[') and '<' in path_part and '>' in path_part:
                    # Extract class name from "devices[N] <ClassName>"
                    device_class_name = path_part.split('<')[1].split('>')[0]
                    break
        
        if not device_class_name:
            print(f"Could not determine device class for encoder {encoder_idx + 1}")
            return
        
        # Use param_tag if available, otherwise use param_name as fallback
        learn_param_tag = param_tag if param_tag else mapping_info.get('param_name', '')
        
        # Enter learning mode
        self.learning_mode = True
        self.learning_encoder_idx = encoder_idx
        
        # Set timeout: cancel learning after 10 seconds
        self.learning_timeout_id = self.root.after(10000, self.on_learn_timeout)
        
        # Update label to show learning state with CC number
        cc_num = 71 + encoder_idx
        learn_text = f"Turn CC{cc_num} now..."
        self.label_widgets[encoder_idx].config(text=learn_text, fg='#00ff00')  # Bright green
        
        print(f"\\n=== MIDI LEARN MODE ===")
        print(f"Encoder {encoder_idx + 1} (CC{cc_num}) - Waiting for parameter change...")
        print(f"Device: {device_class_name}")
        print(f"Parameter tag: {learn_param_tag}")
        print(f"Turn CC{cc_num} encoder now...")
        print(f"Press ESC to cancel or wait 10 seconds for timeout")
    
    def learn_parameter(self, param_name, device_name, lom_path):
        """Complete MIDI learn by saving the captured parameter"""
        if not self.learning_mode or self.learning_encoder_idx is None:
            return
        
        # Cancel timeout since we successfully captured a parameter
        if self.learning_timeout_id:
            self.root.after_cancel(self.learning_timeout_id)
            self.learning_timeout_id = None
        
        encoder_idx = self.learning_encoder_idx
        mapping_info = self.track_mappings[self.current_track][encoder_idx]
        
        param_tag = mapping_info.get('param_tag', '')
        device_class_name = mapping_info.get('device_class_name', '')
        
        print(f"\\n=== LEARN DEBUG ===")
        print(f"Captured: param_name='{param_name}', device_name='{device_name}'")
        print(f"From mapping_info: param_tag='{param_tag}', device_class='{device_class_name}'")
        print(f"lom_path from message: {lom_path}")
        print(f"lom_path from mapping_info: {mapping_info.get('lom_path', [])}")
        
        # Extract device class from lom_path if not already set
        if not device_class_name:
            lom_path_list = mapping_info.get('lom_path', [])
            for path_part in reversed(lom_path_list):
                if path_part.startswith('devices[') and '<' in path_part and '>' in path_part:
                    device_class_name = path_part.split('<')[1].split('>')[0]
                    break
            print(f"Extracted device_class from lom_path: '{device_class_name}'")
        
        # If no param_tag (learning a parameter that was already mapped), use param_name as key
        if not param_tag:
            param_tag = param_name  # Use the captured param name as the tag
            print(f"Note: No param_tag found, using param_name '{param_name}' as tag")
        
        # Get the CC number for this encoder (CC 71-78)
        cc_number = 71 + encoder_idx
        cc_key = str(cc_number)
        
        print(f"Saving: user_mappings['{cc_key}'] = '{param_name}'")
        
        # Save to user mappings using CC number as key (simplest and most reliable)
        self.user_mappings[cc_key] = param_name
        self.save_user_mappings()
        
        # Update mapping info for current session
        mapping_info['param_name'] = param_name
        mapping_info['device_name'] = device_name
        mapping_info['label'] = param_name
        mapping_info['is_unmapped'] = False
        # Store lom_path so it's available if we learn again this session
        if isinstance(lom_path, str) and lom_path:
            mapping_info['lom_path'] = lom_path.split('|')
        elif lom_path:
            mapping_info['lom_path'] = lom_path
        
        # Update display
        self.label_widgets[encoder_idx].config(text=param_name, fg='#FFFFFF')  # Back to white
        
        print(f"\\n=== LEARNED SUCCESSFULLY ===")
        print(f"Mapped: {device_class_name}.{param_tag} -> {param_name}")
        print(f"Saved to: {self.user_mappings_file}")
        print(f"Next time you save the Ableton project, the scanner will use this mapping.\\n")
        
        # Show notification
        self.show_notification("Done! Save your Ableton file and relaunch to see your change")
        
        self.exit_learn_mode()
    
    def exit_learn_mode(self):
        """Exit MIDI learn mode"""
        # Cancel timeout if still active
        if self.learning_timeout_id:
            self.root.after_cancel(self.learning_timeout_id)
            self.learning_timeout_id = None
        
        if self.learning_encoder_idx is not None and self.learning_encoder_idx < len(self.label_widgets):
            # Restore original label
            if self.current_track in self.track_mappings:
                mapping_info = self.track_mappings[self.current_track].get(self.learning_encoder_idx, {})
                label = mapping_info.get('label', f"CC {71 + self.learning_encoder_idx}")
                self.label_widgets[self.learning_encoder_idx].config(text=label, fg='#FFFFFF')
        
        self.learning_mode = False
        self.learning_encoder_idx = None
    
    def on_learn_timeout(self):
        """Handle learning mode timeout"""
        if self.learning_mode and self.learning_encoder_idx is not None:
            print(f"\\n=== LEARN TIMEOUT ===")
            print(f"No parameter change detected after 10 seconds")
            print(f"Learning cancelled for CC{71 + self.learning_encoder_idx}")
            self.exit_learn_mode()
    
    def cancel_learn_mode(self):
        """Cancel learning mode (called by ESC key)"""
        if self.learning_mode:
            print(f"\\n=== LEARN CANCELLED ===")
            print(f"User pressed ESC - learning cancelled for CC{71 + self.learning_encoder_idx}")
            self.exit_learn_mode()
    
    def close(self):
        """Clean up resources"""
        self.running = False
        
        if self.udp_socket:
            self.udp_socket.close()


def main():
    root = tk.Tk()
    app = MIDIOverlay(root)
    
    # Handle window close
    root.protocol("WM_DELETE_WINDOW", lambda: [app.close(), root.destroy()])
    
    root.mainloop()


if __name__ == "__main__":
    main()
