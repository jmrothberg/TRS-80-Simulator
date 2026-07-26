"""Whole-application regression tests.

Constitution, TESTING:

    Do not generate random programs.
    Instead: use AI to create complete BASIC applications.
    Every accepted program becomes a permanent regression test.

Each `programs/NAME.bas` is typed into a fresh machine, run, and its screen
compared with `programs/NAME.out`.  Accepting a new program is two steps: add
the .bas, then record its output with

    python3 tests/record_program.py NAME

which only writes the file after you have read the output and agreed with it.
"""

from __future__ import annotations

import unittest

import support
from support import PROGRAM_DIRECTORY, run_program


def load_cases():
    return sorted(PROGRAM_DIRECTORY.glob("*.bas"))


class ProgramTest(unittest.TestCase):
    def test_at_least_one_program_is_registered(self):
        self.assertTrue(load_cases())

    def test_every_program_has_a_recorded_output(self):
        for source in load_cases():
            with self.subTest(program=source.name):
                self.assertTrue(
                    source.with_suffix(".out").exists(),
                    f"{source.name} has no recorded output; run tests/record_program.py",
                )

    def test_programs_produce_their_recorded_output(self):
        for source in load_cases():
            expected_file = source.with_suffix(".out")
            if not expected_file.exists():
                continue
            with self.subTest(program=source.name):
                actual = run_program(source.read_text())
                expected = expected_file.read_text().rstrip("\n")
                self.assertEqual(actual, expected)

    def test_programs_are_repeatable(self):
        """The machine is deterministic, RND included."""
        for source in load_cases():
            with self.subTest(program=source.name):
                text = source.read_text()
                self.assertEqual(run_program(text), run_program(text))


if __name__ == "__main__":
    unittest.main()
