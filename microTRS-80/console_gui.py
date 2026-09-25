#!/usr/bin/env python3
"""64x16 console for the ESP32 microTRS-80.

This window is the keyboard. Characters from the board are placed in the
same 64x16 grid the e-ink draws in the center of the CrowPanel.
"""

import queue
import sys
import threading
import tkinter as tk

PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
BAUD = 115200
COLS = 64
ROWS = 16


class Console(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('microTRS-80  64x16')
        self.configure(bg='black')
        self.cells = [[' '] * COLS for _ in range(ROWS)]
        self.cursor = 0
        self.esc = ''
        self.snap = []
        self.snap_left = 0
        self.serial = None
        self.inbox = queue.Queue()
        self.text = tk.Text(
            self, width=COLS, height=ROWS, wrap='none',
            bg='black', fg='#33ff66', insertbackground='#33ff66',
            font=('DejaVu Sans Mono', 15), borderwidth=8, relief='flat',
            highlightthickness=0)
        self.text.pack()
        self.status = tk.Label(
            self, text='Connecting to ' + PORT + ' ...',
            bg='black', fg='#1f7a32', font=('DejaVu Sans Mono', 11))
        self.status.pack(fill='x')
        self.text.bind('<Key>', self.on_key)
        self.text.focus_set()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(40, self.drain)
        threading.Thread(target=self.reader, daemon=True).start()

    def reader(self):
        try:
            import serial
            port = serial.Serial(PORT, BAUD, timeout=0.2)
        except Exception as exc:
            self.inbox.put(('status', 'Serial port not open: ' + str(exc)))
            return
        self.serial = port
        self.inbox.put(('status', PORT + '  —  this keyboard talks to the board'))
        # Ask the board to print READY> again if it was already waiting.
        try:
            port.write(b'\n')
        except Exception:
            pass
        while True:
            try:
                data = port.read(256)
            except Exception as exc:
                self.inbox.put(('status', 'Serial closed: ' + str(exc)))
                return
            if data:
                self.inbox.put(('bytes', data.decode('utf-8', 'replace')))

    def on_key(self, event):
        if self.serial is None:
            return 'break'
        if event.keysym == 'Return':
            sent = b'\n'
        elif event.keysym == 'BackSpace':
            sent = b'\x08'
        elif event.keysym == 'Escape':
            sent = b'\x1b'
        elif event.keysym == 'Left':
            sent = bytes([17])
        elif event.keysym == 'Right':
            sent = bytes([18])
        elif event.keysym == 'Up':
            sent = bytes([19])
        elif event.keysym == 'Down':
            sent = bytes([20])
        elif event.char and ord(event.char) >= 32:
            sent = event.char.encode('utf-8')
        else:
            return 'break'
        try:
            self.serial.write(sent)
        except Exception as exc:
            self.status.configure(text='Write failed: ' + str(exc))
        return 'break'

    def write_char(self, char):
        # Same cursor rules as Basic.screen_write on the board.
        if char == '\n':
            self.cursor = ((self.cursor // COLS) + 1) * COLS
        elif char == '\r':
            self.cursor -= self.cursor % COLS
        elif char in '\b\x7f':
            if self.cursor % COLS:
                self.cursor -= 1
                row, col = divmod(self.cursor, COLS)
                self.cells[row][col] = ' '
        elif char >= ' ':
            if self.cursor >= COLS * ROWS:
                self.cells.pop(0)
                self.cells.append([' '] * COLS)
                self.cursor -= COLS
            row, col = divmod(self.cursor, COLS)
            self.cells[row][col] = char
            self.cursor += 1
            if self.cursor >= COLS * ROWS:
                self.cells.pop(0)
                self.cells.append([' '] * COLS)
                self.cursor -= COLS

    def feed(self, text):
        for char in text:
            if self.snap_left:
                self.snap.append(char)
                self.snap_left -= 1
                if self.snap_left == 0:
                    raw = ''.join(self.snap)
                    self.snap = []
                    self.cursor = int(raw[:4])
                    payload = raw[4:]
                    self.cells = [list(payload[row * COLS:(row + 1) * COLS]) for row in range(ROWS)]
                continue
            if self.esc:
                self.esc += char
                # Screen snapshot: ESC ] S, then cursor and the 64x16 the panel just drew.
                if self.esc == '\x1b]S':
                    self.esc = ''
                    self.snap = []
                    self.snap_left = 4 + COLS * ROWS
                    continue
                # CLS sends ESC [ 2 J and ESC [ H. Drop the whole sequence.
                if char.isalpha():
                    if self.esc == '\x1b[2J' or self.esc == '\x1b[H':
                        if self.esc == '\x1b[2J':
                            self.cells = [[' '] * COLS for _ in range(ROWS)]
                            self.cursor = 0
                    self.esc = ''
                elif len(self.esc) > 8:
                    self.esc = ''
                continue
            if char == '\x1b':
                self.esc = char
                continue
            self.write_char(char)

    def paint(self):
        lines = []
        for row in range(ROWS):
            chars = self.cells[row][:]
            if self.cursor // COLS == row:
                col = self.cursor % COLS
                if chars[col] == ' ':
                    chars[col] = '_'
            lines.append(''.join(chars))
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', '\n'.join(lines))

    def drain(self):
        dirty = False
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == 'bytes':
                self.feed(payload)
                dirty = True
            else:
                self.status.configure(text=payload)
        if dirty:
            self.paint()
        self.after(40, self.drain)

    def close(self):
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.destroy()


if __name__ == '__main__':
    Console().mainloop()
