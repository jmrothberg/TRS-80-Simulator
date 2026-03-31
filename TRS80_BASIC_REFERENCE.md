# TRS-80 Model I Level II BASIC — Reference (machine + this interpreter)

This guide describes **Radio Shack TRS-80 Model I Level II BASIC** as it was documented on the **original hardware** (1978-era ROM). Where this project’s **Python / web interpreter** behaves differently, that is called out explicitly — look for **Interpreter:** notes.

---

## Table of contents

- [How to use this document](#how-to-use-this-document)
- [Original machine: overview](#original-machine-overview)
- [Interpreter differences (summary)](#interpreter-differences-summary)
- [Immediate mode and commands](#immediate-mode-and-commands)
- [Program statements](#program-statements)
- [Expressions, operators, functions](#expressions-operators-and-functions)
- [`DEF FN` (user-defined functions)](#def-fn-user-defined-functions)
- [Graphics](#graphics)
- [Memory, PEEK/POKE, cassette](#memory-peekpoke-cassette)
- [Limitations (Level II)](#limitations-level-ii)
- [Syntax and style](#syntax-and-style)
- [Memory map (Model I)](#memory-map-model-i)
- [Examples](#examples)

---

## How to use this document

- **Default text** = **Model I Level II on real hardware** (manuals / common reference material).
- **`Interpreter:`** = **only** applies to **this simulator** (`TRS80_March_31_26.py`, `web_TRS_80/index.html`, `docs/index.html`).

When behavior is unknown or ROM-dependent, that is stated.

---

## Original machine: overview

| Item | Model I Level II |
|------|-------------------|
| Text | **64 × 16** characters |
| Bitmap graphics | **128 × 48** pixels (SET/RESET/POINT) |
| Line numbers | **0–65529** (65530–65535 reserved / system) |
| Keywords | Not case-sensitive on entry; stored/listing uppercase |
| Program storage | Lines in memory; execution in **ascending line-number order** unless redirected |

**`RUN`** on the real machine clears the **display** and performs the same kind of reset as **`CLEAR`** (variables, stacks, `FOR` loops, `DATA` pointer, etc.), then starts at the **smallest** line number (or at **`RUN line`** if given).

**`NEW`** clears the program and variables; it does **not** necessarily ask for confirmation on stock ROM (software overlays sometimes added prompts).

**`CLEAR`** clears variables and control state but **keeps** the program in memory.

---

## Interpreter differences (summary)

| Topic | Original Model I Level II | This interpreter |
|-------|---------------------------|------------------|
| **Editor / I/O** | Keyboard + video; programs from cassette (`CLOAD`/`CSAVE`) or disk (with DOS) | **Text area + RUN/LOAD/SAVE**; **`.bas` files** via **file dialog** for LOAD/SAVE |
| **`NEW`** | Clears program + vars | Prints *“ARE YOU SURE?”*-style text in one code path but **does not wait** for Y/N — clears **immediately** |
| **`ON … GOSUB`** | **Yes** — part of **stock Model I Level II BASIC** (same family as **`ON … GOTO`**) | Was **missing in this simulator**; **now implemented** (`on_gosub` + stack, same as **`GOSUB`**) |
| **`DELAY`** | Not a standard Level II statement keyword | **Extension**: `DELAY n` → pause ≈ **`n × 10` ms** (Tk `after` on desktop) |
| **`SYSTEM`** | Enters machine monitor / exits to DOS depending on ROM and DOS | **Not implemented** (prints a message) |
| **`PEEK(14400)`** | Keyboard **hardware** uses specific addresses; **14400** is used in games as a **keyboard-related** location | **Simulated**: last key **ASCII** or **0**; shares buffer with **`INKEY$`** (read **consumes**). Desktop pumps Tk **only when no key is buffered**, so empty tight loops stay cheap. **Not** cycle-accurate vs real latch. |
| **`RND`** | `RND(0)` / `RND(1)` style float; `RND(n)` integer **1..n** for **n > 1** (see manuals) | **Bare `RND`** (no `(`) is rewritten to a **new** random **float** each occurrence; **`RND(n)`** uses project rules in `_func_rnd` (float if `n≤1`, else integer **1..n**) |
| **Tape** | `PRINT#` / `INPUT#` to cassette with hardware | **`PRINT#-1` / `INPUT#-1`** use an **in-memory “tape”** buffer |
| **UI** | Physical keyboard | **Debug / variables / LLM** (desktop) — **not** on original hardware |

### Interrupt — original machine vs this simulator

- **Real Model I:** **BREAK** key stops the running program, prints **`BREAK IN line`**, returns to **`READY`** / **`>`**.
- **This app (desktop):** **Esc** or **Ctrl+C** calls the same idea (`break_program`) — stops run, **`BREAK IN line`**, **`>`** prompt.
- **Web:** Keyboard handler should offer an equivalent stop path (browser may reserve some shortcuts).

### Screen memory `PEEK(15360–16383)`

- **Original:** Reads the **character code** in the **video RAM** cell.
- **Interpreter:** Same idea — returns **`ord()`** of the character in the **emulated 64×16** buffer for that address. **Yes, this is the right model** for “read what’s on screen.”

---

## Immediate mode and commands

On the real machine, at **`READY`** you can type **commands** (no line number) or **program lines** (with line numbers).

### Commands typically used from READY

| Command | Original Model I Level II |
|---------|---------------------------|
| **`RUN`** / **`RUN line`** | Start program; **`RUN`** clears screen + reset + run from first (or given) line |
| **`LIST`** / **`LIST line`** / **`LIST l1-l2`** | List program |
| **`NEW`** | Erase program and variables |
| **`CLEAR`** | Clear variables / stacks; keep program |
| **`CONT`** | Resume after **`STOP`**, **break**, or some errors (not always after every error — see manual) |
| **`CLS`** | Clear screen |
| **`LOAD` / `SAVE`** | With **cassette** (`CLOAD`/`CSAVE` naming in many manuals) or **disk** when DOS present |

**Interpreter:** **`LOAD` / `SAVE`** open a **file dialog** and read/write **plain text** into the editor. **`DELETE`** (by line or range) is supported for editing the listing. **`SYSTEM`** is stubbed.

---

## Program statements

Statements appear on **numbered lines**. Several statements may appear on one line separated by **`:`** (with rules around **`IF`**).

Core Level II statements include **`PRINT`**, **`LET`** (optional), **`INPUT`**, **`GOTO`**, **`IF … THEN`**, **`FOR`/`NEXT`**, **`GOSUB`/`RETURN`**, **`ON … GOTO`**, **`ON … GOSUB`**, **`READ`/`DATA`/`RESTORE`**, **`DIM`**, **`REM`**, **`STOP`**, **`END`**, **`CLS`**, **`POKE`**, **`SET`/`RESET`**, **`DEF FN`**, **`PRINT#` / `INPUT#`** (cassette), etc.

### `PRINT` and `PRINT@`

- **`;`** — pack output; **`,`** — **16-character** print zones; trailing **`;`** or **`,`** — suppress line advance.
- **`PRINT@ n`** — print at character index **`n`** (0-based position in the **1024**-character text frame: **`row*64 + col`**, **row 0–15**, **col 0–63**).

### `IF … THEN … [ELSE …]`

Level II gained **`ELSE`** in common ROM revisions; **`IF`** may compute **line-number** targets as **`THEN 100`** (implicit **`GOTO`**).

**Interpreter:** Parser/preprocessor should match your **`IF`/`THEN`/`ELSE`** splitting; if something fails, compare with the real machine’s accepted forms.

### `ON` — computed `GOTO` / `GOSUB`

On the **original** Level II ROM, both are available:

```basic
ON X GOTO 100,200,300
ON X GOSUB 1000,2000,3000
```

**Interpreter:** Both **`ON expr GOTO …`** and **`ON expr GOSUB …`** are implemented (same **`GOSUB`** stack as direct **`GOSUB`**).

### `STOP` vs `END`

- **`STOP`** — pause; prints **`BREAK IN line`** (or similar); **`CONT`** may resume.
- **`END`** — end without the break message; **`CONT`** is **not** valid after a normal **`END`** on real Level II (**`?CN` / Can’t CONTinue**).

**Interpreter:** Follows the same broad idea; exact error text may differ.

### `DELAY`

**Interpreter only** — not standard Level II:

```basic
DELAY 100   ' ~1000 ms (100 * 10 ms) in desktop Tk build
```

---

## Expressions, operators, functions

### Operators (Level II)

- Arithmetic: **`+ - * / ^`**
- Integer remainder: **`MOD`** appears in Level II reference material (use your ROM manual if unsure).
- Comparisons: **`= <> < > <= >=`**
- Logical/bitwise: **`AND OR NOT`** (integer-style truth: often **−1** / **0**)

### Random numbers `RND`

Typical Level II usage:

- **`RND(0)`** (and sometimes **`RND(1)`**) — random **fraction** in **(0,1)** or **[0,1)** per manual wording.
- **`RND(n)`** with **integer n > 1** — random **integer** from **1** to **n** inclusive.

**Interpreter:**

- **Bare `RND`** (no parentheses) is replaced in the expression rewriter with a **new** float **0 ≤ x < 1** each time.
- **`RND(n)`** via **`_func_rnd`**: **`n ≤ 1`** → float; **`n > 1`** → integer **1..n**.

### Built-in functions (Level II core)

Numeric: **`ABS` `INT` `FIX` `SGN` `SQR` `SIN` `COS` `TAN` `ATN` `EXP` `LOG` `RND`**

String: **`LEN` `LEFT$` `RIGHT$` `MID$` `STR$` `VAL` `CHR$` `ASC` `STRING$`**

Machine: **`PEEK` `POINT` `INKEY$`**

**Interpreter:** **`INSTR`** is implemented for substring search. On **stock** Model I Level II, **`INSTR`** may be absent or differ — treat as **compatible extension** unless your manual lists it.

---

## `DEF FN` (user-defined functions)

Level II allows **single-line** definitions:

```basic
10 DEF FNA(X)=X*X+1
20 PRINT FNA(3)
```

Only **`FN` + one letter** and a simple parameter list appear in classic manuals.

**Interpreter:** **`DEF FNx(...)=...`** is parsed into a table; **`FNx(...)`** is expanded during evaluation. Match **`TRS80_March_31_26.py`** for exact regex (parameter naming).

---

## Graphics

- **`SET(X,Y)`** / **`RESET(X,Y)`** — turn pixel on/off.
- **`POINT(X,Y)`** — read pixel.

Manuals often use **1-based** **`X` (1–128)** and **`Y` (1–48)** for BASIC, while the hardware maps to **0–127** / **0–47** internally.

**Interpreter:** BASIC **`SET`/`RESET`/`POINT`** use **1-based** coordinates; internal storage is **0-based** (**`get_pixel(x-1,y-1)`** style).

---

## Memory, PEEK/POKE, cassette

### Important Model I addresses (typical)

| Address / range | Role |
|-----------------|------|
| **15360–16383** | **Screen** character buffer (**1024** bytes = **64×16**) |
| **14400** | Often used in **BASIC programs** as a **keyboard** / input cell in published listings |

**Interpreter:** **`PEEK`** for **15360–16383** returns the **character code** at that cell. **`PEEK(14400)`** does **not** emulate Z80/keyboard hardware bit-for-bit; it exposes a **simplified** “last key” style value for game ports.

### Cassette

Original: **`PRINT#-1,…`** / **`INPUT#-1,…`** (device **−1**) talk to **cassette** through the ROM’s I/O.

**Interpreter:** Same syntax maps to an **in-memory tape buffer**, not real audio I/O.

---

## Limitations (Level II)

- **Variable names** — effectively **two significant characters**: one letter, then optional letter or digit, then type suffix **`$` `%` `!` `#`** as applicable.
- **Arrays** — one dimension; **`DIM`** defines size (**0…N** inclusive when **`DIM A(N)`**).
- **No multi-line `DEF FN`** on stock Level II.
- **No structured `PROC`/`SUB`** — use **`GOSUB`**.

**Interpreter:** Same naming rules are enforced in practice by the parser; long names like **`NAME$`** are **not** separate variables on real Level II either.

---

## Syntax and style

1. **Line numbers** on **program** lines; **immediate** statements without numbers at **`READY`**.
2. **Strings** in **double quotes** (standard listings).
3. **`REM`** through end of line.
4. **Multiple statements** — **`:`** separator (watch **`IF`** interactions).

---

## Memory map (Model I)

Text screen formula (hardware / BASIC **`PRINT@`**):

**`address = 15360 + row × 64 + col`**, **`row`** **0–15**, **`col`** **0–63**.

---

## Examples

### Hello (portable)

```basic
10 CLS
20 PRINT "HELLO"
30 END
```

### `DEF FN`

```basic
10 DEF FNC(X)=X*2+1
20 PRINT FNC(5)
30 END
```

### Graphics (1-based coordinates)

```basic
10 CLS
20 SET(64,24)
30 END
```

---

## Maintaining this file

- **Hardware** sections should follow **Tandy/Radio Shack Model I Level II BASIC** manuals.
- **`Interpreter:`** sections should be updated when **`TRS80_March_31_26.py`** (or web `index.html`) changes.

If a statement in this file conflicts with **measured behavior on a real Model I**, **trust the machine** and adjust the **Interpreter** notes — not the other way around.
