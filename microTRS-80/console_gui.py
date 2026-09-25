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
        self.pending = b''
        self.snap = b''
        self.snap_left = 0
        self.snap_kind = ''
        self.serial = None
        self.inbox = queue.Queue()
        # Last text actually put in the widget. A repeat frame must not redraw.
        self.painted = None
        self.painted_cursor = -1
        # Black ink on white paper, same as the e-ink. Green-on-black fought
        # the widget's own white and the lower half flashed every few seconds.
        self.text = tk.Text(
            self, width=COLS, height=ROWS, wrap='none',
            bg='white', fg='black', insertbackground='black',
            selectbackground='white', selectforeground='black',
            font=('DejaVu Sans Mono', 15), borderwidth=8, relief='flat',
            highlightthickness=0, insertwidth=0)
        # The I-beam sat above and left of ">". A block in the cursor cell is the caret.
        self.text.tag_configure('caret', background='black', foreground='white')
        self.caret_on = True
        self.text.pack()
        self.status = tk.Label(
            self, text='Connecting to ' + PORT + ' ...',
            bg='black', fg='#1f7a32', font=('DejaVu Sans Mono', 11))
        self.status.pack(fill='x')
        self.text.bind('<Key>', self.on_key)
        # A click must not move the caret. It stays just after > (the board cursor).
        for seq in ('<Button-1>', '<B1-Motion>', '<ButtonRelease-1>',
                    '<Shift-Button-1>', '<Double-Button-1>', '<Triple-Button-1>',
                    '<Button-2>', '<Button-3>'):
            self.text.bind(seq, self.keep_cursor)
        self.text.focus_set()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(40, self.drain)
        self.after(500, self.blink_caret)
        self.after(2000, self.ask_frame)
        threading.Thread(target=self.reader, daemon=True).start()

    def reader(self):
        try:
            import serial
            port = serial.Serial(PORT, BAUD, timeout=0.2)
        except Exception as exc:
            self.inbox.put(('status', 'Serial port not open: ' + str(exc)))
            return
        self.serial = port
        self.inbox.put(('status', PORT + '  —  this window shows the panel'))
        # Ask for the frame already on the panel. A newline would be a command.
        try:
            port.write(b'\x1c')
        except Exception:
            pass
        while True:
            try:
                data = port.read(256)
            except Exception as exc:
                self.inbox.put(('status', 'Serial closed: ' + str(exc)))
                return
            if data:
                self.inbox.put(('bytes', data))

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

    def keep_cursor(self, event):
        """Leave the caret where the board put it, just after the prompt."""
        self.text.focus_set()
        self.place_cursor()
        return 'break'

    def place_cursor(self):
        """Block in the cell where the next key will go, on the same line as >."""
        self.caret_on = True
        self.text.tag_configure('caret', background='black', foreground='white')
        self.text.tag_remove('caret', '1.0', 'end')
        row, col = divmod(self.cursor, COLS)
        if row >= ROWS:
            row = ROWS - 1
        if col >= COLS:
            col = COLS - 1
        if col < 0:
            col = 0
        start = '%d.%d' % (row + 1, col)
        end = '%d.%d' % (row + 1, col + 1)
        try:
            self.text.tag_add('caret', start, end)
            self.text.mark_set('insert', start)
            self.text.see(start)
        except tk.TclError:
            return
        self.painted_cursor = self.cursor

    def blink_caret(self):
        self.caret_on = not self.caret_on
        if self.caret_on:
            self.text.tag_configure('caret', background='black', foreground='white')
        else:
            self.text.tag_configure('caret', background='white', foreground='black')
        self.after(500, self.blink_caret)

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

    def ask_frame(self):
        # Keep asking. The board answers with the last picture it put on the panel.
        if self.serial is not None:
            try:
                self.serial.write(b'\x1c')
            except Exception:
                pass
        self.after(2000, self.ask_frame)

    def apply_frame(self, raw):
        """raw is 4 cursor digits plus 2048 hex digits, one byte per cell."""
        try:
            cur = int(raw[:4])
            body = bytes.fromhex(raw[4:].decode('ascii'))
        except (ValueError, UnicodeError):
            return False
        if len(body) != COLS * ROWS:
            return False
        self.cursor = cur if 0 <= cur < COLS * ROWS else 0
        self.cells = []
        for row in range(ROWS):
            line = []
            for col in range(COLS):
                code = body[row * COLS + col]
                line.append(chr(code) if code >= 32 else ' ')
            self.cells.append(line)
        return True

    def apply_poke(self, raw):
        """One typed cell: 4 cursor digits, 4 cell digits, 2 hex digits."""
        try:
            cur = int(raw[0:4])
            idx = int(raw[4:8])
            code = int(raw[8:10], 16)
        except (ValueError, IndexError):
            return False
        if not (0 <= idx < COLS * ROWS):
            return False
        ch = chr(code) if code >= 32 else ' '
        row, col = divmod(idx, COLS)
        self.cells[row][col] = ch
        self.cursor = cur if 0 <= cur < COLS * ROWS else 0
        if self.painted is None:
            return True
        pos = '%d.%d' % (row + 1, col)
        nxt = '%d.%d' % (row + 1, col + 1)
        self.text.delete(pos, nxt)
        self.text.insert(pos, ch)
        self.painted = '\n'.join(''.join(line) for line in self.cells)
        self.painted_cursor = -1
        self.place_cursor()
        return False

    def feed(self, data):
        """Take panel frames out of the byte stream. Other serial text is the monitor, not the screen."""
        if isinstance(data, str):
            data = data.encode('latin-1', 'replace')
        self.pending += data
        applied = False
        while True:
            if self.snap_left:
                take = min(self.snap_left, len(self.pending))
                self.snap += self.pending[:take]
                self.pending = self.pending[take:]
                self.snap_left -= take
                if self.snap_left:
                    break
                if self.snap_kind == 'k':
                    applied = self.apply_poke(self.snap) or applied
                else:
                    applied = self.apply_frame(self.snap) or applied
                self.snap = b''
                self.snap_kind = ''
                continue
            mark, kind = self._marker()
            if mark < 0:
                if len(self.pending) > 3:
                    self.pending = self.pending[-3:]
                break
            self.pending = self.pending[mark + 3:]
            self.snap = b''
            self.snap_kind = kind
            if kind == 'k':
                self.snap_left = 10
            else:
                self.snap_left = 4 + COLS * ROWS * 2
        return applied

    def _marker(self):
        """Earliest frame or one-cell echo in the buffer."""
        frame = self.pending.find(b'\x1b]S')
        poke = self.pending.find(b'\x1b]k')
        if frame < 0:
            return poke, 'k'
        if poke < 0 or frame <= poke:
            return frame, 'S'
        return poke, 'k'

    def paint(self):
        blob = '\n'.join(''.join(row) for row in self.cells)
        # The board resends the same picture every couple of seconds.
        # Wiping the widget to draw it again is the flash.
        if blob != self.painted:
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', blob)
            self.painted = blob
            # delete/insert parks the caret at the end. Put it back.
            self.painted_cursor = -1
        if self.cursor != self.painted_cursor:
            self.painted_cursor = self.cursor
            self.place_cursor()

    def drain(self):
        dirty = False
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == 'bytes':
                if self.feed(payload):
                    dirty = True
                    self.status.configure(text=PORT + '  —  same 64x16 as the panel')
            else:
                self.status.configure(text=payload)
                # A failed open used to leave a blank window that looked dead.
                if self.serial is None:
                    self.cells = [[' '] * COLS for _ in range(ROWS)]
                    row = col = 0
                    for ch in payload:
                        if ch == '\n' or col >= COLS:
                            row += 1
                            col = 0
                            if ch == '\n':
                                continue
                        if row >= ROWS:
                            break
                        self.cells[row][col] = ch
                        col += 1
                    self.paint()
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
