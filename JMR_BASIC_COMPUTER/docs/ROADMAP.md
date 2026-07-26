# Roadmap

The Constitution fixes both the development order and the implementation order.
Neither may be skipped. This document records where the project actually is.

## Development order

```
Architecture            done: CONSTITUTION.md + docs/architecture.png
   |
Python Functional Model  <-- we are here
   |
Python Hardware Model
   |
SystemVerilog
   |
Simulation
   |
FPGA
   |
Optimization
```

The Functional Model is the behavioral truth. The Hardware Model does not start
until the language is complete enough that its behavior is settled, because
every difference between the two models later becomes a difference between the
model and the board.

## Implementation order

| # | Step | State | Where |
|---|---|---|---|
| 1 | UART | done | `uart.py` |
| 2 | Video | done | `engines/video_engine.py` |
| 3 | Console | done | `console.py` |
| 4 | Tokenizer | done | `tokenizer.py` |
| 5 | Program RAM | done | `program_memory.py` |
| 6 | LIST | done | microcode `list`, `machine.list_program` |
| 7 | RUN | done | microcode `run`, `machine.start_program` |
| 8 | Integer Expressions | done | `engines/expression_engine.py` |
| 9 | Variables | done | `engines/variable_engine.py` |
| 10 | IF | done | microcode `if` |
| 11 | GOTO | done | microcode `goto` |
| 12 | GOSUB | done | microcode `gosub` / `return` |
| 13 | FOR/NEXT | done | microcode `for` / `next`, `engines/flow_engine.py` |
| 14 | Graphics | done | `engines/graphics_engine.py` |
| 15 | SAVE | done | `engines/storage_engine.py` |
| 16 | LOAD | done | `engines/storage_engine.py` |
| 17 | Strings | **next** | `engines/string_engine.py` (literals only today) |
| 18 | Arrays | not started | `engines/array_engine.py` (interface only) |
| 19 | Floating Point | not started | stage 3 |
| 20 | USB Keyboard | not started | phase 2 keyboard source |

Beyond the numbered list, this milestone also implements `INPUT`,
`READ`/`DATA`/`RESTORE`, `PEEK`/`POKE`, `PRINT@`, `REM`, `END`/`STOP`, `NEW`,
`CLS` and BREAK, because a machine that can only do the numbered steps cannot
run a real program.

## What is deliberately missing, and how it fails

Nothing unfinished pretends to work. A programmer meets a clear error, not a
wrong answer:

| Feature | Today | Arrives at |
|---|---|---|
| `A$`, string variables | `?SN ERROR` at tokenize time | step 17 |
| String concatenation, `LEN`, `CHR$`, `MID$` | not in the keyword table | step 17 |
| `DIM A(10)`, `A(I)` | `?FC ERROR` | step 18 |
| `1.5`, real arithmetic | `?SN ERROR` at tokenize time | step 19 |
| `RND(0)` | `?FC ERROR` (it returns a fraction) | step 19 |
| Values outside -32768..32767 | `?OV ERROR` | step 19 |
| `ON ... GOTO`, `DEF FN`, `ELSE` | not in the keyword table | after the above |

One smaller known difference:

* `GOTO`, `GOSUB` and `THEN` accept a full expression where Level II requires a
  literal line number, so `GOSUB A` works here and would not on a real machine.
  This is a superset: no valid Level II program is affected. `LIST` is the
  exception and takes literals, because `LIST 20-30` is a range and not a
  subtraction.

## Next milestone: strings

The work, in order:

1. String descriptors in Variable Memory (`[name0][name1][length][ptr]`), a
   String Space allocator with compaction, both in `engines/string_engine.py`.
2. `T_STRING_VARIABLE` in the token table and the tokenizer, replacing the
   present "not implemented yet" error.
3. String operands on the expression operand stack — the `'S'` kind is already
   defined and handled; only the producers are missing.
4. `+` for concatenation when both operands are strings, and string comparison.
5. `LEN`, `CHR$`, `ASC`, `STR$`, `VAL`, `LEFT$`, `RIGHT$`, `MID$` as function
   tokens in the Expression Engine.
6. `INPUT` into a string variable, which needs `INPUT_FIELD` to stop parsing the
   field as a number.
7. Regression programs that use strings, recorded with `tests/record_program.py`.

Nothing in that list changes the architecture. That is the test of whether this
milestone was built correctly.

## Before the Hardware Model starts

* Steps 17 and 18 finished, so the language shape is settled.
* Every engine's interface written down (the module docstrings do this today;
  they need to become a signal-level table).
* A cycle budget per micro-operation, so the Hardware Model's clock means
  something.
* The regression suite large enough that the Hardware Model can be validated by
  running it and diffing screens against the Functional Model.
