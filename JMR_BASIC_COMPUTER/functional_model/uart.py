"""UART: the phase 1 host link (implementation order step 1).

Constitution, KEYBOARD phase 1:

    Mac keyboard -> UART -> Console

and STORAGE phase 1:

    Host files -> UART -> Program RAM

The UART is a byte pipe with two registers and a status register.  Received
bytes are handed to the Keyboard Engine, so the Console is already written
against the phase 2 interface.  Transmitted bytes are the host-side echo of
what the machine is doing; the screen itself is Video RAM, not the UART.
"""

from __future__ import annotations

from collections import deque

from . import memory_map as mm
from .memory import Memory


class Uart:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.rx: deque[int] = deque()
        self.tx: deque[int] = deque()
        self._update_status()

    # -- host -> machine ---------------------------------------------------

    def receive(self, data: bytes | str) -> None:
        """Called by the host front end when the user types or sends a file."""
        if isinstance(data, str):
            data = data.encode("ascii", "replace")
        self.rx.extend(data)
        self._update_status()

    def read_byte(self) -> int | None:
        if not self.rx:
            return None
        byte = self.rx.popleft()
        self.memory.write(mm.IO_UART_RX_DATA, byte)
        self._update_status()
        return byte

    def poll(self, keyboard) -> None:
        """Drain the receiver into the Keyboard FIFO.

        In phase 2 the USB host does this instead and nothing else changes.
        """
        while True:
            byte = self.read_byte()
            if byte is None:
                return
            keyboard.push(byte)

    # -- machine -> host ---------------------------------------------------

    def write_byte(self, value: int) -> None:
        self.memory.write(mm.IO_UART_TX_DATA, value & 0xFF)
        self.tx.append(value & 0xFF)
        self._update_status()

    def write(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("ascii", "replace")
        for byte in data:
            self.write_byte(byte)

    def take_transmitted(self) -> bytes:
        """Host side: collect and clear everything the machine has sent."""
        out = bytes(self.tx)
        self.tx.clear()
        self._update_status()
        return out

    def _update_status(self) -> None:
        status = 0
        if self.rx:
            status |= mm.UART_STATUS_RX_READY
        if self.tx:
            status |= mm.UART_STATUS_TX_BUSY
        self.memory.write(mm.IO_UART_STATUS, status)
