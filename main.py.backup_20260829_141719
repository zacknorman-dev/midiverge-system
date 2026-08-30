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
        self.manual_mappings_file = r"C:\Users\zackn\Documents\midi overlay\manual_mappings.json"
        self.manual_mappings = {}  # {track_cc_key: {'mfl_path': str}}
        self.cc_mappings = {}  # {cc: {'param_name': str, 'device_name': str}}
        self.scanning_popup = None  # Popup window for scan progress
        self.scanner_file_mtime = 0  # Track file modification time for auto-reload
        
        # Load manual mappings
        self.load_manual_mappings()
        
        # UI elements
        self.track_label = None
        self.label_widgets = []  # Parameter name labels
        self.value_labels = []   # Value text items
        self.progress_bars = []  # Progress bar rectangles
        
        # Create UI FIRST so widgets exist when messages arrive
        self.create_ui()
        print("UI created - widgets ready")
        
        # Load initial mappings from scanner JSON
        self.load_mappings()
        
        # Start UDP listener AFTER UI is ready
        self.running = True
        self.udp_socket = None
        self.udp_thread = None
        self.start_udp_listener()
        print("UDP listener started - ready to receive messages")
        
        # Start file watcher for auto-reload when scanner updates
        self.check_file_changes()
        
        print("MIDI Overlay started - waiting for Ableton updates...")
    
    def position_window_bottom(self):
        """Position window at bottom center of screen"""
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width - 2560) // 2
        y = screen_height - 102 - 40
        
        self.root.geometry(f"2560x102+{x}+{y}")
    
    def load_manual_mappings(self):
        """Load manual mappings from JSON file"""
        if not os.path.exists(self.manual_mappings_file):
            self.manual_mappings = {}
            return
        
        try:
            with open(self.manual_mappings_file, 'r') as f:
                self.manual_mappings = json.load(f)
            print(f"Loaded {len(self.manual_mappings)} manual mappings")
        except Exception as e:
            print(f"Error loading manual mappings: {e}")
            self.manual_mappings = {}
    
    def save_manual_mappings(self):
        """Save manual mappings to JSON file"""
        try:
            with open(self.manual_mappings_file, 'w') as f:
                json.dump(self.manual_mappings, f, indent=2)
            print(f"Saved {len(self.manual_mappings)} manual mappings")
        except Exception as e:
            print(f"Error saving manual mappings: {e}")
    
    def trigger_rescan(self):
        """Trigger scanner by creating do_scan.txt file"""
        try:
            trigger_file = r"C:\Users\zackn\Documents\midi overlay\do_scan.txt"
            with open(trigger_file, 'w') as f:
                f.write('scan')
            print("Triggered rescan")
            
            # Visual feedback
            if self.track_label:
                old_track = self.track_label.cget('text')
                self.track_label.config(text="⟳ Scanning...", fg='#ffaa00')
                # Check for completion after 2 seconds
                self.root.after(2000, lambda: self.check_scan_completion(old_track))
        except Exception as e:
            print(f"Error triggering rescan: {e}")
            if self.track_label:
                self.track_label.config(text="Scan Error!", fg='#ff0000')
    
    def check_scan_completion(self, old_track_text):
        """Check if scan completed and show results"""
        try:
            with open(self.scanner_file, 'r') as f:
                data = json.load(f)
                total = len(data)
                self.track_label.config(text=f"✓ Scan Complete - {total} mappings", fg='#00cc00')
                self.root.after(3000, lambda: self.track_label.config(text=old_track_text, fg='#00ddff'))
        except Exception as e:
            self.track_label.config(text=f"Scan Error!", fg='#ff0000')
            self.root.after(3000, lambda: self.track_label.config(text=old_track_text, fg='#00ddff'))
    
    def touch_scanner_json(self):
        """Touch scanner JSON to trigger MIDIOverlay reload without full rescan"""
        try:
            # Update timestamp on scanner JSON file
            os.utime(self.scanner_file, None)
            print("Touched scanner JSON - MIDIOverlay will reload")
        except Exception as e:
            print(f"Error touching scanner JSON: {e}")
    
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
            
            # Auto-detect track from first mapping if current_track is "No Track"
            if self.current_track == "No Track" and data.get('mappings'):
                first_track = data['mappings'][0].get('track_name_live', '')
                if first_track:
                    self.current_track = first_track
                    self.track_label.config(text=first_track)
                    print(f"Auto-detected track: {first_track}")
            
            # Find mappings for current track and CC71-78
            for mapping in data.get('mappings', []):
                cc = mapping.get('cc')
                track_name = mapping.get('track_name_live', '')
                
                # Only load if CC is in our range (71-78)
                if 71 <= cc <= 78 and track_name == self.current_track:
                    # Use param_tag since param_live_name is often empty (failed resolution)
                    param_name = mapping.get('param_tag', mapping.get('param_live_name', ''))
                    device_name = mapping.get('device_name', '')
                    
                    # Load scanner data as initial placeholder
                    # parameter_changed messages will overwrite with correct Live names
                    if param_name:
                        self.cc_mappings[cc] = {
                            'param_name': param_name,
                            'device_name': device_name
                        }
            
            # Update UI labels
            self.update_labels()
            
            # Clear value displays for unmapped encoders
            for i in range(8):
                cc = 71 + i
                if cc not in self.cc_mappings:
                    self.update_value_display(i, "--", 0.0)
            
            # Update file modification time
            self.scanner_file_mtime = os.path.getmtime(self.scanner_file)
            
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
                # No mapping - show placeholder
                label_text = "--"
            
            # Update label widget
            if slot_index < len(self.label_widgets):
                self.label_widgets[slot_index].config(text=label_text)
    
    def check_file_changes(self):
        """Periodically check if scanner file has been updated and auto-reload"""
        try:
            if os.path.exists(self.scanner_file):
                current_mtime = os.path.getmtime(self.scanner_file)
                if current_mtime != self.scanner_file_mtime:
                    print(f"Scanner file updated - reloading and updating display...")
                    self.scanner_file_mtime = current_mtime
                    # Reload mappings and update labels immediately
                    self.load_mappings()
                    self.update_labels_from_mappings()
        except Exception as e:
            print(f"Error checking file changes: {e}")
        
        # Check again in 1 second
        self.root.after(1000, self.check_file_changes)
    
    def update_labels_from_mappings(self):
        """Update parameter name labels from loaded mappings"""
        for i in range(8):
            cc = 71 + i
            if cc in self.cc_mappings:
                param_name = self.cc_mappings[cc].get('param_name', f'CC {cc}')
                self.label_widgets[i].config(text=param_name)
            else:
                self.label_widgets[i].config(text=f'CC {cc}')
        print(f"Updated labels from mappings: {len(self.cc_mappings)} CCs loaded")
    
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
        
        # Rescan button (centered, left of track name)
        rescan_btn = tk.Button(
            track_frame,
            text="⟳ RESCAN",
            bg='#00cc00',
            fg='#000000',
            font=('Arial', 14, 'bold'),
            command=self.trigger_rescan,
            relief='raised',
            bd=2,
            cursor='hand2'
        )
        rescan_btn.place(x=850, y=8, width=120, height=32)
        
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
            
            # Double-click to open manual mapping dialog
            cc = 71 + i
            label.bind('<Double-Button-1>', lambda e, c=cc: self.open_manual_mapping_dialog(c))
            gray_area.bind('<Double-Button-1>', lambda e, c=cc: self.open_manual_mapping_dialog(c))
            
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
    
    def open_manual_mapping_dialog(self, cc):
        """Open dialog to manually set MFL path for this CC"""
        # Get current mapping key
        manual_key = f"track_{self.current_track.replace(' ', '_')}_cc_{cc}"
        current_mfl_path = self.manual_mappings.get(manual_key, {}).get('mfl_path', '')
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Manual Mapping - CC{cc}")
        dialog.configure(bg='#1a1a1a')
        dialog.attributes('-topmost', True)
        dialog.resizable(False, False)
        
        # Fixed size container
        main_frame = tk.Frame(dialog, bg='#1a1a1a', width=500, height=300)
        main_frame.pack_propagate(False)
        main_frame.pack()
        
        # Center on screen
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 500) // 2
        y = (dialog.winfo_screenheight() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Label(
            main_frame,
            text=f"CC{cc} - {self.current_track}",
            bg='#2a2a2a',
            fg='#00cc00',
            font=('Arial', 14, 'bold'),
            pady=10
        )
        header.pack(fill='x')
        
        # Content
        content = tk.Frame(main_frame, bg='#1a1a1a')
        content.pack(fill='both', expand=True, padx=20, pady=20)
        
        # MFL Path field
        tk.Label(
            content,
            text="Max for Live Path:",
            bg='#1a1a1a',
            fg='#888888',
            font=('Arial', 10),
            anchor='w'
        ).pack(fill='x', pady=(0, 5))
        
        mfl_entry = tk.Entry(content, bg='#2a2a2a', fg='#ffffff', font=('Arial', 11))
        mfl_entry.insert(0, current_mfl_path)
        mfl_entry.pack(fill='x', pady=(0, 5))
        
        # Right-click paste
        def paste_to_mfl(event):
            try:
                clipboard = dialog.clipboard_get()
                mfl_entry.delete(0, tk.END)
                mfl_entry.insert(0, clipboard)
            except:
                pass
        mfl_entry.bind('<Button-3>', paste_to_mfl)
        
        tk.Label(
            content,
            text="(Right-click to paste)",
            bg='#1a1a1a',
            fg='#666666',
            font=('Arial', 8),
            anchor='w'
        ).pack(fill='x', pady=(0, 20))
        
        # Buttons at bottom
        button_frame = tk.Frame(main_frame, bg='#1a1a1a')
        button_frame.pack(side='bottom', fill='x', padx=20, pady=20)
        
        def save_and_close():
            mfl_path = mfl_entry.get().strip()
            
            # Save manual mapping
            self.manual_mappings[manual_key] = {'mfl_path': mfl_path}
            self.save_manual_mappings()
            
            # Touch scanner JSON to trigger MIDIOverlay reload
            self.touch_scanner_json()
            
            dialog.destroy()
            print(f"Saved manual mapping for CC{cc}: {mfl_path}")
        
        save_btn = tk.Button(
            button_frame,
            text="Save",
            command=save_and_close,
            bg='#00cc00',
            fg='#000000',
            font=('Arial', 11, 'bold'),
            width=15,
            cursor='hand2'
        )
        save_btn.pack(side='right', padx=5)
        
        cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            bg='#444444',
            fg='#ffffff',
            font=('Arial', 11),
            width=15,
            cursor='hand2'
        )
        cancel_btn.pack(side='right')
    
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
        
        if msg_type == 'scan_start':
            # Scanner started - show "Scanning..." popup
            self.show_scanning_popup()
            print("Scan started...")
        
        elif msg_type == 'scan_complete':
            # Scanner finished - WIPE EVERYTHING and reload from scratch
            self.hide_scanning_popup()
            
            # Clear ALL encoders first (nuclear option)
            for i in range(8):
                self.label_widgets[i].config(text=f"CC {71+i}")
                self.update_value_display(i, "--", 0.0)
            
            # Now load fresh mappings from JSON
            self.load_mappings()
            
            total = message.get('total_mappings', 0)
            error = message.get('error')
            
            if error:
                print(f"Scan complete with error: {error}")
                # Show error in track label for 3 seconds
                old_track = self.current_track
                self.track_label.config(text=f"Scan Error!", fg='#ff0000')
                self.root.after(3000, lambda: self.track_label.config(text=old_track, fg='#00cc00'))
            else:
                print(f"Scan complete: {total} total mappings")
                # Show success in track label for 3 seconds
                old_track = self.current_track
                self.track_label.config(text=f"✓ Scan Complete - {total} mappings", fg='#00cc00')
                self.root.after(3000, lambda: self.track_label.config(text=old_track, fg='#00cc00'))
        
        elif msg_type == 'track_changed':
            # Track selection changed - update current track and reload mappings
            track_name = message.get('track_name', 'Unknown Track')
            self.current_track = track_name
            self.track_label.config(text=track_name)
            
            # CLEAR old mappings before loading new track's mappings
            self.cc_mappings.clear()
            
            # Reload mappings for new track (scanner data as initial/fallback)
            self.load_mappings()
            
            # DON'T clear value displays - let parameter_changed messages update them
            # (MIDIOverlay sends those immediately after track_changed)
            
            print(f"Track changed: {track_name}")
        
        elif msg_type == 'parameter_changed':
            # Parameter value changed - update display
            cc = message.get('cc')
            
            if cc is None or cc < 71 or cc > 78:
                return  # Ignore CCs outside our range
            
            slot_index = cc - 71
            param_str = message.get('param_str', '--')
            param_value = message.get('param_value', 0.0)
            param_name = message.get('param_name', '')
            device_name = message.get('device_name', '')
            
            # Update stored mapping with actual parameter name from Ableton
            if param_name:
                self.cc_mappings[cc] = {
                    'param_name': param_name,
                    'device_name': device_name
                }
                # Update label immediately
                if device_name:
                    label_text = f"{device_name}\n{param_name}"
                else:
                    label_text = param_name
                if slot_index < len(self.label_widgets):
                    self.label_widgets[slot_index].config(text=label_text)
            
            # Update display for this encoder
            self.update_value_display(slot_index, param_str, param_value)
    
    def show_scanning_popup(self):
        """Show 'Scanning...' popup in center of screen"""
        if self.scanning_popup is not None:
            return  # Already showing
        
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("")
        popup.geometry("400x150")
        popup.resizable(False, False)
        popup.attributes('-topmost', True)
        popup.configure(bg='#1a1a1a')
        
        # Remove window decorations
        popup.overrideredirect(True)
        
        # Center on screen
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = (screen_w - 400) // 2
        y = (screen_h - 150) // 2
        popup.geometry(f"400x150+{x}+{y}")
        
        # Content
        frame = tk.Frame(popup, bg='#1a1a1a', highlightbackground='#00cc00', highlightthickness=3)
        frame.pack(fill='both', expand=True, padx=0, pady=0)
        
        label = tk.Label(
            frame,
            text="Scanning MIDI Mappings...",
            bg='#1a1a1a',
            fg='#00cc00',
            font=('Arial', 18, 'bold')
        )
        label.pack(expand=True)
        
        sublabel = tk.Label(
            frame,
            text="Please wait...",
            bg='#1a1a1a',
            fg='#888888',
            font=('Arial', 12)
        )
        sublabel.pack()
        
        self.scanning_popup = popup
    
    def hide_scanning_popup(self):
        """Hide scanning popup"""
        if self.scanning_popup is not None:
            self.scanning_popup.destroy()
            self.scanning_popup = None
    
    def cleanup(self):
        """Cleanup on exit"""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()
        if self.scanning_popup:
            self.scanning_popup.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = MIDIOverlay(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()
