# TRS-80 Model I Level II BASIC — Screen, PRINT, and PRINT@ Reference

This document describes the **exact** behavior of the TRS-80 Model I screen
display, the PRINT statement, and the PRINT@ statement.  It is intended as
a spec for the Python and JavaScript interpreters so they produce identical
output.

---

## 1. The Screen — A Flat 1024-Byte Buffer

| Property | Value |
|---|---|
| Columns (COLS) | 64 |
| Rows (ROWS) | 16 |
| Total cells | 1024 (64 × 16) |
| Video RAM | $3C00–$3FFF (1024 bytes) |
| Bytes per cell | 1 |

**Critical rule — one character per cell.**  
The TRS-80 screen is a **memory-mapped, flat byte array**.  Each of the 1024
positions holds exactly **one** byte.  Writing a character to a position
**replaces** whatever was there.  There are no layers, no transparency, no
z-order, and no way to see "two letters in one place."

Position numbering (0-based internally):

```
Row 0:  pos  0 ..  63
Row 1:  pos 64 .. 127
...
Row 15: pos 960 .. 1023
```

`row = position // 64`  
`col = position % 64`

### Level II BASIC Position Convention

Level II BASIC PRINT@ uses **1-based** positions (1–1024).
The interpreter must subtract 1 to convert to 0-based row/col:

```
internal_pos = PRINT@_position - 1
row = internal_pos // 64
col = internal_pos % 64
```

---

## 2. Cursor Model

The TRS-80 maintains a single **cursor position** (row, col) that tracks
where the next character will be written.

| Operation | Effect on cursor |
|---|---|
| Write character | cursor_col += 1 |
| cursor_col reaches 64 | cursor_row += 1, cursor_col = 0, **then** the character is drawn at the new position |
| Newline (\n) | cursor_row += 1, cursor_col = 0 (character is NOT drawn — newline is a control code) |
| cursor_row reaches 16 | Screen scrolls up one row; cursor_row stays at 15 |
| CLS | cursor_row = 0, cursor_col = 0; all 1024 cells set to space (0x20) |

### Column Overflow vs Newline — THE KEY DIFFERENCE

When `cursor_col >= 64` and the current character is a **printable** character
(not `\n`):

1. Advance: `cursor_row++`, `cursor_col = 0`
2. Scroll if needed
3. **Draw the character** at the new (row, col)
4. `cursor_col++`

When the current character is `\n`:

1. Advance: `cursor_row++`, `cursor_col = 0`
2. Scroll if needed
3. **Do NOT draw anything** — newline is invisible

This means a 64-character string printed at col 0 fills the entire row
(cols 0–63), then the trailing `\n` moves to the next row.  A 65-character
string wraps the 65th character to col 0 of the next row.

---

## 3. PRINT Statement

### Syntax

```basic
PRINT expression_list
PRINT expression_list ;
PRINT expression_list ,
```

### Rules

1. **Evaluate** each expression in the list and convert to a string.
2. **Write** each character of each string to the screen at the current
   cursor position, advancing the cursor after each character.
3. After ALL expressions are written:
   - **No trailing separator** → emit a newline (cursor to col 0 of next row)
   - **Trailing semicolon (;)** → do nothing (cursor stays after last character)
   - **Trailing comma (,)** → advance cursor to the next 16-column tab stop

### Separators Between Expressions

| Separator | Behavior |
|---|---|
| `;` (semicolon) | No space between items |
| `,` (comma) | Advance to next 16-column tab stop (cols 0, 16, 32, 48) |

### Number Formatting

Numbers are printed with a leading space (for the sign position) if positive,
or a leading `-` if negative, and a trailing space:

```
PRINT 5      →  " 5 "   (leading space, trailing space)
PRINT -5     →  "-5 "   (minus sign, trailing space)
```

---

## 4. PRINT@ Statement

### Syntax

```basic
PRINT@ position, expression_list
PRINT@ position, expression_list ;
PRINT@ position, expression_list ,
```

### Rules

**PRINT@ is NOT a "poke."  It is: set cursor, then PRINT.**

1. **Set cursor** to the target position: `row = (pos-1)//64`, `col = (pos-1)%64`
2. **Execute a normal PRINT** of the expression_list from that cursor position.
3. All normal PRINT rules apply — including newline at end (unless `;` or `,`).

### PRINT@ with empty content

```basic
PRINT@ 100,""
```

Sets cursor to position 100.  Prints empty string (nothing drawn).
Then emits newline → cursor moves to col 0 of next row.

### PRINT@ with semicolon

```basic
PRINT@ 100,"HELLO";
```

Sets cursor to position 100 (row 1, col 35).  Prints "HELLO" at
cols 35–39.  Semicolon suppresses newline.  Cursor stays at row 1, col 40.

### PRINT@ with no semicolon

```basic
PRINT@ 100,"HELLO"
```

Same as above, but newline IS emitted.  Cursor moves to row 2, col 0.

---

## 5. Character Writing — The Golden Rule

**Every character write REPLACES the cell content.**

On the real TRS-80, writing a byte to video RAM ($3C00 + offset) simply
stores the new value in that byte.  The old value is gone.  There is no
blending, no alpha, no layering.

### For the Simulator

The simulator MUST guarantee that when a character is written to (row, col):

1. The **old visual content** at that cell is fully erased.
2. The **new character** is drawn.
3. No remnant of any previous character is visible.
4. The `screen_content[row][col]` array matches what is on screen.

This means:
- Clear the cell's pixel area (black fill) **before** drawing the new character.
- There must be exactly **one** visual representation per cell — never two
  overlapping text items, never a text item hidden behind a rectangle.

---

## 6. Scrolling

When `cursor_row` reaches 16 (one past the last row):

1. All rows shift up by one: row 1→0, row 2→1, ... row 15→14.
2. Row 15 is filled with spaces.
3. `cursor_row` is set to 15.
4. The entire screen is redrawn.

Scrolling happens ONLY when the cursor tries to move past row 15.
It does NOT happen just because PRINT@ targets a high-numbered position.

---

## 7. CLS

```basic
CLS
```

1. All 1024 cells set to space (0x20).
2. All semigraphics pixels cleared.
3. Cursor set to (0, 0).
4. The entire screen is visually cleared (black).

---

## 8. INPUT and the Cursor

```basic
INPUT A$
INPUT "PROMPT";A$
```

1. If no custom prompt: print `? ` at current cursor position.
2. If custom prompt: print the prompt string (no `? `).
3. Cursor stays after the prompt, waiting for keystrokes.
4. User types characters — each character is written to the screen at
   the cursor position (replacing whatever was there), cursor advances.
5. On Enter: cursor moves to col 0 of next row, execution resumes.

**After PRINT@, INPUT's prompt appears where the cursor was left.**
This is why `PRINT@ 961,"CMD...";` followed by `INPUT A$` shows the
`? ` prompt right after "CMD..." on row 15.

---

## 9. Common Patterns and Expected Results

### Pattern A: Overwrite with PRINT@

```basic
10 CLS
20 PRINT@ 65,"AAAAAAAAAA"
30 PRINT@ 65,"BBBBB"
```

**Expected screen at row 1:**
```
BBBBBAAAAAnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn
```
(n = space, untouched)

PRINT@ 65 writes "AAAAAAAAAA" at row 1 cols 0–9.
PRINT@ 65 writes "BBBBB" at row 1 cols 0–4.
Cols 0–4 now contain "B".  Cols 5–9 still contain "A" (not cleared by
the second PRINT@).  The second PRINT@ only writes 5 chars, so only
5 cells are affected.

**Key: PRINT@ does NOT clear the rest of the row.**

### Pattern B: Cursor after PRINT@ without semicolon

```basic
10 CLS
20 PRINT@ 129,"HELLO"
30 PRINT "WORLD"
```

Line 20: PRINT@ 129 → row 2, col 0.  Print "HELLO" at cols 0–4.
No semicolon → newline → cursor at row 3, col 0.
Line 30: PRINT "WORLD" at row 3, col 0.

**Expected:**
```
Row 2: HELLO
Row 3: WORLD
```

### Pattern C: Cursor after PRINT@ with semicolon

```basic
10 CLS
20 PRINT@ 129,"HELLO";
30 PRINT "WORLD"
```

Line 20: PRINT@ 129 → row 2, col 0.  Print "HELLO" at cols 0–4.
Semicolon → cursor at row 2, col 5.
Line 30: PRINT "WORLD" at row 2, col 5.  No semicolon → newline.

**Expected:**
```
Row 2: HELLOWORLD
```

### Pattern D: Full row write + newline behavior

```basic
10 CLS
20 A$=STRING$(64,"*")
30 PRINT@ 65,A$
```

PRINT@ 65 → row 1, col 0.  Print 64 "*" chars, filling cols 0–63.
After col 63, cursor_col = 64.  Then newline: cursor_row = 3, col = 0.

Wait — the newline processes: cursor_col is 64, which triggers
col overflow → row 2, col 0.  But the character is '\n', so it
uses the newline path: row += 1 again? No.

**Exact sequence:**
1. Write 64 chars at cols 0–63.  After last char, cursor_col = 64.
2. Newline character is processed.
3. `cursor_col >= 64` OR `char == '\n'` → both true.  Either way:
   `cursor_row++`, `cursor_col = 0`.
4. Since char is '\n': do not draw, continue.
5. Cursor is now at row 2, col 0.

But wait — the JavaScript code checks BOTH conditions in ONE if:
```javascript
if (char === '\n' || this.cursorCol >= COLS) {
    this.cursorRow++;
    this.cursorCol = 0;
    ...
    if (char === '\n') continue;
}
```

So when cursor_col is 64 AND char is '\n', only ONE row advance happens
(the conditions are in the same if-block).  Cursor goes to row 2, col 0.
This is correct TRS-80 behavior.

---

## 10. Known Python Interpreter Bugs (vs correct behavior)

### Bug 1: Column overflow drops characters

When cursor_col >= 64 and the character is NOT a newline, the Python code
enters the `if` branch and advances the row, but the character is in the
`if` block — the `else` block (which draws the character) is skipped.
The character is **lost**.

**Correct (JS):** The character wraps to the start of the next row and IS drawn.
**Broken (Python):** The character vanishes.

### Bug 2: PRINT@ creates orphan clearing rectangles

Every PRINT@ call creates a `screen.create_rectangle(...)` to clear the
target area.  These rectangles are never deleted.  Over time, thousands of
rectangle objects accumulate on the tkinter Canvas, causing:
- Visual corruption (rectangles covering text items due to z-order)
- Performance degradation

**Correct (JS):** `ctx.fillRect` paints pixels directly — no retained objects.

### Bug 3: Character writes don't clear the cell first

In the JavaScript version, every character write does:
1. `fillRect(black)` — erase the cell
2. `fillText(char)` — draw the new character

In the Python version, `print_to_screen` does:
1. `itemconfigure(tag, text=char)` — update existing text item
2. Or `create_text(...)` — create new text item

**Neither clears the cell's pixel area first.**  If there are orphan
rectangles, old text items without tags, or other canvas debris at that
position, the old content shows through → "two letters in one place."

### Bug 4: redraw_screen does not clear orphan rectangles

`redraw_screen()` deletes "all" items and redraws from `screen_content`.
This is correct in principle, but if called during PRINT@ sequences,
the clearing rectangles created by subsequent PRINT@ calls pile up again.

---

## 11. The Fix Strategy

The Python interpreter should mimic the JavaScript approach:

**For every character written to (row, col):**
1. Update `screen_content[row][col] = char`
2. Clear the cell visually (black rectangle covering the cell area)
3. If char is not a space, draw the character text

**For PRINT@:**
- Do NOT create a batch clearing rectangle.
- Just set the cursor and let the normal character-by-character write handle
  clearing and drawing.

**For column overflow:**
- When cursor_col >= 64 and char is NOT '\n':
  advance row, reset col, scroll if needed, **then draw the character**.

This matches the JavaScript implementation exactly and produces correct
TRS-80 behavior.
