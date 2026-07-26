"""Keyboard Engine.

Constitution, KEYBOARD:

    Phase 1   Mac keyboard -> UART -> Console
    Phase 2   USB HID Keyboard -> USB Host -> Keyboard FIFO -> Console
    The console behavior remains unchanged.

That last line is the whole point of this engine.  The Console never reads a
UART and never reads a USB endpoint; it reads *here*.  Phase 2 replaces the
source that fills the FIFO and nothing above this line changes.
"""

from __future__ import annotations

from collections import deque

from .. import memory_map as mm
from ..memory import Memory

FIFO_DEPTH = 256


class KeyboardEngine:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.fifo: deque[int] = deque()
        self._update_status()

    # -- source side (UART in phase 1, USB host in phase 2) ----------------

    def push(self, code: int) -> None:
        if len(self.fifo) >= FIFO_DEPTH:
            return  # a full FIFO drops keys, as the hardware will
        self.fifo.append(code & 0xFF)
        self._update_status()

    def push_text(self, text: str) -> None:
        for char in text:
            self.push(ord(char))

    # -- console side ------------------------------------------------------

    @property
    def key_available(self) -> bool:
        return bool(self.fifo)

    def read_key(self) -> int | None:
        """Take one key, or None when the FIFO is empty."""
        if not self.fifo:
            return None
        code = self.fifo.popleft()
        self.memory.write(mm.IO_KEYBOARD_DATA, code)
        self._update_status()
        return code

    def clear(self) -> None:
        self.fifo.clear()
        self._update_status()

    def _update_status(self) -> None:
        status = mm.KEYBOARD_STATUS_READY if self.fifo else 0
        self.memory.write(mm.IO_KEYBOARD_STATUS, status)
