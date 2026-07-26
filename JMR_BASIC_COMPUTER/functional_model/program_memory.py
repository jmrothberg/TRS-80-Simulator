"""Program Memory: tokenized BASIC lines and the line directory.

Lines are held in one contiguous ascending run starting at PROGRAM_BASE, each
one a record of

    [line# lo][line# hi][length][token ...][0x00]

`length` counts the token bytes including the terminating 0x00.  The first free
byte is kept in SYSVAR_PROGRAM_END, so the end of the program is a pointer, not
a sentinel value that a valid line number could collide with.

Inserting or deleting a line moves the tail of the program, exactly as the
hardware will: one block move, no relocation table.  The directory is a *scan*
of the same records rather than a second copy of the data, so it can never
disagree with the token stream.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple

from . import memory_map as mm
from .errors import BasicError, OUT_OF_MEMORY
from .memory import Memory


class LineRecord(NamedTuple):
    address: int  # address of the record header
    number: int  # BASIC line number
    length: int  # token bytes, including the terminating 0x00

    @property
    def tokens_address(self) -> int:
        return self.address + mm.LINE_HEADER_SIZE

    @property
    def total_size(self) -> int:
        return mm.LINE_HEADER_SIZE + self.length

    @property
    def next_address(self) -> int:
        return self.address + self.total_size


class ProgramMemory:
    """Owns the Program Memory region."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.clear()

    # -- whole program -----------------------------------------------------

    def clear(self) -> None:
        """NEW: forget the program (the region itself is left as it is)."""
        self.memory.program_end = mm.PROGRAM_BASE

    @property
    def is_empty(self) -> bool:
        return self.memory.program_end <= mm.PROGRAM_BASE

    @property
    def bytes_used(self) -> int:
        return self.memory.program_end - mm.PROGRAM_BASE

    @property
    def bytes_free(self) -> int:
        return mm.PROGRAM_SIZE - self.bytes_used

    # -- line directory ----------------------------------------------------

    def record_at(self, address: int) -> LineRecord:
        return LineRecord(
            address=address,
            number=self.memory.read_word(address),
            length=self.memory.read(address + 2),
        )

    def lines(self) -> Iterator[LineRecord]:
        """Walk the directory in ascending line-number order."""
        address = mm.PROGRAM_BASE
        end = self.memory.program_end
        while address < end:
            record = self.record_at(address)
            yield record
            address = record.next_address

    def find(self, line_number: int) -> LineRecord | None:
        """Locate a line.  The hardware scans; so does this."""
        for record in self.lines():
            if record.number == line_number:
                return record
            if record.number > line_number:
                return None
        return None

    def first_line(self) -> LineRecord | None:
        if self.is_empty:
            return None
        return self.record_at(mm.PROGRAM_BASE)

    def line_after(self, record: LineRecord) -> LineRecord | None:
        address = record.next_address
        if address >= self.memory.program_end:
            return None
        return self.record_at(address)

    def tokens_of(self, record: LineRecord) -> bytes:
        return self.memory.read_block(record.tokens_address, record.length)

    # -- editing -----------------------------------------------------------

    def store(self, line_number: int, token_bytes: bytes) -> None:
        """Insert or replace a line.  Empty token stream deletes the line."""
        self.delete(line_number)
        if len(token_bytes) <= 1:  # just the T_EOS terminator
            return

        size = mm.LINE_HEADER_SIZE + len(token_bytes)
        if size > self.bytes_free:
            raise BasicError(OUT_OF_MEMORY, "program memory full")

        insert_at = self._insertion_point(line_number)
        end = self.memory.program_end
        tail = end - insert_at
        if tail:
            self.memory.move_block(insert_at, insert_at + size, tail)
        self.memory.write_word(insert_at, line_number)
        self.memory.write(insert_at + 2, len(token_bytes))
        self.memory.write_block(insert_at + mm.LINE_HEADER_SIZE, token_bytes)
        self.memory.program_end = end + size

    def delete(self, line_number: int) -> bool:
        record = self.find(line_number)
        if record is None:
            return False
        end = self.memory.program_end
        tail = end - record.next_address
        if tail:
            self.memory.move_block(record.next_address, record.address, tail)
        self.memory.program_end = end - record.total_size
        return True

    def _insertion_point(self, line_number: int) -> int:
        for record in self.lines():
            if record.number > line_number:
                return record.address
        return self.memory.program_end
