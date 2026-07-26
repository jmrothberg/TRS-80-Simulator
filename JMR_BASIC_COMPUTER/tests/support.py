"""Shared helpers for the regression tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from functional_model import Machine  # noqa: E402
from functional_model.engines.storage_engine import MemoryBackend  # noqa: E402

PROGRAM_DIRECTORY = Path(__file__).resolve().parent / "programs"


def new_machine() -> Machine:
    """A booted machine with an in-memory storage device."""
    machine = Machine(MemoryBackend())
    machine.boot()
    return machine


def enter(machine: Machine, source: str) -> Machine:
    """Type a program in, one line at a time, as a user would."""
    for line in source.strip().splitlines():
        line = line.strip()
        if line:
            machine.type_line(line)
    return machine


def output_of(machine: Machine) -> str:
    """The screen with the trailing READY prompt removed."""
    text = machine.screen_text()
    for tail in ("\nREADY\n>", "READY\n>", "\nREADY", ">"):
        if text.endswith(tail):
            text = text[: -len(tail)]
            break
    return text.rstrip()


def evaluate(expression: str, machine: Machine | None = None):
    """Run one expression through the Expression Engine and return its Value.

    The text is tokenized behind a PRINT so that an expression starting with a
    digit is not mistaken for a line number, then the PRINT token is stepped
    over before the engine is started.
    """
    machine = machine or new_machine()
    tokenized = machine.tokenizer.tokenize("PRINT " + expression)
    machine._load_direct_statement(tokenized.token_bytes)
    machine.stream.next_token()  # step over PRINT
    return machine.expression.evaluate()


def run_program(source: str, input_lines: list[str] | None = None) -> str:
    """Type a program, clear the screen, RUN it and return what it printed.

    `CLS:RUN` is one direct statement, so the echoed command scrolls away with
    the rest of the screen and the output starts at the top left.
    """
    machine = enter(new_machine(), source)
    machine.type_line("CLS:RUN")
    for line in input_lines or []:
        machine.type_line(line)
    return output_of(machine)
