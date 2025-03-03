import tkinter as tk
from tkinter import ttk, messagebox
import requests
import sqlite3
import threading
import sys
import os
import platform
from pynput import keyboard
import json

if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    
    # Windows API constants for window activation
    SW_SHOW = 5
    SW_SHOWNORMAL = 1
    
    # Function to force window focus using Windows API
    def force_window_focus(hwnd):
        """Force window focus using Windows API"""
        user32 = ctypes.WinDLL('user32')
        user32.SetForegroundWindow(hwnd)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetActiveWindow(hwnd)

class QuickDefinitionApp:
    def __init__(self):
        # Shadcn-inspired color palette
        self.colors = {
            'background': '#1a1a1a',        # Dark background
            'card': '#222222',              # Card background
            'primary': '#0ea5e9',           # Primary accent (sky blue)
            'secondary': '#6366f1',         # Secondary accent (indigo)
            'muted': '#71717a',             # Muted text
            'text': '#f8fafc',              # Main text
            'border': '#27272a',            # Border color
            'input': '#27272a',             # Input background
            'error': '#ef4444',             # Error color
            'success': '#22c55e',           # Success color
            'warning': '#f59e0b',           # Warning color
        }
        
        # Set platform-specific fonts
        self.setup_fonts()
        
        # Create data directory if not exists
        self.ensure_data_directory()
        
        # Initialize UI elements
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        self.input_window = None
        self.loading_window = None
        self.result_window = None
        self.error_window = None
        self.suggestion_popup = None
        self.suggestion_after_id = None  # ID for debouncing suggestions
        self.active_fetch_thread = None
        self.selected_suggestion_index = -1  # For keyboard navigation
        
        # Create modern spinner frames
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_spinner_index = 0
        
        self.setup_input_window()
        
        # Setup hotkey based on platform
        self.setup_hotkeys()
        
        # Check if database exists, if not show a message
        if not os.path.exists(self.get_database_path()):
            messagebox.showinfo(
                "Database Not Found", 
                "WordNet database not found. The app will use online API only.\n\n"
                "Please run the database setup script (build_database.py) if you want offline functionality."
            )

    def setup_fonts(self):
        """Configure platform-specific fonts"""
        system = platform.system()
        
        # Default fonts (Linux)
        self.fonts = {
            'heading': ('Noto Sans', 16, 'bold'),
            'subheading': ('Noto Sans', 14, 'bold'),
            'body': ('Noto Sans', 12),
            'small': ('Noto Sans', 10),
            'tiny': ('Noto Sans', 9),
            'monospace': ('Monospace', 12),
        }
        
        # Windows fonts
        if system == 'Windows':
            self.fonts = {
                'heading': ('Segoe UI', 16, 'bold'),
                'subheading': ('Segoe UI', 14, 'bold'),
                'body': ('Segoe UI', 12),
                'small': ('Segoe UI', 10),
                'tiny': ('Segoe UI', 9),
                'monospace': ('Consolas', 12),
            }
        # macOS fonts
        elif system == 'Darwin':
            self.fonts = {
                'heading': ('SF Pro', 16, 'bold'),
                'subheading': ('SF Pro', 14, 'bold'),
                'body': ('SF Pro', 12),
                'small': ('SF Pro', 10),
                'tiny': ('SF Pro', 9),
                'monospace': ('Menlo', 12),
            }

    def get_database_path(self):
        """Get appropriate database path for current platform"""
        system = platform.system()
        
        # Base directory for app data
        if system == 'Windows':
            base_dir = os.path.join(os.environ.get('APPDATA', ''), 'QuickDefinition')
        elif system == 'Darwin':  # macOS
            base_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'QuickDefinition')
        else:  # Linux and others
            base_dir = os.path.join(os.path.expanduser('~'), '.quickdefinition')
        return os.path.join(base_dir, 'wordnet.db')

    def ensure_data_directory(self):
        """Create app data directory if it doesn't exist"""
        db_path = self.get_database_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def setup_hotkeys(self):
        """Setup platform-specific hotkeys"""
        # Platform-specific hotkey combinations
        system = platform.system()
        
        if system == 'Darwin':  # macOS often uses Command instead of Ctrl
            hotkey_combo = '<cmd>+<alt>+d'
        else:  # Windows, Linux, etc.
            hotkey_combo = '<ctrl>+<alt>+d'
        
        # Start listening for the appropriate hotkey
        self.hotkey = keyboard.GlobalHotKeys({
            hotkey_combo: self.show_input
        })
        
        try:
            self.hotkey.start()
        except Exception as e:
            print(f"Error setting up hotkey: {e}")
            messagebox.showwarning(
                "Hotkey Registration Failed", 
                f"Failed to register global hotkey: {e}\n\nYou'll need to use the app interface directly."
            )

    def quit(self):
        """Clean shutdown of the application"""
        try:
            self.hotkey.stop()
        except:
            pass
        self.root.quit()
        self.root.destroy()

    def run(self):
        """Main app loop"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

    def create_rounded_rect(self, canvas, x1, y1, x2, y2, radius=25, **kwargs):
        """Draw a rounded rectangle on a canvas"""
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1
        ]
        return canvas.create_polygon(points, **kwargs, smooth=True)

    def setup_input_window(self):
        """Create the main input window"""
        self.input_window = tk.Toplevel(self.root)
        self.input_window.withdraw()
        self.input_window.attributes('-topmost', True)
        self.input_window.overrideredirect(True)  # No window decorations
        self.input_window.configure(bg=self.colors['background'])
        
        # Add a thin border to make the window more defined against dark backgrounds
        border_frame = tk.Frame(self.input_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        
        # Inner content frame
        content_frame = tk.Frame(border_frame, bg=self.colors['background'])
        content_frame.pack(fill='both', expand=True)
        
        # Title frame with logo/icon
        title_frame = tk.Frame(content_frame, bg=self.colors['background'])
        title_frame.pack(fill='x', padx=16, pady=(16, 8))
        
        # Use a simple icon character as the logo
        logo_label = tk.Label(title_frame, text="📚", 
                             font=self.fonts['heading'], 
                             bg=self.colors['background'], 
                             fg=self.colors['primary'])
        logo_label.pack(side='left', padx=(0, 8))
        
        title_label = tk.Label(title_frame, text="Quick Definition", 
                              font=self.fonts['heading'], 
                              bg=self.colors['background'], 
                              fg=self.colors['text'])
        title_label.pack(side='left')
        
        # Search frame with modern styling
        search_frame = tk.Frame(content_frame, bg=self.colors['background'])
        search_frame.pack(padx=16, pady=(0, 16), fill='both')
        
        # Input frame with border simulation
        input_border = tk.Frame(search_frame, bg=self.colors['border'], padx=1, pady=1)
        input_border.pack(fill='x')
        
        input_frame = tk.Frame(input_border, bg=self.colors['input'], padx=12, pady=8)
        input_frame.pack(fill='x')
        
        self.entry = tk.Entry(input_frame, width=30, font=self.fonts['body'],
                             bg=self.colors['input'], fg=self.colors['text'], bd=0,
                             insertbackground=self.colors['text'])
        self.entry.pack(fill='both')
        self.entry.insert(0, "Type a word to define...")
        self.entry.config(fg=self.colors['muted'])
        
        # Event bindings with focus fixes
        self.entry.bind("<FocusIn>", self.on_entry_focus_in)
        self.entry.bind("<FocusOut>", self.on_entry_focus_out)
        self.entry.bind('<Return>', self.on_return)
        self.entry.bind('<Escape>', lambda e: self.hide_input_window())
        self.entry.bind("<KeyRelease>", self.on_key_release)
        
        # Add arrow key navigation for suggestions
        self.entry.bind("<Down>", self.navigate_suggestions_down)
        self.entry.bind("<Up>", self.navigate_suggestions_up)
        self.entry.bind("<Tab>", self.select_current_suggestion)
        
        self.input_window.bind('<Escape>', lambda e: self.hide_input_window())
        
        # Get platform-specific shortcut name
        shortcut_text = "Ctrl+Alt+D"
        if platform.system() == 'Darwin':  # macOS 
            shortcut_text = "Cmd+Alt+D"
        
        # Keyboard shortcut hint
        shortcut_frame = tk.Frame(content_frame, bg=self.colors['background'])
        shortcut_frame.pack(fill='x', padx=16, pady=(0, 8))
        
        shortcut_label = tk.Label(shortcut_frame, text=f"Global: {shortcut_text} | Press Esc to close", 
                                 font=self.fonts['tiny'], 
                                 bg=self.colors['background'], 
                                 fg=self.colors['muted'])
        shortcut_label.pack(side='right')
        
        # Set window size and center it
        self.center_window(self.input_window, 400, 140)

    def on_entry_focus_in(self, event):
        """Handle entry field focus in"""
        if self.entry.get() == "Type a word to define...":
            self.entry.delete(0, tk.END)
            self.entry.config(fg=self.colors['text'])
    
    def on_entry_focus_out(self, event):
        """Handle entry field focus out"""
        if not self.entry.get():
            self.entry.insert(0, "Type a word to define...")
            self.entry.config(fg=self.colors['muted'])
        
        # Set a small delay before hiding suggestions
        # to allow clicking on them to work properly
        if self.suggestion_popup:
            self.root.after(100, self.check_focus_for_suggestions)

    def on_return(self, event):
        """Return key behavior: select suggestion if shown and a suggestion is selected, otherwise fetch definition."""
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            return self.select_current_suggestion(event)
        else:
            return self.fetch_definition(event)

    def check_focus_for_suggestions(self):
        """Check if we should close the suggestions popup based on focus"""
        # If focus is not on suggestion popup or its children, close it
        try:
            if self.suggestion_popup and self.suggestion_popup.focus_get() is None:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
        except:
            # If there's an error (e.g., window was destroyed), make sure to clean up
            self.suggestion_popup = None

    def center_window(self, window, width, height):
        """Center a window on the screen"""
        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 3
        window.geometry(f'{width}x{height}+{x}+{y}')

    def show_input(self):
        """Show the input window"""
        # Hide any existing windows first
        self.hide_all_windows()
        
        # Reset the entry field
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "Type a word to define...")
        self.entry.config(fg=self.colors['muted'])
        
        # Show the input window
        self.input_window.deiconify()
        
        # Windows-specific focus handling
        if platform.system() == 'win32':
            # Force the window to be active on Windows
            self.input_window.attributes('-topmost', True)
            self.input_window.focus_force()
            
            # Schedule multiple focus attempts with increasing delays
            self.input_window.after(50, self.windows_force_focus)
            self.input_window.after(150, self.windows_force_focus)
            self.input_window.after(300, self.windows_force_focus)
        else:
            # Non-Windows platforms
            self.input_window.lift()
            self.input_window.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
        
        # Ensure we capture keyboard events
        self.input_window.grab_set()

    def windows_force_focus(self):
        """Special function for handling Windows focus issues"""
        try:
            # Standard Tkinter approach
            self.input_window.lift()
            self.input_window.focus_force()
            
            # Windows API approach for stubborn focus issues
            if 'force_window_focus' in globals() and platform.system() == 'win32':
                hwnd = int(self.input_window.winfo_id())
                force_window_focus(hwnd)
            
            # Focus on entry
            self.entry.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
        except Exception as e:
            print(f"Focus error: {e}")

    def force_entry_focus(self):
        """Helper function to force focus on the entry field"""
        try:
            self.input_window.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
            
            # Explicitly disable and re-enable the entry to force focus
            # This is a hacky workaround for stubborn focus issues
            current_state = self.entry["state"]
            self.entry.configure(state="disabled")
            self.entry.after(1, lambda: self.entry.configure(state=current_state))
            
            # On Windows, an additional trick might be needed
            if platform.system() == 'win32':
                self.entry.after(5, lambda: self.input_window.lift())
        except tk.TclError:
            pass  # Window might have been closed

    def set_input_focus(self):
        """Set focus to the input field"""
        # This helps fix the focus issue by delaying the focus action
        self.input_window.focus_force()
        self.entry.focus_set()
        self.entry.selection_range(0, tk.END)
        
        # Explicitly steal focus and keep window on top
        self.input_window.grab_set()
        self.input_window.attributes('-topmost', True)

    def hide_all_windows(self):
        """Hide all app windows to ensure clean state"""
        for window in [self.input_window, self.loading_window, 
                      self.result_window, self.error_window]:
            if window:
                try:
                    window.grab_release()
                    window.withdraw()
                except tk.TclError:
                    pass
        
        if self.suggestion_popup:
            try:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
            except tk.TclError:
                pass

    def hide_input_window(self):
        """Hide the input window"""
        try:
            self.input_window.grab_release()
        except tk.TclError:
            pass
        self.input_window.withdraw()
        
        if self.suggestion_popup:
            try:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
            except tk.TclError:
                pass

    def on_key_release(self, event):
        """Handle key release events for suggestions"""
        # Filter out non-character keys to avoid unnecessary suggestion lookups
        if event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 
                           'Alt_L', 'Alt_R', 'Escape', 'Return', 'Up', 'Down', 'Tab'):
            return
            
        # Debounce: cancel any pending suggestion query
        if self.suggestion_after_id:
            self.entry.after_cancel(self.suggestion_after_id)
            
        # Only query if at least 2 characters are typed
        word = self.entry.get().strip()
        if len(word) >= 2 and word != "Type a word to define...":
            self.suggestion_after_id = self.entry.after(200, self.show_suggestions)
        else:
            if self.suggestion_popup:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None

    def navigate_suggestions_down(self, event):
        """Navigate down through suggestions with Down arrow key"""
        if self.suggestion_popup:
            if hasattr(self, 'suggestion_items') and self.suggestion_items:
                self.selected_suggestion_index = min(
                    self.selected_suggestion_index + 1,
                    len(self.suggestion_items) - 1
                )
                self.highlight_selected_suggestion()
            return "break"  # Prevent default behavior
        return None

    def navigate_suggestions_up(self, event):
        """Navigate up through suggestions with Up arrow key"""
        if self.suggestion_popup:
            if hasattr(self, 'suggestion_items') and self.suggestion_items:
                self.selected_suggestion_index = max(
                    self.selected_suggestion_index - 1,
                    -1  # -1 means no selection
                )
                self.highlight_selected_suggestion()
            return "break"  # Prevent default behavior
        return None

    def highlight_selected_suggestion(self):
        """Highlight the currently selected suggestion"""
        if not hasattr(self, 'suggestion_items') or not self.suggestion_items:
            return
            
        # Reset all items to normal
        for i, (frame, label) in enumerate(self.suggestion_items):
            if i == self.selected_suggestion_index:
                # Highlight the selected item
                frame.configure(bg=self.colors['primary'])
                label.configure(bg=self.colors['primary'])
            else:
                # Reset to normal
                frame.configure(bg=self.colors['background'])
                label.configure(bg=self.colors['background'])

    def select_current_suggestion(self, event=None):
        """Select the currently highlighted suggestion"""
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            try:
                word = self.suggestion_items[self.selected_suggestion_index][1]['text']
                self.entry.delete(0, tk.END)
                self.entry.insert(0, word)
                self.entry.configure(fg=self.colors['text'])
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
                self.selected_suggestion_index = -1
                return "break"  # Prevent default behavior
            except (IndexError, KeyError, tk.TclError):
                pass
        return None

    def show_suggestions(self):
        """Show word suggestions based on typing"""
        word_fragment = self.entry.get().strip()
        if len(word_fragment) < 2 or word_fragment == "Type a word to define...":
            if self.suggestion_popup:
                try:
                    self.suggestion_popup.destroy()
                except tk.TclError:
                    pass
                self.suggestion_popup = None
            self.last_suggestions = []
            return
        # Check if database exists
        if not os.path.exists(self.get_database_path()):
            return  # No suggestions without database
        try:
            conn = sqlite3.connect(self.get_database_path())
            c = conn.cursor()
            # Use a LIKE query for words starting with the fragment (case-insensitive)
            c.execute("SELECT DISTINCT lemma FROM definitions WHERE lemma LIKE ? COLLATE NOCASE LIMIT 8", 
                    (word_fragment + '%',))
            suggestions = [row[0] for row in c.fetchall()]
            conn.close()
        except Exception as ex:
            print("Error fetching suggestions:", ex)
            suggestions = []
        if not suggestions:
            if self.suggestion_popup:
                try:
                    self.suggestion_popup.destroy()
                except tk.TclError:
                    pass
                self.suggestion_popup = None
            self.last_suggestions = []
            return
        # If suggestions haven't changed and popup exists, do not re-render
        if hasattr(self, 'last_suggestions') and self.last_suggestions == suggestions and self.suggestion_popup:
            return
        self.last_suggestions = suggestions
        # If suggestion popup exists, update its contents; otherwise, create it.
        if self.suggestion_popup:
            # Update existing suggestions container
            for child in self.suggestion_container.winfo_children():
                child.destroy()
            self.suggestion_items = []
        else:
            # Create a popup that looks like a dropdown
            self.suggestion_popup = tk.Toplevel(self.input_window)
            self.suggestion_popup.overrideredirect(True)
            self.suggestion_popup.configure(bg=self.colors['border'])
            self.suggestion_popup.attributes('-topmost', True)
            # Calculate popup position below the entry field
            x = self.input_window.winfo_x() + 16
            y = self.input_window.winfo_y() + 95  # Position below entry
            width = self.input_window.winfo_width() - 32
            
            # Calculate the height based on number of suggestions (36px per item plus padding)
            popup_height = len(suggestions) * 36 + 8
            
            self.suggestion_popup.geometry(f"{width}x{popup_height}+{x}+{y}")
            # Inner frame with padding
            inner_frame = tk.Frame(self.suggestion_popup, bg=self.colors['background'], padx=1, pady=1)
            inner_frame.pack(fill='both', expand=True)
            
            # Create a simple frame to hold suggestions instead of a scrollable canvas
            self.suggestion_container = tk.Frame(inner_frame, bg=self.colors['background'])
            self.suggestion_container.pack(fill='both', expand=True)
            
            # Let the popup handle escape to close itself
            self.suggestion_popup.bind('<Escape>', lambda event: self.suggestion_popup.destroy())
        
        # Reset selection index
        self.selected_suggestion_index = -1
        self.suggestion_items = []
        
        # Add suggestion items
        for suggestion in suggestions:
            item_frame = tk.Frame(self.suggestion_container, bg=self.colors['background'], 
                                padx=12, pady=8, height=36)
            item_frame.pack(fill='x')
            item_frame.pack_propagate(False)
            label = tk.Label(item_frame, text=suggestion, font=self.fonts['body'],
                            bg=self.colors['background'], fg=self.colors['text'],
                            anchor='w')
            label.pack(fill='both')
            self.suggestion_items.append((item_frame, label))
            def on_enter(_, frame=item_frame, lbl=label):
                frame.configure(bg=self.colors['primary'])
                lbl.configure(bg=self.colors['primary'])
            def on_leave(_, frame=item_frame, lbl=label):
                if self.selected_suggestion_index == -1 or frame != self.suggestion_items[self.selected_suggestion_index][0]:
                    frame.configure(bg=self.colors['background'])
                    lbl.configure(bg=self.colors['background'])
            def on_click(_, word=suggestion):
                self.entry.delete(0, tk.END)
                self.entry.insert(0, word)
                self.entry.configure(fg=self.colors['text'])
                if self.suggestion_popup:
                    self.suggestion_popup.destroy()
                    self.suggestion_popup = None
                self.entry.focus_set()
            item_frame.bind('<Enter>', on_enter)
            item_frame.bind('<Leave>', on_leave)
            item_frame.bind('<Button-1>', on_click)
            label.bind('<Enter>', on_enter)
            label.bind('<Leave>', on_leave)
            label.bind('<Button-1>', on_click)
        
        # Update the popup dimensions after all items are added
        self.suggestion_container.update_idletasks()
        
        # Recalculate the height based on the actual content
        x = self.input_window.winfo_x() + 16
        y = self.input_window.winfo_y() + 95  # Position below entry
        width = self.input_window.winfo_width() - 32
        actual_height = len(self.suggestion_items) * 36 + 8
        
        self.suggestion_popup.geometry(f"{width}x{actual_height}+{x}+{y}")
    
    def fetch_definition(self, event):
        """Start the definition fetching process"""
        word = self.entry.get().strip()
        if word == "Type a word to define..." or not word:
            return
            
        # Properly close all windows
        self.hide_input_window()
        
        # If a suggestion is currently selected, use that word
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            try:
                word = self.suggestion_items[self.selected_suggestion_index][1]['text']
            except (IndexError, KeyError, tk.TclError):
                pass
            
            # Make sure to close the popup
            try:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
            except tk.TclError:
                pass
            
        # Prevent multiple fetches
        if self.active_fetch_thread and self.active_fetch_thread.is_alive():
            return
            
        self.show_loading_window()
        self.active_fetch_thread = threading.Thread(target=self.get_definition, args=(word,), daemon=True)
        self.active_fetch_thread.start()

    def show_loading_window(self):
        """Display a loading window while waiting for results"""
        if self.loading_window:
            try:
                self.loading_window.destroy()
            except tk.TclError:
                pass
        
        # Create a modern loading window
        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.attributes('-topmost', True)
        self.loading_window.overrideredirect(True)
        self.loading_window.configure(bg=self.colors['background'])
        
        # Add a subtle border
        border_frame = tk.Frame(self.loading_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        
        content_frame = tk.Frame(border_frame, bg=self.colors['background'])
        content_frame.pack(fill='both', expand=True, padx=8, pady=8)
        
        # Loading message
        message_label = tk.Label(content_frame, text="Looking up definition",
                                font=self.fonts['body'],
                                bg=self.colors['background'], fg=self.colors['text'])
        message_label.pack(pady=(12, 8))
        
        # Modern spinner
        self.current_spinner_index = 0
        spinner_font = self.fonts['heading'][0]
        self.spinner_label = tk.Label(content_frame, text=self.spinner_frames[self.current_spinner_index],
                                     font=(spinner_font, 24), 
                                     bg=self.colors['background'], fg=self.colors['primary'])
        self.spinner_label.pack(pady=(0, 12))
        
        # Start animation
        self.animate_spinner()
        
        # Center and size the window
        self.center_window(self.loading_window, 250, 110)
        
        # Make sure this window has focus
        self.loading_window.focus_force()
        self.loading_window.grab_set()

    def animate_spinner(self):
        """Animate the loading spinner"""
        if self.loading_window:
            try:
                self.current_spinner_index = (self.current_spinner_index + 1) % len(self.spinner_frames)
                self.spinner_label.config(text=self.spinner_frames[self.current_spinner_index])
                self.loading_window.after(100, self.animate_spinner)
            except tk.TclError:
                pass  # Window might have been destroyed

    def get_definition(self, word):
        """Fetch the word definition from database or API"""
        # Offline lookup first if database exists
        if os.path.exists(self.get_database_path()):
            try:
                conn = sqlite3.connect(self.get_database_path())
                c = conn.cursor()
                c.execute("SELECT lemma, part_of_speech, synset, definition, example FROM definitions WHERE lemma=? COLLATE NOCASE", (word,))
                rows = c.fetchall()
                conn.close()
                if rows:
                    meanings = {}
                    for row in rows:
                        lemma, pos, synset, definition_text, example_text = row
                        if pos not in meanings:
                            meanings[pos] = []
                        def_obj = {"definition": definition_text}
                        if example_text:
                            def_obj["example"] = example_text
                        meanings[pos].append(def_obj)
                    meanings_list = [{"partOfSpeech": pos, "definitions": defs} for pos, defs in meanings.items()]
                    data = {"word": word, "meanings": meanings_list}
                    self.root.after(0, self.hide_loading_window)
                    self.root.after(0, lambda: self.show_results(data))
                    return
            except Exception as e:
                print("Error querying offline database:", e)
        
        # Fallback to online API
        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            response = requests.get(url, timeout=5)
            data = response.json()
            self.root.after(0, self.hide_loading_window)
            if isinstance(data, list) and data:
                self.root.after(0, lambda: self.show_results(data[0]))
            elif isinstance(data, dict) and "title" in data:
                self.root.after(0, lambda: self.show_error(data["title"]))
            else:
                self.root.after(0, lambda: self.show_error("No definition found"))
        except requests.RequestException:
            self.root.after(0, self.hide_loading_window)
            self.root.after(0, lambda: self.show_error("Network error occurred"))

    def hide_loading_window(self):
        """Hide the loading window"""
        if self.loading_window:
            try:
                self.loading_window.destroy()
                self.loading_window = None
            except tk.TclError:
                pass

    def get_full_pos(self, pos):
        """Convert part of speech abbreviation to full form"""
        mapping = {
            'n': 'Noun',
            'v': 'Verb',
            'a': 'Adjective',
            's': 'Adjective Satellite',
            'r': 'Adverb'
        }
        if pos.lower() in mapping:
            return mapping[pos.lower()]
        return pos.capitalize()

    def show_results(self, data):
            """Display definition results"""
            if self.result_window:
                try:
                    self.result_window.destroy()
                except tk.TclError:
                    pass
            
            self.result_window = tk.Toplevel(self.root)
            self.result_window.attributes('-topmost', True)
            self.result_window.overrideredirect(True)
            self.result_window.configure(bg=self.colors['background'])
            
            # Add a subtle border
            border_frame = tk.Frame(self.result_window, bg=self.colors['border'])
            border_frame.pack(fill='both', expand=True, padx=1, pady=1)
            
            main_frame = tk.Frame(border_frame, bg=self.colors['background'])
            main_frame.pack(fill='both', expand=True)
            
            # Header with word and phonetic
            header_frame = tk.Frame(main_frame, bg=self.colors['background'])
            header_frame.pack(fill='x', padx=24, pady=(24, 8))
            
            # App name label
            app_label = tk.Label(header_frame, text="QUICK DEFINITION", 
                                font=self.fonts['tiny'], 
                                bg=self.colors['background'], fg=self.colors['muted'])
            app_label.pack(anchor='w')
            
            # Word display
            word_label = tk.Label(header_frame, text=data.get('word', '').capitalize(), 
                                font=self.fonts['heading'], 
                                bg=self.colors['background'], fg=self.colors['primary'])
            word_label.pack(anchor='w', pady=(8, 4))
            
            # Show phonetic if available
            if 'phonetic' in data and data['phonetic']:
                phonetic_label = tk.Label(header_frame, text=f"{data['phonetic']}",
                                        font=self.fonts['body'], 
                                        bg=self.colors['background'], fg=self.colors['muted'])
                phonetic_label.pack(anchor='w', pady=(0, 8))
            
            # Content area with scrolling
            content_frame = tk.Frame(main_frame, bg=self.colors['background'])
            content_frame.pack(fill='both', expand=True, padx=24, pady=(0, 16))
            
            # Canvas for scrolling
            canvas = tk.Canvas(content_frame, bg=self.colors['background'], highlightthickness=0)
            
            # Modern scrollbar styling
            style = ttk.Style()
            style.theme_use('clam')
            style.configure("Shadcn.Vertical.TScrollbar", 
                            background=self.colors['background'], 
                            troughcolor=self.colors['background'],
                            bordercolor=self.colors['background'],
                            arrowcolor=self.colors['muted'],
                            relief="flat")
            
            scrollbar = ttk.Scrollbar(content_frame, orient="vertical", 
                                    command=canvas.yview)
            try:
                # Try to apply the custom style, but fallback to default if not available
                scrollbar.configure(style="Shadcn.Vertical.TScrollbar")
            except tk.TclError:
                pass
                
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            
            # Frame for content inside canvas
            scrollable_frame = tk.Frame(canvas, bg=self.colors['background'])
            scrollable_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=canvas.winfo_reqwidth())
            
            # Responsive canvas width
            def on_canvas_configure(event):
                canvas.itemconfig(scrollable_window, width=event.width)
            canvas.bind("<Configure>", on_canvas_configure)
            
            # Auto-show scrollbar when needed
            def update_scrollbar_visibility():
                bbox = canvas.bbox("all")
                if bbox is None:
                    return
                content_height = bbox[3] - bbox[1]
                canvas_height = canvas.winfo_height()
                if content_height > canvas_height:
                    scrollbar.pack(side="right", fill="y")
                else:
                    scrollbar.pack_forget()
            
            # Update scroll region when content size changes
            def on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
                update_scrollbar_visibility()
            
            scrollable_frame.bind("<Configure>", on_frame_configure)
            
            # Mouse wheel scrolling with platform-specific handling
            def on_mousewheel(event):
                # Platform-specific scroll behavior
                if platform.system() == 'Darwin':  # macOS
                    canvas.yview_scroll(int(-1*(event.delta)), "units")
                else:  # Windows and most Linux
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                    
            self.result_window.bind_all("<MouseWheel>", on_mousewheel)
            
            # Additional bindings for Linux
            self.result_window.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            self.result_window.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
            
            # Remove wheel binding when window closes
            def cleanup_bindings():
                try:
                    self.result_window.unbind_all("<MouseWheel>")
                    self.result_window.unbind_all("<Button-4>")
                    self.result_window.unbind_all("<Button-5>")
                except tk.TclError:
                    pass
                
            self.result_window.bind("<Destroy>", lambda e: cleanup_bindings())
            
            # Display definitions by part of speech
            for idx, meaning in enumerate(data.get('meanings', [])):
                pos = meaning.get('partOfSpeech', '')
                
                # Part of speech label
                pos_label = tk.Label(scrollable_frame, text=self.get_full_pos(pos),
                                    font=self.fonts['subheading'],
                                    bg=self.colors['background'], fg=self.colors['warning'])
                pos_label.pack(anchor='w', pady=(16 if idx > 0 else 0, 8))
                
                # Divider
                divider = tk.Frame(scrollable_frame, height=1, bg=self.colors['border'])
                divider.pack(fill='x', pady=(0, 12))
                
                # Group definitions by their text to avoid duplication; accumulate examples per definition
                definitions = meaning.get('definitions', [])
                grouped_defs = {}
                for defn in definitions:
                    def_text = defn.get('definition', '')
                    example = defn.get('example')
                    if def_text in grouped_defs:
                        if example and example not in grouped_defs[def_text]:
                            grouped_defs[def_text].append(example)
                    else:
                        grouped_defs[def_text] = []
                        if example:
                            grouped_defs[def_text].append(example)
                i = 1
                for def_text, examples in grouped_defs.items():
                    # Use a Grid layout inside a frame for better control
                    item_frame = tk.Frame(scrollable_frame, bg=self.colors['background'])
                    item_frame.pack(fill='x', pady=(0, 12), padx=(8, 0))
                    item_frame.grid_columnconfigure(1, weight=1)  # Make definition column expandable
                    
                    # Number in its own cell with fixed width
                    num_label = tk.Label(item_frame, text=f"{i}.",
                                    font=self.fonts['body'],
                                    width=2, anchor='e',
                                    bg=self.colors['background'], fg=self.colors['warning'])
                    num_label.grid(row=0, column=0, sticky='ne', padx=(0, 10))
                    
                    # Definition text in second column
                    def_label = tk.Label(item_frame, text=def_text,
                                        font=self.fonts['body'],
                                        bg=self.colors['background'], fg=self.colors['text'],
                                        wraplength=420, justify='left', anchor='w')
                    def_label.grid(row=0, column=1, sticky='w')
                    
                    # Display each example below the definition text if available
                    current_row = 1
                    for ex in examples:
                        ex_label = tk.Label(item_frame, text=f'"{ex}"',
                                        font=(self.fonts['body'][0], self.fonts['body'][1], 'italic'),
                                        bg=self.colors['background'], fg=self.colors['muted'],
                                        wraplength=400, justify='left', anchor='w')
                        ex_label.grid(row=current_row, column=1, sticky='w', pady=(4, 0))
                        current_row += 1
                    i += 1
            
            # Navigation/control buttons at the bottom
            control_frame = tk.Frame(main_frame, bg=self.colors['background'])
            control_frame.pack(fill='x', padx=24, pady=(0, 16))
            
            # Close button
            close_btn = tk.Button(control_frame, text="Close",
                                font=self.fonts['small'],
                                bg=self.colors['card'], fg=self.colors['text'],
                                activebackground=self.colors['border'],
                                activeforeground=self.colors['text'],
                                bd=0, padx=16, pady=6,
                                command=self.close_result_window)
            close_btn.pack(side='right')
            
            # Search again button
            search_btn = tk.Button(control_frame, text="New Search",
                                font=self.fonts['small'],
                                bg=self.colors['primary'], fg=self.colors['text'],
                                activebackground=self.colors['secondary'],
                                activeforeground=self.colors['text'],
                                bd=0, padx=16, pady=6,
                                command=self.show_input)
            search_btn.pack(side='right', padx=(0, 8))
            
            # Close button in top-right corner for quick exit
            exit_btn = tk.Button(header_frame, text="×", anchor="center",
                                font=(self.fonts['heading'][0], 16),
                                bg=self.colors['background'], fg=self.colors['muted'],
                                activebackground=self.colors['error'],
                                activeforeground=self.colors['text'],
                                bd=0,
                                command=self.close_result_window)
            exit_btn.place(relx=1.0, rely=0.0, anchor='ne', width=30, height=30)
            
            # Keyboard shortcuts
            self.result_window.bind('<Escape>', lambda e: self.close_result_window())
            
            # Position and display window
            self.center_window(self.result_window, 550, 500)
            self.result_window.update()
            self.result_window.focus_force()
            self.result_window.grab_set()  # Ensure this window gets all keyboard events

    def close_result_window(self):
        """Close the results window"""
        if self.result_window:
            try:
                self.result_window.grab_release()
                self.result_window.destroy()
                self.result_window = None
            except tk.TclError:
                pass

    def show_error(self, message):
        """Display an error message window"""
        if self.error_window:
            try:
                self.error_window.destroy()
            except tk.TclError:
                pass
                
        self.error_window = tk.Toplevel(self.root)
        self.error_window.attributes('-topmost', True)
        self.error_window.overrideredirect(True)
        self.error_window.configure(bg=self.colors['background'])
        
        # Add border
        border_frame = tk.Frame(self.error_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        
        main_frame = tk.Frame(border_frame, bg=self.colors['background'])
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Error icon
        icon_label = tk.Label(main_frame, text="⚠️", 
                            font=(self.fonts['heading'][0], 24),
                            bg=self.colors['background'], fg=self.colors['error'])
        icon_label.pack(pady=(0, 12))
        
        # Error message
        message_label = tk.Label(main_frame, text=message,
                            font=self.fonts['body'],
                            bg=self.colors['background'], fg=self.colors['text'],
                            wraplength=250, justify='center')
        message_label.pack(pady=(0, 16))
        
        # Button frame
        button_frame = tk.Frame(main_frame, bg=self.colors['background'])
        button_frame.pack()
        
        # Try again button
        retry_btn = tk.Button(button_frame, text="Try Again",
                            font=self.fonts['small'],
                            bg=self.colors['primary'], fg=self.colors['text'],
                            activebackground=self.colors['secondary'],
                            activeforeground=self.colors['text'],
                            bd=0, padx=16, pady=6,
                            command=self.show_input)
        retry_btn.pack(side='left', padx=(0, 8))
        
        # Close button
        close_btn = tk.Button(button_frame, text="Close",
                            font=self.fonts['small'],
                            bg=self.colors['card'], fg=self.colors['text'],
                            activebackground=self.colors['border'],
                            activeforeground=self.colors['text'],
                            bd=0, padx=16, pady=6,
                            command=self.close_error_window)
        close_btn.pack(side='left')
        
        # Keyboard shortcuts
        self.error_window.bind('<Escape>', lambda e: self.close_error_window())
        self.error_window.bind('<Return>', lambda e: self.show_input())
        
        # Size and position
        self.center_window(self.error_window, 320, 200)
        self.error_window.update()
        self.error_window.focus_force()
        self.error_window.grab_set()  # Ensure this window gets all keyboard events

    def close_error_window(self):
        """Close the error window"""
        if self.error_window:
            try:
                self.error_window.grab_release()
                self.error_window.destroy()
                self.error_window = None
            except tk.TclError:
                pass

if __name__ == "__main__":
    app = QuickDefinitionApp()
    print('Quick Definition App started! Press Ctrl+Alt+D (or Cmd+Alt+D on macOS) to activate.')
    try:
        app.run()
    except Exception as e:
        print(f"Error running application: {e}")
