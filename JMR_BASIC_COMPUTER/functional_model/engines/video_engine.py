"""Video Engine.

Constitution, VIDEO:

    Video memory is shared text and graphics memory.
    64 x 16 characters
    128 x 48 graphics
    Graphics modify bits inside character cells.
    Video subsystem is independent of BASIC execution timing.

This engine owns Video RAM, the cursor register and scrolling.  It knows about
characters and cells; it knows nothing about BASIC.  The Print Engine decides
*what* to display, the Graphics Engine decides *which blocks* to light, and both
of them come here to touch memory.

A cell holds either a character code (0x20..0x7E) or, with bit 7 set, six
semigraphics blocks in bits 0..5 numbered

        block_num = block_y * 2 + block_x

    +---+---+
    | 0 | 1 |
    +---+---+
    | 2 | 3 |
    +---+---+
    | 4 | 5 |
    +---+---+
"""

from __future__ import annotations

from .. import memory_map as mm
from ..memory import Memory

BLANK = 0x20

#: Unicode sextants (U+1FB00..) render a semigraphics cell in one terminal
#: character.  The block-number order above is the same order Unicode uses.
_SEXTANT_SPECIALS = {0: " ", 21: "▌", 42: "▐", 63: "█"}


def _sextant(blocks: int) -> str:
    """Block pattern 0..63 -> one character.

    U+1FB00 is the pattern with only block 0 lit.  The four patterns that
    already exist elsewhere in Unicode (empty, left half, right half, full) are
    skipped in that run, so they are handled first and then subtracted out.
    """
    if blocks in _SEXTANT_SPECIALS:
        return _SEXTANT_SPECIALS[blocks]
    index = blocks - 1 - sum(1 for special in _SEXTANT_SPECIALS if 0 < special < blocks)
    return chr(0x1FB00 + index)


class VideoEngine:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.clear()

    # -- cursor register ---------------------------------------------------

    @property
    def cursor(self) -> int:
        """Cursor as an offset into VRAM (0 .. 1023), i.e. PRINT@ position."""
        return self.memory.read(mm.IO_CURSOR_LO) | (self.memory.read(mm.IO_CURSOR_HI) << 8)

    @cursor.setter
    def cursor(self, offset: int) -> None:
        offset %= mm.VRAM_SIZE
        self.memory.write(mm.IO_CURSOR_LO, offset & 0xFF)
        self.memory.write(mm.IO_CURSOR_HI, offset >> 8)

    @property
    def cursor_row(self) -> int:
        return self.cursor // mm.TEXT_COLUMNS

    @property
    def cursor_column(self) -> int:
        return self.cursor % mm.TEXT_COLUMNS

    # -- cells -------------------------------------------------------------

    def read_cell(self, row: int, column: int) -> int:
        return self.memory.read(mm.vram_address(row, column))

    def write_cell(self, row: int, column: int, value: int) -> None:
        self.memory.write(mm.vram_address(row, column), value)

    def clear(self) -> None:
        """CLS: blank the screen and home the cursor."""
        self.memory.fill(mm.VRAM_BASE, mm.VRAM_SIZE, BLANK)
        self.cursor = 0

    # -- character output --------------------------------------------------

    def put_char(self, code: int) -> None:
        """Write one character at the cursor and advance, scrolling at the end."""
        self.memory.write(mm.VRAM_BASE + self.cursor, code)
        self.advance()

    def advance(self) -> None:
        offset = self.cursor + 1
        if offset >= mm.VRAM_SIZE:
            self.scroll()
            offset = (mm.TEXT_ROWS - 1) * mm.TEXT_COLUMNS
        self.cursor = offset

    def newline(self) -> None:
        row = self.cursor_row
        if row >= mm.TEXT_ROWS - 1:
            self.scroll()
            self.cursor = (mm.TEXT_ROWS - 1) * mm.TEXT_COLUMNS
        else:
            self.cursor = (row + 1) * mm.TEXT_COLUMNS

    def backspace(self) -> None:
        if self.cursor == 0:
            return
        self.cursor -= 1
        self.memory.write(mm.VRAM_BASE + self.cursor, BLANK)

    def scroll(self) -> None:
        """Move every row up one and blank the bottom row."""
        self.memory.move_block(
            mm.VRAM_BASE + mm.TEXT_COLUMNS,
            mm.VRAM_BASE,
            mm.VRAM_SIZE - mm.TEXT_COLUMNS,
        )
        self.memory.fill(
            mm.VRAM_BASE + mm.VRAM_SIZE - mm.TEXT_COLUMNS, mm.TEXT_COLUMNS, BLANK
        )

    # -- readback ----------------------------------------------------------

    def text_lines(self, graphics_as: str = "sextant") -> list[str]:
        """The screen as 16 strings of 64 characters.

        `graphics_as` selects how semigraphics cells are rendered: "sextant"
        for a terminal, "hash" for readable test expectations.
        """
        lines = []
        for row in range(mm.TEXT_ROWS):
            out = []
            for column in range(mm.TEXT_COLUMNS):
                cell = self.read_cell(row, column)
                if cell & mm.SEMIGRAPHICS_FLAG:
                    blocks = cell & mm.SEMIGRAPHICS_BLOCK_MASK
                    if graphics_as == "hash":
                        out.append(" " if blocks == 0 else "#")
                    else:
                        out.append(_sextant(blocks))
                elif 0x20 <= cell <= 0x7E:
                    out.append(chr(cell))
                else:
                    out.append(" ")
            lines.append("".join(out))
        return lines

    def screen_text(self, graphics_as: str = "sextant") -> str:
        """The screen with trailing blanks and trailing blank lines removed."""
        lines = [line.rstrip() for line in self.text_lines(graphics_as)]
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    def pixel_rows(self) -> list[str]:
        """The 128x48 graphics field, '#' for a lit block."""
        rows = []
        for y in range(mm.GRAPHICS_HEIGHT):
            out = []
            for x in range(mm.GRAPHICS_WIDTH):
                out.append("#" if self.get_point(x, y) else " ")
            rows.append("".join(out))
        return rows

    # -- block access, used by the Graphics Engine -------------------------

    def get_point(self, x: int, y: int) -> bool:
        cell, bit = self._decode_point(x, y)
        value = self.memory.read(cell)
        if not value & mm.SEMIGRAPHICS_FLAG:
            return False
        return bool(value & (1 << bit))

    def set_point(self, x: int, y: int, lit: bool) -> None:
        cell, bit = self._decode_point(x, y)
        value = self.memory.read(cell)
        if not value & mm.SEMIGRAPHICS_FLAG:
            # A text cell becomes an empty graphics cell the moment a block in
            # it is addressed; that is how the two modes share one memory.
            value = mm.SEMIGRAPHICS_FLAG
        if lit:
            value |= 1 << bit
        else:
            value &= ~(1 << bit) & 0xFF
        self.memory.write(cell, value | mm.SEMIGRAPHICS_FLAG)

    @staticmethod
    def _decode_point(x: int, y: int) -> tuple[int, int]:
        """SET/RESET/POINT addressing, straight off the architecture diagram."""
        cell_col = x // 2
        cell_row = y // 3
        block_x = x % 2
        block_y = y % 3
        block_num = block_y * 2 + block_x
        return mm.vram_address(cell_row, cell_col), block_num
