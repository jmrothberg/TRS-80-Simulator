#JMR TRS-80 BASIC simulator
#Fully working AUG 19, 2024
#Added step, debug window and variables window
#AUG 21 added multiple commands per line and additonal functions
#AUG 23 added graphics commands
#AUG 27 corrected POINT function, explicit LET, GUI, corrected coordinates, variables robust 
#SEP 5 new eval function that handled nested parentheses better and faster can do B((i-1)*15)aaaaaa
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import re
import random
import os
import math
import time
from TRS80LLMSupport import TRS80LLMSupport
PIXEL_SIZE = 6
INITIAL_WIDTH = 768
INITIAL_HEIGHT = 288

class TRS80Simulator:
    def __init__(self, master):
        self.master = master
        master.title("TRS-80 Simulator")

        # Add scaling factor
        self.scale_factor = 1
        self.base_font_size = 14  # Base font size
        self.input_font_size = 14  # Font size for input area

        # Set up the main frame
        self.main_frame = tk.Frame(master, bg="lightgrey")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create a frame to hold the TRS-80 screen
        self.screen_frame = tk.Frame(self.main_frame, bg="gray", padx=20, pady=20)
        self.screen_frame.pack(pady=0)

        # Create the TRS-80 screen (128x48 pixels, but each pixel is 8 screen pixels)
        self.pixel_size = PIXEL_SIZE * self.scale_factor  # Each pixel is 8 screen pixels, scaled
        self.screen = tk.Canvas(self.screen_frame, width=INITIAL_WIDTH * self.scale_factor, height=INITIAL_HEIGHT * self.scale_factor, bg="black", highlightthickness=0)
        self.screen.pack()
        
        # Make the Canvas focusable and bind click event
        self.screen.config(takefocus=1)
        self.screen.bind("<Button-1>", lambda event: self.set_screen_focus())

        # Create the BASIC input area
        self.input_area = scrolledtext.ScrolledText(self.main_frame, width=72, height=16, bg="lightgray", fg="black", font=("Courier", self.input_font_size))
        self.input_area.pack(pady=10)
        
        # Add right-click menu for cut, copy, paste
        self.create_right_click_menu()

        # Create buttons
        button_frame = tk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, padx=0, pady=0)

        self.run_button = tk.Button(button_frame, text="Run", command=self.run_program)
        self.run_button.pack(side=tk.LEFT, padx=5)

        # In the __init__ method, add this button:
        self.reset_button = tk.Button(button_frame, text="Reset", command=self.reset_program)
        self.reset_button.pack(side=tk.LEFT, padx=5)

        # Add Stop button
        self.stop_button = tk.Button(button_frame, text="Stop", command=self.stop_program, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # Add Step button
        self.step_button = tk.Button(button_frame, text="Step", command=self.step_program, state=tk.DISABLED)
        self.step_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.new_button = tk.Button(button_frame, text="List", command=self.list_program)
        self.new_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(button_frame, text="Clear", command=self.clear_screen)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(button_frame, text="Save", command=self.save_program)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.load_button = tk.Button(button_frame, text="Load", command=self.load_program)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # Add Copy Screen button
        self.copy_screen_button = tk.Button(button_frame, text="Copy Screen", command=self.copy_screen)
        self.copy_screen_button.pack(side=tk.LEFT, padx=5)


        self.debug_button = tk.Button(button_frame, text="Debug: ON", command=self.toggle_debug)
        self.debug_button.pack(side=tk.LEFT, padx=5)

        self.help_index = 0 

        self.help_button = tk.Button(button_frame, text="Help", command=self.show_help)
        self.help_button.pack(side=tk.RIGHT, padx=5)
        
        # Add 2X button
        self.scale_button = tk.Button(button_frame, text="2X", command=self.toggle_scale)
        self.scale_button.pack(side=tk.LEFT, padx=5)

        # Bind key press event to the main window
        self.master.bind('<Key>', self.on_key_press) # DO NOT REMOVE if removed the peek will not work
        self.input_area.bind("<Button-3>", self.on_input_area_click)
        self.screen.bind("<Button-3>", self.on_screen_click)

        # Bind for different systems and mouse buttons
        for button in ("<Button-2>", "<Button-3>"):
            self.screen.bind(button, self.show_right_click_menu)
            self.input_area.bind(button, self.show_right_click_menu)

        # Initialize variables
        self.sorted_program = []
        self.input_area.bind('<KeyRelease>', self.capitalize_input)
        self.stepping = False
        self.variables_window_open = False
        self.remaining_commands = []   
        self.debug_window = None
        self.debug_text = None 
        self.debug_mode = False
        self.original_program = []
        self.tape_file = None  # We'll set this when first tape operation is used
        self.tape_pointer = 0
        self.scalar_variables = {}
        self.array_variables = {}
        self.new_program()
        self.create_debug_window()
        self.last_key_time = 0
        self.key_check_interval = .05  # 100 milliseconds
        self.replaced = False
        
        # Initialize LLM support without creating the window
        self.llm_support = None
        self.llm_support_active = False

        # Add button to open LLM support window
        self.llm_button = tk.Button(button_frame, text="Assistant: ON", command=self.toggle_llm_support)
        self.llm_button.pack(side=tk.LEFT, padx=5)

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
        else:
            self.llm_support.llm_window.deiconify()
        self.llm_support.llm_window.lift()

    def on_llm_window_close(self):
        self.llm_support_active = False
        self.llm_button.config(text="Assistant: ON")
        self.llm_support.llm_window.withdraw()

    def open_llm_support(self):
        if self.llm_support is None or not self.llm_support.llm_window.winfo_exists():
            self.llm_support = TRS80LLMSupport(self.master, self)
        else:
            self.llm_support.llm_window.deiconify()
        self.llm_support.llm_window.lift()

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
    
    def create_debug_window(self):
        if self.debug_window is None or not self.debug_window.winfo_exists():
            self.debug_window = tk.Toplevel(self.master)
            self.debug_window.title("Debug Output")
            self.debug_window.geometry("800x600")

            # Create a frame for buttons
            button_frame = tk.Frame(self.debug_window)
            button_frame.pack(side=tk.TOP, fill=tk.X)

            # Create a frame for the find functionality
            find_frame = tk.Frame(self.debug_window)
            find_frame.pack(side=tk.TOP, fill=tk.X)

            # Add Find entry field
            self.find_entry = tk.Entry(find_frame, width=30)
            self.find_entry.pack(side=tk.LEFT, padx=5, pady=5)

            # Add Find button
            self.find_button = tk.Button(find_frame, text="Find", command=self.find_in_debug)
            self.find_button.pack(side=tk.LEFT, padx=5, pady=5)

            # Add Clear button
            self.clear_button = tk.Button(button_frame, text="Clear", command=lambda: self.debug_text.delete(1.0, tk.END))
            self.clear_button.pack(side=tk.LEFT, padx=5, pady=5)

            # Add List button
            self.list_button = tk.Button(button_frame, text="List", command=self.list_preprocessed_program)
            self.list_button.pack(side=tk.LEFT, padx=5, pady=5)

            # Add Variables button
            self.variables_button = tk.Button(button_frame, text="Variables: ON", command=self.toggle_variables_window)
            self.variables_button.pack(side=tk.LEFT, padx=5, pady=5)

            # Add button to debug window for sending debug output to LLM
            self.send_debug_button = tk.Button(button_frame, text="Send Debug to Companion", command=self.send_debug_to_llm)
            self.send_debug_button.pack(side=tk.LEFT, padx=5, pady=5)

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
            self.variables_window.geometry("400x300")

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
            if level == 'error':
                self.debug_text.insert(tk.END, f"ERROR: {message}\n", 'error')
            elif level == 'warning':
                self.debug_text.insert(tk.END, f"WARNING: {message}\n", 'warning')
            else:
                self.debug_text.insert(tk.END, f"{message}\n")
            self.debug_text.see(tk.END)

    def set_screen_focus(self):
        self.screen.config(state=tk.NORMAL)
        self.screen.focus_set()
        self.screen.config(state=tk.DISABLED)
    
    def on_key_press(self, event):
        if self.program_running and event.widget == self.screen:
            self.last_key_pressed = event.char.upper()
    
    def on_input_area_click(self, event):
        self.input_area.focus_set()

    def on_screen_click(self, event):
        self.set_screen_focus()

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
        screen_text = '\n'.join(''.join(row) for row in self.screen_content)
        self.master.clipboard_clear()
        self.master.clipboard_append(screen_text.rstrip())
        self.debug_print("Screen content copied to clipboard")

    #I/O methods
    def clear_input_area(self):
        self.input_area.delete(1.0, tk.END)

    def clear_screen(self):
        self.screen.delete("all")
        self.screen_content = [[' ' for _ in range(64)] for _ in range(16)]
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self.cursor_row = 0
        self.cursor_col = 0
    

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
        for char in text:
            if char == '\n' or self.cursor_col >= 64:
                self.cursor_row += 1
                self.cursor_col = 0
                if self.cursor_row >= 16:
                    # Scroll the screen content up
                    self.screen_content = self.screen_content[1:] + [[' ' for _ in range(64)]]
                    self.cursor_row = 15
                    self.redraw_screen()
            else:
                self.screen_content[self.cursor_row][self.cursor_col] = char
                x = self.cursor_col * self.pixel_size * 2
                y = self.cursor_row * self.pixel_size * 3
                self.screen.create_text(x, y, text=char, font=("Courier", self.base_font_size * self.scale_factor), fill="lime", anchor="nw")
                self.cursor_col += 1
        self.master.update()


    def redraw_screen(self):
        self.screen.delete("all")
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
                        self.redraw_screen()
                
                if not hasattr(self, 'input_start_pos'):
                    self.input_start_pos = f"{self.cursor_row}.{self.cursor_col - 1}"
                
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
                
                # Update the GUI
                self.master.update_idletasks()


    def handle_input_return(self, event):
        if self.waiting_for_input and event.widget == self.screen:
            # Construct the user input from screen_content
            user_input = ''
            start_row, start_col = map(int, self.input_start_pos.split('.'))
            for row in range(start_row, self.cursor_row + 1):
                if row == start_row:
                    user_input += ''.join(self.screen_content[row][start_col:])
                elif row == self.cursor_row:
                    user_input += ''.join(self.screen_content[row][:self.cursor_col])
                else:
                    user_input += ''.join(self.screen_content[row])

            self.debug_print(f"User input received: {user_input}")  # Debug print
            
            array_match = re.match(r'(\w+\$?)\((.+)\)', self.input_variable)
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
            
            self.waiting_for_input = False
            self.input_variable = None
            delattr(self, 'input_start_pos')  # Remove the input start position attribute
            self.screen.unbind("<Key>")
            self.screen.unbind("<Return>")
            self.current_line_index += 1
            self.debug_print(f"Resuming execution from line index: {self.current_line_index}")  # Debug print
            self.master.after(1, self.execute_next_line)  # Schedule next execution
            return "break"

    def stop_program(self):
        if self.program_running:
            if self.program_paused:
                self.program_paused = False
                self.stop_button.config(text="STOP")
                self.step_button.config(state=tk.DISABLED)
                if self.variables_window_open:
                    self.update_variables_window()
                self.execute_next_line()
            else:
                self.program_paused = True
                self.stop_button.config(text="CONT")
                self.step_button.config(state=tk.NORMAL)
                if self.variables_window_open:
                    self.update_variables_window()
        else:
            self.stop_button.config(text="STOP", state=tk.DISABLED)
            self.step_button.config(state=tk.DISABLED)
            self.program_paused = False
            if self.variables_window_open:
                self.update_variables_window()

    def list_program(self):
        if self.original_program:
            program_text = '\n'.join(self.original_program)
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

        program = self.input_area.get(1.0, tk.END).strip().split('\n')
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
        while self.program_running and not self.program_paused:
            self.master.update # added so i can get control back to the gui
            if self.current_line_index >= len(self.sorted_program):
                self.program_running = False
                self.stop_button.config(state=tk.DISABLED)
                self.step_button.config(state=tk.NORMAL)
                self.debug_print("Program execution completed")
                return

            line = self.sorted_program[self.current_line_index].strip()
            line_number, line = line.split(maxsplit=1)

            # Convert line number to float to handle decimal line numbers
            line_number = float(line_number)
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
                    return  # Exit the method and wait for input
                else:
                    self.current_line_index += 1 
            self.master.update_idletasks()  # Allow GUI to update
            if self.variables_window_open:
                self.update_variables_window()
            if self.stepping:
                self.debug_print("Stepping through the program")
                return

    def update_variables_window(self):
        if self.variables_window_open:
            self.show_variables()

    def send_debug_to_llm(self):
        try:
            debug_text = self.debug_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            debug_text = self.debug_text.get("1.0", tk.END)
        self.llm_support.append_debug_output(debug_text)

    
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
        self.debug_print(f"Original command: {original_command}")
        
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
                    match = re.match(r'PRINT@\s*([^,;]+)\s*,?\s*(.*)', command)
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
                            match = re.search(r'TAB\((\d+)\)', part)
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
                    array_match = re.match(r'(\w+\$?)\((.+)\)', var_name)
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
                match = re.match(r'POKE\s+(.+?)\s*,\s*(.+)', command)
                if match:
                    address_expr, value_expr = match.groups()
                    address = int(self.evaluate_expression(address_expr))
                    value = int(self.evaluate_expression(value_expr))
                    self.poke(address, value)
              

            elif command.startswith('RESET'):
                # Handle RESET command
                match = re.search(r'RESET\s*\(\s*((?:[^(),]+|\([^()]*\))*)\s*,\s*((?:[^(),]+|\([^()]*\))*)\s*\)', command)
                if match:
                    x_expr, y_expr = match.groups()
                    x = int(self.evaluate_expression(x_expr)) - 1  # Adjust for 1-based indexing
                    y = int(self.evaluate_expression(y_expr)) - 1  # Adjust for 1-based indexing
                    self.reset_pixel(x, y)
                else:
                    self.debug_print(f"Invalid RESET command: {command}")

            elif command.startswith('SET'):
                # Handle SET command
                match = re.search(r'SET\s*\(\s*((?:[^(),]+|\([^()]*\))*)\s*,\s*((?:[^(),]+|\([^()]*\))*)\s*\)', command)
                if match:
                    x_expr, y_expr = match.groups()
                    x = int(self.evaluate_expression(x_expr)) - 1  # Adjust for 1-based indexing
                    y = int(self.evaluate_expression(y_expr)) - 1  # Adjust for 1-based indexing
                    self.set_pixel(x, y)
                else:
                    self.debug_print(f"Invalid SET command: {command}")

            elif command == 'CLS':
                # Clear the screen
                self.clear_screen()
                self.cursor_row = 0
                self.cursor_col = 0

            elif command.startswith('DIM'):
                # Match both numeric and string array declarations
                match = re.match(r'DIM\s+(\w+\$?)\((.+)\)', command)
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
                match = re.match(r'INPUT\s*"(.*)"\s*;\s*(\w+\$?(?:\(.*?\))?)', command)
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
                match = re.match(r'IF\s+(.*?)\s+THEN\s+(.*?)(\s+ELSE\s+(.*))?$', command)
                if match:
                    condition, then_action, _, else_action = match.groups()
                    condition_result = self.evaluate_expression(condition)
                    if condition_result:
                        return self.execute_command(then_action)
                    elif else_action:
                        return self.execute_command(else_action)

            elif command.startswith('FOR'):
                match = re.match(r'FOR\s+(\w+)\s*=\s*(.+?)\s+TO\s+(.+?)(\s+STEP\s+(.+))?$', command)
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
                match = re.match(r'ON\s+(.*?)\s+GOTO\s+(.*)', command)
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
                        
                        array_match = re.match(r'(\w+\$?)\((.+)\)', var)
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
                self.program_paused = True
                self.stop_button.config(text="CONT", state=tk.NORMAL)
                #self.current_line_index += 1 # Move to the next line so when you continue it will start from the next line

            elif command == 'END':
                self.program_running = False
                self.stop_button.config(state=tk.DISABLED)
                
            else:
                self.debug_print(f"Unknown command: {command}", 'warning')

        except Exception as e:
            self.debug_print(f"Error executing command: {original_command}", 'error')
            self.debug_print(f"Error details: {str(e)}", 'error')
            self.program_running = False
            self.stop_button.config(state=tk.DISABLED)
        
        return None
    
    def evaluate_expression(self, expr):
        self.debug_print(f"Evaluating expression: {expr}")
        self.replaced = False
        protected_functions = [
    'SIN', 'COS', 'TAN', 'EXP', 'LOG', 'SQR', 'ABS', 'INT', 'RND',
    'CHR$', 'STR$', 'LEFT$', 'RIGHT$', 'MID$', 'INSTR', 'LEN',
    'ASC', 'VAL', 'PEEK', 'POINT', 'FIX', 'SGN', 'STRING$'
]
        def eval_nested(expr):
            # Helper function to check if a position is within quotes
            def is_within_quotes(s, pos):
                double_quote_count = len(re.findall(r'(?<!\\)"', s[:pos]))
                single_quote_count = len(re.findall(r"(?<!\\)'", s[:pos]))
                return (double_quote_count % 2 == 1) or (single_quote_count % 2 == 1)
            
            # Replacement functions
            def replace_rnd(match):
                return str(random.random()) if not is_within_quotes(expr, match.start()) else match.group(0)

            def replace_inkey(match):
                result = self.inkey()
                if not is_within_quotes(expr, match.start()):
                    self.replaced = True
                    return f"'{result}'"  # Always wrap in quotes
                else:
                    return match.group(0)
            
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
            expr = re.sub(r'\bINKEY\$', replace_inkey, expr)
            if self.replaced:
                self.last_key_pressed = ""

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
                self.master.update_idletasks()
                
                func_match = re.search(r'(INT|SIN|COS|TAN|SQR|LOG|EXP|SGN|FIX|CHR\$|STRING\$|VAL|RND|ASC|PEEK|POINT|STR\$|LEN|LEFT\$|RIGHT\$|MID\$|ABS|INSTR)\(((?:[^()]+|\([^()]*\))*)\)', expr) 
                
                if not func_match:
                    break

                func_name, inner_expr = func_match.groups()
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
            parts = re.split(r'("(?:[^"\\]|\\.)*")', expr)

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
            self.debug_print(f"Expression after variable substitution: {expr}")
           
            try:
                # Evaluate the entire expression at once
                result = eval(expr, {"__builtins__": None}, {
                    "int": int, "float": float, "str": str, 
                    "chr": chr, "ord": ord,
                    "self": self
                })
                self.debug_print(f"Evaluation result: {result}")
                return result
            except Exception as e:
                self.debug_print(f"Evaluation failed: {e}")
                # If eval fails, return the original expression (for string literals)
                return expr.strip("'\"")
        
        return eval_nested(expr)

    def find_line_index(self, line_number):
        for i, line in enumerate(self.sorted_program):
            current_line_number = float(line.split()[0])
            if current_line_number == line_number:
                return i
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
            
            # Update the screen
            self.update_screen()
            
            self.debug_print(f"POKE: Address={address}, Value={value}, Row={row}, Col={col}")
        else:
            self.debug_print(f"POKE: Address={address}, Value={value}")
            self.debug_print(f"Warning: Address out of range for screen memory")

        
    def peek(self, address):
        if address == 14400:
            current_time = time.time()
            if current_time - self.last_key_time >= self.key_check_interval:
                self.master.update()  # if just idle it will get stuck in loop 
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
        self.master.update()
        
        key = self.last_key_pressed
        #self.last_key_pressed = None  # Clear the last key pressed STOPS WORKING IF YOU CLEAR THE KEY!
        if key:         
            self.debug_print(f"INKEY$ returning: '{key}'")
            return key  
        self.debug_print("INKEY$ returning empty string")
        return ""  # Return an empty string if no key was pressed'''

    #GRAPHICS METHODS
    def set_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 1
            self.screen.create_rectangle(
                x * self.pixel_size, y * self.pixel_size,
                (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                fill="lime", outline="lime"
            )

    def reset_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            self.pixel_matrix[y][x] = 0
            self.screen.create_rectangle(
                x * self.pixel_size, y * self.pixel_size,
                (x + 1) * self.pixel_size, (y + 1) * self.pixel_size,
                fill="black", outline="black"
            )

    def get_pixel(self, x, y):
        if 0 <= x < 128 and 0 <= y < 48:
            return self.pixel_matrix[y][x]
        return 0

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
                self.input_area.delete(1.0, tk.END)
                self.input_area.insert(tk.END, f.read())
        # turn on the RUN button and Step button list
        self.run_button.config(state=tk.NORMAL)
        self.step_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.NORMAL)

    def show_help(self):
        if not hasattr(self, 'help_index'):
            self.help_index = 0

        help_texts = [
            ("Help", help_text1),
            ("Help 2", help_text2),
            ("Help 3", help_text3),
            ("Help 4", help_text4)
        ]

        title, content = help_texts[self.help_index]
        messagebox.showinfo(title, content)

        self.help_index = (self.help_index + 1) % len(help_texts)
        self.help_button.config(text=help_texts[self.help_index][0])

    def toggle_scale(self):
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

help_text1 = """
TRS-80 BASIC Simulator Help

Supported Commands:
- PRINT "text" or PRINT expression [, expression...]
- PRINT "text", expression
- PRINT@ expression [,expression] # might want to not need a comma but it is needed for the parser
- POKE address, value
- PEEK(address)
- CLS (Clear Screen)
- LET variable = expression
- LET string$ = "text" or LET string$ = expression
- INPUT variable
- INPUT "prompt"; variable
- GOTO line_number
- ON expression GOTO line1, line2, ...
- IF condition THEN action
- IF condition THEN action ELSE action
- FOR variable = start TO end [STEP step]
- NEXT
- REM comment
- GOSUB line_number
- RETURN
- DIM variable(size)
- DATA value1, value2, ...
- READ variable1, variable2, ...
- RESTORE
- PRINT#-1,<expression> to write data to tape.
- INPUT#-1,<variable> to read data from tape."""

help_text2 = """

- ABS(x): Returns the absolute value of x
- LEN(string$): Returns the length of the string
- FIX(x): Returns the integer part of x
- SGN(x): Returns the sign of x (1 if x > 0, 0 if x = 0, -1 if x < 0)
- MOD(x, y): Returns the remainder of x divided by y

- STR$(x): Converts x to a string
- LEFT$(string$, n): Returns the leftmost n characters of the string
- RIGHT$(string$, n): Returns the rightmost n characters of the string
- MID$(string$, start[, length]): Returns a substring from the string 
- ASC(string$): Returns the ASCII code of the first character in the string

- SET(x, y): Sets a pixel at the specified coordinates
- RESET(x, y): Resets a pixel at the specified coordinates
- POINT(x, y): Returns the state of the pixel at the specified coordinates

- RND or RND(X) where X is an integer returns a random integer between 0 and X-1
- SIN, COS, TAN, SQR, LOG, EXP: Functions that return a floating point number
- END (Stop program)

String Operations:
- Use $ at the end of variable names  (e.g., A$)
- Concatenate strings using + (e.g., A$ + B$)

Logic and Comparison:
- Use IF-THEN for conditional statements
- Use relational operators: =, <>, <, >, <=, >=
- Use logical operators: AND, OR

Use line numbers  (e.g., 10 PRINT "Hello")
    
Click 'Run' to execute the program.
Use 'Save' and 'Load' to manage BASIC programs.
Right-click for cut, copy, and paste options.
    
    """
help_text3 = """
    Examples:
10 REM Test program for TRS-80 BASIC Simulator
20 REM Test CLS and PRINT
30 CLS
40 PRINT "TRS-80 BASIC Simulator Test"
50 PRINT "----------------------------"

60 REM Test LET and arithmetic
70 LET A = 5
80 LET B = 3
90 PRINT "A ="; A; "B ="; B
100 PRINT "A + B ="; A + B
110 PRINT "A - B ="; A - B
120 PRINT "A * B ="; A * B
130 PRINT "A / B ="; A / B

140 REM Test string variables and concatenation
150 LET A$ = "HELLO"
160 LET B$ = "WORLD"
170 PRINT A$ + " " + B$

180 REM Test INPUT
190 PRINT "ENTER A NUMBER:"
200 INPUT C
210 PRINT "YOU ENTERED:"; C

220 REM Test IF-THEN
230 IF C > 10 THEN PRINT "C IS GREATER THAN 10"

240 REM Test FOR-NEXT loop
250 FOR I = 1 TO 5
260 PRINT "LOOP ITERATION:"; I
270 NEXT I

280 REM Test GOSUB-RETURN
290 GOSUB 1000
300 PRINT "BACK FROM SUBROUTINE"

310 REM Test ON-GOTO
320 LET D = 2
330 ON D GOTO 350, 360, 370
340 GOTO 380
350 PRINT "D IS 1": GOTO 380
360 PRINT "D IS 2": GOTO 380
370 PRINT "D IS 3"
380 REM Continue after ON-GOTO

390 REM Test RND function
400 PRINT "RANDOM NUMBER:"; RND
"""
help_text4 = """
410 REM Test POKE and PEEK
420 POKE 15360, 65
430 PRINT "PEEKED VALUE:"; PEEK(15360)

440 REM Test key input using PEEK
450 PRINT "PRESS KEYS (Q TO QUIT):"
460 LET K = PEEK(14400)
470 IF K > 0 THEN PRINT "KEY PRESSED:"; CHR$(K)
480 IF K <> ASC("Q") THEN GOTO 460

490 REM TEST FOR DATA-READ
500 DATA 10, 20, 30
510 READ X, Y, Z
520 PRINT "READ DATA:", X, Y, Z

530 REM Test string functions
540 LET S$ = "HELLO WORLD"
550 PRINT "LENGTH OF S$:"; LEN(S$)
560 PRINT "LEFT 5 CHARS:"; LEFT$(S$, 5)
570 PRINT "RIGHT 5 CHARS:"; RIGHT$(S$, 5)
580 PRINT "MIDDLE 5 CHARS:"; MID$(S$, 4, 5)
590 PRINT "ABS OF -5:"; ABS(-5)

610 REM TAPE READ/WRITE TEST PROGRAM
620 PRINT "WRITING TO TAPE..."
630 FOR I = 1 TO 5
640 PRINT#-1,I*10
650 NEXT I
660 PRINT "READING FROM TAPE..."
670 FOR I = 1 TO 5
680 INPUT#-1,A
690 PRINT "READ: ";A
700 NEXT I
710 PRINT "DONE"
720 END

1000 REM Subroutine
1010 PRINT "IN SUBROUTINE"
1020 RETURN

2000 GRAPHICS TEST PROGRAM
2010 CLS
2020 FOR Y = 0 TO 47
2030 FOR X = 0 TO 127
2040 IF X MOD 8 = 0 THEN
2050 SET(X, Y)
2060 ELSE
2070 RESET(X, Y)
2080 END IF
    """

# Create the main window and start the application
root = tk.Tk()
app = TRS80Simulator(root)
root.mainloop()
