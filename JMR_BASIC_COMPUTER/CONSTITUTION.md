# JMR BASIC COMPUTER

## Project Constitution v1.0

This document is the architectural specification for the JMR BASIC Computer.

If there is ever a conflict between this document and the implementation,
THIS DOCUMENT IS CORRECT.

The implementation must be changed to match the specification.

Never simplify the architecture without updating this document.

Never replace major architectural concepts because they appear "easier."

The goal is educational elegance, not minimum code.

---

# PROJECT GOAL

Build an original FPGA computer whose native programming language is BASIC.

The user never programs assembly language.

The FPGA executes BASIC directly.

The visible behavior should feel like a TRS-80 Model I Level II BASIC computer
while the internal implementation is completely original.

This is NOT:

- a Z80 emulator
- a Microsoft BASIC ROM clone
- a retro recreation

It is an entirely new computer architecture inspired by the TRS-80.

---

# FUNDAMENTAL PHILOSOPHY

Traditional computers execute assembly language.

Assembly executes BASIC.

We reverse this.

BASIC becomes the machine language.

The FPGA executes BASIC.

---

# NON-NEGOTIABLE DESIGN RULES

The following rules may NEVER be violated.

1. No Z80 core.
2. No 6502 core.
3. No RISC-V.
4. No hidden CPU underneath BASIC.
5. No interpreter running on another processor.
6. BASIC is the architectural instruction set.
7. User never sees assembly language.
8. Architecture must remain understandable.
9. Every subsystem must have a Python reference model.
10. Every FPGA module must correspond to a documented subsystem.

---

# DEVELOPMENT ORDER

Everything begins in Python.

NOT Verilog.

Python is the executable specification.

Development order is:

Architecture
↓
Python Functional Model
↓
Python Hardware Model
↓
SystemVerilog
↓
Simulation
↓
FPGA
↓
Optimization

Do not skip steps.

---

# TARGET HARDWARE

Digilent Nexys A7-100T

XC7A100T FPGA

Development host:

Mac

Development tools:

Python

Cursor

Claude Code

Vivado

GitHub

---

# USER EXPERIENCE

The computer should boot into:

```
JMR LEVEL II BASIC
READY
```

The user types:

```
10 PRINT "HELLO"
RUN
```

The machine prints:

```
HELLO
```

The user never knows anything about the internal architecture.

---

# BASIC COMPATIBILITY

Compatibility goal:

TRS-80 Model I Level II BASIC

Initial emphasis:

Source compatibility.

Later:

Behavior compatibility.

Later:

Token compatibility.

Eventually:

Maximum practical compatibility.

---

# DISPLAY

Text

64 columns

16 rows

Graphics

128 x 48

Semigraphics compatible.

Graphics commands:

SET

RESET

POINT

PRINT@

CLS

---

# BASIC IS THE CPU

Instead of:

CPU
↓
Interpreter
↓
BASIC

we build:

BASIC
↓
Processor

The processor executes BASIC tokens.

---

# BASIC TOKENS

The architectural instruction set is:

PRINT
INPUT
LET
IF
THEN
GOTO
GOSUB
RETURN
FOR
NEXT
STEP
READ
DATA
RESTORE
DIM
CLS
SET
RESET
POINT
PEEK
POKE
SAVE
LOAD

Every token has:

one opcode

one dispatch table entry

one implementation

---

# CPU ARCHITECTURE

The processor consists of independent hardware engines.

Program Sequencer

Tokenizer

Expression Engine

Variable Engine

Array Engine

Flow Engine

String Engine

Print Engine

Graphics Engine

Video Engine

Keyboard Engine

Storage Engine

These engines communicate through defined interfaces.

Do not merge them into one giant module.

---

# EXECUTION MODEL

Execution is:

Fetch BASIC token
↓
Decode BASIC token
↓
Dispatch
↓
Execute
↓
Fetch next BASIC token

Every BASIC command executes a defined sequence of micro-operations.

---

# MICROCODE

The processor is microcoded.

The programmer never sees this.

Each BASIC command dispatches into microcode.

Example:

PRINT
↓
PRINT microcode
↓
Evaluate expression
↓
Convert to characters
↓
Write to VRAM
↓
Return

Microcode is stored in Block RAM.

Microcode is part of the architecture.

---

# SHARED ENGINES

Never duplicate hardware.

PRINT

LET

IF

FOR

all share one Expression Engine.

SET

RESET

POINT

share one Graphics Engine.

SAVE

LOAD

share one Storage Engine.

Everything reusable must be shared.

---

# MEMORY

Memory regions:

Boot ROM

Character ROM

Program RAM

Variable RAM

Array RAM

String RAM

Expression Stack

FOR Stack

GOSUB Stack

Video RAM

Storage Buffers

Memory map is documented.

Never hard-code addresses throughout the design.

---

# VIDEO

Video memory is shared text and graphics memory.

64 x 16 characters

128 x 48 graphics

Graphics modify bits inside character cells.

Video subsystem is independent of BASIC execution timing.

Use dual-port Block RAM.

---

# KEYBOARD

Phase 1

Mac keyboard
↓
UART
↓
Console

Phase 2

USB HID Keyboard
↓
USB Host
↓
Keyboard FIFO
↓
Console

The console behavior remains unchanged.

---

# STORAGE

Phase 1

Host files
↓
UART
↓
Program RAM

Phase 2

microSD
↓
Storage Engine
↓
Program RAM

The BASIC CPU does not know which storage device is used.

---

# PYTHON REFERENCE MODEL

Every subsystem exists first in Python.

The Python model is the behavioral truth.

Python contains:

Console

Tokenizer

Program RAM

Expression Engine

Variables

Graphics

Storage

Video

Keyboard

Python exposes every internal state.

---

# PYTHON HARDWARE MODEL

The second Python model mirrors FPGA hardware.

Explicit memories.

Explicit stacks.

Explicit state machines.

Explicit clocks.

Explicit interfaces.

The Python Hardware Model and FPGA must produce identical results.

---

# FPGA MODULES

One module per subsystem.

Example:

program_sequencer.sv

expression_engine.sv

graphics_engine.sv

video_engine.sv

storage_engine.sv

Do not create giant monolithic modules.

---

# FPGA RESOURCE STRATEGY

Target board:

XC7A100T

Architecture must comfortably fit.

Share hardware.

Reuse arithmetic.

Reuse parsers.

Reuse memory.

Keep utilization below roughly:

70% LUTs

75% BRAM

20% DSP

Review Vivado after every milestone.

---

# FLOATING POINT

Do NOT implement first.

Stage 1

16-bit signed integer BASIC.

Stage 2

Complete language.

Stage 3

Shared floating-point engine.

---

# TESTING

Do not generate random programs.

Instead:

Use AI to create complete BASIC applications.

Examples:

Games

Graphics

Calendars

Accounting

Maze generation

Animation

Math

String manipulation

Public-domain BASIC programs

Every accepted program becomes a permanent regression test.

---

# IMPLEMENTATION ORDER

1. UART
2. Video
3. Console
4. Tokenizer
5. Program RAM
6. LIST
7. RUN
8. Integer Expressions
9. Variables
10. IF
11. GOTO
12. GOSUB
13. FOR/NEXT
14. Graphics
15. SAVE
16. LOAD
17. Strings
18. Arrays
19. Floating Point
20. USB Keyboard

---

# CLAUDE IMPLEMENTATION RULES

Claude Code should never redesign the architecture.

Claude should:

Implement.

Refactor locally.

Improve code quality.

Improve performance.

Add tests.

Document changes.

Claude should NOT:

Replace the architecture.

Merge independent engines.

Replace BASIC with a hidden CPU.

Replace microcode with another architecture.

Remove documentation.

---

# SUCCESS CRITERIA

The final computer should feel like a TRS-80.

Internally it should be an entirely original computer.

The code should be understandable by students.

Every subsystem should be independently testable.

The architecture should be elegant enough that someone reading the repository
understands how a complete computer works from keyboard input to video output.

The repository should become one of the best educational FPGA computer projects
available.
