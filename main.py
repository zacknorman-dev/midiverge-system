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
        self.scanning_popup = None  # Popup window for scan progress
        
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
                    param_name = mapping.get('param_live_name', 'Unknown')
                    device_name = mapping.get('device_name', '')
                    
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
            else:
                print(f"Scan complete: {total} total mappings")
        
        elif msg_type == 'track_changed':
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
