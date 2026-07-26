"""Memory map, flat memory and the memory-backed stacks."""

from __future__ import annotations

import unittest

import support  # noqa: F401  (puts the package on sys.path)

from functional_model import memory_map as mm
from functional_model.memory import Memory, MemoryStack, StackOverflow, StackUnderflow


class MemoryMapTest(unittest.TestCase):
    def test_regions_do_not_overlap_and_cover_the_space(self):
        expected_base = 0
        for name, base, top in mm.REGIONS:
            self.assertEqual(base, expected_base, f"{name} does not follow the previous region")
            self.assertLess(base, top)
            expected_base = top + 1
        self.assertEqual(expected_base, mm.ADDRESS_SPACE)

    def test_sub_regions_stay_inside_their_region(self):
        self.assertTrue(mm.STACK_BASE <= mm.EXPR_OPERAND_STACK_BASE < mm.STACK_TOP)
        self.assertTrue(mm.STACK_BASE <= mm.EXPR_OPERATOR_STACK_BASE < mm.STACK_TOP)
        self.assertTrue(mm.STACK_BASE <= mm.FOR_STACK_BASE < mm.STACK_TOP)
        self.assertTrue(mm.STACK_BASE <= mm.GOSUB_STACK_BASE < mm.STACK_TOP)
        self.assertTrue(mm.WORK_RAM_BASE <= mm.SYSVAR_BASE <= mm.WORK_RAM_TOP)
        self.assertTrue(mm.IO_BASE <= mm.IO_UART_TX_DATA <= mm.IO_TOP)

    def test_stacks_fit_inside_the_stack_area(self):
        for base, size, depth in (
            (mm.EXPR_OPERAND_STACK_BASE, mm.EXPR_OPERAND_SLOT_SIZE, mm.EXPR_OPERAND_DEPTH),
            (mm.EXPR_OPERATOR_STACK_BASE, mm.EXPR_OPERATOR_SLOT_SIZE, mm.EXPR_OPERATOR_DEPTH),
            (mm.FOR_STACK_BASE, mm.FOR_FRAME_SIZE, mm.FOR_STACK_DEPTH),
            (mm.GOSUB_STACK_BASE, mm.GOSUB_FRAME_SIZE, mm.GOSUB_STACK_DEPTH),
        ):
            self.assertLessEqual(base + size * depth - 1, mm.STACK_TOP)

    def test_video_memory_is_exactly_the_screen(self):
        self.assertEqual(mm.VRAM_SIZE, 64 * 16)
        self.assertEqual(mm.VRAM_TOP - mm.VRAM_BASE + 1, mm.VRAM_SIZE)

    def test_vram_address_matches_the_architecture_diagram(self):
        # VRAM Address = (cell_row * 64 + cell_col)
        self.assertEqual(mm.vram_address(0, 0), mm.VRAM_BASE)
        self.assertEqual(mm.vram_address(15, 63), mm.VRAM_BASE + 1023)
        self.assertEqual(mm.vram_address(2, 3), mm.VRAM_BASE + 131)

    def test_region_of(self):
        self.assertEqual(mm.region_of(mm.PROGRAM_BASE), "Program Memory")
        self.assertEqual(mm.region_of(mm.VRAM_BASE + 5), "Video Memory")
        self.assertEqual(mm.region_of(0xFFFF), "Reserved")


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()

    def test_bytes_wrap_to_eight_bits(self):
        self.memory.write(0x2000, 0x1FF)
        self.assertEqual(self.memory.read(0x2000), 0xFF)

    def test_words_are_little_endian(self):
        self.memory.write_word(0x2000, 0x1234)
        self.assertEqual(self.memory.read(0x2000), 0x34)
        self.assertEqual(self.memory.read(0x2001), 0x12)
        self.assertEqual(self.memory.read_word(0x2000), 0x1234)

    def test_signed_words_round_trip(self):
        for value in (-32768, -1, 0, 1, 32767):
            self.memory.write_signed_word(0x2000, value)
            self.assertEqual(self.memory.read_signed_word(0x2000), value)

    def test_overlapping_move_keeps_the_data(self):
        self.memory.write_block(0x2000, b"ABCDEF")
        self.memory.move_block(0x2000, 0x2002, 6)
        self.assertEqual(self.memory.read_block(0x2002, 6), b"ABCDEF")

    def test_program_end_pointer_lives_in_memory(self):
        self.memory.program_end = 0x2345
        self.assertEqual(self.memory.read_word(mm.SYSVAR_PROGRAM_END), 0x2345)


class MemoryStackTest(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.stack = MemoryStack(self.memory, mm.FOR_STACK_BASE, 4, 3, "test stack")

    def test_frames_are_where_the_map_says(self):
        first = self.stack.push_frame()
        second = self.stack.push_frame()
        self.assertEqual(first, mm.FOR_STACK_BASE)
        self.assertEqual(second, mm.FOR_STACK_BASE + 4)

    def test_push_pop_is_last_in_first_out(self):
        self.stack.push_frame()
        second = self.stack.push_frame()
        self.assertEqual(self.stack.top_frame(), second)
        self.assertEqual(self.stack.pop_frame(), second)
        self.assertEqual(self.stack.pointer, 1)

    def test_depth_is_enforced(self):
        for _ in range(3):
            self.stack.push_frame()
        with self.assertRaises(StackOverflow):
            self.stack.push_frame()

    def test_underflow_is_reported(self):
        with self.assertRaises(StackUnderflow):
            self.stack.pop_frame()


if __name__ == "__main__":
    unittest.main()
