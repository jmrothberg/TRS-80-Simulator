# TRS-80 BASIC Simulator: Python → HTML/JavaScript Web Port

## Context

The user has a fully working TRS-80 Model I Level II BASIC simulator in Python/Tkinter (`TRS80_March_22_26.py`, ~3870 lines). They want an HTML/JavaScript version that runs in the browser. The AI assistant (WebLLM) is deferred — this plan focuses on a **working BASIC interpreter that runs existing .bas files**.

The source Python class `TRS80Simulator` is a single-class interpreter with a 5-stage pipeline: editing/storage → preprocessing → execution loop → command dispatch → expression evaluation. The JS port mirrors this 1:1.

## Output

**Single file:** `web/index.html` containing all HTML, CSS, and JavaScript.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Expression evaluator | JS `eval()` (same as Python's `eval()`) | 1:1 port of all 8 transformation stages; avoids rewrite bugs |
| Execution model | `async/await` with `setTimeout(0)` yields | Can't block main thread; DOM access needed (no Web Worker) |
| Screen rendering | Immediate canvas draw (like Python) | Full redraw only on scroll; matches source behavior |
| AND/OR translation | `&` / `|` (bitwise) | TRS-80 BASIC AND/OR are bitwise; matches real hardware behavior |
| File format | Single `index.html` | Simple deployment, user requirement |

## Implementation Plan

### 1. HTML/CSS Structure (~150 lines)

- `<canvas id="screen">` — 768x288 (128×6 × 48×6), black bg, green phosphor text
- `<textarea id="inputArea">` — 64 cols × 6 rows, monospace, program editing
- `<div id="buttonBar">` — RUN, CLEAR, STOP, STEP, LIST, NEW, SAVE, LOAD, Copy, Debug
- `<div id="debugPanel">` — collapsible scrollable textarea
- CSS: dark gray body, centered layout, `Courier New` monospace font, lime-on-black canvas

### 2. TRS80Simulator Class — State Init (~100 lines)

Port `__init__` (Python lines 120-340):
- `screenContent[16][64]`, `pixelMatrix[48][128]`, cursor state
- `scalarVariables` (Map), `arrayVariables` (Map), `forLoops` (Map)
- `gosubStack[]`, `dataValues[]`, `dataPointer`
- `storedProgram[]`, `commandBuffer`, execution flags
- Canvas setup: PIXEL_SIZE=6, charW=12, charH=18
- Compile regex patterns (port of `_compile_regex_patterns`, Python line 459)
- Define eval helpers: `_gt`, `_lt`, `_ge`, `_le`, `_eq`, `_ne`, `_bnot` as module-scope functions

### 3. Screen Rendering (~120 lines)

Port: `print_to_screen` (line 1195), `clear_screen` (1113), `redraw_screen` (1230), `_scroll_screen_up` (1077), cursor blink (408-450)

- `clearScreen()`: `ctx.fillRect` black, reset arrays
- `printToScreen(text, end)`: iterate chars, `ctx.fillText` in lime, handle wrap/scroll
- `drawChar(row, col, char)`: clear cell, draw character
- `scrollScreenUp()`: shift arrays, full redraw
- `blinkCursor()`: `setInterval(500ms)`, toggle lime rect at cursor pos

### 4. Keyboard Input (~80 lines)

Port: `on_key_press` (897), `handle_input_key` (1256), `handle_input_return` (1311)

- Single `keydown` listener on canvas (with `tabindex="0"`)
- Route to: break (Esc/Ctrl+C), keyboard buffer (INKEY$/PEEK), INPUT handler, or immediate mode
- Prevent default on handled keys

### 5. Immediate Mode (~100 lines)

Port: `enable_immediate_mode` (3492), `handle_immediate_mode_key` (3509), `handle_immediate_mode_return` (3553), `process_immediate_command` (3577)

- `>` prompt, `commandBuffer` accumulation
- RUN, LIST, NEW, CLEAR, CONT, LOAD, SAVE, CLS, DELETE commands
- Numbered lines → store in `storedProgram`, sort, update textarea
- Fallthrough to `executeCommand()` for immediate PRINT, LET, etc.

### 6. Preprocessor (~60 lines)

Port: `preprocess_program` (1473), `_prescanData` (1613)

- Split multi-statement lines on colons (preserving colons in quotes and after IF/THEN/ELSE)
- Generate sub-line numbers (10.1, 10.2)
- Pre-scan DATA statements into `dataValues[]`

### 7. Execution Loop (~100 lines)

Port: `run_program` (1562), `execute_next_line` (1631)

```javascript
async executeNextLine() {
    while (this.programRunning && !this.programPaused) {
        // Execute line, handle GOTO/GOSUB branches
        // Yield to browser every N iterations:
        if (counter % 20 === 0 || this._usesInkey)
            await new Promise(r => setTimeout(r, 0));
        if (this.waitingForInput) return; // resume from handleInputReturn
    }
}
```

- Build 3 parallel arrays: `_lineNumbers`, `_lineCommands`, `_lineCmdWords`
- Binary search `findLineIndex()` for GOTO/GOSUB targets
- INPUT pauses loop; `handleInputReturn()` resumes via `executeNextLine()`
- DELAY uses `await new Promise(r => setTimeout(r, ms))`

### 8. Command Dispatch + Handlers (~380 lines)

Port: `execute_command` (2177), all `_cmd_*` methods (2251-2632)

**Commands:** PRINT, PRINT@, LET, REM, POKE, SET, RESET, CLS, DIM, INPUT, GOTO, IF/THEN/ELSE, FOR/NEXT, ON GOTO, GOSUB/RETURN, DELAY, DATA, READ, RESTORE, STOP, END, INPUT#-1, PRINT#-1

Key porting notes:
- `cmdPrint`: port `findNextSeparator`, TAB(), semicolon/comma formatting, `_formatNumber`
- `cmdIf`: regex match, `_executeMultiStatement` for colon-separated THEN/ELSE clauses
- `cmdDelay`: returns special async marker; execution loop awaits it
- `cmdInput`: sets `waitingForInput = true`; execution loop pauses

### 9. Expression Evaluator (~300 lines) — **Most Complex Section**

Port: `evaluate_expression` (2694), `_eval_nested` (2880), `_buildQuoteMap` (2656), `_wrapTrs80Logic` (2727), operand scanners (2769-2878)

8-stage pipeline (mirrors Python exactly):
1. Fast paths: integer, negative integer, simple variable lookup
2. Build quote-map (bytearray marking positions inside string literals)
3. INKEY$ replacement
4. Keyword translation: `RND`→`Math.random()`, `MOD`→`%`, `OR`→`|`, `AND`→`&`, `NOT`→via `_bnot`, `=`→`==`, `<>`→`!=`, `^`→`**`
5. Built-in function dispatch (regex match, recursive inner eval, replace)
6. Array reference substitution (paren-counting, recursive index eval)
7. Scalar variable substitution (longest-first, skip quoted strings)
8. Comparison wrapping (`A > B` → `_gt(A,B)`)
9. `eval(expr)` with helper functions in scope

### 10. Built-in Functions (~120 lines)

Port: `_init_builtin_functions` (3067), function handlers (3095-3162)

Math: INT, SIN, COS, TAN, SQR, LOG, EXP, SGN, ABS, FIX, RND
String: STR$, CHR$, STRING$, LEFT$, RIGHT$, MID$, INSTR, LEN, ASC, VAL
System: PEEK, POINT

### 11. Memory Model + Graphics (~90 lines)

Port: `peek` (3213), `poke` (3189), `inkey` (3233), `set_pixel` (3254), `reset_pixel` (3264), `_flush_graphics` (3274), `get_pixel` (3298)

- PEEK(14400): keyboard buffer
- PEEK/POKE(15360-16383): screen memory
- SET/RESET: batched graphics (flush every 20 ops)
- `activePixels` Set for efficient scroll redraw

### 12. File I/O (~60 lines)

Port: `save_program` (3359), `load_program` (3370), tape I/O (3313-3357)

- SAVE: `Blob` + download link
- LOAD: `<input type="file">` + `FileReader.readAsText()`
- Tape: in-memory array with file picker for import/export

### 13. Debug + Error Messages + Utilities (~70 lines)

- Error codes: SN, FC, UL, BS, OD, NF, RG (matching TRS-80 originals)
- Debug panel: timestamped log messages
- Utilities: `findLineIndex` (binary search), `sortProgramLines`, `formatNumber`

## Estimated Size: ~1800 lines total in single index.html

## Verification Plan

1. Open `web/index.html` in browser, verify green-on-black screen with `>` prompt and blinking cursor
2. Type `PRINT "HELLO WORLD"` at prompt → verify output
3. Type numbered lines manually (10 PRINT "HI" / 20 GOTO 10 / RUN) → verify loop + STOP with Esc
4. Load `Basic_Code_Examples/Hello_world.bas` via LOAD button → RUN
5. Load `Basic_Code_Examples/Snake.bas` → RUN (tests PEEK, INKEY$, SET/RESET, POINT, DIM, GOSUB, PRINT@)
6. Load `Basic_Code_Examples/hangman.bas` → RUN (tests INPUT, string functions, DATA/READ)
7. Load `Basic_Code_Examples/complex_test_suite.bas` → RUN (comprehensive coverage)
8. Verify SAVE downloads a .bas file that can be re-loaded

## Critical Source Files

- `/home/user/TRS-80-Simulator/TRS80_March_22_26.py` — Complete source to port
- `/home/user/TRS-80-Simulator/Basic_Code_Examples/*.bas` — Test programs
