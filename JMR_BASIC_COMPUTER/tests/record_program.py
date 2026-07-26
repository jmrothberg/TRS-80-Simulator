"""Record the expected output of a regression program.

    python3 tests/record_program.py primes          # show the output
    python3 tests/record_program.py primes --accept # and save it as .out

Look at the output before accepting it.  The Constitution says every accepted
program becomes a permanent regression test, which only means anything if a
human agreed with the output first.
"""

from __future__ import annotations

import sys

from support import PROGRAM_DIRECTORY, run_program


def main(argv: list[str]) -> int:
    if not argv:
        names = sorted(path.stem for path in PROGRAM_DIRECTORY.glob("*.bas"))
        print("usage: record_program.py NAME [--accept]")
        print("programs:", ", ".join(names))
        return 1

    name = argv[0]
    accept = "--accept" in argv[1:]
    source_file = PROGRAM_DIRECTORY / f"{name}.bas"
    if not source_file.exists():
        print(f"no such program: {source_file}")
        return 1

    output = run_program(source_file.read_text())
    print(f"--- {name} ---")
    print(output)
    print("--- end ---")

    if accept:
        source_file.with_suffix(".out").write_text(output + "\n")
        print(f"recorded {source_file.with_suffix('.out').name}")
    else:
        print("(not saved; pass --accept to record this as the expected output)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
