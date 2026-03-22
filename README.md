# TRS-80 Model I Level II BASIC Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A desktop simulator for the TRS-80 Model I Level II BASIC, written in Python with a Tkinter GUI.  It runs vintage-style BASIC programs on a green-on-black 64x16 text / 128x48 graphics display and includes a built-in debugger and an optional LLM companion for code help.

![Screen layout](https://img.shields.io/badge/display-64x16_text_%7C_128x48_graphics-green)

## Quick Start

```bash
pip install -r requirements.txt
python TRS80_March_17_26.py
```

Type BASIC lines directly on the green screen (immediate mode) or paste a program into the input area and press **RUN**.

---

## Project Files

| File | Purpose |
|------|---------|
| `TRS80_March_17_26.py` | Main simulator — interpreter, UI, screen, debugger (~3,600 lines, single class) |
| `TRS80LLMSupport.py` | Optional AI companion window (Claude API, Ollama, HuggingFace) |
| `Basic_Code_Examples/` | Sample `.bas` programs: games, tests, demos |
| `Hailo_for_Pi/` | Hailo-10H AI accelerator support for Raspberry Pi |
| `TRS80_BASIC_REFERENCE.md` | Language reference for the supported BASIC dialect |
| `requirements.txt` | Python dependencies |

---

## How the Interpreter Works

The interpreter turns BASIC source text into execution through a five-stage pipeline that runs cooperatively inside the Tkinter main loop.

### Stage 1 — Editing & Storage

The user types BASIC lines into either:
- The **green screen** (immediate mode, `>` prompt) — numbered lines are stored; bare commands execute immediately.
- The **input area** (ScrolledText widget below the screen) — edited as plain text, synced to `stored_program` on every keystroke.

Lines are always kept sorted by line number.

### Stage 2 — Preprocessing (`preprocess_program`)

Before RUN, multi-statement lines are split on colons:

```
10 A=1: B=2: PRINT A+B
```
becomes three internal entries:
```
10   A=1
10.1 B=2
10.2 PRINT A+B
```

Colons inside quoted strings and after `THEN`/`ELSE` are preserved (the IF/THEN clause stays as one unit).  All `DATA` statements are pre-scanned into `data_values[]` so `READ` can access them in program order regardless of execution flow.

### Stage 3 — Execution Loop (`execute_next_line`)

`run_program` builds three parallel arrays from the sorted, preprocessed lines:

| Array | Contents |
|-------|----------|
| `_line_numbers[i]` | BASIC line number (float — supports `10.1`) |
| `_line_commands[i]` | Command text after the line number |
| `_line_cmd_words[i]` | First keyword, pre-extracted for fast dispatch |

`execute_next_line` is a tight `while` loop that walks `current_line_index` forward, calling `execute_command()` for each line.  The return value controls flow:

| Return | Meaning |
|--------|---------|
| `None` | Advance to the next line |
| `int`/`float` | Branch to that line number (GOTO, GOSUB, FOR/NEXT loop-back) |
| *sets `waiting_for_input`* | Pause — return to Tkinter event loop; `handle_input_return` resumes via `after()` |

**GUI responsiveness:**  The loop yields to Tkinter periodically — `update_idletasks()` every iteration when `INKEY$` is used (games need responsive key polling), otherwise every 10th iteration.  A full `update()` happens every 25th iteration to flush graphics.

### Stage 4 — Command Dispatch (`execute_command`)

The pre-extracted keyword is looked up in `_command_handlers`, a dict mapping strings to `_cmd_*` methods:

```python
_command_handlers = {
    'PRINT': _cmd_print,
    'LET':   _cmd_let,
    'FOR':   _cmd_for,
    'NEXT':  _cmd_next,
    'GOTO':  _cmd_goto,
    'GOSUB': _cmd_gosub,
    'IF':    _cmd_if,
    ...
}
```

If the keyword isn't found but the line contains `=`, it's treated as an implicit `LET` (`A=5` becomes `LET A=5`).

### Stage 5 — Expression Evaluation (`evaluate_expression` / `_eval_nested`)

This is the heart of the interpreter.  Expressions like `A*2+RND(5)` go through eight stages:

```
  BASIC expression string
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 1. Fast paths: pure integer, negative int, or    │
  │    simple variable lookup → return immediately    │
  └────┬─────────────────────────────────────────────┘
       │ (not a fast path)
  ┌────▼─────────────────────────────────────────────┐
  │ 2. Build quote-map (bytearray, 0/1 per char)    │
  │    to protect string literals from replacement    │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 3. INKEY$ replacement (at most once)             │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 4. Single-pass keyword translation               │
  │    (one combined regex: AND→and, OR→or, MOD→%,   │
  │     ^→**, =→==, <>→!=, bare RND→random float)    │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 5. Built-in function dispatch (INT, RND, LEFT$,  │
  │    MID$, etc.) via _builtin_functions table       │
  │    — inner expression evaluated recursively       │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 6. Array reference substitution                  │
  │    A(I) → looked up in array_variables            │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 7. Scalar variable substitution                  │
  │    (longest-first to prevent "A" clobbering "AB") │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 8. Comparison wrapping for TRS-80 semantics      │
  │    A > B → _gt(A,B) returning -1 (true) or 0     │
  └────┬─────────────────────────────────────────────┘
       │
  ┌────▼─────────────────────────────────────────────┐
  │ 9. Python eval() in restricted namespace         │
  │    (__builtins__=None, only math + comparisons)   │
  └────┴─────────────────────────────────────────────┘
```

---

## Screen Model

| Layer | Resolution | Storage | Canvas tags |
|-------|-----------|---------|-------------|
| Text | 64 cols x 16 rows | `screen_content[][]` | `c{row}_{col}` |
| Graphics | 128 x 48 pixels | `pixel_matrix[][]` | `p{x}_{y}` |

Each text cell covers a 2x3 block of graphics pixels.  Canvas items use tags so `find_withtag`/`itemconfigure` can update in place instead of delete+create.

Graphics `SET`/`RESET` calls are batched in `_pending_graphics` and flushed every 20 operations or at GUI-update boundaries.  `_active_pixels` (a set) tracks which pixels are lit for efficient scroll and redraw.

---

## Key Data Structures

```
scalar_variables    dict  {name: value}         {"A": 5, "N$": "HI"}
array_variables     dict  {name: list}          {"A": [0,0,0,...]}
for_loops           dict  {var: loop_info}      loop_info has start/end/step/current/next_line_number
gosub_stack         list  [return_line_index]    indices into _line_numbers
_line_numbers       list  [float]                parallel array: BASIC line numbers
_line_commands      list  [str]                  parallel array: command text
_line_cmd_words     list  [str]                  parallel array: first keyword
_command_handlers   dict  {keyword: method}      command dispatch table
_builtin_functions  dict  {name: callable}       function dispatch table
_regex_cache        dict  {name: compiled_re}    all pre-compiled regex patterns
_eval_namespace     dict                          restricted namespace for eval()
```

---

## Performance Architecture

The hot path is: `execute_next_line` → `execute_command` → `evaluate_expression` → `_eval_nested`.  Key optimizations:

- **Cached derived values:** `_screen_font`, `_char_w`, `_char_h` avoid recomputing font tuples and pixel math on every draw call.
- **Single-pass keyword replacement:** One combined regex replaces all BASIC→Python operator translations in a single `re.sub` pass instead of eight separate passes.
- **Quote-map as bytearray:** Faster allocation and truthiness checks than `list[bool]`.
- **Pre-parsed command words:** The first keyword of each line is extracted once at RUN time and passed to `execute_command`, avoiding repeated string splitting.
- **Guarded debug prints:** f-string formatting for debug messages is skipped entirely when debug mode is off.
- **Canvas itemconfigure:** Text characters use `find_withtag` + `itemconfigure` to update existing items instead of deleting and recreating.
- **Batched graphics:** `SET`/`RESET` queue operations and flush in batches of 20.
- **O(active) scroll:** `_scroll_screen_up` shifts the active-pixel set with a comprehension instead of scanning all 6,144 positions.

---

## BASIC Dialect Notes

The simulator targets TRS-80 Model I Level II BASIC:

- Every program line needs a line number.  Keywords must be uppercase.
- `PRINT@` uses 1-based screen positions (1-1024).
- `RND(n)` returns an integer from 1 to n.  `RND(0)` returns a float 0-1.
- Comparisons return `-1` (true) or `0` (false).
- `AND`, `OR`, `NOT` work as logical operators on -1/0 values.
- `STR$(n)` includes a leading space for the sign placeholder.
- `PEEK(14400)` polls the keyboard buffer (primary method for game input).
- Multiple statements per line: `10 A=1: B=2: PRINT A+B`
- `IF ... THEN ... ELSE ...` — colons after THEN/ELSE stay in the IF clause.

See `TRS80_BASIC_REFERENCE.md` for the full language reference.

---

## Debugging Tools

- **Debug window** — Toggle with the Debug button.  Shows a timestamped execution trace (line number, step count, variable assignments, errors) with search and copy.
- **Variables window** — Live view of scalars, arrays, FOR loops, and GOSUB stack.
- **Step mode** — Single-step through execution with the STEP button.
- **LLM companion** — Send debug output or program state to an AI assistant (Claude, Ollama, or local HuggingFace models).

---

## Example Programs

The `Basic_Code_Examples/` directory contains:

| File | Description |
|------|-------------|
| `Invaders_V.bas` / `Invaders_VI.bas` | Space Invaders variants |
| `asteroid.bas` | Space shooter |
| `Snake.bas` | Snake game |
| `breakout_II.bas` | Breakout clone |
| `Hi_Low.bas` | Number guessing game |
| `complex_test_suite.bas` | Comprehensive BASIC feature tests |

Run with: type `LOAD` on the green screen, select a `.bas` file, then type `RUN`.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` or `Ctrl+C` | BREAK — stop running program |
| `Ctrl+R` | Emergency reset to immediate mode |
| Right-click | Copy/paste context menu |
| Click green screen | Auto-recover immediate mode if lost |

---

## Troubleshooting

- **Ollama models don't appear:** Make sure Ollama is running (`ollama list`).
- **Anthropic API not working:** Set `ANTHROPIC_API_KEY` in your shell environment.
- **Graphics seem too small:** Use the `2X` button (not available on Raspberry Pi).
- **Screen seems frozen:** Click the green screen or press `Ctrl+R`.

## License

This project is licensed under the MIT License.  See `LICENSE`.
