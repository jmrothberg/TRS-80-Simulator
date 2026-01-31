#JMR TRS-80 BASIC simulator
#Fully working AUG 19, 2024
#Added step, debug window and variables window
#AUG 21 added multiple commands per line and additonal functions
#AUG 23 added graphics commands
#AUG 27 corrected POINT function, explicit LET, GUI, corrected coordinates, variables robust
#SEP 5 new eval function that handled nested parentheses better and faster can do B((i-1)*15)
#Sept 7 needed for mac to run on python 3.11.4 the new one 3.12.x was not working in pyinstaller buggy
#July 6 2025 added Ollama support, added ability to type into the main screen and original TRS-80 prompt
#Sept 24 2025 Adjusted for 7" screen, no 2x scaling on Raspberry Pi, added LLM support error checking
#Jan 21 2026 Added Hailo-10H AI accelerator support for LLM inference on Raspberry Pi
#           - Integrated HailoRT runtime for GPU-accelerated AI models
#           - Added auto-download of Hailo-compiled models (qwen2.5, llama3.2, etc.)
#           - Optimized for ARM64 Raspberry Pi 5 with PCIe Hailo-10H card
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import re
import random
import os
import math
import time
import platform
from TRS80LLMSupport import TRS80LLMSupport
PIXEL_SIZE = 6  # Reduced from 6 to 4 for smaller screen
INITIAL_WIDTH = 768  # 128 pixels * 6 = 774 to accommodate coordinates 1-128
INITIAL_HEIGHT = 288  # Reduced from 288 to 192 for 7" screen

class TRS80Simulator:
    def __init__(self, master):
        self.master = master
        master.title("JMR's TRS-80 Simulator")

        # Detect if running on Raspberry Pi to disable 2x scaling
        self.is_raspberry_pi = self.detect_raspberry_pi()

        # Add scaling factor
        self.scale_factor = 1
        self.base_font_size = 14  # Reduced from 14 to 10 for 7" screen
        self.input_font_size = 14  # Reduced from 14 to 10 for 7" screen

        # Set up the main frame
        self.main_frame = tk.Frame(master, bg="lightgrey")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create a frame to hold the TRS-80 screen
        self.screen_frame = tk.Frame(self.main_frame, bg="gray", padx=5, pady=5)
        self.screen_frame.pack(pady=0)

        # Create the TRS-80 screen (128x48 pixels, but each pixel is 4 screen pixels for 7" screen)
        self.pixel_size = PIXEL_SIZE * self.scale_factor  # Each pixel is 4 screen pixels, scaled
        self.screen = tk.Canvas(self.screen_frame, width=INITIAL_WIDTH * self.scale_factor, height=INITIAL_HEIGHT * self.scale_factor, bg="black", highlightthickness=0)
        self.screen.pack()
        
        # Make the Canvas focusable and bind click event
        self.screen.config(takefocus=1)
        self.screen.bind("<Button-1>", lambda event: self.set_screen_focus())

        # Create the BASIC input area - reduced size for 7" screen
        self.input_area = scrolledtext.ScrolledText(self.main_frame, width=64, height=4, bg="lightgray", fg="black", font=("Courier", self.input_font_size))
        self.input_area.pack(pady=5)
        
        # Add right-click menu for cut, copy, paste
        self.create_right_click_menu()

        # Create buttons - more compact for 7" screen
        button_frame = tk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, padx=0, pady=0)  # Reduced padding

        self.run_button = tk.Button(button_frame, text="Run", command=self.run_program, font=("Arial", 8), width=4, height=1)
        self.run_button.pack(side=tk.LEFT, padx=1)  # Further reduced padding

        # In the __init__ method, add this button:
        self.reset_button = tk.Button(button_frame, text="Reset", command=self.reset_program, font=("Arial", 8), width=4, height=1)
        self.reset_button.pack(side=tk.LEFT, padx=1)

        # Add Stop button
        self.stop_button = tk.Button(button_frame, text="Stop", command=self.stop_program, state=tk.DISABLED, font=("Arial", 8), width=10, height=1)
        self.stop_button.pack(side=tk.LEFT, padx=1)

        # Add Step button
        self.step_button = tk.Button(button_frame, text="Step", command=self.step_program, state=tk.DISABLED, font=("Arial", 8), width=4, height=1)
        self.step_button.pack(side=tk.LEFT, padx=1)

        self.new_button = tk.Button(button_frame, text="List", command=self.list_program, font=("Arial", 8), width=4, height=1)
        self.new_button.pack(side=tk.LEFT, padx=1)

        self.clear_button = tk.Button(button_frame, text="Clear", command=self.clear_screen, font=("Arial", 8), width=4, height=1)
        self.clear_button.pack(side=tk.LEFT, padx=1)

        self.save_button = tk.Button(button_frame, text="Save", command=self.save_program, font=("Arial", 8), width=4, height=1)
        self.save_button.pack(side=tk.LEFT, padx=1)

        self.load_button = tk.Button(button_frame, text="Load", command=self.load_program, font=("Arial", 8), width=4, height=1)
        self.load_button.pack(side=tk.LEFT, padx=1)

        # Add Copy Screen button
        self.copy_screen_button = tk.Button(button_frame, text="Copy", command=self.copy_screen, font=("Arial", 8), width=4, height=1)
        self.copy_screen_button.pack(side=tk.LEFT, padx=1)


        self.debug_button = tk.Button(button_frame, text="Debug: ON", command=self.toggle_debug, font=("Arial", 8), width=6, height=1)
        self.debug_button.pack(side=tk.LEFT, padx=1)

        # Create Help dropdown menu button
        self.help_button = tk.Menubutton(button_frame, text="Help", relief=tk.RAISED, font=("Arial", 8), width=4, height=1)
        self.help_button.pack(side=tk.RIGHT, padx=1)
        
        self.help_menu = tk.Menu(self.help_button, tearoff=0)
        self.help_menu.add_command(label="Commands & Syntax", command=lambda: self.show_specific_help(0))
        self.help_menu.add_command(label="Functions & Operators", command=lambda: self.show_specific_help(1))
        self.help_menu.add_command(label="Graphics & Memory", command=lambda: self.show_specific_help(2))
        self.help_menu.add_command(label="Examples & Tips", command=lambda: self.show_specific_help(3))
        self.help_menu.add_separator()
        self.help_menu.add_command(label="Show All Help", command=self.show_all_help)
        
        self.help_button.config(menu=self.help_menu)
        
        # Add 2X button (disabled on Raspberry Pi)
        if hasattr(self, 'is_raspberry_pi') and self.is_raspberry_pi:
            self.scale_button = tk.Button(button_frame, text="N/A", command=self.toggle_scale, 
                                        font=("Arial", 8), width=3, height=1, state=tk.DISABLED)
        else:
            self.scale_button = tk.Button(button_frame, text="2X", command=self.toggle_scale, 
                                        font=("Arial", 8), width=3, height=1)
        self.scale_button.pack(side=tk.LEFT, padx=1)

        # Bind key press event to the main window
        self.master.bind('<Key>', self.on_key_press) # DO NOT REMOVE if removed the peek will not work
        self.input_area.bind("<Button-3>", self.on_input_area_click)
        self.screen.bind("<Button-3>", self.on_screen_click)

        # Bind for different systems and mouse buttons
        for button in ("<Button-2>", "<Button-3>", "<Control-Button-1>", "<Control-Button-2>"):
            self.screen.bind(button, self.show_right_click_menu)
            self.input_area.bind(button, self.show_right_click_menu)

        # Initialize screen content
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.cursor_row = 0
        self.cursor_col = 0
        
        # Add cursor display variables
        self.cursor_visible = True
        self.cursor_blink_timer = None
        self.cursor_canvas_item = None

        # Initialize variables first (needed for cursor display)
        self.scalar_variables = {}
        self.array_variables = {}
        self.current_line_index = 0
        self.program_running = False
        self.program_paused = False
        self.waiting_for_input = False
        self.input_variable = None
        self.gosub_stack = []
        self.for_loops = {}
        self.data_values = []
        self.data_pointer = 0
        self.last_key_pressed = None
        self.tape_file = None
        self.tape_data = []
        self.tape_pointer = 0
        self.stepping = False
        
        # Add immediate mode support
        self.immediate_mode = True
        self.command_buffer = ""
        self.stored_program = []  # Store program lines entered in immediate mode
        
        # Add variables window tracking
        self.variables_window_open = False
        self.variables_window = None
        self.debug_window_open = False
        self.debug_window = None
        
        # LLM Support window tracking
        self.llm_window_open = False
        self.llm_support = None

        # Initialize missing variables
        self.sorted_program = []
        self.input_area.bind('<KeyRelease>', self.capitalize_input)
        self.remaining_commands = []   
        self.debug_text = None 
        self.debug_mode = False
        self.original_program = []
        
        # Initialize screen dimensions early for window positioning
        self.screen_width = 852
        self.screen_height = 460
        self.taskbar_height = 20
        
        self.new_program()
        self.create_debug_window()
        self.last_key_time = 0
        self.key_check_interval = .05  # 100 milliseconds
        self.replaced = False
        
        # Bind input area changes to sync with stored_program
        self.input_area.bind('<KeyRelease>', self.sync_input_to_stored, add='+')
        
        # Initialize LLM support without creating the window
        self.llm_support_active = False

        # Performance optimization: Cache compiled regex patterns
        self._regex_cache = {}
        
        # Compile regex patterns once for better performance
        self._compile_regex_patterns()

        # Add button to open LLM support window
        self.llm_button = tk.Button(button_frame, text="Assistant: ON", command=self.toggle_llm_support, font=("Arial", 8), width=10, height=1)
        self.llm_button.pack(side=tk.LEFT, padx=1)
        
        # Add Debug button (duplicate removed - already styled above)
        
        # Start cursor blinking after all initialization is complete
        self.blink_cursor()
        
        # Enable immediate mode input
        self.enable_immediate_mode()
        
        # Set main window size and position for 7" screen
        self.optimize_for_7inch_screen()

    def optimize_for_7inch_screen(self):
        """Optimize window layout for 7" Raspberry Pi screen (800x480)"""
        # Set main window size and position
        # Account for window manager decorations (about 30px for title bar, 40px for taskbar)
        main_width = 800
        main_height = 420  # Leave room for taskbar
        
        # Center the main window
        self.master.geometry(f"{main_width}x{main_height}+0+0")
        
        # Set minimum size to prevent shrinking too much
        self.master.minsize(400, 200)
        
        # Store screen dimensions for positioning child windows
        self.screen_width = 800
        self.screen_height = 480
        self.taskbar_height = 40

    def detect_raspberry_pi(self):
        """Detect if running on Raspberry Pi"""
        try:
            # Check device tree model (most reliable method)
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                if 'Raspberry Pi' in model:
                    print("Raspberry Pi detected - 2x scaling disabled")
                    return True
        except (FileNotFoundError, IOError):
            pass
        
        # Alternative check for Raspberry Pi
        if platform.machine().startswith('arm') or platform.machine() == 'aarch64':
            try:
                # Check for Raspberry Pi specific files
                if os.path.exists('/sys/firmware/devicetree/base/model'):
                    with open('/sys/firmware/devicetree/base/model', 'r') as f:
                        if 'Raspberry Pi' in f.read():
                            print("Raspberry Pi detected - 2x scaling disabled")
                            return True
            except (FileNotFoundError, IOError):
                pass
        
        print("Not running on Raspberry Pi - 2x scaling available")
        return False

    def position_child_window(self, window, width, height, offset_x=0, offset_y=0):
        """Position child windows to fit on 7" screen without overlapping"""
        # Safety check - use defaults if screen dimensions not set
        screen_width = getattr(self, 'screen_width', 800)
        screen_height = getattr(self, 'screen_height', 480)
        taskbar_height = getattr(self, 'taskbar_height', 40)
        
        # Calculate position to avoid going off screen
        x = min(offset_x, screen_width - width - 10)
        y = min(offset_y, screen_height - height - taskbar_height - 10)
        
        # Ensure window is not positioned off-screen
        x = max(0, x)
        y = max(0, y)
        
        window.geometry(f"{width}x{height}+{x}+{y}")

    def blink_cursor(self):
        """Handle cursor blinking like the original TRS-80"""
        if self.cursor_blink_timer:
            self.master.after_cancel(self.cursor_blink_timer)
        
        # Don't blink cursor while program is running (except during INPUT)
        if self.program_running and not self.waiting_for_input:
            # Hide cursor during program execution
            if self.cursor_canvas_item:
                self.screen.delete(self.cursor_canvas_item)
                self.cursor_canvas_item = None
            self.cursor_visible = False
            # Schedule next check
            self.cursor_blink_timer = self.master.after(500, self.blink_cursor)
            return
        
        # Toggle cursor visibility
        self.cursor_visible = not self.cursor_visible
        self.update_cursor_display()
        
        # Schedule next blink (500ms like original TRS-80)
        self.cursor_blink_timer = self.master.after(500, self.blink_cursor)

    def update_cursor_display(self):
        """Update the cursor display on screen"""
        # Remove existing cursor if it exists
        if self.cursor_canvas_item:
            self.screen.delete(self.cursor_canvas_item)
            self.cursor_canvas_item = None
        
        # Draw cursor if visible and not waiting for input (during INPUT commands, cursor should be visible)
        if self.cursor_visible or self.waiting_for_input:
            x = self.cursor_col * self.pixel_size * 2
            y = self.cursor_row * self.pixel_size * 3
            
            # Draw a solid block cursor like the original TRS-80 (ASCII 143 or solid block)
            self.cursor_canvas_item = self.screen.create_rectangle(
                x, y, 
                x + self.pixel_size * 2, 
                y + self.pixel_size * 3, 
                fill="lime", 
                outline="lime",
                tags="cursor"
            )

    def move_cursor(self, row, col):
        """Move cursor to new position and update display"""
        self.cursor_row = row
        self.cursor_col = col
        self.update_cursor_display()

    def _compile_regex_patterns(self):
        """Pre-compile frequently used regex patterns for performance"""
        self._regex_cache['array_match'] = re.compile(r'(\w+\$?)\((.+)\)')
        self._regex_cache['print_at'] = re.compile(r'PRINT@\s*([^,;]+)\s*,?\s*(.*)')
        self._regex_cache['input_prompt'] = re.compile(r'INPUT\s*"(.*)"\s*;\s*(\w+\$?(?:\(.*?\))?)')
        self._regex_cache['if_then'] = re.compile(r'IF\s+(.*?)\s+THEN\s+(.*?)(\s+ELSE\s+(.*))?$')
        self._regex_cache['for_loop'] = re.compile(r'FOR\s+(\w+)\s*=\s*(.+?)\s+TO\s+(.+?)(\s+STEP\s+(.+))?$')
        self._regex_cache['on_goto'] = re.compile(r'ON\s+(.*?)\s+GOTO\s+(.*)')
        self._regex_cache['dim'] = re.compile(r'DIM\s+(\w+\$?)\((.+)\)')
        self._regex_cache['poke'] = re.compile(r'POKE\s+(.+?)\s*,\s*(.+)')
        self._regex_cache['set_reset'] = re.compile(r'(SET|RESET)\s*\(\s*((?:[^(),]+|\([^()]*\))*)\s*,\s*((?:[^(),]+|\([^()]*\))*)\s*\)')
        self._regex_cache['tab'] = re.compile(r'TAB\((\d+)\)')
        self._regex_cache['func_match'] = re.compile(r'(INT|SIN|COS|TAN|SQR|LOG|EXP|SGN|FIX|CHR\$|STRING\$|VAL|RND|ASC|PEEK|POINT|STR\$|LEN|LEFT\$|RIGHT\$|MID\$|ABS|INSTR)\(((?:[^()]+|\([^()]*\))*)\)')
        self._regex_cache['quotes'] = re.compile(r'(?<!\\)"')
        self._regex_cache['quotes_single'] = re.compile(r"(?<!\\)'")
        self._regex_cache['string_split'] = re.compile(r'("(?:[^"\\]|\\.)*")')

    def toggle_llm_support(self):
        self.llm_support_active = not self.llm_support_active
        if self.llm_support_active:
            self.llm_button.config(text="Assistant: OFF")
            self.open_llm_support()
        else:
            self.llm_button.config(text="Assistant: ON")
            if self.llm_support and self.llm_support.llm_window.winfo_exists():
                self.llm_support.llm_window.withdraw()

    def open_llm_support(self):
        if self.llm_support is None or not self.llm_support.llm_window.winfo_exists():
            self.llm_support = TRS80LLMSupport(self.master, self)
            self.llm_support.llm_window.protocol("WM_DELETE_WINDOW", self.on_llm_window_close)
            
            # Position LLM window for 7" screen - wider but shorter
            self.position_child_window(self.llm_support.llm_window, 600, 260, 100, 70)
            
            # Auto-populate with current program if available
            if self.stored_program:
                program_text = "\n".join(self.stored_program)
                self.llm_support.input_text.insert(tk.END, 
                    f"Here is my current TRS-80 BASIC program:\n\n```BASIC\n{program_text}\n```\n\n"
                    f"Please review this program and help me debug any issues or suggest improvements.\n\n")
        else:
            self.llm_support.llm_window.deiconify()
        self.llm_support.llm_window.lift()

    def on_llm_window_close(self):
        self.llm_support_active = False
        self.llm_button.config(text="Assistant: ON")
        self.llm_support.llm_window.withdraw()



    def capitalize_input(self, event):
        # Get the current cursor position
        cursor_pos = self.input_area.index(tk.INSERT)
        
        # Get all the text
        text = self.input_area.get("1.0", tk.END)
        
        # Capitalize the text
        capitalized_text = text.upper()
        
        # Check if the text has actually changed
        if text != capitalized_text:
            # Remember the current view
            first, last = self.input_area.yview()
            
            # Replace the text
            self.input_area.delete("1.0", tk.END)
            self.input_area.insert("1.0", capitalized_text)
            
            # Restore the cursor position
            self.input_area.mark_set(tk.INSERT, cursor_pos)
            
            # Ensure the cursor is visible
            self.input_area.see(cursor_pos)
            
            # Adjust the view if it has scrolled too far
            new_first, new_last = self.input_area.yview()
            if new_first > first:
                self.input_area.yview_moveto(first)
    
    def sync_input_to_stored(self, event):
        """Sync input area changes to stored_program"""
        # Only sync if we're not in the middle of capitalizing
        if event.keysym not in ['Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R']:
            current_program = self.input_area.get(1.0, tk.END).strip().split('\n')
            self.stored_program = [line for line in current_program if line.strip()]
    
    def create_debug_window(self):
        if self.debug_window is None or not self.debug_window.winfo_exists():
            self.debug_window = tk.Toplevel(self.master)
            self.debug_window.title("Debug Output")
            # Position debug window to the right of main window
            self.position_child_window(self.debug_window, 500, 300, 150, 40)

            # Create a frame for buttons
            button_frame = tk.Frame(self.debug_window)
            button_frame.pack(side=tk.TOP, fill=tk.X)

            # Create a frame for the find functionality
            find_frame = tk.Frame(self.debug_window)
            find_frame.pack(side=tk.TOP, fill=tk.X)

            # Add Find entry field
            self.find_entry = tk.Entry(find_frame, width=20, font=("Arial", 7))
            self.find_entry.pack(side=tk.LEFT, padx=2, pady=2)

            # Add Find button
            self.find_button = tk.Button(find_frame, text="Find", command=self.find_in_debug, font=("Arial", 7), width=5, height=1)
            self.find_button.pack(side=tk.LEFT, padx=2, pady=2)

            # Add Clear button
            self.clear_button = tk.Button(button_frame, text="Clear", command=lambda: self.debug_text.delete(1.0, tk.END), font=("Arial", 7), width=5, height=1)
            self.clear_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Add List button
            self.list_button = tk.Button(button_frame, text="List", command=self.list_preprocessed_program, font=("Arial", 7), width=5, height=1)
            self.list_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Add Variables button
            self.variables_button = tk.Button(button_frame, text="Variables: ON", command=self.toggle_variables_window, font=("Arial", 7), width=10, height=1)
            self.variables_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Add button to debug window for sending debug output to LLM
            self.send_debug_button = tk.Button(button_frame, text="Send Debug to Companion", command=self.send_debug_to_llm, font=("Arial", 7), width=15, height=1)
            self.send_debug_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Add button to send program state to LLM
            self.send_state_button = tk.Button(button_frame, text="Send State to Companion", command=self.send_state_to_llm, font=("Arial", 7), width=15, height=1)
            self.send_state_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Add button to analyze program
            self.analyze_button = tk.Button(button_frame, text="Analyze Program", command=self.analyze_and_display_program, font=("Arial", 7), width=12, height=1)
            self.analyze_button.pack(side=tk.LEFT, padx=1, pady=2)

            # Create debug text area
            self.debug_text = scrolledtext.ScrolledText(self.debug_window, wrap=tk.WORD)
            self.debug_text.pack(expand=True, fill='both')

            # Add right-click menu for debug window
            self.debug_right_click_menu = tk.Menu(self.debug_window, tearoff=0)
            self.debug_right_click_menu.add_command(label="Copy", command=self.copy_debug)
            self.debug_right_click_menu.add_command(label="Select All", command=self.select_all_debug)
            self.debug_text.bind("<Button-3>", self.show_debug_right_click_menu)

            self.debug_window.withdraw()  # Hide the window initially
        self.debug_window.protocol("WM_DELETE_WINDOW", self.on_debug_window_close)


    def find_in_debug(self):
        search_text = self.find_entry.get()
        if search_text:
            start_pos = self.debug_text.search(search_text, '1.0', tk.END)
            if start_pos:
                line, col = start_pos.split('.')
                end_pos = f"{line}.{int(col) + len(search_text)}"
                self.debug_text.tag_remove('found', '1.0', tk.END)
                self.debug_text.tag_add('found', start_pos, end_pos)
                self.debug_text.tag_config('found', background='yellow')
                self.debug_text.see(start_pos)
            else:
                messagebox.showinfo("Find", f"Text '{search_text}' not found.")
    
    def create_debug_right_click_menu(self):
        self.debug_right_click_menu = tk.Menu(self.debug_window, tearoff=0)
        self.debug_right_click_menu.add_command(label="Copy", command=self.copy_debug)
        self.debug_right_click_menu.add_command(label="Select All", command=self.select_all_debug)
        self.debug_text.bind("<Button-3>", self.show_debug_right_click_menu)

    def show_debug_right_click_menu(self, event):
        self.debug_right_click_menu.tk_popup(event.x_root, event.y_root)

    def copy_debug(self):
        try:
            selected_text = self.debug_text.selection_get()
            self.debug_window.clipboard_clear()
            self.debug_window.clipboard_append(selected_text)
        except tk.TclError:
            pass  # No selection   

    def select_all_debug(self):
        self.debug_text.tag_add(tk.SEL, "1.0", tk.END)
        self.debug_text.mark_set(tk.INSERT, "1.0")
        self.debug_text.see(tk.INSERT)

    def toggle_variables_window(self):
        if not self.variables_window_open:
            self.show_variables()
            self.variables_button.config(text="Variables: OFF")
        else:
            self.close_variables_window()
            self.variables_button.config(text="Variables: ON")

    def show_variables(self):
        if not self.variables_window_open:
            self.variables_window = tk.Toplevel(self.debug_window)
            self.variables_window.title("Program State")
            # Position variables window below debug window
            self.position_child_window(self.variables_window, 280, 180, 200, 180)

            self.state_text = scrolledtext.ScrolledText(self.variables_window, wrap=tk.WORD)
            self.state_text.pack(expand=True, fill='both')
            
            # Add right-click menu for variables window
            self.variables_right_click_menu = tk.Menu(self.variables_window, tearoff=0)
            self.variables_right_click_menu.add_command(label="Copy", command=self.copy_variables)
            self.variables_right_click_menu.add_command(label="Select All", command=self.select_all_variables)
            self.state_text.bind("<Button-3>", self.show_variables_right_click_menu)
            
            self.variables_window_open = True
            self.variables_window.protocol("WM_DELETE_WINDOW", self.close_variables_window)

        # Update the content of the variables window
        self.update_variables_content()

    def update_variables_content(self):
        self.state_text.config(state=tk.NORMAL)
        self.state_text.delete(1.0, tk.END)
        
        # Program execution state
        self.state_text.insert(tk.END, f"Program Running: {self.program_running}\n")
        self.state_text.insert(tk.END, f"Program Paused: {self.program_paused}\n")
        self.state_text.insert(tk.END, f"Stepping Mode: {self.stepping}\n\n")

        # Current line information
        if self.current_line_index < len(self.sorted_program):
            current_line = self.sorted_program[self.current_line_index]
            line_number = current_line.split()[0]
            self.state_text.insert(tk.END, f"Current Line Number: {line_number}\n")
            self.state_text.insert(tk.END, f"Current Line: {current_line}\n\n")
        else:
            self.state_text.insert(tk.END, "Program execution completed\n\n")

        # Variables
        self.state_text.insert(tk.END, "Variables:\n")
        for var, value in self.scalar_variables.items():
            self.state_text.insert(tk.END, f"{var} = {value}\n")

        for var, value in self.array_variables.items():
            if isinstance(value, list):
                self.state_text.insert(tk.END, f"{var} = {value}\n")
            else:
                self.state_text.insert(tk.END, f"{var} = {value}\n")

        # For Loops
        self.state_text.insert(tk.END, "\nFor Loops:\n")
        for var, loop_info in self.for_loops.items():
            self.state_text.insert(tk.END, f"{var}: {loop_info}\n")

        # GOSUB Stack
        self.state_text.insert(tk.END, f"\nGOSUB Stack: {self.gosub_stack}\n")

        # Data pointer
        self.state_text.insert(tk.END, f"\nData Pointer: {self.data_pointer}\n")

        # Last key pressed
        self.state_text.insert(tk.END, f"Last Key Pressed: {self.last_key_pressed}\n")
        self.state_text.config(state=tk.DISABLED)

    def show_variables_right_click_menu(self, event):
        self.variables_right_click_menu.tk_popup(event.x_root, event.y_root)

    def copy_variables(self):
        try:
            selected_text = self.state_text.selection_get()
            self.variables_window.clipboard_clear()
            self.variables_window.clipboard_append(selected_text)
        except tk.TclError:
            pass  # No selection

    def select_all_variables(self):
        self.state_text.tag_add(tk.SEL, "1.0", tk.END)
        self.state_text.mark_set(tk.INSERT, "1.0")
        self.state_text.see(tk.INSERT)

    def close_variables_window(self):
        if self.variables_window_open:
            self.variables_window.destroy()
            self.variables_window_open = False
            self.variables_button.config(text="Variables: ON")

    def toggle_debug(self):
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.debug_button.config(text="Debug: OFF")
            self.debug_window.deiconify()  # Show the window
        else:
            self.debug_button.config(text="Debug: ON")
            self.debug_window.withdraw()  # Hide the window    
            if hasattr(self, 'variables_window') and self.variables_window.winfo_exists():
                self.variables_window.withdraw()  # Hide the variables window
            #clear the hashtag so you can reopen the variables window
            self.variables_window_open = False
            if hasattr(self, 'variables_button'):
                self.variables_button.config(text="Variables: ON")

    def on_debug_window_close(self):
        self.debug_window.withdraw()
        self.debug_mode = False
        self.debug_button.config(text="Debug: ON")

    def debug_print(self, message, level='info'):
        if self.debug_mode:
            # Add timestamp and context for better debugging
            timestamp = f"[Step {self.current_line_index + 1}]"
            
            if level == 'error':
                self.debug_text.insert(tk.END, f"{timestamp} ERROR: {message}\n", 'error')
            elif level == 'warning':
                self.debug_text.insert(tk.END, f"{timestamp} WARNING: {message}\n", 'warning')
            else:
                self.debug_text.insert(tk.END, f"{timestamp} {message}\n")
            self.debug_text.see(tk.END)

    def set_screen_focus(self):
        self.screen.config(state=tk.NORMAL)
        self.screen.focus_set()
        self.screen.config(state=tk.DISABLED)
    
    def on_key_press(self, event):
        # Check for BREAK key (Ctrl+C or Escape) during program execution
        if self.program_running and (event.keysym == 'Escape' or (event.state & 0x4 and event.keysym == 'c')):
            self.break_program()
            return "break"
        
        # Emergency reset: Ctrl+R to force immediate mode back on
        if event.state & 0x4 and event.keysym == 'r' and event.widget == self.screen:
            self.debug_print("Emergency reset to immediate mode (Ctrl+R)")
            self.program_running = False
            self.program_paused = False
            self.waiting_for_input = False
            self.input_variable = None
            self.screen.unbind("<Key>")
            self.screen.unbind("<Return>")
            self.enable_immediate_mode()
            self.set_screen_focus()
            return "break"
        
        if self.program_running and event.widget == self.screen:
            # Only update if no key is currently stored (simulate keyboard buffer)
            if not self.last_key_pressed and event.char:
                self.last_key_pressed = event.char.upper()
        elif self.immediate_mode and not self.program_running and event.widget == self.screen:
            self.handle_immediate_mode_key(event)
    
    def on_input_area_click(self, event):
        self.input_area.focus_set()

    def on_screen_click(self, event):
        self.set_screen_focus()
        # Failsafe: if we're not running a program and not in immediate mode, force it back
        if not self.program_running and not self.waiting_for_input and not self.immediate_mode:
            self.debug_print("Forcing immediate mode back on after screen click")
            self.enable_immediate_mode()

    def create_right_click_menu(self):
        self.right_click_menu = tk.Menu(self.master, tearoff=0)
        self.right_click_menu.add_command(label="Copy", command=self.copy_screen)
        
        # Additional options for input area
        self.input_right_click_menu = tk.Menu(self.master, tearoff=0)
        self.input_right_click_menu.add_command(label="Cut", command=self.cut)
        self.input_right_click_menu.add_command(label="Copy", command=self.copy)
        self.input_right_click_menu.add_command(label="Paste", command=self.paste)
        self.input_right_click_menu.add_command(label="Clear", command=self.clear_input_area)
        self.input_right_click_menu.add_command(label="Select All", command=self.select_all)

        # Bind for different systems and mouse buttons
        for button in ("<Button-2>", "<Button-3>", "<Control-Button-1>", "<Control-Button-2>"):
            self.screen.bind(button, self.show_right_click_menu)
            self.input_area.bind(button, self.show_right_click_menu)

    def show_right_click_menu(self, event):
        widget = event.widget
        if widget == self.screen:
            self.right_click_menu.tk_popup(event.x_root, event.y_root)
        elif widget == self.input_area:
            self.input_right_click_menu.tk_popup(event.x_root, event.y_root)
        return "break"  # Prevent the default behavior

    def show_right_click_menu(self, event):
        widget = event.widget
        if widget == self.screen:
            self.right_click_menu.tk_popup(event.x_root, event.y_root)
        elif widget == self.input_area:
            self.input_right_click_menu.tk_popup(event.x_root, event.y_root)

    def select_all(self):
        widget = self.master.focus_get()
        if widget == self.input_area:
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
        return "break"

    def cut(self):
        self.copy()
        try:
            self.input_area.delete("sel.first", "sel.last")
        except tk.TclError:
            pass  # No selection

    def copy(self):
        try:
            selected_text = self.master.selection_get()
            self.master.clipboard_clear()
            self.master.clipboard_append(selected_text)
        except tk.TclError:
            pass  # No selection

    def paste(self):
        try:
            clipboard_text = self.master.clipboard_get()
            self.input_area.insert(tk.INSERT, clipboard_text)
        except tk.TclError:
            pass  # Nothing in clipboard

    def copy_screen(self):
        """Copy both text and graphics as a visual representation"""
        # Check if there are any graphics pixels set
        has_graphics = any(any(row) for row in self.pixel_matrix)
        
        if not has_graphics:
            # No graphics - just copy text content as before
            screen_text = '\n'.join(''.join(row) for row in self.screen_content)
            self.master.clipboard_clear()
            self.master.clipboard_append(screen_text.rstrip())
            self.debug_print("Screen text content copied to clipboard")
        else:
            # Has graphics - create combined visual representation
            combined_output = []
            combined_output.append("=== TRS-80 Screen Content (Text + Graphics) ===")
            combined_output.append("Format: Text characters overlaid with graphics pixels")
            combined_output.append("Graphics pixels shown as: ░ (light) █ (solid)")
            combined_output.append("Text overlay position: 64x16 chars, Graphics: 128x48 pixels")
            combined_output.append("")
            
            # Create a visual representation that combines both
            # Each character position covers 2x3 pixels (128/64 = 2, 48/16 = 3)
            visual_screen = []
            
            for text_row in range(16):
                line = []
                for text_col in range(64):
                    char = self.screen_content[text_row][text_col]
                    
                    # Check corresponding pixel area (each char covers 2x3 pixels)
                    pixel_x_start = text_col * 2
                    pixel_y_start = text_row * 3
                    
                    # Count pixels in this character area
                    pixel_count = 0
                    for py in range(pixel_y_start, min(pixel_y_start + 3, 48)):
                        for px in range(pixel_x_start, min(pixel_x_start + 2, 128)):
                            if self.pixel_matrix[py][px]:
                                pixel_count += 1
                    
                    # Determine what to display
                    if char != ' ':
                        # Text character takes precedence
                        line.append(char)
                    elif pixel_count > 0:
                        # Show pixel intensity
                        if pixel_count >= 5:
                            line.append('█')  # Solid block for many pixels
                        elif pixel_count >= 3:
                            line.append('▓')  # Medium block
                        else:
                            line.append('░')  # Light block for few pixels
                    else:
                        line.append(' ')  # Empty space
                
                visual_screen.append(''.join(line))
            
            # Add the visual representation
            combined_output.extend(visual_screen)
            combined_output.append("")
            combined_output.append("=== Raw Text Content (64x16) ===")
            for row in self.screen_content:
                combined_output.append(''.join(row).rstrip())
            
            # Copy to clipboard
            final_output = '\n'.join(combined_output)
            self.master.clipboard_clear()
            self.master.clipboard_append(final_output)
            self.debug_print("Screen content with graphics copied to clipboard")

    #I/O methods
    def clear_input_area(self):
        self.input_area.delete(1.0, tk.END)

    def clear_screen(self):
        # Flush any pending graphics before clearing
        self._flush_graphics()
        
        self.screen.delete("all")
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self.cursor_row = 0
        self.cursor_col = 0
        self.update_cursor_display()
        
        # Clear any pending graphics after screen clear
        if hasattr(self, '_pending_graphics'):
            self._pending_graphics = []
    

    def new_program(self):
        self.scalar_variables = {}
        self.array_variables = {}
        self.for_loops = {}
        self.current_line_index = 0
        self.waiting_for_input = False
        self.input_variable = None
        self.gosub_stack = []
        self.program_running = False
        self.program_paused = False
        self.last_key_pressed = None
        self.data_pointer = 0
        self.data_values = []
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        
        self.cursor_row = 0
        self.cursor_col = 0
        self.tape_file = None
        self.tape_pointer = 0
        
        # Clear the screen and reset cursor position
        self.clear_screen()
        self.cursor_row = 0
        self.cursor_col = 0
       
        # Reset the stop button
        self.stop_button.config(text="DISABLED", state=tk.DISABLED)
        
        # Unbind any lingering event handlers
        self.screen.unbind("<Key>")
        self.screen.unbind("<Return>")
        
        # Clear any attributes that might have been set during input handling
        if hasattr(self, 'input_start_pos'):
            delattr(self, 'input_start_pos')
        if hasattr(self, 'initial_start_pos'):
            delattr(self, 'initial_start_pos')

        self.debug_print("New program initialized. All variables and states reset.")
            
    def reset_program(self):
        # Reset all variables and states without starting the program
        self.new_program()
        self.debug_print("Program reset. All variables and states cleared.")   

    def print_to_screen(self, *args, end='\n'):
        text = ' '.join(str(arg) for arg in args) + end
        chars_to_draw = []  # Batch characters for drawing
        
        for char in text:
            if char == '\n' or self.cursor_col >= 64:
                self.cursor_row += 1
                self.cursor_col = 0
                if self.cursor_row >= 16:
                    # Scroll the screen content up
                    self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                    self.cursor_row = 15
                    # Also scroll graphics up by one text line (3 pixel rows)
                    self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
                    self.redraw_screen()
                    chars_to_draw = []  # Clear batch after redraw
            else:
                self.screen_content[self.cursor_row][self.cursor_col] = char
                x = self.cursor_col * self.pixel_size * 2
                y = self.cursor_row * self.pixel_size * 3
                chars_to_draw.append((x, y, char))
                self.cursor_col += 1
        
        # Draw all characters at once
        for x, y, char in chars_to_draw:
            self.screen.create_text(x, y, text=char, font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")
        
        # Update cursor display after printing
        self.update_cursor_display()
        
        # Only update display once at the end
        if chars_to_draw or text.endswith('\n'):
            self.master.update_idletasks()


    def redraw_screen(self):
        self.screen.delete("all")
        
        # Redraw all graphics pixels first
        for y in range(48):
            for x in range(128):
                if self.pixel_matrix[y][x]:
                    self.screen.create_rectangle(
                        x * self.pixel_size, y * self.pixel_size,
                        (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                        fill="lime", outline="lime"
                    )
        
        # Then redraw all text characters on top
        for row in range(16):
            for col in range(64):
                char = self.screen_content[row][col]
                x = col * self.pixel_size * 2
                y = row * self.pixel_size * 3
                self.screen.create_text(x, y, text=char, font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")

    
    def handle_input_key(self, event):
        if self.waiting_for_input and event.widget == self.screen:
            if event.keysym == 'BackSpace':
                self.handle_backspace(event)
            elif event.char:
                if self.cursor_row >= 15 and self.cursor_col >= 63:
                    # Scroll the screen before adding a character on the last position
                    self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                    self.cursor_row = 15
                    self.cursor_col = 0
                    # Also scroll graphics up by one text line (3 pixel rows)
                    self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
                    self.redraw_screen()
                
                x = self.cursor_col * self.pixel_size * 2
                y = self.cursor_row * self.pixel_size * 3
                self.screen.create_text(x, y, text=event.char.upper(), font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")
                
                self.screen_content[self.cursor_row][self.cursor_col] = event.char.upper()
                self.cursor_col += 1
                if self.cursor_col >= 64:
                    self.cursor_row += 1
                    self.cursor_col = 0
                    if self.cursor_row >= 16:
                        self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                        self.cursor_row = 15
                        # Also scroll graphics up by one text line (3 pixel rows)
                        self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
                        self.redraw_screen()
                
                if not hasattr(self, 'input_start_pos'):
                    self.input_start_pos = f"{self.cursor_row}.{self.cursor_col - 1}"
                
                # Update cursor display after typing
                self.update_cursor_display()
                self.master.update_idletasks()
            return "break"


    def handle_backspace(self, event):
        if self.waiting_for_input and event.widget == self.screen:
            current_pos = f"{self.cursor_row + 1}.{self.cursor_col}"
            if current_pos > self.initial_start_pos:
                # Move cursor back
                self.cursor_col -= 1
                if self.cursor_col < 0:
                    self.cursor_row -= 1
                    self.cursor_col = 63
                
                # Clear the character on the canvas
                x = self.cursor_col * self.pixel_size * 2
                y = self.cursor_row * self.pixel_size * 3
                self.screen.create_rectangle(x, y, x + self.pixel_size * 2, y + self.pixel_size * 3, fill="black", outline="black")
                
                # Update the screen content
                self.screen_content[self.cursor_row][self.cursor_col] = ' '
                
                # Update cursor display after backspace
                self.update_cursor_display()
                
                # Update the GUI
                self.master.update_idletasks()


    def handle_input_return(self, event):
        if self.waiting_for_input and event.widget == self.screen:
            # Construct the user input from screen_content
            user_input = ''
            # Check if input_start_pos exists, if not use current position
            if hasattr(self, 'input_start_pos'):
                start_row, start_col = map(int, self.input_start_pos.split('.'))
            else:
                # If no input was typed, use empty string
                start_row, start_col = self.cursor_row, self.cursor_col
            
            for row in range(start_row, self.cursor_row + 1):
                if row == start_row:
                    user_input += ''.join(self.screen_content[row][start_col:])
                elif row == self.cursor_row:
                    user_input += ''.join(self.screen_content[row][:self.cursor_col])
                else:
                    user_input += ''.join(self.screen_content[row])

            self.debug_print(f"User input received: {user_input}")  # Debug print
            
            array_match = self._regex_cache['array_match'].match(self.input_variable)
            if array_match:
                array_name, index = array_match.groups()
                index = int(self.evaluate_expression(index))
                if array_name in self.array_variables:
                    if 0 <= index < len(self.array_variables[array_name]):
                        if array_name.endswith('$'):
                            self.array_variables[array_name][index] = user_input
                        else:
                            try:
                                self.array_variables[array_name][index] = int(user_input)
                            except ValueError:
                                try:
                                    self.array_variables[array_name][index] = float(user_input)
                                except ValueError:
                                    self.debug_print(f"Error: Invalid numeric input for {array_name}[{index}]", 'error')
                    else:
                        self.debug_print(f"Error: Index {index} out of bounds for array {array_name}", 'error')
                else:
                    self.debug_print(f"Error: Array {array_name} not defined", 'error')
            else:
                if self.input_variable.endswith('$'):
                    self.scalar_variables[self.input_variable] = user_input
                else:
                    try:
                        self.scalar_variables[self.input_variable] = int(user_input)
                    except ValueError:
                        try:
                            self.scalar_variables[self.input_variable] = float(user_input)
                        except ValueError:
                            self.debug_print(f"Error: Invalid numeric input for {self.input_variable}", 'error')
            
            self.debug_print(f"Variable {self.input_variable} set to: {self.scalar_variables.get(self.input_variable, self.array_variables.get(self.input_variable))}")  # Debug print
            
            # Move to the next line
            self.cursor_row += 1
            self.cursor_col = 0
            if self.cursor_row >= 16:
                # Scroll the screen content up
                self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                self.cursor_row = 15
                # Also scroll graphics up by one text line (3 pixel rows)
                self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
            
            self.waiting_for_input = False
            self.input_variable = None
            if hasattr(self, 'input_start_pos'):
                delattr(self, 'input_start_pos')  # Remove the input start position attribute
            self.screen.unbind("<Key>")
            self.screen.unbind("<Return>")
            self.current_line_index += 1
            # If program ended on this INPUT line, restore immediate-mode
            if self.current_line_index >= len(self.sorted_program):
                self.program_running = False
                self.stop_button.config(state=tk.DISABLED)
                self.enable_immediate_mode()
            else:
                self.debug_print(f"Resuming execution from line index: {self.current_line_index}")  # Debug print
                self.master.after(1, self.execute_next_line)  # Schedule next execution
            return "break"

    def break_program(self):
        """Handle BREAK key press - stop program and show break message"""
        if self.program_running:
            # Show BREAK message like original TRS-80
            if self.current_line_index < len(self.sorted_program):
                current_line = self.sorted_program[self.current_line_index]
                line_number = current_line.split()[0]
                self.print_to_screen(f"BREAK IN {line_number}")
            else:
                self.print_to_screen("BREAK")
            
            # Stop the program
            self.program_running = False
            self.program_paused = False
            self.stop_button.config(text="STOP", state=tk.DISABLED)
            self.step_button.config(state=tk.DISABLED)
            
            # Return to immediate mode
            self.enable_immediate_mode()
            self.set_screen_focus()

    def stop_program(self):
        if self.program_running:
            if self.program_paused:
                self.program_paused = False
                self.stop_button.config(text="STOP")
                self.step_button.config(state=tk.DISABLED)
                if self.variables_window_open:
                    self.update_variables_window()
                self.disable_immediate_mode()  # Disable immediate mode when continuing
                self.execute_next_line()
            else:
                self.program_paused = True
                self.stop_button.config(text="CONT")
                self.step_button.config(state=tk.NORMAL)
                if self.variables_window_open:
                    self.update_variables_window()
                

                
                self.enable_immediate_mode()  # Enable immediate mode when paused
        else:
            self.stop_button.config(text="STOP", state=tk.DISABLED)
            self.step_button.config(state=tk.DISABLED)
            self.program_paused = False
            if self.variables_window_open:
                self.update_variables_window()
            self.enable_immediate_mode()  # Enable immediate mode when stopped

    def list_program(self):
        # Always sync from input area first
        current_program = self.input_area.get(1.0, tk.END).strip().split('\n')
        self.stored_program = [line for line in current_program if line.strip()]
        
        if self.stored_program:
            program_text = '\n'.join(self.stored_program)
            self.print_to_screen(program_text)
        else:
            self.debug_print("No program loaded.")

    def list_preprocessed_program(self):
        program = self.sorted_program
        if program:
            program_text = '\n'.join(program)
            self.debug_print(program_text)

    def step_program(self):
        #if not running start the program
        self.stepping = True
        if not self.program_running:
            self.run_program()
        self.step_button.config(state=tk.NORMAL)
        
        #if not self.program_running:
        #    self.run_program()
        self.program_paused = False   
        self.execute_next_line()
        self.program_paused = True
        self.show_variables()
        self.stop_button.config(text="CONT")
        self.stepping = False

    def preprocess_program(self, program):
        def is_within_quotes(s, pos):
                quote_count = len(re.findall(r'(?<!\\)"', s[:pos]))
                return quote_count % 2 == 1    
        self.debug_print ("Preprocessing")
        preprocessed = []
        for line in program:
            if ':' in line and not is_within_quotes(line, line.index(':')):
                line_number, content = line.split(maxsplit=1)
                statements = content.split(':')
                for i, statement in enumerate(statements):
                    if i == 0:
                        preprocessed.append(f"{line_number} {statement.strip()}")
                    else:
                        new_line_number = f"{line_number}.{i}"
                        preprocessed.append(f"{new_line_number} {statement.strip()}")
            else:
                preprocessed.append(line)
        return preprocessed
    
    #Simulator methods
    def run_program(self):
        self.new_program()
        self.input_area.unbind("<Key>")
        self.input_area.unbind("<Return>")

        # Clear the screen and reset cursor position
        self.clear_screen()
        self.cursor_row = 0
        self.cursor_col = 0
        
        # Reset program execution variables
        self.current_line_index = 0
        self.waiting_for_input = False
        self.input_variable = None
        self.gosub_stack = []
        self.for_loops = {}
        self.data_values = []
        self.data_pointer = 0
        self.last_key_pressed = None

        # Always sync from input area to stored_program before running
        program = self.input_area.get(1.0, tk.END).strip().split('\n')
        self.stored_program = [line for line in program if line.strip()]
        self.original_program = program  # Store the original program
        preprocessed_program = self.preprocess_program(program)
        self.sorted_program = sorted(
            [line for line in preprocessed_program if line.strip() and line.split()[0].replace('.', '').isdigit()],
            key=lambda x: float(x.split()[0])
        )   
        self.program_running = True
        self.program_paused = False
        self.stop_button.config(text="STOP", state=tk.NORMAL)
        self.step_button.config(state=tk.NORMAL)  # Enable step button
        self.debug_print("Starting program execution")
        self.set_screen_focus()  # Set focus to the screen
        self.update_variables_window()  # Update variables window at start
        if not self.stepping:
            self.execute_next_line()
       
    def execute_next_line(self):
        update_counter = 0  # Counter for batching GUI updates
        
        while self.program_running and not self.program_paused:
            # Always process keyboard events for INKEY$ to work properly
            self.master.update_idletasks()  # Process events without full redraw
            
            # Reduce full GUI updates for better performance - only every 25 iterations
            if update_counter % 25 == 0:
                self.master.update()  # Full GUI update including screen redraws
                # Flush any pending graphics operations
                self._flush_graphics()
            update_counter += 1
            
            if self.current_line_index >= len(self.sorted_program):
                self.program_running = False
                self.stop_button.config(state=tk.DISABLED)
                self.step_button.config(state=tk.NORMAL)
                self.debug_print("Program execution completed")
                # Flush any remaining graphics
                self._flush_graphics()
                # Only enable immediate mode if we're not already in it
                if not self.immediate_mode:
                    self.enable_immediate_mode()  # Re-enable immediate mode
                self.set_screen_focus()  # Restore focus to green screen
                return

            line = self.sorted_program[self.current_line_index].strip()
            line_number, line = line.split(maxsplit=1)

            # Convert line number to float to handle decimal line numbers
            line_number = float(line_number)
            # Only debug print every 10th line when not in debug mode for speed
            if self.debug_mode or update_counter % 10 == 0:
                self.debug_print(f"Executing line {line_number}: {line}")
            
            if line:
                parts = line.split(maxsplit=1)
                command = parts[1] if len(parts) > 1 and parts[0].isdigit() else line                   
                result = self.execute_command(command)
                if isinstance(result, (int,float)):
                    new_index = self.find_line_index(result)
                    if new_index != -1:
                        self.current_line_index = new_index
                    else:
                        self.debug_print(f"Warning: Line number {result} not found")
                        self.current_line_index += 1
                elif self.waiting_for_input:
                    # Flush graphics before waiting for input
                    self._flush_graphics()
                    return  # Exit the method and wait for input
                else:
                    self.current_line_index += 1
            
            # Only update GUI and variables window occasionally - reduced frequency
            if update_counter % 100 == 0:
                self.master.update_idletasks()  # Allow GUI to update
                if self.variables_window_open:
                    self.update_variables_window()
                

                    
            if self.stepping:
                self.debug_print("Stepping through the program")
                # Flush graphics when stepping
                self._flush_graphics()
                return

    def update_variables_window(self):
        if self.variables_window_open:
            self.show_variables()

    def send_debug_to_llm(self):
        """Send formatted debug output to the LLM companion"""
        if not self.llm_support_active or not self.llm_support:
            messagebox.showwarning("LLM Support", "LLM Assistant is not active. Please enable it first.")
            return
        
        try:
            debug_text = self.debug_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            debug_text = self.debug_text.get("1.0", tk.END)
        
        # Format the debug output for better LLM understanding
        formatted_debug = self.format_debug_for_llm(debug_text)
        self.llm_support.append_debug_output(formatted_debug)
    
    def format_debug_for_llm(self, debug_text):
        """Format debug output to be more helpful for LLM analysis"""
        if not debug_text.strip():
            return "No debug output available."
        
        formatted = []
        formatted.append("=== TRS-80 BASIC DEBUG OUTPUT ===")
        formatted.append("This is execution trace and debug information from the TRS-80 BASIC simulator.")
        formatted.append("Please analyze this output to help identify issues or provide debugging assistance.")
        formatted.append("")
        
        # Add timestamp and context
        formatted.append(f"Program State: {'Running' if self.program_running else 'Stopped'}")
        if self.program_running:
            formatted.append(f"Current Line: {self.current_line_index + 1} of {len(self.sorted_program)}")
        formatted.append("")
        
        formatted.append("=== DEBUG TRACE ===")
        formatted.append(debug_text.strip())
        formatted.append("=== END DEBUG TRACE ===")
        
        return "\n".join(formatted)

    def send_state_to_llm(self):
        """Send formatted program state information to the LLM companion"""
        if not self.llm_support_active or not self.llm_support:
            messagebox.showwarning("LLM Support", "LLM Assistant is not active. Please enable it first.")
            return
        
        state_info = self.get_formatted_program_state()
        self.llm_support.append_program_state(state_info)
    
    def get_formatted_program_state(self):
        """Generate a comprehensive, LLM-friendly program state report"""
        report = []
        
        # Header
        report.append("=== TRS-80 BASIC PROGRAM STATE REPORT ===")
        report.append(f"Generated at execution step: {self.current_line_index + 1}")
        report.append("")
        
        # Program execution status
        report.append("EXECUTION STATUS:")
        report.append(f"  Program Running: {'YES' if self.program_running else 'NO'}")
        report.append(f"  Program Paused: {'YES' if self.program_paused else 'NO'}")
        report.append(f"  Stepping Mode: {'YES' if self.stepping else 'NO'}")
        report.append(f"  Waiting for Input: {'YES' if self.waiting_for_input else 'NO'}")
        if self.waiting_for_input:
            report.append(f"  Input Variable: {self.input_variable}")
        report.append("")
        
        # Current program line context
        if self.sorted_program and self.current_line_index < len(self.sorted_program):
            current_line = self.sorted_program[self.current_line_index]
            line_number = current_line.split()[0]
            report.append("CURRENT EXECUTION CONTEXT:")
            report.append(f"  Current Line Number: {line_number}")
            report.append(f"  Current Line: {current_line}")
            report.append(f"  Line Index: {self.current_line_index} of {len(self.sorted_program)}")
            
            # Show surrounding lines for context
            report.append("  Context (previous 3 lines):")
            for i in range(max(0, self.current_line_index - 3), self.current_line_index):
                if i < len(self.sorted_program):
                    report.append(f"    {self.sorted_program[i]}")
            report.append(f"  → {current_line}  ← CURRENT")
            report.append("  Context (next 3 lines):")
            for i in range(self.current_line_index + 1, min(len(self.sorted_program), self.current_line_index + 4)):
                report.append(f"    {self.sorted_program[i]}")
        else:
            report.append("CURRENT EXECUTION CONTEXT:")
            report.append("  Program execution completed or not started")
        report.append("")
        
        # Complete program listing
        report.append("COMPLETE PROGRAM:")
        if self.sorted_program:
            for i, line in enumerate(self.sorted_program):
                marker = " ← CURRENT" if i == self.current_line_index else ""
                report.append(f"  {line}{marker}")
        else:
            report.append("  No program loaded")
        report.append("")
        
        # Variables state
        report.append("VARIABLES STATE:")
        if self.scalar_variables:
            report.append("  Scalar Variables:")
            for var, value in sorted(self.scalar_variables.items()):
                var_type = "String" if var.endswith('$') else "Numeric"
                report.append(f"    {var} = {repr(value)} ({var_type})")
        else:
            report.append("  No scalar variables defined")
        
        if self.array_variables:
            report.append("  Array Variables:")
            for var, value in sorted(self.array_variables.items()):
                var_type = "String Array" if var.endswith('$') else "Numeric Array"
                if isinstance(value, list):
                    report.append(f"    {var} = {var_type}, Size: {len(value)}")
                    # Show first few elements
                    for i, elem in enumerate(value[:10]):  # Show first 10 elements
                        report.append(f"      [{i}] = {repr(elem)}")
                    if len(value) > 10:
                        report.append(f"      ... and {len(value) - 10} more elements")
                else:
                    report.append(f"    {var} = {repr(value)} ({var_type})")
        else:
            report.append("  No array variables defined")
        report.append("")
        
        # Control flow state
        report.append("CONTROL FLOW STATE:")
        if self.for_loops:
            report.append("  Active FOR Loops:")
            for var, loop_info in self.for_loops.items():
                report.append(f"    FOR {var} = {loop_info['current']} TO {loop_info['end']} STEP {loop_info['step']}")
                report.append(f"      Loop started at line index: {loop_info['line_index']}")
                remaining = abs((loop_info['end'] - loop_info['current']) / loop_info['step'])
                report.append(f"      Estimated iterations remaining: {int(remaining)}")
        else:
            report.append("  No active FOR loops")
        
        if self.gosub_stack:
            report.append("  GOSUB Stack (return addresses):")
            for i, return_line in enumerate(reversed(self.gosub_stack)):
                report.append(f"    Level {i + 1}: Return to line {return_line}")
        else:
            report.append("  No active GOSUB calls")
        report.append("")
        
        # Data handling state
        report.append("DATA HANDLING STATE:")
        if self.data_values:
            report.append(f"  DATA Values Available: {len(self.data_values)}")
            report.append(f"  Current DATA Pointer: {self.data_pointer}")
            report.append(f"  Remaining DATA Items: {len(self.data_values) - self.data_pointer}")
            report.append("  DATA Values:")
            for i, value in enumerate(self.data_values):
                marker = " ← NEXT" if i == self.data_pointer else ""
                status = "READ" if i < self.data_pointer else "UNREAD"
                report.append(f"    [{i}] = {repr(value)} ({status}){marker}")
        else:
            report.append("  No DATA values defined")
        report.append("")
        
        # Screen and I/O state
        report.append("SCREEN AND I/O STATE:")
        report.append(f"  Cursor Position: Row {self.cursor_row}, Column {self.cursor_col}")
        report.append(f"  Last Key Pressed: {repr(self.last_key_pressed) if self.last_key_pressed else 'None'}")
        
        # Show current screen content (non-empty lines only)
        screen_has_content = False
        for row_idx, row in enumerate(self.screen_content):
            line_content = ''.join(row).rstrip()
            if line_content:
                if not screen_has_content:
                    report.append("  Screen Content (non-empty lines):")
                    screen_has_content = True
                report.append(f"    Row {row_idx:2d}: {repr(line_content)}")
        
        if not screen_has_content:
            report.append("  Screen Content: Empty")
        report.append("")
        
        # Tape/file operations
        if self.tape_file:
            report.append("TAPE/FILE OPERATIONS:")
            report.append(f"  Tape File: {self.tape_file}")
            report.append(f"  Tape Pointer: {self.tape_pointer}")
        
        # Error indicators and potential issues
        report.append("RUNTIME ISSUES TO CHECK:")
        runtime_issues = []
        
        # Check for common runtime problems
        if self.program_running and self.current_line_index >= len(self.sorted_program):
            runtime_issues.append("Program appears to be running but has reached the end")
        
        if self.waiting_for_input and not self.input_variable:
            runtime_issues.append("Program is waiting for input but no input variable is set")
        
        if self.for_loops:
            for var, loop_info in self.for_loops.items():
                if loop_info['step'] == 0:
                    runtime_issues.append(f"FOR loop variable {var} has zero step - infinite loop risk")
                if loop_info['step'] > 0 and loop_info['current'] > loop_info['end']:
                    runtime_issues.append(f"FOR loop variable {var} may have overshot its end value")
                if loop_info['step'] < 0 and loop_info['current'] < loop_info['end']:
                    runtime_issues.append(f"FOR loop variable {var} may have undershot its end value")
        
        if self.data_pointer >= len(self.data_values) and self.data_values:
            runtime_issues.append("DATA pointer is beyond available data - READ statements may fail")
        
        if len(self.gosub_stack) > 10:
            runtime_issues.append("GOSUB stack is very deep - possible infinite recursion")
        
        if runtime_issues:
            for issue in runtime_issues:
                report.append(f"  ⚠️  {issue}")
        else:
            report.append("  No obvious runtime issues detected")
        
        report.append("")
        
        # Add program analysis
        analysis = self.analyze_program_issues()
        report.append(analysis)
        
        report.append("")
        report.append("=== END PROGRAM STATE REPORT ===")
        
        return "\n".join(report)
    
    def analyze_and_display_program(self):
        """Analyze the current program and display results in debug window"""
        analysis = self.analyze_program_issues()
        self.debug_print("=== PROGRAM ANALYSIS ===")
        self.debug_print(analysis)
        self.debug_print("=== END ANALYSIS ===")
        
        # Also send to LLM if active
        if self.llm_support_active and self.llm_support:
            program_text = "\n".join(self.stored_program) if self.stored_program else "No program loaded"
            full_analysis = f"PROGRAM ANALYSIS REQUEST:\n\n```BASIC\n{program_text}\n```\n\n{analysis}\n\nPlease review this analysis and provide debugging suggestions."
            self.llm_support.append_program_state(full_analysis)
    
    def analyze_program_issues(self):
        """Analyze the current program for common issues and return a report"""
        if not self.stored_program:
            return "No program loaded to analyze."
        
        issues = []
        warnings = []
        
        # Check for common programming issues
        line_numbers = []
        for line in self.stored_program:
            if line.strip():
                try:
                    line_num = float(line.split()[0])
                    line_numbers.append(line_num)
                except (ValueError, IndexError):
                    issues.append(f"Invalid line number in: {line}")
        
        # Check for duplicate line numbers
        if len(line_numbers) != len(set(line_numbers)):
            issues.append("Duplicate line numbers detected")
        
        # Check for missing line numbers in sequences
        if line_numbers:
            sorted_lines = sorted(line_numbers)
            for i in range(len(sorted_lines) - 1):
                if sorted_lines[i+1] - sorted_lines[i] > 20:
                    warnings.append(f"Large gap between line {sorted_lines[i]} and {sorted_lines[i+1]}")
        
        # Check for unmatched FOR/NEXT loops
        for_vars = []
        for line in self.stored_program:
            if 'FOR ' in line.upper():
                try:
                    var = line.upper().split('FOR ')[1].split('=')[0].strip()
                    for_vars.append(var)
                except:
                    pass
            if 'NEXT' in line.upper():
                if for_vars:
                    for_vars.pop()
                else:
                    issues.append(f"NEXT without matching FOR in line: {line}")
        
        if for_vars:
            issues.append(f"FOR loop(s) without matching NEXT: {', '.join(for_vars)}")
        
        # Check for unmatched GOSUB/RETURN
        gosub_count = sum(1 for line in self.stored_program if 'GOSUB' in line.upper())
        return_count = sum(1 for line in self.stored_program if line.upper().strip() == 'RETURN')
        if gosub_count != return_count:
            warnings.append(f"Unbalanced GOSUB/RETURN: {gosub_count} GOSUBs, {return_count} RETURNs")
        
        # Check for variables that might not be initialized
        var_assignments = set()
        var_usage = set()
        for line in self.stored_program:
            if '=' in line and not line.upper().startswith('IF'):
                try:
                    var = line.split('=')[0].strip().split()[-1]
                    var_assignments.add(var)
                except:
                    pass
            # Simple check for variable usage (this could be improved)
            for word in line.split():
                if word.isalpha() and len(word) <= 2:
                    var_usage.add(word)
        
        uninitialized = var_usage - var_assignments
        if uninitialized:
            warnings.append(f"Variables used but not clearly assigned: {', '.join(uninitialized)}")
        
        # Generate report
        report = []
        report.append("=== PROGRAM ANALYSIS ===")
        
        if issues:
            report.append("ISSUES FOUND:")
            for issue in issues:
                report.append(f"  ❌ {issue}")
        
        if warnings:
            report.append("WARNINGS:")
            for warning in warnings:
                report.append(f"  ⚠️  {warning}")
        
        if not issues and not warnings:
            report.append("✅ No obvious issues detected")
        
        return "\n".join(report)
    
    # Helper function to check if a position is within quotes
    def is_within_quotes(self,s, pos):
        quote_count = len(re.findall(r'(?<!\\)"', s[:pos]))
        return quote_count % 2 == 1

    # Helper function to find the next unquoted comma or semicolon
    def find_next_separator(self, s, start):
        paren_count = 0
        for i in range(start, len(s)):
            if s[i] == '(' and not self.is_within_quotes(s, i):
                paren_count += 1
            elif s[i] == ')' and not self.is_within_quotes(s, i):
                paren_count -= 1
            elif (s[i] in ',;') and paren_count == 0 and not self.is_within_quotes(s, i):
                return i
        return -1

    def execute_command(self, command):
        original_command = command  # Store the original command for debugging
        
        # Optimize debug printing - only when debug mode is on
        if self.debug_mode:
            self.debug_print(f"Executing: {original_command}")
            
            # Add variable state before execution if in debug mode
            if self.scalar_variables:
                vars_summary = ", ".join([f"{k}={v}" for k, v in list(self.scalar_variables.items())[:5]])
                if len(self.scalar_variables) > 5:
                    vars_summary += f", ... and {len(self.scalar_variables) - 5} more"
                self.debug_print(f"Variables before: {vars_summary}")
        
        try:
            # Check for implicit LET statement
            if '=' in command and not any(command.startswith(keyword) for keyword in ['LET', 'IF', 'FOR', 'PRINT', 'INPUT', 'READ', 'DIM']):
                command = 'LET ' + command
                self.debug_print(f"Implicit LET detected. Modified command: {command}")

            if command.startswith('PRINT') and not command.startswith('PRINT#-1'):
                # Handle PRINT command
                self.debug_print(f"Executing PRINT command: {command}")
                is_print_at = command.startswith('PRINT@')
                original_row, original_col = self.cursor_row, self.cursor_col
                
                if is_print_at:
                    # Handle PRINT@ command
                    match = self._regex_cache['print_at'].match(command)
                    if match:
                        position_expr, content = match.groups()
                        position = int(self.evaluate_expression(position_expr))
                        # Adjust for 1-based indexing
                        position -= 1
                        self.cursor_row = position // 64
                        self.cursor_col = position % 64
                        self.debug_print(f"PRINT@ position: {position + 1}, row: {self.cursor_row}, col: {self.cursor_col}")
                else:
                    content = command[5:].strip()  # Remove PRINT

                output = ""
                cursor_pos = self.cursor_col

                # Process the content
                start = 0
                while start < len(content):
                    end = self.find_next_separator(content, start)
                    if end == -1:
                        part = content[start:]
                        start = len(content)
                    else:
                        part = content[start:end]
                        start = end + 1

                    if part:
                        if 'TAB(' in part:
                            match = self._regex_cache['tab'].search(part)
                            if match:
                                tab_pos = int(match.group(1))
                                cursor_pos = tab_pos
                        else:
                            evaluated_part = self.evaluate_expression(part.strip())
                            output += str(evaluated_part)
                            cursor_pos += len(str(evaluated_part))

                    if end != -1:
                        if content[end] == ',':
                            spaces_to_add = (16 - cursor_pos % 16) % 16
                            output += ' ' * spaces_to_add
                            cursor_pos += spaces_to_add

                # For PRINT@, clear the area where we're about to print
                if is_print_at and output:
                    # Clear the text area before printing
                    for i in range(len(output)):
                        if self.cursor_col + i < 64:
                            # Clear the character position on screen
                            x = (self.cursor_col + i) * self.pixel_size * 2
                            y = self.cursor_row * self.pixel_size * 3
                            # Draw a black rectangle to clear the character
                            self.screen.create_rectangle(
                                x, y, 
                                x + self.pixel_size * 2, 
                                y + self.pixel_size * 3, 
                                fill="black", outline="black"
                            )
                            # Also update the screen_content array
                            self.screen_content[self.cursor_row][self.cursor_col + i] = ' '

                # Print the final output
                if content.rstrip().endswith((';', ',')):
                    self.print_to_screen(output, end='')
                else:
                    self.print_to_screen(output, end='\n')

                # Reset cursor position if it was a PRINT@ command
                if is_print_at:
                    self.cursor_row, self.cursor_col = original_row, original_col

            elif command.startswith('LET'):
                # Handle variable assignment
                self.debug_print(f"Executing {'implicit ' if original_command != command else ''}LET command: {command}")
                parts = command[3:].split('=', 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    value = parts[1].strip()
                    array_match = self._regex_cache['array_match'].match(var_name)
                    if array_match:
                        array_name, index = array_match.groups()
                        index = int(self.evaluate_expression(index))
                        if array_name in self.array_variables:
                            if 0 <= index < len(self.array_variables[array_name]):
                                if array_name.endswith('$'):
                                    self.array_variables[array_name][index] = str(self.evaluate_expression(value))
                                else:
                                    self.array_variables[array_name][index] = self.evaluate_expression(value)
                                self.debug_print(f"Array assignment: {array_name}[{index}] = {self.array_variables[array_name][index]}")
                            else:
                                self.debug_print(f"Error: Index {index} out of bounds for array {array_name}", 'error')
                        else:
                            self.debug_print(f"Error: Array {array_name} not defined", 'error')
                    else:
                        if var_name.endswith('$'):
                            self.scalar_variables[var_name] = str(self.evaluate_expression(value))
                        else:
                            self.scalar_variables[var_name] = self.evaluate_expression(value)
                        self.debug_print(f"Variable assignment: {var_name} = {self.scalar_variables[var_name]}")

            elif command.startswith('REM'):
                self.debug_print(f"Executing REM command: {command}")
                pass  # REM is a comment, do nothing

            elif command.startswith('POKE'):
                # Handle POKE command
                self.debug_print(f"Executing POKE command: {command}")
                match = self._regex_cache['poke'].match(command)
                if match:
                    address_expr, value_expr = match.groups()
                    address = int(self.evaluate_expression(address_expr))
                    value = int(self.evaluate_expression(value_expr))
                    self.poke(address, value)
              

            elif command.startswith('RESET') or command.startswith('SET'):
                # Optimized SET/RESET commands - faster parsing for graphics
                try:
                    # Fast parsing for common SET(x,y) and RESET(x,y) patterns
                    if '(' in command and ')' in command:
                        cmd_type = 'SET' if command.startswith('SET') else 'RESET'
                        # Extract coordinates more efficiently
                        paren_start = command.index('(')
                        paren_end = command.index(')')
                        coords = command[paren_start+1:paren_end]
                        
                        if ',' in coords:
                            x_str, y_str = coords.split(',', 1)
                            x = int(self.evaluate_expression(x_str.strip())) - 1  # Adjust for 1-based indexing
                            y = int(self.evaluate_expression(y_str.strip())) - 1  # Adjust for 1-based indexing
                            
                            if cmd_type == 'SET':
                                self.set_pixel(x, y)
                            else:
                                self.reset_pixel(x, y)
                        else:
                            raise ValueError("Invalid coordinate format")
                    else:
                        raise ValueError("Missing parentheses")
                except (ValueError, IndexError) as e:
                    # Fall back to regex if fast parsing fails
                    match = self._regex_cache['set_reset'].match(command)
                    if match:
                        cmd_type, x_expr, y_expr = match.groups()
                        x = int(self.evaluate_expression(x_expr)) - 1  # Adjust for 1-based indexing
                        y = int(self.evaluate_expression(y_expr)) - 1  # Adjust for 1-based indexing
                        if cmd_type == 'SET':
                            self.set_pixel(x, y)
                        else:
                            self.reset_pixel(x, y)
                    else:
                        if self.debug_mode:
                            self.debug_print(f"Invalid {command.split()[0]} command: {command}")

            elif command == 'CLS':
                # Clear the screen
                self.clear_screen()
                self.cursor_row = 0
                self.cursor_col = 0

            elif command.startswith('DIM'):
                # Match both numeric and string array declarations
                match = self._regex_cache['dim'].match(command)
                if match:
                    array_name, size_expr = match.groups()
                    size = int(self.evaluate_expression(size_expr))
                    
                    # Check if it's a string array (ends with $) or numeric array
                    if array_name.endswith('$'):
                        self.array_variables[array_name] = [''] * (size + 1)
                    else:
                        self.array_variables[array_name] = [0] * (size + 1)
                    
                    self.debug_print(f"Array {array_name} dimensioned with size {size + 1}")
                else:
                    self.debug_print(f"Invalid DIM command: {command}", 'error')

            elif command.startswith('INPUT#-1'):
                if not self.tape_file:
                    self.select_tape_file()
                var_name = command.split(',')[1].strip()
                tape_data = self.read_from_tape()
                if tape_data is not None:
                    self.scalar_variables[var_name] = tape_data
                    self.debug_print(f"Read from tape: {var_name} = {tape_data}")
                else:
                    self.debug_print("Error: No more data on tape")
                
            elif command.startswith('PRINT#-1'):
                # Write to tape
                if not self.tape_file:
                    self.create_tape_file()
                _, data = command.split(',', 1)
                data = self.evaluate_expression(data.strip())
                self.write_to_tape(data)
                self.debug_print(f"Wrote to tape: {data}")

            elif command.startswith('INPUT '):
                match = self._regex_cache['input_prompt'].match(command)
                if match:
                    prompt, var_name = match.groups()
                    self.print_to_screen(prompt, end='')
                else:
                    var_name = command[5:].strip()
                    self.print_to_screen("? ", end='')    
                self.waiting_for_input = True
                self.input_variable = var_name
                self.initial_start_pos= f"{self.cursor_row + 1}.{self.cursor_col}"
                self.screen.config(state=tk.NORMAL)
                self.screen.bind("<Key>", self.handle_input_key)
                self.screen.bind("<Return>", self.handle_input_return)
                self.screen.focus_set()

            elif command.startswith('GOTO'):
                line_number = int(command[4:].strip())
                return line_number
            
            elif command.startswith('IF'):
                match = self._regex_cache['if_then'].match(command)
                if match:
                    condition, then_action, _, else_action = match.groups()
                    condition_result = self.evaluate_expression(condition)
                    if condition_result:
                        return self.execute_command(then_action)
                    elif else_action:
                        return self.execute_command(else_action)

            elif command.startswith('FOR'):
                match = self._regex_cache['for_loop'].match(command)
                if match:
                    var, start_expr, end_expr, _, step_expr = match.groups()
                    start = self.evaluate_expression(start_expr)
                    end = self.evaluate_expression(end_expr)
                    step = self.evaluate_expression(step_expr) if step_expr else 1
                    self.for_loops[var] = {
                        'start': start,
                        'end': end,
                        'step': step,
                        'current': start,
                        'line_index': self.current_line_index
                    }
                    self.scalar_variables[var] = start
            
            elif command.startswith('NEXT'):
                if self.for_loops:
                    var = list(self.for_loops.keys())[-1]
                    loop = self.for_loops[var]
                    loop['current'] += loop['step']
                    self.scalar_variables[var] = loop['current']
                    if (loop['step'] > 0 and loop['current'] <= loop['end']) or (loop['step'] < 0 and loop['current'] >= loop['end']):   
                        self.debug_print(f"Looping back to line index: {loop['line_index']}")  # Debug print
                        next_line_number = float(self.sorted_program[loop['line_index'] + 1].split()[0])
                        return next_line_number   
                    else:
                        self.for_loops.pop(var)

            elif command.startswith('ON'):
                match = self._regex_cache['on_goto'].match(command)
                if match:
                    expression, line_numbers = match.groups()
                    value = int(self.evaluate_expression(expression))
                    targets = [int(ln.strip()) for ln in line_numbers.split(',')]
                    if 1 <= value <= len(targets):
                        return targets[value - 1]
            
            elif command.startswith('GOSUB'):
                line_number = int(command[5:].strip())
                next_line_number = float(self.sorted_program[self.current_line_index + 1].split()[0])
                self.gosub_stack.append(next_line_number)
                return line_number

            elif command == 'RETURN':
                if self.gosub_stack:
                    return self.gosub_stack.pop()
                else:
                    self.debug_print("Error: RETURN without GOSUB")

            elif command.startswith('DELAY'):
                delay_time = int(command.split()[1])
                self.master.after(delay_time * 10)  # Multiply by 10 to make the delay more noticeable

            elif command.startswith('DATA'):
                data = command[4:].strip()
                self.data_values.extend(data.split(','))
                self.debug_print(f"Added DATA: {data.split(',')}")  # Debug print

            elif command.startswith('READ'):
                variables = [v.strip() for v in command[4:].split(',')]
                for var in variables:
                    if self.data_pointer < len(self.data_values):
                        value = self.data_values[self.data_pointer].strip()
                        
                        array_match = self._regex_cache['array_match'].match(var)
                        if array_match:
                            array_name, index = array_match.groups()
                            index = int(self.evaluate_expression(index))
                            if array_name in self.array_variables:
                                if 0 <= index < len(self.array_variables[array_name]):
                                    if array_name.endswith('$'):
                                        self.array_variables[array_name][index] = value.strip("'\"")
                                    else:
                                        self.array_variables[array_name][index] = self.evaluate_expression(value)
                                else:
                                    self.debug_print(f"Error: Index {index} out of bounds for array {array_name}", 'error')
                            else:
                                self.debug_print(f"Error: Array {array_name} not defined", 'error')
                        else:
                            if var.endswith('$'):
                                self.scalar_variables[var] = value.strip("'\"")
                            else:
                                self.scalar_variables[var] = self.evaluate_expression(value)
                        
                        self.data_pointer += 1
                        self.debug_print(f"READ: {var} = {value}")  # Debug print
                    else:
                        self.debug_print("Error: Out of DATA", 'error')

            elif command == 'RESTORE':
                self.data_pointer = 0
                self.debug_print("RESTORE: Data pointer reset to 0")  # Debug print

            elif command == 'STOP':
                # Show BREAK message like original TRS-80
                current_line = self.sorted_program[self.current_line_index]
                line_number = current_line.split()[0]
                self.print_to_screen(f"BREAK IN {line_number}")
                self.program_paused = True
                self.stop_button.config(text="CONT", state=tk.NORMAL)
                self.enable_immediate_mode()  # Enable immediate mode when stopped
                #self.current_line_index += 1 # Move to the next line so when you continue it will start from the next line

            elif command == 'END':
                self.program_running = False
                self.stop_button.config(state=tk.DISABLED)
                # Flush any remaining graphics operations
                self._flush_graphics()
                # Don't call enable_immediate_mode here - it will be called when execute_next_line finishes
                
            else:
                self.debug_print(f"Unknown command: {command}", 'warning')

        except Exception as e:
            self.debug_print(f"Error executing command: {original_command}", 'error')
            self.debug_print(f"Error details: {str(e)}", 'error')
            

            
            self.program_running = False
            self.stop_button.config(state=tk.DISABLED)
        
        return None
    
    def evaluate_expression(self, expr):
        # Only debug print in debug mode to improve performance
        if self.debug_mode:
            self.debug_print(f"Evaluating expression: {expr}")
        self.replaced = False
        
        # Fast path for simple numeric values (common in graphics operations)
        expr_stripped = expr.strip()
        if expr_stripped.isdigit():
            return int(expr_stripped)
        
        # Fast path for simple variable references
        if expr_stripped in self.scalar_variables:
            return self.scalar_variables[expr_stripped]
        protected_functions = [
    'SIN', 'COS', 'TAN', 'EXP', 'LOG', 'SQR', 'ABS', 'INT', 'RND',
    'CHR$', 'STR$', 'LEFT$', 'RIGHT$', 'MID$', 'INSTR', 'LEN',
    'ASC', 'VAL', 'PEEK', 'POINT', 'FIX', 'SGN', 'STRING$'
]
        def eval_nested(expr):
            # Helper function to check if a position is within quotes
            def is_within_quotes(s, pos):
                double_quote_count = len(self._regex_cache['quotes'].findall(s[:pos]))
                single_quote_count = len(self._regex_cache['quotes_single'].findall(s[:pos]))
                return (double_quote_count % 2 == 1) or (single_quote_count % 2 == 1)
            
            # Replacement functions
            def replace_rnd(match):
                return str(random.random()) if not is_within_quotes(expr, match.start()) else match.group(0)


            
            def replace_mod(match):
                return '%' if not is_within_quotes(expr, match.start()) else match.group(0)

            def replace_or(match):
                return ' or ' if not is_within_quotes(expr, match.start()) else match.group(0)

            def replace_and(match):
                return ' and ' if not is_within_quotes(expr, match.start()) else match.group(0)

            def replace_equal(match):
                return '==' if not is_within_quotes(expr, match.start()) else match.group(0)

            def replace_not_equal(match):
                return '!=' if not is_within_quotes(expr, match.start()) else match.group(0)
            
            def replace_not(match):
                return ' not ' if not is_within_quotes(expr, match.start()) else match.group(0)
            
            def replace_exp(match):
                return ' ** ' if not is_within_quotes(expr, match.start()) else match.group(0)

            
            # Handle operators and functions
            # Replace INKEY$ only once to avoid multiple calls in the same expression
            inkey_match = re.search(r'\bINKEY\$', expr)
            if inkey_match and not is_within_quotes(expr, inkey_match.start()):
                inkey_result = self.inkey()
                expr = expr[:inkey_match.start()] + f"'{inkey_result}'" + expr[inkey_match.end():]
                self.replaced = True

            expr = re.sub(r'\bRND\b(?!\()', replace_rnd, expr)  # This correctly handles RND without arguments

            expr = re.sub(r'\bMOD\b', replace_mod, expr)
            expr = re.sub(r'\bOR\b', replace_or, expr)
            expr = re.sub(r'\bAND\b', replace_and, expr)
            expr = re.sub(r'\bNOT\b', replace_not, expr)

            expr = re.sub(r'(?<![=<>])=(?![=])', replace_equal, expr)
            expr = re.sub(r'<>', replace_not_equal, expr)
            #need to replace ^ with ** for exponentiation
            expr = re.sub(r'\^', replace_exp, expr)

            # Handle nested functions
            while True:
                # Remove update_idletasks from inner loop for performance
                func_match = self._regex_cache['func_match'].search(expr) 
                
                if not func_match:
                    break

                func_name, inner_expr = func_match.groups()
                if self.debug_mode:
                    self.debug_print(f"Evaluating function: {func_name}({inner_expr})")
                
                # Check if the function is within quotes
                if is_within_quotes(expr, func_match.start()):
                    break

                # Evaluate the inner expression first
                inner_value = eval_nested(inner_expr)

                # Handle different functions
                if func_name == 'INT':
                    result = int(float(inner_value))
                elif func_name == 'SIN':
                    result = math.sin(float(inner_value))
                elif func_name == 'COS':
                    result = math.cos(float(inner_value))
                elif func_name == 'TAN':
                    result = math.tan(float(inner_value))
                elif func_name == 'SQR':
                    result = math.sqrt(float(inner_value))
                elif func_name == 'LOG':
                    result = math.log(float(inner_value))
                elif func_name == 'EXP':
                    result = math.exp(float(inner_value))    
                elif func_name == 'SGN':
                    value = float(inner_value)
                    result = -1 if value < 0 else (1 if value > 0 else 0)
                elif func_name == 'ABS':
                    result = abs(float(inner_value))
                elif func_name == 'FIX':
                    result = math.trunc(float(inner_value))
                elif func_name == 'VAL':
                    result = float(str(inner_value).strip("'\""))    
                elif func_name == 'RND':
                    result = random.randint(0, int(inner_value) - 1)

                elif func_name == 'ASC':
                    result = ord(str(inner_value).strip("'\""))

                elif func_name == 'PEEK':               
                    result = self.peek(int(inner_value))

                elif func_name == 'POINT':
                    # POINT(x,y) returns 1 if pixel is on, 0 if off. x range: 1-128, y range: 1-48
                    try:
                        x, y = map(lambda v: int(eval_nested(v.strip())), inner_expr.split(','))
                        result = self.get_pixel(x - 1, y - 1)  # Adjust for 1-based indexing
                    except ValueError as e:
                        self.debug_print(f"Error in POINT function: {str(e)}", 'error')
                        result = 0  # Default to 0 if there's an error

                elif func_name == 'LEN':
                    result = len(str(inner_value))

                elif func_name == 'STR$':
                    result = f"'{str(inner_value)}'"

                elif func_name == 'CHR$':
                    result = f"'{chr(int(float(inner_value)))}'"

                elif func_name == 'STRING$':
                    count, char = inner_expr.split(',')
                    count = int(eval_nested(count.strip()))
                    char = eval_nested(char.strip())
                    if isinstance(char, str):
                        char = char[0] if char else ''
                    else:
                        char = chr(int(char))
                    result = f"'{char * count}'"

                elif func_name == 'LEFT$':
                    string, length = map(eval_nested, inner_expr.split(','))
                    result = f"'{str(string)[:int(length)]}'"
                elif func_name == 'RIGHT$':
                    string, length = map(eval_nested, inner_expr.split(','))
                    result = f"'{str(string)[-int(length):]}'"
                elif func_name == 'MID$':
                    parts = inner_expr.split(',')
                    string, start = map(eval_nested, parts[:2])
                    start = int(start) - 1  # BASIC uses 1-based indexing
                    if len(parts) > 2:
                        length = int(eval_nested(parts[2]))
                        result = f"'{str(string)[start:start+length]}'"
                    else:
                        result = f"'{str(string)[start:]}'"
                elif func_name == 'INSTR':
                    parts = inner_expr.split(',')
                    if len(parts) == 2:
                        string, substring = map(eval_nested, parts)
                        start = 1
                    elif len(parts) == 3:
                        start, string, substring = map(eval_nested, parts)
                        start = int(start)
                    else:
                        raise ValueError("INSTR requires 2 or 3 arguments")
                    
                    # Adjust for 1-based indexing
                    result = string.find(substring, start - 1) + 1
                    if result == 0:  # If not found, return 0 instead of -1
                        result = 0
                
                # Replace the function call with the result
                expr = expr.replace(func_match.group(), str(result), 1)
                if self.debug_mode:
                    self.debug_print(f"Function {func_name}({inner_value}) = {result}")

            # Handle array references
            for array_name in self.array_variables:
                if isinstance(self.array_variables[array_name], list):
                    array_pattern = rf'\b{re.escape(array_name)}\('
                    start = 0
                    while True:
                        match = re.search(array_pattern, expr[start:])
                        if not match:
                            break
                        start_index = start + match.end()
                        paren_count = 1
                        end_index = start_index
                        for i, char in enumerate(expr[start_index:], start=start_index):
                            if char == '(':
                                paren_count += 1
                            elif char == ')':
                                paren_count -= 1
                                if paren_count == 0:
                                    end_index = i
                                    break
                        if paren_count != 0:
                            self.debug_print(f"Mismatched parentheses in array reference: {array_name}", 'error')
                            return None
                        
                        index_expr = expr[start_index:end_index]
                        index = int(eval_nested(index_expr))
                        if 0 <= index < len(self.array_variables[array_name]):
                            replacement = self.array_variables[array_name][index]
                            if array_name.endswith('$') or isinstance(replacement, str):
                                replacement = f"'{replacement}'"
                            expr = expr[:start + match.start()] + str(replacement) + expr[end_index + 1:]
                        else:
                            self.debug_print(f"Array index out of bounds: {array_name}[{index}]", 'error')
                            return None
                        start = start + match.start() + len(str(replacement))

            # Split the expression by string literals
            parts = self._regex_cache['string_split'].split(expr)

            # Sort variables by length in descending order
            sorted_vars = sorted(self.scalar_variables.keys(), key=len, reverse=True)

            for i in range(0, len(parts), 2):
                if not parts[i].strip():
                    continue  # Skip empty parts

                # Replace variables with their values
                for var in sorted_vars:
                    value = self.scalar_variables[var]
                    new_parts = []
                    last_end = 0
                    # Add this condition to check for protected functions
                    if var.upper() in protected_functions:
                        pattern = rf'\b{re.escape(var)}\b(?!\()'
                    else:
                        pattern = re.escape(var) if var.endswith('$') else r'\b' + re.escape(var) + r'\b'
                    
                    for match in re.finditer(pattern, parts[i]):
                        start, end = match.span()
                        if not is_within_quotes(parts[i], start):
                            new_parts.append(parts[i][last_end:start])
                            if var.endswith('$'):
                                replacement = f"'{str(value).rstrip()}'"
                                # Check for string concatenation
                                if i + 2 < len(parts) and parts[i+1] == '+':
                                    replacement = replacement[:-1]  # Remove trailing quote
                            else:
                                replacement = str(value)
                            new_parts.append(replacement)
                        else:
                            new_parts.append(parts[i][last_end:end])
                        last_end = end
                    new_parts.append(parts[i][last_end:])
                    parts[i] = ''.join(new_parts)

            # Rejoin the parts
            expr = ''.join(parts)
            if self.debug_mode:
                self.debug_print(f"Expression after variable substitution: {expr}")
           
            try:
                # Evaluate the entire expression at once
                result = eval(expr, {"__builtins__": None}, {
                    "int": int, "float": float, "str": str, 
                    "chr": chr, "ord": ord,
                    "self": self
                })
                if self.debug_mode:
                    self.debug_print(f"Evaluation result: {result}")
                return result
            except Exception as e:
                if self.debug_mode:
                    self.debug_print(f"Evaluation failed: {e}")
                # If eval fails, return the original expression (for string literals)
                return expr.strip("'\"")
        
        return eval_nested(expr)

    def find_line_index(self, line_number):
        # Use binary search for better performance on large programs
        left, right = 0, len(self.sorted_program) - 1
        
        while left <= right:
            mid = (left + right) // 2
            current_line_number = float(self.sorted_program[mid].split()[0])
            
            if current_line_number == line_number:
                return mid
            elif current_line_number < line_number:
                left = mid + 1
            else:
                right = mid - 1
        
        return -1

    # Memory methods for TRS-80
    def poke(self, address, value):
        """
        Simulate POKE command for TRS-80 screen memory.
        Screen memory starts at 15360 and ends at 16383.
        """
        if 15360 <= address <= 16383:
            screen_pos = address - 15360
            row = screen_pos // 64
            col = screen_pos % 64
            
            # Update the screen_content
            self.screen_content[row][col] = chr(value)
            
            # Update the screen display
            x = col * self.pixel_size * 2
            y = row * self.pixel_size * 3
            self.screen.create_text(x, y, text=chr(value), font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")
            
            self.debug_print(f"POKE: Address={address}, Value={value}, Row={row}, Col={col}")
        else:
            self.debug_print(f"POKE: Address={address}, Value={value}")
            self.debug_print(f"Warning: Address out of range for screen memory")

        
    def peek(self, address):
        if address == 14400:
            current_time = time.time()
            if current_time - self.last_key_time >= self.key_check_interval:
                self.master.update_idletasks()  # Process events without full GUI update
                self.last_key_time = current_time
                if self.last_key_pressed:
                    key_value = ord(self.last_key_pressed)
                    self.debug_print(f"PEEK: Address={address}, Value={key_value}, Key={self.last_key_pressed}")
                    self.last_key_pressed = None
                    return key_value
            return 0
        elif 15360 <= address <= 16383:
            screen_pos = address - 15360
            row = screen_pos // 64
            col = screen_pos % 64
            return ord(self.screen_content[row][col])
        else:
            return 0
    
    def inkey(self):
        # Check if a key has been pressed
        # Process events but don't do full GUI update to avoid timing issues
        self.master.update_idletasks()
        
        key = self.last_key_pressed
        if key:         
            self.debug_print(f"INKEY$ returning: '{key}'")
            # Clear the key after returning it
            self.last_key_pressed = None
            return key  
        self.debug_print("INKEY$ returning empty string")
        return ""  # Return an empty string if no key was pressed

    #GRAPHICS METHODS - OPTIMIZED FOR SPEED
    def set_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 1
            # Batch graphics updates for better performance
            if not hasattr(self, '_pending_graphics'):
                self._pending_graphics = []
            self._pending_graphics.append(('set', x, y))
            
            # Process graphics in batches to improve speed
            if len(self._pending_graphics) >= 20:
                self._flush_graphics()

    def reset_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 0
            # Batch graphics updates for better performance
            if not hasattr(self, '_pending_graphics'):
                self._pending_graphics = []
            self._pending_graphics.append(('reset', x, y))
            
            # Process graphics in batches to improve speed
            if len(self._pending_graphics) >= 20:
                self._flush_graphics()
    
    def _flush_graphics(self):
        """Process all pending graphics operations in one batch"""
        if not hasattr(self, '_pending_graphics') or not self._pending_graphics:
            return
        
        # Process all pending operations
        for operation, x, y in self._pending_graphics:
            if operation == 'set':
                self.screen.create_rectangle(
                    x * self.pixel_size, y * self.pixel_size,
                    (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                    fill="lime", outline="lime"
                )
            else:  # reset
                self.screen.create_rectangle(
                    x * self.pixel_size, y * self.pixel_size,
                    (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                    fill="black", outline="black"
                )
        
        # Clear the pending operations
        self._pending_graphics = []
        
        # Update the display once for all operations
        self.master.update_idletasks()

    def get_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            return self.pixel_matrix[y][x]
        return 0
    
    def flush_graphics(self):
        """Public method to force immediate graphics update"""
        self._flush_graphics()

    def create_tape_file(self): 
        self.debug_print("Creating tape .dat file")
        file_name = filedialog.asksaveasfilename(defaultextension=".dat")
        if file_name:
            self.tape_file = file_name
            with open(self.tape_file, 'w'):
                pass
            self.debug_print(f"Created tape file: {self.tape_file}")
        else:
            self.debug_print("Error: Tape file creation cancelled")

    def select_tape_file(self):
        """Open a file dialog to select the tape file."""
        
        self.debug_print("Selecting tape file")
        
        self.tape_file = filedialog.askopenfilename(
            title="Select Tape File",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if not self.tape_file:
            # If user cancels, create a default tape file
            self.tape_file = "default_tape.dat"
        self.debug_print(f"Selected tape file: {self.tape_file}")

    def read_from_tape(self):
        """Read a line from the tape file."""
        if not os.path.exists(self.tape_file):
            return None
        
        with open(self.tape_file, 'r') as file:
            lines = file.readlines() #how does this work?
            self.debug_print(f"Reading from tape: len={len(lines)}, pointer={self.tape_pointer}")
            if self.tape_pointer < len(lines):
                data = lines[self.tape_pointer].strip()
                self.tape_pointer += 1
                return data
            else:
                self.debug_print("Error: No more data on tape")
                return None
            
    def write_to_tape(self, data):
        """Append data to the tape file."""
        with open(self.tape_file, 'a') as file:
            file.write(f"{data}\n")

    #Interface methods
    def save_program(self):
        filename = filedialog.asksaveasfilename(defaultextension=".bas")
        if filename:
            with open(filename, 'w') as f:
                f.write(self.input_area.get(1.0, tk.END))

    def load_program(self):
        filename = filedialog.askopenfilename(filetypes=[("BASIC files", "*.bas"), ("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            with open(filename, 'r') as f:
                content = f.read()
                self.input_area.delete(1.0, tk.END)
                self.input_area.insert(tk.END, content)
                # Update stored_program from loaded content
                self.stored_program = [line for line in content.strip().split('\n') if line.strip()]
        # turn on the RUN button and Step button list
        self.run_button.config(state=tk.NORMAL)
        self.step_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.NORMAL)

    def show_specific_help(self, help_index):
        """Show a specific help screen in a non-modal window"""
        help_texts = [
            ("Commands & Syntax", help_text1),
            ("Functions & Operators", help_text2),
            ("Graphics & Memory", help_text3),
            ("Examples & Tips", help_text4)
        ]

        if 0 <= help_index < len(help_texts):
            title, content = help_texts[help_index]
            self.show_help_window(f"TRS-80 Help - {title}", content)

    def show_all_help(self):
        """Show all help screens in sequence"""
        help_texts = [
            ("Commands & Syntax", help_text1),
            ("Functions & Operators", help_text2),
            ("Graphics & Memory", help_text3),
            ("Examples & Tips", help_text4)
        ]
        
        all_content = ""
        for title, content in help_texts:
            all_content += f"=== {title.upper()} ===\n\n{content}\n\n"
        
        self.show_help_window("TRS-80 Complete Help Reference", all_content)
    
    def show_help_window(self, title, content):
        """Create a non-modal help window that fits on 7" screen"""
        help_window = tk.Toplevel(self.master)
        help_window.title(title)
        # Position help window to not overlap main window
        self.position_child_window(help_window, 500, 300, 250, 80)
        
        # Create scrolled text widget with smaller font
        help_text_widget = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, font=("Courier", 8))
        help_text_widget.pack(expand=True, fill='both', padx=5, pady=5)
        
        # Insert help content
        help_text_widget.insert(tk.END, content)
        help_text_widget.config(state=tk.DISABLED)  # Make it read-only
        
        # Add close button with smaller size
        close_button = tk.Button(help_window, text="Close", command=help_window.destroy, font=("Arial", 7), width=8, height=1)
        close_button.pack(pady=2)

    def toggle_scale(self):
        # Check if running on Raspberry Pi
        if hasattr(self, 'is_raspberry_pi') and self.is_raspberry_pi:
            messagebox.showinfo("Scale Not Available", 
                              "2x scaling is disabled on Raspberry Pi.")
            return
            
        # Toggle between 1x and 2x scale
        if self.scale_factor == 1:
            self.scale_factor = 2
            self.scale_button.config(text="1X")
        else:
            self.scale_factor = 1
            self.scale_button.config(text="2X")
        self.resize_components()

    def resize_components(self):
        # Resize the screen
        self.pixel_size = PIXEL_SIZE * self.scale_factor
        self.screen.config(width=INITIAL_WIDTH * self.scale_factor, height=INITIAL_HEIGHT * self.scale_factor)
        
        # Resize the font for input area
        self.input_area.config(font=("Courier", self.input_font_size* self.scale_factor))
        
        # Redraw the screen content
        self.redraw_screen()

    def enable_immediate_mode(self):
        """Enable immediate mode input on the main screen"""
        if not self.program_running and not self.waiting_for_input:
            self.immediate_mode = True
            self.screen.config(state=tk.NORMAL)
            self.screen.bind("<Key>", self.handle_immediate_mode_key)
            self.screen.bind("<Return>", self.handle_immediate_mode_return)
            self.screen.focus_set()
            # Show prompt if screen is empty or after program ends
            if self.cursor_row == 0 and self.cursor_col == 0:
                self.print_to_screen("READY", end='\n')
                self.print_to_screen(">", end='')
            else:
                # Avoid duplicate prompt: check if current line already ends with '>'
                line_str = ''.join(self.screen_content[self.cursor_row]).rstrip()
                if not line_str.endswith('>'):
                    if self.cursor_col > 0:
                        self.print_to_screen("")  # New line if not at start of line
                    self.print_to_screen(">", end='')

    def disable_immediate_mode(self):
        """Disable immediate mode input"""
        self.immediate_mode = False
        self.screen.unbind("<Key>")
        self.screen.unbind("<Return>")
        self.command_buffer = ""

    def handle_immediate_mode_key(self, event):
        """Handle keyboard input in immediate mode"""
        if not self.immediate_mode or self.program_running:
            return "break"
        
        if event.keysym == 'Return':
            # Fallback: if Return binding was somehow lost, process command here
            return self.handle_immediate_mode_return(event)
        
        if event.keysym == 'BackSpace':
            if self.command_buffer:
                # Remove last character from buffer
                self.command_buffer = self.command_buffer[:-1]
                # Handle backspace on screen
                if self.cursor_col > 1 or (self.cursor_col == 1 and self.screen_content[self.cursor_row][0] != '>'):  # Don't delete the prompt
                    self.cursor_col -= 1
                    x = self.cursor_col * self.pixel_size * 2
                    y = self.cursor_row * self.pixel_size * 3
                    self.screen.create_rectangle(x, y, x + self.pixel_size * 2, y + self.pixel_size * 3, fill="black", outline="black")
                    self.screen_content[self.cursor_row][self.cursor_col] = ' '
                    self.update_cursor_display()
        elif event.char and event.char.isprintable():
            # Add character to buffer and display
            char = event.char.upper()
            self.command_buffer += char
            
            # Display character on screen
            x = self.cursor_col * self.pixel_size * 2
            y = self.cursor_row * self.pixel_size * 3
            self.screen.create_text(x, y, text=char, font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")
            self.screen_content[self.cursor_row][self.cursor_col] = char
            self.cursor_col += 1
            
            # Handle line wrap
            if self.cursor_col >= 64:
                self.cursor_row += 1
                self.cursor_col = 0
                if self.cursor_row >= 16:
                    self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                    self.cursor_row = 15
                    # Also scroll graphics up by one text line (3 pixel rows)
                    self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
                    self.redraw_screen()
            
            self.update_cursor_display()
        
        return "break"

    def handle_immediate_mode_return(self, event):
        """Process the command when Enter is pressed in immediate mode"""
        if not self.immediate_mode or self.program_running:
            return "break"
        
        command = self.command_buffer.strip()
        self.command_buffer = ""
        
        # Move to next line
        self.cursor_row += 1
        self.cursor_col = 0
        if self.cursor_row >= 16:
            self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
            self.cursor_row = 15
            # Also scroll graphics up by one text line (3 pixel rows)
            self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
            self.redraw_screen()
        
        if command:
            self.process_immediate_command(command)
        
        # Show prompt for next command only if we're still in immediate mode
        # and not running a program (process_immediate_command might have started one)
        if self.immediate_mode and not self.program_running and not self.waiting_for_input:
            self.print_to_screen(">", end='')
        
        return "break"

    def process_immediate_command(self, command):
        """Process commands entered in immediate mode"""
        self.debug_print(f"Immediate mode command: {command}")
        
        # Check if it's a numbered line (program entry)
        if command and command.split()[0].replace('.', '').isdigit():
            line_number = command.split()[0]
            # Add to stored program
            self.stored_program = [line for line in self.stored_program if not line.startswith(line_number + ' ')]
            if len(command.split()) > 1:  # If there's content after line number
                self.stored_program.append(command)
            # Sort the program
            self.stored_program.sort(key=lambda x: float(x.split()[0]))
            # Update the input area with the stored program
            self.input_area.delete(1.0, tk.END)
            self.input_area.insert(tk.END, '\n'.join(self.stored_program))
            return
        
        # Process immediate commands
        cmd_parts = command.split(maxsplit=1)
        if not cmd_parts:
            return
        
        cmd = cmd_parts[0]
        
        if cmd == "RUN":
            self.disable_immediate_mode()
            self.run_program()
            return  # Don't show prompt here - it will be shown when program ends
        
        elif cmd == "LIST":
            if len(cmd_parts) > 1:
                # Handle LIST with line numbers
                self.list_program_range(cmd_parts[1])
            else:
                self.list_program()
        
        elif cmd == "NEW":
            response = self.print_to_screen("NEW PROGRAM - ARE YOU SURE? (Y/N)")
            # For simplicity, we'll just clear immediately
            self.new_program()
            self.stored_program = []
            self.input_area.delete(1.0, tk.END)
            self.print_to_screen("READY")
        
        elif cmd == "CLEAR":
            self.scalar_variables = {}
            self.array_variables = {}
            self.for_loops = {}
            self.gosub_stack = []
            self.data_pointer = 0
            self.print_to_screen("VARIABLES CLEARED")
        
        elif cmd == "CONT":
            if self.program_paused:
                self.disable_immediate_mode()
                self.stop_program()  # This toggles the pause state
        
        elif cmd == "LOAD":
            self.disable_immediate_mode()
            self.load_program()
            self.enable_immediate_mode()
            return  # Don't show another prompt
        
        elif cmd == "SAVE":
            self.disable_immediate_mode()
            self.save_program()
            self.enable_immediate_mode()
        
        elif cmd == "CLS":
            self.clear_screen()
            self.print_to_screen("READY", end='\n')
        
        elif cmd == "DELETE":
            if len(cmd_parts) > 1:
                self.delete_lines(cmd_parts[1])
        
        elif cmd == "SYSTEM":
            self.print_to_screen("SYSTEM COMMAND NOT IMPLEMENTED")
        
        else:
            # Try to execute as an immediate statement
            try:
                self.execute_command(command)
            except Exception as e:
                self.print_to_screen(f"?{str(e)}")

    def list_program_range(self, range_spec):
        """List specific line numbers or ranges"""
        # Always sync from input area first
        current_program = self.input_area.get(1.0, tk.END).strip().split('\n')
        self.stored_program = [line for line in current_program if line.strip()]
        
        try:
            if '-' in range_spec:
                start, end = map(float, range_spec.split('-'))
                lines = [line for line in self.stored_program 
                        if start <= float(line.split()[0]) <= end]
            else:
                target = float(range_spec)
                lines = [line for line in self.stored_program 
                        if float(line.split()[0]) == target]
            
            if lines:
                for line in lines:
                    self.print_to_screen(line)
            else:
                self.print_to_screen("NO SUCH LINE")
        except:
            self.print_to_screen("?SYNTAX ERROR")

    def delete_lines(self, range_spec):
        """Delete specific line numbers or ranges"""
        # Always sync from input area first
        current_program = self.input_area.get(1.0, tk.END).strip().split('\n')
        self.stored_program = [line for line in current_program if line.strip()]
        
        try:
            if '-' in range_spec:
                start, end = map(float, range_spec.split('-'))
                self.stored_program = [line for line in self.stored_program 
                                     if not (start <= float(line.split()[0]) <= end)]
            else:
                target = float(range_spec)
                self.stored_program = [line for line in self.stored_program 
                                     if float(line.split()[0]) != target]
            
            # Update the input area
            self.input_area.delete(1.0, tk.END)
            self.input_area.insert(tk.END, '\n'.join(self.stored_program))
            self.print_to_screen("DELETED")
        except:
            self.print_to_screen("?SYNTAX ERROR")

help_text1 = """
TRS-80 BASIC Simulator Help

Immediate Mode Commands (type directly on green screen):
- RUN - Run the program
- LIST [line#] or [line#-line#] - List program
- NEW - Clear program memory
- CLEAR - Clear variables
- CONT - Continue after STOP
- LOAD - Load program from file
- SAVE - Save program to file
- CLS - Clear screen
- DELETE line# or line#-line# - Delete lines

Program Commands:
- PRINT "text" or PRINT expression [, expression...]
- PRINT "text", expression
- PRINT@ position, expression  (position 0-1023)
- POKE address, value
- CLS (Clear Screen)
- LET variable = expression (LET is optional)
- LET string$ = "text" or LET string$ = expression
- INPUT variable or INPUT "prompt"; variable
- GOTO line_number
- ON expression GOTO line1, line2, ...
- IF condition THEN action [ELSE action]
- FOR variable = start TO end [STEP step]
- NEXT [variable]
- REM comment
- GOSUB line_number
- RETURN
- DIM variable(size) or DIM string$(size)
- DATA value1, value2, ...
- READ variable1, variable2, ...
- RESTORE
- STOP (Pause program - can continue)
- END (Stop program)
- PRINT#-1,expression (write to tape)
- INPUT#-1,variable (read from tape)"""

help_text2 = """
Mathematical Functions:
- ABS(x): Absolute value
- INT(x): Integer part (rounds toward zero)
- FIX(x): Truncate to integer
- SGN(x): Sign (-1 if x<0, 0 if x=0, 1 if x>0)
- SQR(x): Square root
- SIN(x), COS(x), TAN(x): Trig functions (radians)
- EXP(x): e^x
- LOG(x): Natural logarithm
- RND: Random 0.0 to 0.999999
- RND(n): Random integer 0 to n-1

String Functions:
- LEN(string$): Length of string
- LEFT$(string$, n): Leftmost n characters
- RIGHT$(string$, n): Rightmost n characters
- MID$(string$, start[, length]): Substring (1-based)
- STR$(number): Convert number to string
- VAL(string$): Convert string to number
- CHR$(code): ASCII code to character
- ASC(string$): First character to ASCII code
- STRING$(count, char): Repeat character
- INSTR([start,] string$, find$): Find substring (1-based)
- INKEY$: Get key press (non-blocking)

Operators:
- Arithmetic: +, -, *, /, ^ (power), MOD
- Comparison: =, <>, <, >, <=, >=
- Logical: AND, OR, NOT
- String: + (concatenation)
"""

help_text3 = """
Graphics & Screen:
- SET(x, y): Turn on pixel (x:1-128, y:1-48)
- RESET(x, y): Turn off pixel
- POINT(x, y): Check pixel (returns 0 or 1)
- TAB(n): Move to column n in PRINT

Memory Functions:
- PEEK(address): Read memory byte
  * 14400: Keyboard buffer
  * 15360-16383: Screen memory
- POKE address, value: Write memory byte

Special Features:
- Multiple statements per line with :
- Implicit LET (can omit LET keyword)
- Line numbers can use decimals (10.5)
- Variables: A-Z, A0-Z9, A$-Z$, A0$-Z9$
- Arrays: DIM creates size+1 elements (0 to size)
- PRINT formatting:
  * ; = no space between items
  * , = tab to next 16-char column
  * Trailing ; or , suppresses newline

Examples:
10 PRINT "HELLO"; TAB(20); "WORLD"
20 A = 5: B = 10: PRINT A + B
30 IF RND < 0.5 THEN PRINT "HEADS" ELSE PRINT "TAILS"
40 FOR I = 1 TO 10: SET(I*10, I*4): NEXT
"""

help_text4 = """
Example Programs:

1. Keyboard Test:
10 CLS
20 K$ = INKEY$
30 IF K$ = "" THEN 20
40 PRINT "YOU PRESSED: "; K$
50 IF K$ <> "Q" THEN 20
60 END

2. Graphics Demo:
10 CLS
20 FOR X = 1 TO 128 STEP 4
30 FOR Y = 1 TO 48 STEP 4
40 IF (X + Y) MOD 8 = 0 THEN SET(X,Y)
50 NEXT Y: NEXT X
60 END

3. Data/Read Example:
10 DATA "APPLE", "BANANA", "CHERRY"
20 FOR I = 1 TO 3
30 READ F$
40 PRINT I; ": "; F$
50 NEXT I
60 END

4. Screen Memory:
10 REM DRAW PATTERN ON SCREEN
20 FOR I = 15360 TO 15423
30 POKE I, 42  ' * CHARACTER
40 NEXT I
50 END

Special Keys:
- ESC or Ctrl+C: BREAK (stop running program)
- Ctrl+R: Emergency reset to immediate mode
- Right-click: Copy/paste options
- Click green screen: Auto-recover immediate mode

Tips:
- Use Step/Debug mode to trace execution
- 2X button doubles display size
- Assistant button for AI help
- Cursor disappears during program execution (authentic TRS-80)
"""

# Create the main window and start the application
root = tk.Tk()
app = TRS80Simulator(root)
root.mainloop()

