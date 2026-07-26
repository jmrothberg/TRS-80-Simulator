"""Video Engine: cells, cursor, scrolling and semigraphics addressing."""

from __future__ import annotations

import unittest

import support  # noqa: F401

from functional_model import memory_map as mm
from functional_model.engines.graphics_engine import GraphicsEngine
from functional_model.engines.print_engine import PrintEngine
from functional_model.engines.video_engine import VideoEngine
from functional_model.errors import BasicError
from functional_model.memory import Memory


class VideoEngineTest(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.video = VideoEngine(self.memory)

    def test_clear_blanks_video_memory_and_homes_the_cursor(self):
        self.memory.write(mm.VRAM_BASE + 10, ord("X"))
        self.video.cursor = 100
        self.video.clear()
        self.assertEqual(self.memory.read(mm.VRAM_BASE + 10), 0x20)
        self.assertEqual(self.video.cursor, 0)

    def test_characters_land_in_video_memory(self):
        self.video.put_char(ord("A"))
        self.assertEqual(self.memory.read(mm.VRAM_BASE), ord("A"))
        self.assertEqual(self.video.cursor, 1)

    def test_cursor_register_is_readable_in_the_io_area(self):
        self.video.cursor = 0x0123
        self.assertEqual(self.memory.read(mm.IO_CURSOR_LO), 0x23)
        self.assertEqual(self.memory.read(mm.IO_CURSOR_HI), 0x01)

    def test_newline_moves_to_the_next_row(self):
        self.video.cursor = mm.vram_address(2, 30) - mm.VRAM_BASE
        self.video.newline()
        self.assertEqual(self.video.cursor_row, 3)
        self.assertEqual(self.video.cursor_column, 0)

    def test_the_screen_scrolls_at_the_bottom(self):
        self.video.cursor = 0
        for char in "TOP":
            self.video.put_char(ord(char))
        self.video.cursor = (mm.TEXT_ROWS - 1) * mm.TEXT_COLUMNS
        self.video.newline()
        self.assertEqual(self.video.text_lines()[0].strip(), "")
        self.assertEqual(self.video.cursor_row, mm.TEXT_ROWS - 1)

    def test_writing_past_the_last_cell_scrolls(self):
        self.video.cursor = mm.VRAM_SIZE - 1
        self.video.put_char(ord("Z"))
        self.assertEqual(self.video.cursor_row, mm.TEXT_ROWS - 1)
        self.assertEqual(self.video.cursor_column, 0)


class SemigraphicsTest(unittest.TestCase):
    """The SET/RESET/POINT ADDRESSING panel of the architecture diagram."""

    def setUp(self):
        self.memory = Memory()
        self.video = VideoEngine(self.memory)
        self.graphics = GraphicsEngine(self.video)

    def decode(self, x, y):
        return self.video._decode_point(x, y)

    def test_addressing_formulas(self):
        for x, y in ((0, 0), (1, 2), (127, 47), (65, 25)):
            with self.subTest(point=(x, y)):
                cell, block = self.decode(x, y)
                cell_col = x // 2
                cell_row = y // 3
                block_num = (y % 3) * 2 + (x % 2)
                self.assertEqual(cell, mm.VRAM_BASE + cell_row * 64 + cell_col)
                self.assertEqual(block, block_num)

    def test_the_six_blocks_of_one_cell_are_independent(self):
        for x in (0, 1):
            for y in (0, 1, 2):
                self.graphics.set(x, y)
        self.assertEqual(self.memory.read(mm.VRAM_BASE), 0xBF)  # flag + all six
        self.graphics.reset(1, 1)
        self.assertEqual(self.memory.read(mm.VRAM_BASE) & 0x08, 0)

    def test_point_reports_minus_one_and_zero(self):
        self.assertEqual(self.graphics.point(10, 10), 0)
        self.graphics.set(10, 10)
        self.assertEqual(self.graphics.point(10, 10), -1)
        self.graphics.reset(10, 10)
        self.assertEqual(self.graphics.point(10, 10), 0)

    def test_graphics_and_text_share_one_memory(self):
        self.video.write_cell(0, 0, ord("A"))
        self.graphics.set(0, 0)
        cell = self.memory.read(mm.VRAM_BASE)
        self.assertTrue(cell & mm.SEMIGRAPHICS_FLAG)
        self.assertEqual(cell & mm.SEMIGRAPHICS_BLOCK_MASK, 0x01)

    def test_coordinates_are_checked(self):
        for x, y in ((-1, 0), (128, 0), (0, 48), (0, -1)):
            with self.subTest(point=(x, y)):
                with self.assertRaises(BasicError) as caught:
                    self.graphics.set(x, y)
                self.assertEqual(caught.exception.code, "FC")

    def test_the_whole_graphics_field_is_addressable(self):
        self.graphics.set(127, 47)
        rows = self.video.pixel_rows()
        self.assertEqual(len(rows), 48)
        self.assertEqual(len(rows[0]), 128)
        self.assertEqual(rows[47][127], "#")


class PrintEngineTest(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.video = VideoEngine(self.memory)
        self.printer = PrintEngine(self.video)

    def test_level_two_number_format(self):
        self.assertEqual(self.printer.format_number(5), " 5 ")
        self.assertEqual(self.printer.format_number(-5), "-5 ")
        self.assertEqual(self.printer.format_number(0), " 0 ")

    def test_comma_moves_to_the_next_print_zone(self):
        self.printer.put_text("AB")
        self.printer.next_zone()
        self.assertEqual(self.video.cursor_column, 16)
        self.printer.next_zone()
        self.assertEqual(self.video.cursor_column, 32)

    def test_print_at_positions_the_cursor(self):
        self.printer.print_at(64 * 2 + 5)
        self.assertEqual((self.video.cursor_row, self.video.cursor_column), (2, 5))


if __name__ == "__main__":
    unittest.main()
