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
import re

if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    
    SW_SHOW = 5
    SW_SHOWNORMAL = 1
    
    def force_window_focus(hwnd):
        user32 = ctypes.WinDLL('user32')
        user32.SetForegroundWindow(hwnd)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetActiveWindow(hwnd)

class AutoHeightText(tk.Text):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.bind('<Configure>', self._adjust_height)
    
    def _adjust_height(self, event=None):
        num_lines = self.count("1.0", "end", "displaylines")[0]
        self.config(height=int(num_lines))

class QuickDefinitionApp:
    def __init__(self):
        self.colors = {
            'background': '#1a1a1a',
            'card': '#222222',
            'primary': '#0ea5e9',
            'secondary': '#6366f1',
            'muted': '#71717a',
            'text': '#f8fafc',
            'border': '#27272a',
            'input': '#27272a',
            'error': '#ef4444',
            'success': '#22c55e',
            'warning': '#f59e0b',
        }
        
        self.setup_fonts()
        self.ensure_data_directory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.input_window = None
        self.loading_window = None
        self.result_window = None
        self.error_window = None
        self.suggestion_popup = None
        self.suggestion_after_id = None
        self.active_fetch_thread = None
        self.selected_suggestion_index = -1
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_spinner_index = 0
        self.history = []  # Navigation history
        self.setup_input_window()
        self.setup_hotkeys()
        if not os.path.exists(self.get_database_path()):
            messagebox.showinfo(
                "Database Not Found", 
                "WordNet database not found. The app will use online API only.\n\nPlease run the database setup script (build_database.py) if you want offline functionality."
            )

    def setup_fonts(self):
        system = platform.system()
        self.fonts = {
            'heading': ('Noto Sans', 16, 'bold'),
            'subheading': ('Noto Sans', 14, 'bold'),
            'body': ('Noto Sans', 12),
            'small': ('Noto Sans', 10),
            'tiny': ('Noto Sans', 9),
            'monospace': ('Monospace', 12),
        }
        if system == 'Windows':
            self.fonts = {
                'heading': ('Segoe UI', 16, 'bold'),
                'subheading': ('Segoe UI', 14, 'bold'),
                'body': ('Segoe UI', 12),
                'small': ('Segoe UI', 10),
                'tiny': ('Segoe UI', 9),
                'monospace': ('Consolas', 12),
            }
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
        system = platform.system()
        if system == 'Windows':
            base_dir = os.path.join(os.environ.get('APPDATA', ''), 'QuickDefinition')
        elif system == 'Darwin':
            base_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'QuickDefinition')
        else:
            base_dir = os.path.join(os.path.expanduser('~'), '.quickdefinition')
        return os.path.join(base_dir, 'wordnet.db')

    def ensure_data_directory(self):
        db_path = self.get_database_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def setup_hotkeys(self):
        system = platform.system()
        hotkey_combo = '<ctrl>+<alt>+d' if system != 'Darwin' else '<cmd>+<alt>+d'
        self.hotkey = keyboard.GlobalHotKeys({hotkey_combo: self.show_input})
        try:
            self.hotkey.start()
        except Exception as e:
            print(f"Error setting up hotkey: {e}")
            messagebox.showwarning(
                "Hotkey Registration Failed", 
                f"Failed to register global hotkey: {e}\n\nYou'll need to use the app interface directly."
            )

    def quit(self):
        try:
            self.hotkey.stop()
        except:
            pass
        self.root.quit()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

    def create_rounded_rect(self, canvas, x1, y1, x2, y2, radius=25, **kwargs):
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
        self.input_window = tk.Toplevel(self.root)
        self.input_window.withdraw()
        self.input_window.attributes('-topmost', True)
        self.input_window.overrideredirect(True)
        self.input_window.configure(bg=self.colors['background'])
        border_frame = tk.Frame(self.input_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        content_frame = tk.Frame(border_frame, bg=self.colors['background'])
        content_frame.pack(fill='both', expand=True)
        title_frame = tk.Frame(content_frame, bg=self.colors['background'])
        title_frame.pack(fill='x', padx=16, pady=(16, 8))
        logo_label = tk.Label(title_frame, text="📚", font=self.fonts['heading'], bg=self.colors['background'], fg=self.colors['primary'])
        logo_label.pack(side='left', padx=(0, 8))
        title_label = tk.Label(title_frame, text="Quick Definition", font=self.fonts['heading'], bg=self.colors['background'], fg=self.colors['text'])
        title_label.pack(side='left')
        search_frame = tk.Frame(content_frame, bg=self.colors['background'])
        search_frame.pack(padx=16, pady=(0, 16), fill='both')
        input_border = tk.Frame(search_frame, bg=self.colors['border'], padx=1, pady=1)
        input_border.pack(fill='x')
        input_frame = tk.Frame(input_border, bg=self.colors['input'], padx=12, pady=8)
        input_frame.pack(fill='x')
        self.entry = tk.Entry(input_frame, width=30, font=self.fonts['body'], bg=self.colors['input'], fg=self.colors['text'], bd=0, insertbackground=self.colors['text'])
        self.entry.pack(fill='both')
        self.entry.insert(0, "Type a word to define...")
        self.entry.config(fg=self.colors['muted'])
        self.entry.bind("<FocusIn>", self.on_entry_focus_in)
        self.entry.bind("<FocusOut>", self.on_entry_focus_out)
        self.entry.bind('<Return>', self.on_return)
        self.entry.bind('<Escape>', lambda e: self.hide_input_window() or "break")
        self.entry.bind("<KeyRelease>", self.on_key_release)
        self.entry.bind("<Down>", self.navigate_suggestions_down)
        self.entry.bind("<Up>", self.navigate_suggestions_up)
        self.entry.bind("<Tab>", self.select_current_suggestion)
        self.input_window.bind('<Escape>', lambda e: self.hide_input_window() or "break")
        shortcut_text = "Ctrl+Alt+D" if platform.system() != 'Darwin' else "Cmd+Alt+D"
        shortcut_frame = tk.Frame(content_frame, bg=self.colors['background'])
        shortcut_frame.pack(fill='x', padx=16, pady=(0, 8))
        shortcut_label = tk.Label(shortcut_frame, text=f"Global: {shortcut_text} | Press Esc to close", font=self.fonts['tiny'], bg=self.colors['background'], fg=self.colors['muted'])
        shortcut_label.pack(side='right')
        self.center_window(self.input_window, 400, 140)

    def on_entry_focus_in(self, event):
        if self.entry.get() == "Type a word to define...":
            self.entry.delete(0, tk.END)
            self.entry.config(fg=self.colors['text'])

    def on_entry_focus_out(self, event):
        if not self.entry.get():
            self.entry.insert(0, "Type a word to define...")
            self.entry.config(fg=self.colors['muted'])
        if self.suggestion_popup:
            self.root.after(100, self.check_focus_for_suggestions)

    def on_return(self, event):
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            return self.select_current_suggestion(event)
        else:
            self.fetch_definition()
            return "break"

    def check_focus_for_suggestions(self):
        try:
            if self.suggestion_popup and self.suggestion_popup.focus_get() is None:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
        except:
            self.suggestion_popup = None

    def center_window(self, window, width, height):
        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 3
        window.geometry(f'{width}x{height}+{x}+{y}')

    def show_input(self):
        self.hide_all_windows()
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "Type a word to define...")
        self.entry.config(fg=self.colors['muted'])
        self.input_window.deiconify()
        if platform.system() == 'win32':
            self.input_window.attributes('-topmost', True)
            self.input_window.focus_force()
            self.input_window.after(50, self.windows_force_focus)
            self.input_window.after(150, self.windows_force_focus)
            self.input_window.after(300, self.windows_force_focus)
        else:
            self.input_window.lift()
            self.input_window.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
        self.input_window.grab_set()

    def windows_force_focus(self):
        try:
            self.input_window.lift()
            self.input_window.focus_force()
            if 'force_window_focus' in globals() and platform.system() == 'win32':
                hwnd = int(self.input_window.winfo_id())
                force_window_focus(hwnd)
            self.entry.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
        except Exception as e:
            print(f"Focus error: {e}")

    def force_entry_focus(self):
        try:
            self.input_window.focus_force()
            self.entry.focus_set()
            self.entry.selection_range(0, tk.END)
            current_state = self.entry["state"]
            self.entry.configure(state="disabled")
            self.entry.after(1, lambda: self.entry.configure(state=current_state))
            if platform.system() == 'win32':
                self.entry.after(5, lambda: self.input_window.lift())
        except tk.TclError:
            pass

    def set_input_focus(self):
        self.input_window.focus_force()
        self.entry.focus_set()
        self.entry.selection_range(0, tk.END)
        self.input_window.grab_set()
        self.input_window.attributes('-topmost', True)

    def hide_all_windows(self, clear_history=True):
        if self.suggestion_popup:
            try:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
            except tk.TclError:
                pass
        for window in [self.result_window, self.error_window]:
            if window:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
        if clear_history:
            self.history = []
        self.result_window = None
        self.error_window = None
        for window in [self.input_window, self.loading_window]:
            if window:
                try:
                    window.withdraw()
                except tk.TclError:
                    pass

    def hide_input_window(self):
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
        if event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Escape', 'Return', 'Up', 'Down', 'Tab'):
            return
        if self.suggestion_after_id:
            self.entry.after_cancel(self.suggestion_after_id)
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
                self.selected_suggestion_index = (self.selected_suggestion_index + 1) % len(self.suggestion_items)
                self.highlight_selected_suggestion()
            return "break"  # Prevent default behavior
        return None

    def navigate_suggestions_up(self, event):
        """Navigate up through suggestions with Up arrow key"""
        if self.suggestion_popup:
            if hasattr(self, 'suggestion_items') and self.suggestion_items:
                if self.selected_suggestion_index <= 0:
                    self.selected_suggestion_index = len(self.suggestion_items) - 1
                else:
                    self.selected_suggestion_index -= 1
                self.highlight_selected_suggestion()
            return "break"  # Prevent default behavior
        return None

    def highlight_selected_suggestion(self):
        if not hasattr(self, 'suggestion_items') or not self.suggestion_items:
            return
        for i, (frame, label) in enumerate(self.suggestion_items):
            if i == self.selected_suggestion_index:
                frame.configure(bg=self.colors['primary'])
                label.configure(bg=self.colors['primary'])
            else:
                frame.configure(bg=self.colors['background'])
                label.configure(bg=self.colors['background'])

    def select_current_suggestion(self, event=None):
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            try:
                word = self.suggestion_items[self.selected_suggestion_index][1]['text']
                self.entry.delete(0, tk.END)
                self.entry.insert(0, word)
                self.entry.configure(fg=self.colors['text'])
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
                self.selected_suggestion_index = -1
                return "break"
            except (IndexError, KeyError, tk.TclError):
                pass
        return None

    def show_suggestions(self):
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
        if not os.path.exists(self.get_database_path()):
            return
        try:
            conn = sqlite3.connect(self.get_database_path())
            c = conn.cursor()
            c.execute("SELECT DISTINCT lemma FROM definitions WHERE lemma LIKE ? COLLATE NOCASE LIMIT 8", (word_fragment + '%',))
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
        if hasattr(self, 'last_suggestions') and self.last_suggestions == suggestions and self.suggestion_popup:
            return
        self.last_suggestions = suggestions
        if self.suggestion_popup:
            for child in self.suggestion_container.winfo_children():
                child.destroy()
            self.suggestion_items = []
        else:
            self.suggestion_popup = tk.Toplevel(self.input_window)
            self.suggestion_popup.overrideredirect(True)
            self.suggestion_popup.configure(bg=self.colors['border'])
            self.suggestion_popup.attributes('-topmost', True)
            x = self.input_window.winfo_x() + 16
            y = self.input_window.winfo_y() + 95
            width = self.input_window.winfo_width() - 32
            popup_height = len(suggestions) * 36 + 8
            self.suggestion_popup.geometry(f"{width}x{popup_height}+{x}+{y}")
            inner_frame = tk.Frame(self.suggestion_popup, bg=self.colors['background'], padx=1, pady=1)
            inner_frame.pack(fill='both', expand=True)
            self.suggestion_container = tk.Frame(inner_frame, bg=self.colors['background'])
            self.suggestion_container.pack(fill='both', expand=True)
            self.suggestion_popup.bind('<Escape>', lambda event: (self.suggestion_popup.destroy() or "break"))
        self.selected_suggestion_index = -1
        self.suggestion_items = []
        for suggestion in suggestions:
            item_frame = tk.Frame(self.suggestion_container, bg=self.colors['background'], padx=12, pady=8, height=36)
            item_frame.pack(fill='x')
            item_frame.pack_propagate(False)
            label = tk.Label(item_frame, text=suggestion, font=self.fonts['body'], bg=self.colors['background'], fg=self.colors['text'], anchor='w')
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
        self.suggestion_container.update_idletasks()
        x = self.input_window.winfo_x() + 16
        y = self.input_window.winfo_y() + 95
        width = self.input_window.winfo_width() - 32
        actual_height = len(self.suggestion_items) * 36 + 8
        self.suggestion_popup.geometry(f"{width}x{actual_height}+{x}+{y}")

    def fetch_definition(self, word=None):
        if word is None:
            word = self.entry.get().strip()
        if word == "Type a word to define..." or not word:
            return
        self.hide_input_window()
        if self.suggestion_popup and self.selected_suggestion_index >= 0:
            try:
                word = self.suggestion_items[self.selected_suggestion_index][1]['text']
            except (IndexError, KeyError, tk.TclError):
                pass
            try:
                self.suggestion_popup.destroy()
                self.suggestion_popup = None
            except tk.TclError:
                pass
        if self.active_fetch_thread and self.active_fetch_thread.is_alive():
            return
        self.hide_all_windows(clear_history=False)
        self.show_loading_window()
        self.active_fetch_thread = threading.Thread(target=self.get_definition, args=(word,), daemon=True)
        self.active_fetch_thread.start()

    def show_loading_window(self):
        if self.loading_window:
            try:
                self.loading_window.destroy()
            except tk.TclError:
                pass
        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.attributes('-topmost', True)
        self.loading_window.overrideredirect(True)
        self.loading_window.configure(bg=self.colors['background'])
        border_frame = tk.Frame(self.loading_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        content_frame = tk.Frame(border_frame, bg=self.colors['background'])
        content_frame.pack(fill='both', expand=True, padx=8, pady=8)
        message_label = tk.Label(content_frame, text="Looking up definition", font=self.fonts['body'], bg=self.colors['background'], fg=self.colors['text'])
        message_label.pack(pady=(12, 8))
        self.current_spinner_index = 0
        spinner_font = self.fonts['heading'][0]
        self.spinner_label = tk.Label(content_frame, text=self.spinner_frames[self.current_spinner_index], font=(spinner_font, 24), bg=self.colors['background'], fg=self.colors['primary'])
        self.spinner_label.pack(pady=(0, 12))
        self.animate_spinner()
        self.center_window(self.loading_window, 250, 110)
        self.loading_window.focus_force()
        self.loading_window.grab_set()

    def animate_spinner(self):
        if self.loading_window:
            try:
                self.current_spinner_index = (self.current_spinner_index + 1) % len(self.spinner_frames)
                self.spinner_label.config(text=self.spinner_frames[self.current_spinner_index])
                self.loading_window.after(100, self.animate_spinner)
            except tk.TclError:
                pass

    def get_definition(self, word):
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
        if self.loading_window:
            try:
                self.loading_window.destroy()
                self.loading_window = None
            except tk.TclError:
                pass

    def get_full_pos(self, pos):
        mapping = {
            'n': 'Noun',
            'v': 'Verb',
            'a': 'Adjective',
            's': 'Adjective Satellite',
            'r': 'Adverb'
        }
        return mapping.get(pos.lower(), pos.capitalize())

    def show_results(self, data):
        if self.result_window:
            try:
                self.result_window.destroy()
            except tk.TclError:
                pass
        self.result_window = tk.Toplevel(self.root)
        self.result_window.attributes('-topmost', True)
        self.result_window.overrideredirect(True)
        self.result_window.configure(bg=self.colors['background'])
        self.result_window.current_word = data.get('word', '').lower()
        border_frame = tk.Frame(self.result_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        main_frame = tk.Frame(border_frame, bg=self.colors['background'])
        main_frame.pack(fill='both', expand=True)
        header_frame = tk.Frame(main_frame, bg=self.colors['background'])
        header_frame.pack(fill='x', padx=24, pady=(24, 8))
        app_label = tk.Label(header_frame, text="QUICK DEFINITION", font=self.fonts['tiny'], bg=self.colors['background'], fg=self.colors['muted'])
        app_label.pack(anchor='w')
        word_label = tk.Label(header_frame, text=data.get('word', '').capitalize(), font=self.fonts['heading'], bg=self.colors['background'], fg=self.colors['primary'])
        word_label.pack(anchor='w', pady=(8, 4))
        if 'phonetic' in data and data['phonetic']:
            phonetic_label = tk.Label(header_frame, text=f"{data['phonetic']}", font=self.fonts['body'], bg=self.colors['background'], fg=self.colors['muted'])
            phonetic_label.pack(anchor='w', pady=(0, 8))
        content_frame = tk.Frame(main_frame, bg=self.colors['background'])
        content_frame.pack(fill='both', expand=True, padx=24, pady=(0, 16))
        canvas = tk.Canvas(content_frame, bg=self.colors['background'], highlightthickness=0)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Shadcn.Vertical.TScrollbar", background=self.colors['background'], troughcolor=self.colors['background'], bordercolor=self.colors['background'], arrowcolor=self.colors['muted'], relief="flat")
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        try:
            scrollbar.configure(style="Shadcn.Vertical.TScrollbar")
        except tk.TclError:
            pass
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['background'])
        scrollable_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=canvas.winfo_reqwidth())
        def on_canvas_configure(event):
            canvas.itemconfig(scrollable_window, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)
        def update_scrollbar_visibility():
            bbox = canvas.bbox("all")
            if bbox:
                content_height = bbox[3] - bbox[1]
                canvas_height = canvas.winfo_height()
                if content_height > canvas_height:
                    scrollbar.pack(side="right", fill="y")
                else:
                    scrollbar.pack_forget()
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            update_scrollbar_visibility()
        scrollable_frame.bind("<Configure>", on_frame_configure)
        def on_mousewheel(event):
            if platform.system() == 'Darwin':
                canvas.yview_scroll(int(-1*(event.delta)), "units")
            else:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.result_window.bind_all("<MouseWheel>", on_mousewheel)
        self.result_window.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        self.result_window.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        def cleanup_bindings():
            try:
                self.result_window.unbind_all("<MouseWheel>")
                self.result_window.unbind_all("<Button-4>")
                self.result_window.unbind_all("<Button-5>")
            except tk.TclError:
                pass
        self.result_window.bind("<Destroy>", lambda e: cleanup_bindings())
        for idx, meaning in enumerate(data.get('meanings', [])):
            pos = meaning.get('partOfSpeech', '')
            pos_label = tk.Label(scrollable_frame, text=self.get_full_pos(pos), font=self.fonts['subheading'], bg=self.colors['background'], fg=self.colors['warning'])
            pos_label.pack(anchor='w', pady=(16 if idx > 0 else 0, 8))
            divider = tk.Frame(scrollable_frame, height=1, bg=self.colors['border'])
            divider.pack(fill='x', pady=(0, 12))
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
                item_frame = tk.Frame(scrollable_frame, bg=self.colors['background'])
                item_frame.pack(fill='x', pady=(0, 12), padx=(8, 0))
                item_frame.grid_columnconfigure(1, weight=1)
                
                num_label = tk.Label(item_frame, text=f"{i}.", 
                                    font=self.fonts['body'],
                                    width=2, anchor='e',
                                    bg=self.colors['background'], fg=self.colors['warning'])
                num_label.grid(row=0, column=0, sticky='ne', padx=(0, 10))
                
                def_text_widget = AutoHeightText(item_frame, 
                        font=self.fonts['body'],
                        bg=self.colors['background'], fg=self.colors['text'],
                        wrap=tk.WORD, width=50,
                        borderwidth=0, highlightthickness=0)
                def_text_widget.insert(tk.END, def_text)
                def_text_widget.tag_configure("hover", foreground=self.colors['primary'], underline=1)
                def_text_widget.config(state=tk.DISABLED)
                def_text_widget.grid(row=0, column=1, sticky='w')
                
                # Bind hover events
                def_text_widget.bind("<Motion>", 
                                lambda e, tw=def_text_widget: self.on_text_hover(e, tw))
                def_text_widget.bind("<Leave>", 
                                lambda e, tw=def_text_widget: tw.tag_remove("hover", "1.0", "end"))
                def_text_widget.bind('<Button-1>', 
                                lambda e, tw=def_text_widget: self.on_definition_click(e, tw))
                current_row = 1
                for ex in examples:
                    ex_label = tk.Label(item_frame, text=f'"{ex}"', font=(self.fonts['body'][0], self.fonts['body'][1], 'italic'), bg=self.colors['background'], fg=self.colors['muted'], wraplength=400, justify='left', anchor='w')
                    ex_label.grid(row=current_row, column=1, sticky='w', pady=(4, 0))
                    current_row += 1
                i += 1
        control_frame = tk.Frame(main_frame, bg=self.colors['background'])
        control_frame.pack(fill='x', padx=24, pady=(0, 16))
        close_btn = tk.Button(control_frame, text="Close", font=self.fonts['small'], bg=self.colors['card'], fg=self.colors['text'], activebackground=self.colors['border'], activeforeground=self.colors['text'], bd=0, padx=16, pady=6, command=self.close_result_window)
        close_btn.pack(side='right')
        search_btn = tk.Button(control_frame, text="New Search", font=self.fonts['small'], bg=self.colors['primary'], fg=self.colors['text'], activebackground=self.colors['secondary'], activeforeground=self.colors['text'], bd=0, padx=16, pady=6, command=self.show_input)
        search_btn.pack(side='right', padx=(0, 8))
        if self.history:
            go_back_btn = tk.Button(control_frame, text="Go Back", font=self.fonts['small'], bg=self.colors['card'], fg=self.colors['text'], activebackground=self.colors['border'], activeforeground=self.colors['text'], bd=0, padx=16, pady=6, command=self.go_back)
            go_back_btn.pack(side='right', padx=(0, 8))
        exit_btn = tk.Button(header_frame, text="×", font=(self.fonts['heading'][0], 16), bg=self.colors['background'], fg=self.colors['muted'], activebackground=self.colors['error'], activeforeground=self.colors['text'], bd=0, command=self.close_result_window)
        exit_btn.place(relx=1.0, rely=0.0, anchor='ne', width=30, height=30)
        self.result_window.bind('<Escape>', lambda e: (self.close_result_window() or "break"))
        self.center_window(self.result_window, 550, 500)
        self.result_window.update()
        self.result_window.focus_force()
        self.result_window.grab_set()

    def on_text_hover(self, event, text_widget):
        """Handle hover effects on definition text"""
        text_widget.tag_remove("hover", "1.0", "end")
        index = text_widget.index(f"@{event.x},{event.y}")
        start = text_widget.index(f"{index} wordstart")
        end = text_widget.index(f"{index} wordend")
        word = text_widget.get(start, end).strip()
        
        if word and re.search(r'[A-Za-z]', word):
            text_widget.configure(cursor="hand2")
            text_widget.tag_add("hover", start, end)
        else:
            text_widget.configure(cursor="xterm")
            
    def on_definition_click(self, event, text_widget):
        """Handle clicks on words in definitions"""
        text_widget.tag_remove("hover", "1.0", "end")
        index = text_widget.index(f"@{event.x},{event.y}")
        start = text_widget.index(f"{index} wordstart")
        end = text_widget.index(f"{index} wordend")
        word = text_widget.get(start, end).strip()
        
        if word and re.search(r'[A-Za-z]', word):
            current_window = text_widget.winfo_toplevel()
            previous_word = current_window.current_word
            self.history.append(previous_word)
            self.fetch_definition(word)

    def go_back(self):
        if self.history:
            previous_word = self.history.pop()
            self.fetch_definition(previous_word)

    def close_result_window(self):
        self.hide_all_windows()

    def show_error(self, message):
        if self.error_window:
            try:
                self.error_window.destroy()
            except tk.TclError:
                pass
        self.error_window = tk.Toplevel(self.root)
        self.error_window.attributes('-topmost', True)
        self.error_window.overrideredirect(True)
        self.error_window.configure(bg=self.colors['background'])
        border_frame = tk.Frame(self.error_window, bg=self.colors['border'])
        border_frame.pack(fill='both', expand=True, padx=1, pady=1)
        main_frame = tk.Frame(border_frame, bg=self.colors['background'], padx=20, pady=20)
        main_frame.pack(fill='both', expand=True)
        icon_label = tk.Label(main_frame, text="⚠️", font=(self.fonts['heading'][0], 24), bg=self.colors['background'], fg=self.colors['error'])
        icon_label.pack(pady=(0, 12))
        message_label = tk.Label(main_frame, text=message, font=self.fonts['body'], bg=self.colors['background'], fg=self.colors['text'], wraplength=250, justify='center')
        message_label.pack(pady=(0, 16))
        button_frame = tk.Frame(main_frame, bg=self.colors['background'])
        button_frame.pack()
        retry_btn = tk.Button(button_frame, text="Try Again", font=self.fonts['small'], bg=self.colors['primary'], fg=self.colors['text'], activebackground=self.colors['secondary'], activeforeground=self.colors['text'], bd=0, padx=16, pady=6, command=self.show_input)
        retry_btn.pack(side='left', padx=(0, 8))
        close_btn = tk.Button(button_frame, text="Close", font=self.fonts['small'], bg=self.colors['card'], fg=self.colors['text'], activebackground=self.colors['border'], activeforeground=self.colors['text'], bd=0, padx=16, pady=6, command=self.close_error_window)
        close_btn.pack(side='left')
        self.error_window.bind('<Escape>', lambda e: (self.close_error_window() or "break"))
        self.error_window.bind('<Return>', lambda e: self.show_input())
        self.center_window(self.error_window, 320, 200)
        self.error_window.update()
        self.error_window.focus_force()
        self.error_window.grab_set()

    def close_error_window(self):
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
