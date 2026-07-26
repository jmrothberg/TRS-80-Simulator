"""Program Memory: line records, the directory and editing."""

from __future__ import annotations

import unittest

import support  # noqa: F401

from functional_model import memory_map as mm
from functional_model.errors import BasicError
from functional_model.memory import Memory
from functional_model.program_memory import ProgramMemory
from functional_model.tokenizer import Tokenizer


class ProgramMemoryTest(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.program = ProgramMemory(self.memory)
        self.tokenizer = Tokenizer()

    def store(self, source: str) -> None:
        line = self.tokenizer.tokenize(source)
        self.program.store(line.line_number, line.token_bytes)

    def numbers(self) -> list[int]:
        return [record.number for record in self.program.lines()]

    def test_a_new_program_is_empty(self):
        self.assertTrue(self.program.is_empty)
        self.assertEqual(self.memory.program_end, mm.PROGRAM_BASE)

    def test_record_layout_matches_the_map(self):
        self.store("10 PRINT 1")
        record = self.program.find(10)
        self.assertEqual(record.address, mm.PROGRAM_BASE)
        self.assertEqual(self.memory.read_word(record.address), 10)
        self.assertEqual(self.memory.read(record.address + 2), record.length)
        self.assertEqual(record.tokens_address, record.address + mm.LINE_HEADER_SIZE)
        self.assertEqual(self.memory.read(record.next_address - 1), 0x00)

    def test_lines_are_kept_in_ascending_order(self):
        for source in ("30 PRINT 3", "10 PRINT 1", "20 PRINT 2"):
            self.store(source)
        self.assertEqual(self.numbers(), [10, 20, 30])

    def test_replacing_a_line_keeps_the_order(self):
        for source in ("10 PRINT 1", "20 PRINT 2", "30 PRINT 3"):
            self.store(source)
        self.store("20 PRINT 22222")
        self.assertEqual(self.numbers(), [10, 20, 30])
        record = self.program.find(20)
        self.assertIn(b"\x02", self.program.tokens_of(record)[:1] + b"\x02")

    def test_replacing_a_line_moves_the_tail_correctly(self):
        for source in ("10 PRINT 1", "20 PRINT 2", "30 PRINT 3"):
            self.store(source)
        self.store("20 REM a much longer line than before")
        self.assertEqual(self.numbers(), [10, 20, 30])
        third = self.program.find(30)
        self.assertEqual(self.memory.read(third.next_address - 1), 0x00)

    def test_an_empty_line_deletes(self):
        for source in ("10 PRINT 1", "20 PRINT 2"):
            self.store(source)
        self.store("10")
        self.assertEqual(self.numbers(), [20])

    def test_deleting_an_absent_line_is_harmless(self):
        self.store("10 PRINT 1")
        self.assertFalse(self.program.delete(999))
        self.assertEqual(self.numbers(), [10])

    def test_find_stops_at_the_first_larger_line(self):
        for source in ("10 PRINT 1", "30 PRINT 3"):
            self.store(source)
        self.assertIsNone(self.program.find(20))

    def test_bytes_used_tracks_the_records(self):
        self.store("10 PRINT 1")
        record = self.program.find(10)
        self.assertEqual(self.program.bytes_used, record.total_size)
        self.assertEqual(self.program.bytes_free, mm.PROGRAM_SIZE - record.total_size)

    def test_running_out_of_program_memory_is_reported(self):
        line = self.tokenizer.tokenize("10 REM " + "x" * 200)
        number = 10
        with self.assertRaises(BasicError) as caught:
            while number < 60000:
                self.program.store(number, line.token_bytes)
                number += 1
        self.assertEqual(caught.exception.code, "OM")

    def test_clear_forgets_everything(self):
        self.store("10 PRINT 1")
        self.program.clear()
        self.assertTrue(self.program.is_empty)
        self.assertEqual(self.numbers(), [])


if __name__ == "__main__":
    unittest.main()
