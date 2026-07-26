#!/usr/bin/env python3
"""Host front end for the JMR BASIC Computer.

Phase 1 of the Constitution's KEYBOARD section:

    Mac keyboard -> UART -> Console

This program is the *host*, not the computer.  All it does is push bytes into
the UART and draw Video RAM on the terminal.  Everything else happens inside
`functional_model`.

    python3 run_jmr.py                 interactive
    python3 run_jmr.py --script F.bas  type a file in, then show the screen
    python3 run_jmr.py --microcode     dump the microcode ROM and dispatch table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from functional_model import Machine  # noqa: E402
from functional_model.machine import dispatch_table_listing  # noqa: E402
from functional_model.microcode import listing  # noqa: E402
from functional_model.sequencer import Status  # noqa: E402

# One slice of a running program before the host gets a look in.  It only
# affects responsiveness, never results.
SLICE = 500

CLEAR_SCREEN = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def render(machine: Machine) -> str:
    lines = machine.video.text_lines("sextant")
    top = "+" + "-" * 64 + "+"
    body = "\n".join(f"|{line}|" for line in lines)
    return f"{top}\n{body}\n{top}"


def draw(machine: Machine) -> None:
    sys.stdout.write(CLEAR_SCREEN + render(machine) + "\n")
    sys.stdout.flush()


def interactive(machine: Machine) -> int:
    """Raw-mode terminal when we have one, line mode otherwise."""
    try:
        import termios
        import tty

        raw_available = sys.stdin.isatty()
    except ImportError:  # pragma: no cover - non-POSIX host
        raw_available = False

    if not raw_available:
        return line_mode(machine)

    settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        sys.stdout.write(HIDE_CURSOR)
        draw(machine)
        while True:
            if machine.pcu.status is Status.RUNNING:
                machine.tick()
                draw(machine)
                continue
            char = sys.stdin.read(1)
            if not char:
                return 0
            code = ord(char)
            if code == 0x03:  # Ctrl-C: BREAK, or quit when nothing is running
                if machine.pcu.status is Status.RUNNING:
                    machine.request_break()
                    continue
                return 0
            if code == 0x1C:  # Ctrl-\ always quits
                return 0
            machine.receive(char)
            machine.tick()
            draw(machine)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        sys.stdout.write(SHOW_CURSOR + "\n")
        sys.stdout.flush()


def line_mode(machine: Machine) -> int:
    """Fallback for a pipe or a terminal we cannot put into raw mode."""
    draw(machine)
    while True:
        try:
            line = input()
        except EOFError:
            return 0
        machine.type_line(line)
        while machine.pcu.status is Status.RUNNING:
            machine.tick()
        draw(machine)


def run_script(machine: Machine, path: Path, then_run: bool) -> int:
    for line in path.read_text().splitlines():
        if line.strip():
            machine.type_line(line)
    if then_run:
        machine.type_line("RUN")
        while machine.pcu.status is Status.RUNNING:
            machine.tick()
    print(render(machine))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, help="type a file in, then show the screen")
    parser.add_argument("--run", action="store_true", help="RUN the script after typing it")
    parser.add_argument("--microcode", action="store_true", help="dump the microcode ROM")
    parser.add_argument("--storage", type=Path, help="directory SAVE and LOAD use")
    arguments = parser.parse_args(argv)

    if arguments.microcode:
        machine = Machine()
        print("DISPATCH TABLE (token -> microcode entry address)")
        print(dispatch_table_listing(machine))
        print()
        print("MICROCODE ROM")
        print(listing(machine.microcode_rom, machine.dispatch))
        return 0

    backend = None
    if arguments.storage:
        from functional_model.engines.storage_engine import HostFileBackend

        backend = HostFileBackend(arguments.storage)

    machine = Machine(backend)
    machine.statement_limit = SLICE
    machine.boot()

    if arguments.script:
        return run_script(machine, arguments.script, arguments.run)
    return interactive(machine)


if __name__ == "__main__":
    raise SystemExit(main())
