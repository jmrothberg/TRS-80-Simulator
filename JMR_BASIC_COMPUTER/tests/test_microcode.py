"""Microcode ROM, dispatch table and the micro sequencer.

Constitution, BASIC TOKENS:

    Every token has: one opcode, one dispatch table entry, one implementation.

These tests hold the machine to that.
"""

from __future__ import annotations

import unittest

import support
from support import new_machine

from functional_model import tokens as tk
from functional_model.microcode import (
    MICROCODE_BASE,
    MicroOp,
    MicrocodeAssembler,
    build_microcode,
    listing,
)
from functional_model.sequencer import MicroSequencer


class DispatchTableTest(unittest.TestCase):
    def setUp(self):
        self.rom, self.dispatch = build_microcode()

    def test_every_statement_token_has_a_dispatch_entry(self):
        for token in tk.STATEMENT_TOKENS:
            with self.subTest(token=tk.SPELLING.get(token, hex(token))):
                self.assertIn(token, self.dispatch)

    def test_every_dispatch_entry_points_into_the_rom(self):
        for token, address in self.dispatch.items():
            with self.subTest(token=tk.SPELLING.get(token, hex(token))):
                self.assertIn(address, self.rom)

    def test_entries_start_where_the_diagram_says_microcode_lives(self):
        for address in self.dispatch.values():
            self.assertGreaterEqual(address, MICROCODE_BASE)

    def test_every_routine_ends_in_a_terminator(self):
        """No routine may run off the end of the ROM."""
        terminators = {MicroOp.END_STMT, MicroOp.NEXT_STATEMENT, MicroOp.HALT}
        for token, entry in self.dispatch.items():
            with self.subTest(token=tk.SPELLING.get(token, hex(token))):
                self.assertTrue(self._reaches_terminator(entry, terminators))

    def _reaches_terminator(self, entry: int, terminators: set[str]) -> bool:
        """Walk every reachable path; a routine is correct if all of them stop."""
        seen = set()
        pending = [entry]
        while pending:
            address = pending.pop()
            if address in seen:
                continue
            seen.add(address)
            instruction = self.rom.get(address)
            if instruction is None:
                return False
            if instruction.op in terminators:
                continue
            if instruction.op == MicroOp.JUMP:
                pending.append(instruction.arg)
                continue
            if instruction.op in (MicroOp.BRANCH_IF, MicroOp.BRANCH_IF_NOT):
                pending.append(instruction.arg)
            pending.append(address + 1)
        return True

    def test_branch_targets_are_resolved_addresses(self):
        for instruction in self.rom.values():
            if instruction.op in (MicroOp.JUMP, MicroOp.BRANCH_IF, MicroOp.BRANCH_IF_NOT):
                self.assertIsInstance(instruction.arg, int)
                self.assertIn(instruction.arg, self.rom)

    def test_the_listing_is_readable(self):
        text = listing(self.rom, self.dispatch)
        self.assertIn("PRINT:", text)
        self.assertIn("EVAL", text)


class AssemblerTest(unittest.TestCase):
    def test_labels_resolve(self):
        asm = MicrocodeAssembler(base=0x0100)
        asm.entry(tk.T_CLS)
        asm.emit(MicroOp.JUMP, "target")
        asm.emit(MicroOp.NOP)
        asm.label("target")
        asm.emit(MicroOp.END_STMT)
        rom, dispatch = asm.build()
        self.assertEqual(dispatch[tk.T_CLS], 0x0100)
        self.assertEqual(rom[0x0100].arg, 0x0102)

    def test_an_undefined_label_is_a_build_error(self):
        asm = MicrocodeAssembler()
        asm.emit(MicroOp.JUMP, "nowhere")
        with self.assertRaises(ValueError):
            asm.build()

    def test_a_token_cannot_have_two_entries(self):
        asm = MicrocodeAssembler()
        asm.entry(tk.T_CLS)
        with self.assertRaises(ValueError):
            asm.entry(tk.T_CLS)


class SequencerTest(unittest.TestCase):
    def test_every_micro_op_has_an_implementation(self):
        machine = new_machine()
        sequencer = MicroSequencer(machine)
        declared = {
            value
            for name, value in vars(MicroOp).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        self.assertEqual(declared, set(sequencer.handlers))

    def test_every_micro_op_in_the_rom_is_implemented(self):
        machine = new_machine()
        used = {instruction.op for instruction in machine.microcode_rom.values()}
        self.assertTrue(used.issubset(set(machine.pcu.sequencer.handlers)))

    def test_the_registers_are_visible(self):
        machine = new_machine()
        machine.type_line("10 PRINT 1")
        state = machine.state()
        self.assertIn("micro_pc", state["registers"])
        self.assertIn("token_pointer", state["registers"])
        self.assertGreater(state["program_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
