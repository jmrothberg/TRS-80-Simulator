"""String Engine: String Space and string values.

Strings are implementation order step 17.  This milestone implements the part
the boot experience needs -- string *literals*, so that

    10 PRINT "HELLO"

works -- and nothing more.  String variables, concatenation and the string
functions are the next milestone, and they belong here rather than being
sprinkled through the Expression Engine.

Even a literal is copied into String Space at its documented address instead of
being carried around as a Python object, because that is where the hardware
will have to put it.
"""

from __future__ import annotations

from .. import memory_map as mm
from ..errors import BasicError, OUT_OF_MEMORY
from ..memory import Memory

STRING_SPACE_SIZE = mm.STRING_TOP - mm.STRING_BASE + 1


class StringEngine:
    """Owns String Space.

    A string is stored as [length][characters] and referred to by the address of
    its length byte, which is what a string descriptor will hold.
    """

    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.clear()

    def clear(self) -> None:
        self.next_free = mm.STRING_BASE

    @property
    def bytes_used(self) -> int:
        return self.next_free - mm.STRING_BASE

    def store(self, text: str) -> int:
        """Copy a string into String Space and return its address."""
        data = text.encode("ascii", "replace")[:255]
        needed = 1 + len(data)
        if self.next_free + needed > mm.STRING_BASE + STRING_SPACE_SIZE:
            raise BasicError(OUT_OF_MEMORY, "string space full")
        address = self.next_free
        self.memory.write(address, len(data))
        self.memory.write_block(address + 1, data)
        self.next_free += needed
        return address

    def load(self, address: int) -> str:
        length = self.memory.read(address)
        return self.memory.read_block(address + 1, length).decode("ascii", "replace")
