"""Console: keyboard interpreter, line editor and command detector.

The CONSOLE / LINE EDITOR block of the architecture diagram.  It reads the
Keyboard Engine (never the UART directly, so phase 2 changes nothing here),
echoes to the screen through the Print Engine, and hands finished lines up.

The same line editor serves both the `>` prompt and a running program's INPUT
statement.  There is one line editor in this computer.
"""

from __future__ import annotations

from collections import deque

from . import memory_map as mm
from .engines.keyboard_engine import KeyboardEngine
from .engines.print_engine import PrintEngine
from .engines.video_engine import VideoEngine

CARRIAGE_RETURN = 0x0D
LINE_FEED = 0x0A
BACKSPACE = 0x08
DELETE = 0x7F
CANCEL = 0x18  # shift-left-arrow on a Level II machine: kill the line

PROMPT = ">"


class Console:
    def __init__(
        self,
        memory,
        keyboard: KeyboardEngine,
        printer: PrintEngine,
        video: VideoEngine,
    ) -> None:
        self.memory = memory
        self.keyboard = keyboard
        self.printer = printer
        self.video = video
        self.buffer = ""
        self.completed: deque[str] = deque()

    # -- keyboard interpreter ---------------------------------------------

    def poll(self) -> None:
        """Drain the Keyboard FIFO into the line buffer, echoing as we go."""
        while True:
            code = self.keyboard.read_key()
            if code is None:
                return
            self._interpret(code)

    def _interpret(self, code: int) -> None:
        if code in (CARRIAGE_RETURN, LINE_FEED):
            self.printer.newline()
            self.completed.append(self.buffer)
            self._store_buffer()
            self.buffer = ""
        elif code in (BACKSPACE, DELETE):
            if self.buffer:
                self.buffer = self.buffer[:-1]
                self.video.backspace()
        elif code == CANCEL:
            while self.buffer:
                self.buffer = self.buffer[:-1]
                self.video.backspace()
        elif 0x20 <= code <= 0x7E:
            if len(self.buffer) < mm.INPUT_LINE_BUFFER_SIZE - 1:
                self.buffer += chr(code)
                self.printer.put_text(chr(code))

    def _store_buffer(self) -> None:
        """Keep the finished line where the hardware will: in Work RAM."""
        data = self.buffer.encode("ascii", "replace")[: mm.INPUT_LINE_BUFFER_SIZE - 1]
        self.memory.write_block(mm.INPUT_LINE_BUFFER, data + b"\0")

    # -- command detector --------------------------------------------------

    @property
    def has_line(self) -> bool:
        return bool(self.completed)

    def take_line(self) -> str | None:
        """A finished line for the `>` prompt."""
        return self.completed.popleft() if self.completed else None

    def take_input_line(self) -> str | None:
        """A finished line for a running INPUT statement (same editor)."""
        return self.take_line()

    def prompt(self) -> None:
        self.printer.put_text(PROMPT)

    def ready(self) -> None:
        self.printer.print_line("READY")

    def reset(self) -> None:
        self.buffer = ""
        self.completed.clear()
