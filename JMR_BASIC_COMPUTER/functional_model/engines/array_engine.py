"""Array Engine.

Arrays are implementation order step 18, after Strings.  The engine exists now
as its own module with its own interface so that DIM and subscripted references
have somewhere to land, and so that nothing else in the machine grows array
code that would later have to be pulled back out ("Do not merge them into one
giant module").

Planned layout, in Variable Memory above the scalars:

    descriptor: [name0][name1][rank][dim0 lo][dim0 hi]...[data ptr lo][data ptr hi]
    data:       rank-major, 2 bytes per integer element

Until the milestone is implemented, DIM and subscripted access report the
Level II "not implemented" path rather than silently doing something else.
"""

from __future__ import annotations

from .. import memory_map as mm
from ..errors import BasicError, ILLEGAL_FUNCTION_CALL
from ..memory import Memory


class ArrayEngine:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.clear()

    def clear(self) -> None:
        self.memory.fill(mm.ARRAY_TABLE_BASE, mm.ARRAY_TABLE_TOP - mm.ARRAY_TABLE_BASE + 1, 0)

    def dimension(self, name0: int, name1: int, bounds: list[int]) -> int:
        raise BasicError(ILLEGAL_FUNCTION_CALL, "arrays arrive in implementation step 18")

    def element_address(self, name0: int, name1: int, subscripts: list[int]) -> int:
        raise BasicError(ILLEGAL_FUNCTION_CALL, "arrays arrive in implementation step 18")
