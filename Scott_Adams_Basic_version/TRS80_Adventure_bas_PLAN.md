# Plan: TRS-80 Level II BASIC Adventure Interpreter

## Context

The repository contains 18 Scott Adams adventure games as ScottFree-format `.dat` files (ASCII text with quoted strings and integers). The current engine is a JavaScript/HTML reimplementation. This plan describes a **TRS-80 Level II BASIC program** that can load these `.dat` files and play the games — no graphics, no WebLLM, just a classic text adventure experience on a TRS-80 (or emulator) running Level II BASIC with disk access.

No original BASIC source exists in this repo. The original Scott Adams BASIC driver used a different (binary) data format. This would be a new BASIC program that reads the ScottFree text format directly.

## File to Create

`trs80/SCOTTADV.BAS` — A single TRS-80 Level II BASIC program (~400-500 lines)

## Program Design

### Data Format

The `.dat` files are ASCII text with the following structure:
- 12 header integers: ID, numItems, numActions, numWords, numRooms, maxCarry, startRoom, numTreasures, wordLen, lightTime, numMessages, treasureRoom
- Action table: (numActions+1) entries, each with 8 integers (vocab, cond[0-4], act[0-1])
- Vocabulary: (numWords+1) pairs of quoted strings (verb, noun)
- Rooms: (numRooms+1) entries with 6 exit integers + quoted description string
- Messages: (numMessages+1) quoted strings
- Items: (numItems+1) entries with quoted description + integer location
- Action comments: (numActions+1) quoted strings (skipped)
- Trailer: version integer, adventure number integer

Quoted strings use double quotes. Integers are separated by whitespace.

### Key Design Decisions

- **`DEFINT A-Z`** — All numerics as 2-byte integers (saves ~60% memory vs floating point)
- **Requires Disk BASIC** (TRSDOS/LDOS) for `OPEN`/`LINE INPUT#`/`CLOSE`
- **48K RAM minimum** — arrays dimensioned dynamically from header values
- **Character-by-character tokenizer** to handle quoted strings (including multi-line) and integers from the `.dat` file
- **Carried items stored as location -1**, destroyed as 0 (matching the JS engine)
- **64-column display** — TRS-80 Model I/III screen is 64x16

### Line Number Layout

| Lines | Purpose |
|-------|---------|
| 10-99 | Init, DEFINT, title screen, file selection |
| 100-299 | Load game data from .dat file |
| 500-599 | Post-load setup (extract autoget words, initialize state) |
| 1000-1199 | Main game loop (light tracking, redraw, input, dispatch) |
| 1200-1399 | Input parsing (uppercase, expand shortcuts, word lookup) |
| 1400-1599 | Action processing (iterate actions, check conditions, execute) |
| 2000-2099 | Condition checker (20 condition types via ON...GOTO) |
| 2200-2599 | Opcode execution (opcodes 52-87) |
| 2600-2699 | LOOK subroutine (room description, items, exits) |
| 2800-2899 | INVENTORY subroutine |
| 2900-2999 | SCORE subroutine |
| 3000-3049 | GO direction subroutine |
| 3050-3099 | GET subroutine |
| 3100-3149 | DROP subroutine |
| 3200-3299 | Save/Load game to disk |
| 3300-3399 | Token reader (core tokenizer from file) |

### Arrays

| Array | Size | Purpose |
|-------|------|---------|
| `AC%(NA,7)` | dynamic | Action table (vocab + 5 conds + 2 acts) |
| `EX%(NR,5)` | dynamic | Room exits (6 directions: N,S,E,W,U,D) |
| `IL%(NI)` | dynamic | Item current locations |
| `IS%(NI)` | dynamic | Item starting locations (for condition 17/18) |
| `VB$(NW)` | dynamic | Verb vocabulary |
| `NN$(NW)` | dynamic | Noun vocabulary |
| `RD$(NR)` | dynamic | Room descriptions |
| `MS$(MM)` | dynamic | Messages |
| `ID$(NI)` | dynamic | Item descriptions |
| `IG$(NI)` | dynamic | Item autoget words (extracted from `/WORD/` in desc) |
| `FL%(31)` | 32 | Boolean flags |
| `CT%(15)` | 16 | Counters |
| `SR%(15)` | 16 | Saved room registers |
| `PP%(4)` | 5 | Action parameters (temp, extracted from conditions) |

### Core Engine Logic

Reference implementation: `index.html` lines 88-549 (JavaScript)

#### Tokenizer (Line 3300+)
- Maintain a line buffer `LB$` and position pointer `LP`
- When buffer exhausted, read next line with `LINE INPUT#1,LB$`
- Skip whitespace, then:
  - If `"`: read quoted string until closing `"` (handling multi-line by reading more lines)
  - If digit or `-`: read integer, return via `VAL()`
- Returns: `TT` (0=integer, 1=string), `TV` (integer value), `TK$` (string value)

#### Action Processing (Lines 1400-1599)
- Iterate all actions (0 to NA)
- Decode verb/noun from vocab: `AV = vocab \ 150`, `AN = vocab - AV * 150`
- For auto-actions (verb=0): noun value is random % chance of firing
- Check 5 conditions: `code = cond MOD 20`, `value = cond \ 20`
- If code=0, value goes to parameter list; otherwise check condition
- Decode 4 sub-actions from 2 packed integers: `INT(x/150)` and `x MOD 150`
- Sub-actions 1-51: print `message[n]`
- Sub-actions 52-87: execute opcode
- Sub-actions 102+: print `message[n-50]`
- Sub-action 73: continue flag (chain to next matching action)

#### Condition Types (20 types, Lines 2000-2099)

| Code | Condition |
|------|-----------|
| 0 | Parameter extraction (value pushed to param list) |
| 1 | Item VAL is carried (location = -1) |
| 2 | Item VAL is in current room |
| 3 | Item VAL is available (carried or in room) |
| 4 | Player is in room VAL |
| 5 | Item VAL is NOT in current room |
| 6 | Item VAL is NOT carried |
| 7 | Player is NOT in room VAL |
| 8 | Flag VAL is set |
| 9 | Flag VAL is not set |
| 10 | Player is carrying at least one item |
| 11 | Player is carrying nothing |
| 12 | Item VAL is not available (not carried and not in room) |
| 13 | Item VAL is not destroyed (location != 0) |
| 14 | Item VAL is destroyed (location = 0) |
| 15 | Current counter <= VAL |
| 16 | Current counter > VAL |
| 17 | Item VAL is at its original starting location |
| 18 | Item VAL is NOT at its original starting location |
| 19 | Current counter = VAL |

#### Action Opcodes (36 opcodes, Lines 2200-2599)

| Opcode | Action | Params |
|--------|--------|--------|
| 52 | Auto-GET by last noun (search items for matching autoget word) | 0 |
| 53 | Auto-DROP by last noun | 0 |
| 54 | Move player to room | 1 (room#) |
| 55 | Destroy item (set location to 0) | 1 (item#) |
| 56 | Set dark flag (flag 15 = true) | 0 |
| 57 | Clear dark flag (flag 15 = false) | 0 |
| 58 | Set flag | 1 (flag#) |
| 59 | Destroy item (same as 55) | 1 (item#) |
| 60 | Clear flag | 1 (flag#) |
| 61 | Die — print "I'm dead...", move to last room, clear dark | 0 |
| 62 | Put item in room | 2 (item#, room#) |
| 63 | Game over (set dead flag) | 0 |
| 64 | Look (describe current room) | 0 |
| 65 | Score (count treasures in treasure room) | 0 |
| 66 | Inventory (list carried items) | 0 |
| 67 | Set flag 0 | 0 |
| 68 | Clear flag 0 | 0 |
| 69 | Refill lamp (reset light time to original value) | 0 |
| 70 | Clear screen (CLS on TRS-80) | 0 |
| 71 | Save game (write state to disk) | 0 |
| 72 | Swap two items' locations | 2 (item#, item#) |
| 73 | Continue (chain to next action — handled as flag) | 0 |
| 74 | Superget (pick up item ignoring carry limit) | 1 (item#) |
| 75 | Put item with another item (copy location) | 2 (item#, item#) |
| 76 | Look (same as 64) | 0 |
| 77 | Decrement current counter | 0 |
| 78 | Print current counter value | 0 |
| 79 | Set current counter to value | 1 (value) |
| 80 | Swap player location with saved room (current counter index) | 0 |
| 81 | Select counter register | 1 (counter#) |
| 82 | Add value to current counter | 1 (value) |
| 83 | Subtract value from current counter | 1 (value) |
| 84 | Print last noun | 0 |
| 85 | Print last noun + newline | 0 |
| 86 | Print newline | 0 |
| 87 | Swap player location with specific saved room | 1 (slot#) |

#### Word Matching
- Only first `WL` characters compared (typically 3)
- Vocabulary entries starting with `*` are aliases — they share the word group index of the preceding non-`*` entry
- Verb 1 = GO, Nouns 1-6 = NORTH/SOUTH/EAST/WEST/UP/DOWN
- Verb 10 = GET, Verb 18 = DROP (built-in fallbacks)

#### Command Shortcuts
- N/S/E/W/U/D → GO NORTH/SOUTH/EAST/WEST/UP/DOWN
- I → INVENTORY
- L → LOOK

### Game Selection Menu

On startup, display a numbered menu of all 18 games:

```
 1. Adventureland          (adv01.dat)
 2. Pirate Adventure       (adv02.dat)
 3. Mission Impossible     (adv03.dat)
 4. Voodoo Castle          (adv04.dat)
 5. The Count              (adv05.dat)
 6. Strange Odyssey        (adv06.dat)
 7. Mystery Fun House      (adv07.dat)
 8. Pyramid of Doom        (adv08.dat)
 9. Ghost Town             (adv09.dat)
10. Savage Island Part 1   (adv10.dat)
11. Savage Island Part 2   (adv11.dat)
12. Golden Voyage          (adv12.dat)
13. Sorcerer of Claymorgue (adv13.dat)
14. Return to Pirate's Isle(adv14a.dat)
15. Buckaroo Banzai        (adv14b.dat)
16. Questprobe: Hulk       (quest1.dat)
17. Questprobe: Spider-Man (quest2.dat)
18. Mini Adventure Sampler (sampler1.dat)
```

### Memory Estimate for Adventureland (adv01)

- Action table: 170 actions × 8 ints × 2 bytes = ~2,720 bytes
- Room exits: 34 rooms × 6 ints × 2 bytes = ~408 bytes
- Item locations: 66 items × 2 arrays × 2 bytes = ~264 bytes
- Flags/counters/saved: 64 × 2 bytes = ~128 bytes
- Strings (vocab 140 + rooms 34 + messages 76 + items 132): ~4,000 bytes
- BASIC program text: ~8,000-10,000 bytes
- **Total: ~16-18 KB** — fits comfortably in 48K

### TRS-80 Compatibility Notes

1. **Requires Disk BASIC** — Cassette BASIC has no file I/O
2. **Model I Level II, Model III, or Model 4** with floppy disk
3. **No INSTR on Model I** — string searching uses MID$ character loop
4. **`\` for integer division** (faster than `INT(X/Y)` with DEFINT)
5. **`RND(N)` returns 1 to N** — auto-action chance: `IF RND(100)>AN THEN skip`
6. **Boolean expressions return -1/0** (true/false) — nonzero is truthy for IF
7. **240-character line limit** — long ON...GOTO lines must be split
8. **Uppercase keyboard** — TRS-80 naturally produces uppercase
9. **Line endings** — .dat files may need LF→CR conversion for TRS-80 disk

### Save/Load Implementation

Save game state to a sequential file `SAVE.DAT` on disk:
- Player location, current counter index, light time
- All item locations
- All 32 flags
- All 16 counters
- All 16 saved rooms

### Dat File Transfer

The `.dat` files must be transferred to TRS-80 disk format:
- They are plain ASCII text, suitable for serial transfer
- Line endings may need conversion (Unix LF → CR)
- Tools: TRS-80 Tool Shed, cpmtools, or serial transfer utilities
- On emulators: mount host directory or import files directly

## Verification Plan

1. Load `sampler1.dat` — verify all data reads without errors
2. Load `adv01.dat` (Adventureland) — verify room descriptions, items, exits display correctly
3. Test commands: N, S, E, W, GET, DROP, INVENTORY, LOOK, SCORE
4. Test auto-actions fire (random events like chigger bites)
5. Test save/load game state
6. Verify game completion is possible (score command, treasure counting)
7. Test on a TRS-80 emulator (e.g., trs80gp, SDLTRS)

## Status

**Plan complete — BASIC program implementation pending.**
