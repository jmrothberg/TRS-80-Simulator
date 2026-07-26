"""The processor's architectural registers.

These are the boxes drawn inside the PROGRAM CONTROL UNIT on the architecture
diagram plus the working registers the microcode operates on.  Keeping them in
one object (rather than as attributes scattered over the engines) is what lets a
test dump the whole processor state, and is what the hardware model will mirror
as real registers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .values import Value


@dataclass
class Registers:
    # -- Program Control Unit ---------------------------------------------
    line_address: int = 0  # record being executed, 0 = direct statement buffer
    line_number: int = 0  # its BASIC line number, 0 in direct mode
    token_pointer: int = 0  # absolute address of the next token

    # -- microcode working registers --------------------------------------
    accumulator: Value = field(default_factory=lambda: Value.of_integer(0))
    address: int = 0  # ADDR: a variable slot, a line record, ...
    temporary: int = 0  # TMP: a flag or a spare operand
    condition: bool = False  # COND: set by TEST, read by the branch micro-ops
    name0: int = 0  # the variable name a statement is working on
    name1: int = 0
    scratch: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    # -- sequencer state ---------------------------------------------------
    micro_pc: int = 0
    statement_entry: int = 0  # where the current statement's microcode began
    statement_pointer: int = 0  # token pointer when it began (for INPUT redo)
    branched: bool = False  # a control transfer happened in this statement
    stalled: bool = False  # mid-statement, waiting on the console
    running: bool = False  # a program is executing (as opposed to direct mode)

    def snapshot(self) -> dict:
        """Every register, for tests and the monitor."""
        return {
            "line_address": self.line_address,
            "line_number": self.line_number,
            "token_pointer": self.token_pointer,
            "accumulator": self.accumulator,
            "address": self.address,
            "temporary": self.temporary,
            "condition": self.condition,
            "name": (self.name0, self.name1),
            "scratch": list(self.scratch),
            "micro_pc": self.micro_pc,
            "branched": self.branched,
            "stalled": self.stalled,
            "running": self.running,
        }
