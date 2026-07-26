"""Tokenizer: source text in, architectural instruction stream out."""

from __future__ import annotations

import unittest

import support  # noqa: F401

from functional_model import tokens as tk
from functional_model.errors import BasicError
from functional_model.tokenizer import Tokenizer, detokenize


class TokenEncodingTest(unittest.TestCase):
    def setUp(self):
        self.tokenizer = Tokenizer()

    def test_the_example_from_the_architecture_diagram(self):
        # BASIC TOKEN STRUCTURE panel: PRINT A+5
        line = self.tokenizer.tokenize("10 PRINT A+5")
        self.assertEqual(line.line_number, 10)
        self.assertEqual(
            list(line.token_bytes),
            [
                0x81,  # PRINT
                0x0D, ord("A"), 0x00,  # variable A
                0x8E,  # plus
                0x01, 0x05, 0x00,  # integer 5
                0x00,  # end of statement
            ],
        )

    def test_opcodes_pinned_by_the_diagram(self):
        self.assertEqual(tk.T_PRINT, 0x81)
        self.assertEqual(tk.T_PLUS, 0x8E)
        self.assertEqual(tk.T_VARIABLE, 0x0D)
        self.assertEqual(tk.T_INTEGER, 0x01)
        self.assertEqual(tk.T_EOS, 0x00)

    def test_every_token_has_exactly_one_opcode(self):
        opcodes = [tk.KEYWORDS[name] for name in tk.KEYWORDS]
        # Aliases are allowed (? for PRINT), but no opcode may mean two things.
        for opcode in set(opcodes):
            spellings = {name for name, code in tk.KEYWORDS.items() if code == opcode}
            self.assertTrue(spellings)

    def test_line_number_is_optional(self):
        self.assertIsNone(self.tokenizer.tokenize("PRINT 1").line_number)
        self.assertTrue(self.tokenizer.tokenize("PRINT 1").token_bytes.endswith(b"\x00"))

    def test_a_bare_line_number_deletes(self):
        line = self.tokenizer.tokenize("10")
        self.assertEqual(line.line_number, 10)
        self.assertTrue(line.is_empty)

    def test_whitespace_is_not_significant(self):
        packed = self.tokenizer.tokenize("10 PRINT A+5").token_bytes
        spaced = self.tokenizer.tokenize("10   PRINT   A + 5").token_bytes
        self.assertEqual(packed, spaced)

    def test_case_is_folded(self):
        self.assertEqual(
            self.tokenizer.tokenize("10 print a").token_bytes,
            self.tokenizer.tokenize("10 PRINT A").token_bytes,
        )

    def test_string_literal_carries_its_length(self):
        body = self.tokenizer.tokenize('PRINT "HI"').token_bytes
        self.assertEqual(list(body[1:5]), [tk.T_STRING, 2, ord("H"), ord("I")])

    def test_two_character_operators_win_over_one(self):
        body = self.tokenizer.tokenize("IF A<=B THEN 10").token_bytes
        self.assertIn(tk.T_LESS_EQUAL, body)
        self.assertNotIn(tk.T_LESS, body)

    def test_question_mark_is_print(self):
        self.assertEqual(
            self.tokenizer.tokenize("? 1").token_bytes,
            self.tokenizer.tokenize("PRINT 1").token_bytes,
        )

    def test_only_two_characters_of_a_name_are_significant(self):
        long_name = self.tokenizer.tokenize("COUNT=1").token_bytes
        short_name = self.tokenizer.tokenize("CO=1").token_bytes
        self.assertEqual(long_name, short_name)

    def test_rem_keeps_its_text(self):
        line = self.tokenizer.tokenize("10 REM this is a note")
        self.assertEqual(detokenize(line.token_bytes), "REM this is a note")

    def test_floating_point_is_rejected_until_stage_three(self):
        with self.assertRaises(BasicError):
            self.tokenizer.tokenize("A=1.5")

    def test_string_variables_are_rejected_until_step_seventeen(self):
        with self.assertRaises(BasicError):
            self.tokenizer.tokenize('A$="X"')

    def test_integer_constants_are_range_checked(self):
        with self.assertRaises(BasicError):
            self.tokenizer.tokenize("A=70000")

    def test_addresses_above_32767_are_written_the_natural_way(self):
        # POKE 45056,42 must be typeable: the literal is stored as its 16-bit
        # pattern, which is what the address bus wants.
        line = self.tokenizer.tokenize("POKE 45056,42")
        self.assertEqual(list(line.token_bytes[1:4]), [tk.T_INTEGER, 0x00, 0xB0])


class DetokenizeTest(unittest.TestCase):
    def setUp(self):
        self.tokenizer = Tokenizer()

    def round_trip(self, source: str) -> str:
        return detokenize(self.tokenizer.tokenize(source).token_bytes)

    def test_listing_is_readable_and_retokenizes(self):
        for source, expected in (
            ('PRINT "HELLO"', 'PRINT"HELLO"'),
            ("FOR I=1 TO 10 STEP 2", "FOR I=1 TO 10 STEP 2"),
            ("IF A>B THEN 100", "IF A>B THEN 100"),
            ("PRINT A;B,C", "PRINT A;B,C"),
            ("SET(X,Y)", "SET(X,Y)"),
            ("A=-5", "A=-5"),
        ):
            with self.subTest(source=source):
                listed = self.round_trip(source)
                self.assertEqual(listed, expected)
                # A listing must tokenize back to the same program.
                self.assertEqual(
                    self.tokenizer.tokenize(listed).token_bytes,
                    self.tokenizer.tokenize(source).token_bytes,
                )


if __name__ == "__main__":
    unittest.main()
