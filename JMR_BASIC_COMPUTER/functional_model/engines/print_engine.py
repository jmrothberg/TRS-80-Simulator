"""Print Engine.

Turns values into characters and hands them to the Video Engine.  This is the
"Convert to decimal string / Output characters / Update cursor" part of the
PRINT microcode on the architecture diagram.

Level II display conventions kept here:

* a number is printed with a leading space when it is positive (the space is
  where the minus sign would go) and always with one trailing space
* a comma between items moves to the next 16-column print zone
* a semicolon between items moves nothing
* an item list that ends in "," or ";" suppresses the newline
"""

from __future__ import annotations

from .. import memory_map as mm
from .video_engine import VideoEngine

PRINT_ZONE_WIDTH = 16


class PrintEngine:
    def __init__(self, video: VideoEngine) -> None:
        self.video = video

    # -- primitives --------------------------------------------------------

    def put_text(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.video.newline()
            else:
                self.video.put_char(ord(char) & 0xFF)

    def newline(self) -> None:
        self.video.newline()

    def print_line(self, text: str) -> None:
        self.put_text(text)
        self.newline()

    # -- BASIC value formatting -------------------------------------------

    @staticmethod
    def format_number(value: int) -> str:
        """16-bit signed integer in Level II display format."""
        return (f"{value} " if value < 0 else f" {value} ")

    def print_number(self, value: int) -> None:
        self.put_text(self.format_number(value))

    def print_string(self, text: str) -> None:
        self.put_text(text)

    # -- separators --------------------------------------------------------

    def next_zone(self) -> None:
        """The comma separator: advance to the next print zone."""
        column = self.video.cursor_column
        target = ((column // PRINT_ZONE_WIDTH) + 1) * PRINT_ZONE_WIDTH
        if target >= mm.TEXT_COLUMNS:
            self.video.newline()
            return
        self.put_text(" " * (target - column))

    def print_at(self, position: int) -> None:
        """PRINT@ n: move the cursor to VRAM offset n."""
        self.video.cursor = position % mm.VRAM_SIZE
