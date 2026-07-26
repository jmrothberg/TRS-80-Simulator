# JMR BASIC Computer

An original computer whose **native machine language is BASIC**. There is no
Z80, no 6502, no hidden CPU running an interpreter: BASIC tokens *are* the
instruction set, a dispatch table decodes them, and microcode drives independent
hardware engines.

It is heading for a Digilent Nexys A7-100T. It starts, as the
[Constitution](CONSTITUTION.md) requires, in Python.

```
$ python3 run_jmr.py
+----------------------------------------------------------------+
|JMR LEVEL II BASIC                                              |
|READY                                                           |
|>10 PRINT "HELLO"                                               |
|>RUN                                                            |
|HELLO                                                           |
|READY                                                           |
|>                                                               |
```

**[CONSTITUTION.md](CONSTITUTION.md) is the specification.** If the code and
the Constitution disagree, the code is wrong.

---

## Running it

No dependencies beyond Python 3.11.

```bash
python3 run_jmr.py                                  # interactive
python3 run_jmr.py --script tests/programs/primes.bas --run
python3 run_jmr.py --microcode                      # dump the ROM and dispatch table
python3 -m unittest discover -s tests -p "test_*.py"  # the full suite
```

In the interactive terminal, Ctrl-C breaks a running program (and quits when
nothing is running); Ctrl-\ always quits.

Or drive the machine from Python — every internal register and memory cell is
readable:

```python
from functional_model import Machine

machine = Machine()
machine.boot()
machine.type_line('10 FOR I=1 TO 3: PRINT I;: NEXT')
machine.type_line('RUN')
print(machine.screen_text())        #  1  2  3
print(machine.state()['registers']) # every processor register
```

## What is here

```
CONSTITUTION.md          the specification; this document is correct
docs/
  architecture.png       the architecture diagram
  ARCHITECTURE.md        how the diagram maps onto the code
  MEMORY_MAP.md          every region and every address
  TOKENS.md              the architectural instruction set
  MICROCODE.md           the micro-instruction set and how routines are written
  ROADMAP.md             implementation order, what is done, what is next
functional_model/        the Python Functional Model (behavioral truth)
  memory_map.py          the only file allowed to contain an address literal
  memory.py              64K address space and the memory-backed stacks
  tokens.py              one opcode per BASIC token
  tokenizer.py           source text -> token stream, and back for LIST
  program_memory.py      line records and the line directory
  registers.py           the processor's architectural registers
  token_stream.py        reading tokens through the Token Pointer
  microcode.py           the micro-instruction set, assembler and ROM
  sequencer.py           Program Control Unit + Micro Sequencer
  console.py             keyboard interpreter, line editor, command detector
  uart.py                the phase 1 host link
  machine.py             the wiring diagram
  engines/               one module per engine, as the Constitution requires
run_jmr.py               the host front end (not part of the computer)
tests/                   subsystem tests plus whole-application regressions
tools/gen_tokens.py      regenerates docs/TOKENS.md from the opcode table
storage/                 where SAVE and LOAD put files
```

## How it executes a statement

`PRINT A+5`, end to end:

1. **Tokenizer** turns the text into `81 0D 41 00 8E 01 05 00 00` once, when the
   line is typed. The processor never sees text again.
2. **Program Control Unit** fetches the token at the Token Pointer: `0x81`.
3. **Dispatch table** turns `0x81` into a microcode entry address.
4. **Micro Sequencer** runs the PRINT routine: `EVAL` (the shared Expression
   Engine reads `A+5` off the token stream using two stacks in the Stack Area),
   `PRINT_VALUE` (Print Engine converts to characters, Video Engine writes them
   to Video RAM), `PRINT_SEP`, `PRINT_NL`, `END_STMT`.
5. Control returns to the PCU, which moves to the next statement.

`python3 run_jmr.py --microcode` prints the whole ROM with that routine in it.

## Status

Implementation order steps 1–16 are done at stage-1 (16-bit signed integer)
level: UART, Video, Console, Tokenizer, Program RAM, LIST, RUN, integer
expressions, variables, IF, GOTO, GOSUB, FOR/NEXT, graphics, SAVE and LOAD, plus
INPUT, READ/DATA/RESTORE, PEEK/POKE and PRINT@.

Steps 17–20 (strings, arrays, floating point, USB keyboard) are **not** done.
They are not stubbed out silently: `A$` and `1.5` are syntax errors and `DIM`
reports `?FC ERROR`, so nothing quietly pretends to work. See
[docs/ROADMAP.md](docs/ROADMAP.md).

## Adding a regression test

The Constitution says every accepted BASIC application becomes a permanent
regression test.

```bash
vi tests/programs/mygame.bas
python3 tests/record_program.py mygame            # look at the output
python3 tests/record_program.py mygame --accept   # then record it
```
