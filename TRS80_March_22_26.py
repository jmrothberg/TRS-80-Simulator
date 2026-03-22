# ===========================================================================
#  TRS-80 Model I Level II BASIC Simulator
# ===========================================================================
#  Author: Jonathan Rothberg (JMR)
#  First working version: Aug 19, 2024
#
#  Changelog:
#    Aug 21 2024 - Multiple statements per line, additional functions
#    Aug 23 2024 - Graphics commands (SET, RESET, POINT)
#    Aug 27 2024 - POINT fix, implicit LET, GUI polish, coordinate fixes
#    Sep  5 2024 - Nested-paren expression evaluator rewrite
#    Sep  7 2024 - Pin to Python 3.11 (PyInstaller compat)
#    Jul  6 2025 - Ollama support, immediate-mode green-screen prompt
#    Sep 24 2025 - 7" Raspberry Pi display, LLM error handling
#    Jan 21 2026 - Hailo-10H AI accelerator for Pi LLM inference
#    Mar 22 2026 - Performance optimizations (single-pass keyword
#                  replacement, cached fonts/dimensions, canvas
#                  itemconfigure, guarded debug prints)
#
# ---------------------------------------------------------------------------
#  HOW THE INTERPRETER WORKS  (read this before diving into the code)
# ---------------------------------------------------------------------------
#
#  The interpreter turns BASIC source text into execution through a five-
#  stage pipeline that runs inside a single Tkinter main-loop:
#
#  1. EDITING & STORAGE
#     The user types BASIC lines into the input area (ScrolledText widget)
#     or directly on the green screen in immediate mode.  Lines with a
#     leading number are stored in `self.stored_program`; lines without a
#     number execute immediately.
#
#  2. PREPROCESSING  (preprocess_program)
#     Before RUN, multi-statement lines like "10 A=1: B=2" are split on
#     colons into separate entries ("10 A=1", "10.1 B=2").  Colons that
#     appear inside quoted strings or after IF/THEN/ELSE are preserved.
#     DATA statements are pre-scanned into self.data_values so READ can
#     access them in program order regardless of execution flow.
#
#  3. EXECUTION LOOP  (execute_next_line)
#     A while-loop walks self.current_line_index through three parallel
#     arrays built at RUN time:
#       _line_numbers[i]   – the BASIC line number (float, supports 10.1)
#       _line_commands[i]   – the command text after the line number
#       _line_cmd_words[i]  – the first keyword, pre-extracted for dispatch
#     Each iteration calls execute_command(), which returns:
#       None   → advance to next line
#       int/float → GOTO that line number (binary-searched via find_line_index)
#     The loop yields to the Tkinter event loop every N iterations so the
#     GUI stays responsive and INKEY$/PEEK(14400) can poll keystrokes.
#
#  4. COMMAND DISPATCH  (execute_command → _command_handlers dict)
#     The pre-extracted keyword is looked up in self._command_handlers, a
#     dict mapping strings like 'PRINT', 'FOR', 'GOTO' to _cmd_* methods.
#     If the keyword isn't found but the line contains '=', it's treated
#     as an implicit LET ("A=5" becomes "LET A=5").
#
#  5. EXPRESSION EVALUATION  (evaluate_expression → _eval_nested)
#     Expressions like "A*2+RND(5)" go through these stages:
#       a. Fast paths – pure integers, negative integers, and simple
#          variable lookups return immediately without regex.
#       b. INKEY$ replacement – checked once per expression.
#       c. Keyword translation – a single combined regex pass converts
#          BASIC operators (AND→and, OR→or, MOD→%, ^→**, =→==, <>→!=)
#          and bare RND to Python equivalents.  Matches inside quoted
#          strings are skipped using a bytearray quote-map.
#       d. Built-in functions – a regex matches function calls like
#          INT(...), RND(...), LEFT$(...); the dispatch table
#          _builtin_functions maps each name to a handler.
#       e. Array substitution – array references like A(I) are resolved
#          from self.array_variables.
#       f. Variable substitution – scalar variables are replaced longest-
#          first so that "AB" doesn't clobber "A" inside "AB".
#       g. Comparison wrapping – operators like >, <, >= are rewritten
#          into function calls _gt(a,b) that return -1 (true) or 0 (false)
#          for TRS-80 semantics.
#       h. Python eval() – the fully-transformed string is evaluated in
#          a restricted namespace containing only math helpers and the
#          comparison/logic wrappers.
#
#  SCREEN MODEL
#     Text: 64 columns x 16 rows stored in self.screen_content[][].
#     Graphics: 128 x 48 pixel grid stored in self.pixel_matrix[][].
#     Each text cell covers a 2x3 block of graphics pixels.
#     The Tkinter Canvas draws text items tagged "c{row}_{col}" and pixel
#     rectangles tagged "p{x}_{y}" so items are bounded and reusable.
#     Graphics SET/RESET calls are batched in _pending_graphics and flushed
#     every 20 operations or at GUI-update boundaries.
#
#  KEY DATA STRUCTURES
#     scalar_variables   – dict {name: value}  (e.g. {"A": 5, "N$": "HI"})
#     array_variables    – dict {name: list}   (e.g. {"A": [0,0,0,...]})
#     for_loops          – OrderedDict {var: {start, end, step, current, ...}}
#     gosub_stack        – list of return-line indices
#     _eval_namespace    – restricted dict passed to Python's eval()
#
# ===========================================================================
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import re
import random
import os
import math
import time
import platform
# TRS80LLMSupport is imported lazily in open_llm_support() to avoid
# pulling in torch/transformers at startup (faster launch, smaller binary).
TRS80LLMSupport = None
PIXEL_SIZE = 6  # Reduced from 6 to 4 for smaller screen
INITIAL_WIDTH = 768  # 128 pixels * 6 = 774 to accommodate coordinates 1-128
INITIAL_HEIGHT = 288  # Reduced from 288 to 192 for 7" screen

class TRS80Simulator:
    # ============================================================
    #  SECTION: Init & Configuration
    #  Build the Tkinter GUI (Canvas, input area, buttons), set up
    #  interpreter state, compile regex patterns, and initialize
    #  the command/function dispatch tables.
    # ============================================================
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
        self._char_w = self.pixel_size * 2   # cached character cell width
        self._char_h = self.pixel_size * 3   # cached character cell height
        self._screen_font = ("Courier", self.base_font_size * self.scale_factor)
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

        self.run_button = tk.Button(button_frame, text="RUN", command=self.run_program, font=("Arial", 8), width=4, height=1)
        self.run_button.pack(side=tk.LEFT, padx=1)  # Further reduced padding

        self.reset_button = tk.Button(button_frame, text="CLEAR", command=self.clear_variables_button_cmd, font=("Arial", 8), width=5, height=1)
        self.reset_button.pack(side=tk.LEFT, padx=1)

        # Add Stop button
        self.stop_button = tk.Button(button_frame, text="STOP", command=self.stop_program, state=tk.DISABLED, font=("Arial", 8), width=10, height=1)
        self.stop_button.pack(side=tk.LEFT, padx=1)

        # Add Step button
        self.step_button = tk.Button(button_frame, text="STEP", command=self.step_program, state=tk.DISABLED, font=("Arial", 8), width=4, height=1)
        self.step_button.pack(side=tk.LEFT, padx=1)

        self.new_button = tk.Button(button_frame, text="LIST", command=self.list_program, font=("Arial", 8), width=4, height=1)
        self.new_button.pack(side=tk.LEFT, padx=1)

        self.clear_button = tk.Button(button_frame, text="NEW", command=self.clear_memory_button_cmd, font=("Arial", 8), width=4, height=1)
        self.clear_button.pack(side=tk.LEFT, padx=1)

        self.save_button = tk.Button(button_frame, text="SAVE", command=self.save_program, font=("Arial", 8), width=4, height=1)
        self.save_button.pack(side=tk.LEFT, padx=1)

        self.load_button = tk.Button(button_frame, text="LOAD", command=self.load_program, font=("Arial", 8), width=4, height=1)
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
        self._last_debug_command = ""
        self._last_eval_original = ""
        self._last_eval_substituted = ""
        self.original_program = []
        self._pending_graphics = []
        self._active_pixels = set()
        
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

        # Initialize command and function dispatch tables
        self._init_command_handlers()
        self._init_builtin_functions()

        # Restricted namespace for Python eval() in the expression evaluator.
        # __builtins__=None prevents access to open/exec/import etc.
        # The _gt/_lt/etc. lambdas implement TRS-80 comparison semantics
        # (return -1 for true, 0 for false instead of Python's True/False).
        self._eval_globals = {"__builtins__": None}
        self._eval_namespace = {
            "int": int, "float": float, "str": str,
            "chr": chr, "ord": ord,
            "self": self,
            "_gt": lambda a, b: -1 if a > b else 0,
            "_lt": lambda a, b: -1 if a < b else 0,
            "_ge": lambda a, b: -1 if a >= b else 0,
            "_le": lambda a, b: -1 if a <= b else 0,
            "_eq": lambda a, b: -1 if a == b else 0,
            "_ne": lambda a, b: -1 if a != b else 0,
            "_bnot": lambda a: ~int(a),
        }

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
            x = self.cursor_col * self._char_w
            y = self.cursor_row * self._char_h

            # Draw a solid block cursor like the original TRS-80 (ASCII 143 or solid block)
            self.cursor_canvas_item = self.screen.create_rectangle(
                x, y,
                x + self._char_w,
                y + self._char_h,
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
        """Pre-compile all regex patterns used by the interpreter.

        Patterns are stored in self._regex_cache keyed by short names.
        This avoids re-compiling the same pattern on every expression
        evaluation or command parse.  The 'all_keywords' pattern is the
        combined single-pass regex used in _eval_nested to translate
        BASIC operators to Python equivalents in one re.sub call.
        """
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
        self._regex_cache['string_split'] = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
        # Cached patterns for expression evaluation (Part 3A)
        self._regex_cache['rnd_bare'] = re.compile(r'\bRND\b(?!\()')
        self._regex_cache['mod_op'] = re.compile(r'\bMOD\b')
        self._regex_cache['or_op'] = re.compile(r'\bOR\b')
        self._regex_cache['and_op'] = re.compile(r'\bAND\b')
        self._regex_cache['not_op'] = re.compile(r'\bNOT\b')
        self._regex_cache['equal_op'] = re.compile(r'(?<![=<>])=(?![=])')
        self._regex_cache['not_equal_op'] = re.compile(r'<>')
        self._regex_cache['exp_op'] = re.compile(r'\^')
        self._regex_cache['inkey'] = re.compile(r'\bINKEY\$')
        # Combined keyword regex for single-pass replacement in _eval_nested
        self._regex_cache['all_keywords'] = re.compile(
            r'\bRND\b(?!\()'     # bare RND (no parens)
            r'|\bMOD\b'
            r'|\bOR\b'
            r'|\bAND\b'
            r'|\bNOT\b'
            r'|<>'               # not-equal
            r'|(?<![=<>])=(?!=)' # single = (not ==, <=, >=, <>)
            r'|\^'               # exponent
        )

    # ============================================================
    #  SECTION: LLM Support
    #  Toggle, open, and close the optional AI companion window
    #  (TRS80LLMSupport) which can help write and debug BASIC code.
    # ============================================================
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
        global TRS80LLMSupport
        if TRS80LLMSupport is None:
            from TRS80LLMSupport import TRS80LLMSupport
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
            self.stored_program = self._sort_program_lines(current_program)

    def _sort_program_lines(self, lines):
        """Keep BASIC program lines in numeric line-number order."""
        cleaned = [line.rstrip() for line in lines if line.strip()]

        def sort_key(line):
            parts = line.split(maxsplit=1)
            if not parts:
                return (1, float('inf'))
            try:
                return (0, float(parts[0]))
            except ValueError:
                return (1, float('inf'))

        return sorted(cleaned, key=sort_key)
    
    # ============================================================
    #  SECTION: Debug & Variables Windows
    #  The debug window shows a timestamped execution trace
    #  (line number, step count, variable assignments, errors).
    #  The variables window shows live scalar/array/loop state.
    #  Both are Toplevel windows positioned for 7" screens.
    # ============================================================
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
        self.state_text.insert(tk.END, "STATUS\n")
        self.state_text.insert(tk.END, f"Program Running: {self.program_running}\n")
        self.state_text.insert(tk.END, f"Program Paused: {self.program_paused}\n")
        self.state_text.insert(tk.END, f"Stepping Mode: {self.stepping}\n")
        self.state_text.insert(tk.END, f"Last Key Pressed: {self.last_key_pressed}\n")
        self.state_text.insert(tk.END, f"Data Pointer: {self.data_pointer}\n\n")

        # Current line information - use the live parsed line tables when available.
        self.state_text.insert(tk.END, "CURRENT LINE\n")
        if 0 <= self.current_line_index < len(self._line_numbers):
            line_number = self._line_numbers[self.current_line_index]
            command = self._line_commands[self.current_line_index]
            self.state_text.insert(tk.END, f"Line Number: {line_number}\n")
            self.state_text.insert(tk.END, f"Command: {command}\n\n")
        else:
            self.state_text.insert(tk.END, "Program execution completed or not started\n\n")

        # Scalar variables
        self.state_text.insert(tk.END, "SCALAR VARIABLES\n")
        if self.scalar_variables:
            for var, value in sorted(self.scalar_variables.items()):
                self.state_text.insert(tk.END, f"{var} = {self._format_state_value(value)}\n")
        else:
            self.state_text.insert(tk.END, "None\n")

        # Arrays - summarize instead of dumping entire arrays.
        self.state_text.insert(tk.END, "\nARRAYS\n")
        if self.array_variables:
            for var, value in sorted(self.array_variables.items()):
                self.state_text.insert(tk.END, f"{self._summarize_state_array(var, value)}\n")
        else:
            self.state_text.insert(tk.END, "None\n")

        # Active FOR loops
        self.state_text.insert(tk.END, "\nACTIVE FOR LOOPS\n")
        if self.for_loops:
            for var, loop_info in self.for_loops.items():
                next_line = loop_info.get('next_line_number')
                self.state_text.insert(
                    tk.END,
                    f"{var}: current={loop_info.get('current')} start={loop_info.get('start')} "
                    f"end={loop_info.get('end')} step={loop_info.get('step')} next={next_line}\n"
                )
        else:
            self.state_text.insert(tk.END, "None\n")

        # GOSUB stack as target line numbers when possible.
        self.state_text.insert(tk.END, "\nGOSUB STACK\n")
        if self.gosub_stack:
            stack_lines = []
            for return_index in self.gosub_stack:
                if 0 <= return_index < len(self._line_numbers):
                    stack_lines.append(str(self._line_numbers[return_index]))
                else:
                    stack_lines.append(str(return_index))
            self.state_text.insert(tk.END, " -> ".join(stack_lines) + "\n")
        else:
            self.state_text.insert(tk.END, "Empty\n")

        self.state_text.config(state=tk.DISABLED)

    def _format_state_value(self, value):
        """Compact variable formatting for the Variables window."""
        if isinstance(value, str):
            return repr(value)
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    def _summarize_state_array(self, name, value):
        """Show only the useful parts of arrays instead of dumping full contents."""
        if not isinstance(value, list):
            return f"{name} = {self._format_state_value(value)}"

        if name.endswith('$'):
            active = [(i, v) for i, v in enumerate(value) if v != ""]
        else:
            active = [(i, v) for i, v in enumerate(value) if v != 0]

        if not active:
            return f"{name}({len(value) - 1}) = [all default]"

        preview = ", ".join(
            f"[{i}]={self._format_state_value(v)}" for i, v in active[:8]
        )
        if len(active) > 8:
            preview += f", ... ({len(active)} used)"

        return f"{name}({len(value) - 1}) = {preview}"

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
            # Show both BASIC line and step so traces match the program.
            timestamp = f"[Line {self._get_current_line_number()} | Step {self.current_line_index + 1}]"
            
            if level == 'error':
                self.debug_text.insert(tk.END, f"{timestamp} ERROR: {message}\n", 'error')
            elif level == 'warning':
                self.debug_text.insert(tk.END, f"{timestamp} WARNING: {message}\n", 'warning')
            else:
                self.debug_text.insert(tk.END, f"{timestamp} {message}\n")
            self.debug_text.see(tk.END)

    # ============================================================
    #  SECTION: Input Handling
    #  Keyboard events go through on_key_press, which routes to:
    #    - BREAK handling (Esc / Ctrl+C) during program execution
    #    - Keyboard buffer (PEEK 14400 / INKEY$) during RUN
    #    - Immediate-mode key handler when no program is running
    #  The BASIC INPUT statement temporarily rebinds the Canvas to
    #  handle_input_key / handle_input_return, then resumes execution.
    # ============================================================
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

    # ============================================================
    #  SECTION: GUI Setup & Menus
    #  Right-click context menus for cut/copy/paste on the green
    #  screen Canvas and the input ScrolledText area.
    # ============================================================
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

    # ============================================================
    #  SECTION: Screen Rendering
    #  The TRS-80 display is a Tkinter Canvas (green on black).
    #  Text characters are Canvas text items tagged "c{row}_{col}";
    #  graphics pixels are rectangles tagged "p{x}_{y}".
    #  print_to_screen writes characters and uses itemconfigure to
    #  update existing items (avoids delete+create overhead).
    #  _scroll_screen_up shifts screen_content and pixel_matrix up
    #  by one text row (3 pixel rows), then redraws.
    #  redraw_screen does a full repaint from the data arrays.
    # ============================================================
    def clear_input_area(self):
        self.input_area.delete(1.0, tk.END)

    def _scroll_screen_up(self):
        """Scroll screen content and graphics up by one text line"""
        self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
        self.cursor_row = 15
        self.pixel_matrix = self.pixel_matrix[3:] + [[0 for _ in range(128)] for _ in range(3)]
        # O(active) set-shift instead of O(6144) full scan
        self._active_pixels = {(x, y - 3) for x, y in self._active_pixels if y >= 3}
        self.redraw_screen()

    def clear_variables_button_cmd(self):
        # CLEAR matches TRS-80 BASIC: clear variables, keep the program.
        if self.program_running:
            self.program_running = False
            self.program_paused = False
            self.stop_button.config(text="DISABLED", state=tk.DISABLED)
        self.scalar_variables = {}
        self.array_variables = {}
        self.for_loops = {}
        self.gosub_stack = []
        self.data_pointer = 0
        self.data_values = []
        self.last_key_pressed = None
        self.print_to_screen("VARIABLES CLEARED")

    def clear_memory_button_cmd(self):
        # NEW matches TRS-80 BASIC: erase program and variables from memory.
        if self.program_running:
            self.program_running = False
            self.program_paused = False
            self.stop_button.config(text="DISABLED", state=tk.DISABLED)
        self.new_program()
        self.stored_program = []
        self.input_area.delete(1.0, tk.END)
        self.enable_immediate_mode()
        self.set_screen_focus()

    def clear_screen(self):
        # Flush any pending graphics before clearing
        self._flush_graphics()

        self.screen.delete("all")
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self._active_pixels = set()
        self.cursor_row = 0
        self.cursor_col = 0
        self.update_cursor_display()

        self._pending_graphics = []
    

    def new_program(self):
        """Reset all interpreter state for a fresh program.

        Clears variables, loop stacks, display, and the pre-parsed line
        arrays.  Called by RUN (before re-parsing), NEW, and on startup.
        """
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
        # Optimization 2: Pre-parsed line number/command arrays
        self._line_numbers = []
        self._line_commands = []
        # Optimization 5: Cached sorted variable list
        self._sorted_vars_cache = []
        self._last_var_count = 0
        # Optimization 6: Cached compiled array patterns
        self._array_patterns = {}
        # Cached compiled variable regex patterns
        self._var_regex_cache = {}
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self._active_pixels = set()

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

        self._last_debug_command = ""
        self._last_eval_original = ""
        self._last_eval_substituted = ""
        self.command_buffer = ""

        self.debug_print("New program initialized. All variables and states reset.")
            
    def reset_program(self):
        # Reset all variables and states without starting the program
        self.new_program()
        self.debug_print("Program reset. All variables and states cleared.")   

    def print_to_screen(self, *args, end='\n'):
        text = ' '.join(str(arg) for arg in args) + end
        chars_to_draw = []  # Batch characters for drawing
        char_w = self._char_w
        char_h = self._char_h

        for char in text:
            if char == '\n' or self.cursor_col >= 64:
                self.cursor_row += 1
                self.cursor_col = 0
                if self.cursor_row >= 16:
                    self._scroll_screen_up()
                    chars_to_draw = []
            else:
                self.screen_content[self.cursor_row][self.cursor_col] = char
                row, col = self.cursor_row, self.cursor_col
                chars_to_draw.append((col * char_w, row * char_h, char, row, col))
                self.cursor_col += 1

        # Draw all characters using itemconfigure when item exists, create_text otherwise
        screen = self.screen
        font = self._screen_font
        for x, y, char, row, col in chars_to_draw:
            tag = f"c{row}_{col}"
            items = screen.find_withtag(tag)
            if items:
                screen.itemconfigure(items[0], text=char)
            else:
                screen.create_text(x, y, text=char,
                    font=font, fill="lime", anchor="nw", tags=tag)

        # Update cursor display after printing
        self.update_cursor_display()


    def redraw_screen(self):
        self.screen.delete("all")
        ps = self.pixel_size

        # Redraw only active pixels (performance: skip empty positions)
        for x, y in self._active_pixels:
            self.screen.create_rectangle(
                x * ps, y * ps,
                (x + 1) * ps, (y + 1) * ps,
                fill="lime", outline="lime",
                tags=f"p{x}_{y}"
            )

        # Redraw text characters with tags for bounded canvas items
        char_w = self._char_w
        char_h = self._char_h
        font = self._screen_font
        for row in range(16):
            for col in range(64):
                char = self.screen_content[row][col]
                if char != ' ':
                    tag = f"c{row}_{col}"
                    self.screen.create_text(col * char_w, row * char_h, text=char,
                        font=font, fill="lime", anchor="nw", tags=tag)

    
    def handle_input_key(self, event):
        if self.waiting_for_input and event.widget == self.screen:
            if event.keysym == 'BackSpace':
                self.handle_backspace(event)
            elif event.char:
                if self.cursor_row >= 15 and self.cursor_col >= 63:
                    self._scroll_screen_up()
                    self.cursor_col = 0
                
                x = self.cursor_col * self._char_w
                y = self.cursor_row * self._char_h
                self.screen.create_text(x, y, text=event.char.upper(), font=self._screen_font, fill="lime", anchor="nw")
                
                self.screen_content[self.cursor_row][self.cursor_col] = event.char.upper()
                self.cursor_col += 1
                if self.cursor_col >= 64:
                    self.cursor_row += 1
                    self.cursor_col = 0
                    if self.cursor_row >= 16:
                        self._scroll_screen_up()

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
                x = self.cursor_col * self._char_w
                y = self.cursor_row * self._char_h
                self.screen.create_rectangle(x, y, x + self._char_w, y + self._char_h, fill="black", outline="black")
                
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
                self._scroll_screen_up()

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
        self.stored_program = self._sort_program_lines(current_program)
        
        if self.stored_program:
            program_text = '\n'.join(self.stored_program)
            self.input_area.delete(1.0, tk.END)
            self.input_area.insert(tk.END, program_text)
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

        def is_keyword_at(text, pos, keyword):
            """Check if keyword starts at pos with word boundaries."""
            klen = len(keyword)
            if text[pos:pos+klen] != keyword:
                return False
            if pos > 0 and text[pos-1].isalpha():
                return False
            if pos + klen < len(text) and text[pos+klen].isalpha():
                return False
            return True

        def find_split_colons(content):
            """Find colon positions that are safe to split on (not inside quotes, not after THEN/ELSE)."""
            positions = []
            in_if_clause = False
            upper_content = content.upper()
            i = 0
            while i < len(content):
                if content[i] == '"':
                    # Skip quoted strings
                    i += 1
                    while i < len(content) and content[i] != '"':
                        i += 1
                    i += 1
                    continue
                # REM makes the rest of the line a comment — stop splitting here
                if is_keyword_at(upper_content, i, 'REM'):
                    break
                # Check if we're entering an IF/THEN clause (with word boundaries)
                if is_keyword_at(upper_content, i, 'IF'):
                    in_if_clause = True
                if is_keyword_at(upper_content, i, 'THEN') or is_keyword_at(upper_content, i, 'ELSE'):
                    in_if_clause = True
                if content[i] == ':' and not in_if_clause:
                    positions.append(i)
                i += 1
            return positions

        self.debug_print("Preprocessing")
        preprocessed = []
        for line in program:
            if ':' in line:
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    preprocessed.append(line)
                    continue
                line_number = parts[0]
                content = parts[1]
                split_positions = find_split_colons(content)
                if split_positions:
                    # Split at the safe colon positions
                    statements = []
                    prev = 0
                    for pos in split_positions:
                        statements.append(content[prev:pos].strip())
                        prev = pos + 1
                    statements.append(content[prev:].strip())
                    for i, statement in enumerate(statements):
                        if not statement:
                            continue
                        if i == 0:
                            preprocessed.append(f"{line_number} {statement}")
                        else:
                            new_line_number = f"{line_number}.{i}"
                            preprocessed.append(f"{new_line_number} {statement}")
                else:
                    preprocessed.append(line)
            else:
                preprocessed.append(line)
        return preprocessed
    
    # ============================================================
    #  SECTION: Interpreter Core — Run & Execute
    #  run_program: syncs the input area, preprocesses (colon-split),
    #    sorts by line number, builds parallel arrays (_line_numbers,
    #    _line_commands, _line_cmd_words), pre-scans DATA, then enters
    #    execute_next_line.
    #  execute_next_line: tight while-loop that walks current_line_index
    #    forward, dispatching each line through execute_command.
    #    Yields to Tkinter periodically (update_idletasks / update)
    #    so the GUI stays responsive.
    #  preprocess_program: splits multi-statement lines on unquoted
    #    colons, preserving colons after IF/THEN/ELSE and inside strings.
    # ============================================================
    def run_program(self):
        """Entry point for RUN.  Resets state, preprocesses the source,
        builds the three parallel dispatch arrays, pre-scans DATA
        statements, then kicks off execute_next_line.
        """
        self.new_program()
        self.input_area.unbind("<Key>")
        self.input_area.unbind("<Return>")

        # Always sync from input area to stored_program before running
        program = self.input_area.get(1.0, tk.END).strip().split('\n')
        self.stored_program = self._sort_program_lines(program)
        self.original_program = program  # Store the original program
        preprocessed_program = self.preprocess_program(self.stored_program)
        self.sorted_program = sorted(
            [line for line in preprocessed_program if line.strip() and line.split()[0].replace('.', '').isdigit()],
            key=lambda x: float(x.split()[0])
        )
        # Optimization 2: Pre-parse line numbers, commands, and command words once
        self._line_numbers = []
        self._line_commands = []
        self._line_cmd_words = []
        for line in self.sorted_program:
            parts = line.strip().split(maxsplit=1)
            self._line_numbers.append(float(parts[0]))
            cmd = parts[1] if len(parts) > 1 else ''
            self._line_commands.append(cmd)
            # Pre-extract cmd_word for dispatch
            if cmd:
                cw = cmd.split('(')[0].split()[0] if cmd else ''
                if cw.startswith('PRINT'):
                    cw = 'PRINT'
                self._line_cmd_words.append(cw)
            else:
                self._line_cmd_words.append('')
        # If the program uses INKEY$ or PEEK(14400) for keyboard polling,
        # we must process Tkinter events every iteration so key presses
        # are picked up promptly.  Otherwise we can skip most updates.
        self._uses_inkey = any('INKEY$' in line for line in self.sorted_program)
        # Pre-scan all DATA statements before execution (TRS-80 behavior)
        self._prescan_data()
        self.program_running = True
        self.program_paused = False
        self.stop_button.config(text="STOP", state=tk.NORMAL)
        self.step_button.config(state=tk.NORMAL)  # Enable step button
        self.debug_print("Starting program execution")
        self.set_screen_focus()  # Set focus to the screen
        self.update_variables_window()  # Update variables window at start
        if not self.stepping:
            self.execute_next_line()
       
    def _prescan_data(self):
        """Pre-scan all DATA statements in program order (TRS-80 Level II BASIC behavior)"""
        self.data_values = []
        self.data_pointer = 0
        for line in self.sorted_program:
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                content = parts[1]
                # Check if second word is also a line number (from preprocessing)
                content_parts = content.split(maxsplit=1)
                if content_parts[0].replace('.', '').isdigit() and len(content_parts) > 1:
                    content = content_parts[1]
                if content.startswith('DATA'):
                    data = content[4:].strip()
                    self.data_values.extend(data.split(','))
        if self.data_values:
            self.debug_print(f"Pre-scanned {len(self.data_values)} DATA values")

    def execute_next_line(self):
        """Main execution loop — runs until the program ends, pauses, or
        waits for INPUT.

        Walks current_line_index through the pre-parsed line arrays.
        execute_command returns None (advance), a line number (GOTO/GOSUB),
        or sets waiting_for_input (INPUT pauses the loop and returns to
        the Tkinter event loop; handle_input_return resumes via after()).

        GUI responsiveness: update_idletasks every iteration when INKEY$
        is in use, otherwise every 10th; full update() every 25th.
        """
        update_counter = 0  # Counter for batching GUI updates
        uses_inkey = getattr(self, '_uses_inkey', True)  # Optimization 7

        while self.program_running and not self.program_paused:
            # Optimization 7: Only process events every iteration if INKEY$ is used
            if uses_inkey or update_counter % 10 == 0:
                self.master.update_idletasks()  # Process events without full redraw

            # Reduce full GUI updates for better performance - only every 25 iterations
            if update_counter % 25 == 0:
                self.master.update()  # Full GUI update including screen redraws
                # Flush any pending graphics operations
                self._flush_graphics()
            update_counter += 1

            if self.current_line_index >= len(self._line_numbers) or not self._line_numbers:
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

            # Optimization 2: Use pre-parsed line numbers and commands
            line_number = self._line_numbers[self.current_line_index]
            command = self._line_commands[self.current_line_index]

            # Only debug print every 10th line when not in debug mode for speed
            if self.debug_mode or update_counter % 10 == 0:
                self.debug_print(f"Executing line {line_number}: {command}")

            if command:
                # Check if command has a duplicate line number prefix (from preprocessing)
                parts = command.split(maxsplit=1)
                if len(parts) > 1 and parts[0].isdigit():
                    command = parts[1]
                    cmd_word = None  # re-parse needed
                else:
                    cmd_word = self._line_cmd_words[self.current_line_index] if self.current_line_index < len(self._line_cmd_words) else None
                result = self.execute_command(command, cmd_word=cmd_word)
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
        
        # Check for unmatched FOR/NEXT loops (skip REM lines and string literals)
        for_vars = []
        for line in self.stored_program:
            upper = line.upper()
            # Strip line number and get the content
            content_part = upper.split(None, 1)[1] if len(upper.split(None, 1)) > 1 else ''
            # Skip REM lines and lines where keyword only appears inside a string
            if content_part.startswith('REM ') or content_part == 'REM':
                continue
            # Remove string literals before checking for keywords
            stripped = re.sub(r'"[^"]*"', '', content_part)
            if 'FOR ' in stripped:
                try:
                    var = stripped.split('FOR ')[1].split('=')[0].strip()
                    for_vars.append(var)
                except:
                    pass
            if 'NEXT' in stripped:
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

    # ============================================================
    #  SECTION: TRS-80 Error Messages
    #  Authentic TRS-80 error codes: ?SN (Syntax), ?FC (Function
    #  Call), ?UL (Undefined Line), ?BS (Bad Subscript), ?OD (Out
    #  of Data), ?NF (NEXT without FOR), ?RG (RETURN without GOSUB).
    #  Each prints to the green screen and logs to the debug window.
    # ============================================================
    def _get_current_line_number(self):
        """Get current BASIC line number for error messages"""
        if self.current_line_index < len(self._line_numbers):
            ln = self._line_numbers[self.current_line_index]
            return str(int(ln)) if ln == int(ln) else str(ln)
        return '?'

    def _error_sn(self, detail=''):
        """?SN ERROR - Syntax Error"""
        ln = self._get_current_line_number()
        msg = f"?SN ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(f"{msg} - {detail}" if detail else msg, 'error')

    def _error_fc(self, detail=''):
        """?FC ERROR - Illegal Function Call"""
        ln = self._get_current_line_number()
        msg = f"?FC ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(f"{msg} - {detail}" if detail else msg, 'error')

    def _error_ul(self, line_num):
        """?UL ERROR - Undefined Line"""
        ln = self._get_current_line_number()
        msg = f"?UL ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(f"{msg} - Line {line_num} not found", 'error')

    def _error_bs(self, array_name='', index=0):
        """?BS ERROR - Bad Subscript"""
        ln = self._get_current_line_number()
        msg = f"?BS ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(f"{msg} - Index {index} out of bounds for {array_name}", 'error')

    def _error_od(self):
        """?OD ERROR - Out of Data"""
        ln = self._get_current_line_number()
        msg = f"?OD ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(msg, 'error')

    def _error_nf(self, var=''):
        """?NF ERROR - NEXT without FOR"""
        ln = self._get_current_line_number()
        msg = f"?NF ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(f"{msg} - Variable {var}" if var else msg, 'error')

    def _error_rg(self):
        """?RG ERROR - RETURN without GOSUB"""
        ln = self._get_current_line_number()
        msg = f"?RG ERROR IN {ln}"
        self.print_to_screen(msg)
        self.debug_print(msg, 'error')

    # ============================================================
    #  SECTION: Interpreter Core — Command Dispatch
    #  _command_handlers maps keyword strings to _cmd_* methods:
    #    'PRINT' → _cmd_print,  'FOR' → _cmd_for,  etc.
    #  execute_command extracts the first keyword (or uses the
    #  pre-parsed cmd_word from the execution loop), looks it up,
    #  and calls the handler.  If no handler matches and the line
    #  contains '=', it's treated as implicit LET.
    # ============================================================
    def _init_command_handlers(self):
        """Initialize the command dispatch table"""
        self._command_handlers = {
            'PRINT': self._cmd_print,
            'LET': self._cmd_let,
            'REM': self._cmd_rem,
            'POKE': self._cmd_poke,
            'SET': self._cmd_set_reset,
            'RESET': self._cmd_set_reset,
            'CLS': self._cmd_cls,
            'DIM': self._cmd_dim,
            'INPUT': self._cmd_input,
            'GOTO': self._cmd_goto,
            'IF': self._cmd_if,
            'FOR': self._cmd_for,
            'NEXT': self._cmd_next,
            'ON': self._cmd_on,
            'GOSUB': self._cmd_gosub,
            'RETURN': self._cmd_return,
            'DELAY': self._cmd_delay,
            'DATA': self._cmd_data,
            'READ': self._cmd_read,
            'RESTORE': self._cmd_restore,
            'STOP': self._cmd_stop,
            'END': self._cmd_end,
        }

    def execute_command(self, command, cmd_word=None):
        """Dispatch a single BASIC statement to its handler.

        Args:
            command:  The full statement text (e.g. "PRINT A+B").
            cmd_word: Pre-extracted first keyword (optimization: avoids
                      re-splitting in the hot path).  None when called
                      from IF/THEN/ELSE or immediate mode.
        Returns:
            None to advance to the next line, or a line number (int/float)
            to branch (GOTO, GOSUB, FOR/NEXT loop-back).
        """
        original_command = command

        if self.debug_mode:
            self._last_debug_command = original_command

        try:
            # Handle tape I/O commands specially (before dispatch table)
            if command.startswith('INPUT#-1'):
                return self._cmd_input_tape(command)
            if command.startswith('PRINT#-1'):
                return self._cmd_print_tape(command)

            # Extract cmd_word if not pre-parsed
            if cmd_word is None:
                cmd_word = command.split('(')[0].split()[0] if command else ''
                if cmd_word.startswith('PRINT'):
                    cmd_word = 'PRINT'

            # Check for implicit LET: cmd_word not in dispatch table and has '='
            handler = self._command_handlers.get(cmd_word)
            if handler is None and '=' in command:
                command = 'LET ' + command
                cmd_word = 'LET'
                handler = self._command_handlers.get(cmd_word)
                if self.debug_mode:
                    self.debug_print(f"AUTO LET -> {command}")

            if handler:
                return handler(command)
            else:
                self.debug_print(f"Unknown command: {command}", 'warning')

        except Exception as e:
            self.debug_print(f"Error executing command: {original_command}", 'error')
            if self._last_eval_original:
                self.debug_print(f"Expression: {self._last_eval_original}", 'error')
            if self._last_eval_substituted and self._last_eval_substituted != self._last_eval_original:
                self.debug_print(f"Expanded: {self._last_eval_substituted}", 'error')
            self.debug_print(f"Error details: {str(e)}", 'error')
            self.program_running = False
            self.stop_button.config(state=tk.DISABLED)

        return None

    def _format_number(self, value):
        """Format a number for PRINT per TRS-80 conventions:
        - Leading space for positive, minus sign for negative
        - No trailing .0 for integers
        - Trailing space after the number
        Strings pass through unchanged.
        """
        if isinstance(value, (int, float)):
            if isinstance(value, float) and value == int(value) and not (value != value):  # not NaN
                s = str(int(value))
            else:
                s = str(value)
            if value >= 0:
                return ' ' + s + ' '
            else:
                return s + ' '
        return str(value)

    def _cmd_print(self, command):
        is_print_at = command.startswith('PRINT@')
        original_row, original_col = self.cursor_row, self.cursor_col

        if is_print_at:
            match = self._regex_cache['print_at'].match(command)
            if match:
                position_expr, content = match.groups()
                position = int(self.evaluate_expression(position_expr))
                position -= 1
                self.cursor_row = position // 64
                self.cursor_col = position % 64
                if self.debug_mode:
                    self.debug_print(f"PRINT@ {position + 1} -> row {self.cursor_row}, col {self.cursor_col}")
        else:
            content = command[5:].strip()

        output = ""
        cursor_pos = self.cursor_col

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
                    formatted = self._format_number(evaluated_part)
                    output += formatted
                    cursor_pos += len(formatted)

            if end != -1:
                if content[end] == ',':
                    spaces_to_add = (16 - cursor_pos % 16) % 16
                    output += ' ' * spaces_to_add
                    cursor_pos += spaces_to_add

        if is_print_at and output:
            # Batch clear with a single rectangle instead of per-character
            clear_len = min(len(output), 64 - self.cursor_col)
            if clear_len > 0:
                x_start = self.cursor_col * self._char_w
                y_start = self.cursor_row * self._char_h
                self.screen.create_rectangle(
                    x_start, y_start,
                    x_start + clear_len * self._char_w,
                    y_start + self._char_h,
                    fill="black", outline="black"
                )
                for i in range(clear_len):
                    self.screen_content[self.cursor_row][self.cursor_col + i] = ' '

        if content.rstrip().endswith((';', ',')):
            self.print_to_screen(output, end='')
        else:
            self.print_to_screen(output, end='\n')

        if is_print_at:
            self.cursor_row, self.cursor_col = original_row, original_col

    def _cmd_let(self, command):
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
                        if self.debug_mode:
                            self.debug_print(f"Array assignment: {array_name}[{index}] = {self.array_variables[array_name][index]}")
                    else:
                        self._error_bs(array_name, index)
                else:
                    self._error_sn(f"Array {array_name} not defined")
            else:
                if var_name.endswith('$'):
                    self.scalar_variables[var_name] = str(self.evaluate_expression(value))
                else:
                    self.scalar_variables[var_name] = self.evaluate_expression(value)
                if self.debug_mode:
                    self.debug_print(f"Variable assignment: {var_name} = {self.scalar_variables[var_name]}")

    def _cmd_rem(self, command):
        pass

    def _cmd_poke(self, command):
        self.debug_print(f"Executing POKE command: {command}")
        match = self._regex_cache['poke'].match(command)
        if match:
            address_expr, value_expr = match.groups()
            address = int(self.evaluate_expression(address_expr))
            value = int(self.evaluate_expression(value_expr))
            self.poke(address, value)

    def _cmd_set_reset(self, command):
        try:
            if '(' in command and ')' in command:
                cmd_type = 'SET' if command.startswith('SET') else 'RESET'
                paren_start = command.index('(')
                paren_end = command.index(')')
                coords = command[paren_start+1:paren_end]
                if ',' in coords:
                    x_str, y_str = coords.split(',', 1)
                    x = int(self.evaluate_expression(x_str.strip())) - 1
                    y = int(self.evaluate_expression(y_str.strip())) - 1
                    if cmd_type == 'SET':
                        self.set_pixel(x, y)
                    else:
                        self.reset_pixel(x, y)
                else:
                    raise ValueError("Invalid coordinate format")
            else:
                raise ValueError("Missing parentheses")
        except (ValueError, IndexError):
            match = self._regex_cache['set_reset'].match(command)
            if match:
                cmd_type, x_expr, y_expr = match.groups()
                x = int(self.evaluate_expression(x_expr)) - 1
                y = int(self.evaluate_expression(y_expr)) - 1
                if cmd_type == 'SET':
                    self.set_pixel(x, y)
                else:
                    self.reset_pixel(x, y)
            else:
                if self.debug_mode:
                    self.debug_print(f"Invalid {command.split()[0]} command: {command}")

    def _cmd_cls(self, command):
        self.clear_screen()
        self.cursor_row = 0
        self.cursor_col = 0

    def _cmd_dim(self, command):
        match = self._regex_cache['dim'].match(command)
        if match:
            array_name, size_expr = match.groups()
            size = int(self.evaluate_expression(size_expr))
            if array_name.endswith('$'):
                self.array_variables[array_name] = [''] * (size + 1)
            else:
                self.array_variables[array_name] = [0] * (size + 1)
            # Optimization 6: Pre-compile array pattern for this array
            self._array_patterns[array_name] = re.compile(rf'\b{re.escape(array_name)}\(')
            self.debug_print(f"Array {array_name} dimensioned with size {size + 1}")
        else:
            self._error_sn(f"Invalid DIM command: {command}")

    def _cmd_input_tape(self, command):
        if not self.tape_file:
            self.select_tape_file()
        var_name = command.split(',')[1].strip()
        tape_data = self.read_from_tape()
        if tape_data is not None:
            self.scalar_variables[var_name] = tape_data
            self.debug_print(f"Read from tape: {var_name} = {tape_data}")
        else:
            self.debug_print("Error: No more data on tape")

    def _cmd_print_tape(self, command):
        if not self.tape_file:
            self.create_tape_file()
        _, data = command.split(',', 1)
        data = self.evaluate_expression(data.strip())
        self.write_to_tape(data)
        self.debug_print(f"Wrote to tape: {data}")

    def _cmd_input(self, command):
        match = self._regex_cache['input_prompt'].match(command)
        if match:
            prompt, var_name = match.groups()
            self.print_to_screen(prompt, end='')
            self.debug_print(f"INPUT {var_name} prompt={prompt!r}")
        else:
            var_name = command[5:].strip()
            self.print_to_screen("? ", end='')
            self.debug_print(f"INPUT {var_name}")
        self.waiting_for_input = True
        self.input_variable = var_name
        self.initial_start_pos = f"{self.cursor_row + 1}.{self.cursor_col}"
        self.screen.config(state=tk.NORMAL)
        self.screen.bind("<Key>", self.handle_input_key)
        self.screen.bind("<Return>", self.handle_input_return)
        self.screen.focus_set()

    def _cmd_goto(self, command):
        line_number = int(command[4:].strip())
        if self.debug_mode:
            self.debug_print(f"GOTO {line_number}")
        return line_number

    def _split_on_unquoted_colons(self, text):
        """Split text on colons that aren't inside quoted strings."""
        parts = []
        current = []
        in_quotes = False
        for ch in text:
            if ch == '"':
                in_quotes = not in_quotes
            if ch == ':' and not in_quotes:
                parts.append(''.join(current))
                current = []
            else:
                current.append(ch)
        parts.append(''.join(current))
        return parts

    def _cmd_if(self, command):
        match = self._regex_cache['if_then'].match(command)
        if match:
            condition, then_action, _, else_action = match.groups()
            condition_result = self.evaluate_expression(condition)
            if condition_result:
                if self.debug_mode:
                    self.debug_print(f"IF {condition} -> TRUE; THEN {then_action}")
                return self._execute_multi_statement(then_action)
            elif else_action:
                if self.debug_mode:
                    self.debug_print(f"IF {condition} -> FALSE; ELSE {else_action}")
                return self._execute_multi_statement(else_action)
            else:
                if self.debug_mode:
                    self.debug_print(f"IF {condition} -> FALSE")

    def _execute_multi_statement(self, statements):
        """Execute colon-separated statements from IF/THEN/ELSE clause."""
        parts = self._split_on_unquoted_colons(statements)
        result = None
        for part in parts:
            part = part.strip()
            if part:
                result = self.execute_command(part)
                if result is not None:
                    return result
        return result

    def _cmd_for(self, command):
        match = self._regex_cache['for_loop'].match(command)
        if match:
            var, start_expr, end_expr, _, step_expr = match.groups()
            start = self.evaluate_expression(start_expr)
            end = self.evaluate_expression(end_expr)
            step = self.evaluate_expression(step_expr) if step_expr else 1
            # Optimization 8: Store next_line_number at FOR time
            next_idx = self.current_line_index + 1
            next_ln = self._line_numbers[next_idx] if next_idx < len(self._line_numbers) else None
            self.for_loops[var] = {
                'start': start,
                'end': end,
                'step': step,
                'current': start,
                'line_index': self.current_line_index,
                'next_line_number': next_ln,
            }
            self.scalar_variables[var] = start
            if self.debug_mode:
                self.debug_print(f"FOR {var}={start} TO {end} STEP {step}")

    def _cmd_next(self, command):
        if self.for_loops:
            # Parse variable name from NEXT command
            next_var = command[4:].strip() if len(command) > 4 else ''
            if next_var:
                # Match specified variable
                if next_var in self.for_loops:
                    var = next_var
                else:
                    self._error_nf(next_var)
                    return
            else:
                # Use innermost loop (avoid building a full list)
                var = next(reversed(self.for_loops))
            loop = self.for_loops[var]
            loop['current'] += loop['step']
            self.scalar_variables[var] = loop['current']
            if (loop['step'] > 0 and loop['current'] <= loop['end']) or (loop['step'] < 0 and loop['current'] >= loop['end']):
                if self.debug_mode:
                    self.debug_print(f"NEXT {var} -> {loop['current']} (repeat)")
                # Optimization 8: Use cached next_line_number from FOR time
                return loop['next_line_number']
            else:
                if self.debug_mode:
                    self.debug_print(f"NEXT {var} -> done")
                self.for_loops.pop(var)
        else:
            self._error_nf('')

    def _cmd_on(self, command):
        match = self._regex_cache['on_goto'].match(command)
        if match:
            expression, line_numbers = match.groups()
            value = int(self.evaluate_expression(expression))
            targets = [int(ln.strip()) for ln in line_numbers.split(',')]
            if 1 <= value <= len(targets):
                return targets[value - 1]

    def _cmd_gosub(self, command):
        line_number = int(command[5:].strip())
        # Store return line index directly
        self.gosub_stack.append(self.current_line_index + 1)
        if self.debug_mode:
            self.debug_print(f"GOSUB {line_number} (depth {len(self.gosub_stack)})")
        return line_number

    def _cmd_return(self, command):
        if self.gosub_stack:
            return_index = self.gosub_stack.pop()
            # Optimization 2: Use pre-parsed _line_numbers
            if return_index < len(self._line_numbers):
                if self.debug_mode:
                    self.debug_print(f"RETURN (depth {len(self.gosub_stack)})")
                return self._line_numbers[return_index]
            return None
        else:
            self._error_rg()

    def _cmd_delay(self, command):
        delay_time = int(command.split()[1])
        self.master.after(delay_time * 10)

    def _cmd_data(self, command):
        # DATA is pre-scanned; skip during execution
        pass

    def _cmd_read(self, command):
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
                            self._error_bs(array_name, index)
                    else:
                        self._error_sn(f"Array {array_name} not defined")
                else:
                    if var.endswith('$'):
                        self.scalar_variables[var] = value.strip("'\"")
                    else:
                        self.scalar_variables[var] = self.evaluate_expression(value)
                self.data_pointer += 1
                self.debug_print(f"READ: {var} = {value}")
            else:
                self._error_od()

    def _cmd_restore(self, command):
        self.data_pointer = 0
        self.debug_print("RESTORE: Data pointer reset to 0")

    def _cmd_stop(self, command):
        line_number = self._get_current_line_number()
        self.print_to_screen(f"BREAK IN {line_number}")
        self.program_paused = True
        self.stop_button.config(text="CONT", state=tk.NORMAL)
        self.enable_immediate_mode()

    def _cmd_end(self, command):
        self.program_running = False
        self.stop_button.config(state=tk.DISABLED)
        self._flush_graphics()
    
    # ============================================================
    #  SECTION: Expression Evaluator
    #  This is the heart of the interpreter.  evaluate_expression is
    #  called from almost every command handler.  It has fast paths
    #  for pure integers and simple variable lookups, then falls
    #  through to _eval_nested which:
    #    1. Builds a quote-map (bytearray) to protect string literals
    #    2. Single-pass regex replaces BASIC keywords → Python ops
    #    3. Resolves built-in functions via _builtin_functions table
    #    4. Substitutes array references and scalar variables
    #    5. Wraps comparisons for TRS-80 TRUE=-1 / FALSE=0 semantics
    #    6. Calls Python eval() in a restricted namespace
    # ============================================================
    _PROTECTED_FUNCTIONS = frozenset([
        'SIN', 'COS', 'TAN', 'EXP', 'LOG', 'SQR', 'ABS', 'INT', 'RND',
        'CHR$', 'STR$', 'LEFT$', 'RIGHT$', 'MID$', 'INSTR', 'LEN',
        'ASC', 'VAL', 'PEEK', 'POINT', 'FIX', 'SGN', 'STRING$'
    ])

    def _build_quote_map(self, s):
        """Return a bytearray: nonzero if position i is inside quotes.
        Tracks both double and single quotes (single only outside double,
        double only outside single) so that internally-generated single-
        quoted strings (INKEY$, variable substitution) are also protected."""
        n = len(s)
        in_quotes = bytearray(n)
        in_double = 0
        in_single = 0
        for i in range(n):
            ch = s[i]
            if ch == '"' and not in_single:
                in_double ^= 1
            elif ch == "'" and not in_double:
                in_single ^= 1
            in_quotes[i] = in_double | in_single
        return in_quotes

    # Mapping from matched keyword text to Python equivalent
    _KEYWORD_REPLACEMENTS = {
        'MOD': '%',
        'OR': ' or ',
        'AND': ' and ',
        'NOT': ' not ',
        '<>': '!=',
        '=': '==',
        '^': ' ** ',
    }

    def _replace_keyword(self, match, quote_map):
        """Replace a keyword match only if not inside quotes."""
        if match.start() < len(quote_map) and quote_map[match.start()]:
            return match.group(0)
        text = match.group(0)
        if text == 'RND':
            return str(random.random())
        return self._KEYWORD_REPLACEMENTS.get(text, text)

    def evaluate_expression(self, expr):
        """Evaluate a BASIC expression and return its value.

        Fast paths return immediately for integers, negative integers,
        and bare variable names.  Everything else goes to _eval_nested
        for full regex-based transformation and Python eval().
        """
        self._last_eval_original = expr
        self._last_eval_substituted = expr
        self.replaced = False

        # Fast path for simple numeric values
        expr_stripped = expr.strip()
        if expr_stripped.isdigit():
            return int(expr_stripped)

        # Fast path for negative integers like "-5"
        if len(expr_stripped) > 1 and expr_stripped[0] == '-' and expr_stripped[1:].isdigit():
            return int(expr_stripped)

        # Fast path for simple variable references
        if expr_stripped in self.scalar_variables:
            return self.scalar_variables[expr_stripped]

        return self._eval_nested(expr)

    # ============================================================
    #  TRS-80 Comparison & Logic Wrapping (TRUE=-1, FALSE=0)
    #  TRS-80 BASIC comparisons return -1 for true and 0 for false.
    #  _wrap_trs80_logic rewrites "A > B" into "_gt(A,B)" which is
    #  a lambda in _eval_namespace that returns -1 or 0.
    #  NOT is rewritten to _bnot() (bitwise complement ~int(x)).
    # ============================================================
    def _wrap_trs80_logic(self, expr):
        """Transform comparisons and NOT for TRS-80 semantics (-1/0).
        Comparisons become function calls: A > B -> _gt(A,B)
        NOT becomes: not X -> _bnot(X)
        """
        # 1. Wrap comparison operators with function calls
        for op_str, func_name in [('>=', '_ge'), ('<=', '_le'), ('!=', '_ne'),
                                   ('==', '_eq'), ('>', '_gt'), ('<', '_lt')]:
            while True:
                pos = self._find_comp_op(expr, op_str)
                if pos == -1:
                    break
                left_start = self._scan_left_boundary(expr, pos)
                right_end = self._scan_right_boundary(expr, pos + len(op_str))
                left = expr[left_start:pos].strip()
                right = expr[pos + len(op_str):right_end].strip()
                expr = expr[:left_start] + f"{func_name}({left},{right})" + expr[right_end:]
        # 2. Replace 'not' with _bnot() for bitwise NOT
        expr = self._wrap_not_ops(expr)
        return expr

    def _find_comp_op(self, expr, op_str):
        """Find first comparison operator not inside quotes."""
        in_quote = False
        op_len = len(op_str)
        i = 0
        while i <= len(expr) - op_len:
            if expr[i] == '"':
                in_quote = not in_quote
            elif not in_quote and expr[i:i + op_len] == op_str:
                # Don't match > if part of >=
                if op_str == '>' and i + 1 < len(expr) and expr[i + 1] == '=':
                    i += 2
                    continue
                # Don't match < if part of <=
                if op_str == '<' and i + 1 < len(expr) and expr[i + 1] == '=':
                    i += 2
                    continue
                return i
            i += 1
        return -1

    def _scan_left_boundary(self, expr, op_pos):
        """Find start of left operand by scanning backwards from operator."""
        depth = 0
        i = op_pos - 1
        while i >= 0 and expr[i] == ' ':
            i -= 1
        while i >= 0:
            ch = expr[i]
            if ch == ')':
                depth += 1
            elif ch == '(':
                if depth > 0:
                    depth -= 1
                else:
                    return i + 1  # stop at unmatched open paren
            elif ch == "'":
                i -= 1
                while i >= 0 and expr[i] != "'":
                    i -= 1
            elif depth == 0:
                # Stop at logical operator boundaries
                if i >= 3 and expr[i - 3:i + 1] == 'and ':
                    return i + 1
                if i >= 2 and expr[i - 2:i + 1] == 'or ':
                    return i + 1
                if i >= 3 and expr[i - 3:i + 1] == 'not ':
                    return i + 1
                if ch == ',':
                    return i + 1
            i -= 1
        return 0

    def _scan_right_boundary(self, expr, op_end):
        """Find end of right operand by scanning forwards from operator."""
        depth = 0
        i = op_end
        while i < len(expr) and expr[i] == ' ':
            i += 1
        while i < len(expr):
            ch = expr[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth > 0:
                    depth -= 1
                else:
                    return i  # stop at unmatched close paren
            elif ch == "'":
                i += 1
                while i < len(expr) and expr[i] != "'":
                    i += 1
            elif depth == 0:
                if expr[i:i + 5] == ' and ':
                    return i
                if expr[i:i + 4] == ' or ':
                    return i
                if ch == ',':
                    return i
            i += 1
        return len(expr)

    def _wrap_not_ops(self, expr):
        """Replace 'not X' with '_bnot(X)' for TRS-80 bitwise NOT."""
        while True:
            in_quote = False
            pos = -1
            for i in range(len(expr)):
                if expr[i] == '"':
                    in_quote = not in_quote
                elif not in_quote and expr[i:i + 4] == 'not ':
                    if i == 0 or not expr[i - 1].isalpha():
                        pos = i
                        break
            if pos == -1:
                break
            # Find operand start (skip 'not ' and spaces)
            op_start = pos + 4
            while op_start < len(expr) and expr[op_start] == ' ':
                op_start += 1
            # Find operand end
            depth = 0
            j = op_start
            if j < len(expr) and expr[j] == '(':
                depth = 1
                j += 1
                while j < len(expr) and depth > 0:
                    if expr[j] == '(':
                        depth += 1
                    elif expr[j] == ')':
                        depth -= 1
                    j += 1
            else:
                while j < len(expr):
                    ch = expr[j]
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        if depth > 0:
                            depth -= 1
                        else:
                            break
                    elif depth == 0:
                        if expr[j:j + 5] == ' and ':
                            break
                        if expr[j:j + 4] == ' or ':
                            break
                    j += 1
            operand = expr[op_start:j]
            expr = expr[:pos] + f"_bnot({operand})" + expr[j:]
        return expr

    def _eval_nested(self, expr):
        """Full expression evaluation pipeline.

        Transforms a BASIC expression string into a Python-evaluable string,
        then calls eval().  Stages are documented in the file header.
        """
        # --- Stage 1: Build quote-map (bytearray, 0/1 per char) ---
        # Used throughout to skip replacements inside string literals.
        quote_map = self._build_quote_map(expr)

        def is_in_quotes(pos):
            return pos < len(quote_map) and quote_map[pos]

        # --- Stage 2: INKEY$ replacement (at most once) ---
        inkey_match = self._regex_cache['inkey'].search(expr)
        if inkey_match and not is_in_quotes(inkey_match.start()):
            inkey_result = self.inkey()
            expr = expr[:inkey_match.start()] + f"'{inkey_result}'" + expr[inkey_match.end():]
            self.replaced = True
            quote_map = self._build_quote_map(expr)

        # --- Stage 3: Single-pass keyword translation ---
        # One combined regex matches RND, MOD, OR, AND, NOT, =, <>, ^
        # and _replace_keyword maps each to its Python equivalent,
        # skipping matches inside quotes.
        prev = expr
        expr = self._regex_cache['all_keywords'].sub(
            lambda m: self._replace_keyword(m, quote_map), expr)
        if expr is not prev:
            quote_map = self._build_quote_map(expr)

        # --- Stage 4: Built-in function dispatch ---
        while True:
            func_match = self._regex_cache['func_match'].search(expr)
            if not func_match:
                break

            func_name, inner_expr = func_match.groups()

            if is_in_quotes(func_match.start()):
                break

            # Evaluate inner expression first
            inner_value = self._eval_nested(inner_expr)

            # Dispatch to function handler
            handler = self._builtin_functions.get(func_name)
            if handler:
                result = handler(inner_value, inner_expr)
            else:
                self.debug_print(f"Unknown function: {func_name}", 'error')
                break

            expr = expr.replace(func_match.group(), str(result), 1)
            quote_map = self._build_quote_map(expr)

        # --- Stage 5: Array reference substitution ---
        # Matches "A(" patterns, recursively evaluates the index expression,
        # and replaces with the array value.  Skipped entirely when there
        # are no parentheses or no arrays defined.
        if '(' in expr and self.array_variables:
            for array_name in self.array_variables:
                if isinstance(self.array_variables[array_name], list):
                    # Use cached compiled pattern per array name
                    if array_name not in self._array_patterns:
                        self._array_patterns[array_name] = re.compile(rf'\b{re.escape(array_name)}\(')
                    array_re = self._array_patterns[array_name]
                    start = 0
                    while True:
                        match = array_re.search(expr, start)
                        if not match:
                            break
                        start_index = match.end()
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
                            self._error_sn(f"Mismatched parentheses in array reference: {array_name}")
                            raise ValueError(f"Mismatched parentheses in array reference: {array_name}")

                        index_expr = expr[start_index:end_index]
                        index = int(self._eval_nested(index_expr))
                        if 0 <= index < len(self.array_variables[array_name]):
                            replacement = self.array_variables[array_name][index]
                            if array_name.endswith('$') or isinstance(replacement, str):
                                replacement = f"'{replacement}'"
                            expr = expr[:match.start()] + str(replacement) + expr[end_index + 1:]
                        else:
                            self._error_bs(array_name, index)
                            raise IndexError(f"Array index out of bounds: {array_name}[{index}]")
                        start = match.start() + len(str(replacement))

        # --- Stage 6: Scalar variable substitution ---
        # Split on quoted strings so replacements don't touch literals.
        # Variables are sorted longest-first to prevent "A" clobbering "AB".
        # Cached compiled regex per variable name avoids repeated re.compile.
        parts = self._regex_cache['string_split'].split(expr)

        # Skip entirely for pure-numeric expressions (no alpha chars)
        has_alpha = any(c.isalpha() for c in expr)
        if has_alpha and self.scalar_variables:
            # Optimization 5: Cache sorted_vars, only re-sort when variable count changes
            var_count = len(self.scalar_variables)
            if var_count != self._last_var_count:
                self._sorted_vars_cache = sorted(self.scalar_variables.keys(), key=len, reverse=True)
                self._last_var_count = var_count
            sorted_vars = self._sorted_vars_cache
            quote_map = self._build_quote_map(expr)

            for i in range(0, len(parts), 2):
                if not parts[i].strip():
                    continue

                # Optimization 4: Build part_quote_map once per part, outside variable loop
                part_quote_map = self._build_quote_map(parts[i])

                for var in sorted_vars:
                    value = self.scalar_variables[var]
                    new_parts = []
                    last_end = 0
                    # Use cached compiled regex per variable name
                    if var not in self._var_regex_cache:
                        if var.upper() in self._PROTECTED_FUNCTIONS:
                            pattern = rf'\b{re.escape(var)}\b(?!\()'
                        else:
                            pattern = re.escape(var) if var.endswith('$') else r'\b' + re.escape(var) + r'\b'
                        self._var_regex_cache[var] = re.compile(pattern)
                    var_re = self._var_regex_cache[var]

                    for match in var_re.finditer(parts[i]):
                        s, e = match.span()
                        if not (s < len(part_quote_map) and part_quote_map[s]):
                            new_parts.append(parts[i][last_end:s])
                            if var.endswith('$'):
                                replacement = f"'{str(value).rstrip()}'"
                                if i + 2 < len(parts) and parts[i+1] == '+':
                                    replacement = replacement[:-1]
                            else:
                                replacement = str(value)
                            new_parts.append(replacement)
                        else:
                            new_parts.append(parts[i][last_end:e])
                        last_end = e
                    new_parts.append(parts[i][last_end:])
                    new_part = ''.join(new_parts)
                    # Optimization 4: Only rebuild part_quote_map if part actually changed
                    if new_part is not parts[i]:
                        parts[i] = new_part
                        part_quote_map = self._build_quote_map(parts[i])

        expr = ''.join(parts)
        self._last_eval_substituted = expr

        # --- Stage 7: Comparison wrapping for TRS-80 semantics ---
        # Rewrites "A > B" → "_gt(A,B)" and "not X" → "_bnot(X)"
        # so eval() produces -1 (true) or 0 (false).
        expr = self._wrap_trs80_logic(expr)
        self._last_eval_substituted = expr

        # --- Stage 8: Python eval() in restricted namespace ---
        # _eval_globals has __builtins__=None for safety.
        # _eval_namespace provides int/float/str/chr/ord plus the
        # comparison wrappers (_gt, _lt, _ge, _le, _eq, _ne, _bnot).
        try:
            result = eval(expr, self._eval_globals, self._eval_namespace)
            return result
        except Exception as e:
            if self.debug_mode:
                self.debug_print(f"Evaluation failed: {e}", 'error')
            # Fall back: treat as a string literal (unquote)
            return expr.strip("'\"")

    # ============================================================
    #  SECTION: Built-in Functions (dispatch table)
    #  _builtin_functions maps function names to handler callables.
    #  Each handler receives (inner_value, inner_expr) where
    #  inner_value is the already-evaluated argument and inner_expr
    #  is the raw text (needed by multi-argument functions like
    #  LEFT$, MID$, INSTR which split on commas internally).
    # ============================================================
    def _init_builtin_functions(self):
        """Initialize the built-in function dispatch table"""
        self._builtin_functions = {
            'INT': lambda v, ie: int(float(v)),
            'SIN': lambda v, ie: math.sin(float(v)),
            'COS': lambda v, ie: math.cos(float(v)),
            'TAN': lambda v, ie: math.tan(float(v)),
            'SQR': lambda v, ie: math.sqrt(float(v)),
            'LOG': lambda v, ie: math.log(float(v)),
            'EXP': lambda v, ie: math.exp(float(v)),
            'SGN': lambda v, ie: -1 if float(v) < 0 else (1 if float(v) > 0 else 0),
            'ABS': lambda v, ie: abs(float(v)),
            'FIX': lambda v, ie: math.trunc(float(v)),
            'VAL': lambda v, ie: (lambda s: int(float(s)) if float(s) == int(float(s)) else float(s))(str(v).strip("'\"")),
            'RND': self._func_rnd,
            'ASC': lambda v, ie: ord(str(v).strip("'\"")),
            'PEEK': lambda v, ie: self.peek(int(v)),
            'POINT': self._func_point,
            'LEN': lambda v, ie: len(str(v)),
            'STR$': self._func_str,
            'CHR$': lambda v, ie: f"'{chr(int(float(v)))}'",
            'STRING$': self._func_string,
            'LEFT$': self._func_left,
            'RIGHT$': self._func_right,
            'MID$': self._func_mid,
            'INSTR': self._func_instr,
        }

    def _func_rnd(self, inner_value, inner_expr):
        """RND(n): TRS-80 returns 1 to n for positive n, random float for 0"""
        n = int(inner_value)
        if n == 0:
            return random.random()
        return random.randint(1, n)

    def _func_str(self, inner_value, inner_expr):
        """STR$(n): TRS-80 adds leading space for non-negative numbers"""
        num = float(inner_value)
        if num == int(num):
            s = str(int(num))
        else:
            s = str(num)
        if num >= 0:
            s = ' ' + s
        return f"'{s}'"

    def _func_point(self, inner_value, inner_expr):
        try:
            x, y = map(lambda v: int(self._eval_nested(v.strip())), inner_expr.split(','))
            return self.get_pixel(x - 1, y - 1)
        except ValueError as e:
            self.debug_print(f"Error in POINT function: {str(e)}", 'error')
            return 0

    def _func_string(self, inner_value, inner_expr):
        count, char = inner_expr.split(',')
        count = int(self._eval_nested(count.strip()))
        char = self._eval_nested(char.strip())
        if isinstance(char, str):
            char = char[0] if char else ''
        else:
            char = chr(int(char))
        return f"'{char * count}'"

    def _func_left(self, inner_value, inner_expr):
        string, length = map(self._eval_nested, inner_expr.split(','))
        return f"'{str(string)[:int(length)]}'"

    def _func_right(self, inner_value, inner_expr):
        string, length = map(self._eval_nested, inner_expr.split(','))
        return f"'{str(string)[-int(length):]}'"

    def _func_mid(self, inner_value, inner_expr):
        parts = inner_expr.split(',')
        string, start = map(self._eval_nested, parts[:2])
        start = int(start) - 1
        if len(parts) > 2:
            length = int(self._eval_nested(parts[2]))
            return f"'{str(string)[start:start+length]}'"
        else:
            return f"'{str(string)[start:]}'"

    def _func_instr(self, inner_value, inner_expr):
        parts = inner_expr.split(',')
        if len(parts) == 2:
            string, substring = map(self._eval_nested, parts)
            start = 1
        elif len(parts) == 3:
            start, string, substring = map(self._eval_nested, parts)
            start = int(start)
        else:
            raise ValueError("INSTR requires 2 or 3 arguments")
        result = string.find(substring, start - 1) + 1
        if result == 0:
            result = 0
        return result

    def find_line_index(self, line_number):
        # Optimization 2: Binary search using pre-parsed _line_numbers array
        line_nums = self._line_numbers
        left, right = 0, len(line_nums) - 1

        while left <= right:
            mid = (left + right) // 2
            current = line_nums[mid]

            if current == line_number:
                return mid
            elif current < line_number:
                left = mid + 1
            else:
                right = mid - 1

        return -1

    # ============================================================
    #  SECTION: Memory (POKE/PEEK)
    #  TRS-80 screen memory: addresses 15360-16383 map to the
    #  64x16 text grid.  PEEK(14400) returns the last key pressed
    #  (keyboard buffer) — the primary way games poll input.
    #  INKEY$ is the string-returning equivalent.
    # ============================================================
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
            x = col * self._char_w
            y = row * self._char_h
            self.screen.create_text(x, y, text=chr(value), font=self._screen_font, fill="lime", anchor="nw")
            
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
                    self.debug_print(f"KEY PEEK -> {self.last_key_pressed} ({key_value})")
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
            self.debug_print(f"INKEY$ -> '{key}'")
            # Clear the key after returning it
            self.last_key_pressed = None
            return key  
        return ""  # Return an empty string if no key was pressed

    # ============================================================
    #  SECTION: Graphics (SET/RESET/POINT)
    #  The 128x48 pixel grid is stored in self.pixel_matrix.
    #  SET/RESET queue operations in _pending_graphics (batched
    #  every 20 ops or at GUI-update boundaries).  _flush_graphics
    #  draws/erases pixel rectangles on the Canvas.  self._active_pixels
    #  tracks which (x,y) are lit for efficient redraw/scroll.
    # ============================================================
    def set_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 1
            self._pending_graphics.append(('set', x, y))
            self._active_pixels.add((x, y))
            
            # Process graphics in batches to improve speed
            if len(self._pending_graphics) >= 20:
                self._flush_graphics()

    def reset_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 0
            self._pending_graphics.append(('reset', x, y))
            self._active_pixels.discard((x, y))
            
            # Process graphics in batches to improve speed
            if len(self._pending_graphics) >= 20:
                self._flush_graphics()
    
    def _flush_graphics(self):
        """Process all pending graphics operations in one batch"""
        if not self._pending_graphics:
            return

        for operation, x, y in self._pending_graphics:
            tag = f"p{x}_{y}"
            self.screen.delete(tag)
            if operation == 'set':
                self.screen.create_rectangle(
                    x * self.pixel_size, y * self.pixel_size,
                    (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                    fill="lime", outline="lime", tags=tag
                )
            else:  # reset
                self.screen.create_rectangle(
                    x * self.pixel_size, y * self.pixel_size,
                    (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                    fill="black", outline="black", tags=tag
                )

        self._pending_graphics = []
        self.master.update_idletasks()

    def get_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            return self.pixel_matrix[y][x]
        return 0
    
    def flush_graphics(self):
        """Public method to force immediate graphics update"""
        self._flush_graphics()

    # ============================================================
    #  SECTION: File I/O (Tape/Save/Load)
    #  Tape I/O (PRINT#-1 / INPUT#-1) reads/writes .dat files
    #  one line at a time.  SAVE/LOAD use .bas text files.
    #  Programs are always sorted by line number on save/load.
    # ============================================================
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

    def save_program(self):
        filename = filedialog.asksaveasfilename(defaultextension=".bas")
        if filename:
            program_lines = self._sort_program_lines(self.input_area.get(1.0, tk.END).strip().split('\n'))
            program_text = '\n'.join(program_lines)
            self.input_area.delete(1.0, tk.END)
            self.input_area.insert(tk.END, program_text)
            self.stored_program = program_lines
            with open(filename, 'w') as f:
                f.write(program_text + '\n')

    def load_program(self):
        filename = filedialog.askopenfilename(filetypes=[("BASIC files", "*.bas"), ("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            with open(filename, 'r') as f:
                content = f.read()
                program_lines = self._sort_program_lines(content.strip().split('\n'))
                program_text = '\n'.join(program_lines)
                self.input_area.delete(1.0, tk.END)
                self.input_area.insert(tk.END, program_text)
                # Update stored_program from loaded content
                self.stored_program = program_lines
        # turn on the RUN button and Step button list
        self.run_button.config(state=tk.NORMAL)
        self.step_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.NORMAL)

    # ============================================================
    #  SECTION: Help Text & Scale Toggle
    #  Help content is shown in non-modal Toplevel windows.
    #  toggle_scale switches between 1x and 2x display size
    #  (disabled on Raspberry Pi).  resize_components updates
    #  cached pixel_size, _char_w, _char_h, _screen_font.
    # ============================================================
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
        self._char_w = self.pixel_size * 2
        self._char_h = self.pixel_size * 3
        self._screen_font = ("Courier", self.base_font_size * self.scale_factor)
        self.screen.config(width=INITIAL_WIDTH * self.scale_factor, height=INITIAL_HEIGHT * self.scale_factor)

        # Resize the font for input area
        self.input_area.config(font=("Courier", self.input_font_size* self.scale_factor))

        # Redraw the screen content
        self.redraw_screen()

    # ============================================================
    #  SECTION: Immediate Mode
    #  When no program is running, the green screen shows a ">"
    #  prompt.  Typed characters accumulate in command_buffer.
    #  On Enter, process_immediate_command either:
    #    - Stores a numbered line in stored_program
    #    - Dispatches a command (RUN, LIST, NEW, CLEAR, CLS, etc.)
    #    - Falls through to execute_command for direct execution
    # ============================================================
    def _ensure_immediate_prompt(self, show_ready_if_empty=False):
        """Keep exactly one immediate-mode prompt visible on the current line."""
        if show_ready_if_empty and self.cursor_row == 0 and self.cursor_col == 0:
            self.print_to_screen("READY", end='\n')

        line_str = ''.join(self.screen_content[self.cursor_row]).rstrip()
        if line_str.endswith('>'):
            return

        if self.cursor_col > 0:
            self.print_to_screen("")
        self.print_to_screen(">", end='')

    def enable_immediate_mode(self):
        """Enable immediate mode input on the main screen"""
        if not self.program_running and not self.waiting_for_input:
            self.immediate_mode = True
            self.screen.config(state=tk.NORMAL)
            self.screen.bind("<Key>", self.handle_immediate_mode_key)
            self.screen.bind("<Return>", self.handle_immediate_mode_return)
            self.screen.focus_set()
            self._ensure_immediate_prompt(show_ready_if_empty=True)

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
                    x = self.cursor_col * self._char_w
                    y = self.cursor_row * self._char_h
                    self.screen.create_rectangle(x, y, x + self._char_w, y + self._char_h, fill="black", outline="black")
                    self.screen_content[self.cursor_row][self.cursor_col] = ' '
                    self.update_cursor_display()
        elif event.char and event.char.isprintable():
            # Add character to buffer and display
            char = event.char.upper()
            self.command_buffer += char

            # Display character on screen
            x = self.cursor_col * self._char_w
            y = self.cursor_row * self._char_h
            self.screen.create_text(x, y, text=char, font=self._screen_font, fill="lime", anchor="nw")
            self.screen_content[self.cursor_row][self.cursor_col] = char
            self.cursor_col += 1
            
            # Handle line wrap
            if self.cursor_col >= 64:
                self.cursor_row += 1
                self.cursor_col = 0
                if self.cursor_row >= 16:
                    self._scroll_screen_up()

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
            self._scroll_screen_up()

        if command:
            self.process_immediate_command(command)
        
        # Show prompt for next command only if we're still in immediate mode
        # and not running a program (process_immediate_command might have started one)
        if self.immediate_mode and not self.program_running and not self.waiting_for_input:
            self._ensure_immediate_prompt()
        
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
            self.enable_immediate_mode()
            self.set_screen_focus()
        
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
            self.set_screen_focus()
            return  # Don't show another prompt
        
        elif cmd == "SAVE":
            self.disable_immediate_mode()
            self.save_program()
            self.enable_immediate_mode()
            self.set_screen_focus()
        
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
        self.stored_program = self._sort_program_lines(current_program)
        
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
        self.stored_program = self._sort_program_lines(current_program)
        
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
- RND(n): Random integer 1 to n
- RND(0): New random float

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

