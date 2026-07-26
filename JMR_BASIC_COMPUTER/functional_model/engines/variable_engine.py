"""Variable Engine: scalar variables in Variable Memory.

A slot is four bytes -- two name characters and a 16-bit signed value -- and
slots are allocated in order of first use.  Lookup is a linear scan that stops
at the first unallocated slot, which is what the hardware will do: a small
comparator walking a table in Block RAM.

Names follow Level II: the first two characters are significant, so `COUNT` and
`COUNTER` are the same variable.  A variable that has never been assigned reads
as 0 without being allocated.
"""

from __future__ import annotations

from .. import memory_map as mm
from ..errors import BasicError, OUT_OF_MEMORY
from ..memory import Memory

INT16_MIN = -32768
INT16_MAX = 32767


class VariableEngine:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.clear()

    def clear(self) -> None:
        """CLEAR / RUN / NEW: drop every variable."""
        self.memory.fill(
            mm.SCALAR_TABLE_BASE, mm.SCALAR_SLOT_COUNT * mm.SCALAR_SLOT_SIZE, 0
        )

    # -- slots -------------------------------------------------------------

    def find_slot(self, name0: int, name1: int) -> int | None:
        address = mm.SCALAR_TABLE_BASE
        for _ in range(mm.SCALAR_SLOT_COUNT):
            stored0 = self.memory.read(address)
            if stored0 == 0:
                return None  # first free slot ends the search
            if stored0 == name0 and self.memory.read(address + 1) == name1:
                return address
            address += mm.SCALAR_SLOT_SIZE
        return None

    def allocate_slot(self, name0: int, name1: int) -> int:
        address = mm.SCALAR_TABLE_BASE
        for _ in range(mm.SCALAR_SLOT_COUNT):
            if self.memory.read(address) == 0:
                self.memory.write(address, name0)
                self.memory.write(address + 1, name1)
                self.memory.write_word(address + 2, 0)
                return address
            address += mm.SCALAR_SLOT_SIZE
        raise BasicError(OUT_OF_MEMORY, "variable table full")

    def address_of(self, name0: int, name1: int) -> int:
        """Slot address, allocating on first use (what LET and FOR need)."""
        address = self.find_slot(name0, name1)
        if address is None:
            address = self.allocate_slot(name0, name1)
        return address

    # -- values ------------------------------------------------------------

    def read(self, name0: int, name1: int) -> int:
        address = self.find_slot(name0, name1)
        if address is None:
            return 0
        return self.memory.read_signed_word(address + 2)

    def write(self, name0: int, name1: int, value: int) -> None:
        self.write_at(self.address_of(name0, name1), value)

    def read_at(self, slot_address: int) -> int:
        return self.memory.read_signed_word(slot_address + 2)

    def write_at(self, slot_address: int, value: int) -> None:
        self.memory.write_signed_word(slot_address + 2, check_range(value))

    # -- inspection --------------------------------------------------------

    def items(self) -> list[tuple[str, int]]:
        """Every allocated variable, in allocation order (tests, monitor)."""
        out = []
        address = mm.SCALAR_TABLE_BASE
        for _ in range(mm.SCALAR_SLOT_COUNT):
            name0 = self.memory.read(address)
            if name0 == 0:
                break
            name1 = self.memory.read(address + 1)
            name = chr(name0) + (chr(name1) if name1 else "")
            out.append((name, self.memory.read_signed_word(address + 2)))
            address += mm.SCALAR_SLOT_SIZE
        return out


def check_range(value: int) -> int:
    """Stage 1 is 16-bit signed integer BASIC; anything else is ?OV ERROR."""
    if not INT16_MIN <= value <= INT16_MAX:
        raise BasicError("OV", f"{value} is outside 16-bit signed range")
    return value
