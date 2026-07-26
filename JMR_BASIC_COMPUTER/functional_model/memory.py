"""Flat 64K address space shared by every engine.

The Constitution requires that "Python exposes every internal state".  Nothing
in this computer keeps architectural state in a private Python object: program
text, variables, stacks and the screen all live here, at the documented
addresses, where a test (or a future monitor command) can read them.

Word storage is little endian throughout.
"""

from __future__ import annotations

from . import memory_map as mm


class MemoryError_(Exception):
    """Raised on an access outside the address space."""


class Memory:
    """A byte-addressed 64K space with word and stack helpers."""

    def __init__(self) -> None:
        self.cells = bytearray(mm.ADDRESS_SPACE)

    # -- byte access -------------------------------------------------------

    def read(self, address: int) -> int:
        if not 0 <= address < mm.ADDRESS_SPACE:
            raise MemoryError_(f"read outside address space: {address:#06x}")
        return self.cells[address]

    def write(self, address: int, value: int) -> None:
        if not 0 <= address < mm.ADDRESS_SPACE:
            raise MemoryError_(f"write outside address space: {address:#06x}")
        self.cells[address] = value & 0xFF

    # -- word access -------------------------------------------------------

    def read_word(self, address: int) -> int:
        """Unsigned 16-bit little endian."""
        return self.read(address) | (self.read(address + 1) << 8)

    def write_word(self, address: int, value: int) -> None:
        self.write(address, value & 0xFF)
        self.write(address + 1, (value >> 8) & 0xFF)

    def read_signed_word(self, address: int) -> int:
        value = self.read_word(address)
        return value - 0x10000 if value & 0x8000 else value

    def write_signed_word(self, address: int, value: int) -> None:
        self.write_word(address, value & 0xFFFF)

    # -- block access ------------------------------------------------------

    def read_block(self, address: int, length: int) -> bytes:
        if address < 0 or address + length > mm.ADDRESS_SPACE:
            raise MemoryError_(f"block read outside address space: {address:#06x}+{length}")
        return bytes(self.cells[address : address + length])

    def write_block(self, address: int, data: bytes) -> None:
        if address < 0 or address + len(data) > mm.ADDRESS_SPACE:
            raise MemoryError_(f"block write outside address space: {address:#06x}+{len(data)}")
        self.cells[address : address + len(data)] = data

    def move_block(self, source: int, destination: int, length: int) -> None:
        """Overlap-safe copy; program memory insertion depends on this."""
        self.write_block(destination, self.read_block(source, length))

    def fill(self, address: int, length: int, value: int = 0) -> None:
        self.write_block(address, bytes([value & 0xFF]) * length)

    # -- system pointers ---------------------------------------------------

    @property
    def program_end(self) -> int:
        return self.read_word(mm.SYSVAR_PROGRAM_END)

    @program_end.setter
    def program_end(self, address: int) -> None:
        self.write_word(mm.SYSVAR_PROGRAM_END, address)

    @property
    def current_line(self) -> int:
        return self.read_word(mm.SYSVAR_CURRENT_LINE)

    @current_line.setter
    def current_line(self, line_number: int) -> None:
        self.write_word(mm.SYSVAR_CURRENT_LINE, line_number)


class MemoryStack:
    """A stack living in the documented Stack Area.

    Frames are fixed size, the pointer is a frame index, and both are visible in
    memory.  Every stack in the machine (expression operands, operators, FOR,
    GOSUB) is one of these, so there is one implementation to port to hardware.
    """

    def __init__(self, memory: Memory, base: int, frame_size: int, depth: int, name: str) -> None:
        self.memory = memory
        self.base = base
        self.frame_size = frame_size
        self.depth = depth
        self.name = name
        self.pointer = 0

    def reset(self) -> None:
        self.pointer = 0

    @property
    def empty(self) -> bool:
        return self.pointer == 0

    def frame_address(self, index: int) -> int:
        return self.base + index * self.frame_size

    def push_frame(self) -> int:
        """Reserve a frame and return its address."""
        if self.pointer >= self.depth:
            raise StackOverflow(self.name)
        address = self.frame_address(self.pointer)
        self.pointer += 1
        return address

    def pop_frame(self) -> int:
        if self.pointer == 0:
            raise StackUnderflow(self.name)
        self.pointer -= 1
        return self.frame_address(self.pointer)

    def top_frame(self) -> int:
        if self.pointer == 0:
            raise StackUnderflow(self.name)
        return self.frame_address(self.pointer - 1)

    def drop(self, count: int = 1) -> None:
        self.pointer = max(0, self.pointer - count)


class StackOverflow(Exception):
    pass


class StackUnderflow(Exception):
    pass
