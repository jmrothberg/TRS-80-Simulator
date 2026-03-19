import tkinter as tk
from tkinter import scrolledtext
import re

class TRS80Simulator:
    def __init__(self, master):
        self.master = master
        master.title("TRS-80 Simulator")

        # Set up the main frame
        self.main_frame = tk.Frame(master, bg="black")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create the TRS-80 screen (128x48 pixels, but each pixel is 2x2 screen pixels)
        self.pixel_size = 6  # Each pixel is 3x3 screen pixels
        self.screen = tk.Canvas(self.main_frame, width=768, height=546, bg="black", highlightthickness=0)  # Doubled height
        self.screen.pack(pady=10)

        # Create the BASIC input area
        self.input_area = scrolledtext.ScrolledText(self.main_frame, width=64, height=10, bg="lightgray", fg="black", font=("Courier", 14))
        self.input_area.pack(pady=10)

        # Create Run button
        self.run_button = tk.Button(self.main_frame, text="Run", command=self.run_program)
        self.run_button.pack(pady=5)

        # Create Clear button
        self.clear_button = tk.Button(self.main_frame, text="Clear Screen", command=self.clear_screen)
        self.clear_button.pack(pady=5)

        # Initialize screen content
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self.text_matrix = [[' ' for _ in range(64)] for _ in range(16)]
        
        
        self.clear_screen()

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

    def print_text(self, text, row, col):
        if 0 <= row < 16 and 0 <= col < 64:
            # Update the text matrix
            for i, char in enumerate(text):
                if col + i < 64:
                    self.text_matrix[row][col + i] = char

            # Redraw the entire text display
            self.redraw_text()

    def redraw_text(self):
        # Clear previous text
        self.screen.delete("text")

        # Draw all text in the text matrix
        for row in range(16):
            for col in range(64):
                char = self.text_matrix[row][col]
                x = col * 12  # 4 pixels per character horizontally
                y = row * 36  # 12 pixels per character vertically (doubled from 6)
                self.screen.create_text(x, y, text=char, font=("Courier", 14), fill="lime", anchor="nw", tags="text")  # Increased font size

    def run_program(self):
        program = self.input_area.get(1.0, tk.END).strip().split('\n')
        for line in program:
            self.execute_command(line)

    def execute_command(self, command):
        if command.startswith('SET'):
            match = re.match(r'SET\s*\((\d+)\s*,\s*(\d+)\)', command)
            if match:
                x, y = map(int, match.groups())
                self.set_pixel(x, y)
        elif command.startswith('RESET'):
            match = re.match(r'RESET\s*\((\d+)\s*,\s*(\d+)\)', command)
            if match:
                x, y = map(int, match.groups())
                self.reset_pixel(x, y)
        elif command.startswith('PRINT POINT'):
            match = re.match(r'PRINT POINT\s*\((\d+)\s*,\s*(\d+)\)', command)
            if match:
                x, y = map(int, match.groups())
                value = self.get_pixel(x, y)
                print(f"POINT({x},{y}) = {value}")
        elif command.startswith('PRINT'):
            match = re.match(r'PRINT\s*@\s*(\d+)\s*,\s*"(.+)"', command)
            if match:
                position, text = match.groups()
                position = int(position)
                row, col = position // 64, position % 64
                self.print_text(text, row, col)

    def clear_screen(self):
        self.screen.delete("all")
        self.pixel_matrix = [[0 for _ in range(128)] for _ in range(48)]
        self.text_matrix = [[' ' for _ in range(64)] for _ in range(16)]

# Create the main window and start the application
root = tk.Tk()
app = TRS80Simulator(root)

# Add a test program to the input area
test_program = """
SET(0,0)
SET(127,0)
SET(0,47)
SET(127,47)
SET(64,24)
PRINT POINT(0,0)
PRINT POINT(127,0)
PRINT POINT(0,47)
PRINT POINT(127,47)
PRINT POINT(64,24)
PRINT POINT(63,23)
RESET(0,0)
PRINT POINT(0,0)
PRINT @0,"HELLO, TRS-80!"
PRINT @128,"THIS IS TEXT"
"""
app.input_area.insert(tk.END, test_program)

root.mainloop()