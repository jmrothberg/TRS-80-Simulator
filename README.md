# TRS-80 Model I Level II BASIC Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Live Demo](https://img.shields.io/badge/demo-GitHub_Pages-brightgreen)](https://jmrothberg.github.io/TRS-80-Simulator/)

Two faithful TRS-80 Model I Level II BASIC emulators — a **Python desktop app** (Tkinter) and a **browser-based JavaScript version** — that run vintage BASIC programs on a green-on-black 64x16 text / 128x48 graphics display. Both support tape I/O (`INPUT#-1` / `PRINT#-1`) for loading data files, and both include a built-in debugger.

The flagship demo is **SCOTTADV.BAS**, a ~580-line BASIC program that plays all 18 classic Scott Adams text adventure games from their original ScottFree `.dat` files.

![Screen layout](https://img.shields.io/badge/display-64x16_text_%7C_128x48_graphics-green)

---

## Two Versions of the Simulator

| Version | Location | How to run |
|---------|----------|------------|
| **Python (desktop)** | `TRS80_March_30_26.py` | `pip install -r requirements.txt && python TRS80_March_30_26.py` |
| **JavaScript (browser)** | `web_TRS_80/index.html` | Open in any browser — no server needed |
| **Live online demo** | `docs/index.html` | **[jmrothberg.github.io/TRS-80-Simulator](https://jmrothberg.github.io/TRS-80-Simulator/)** |

Both versions run the same BASIC programs identically. The `docs/` folder is a copy of `web_TRS_80/index.html` that GitHub Pages serves — you can't serve `web_TRS_80/` directly from Pages, so the copy is necessary.

> **Keep in sync:** After changing `web_TRS_80/index.html`, run `cp web_TRS_80/index.html docs/index.html` before committing so the live demo stays current.

Type BASIC lines directly on the green screen (immediate mode) or paste a program into the input area and press **RUN**. The web version also has a **Help** button with tabbed reference covering commands, functions, graphics, and adventure game instructions.

---

## Tape I/O — Loading Data Files

Both simulators support TRS-80 tape I/O for reading and writing sequential data. This is how programs like SCOTTADV.BAS load game data from `.dat` files.

### BASIC tape commands

```basic
INPUT#-1, V$          ' Read next line from tape into string variable V$
INPUT#-1, X           ' Read next line from tape into numeric variable X
PRINT#-1, expression  ' Write a value to tape output
```

### How to load a tape file

**Web version:**
1. Click the **Load Tape** button and select your `.dat` file
2. The screen shows `TAPE LOADED: filename (N records)`
3. Now run your BASIC program — `INPUT#-1` reads from the loaded data immediately

If you run a program that calls `INPUT#-1` before loading a tape, the simulator pauses with `INSERT TAPE` and the Load Tape button pulses amber. Click it to select a file, and the program resumes automatically.

**Python version:**
1. When a running program hits `INPUT#-1` with no tape loaded, a file dialog opens
2. Select your `.dat` file
3. The program continues reading from it

### Example: Reading a data file in BASIC

```basic
10 REM *** READ DATA FROM TAPE ***
20 INPUT#-1, N$
30 PRINT "FIRST LINE: "; N$
40 INPUT#-1, X
50 PRINT "SECOND LINE (NUMERIC): "; X
60 END
```

Load a tape file before (or when prompted), and the program reads each line sequentially. Each `INPUT#-1` call reads the next line from the file.

---

## SCOTTADV.BAS — Scott Adams Adventure Interpreter

The crown jewel of this project: a complete Scott Adams adventure engine written in TRS-80 BASIC (~580 lines). It reads the standard ScottFree `.dat` format via tape I/O and plays all 18 classic text adventures.

### How to play

**Web version** ([try it live](https://jmrothberg.github.io/TRS-80-Simulator/)):
1. Click **LOAD** → select `Scott_Adams_Basic_version/SCOTTADV.BAS`
2. Click **Load Tape** → select a `.dat` file from `Scott_Adams_Basic_version/Game_Data/`
3. Click **RUN** → press Enter when prompted → the adventure loads!

**Python version:**
1. Launch `python TRS80_March_30_26.py`
2. Type `LOAD` on the green screen → select `SCOTTADV.BAS`
3. Type `RUN` → press Enter → select the `.dat` file when the dialog appears

### Playing the game

Type two-word commands at the `WHAT SHALL I DO?` prompt:

```
GO NORTH        — move north
GET AXE         — pick up an item
DROP LAMP       — drop an item
OPEN DOOR       — interact with objects
SAY BUNYUN      — speak a magic word
```

**Shortcuts:** `N` `S` `E` `W` `U` `D` (movement), `I` (inventory), `L` (look), `SCORE`, `HELP`, `QUIT`

Collect treasures (items with `*` in their name) and bring them to the treasure room to score points.

### Available game data files

All 18 ScottFree `.dat` files are in `Scott_Adams_Basic_version/Game_Data/`:

| File | Game |
|------|------|
| `adv01.dat` | Adventureland |
| `adv02.dat` | Pirate Adventure |
| `adv03.dat` | Mission Impossible |
| `adv04.dat` | Voodoo Castle |
| `adv05.dat` | The Count |
| `adv06.dat` | Strange Odyssey |
| `adv07.dat` | Mystery Fun House |
| `adv08.dat` | Pyramid of Doom |
| `adv09.dat` | Ghost Town |
| `adv10.dat` | Savage Island Part 1 |
| `adv11.dat` | Savage Island Part 2 |
| `adv12.dat` | Golden Voyage |
| `adv13.dat` | Sorcerer of Claymorgue Castle |
| `adv14a.dat` | Return to Pirate's Isle (Part 1) |
| `adv14b.dat` | Return to Pirate's Isle (Part 2) |
| `quest1.dat` | QuestProbe: The Hulk |
| `quest2.dat` | QuestProbe: Spider-Man |
| `sampler1.dat` | Adventure Sampler |

The interpreter reads the standard ScottFree ASCII `.dat` format. Additional `.dat` files can be downloaded from the [ScottFree archive](https://www.ifarchive.org/indexes/if-archive/scott-adams/).

> **Also available:** A standalone JavaScript version of the Scott Adams engine with graphics is at **[jmrothberg.github.io/scott-adams-adventures](https://jmrothberg.github.io/scott-adams-adventures/)** ([repo](https://github.com/jmrothberg/scott-adams-adventures)). That version runs the `.dat` files directly in JavaScript without a BASIC interpreter.

---

## Project Files

| File / Folder | Purpose |
|---------------|---------|
| `TRS80_March_30_26.py` | **Python simulator** — interpreter, Tkinter UI, screen, debugger (~4,100 lines) |
| `web_TRS_80/` | **JavaScript simulator** — same BASIC interpreter in the browser (`index.html`) |
| `docs/` | Copy of `web_TRS_80/index.html` for **[GitHub Pages](https://jmrothberg.github.io/TRS-80-Simulator/)** |
| `Scott_Adams_Basic_version/` | **SCOTTADV.BAS** adventure interpreter + 18 `.dat` game data files |
| `Basic_Code_Examples/` | Sample `.bas` programs: games, tests, demos |
| `TRS80LLMSupport.py` | Optional AI companion window (Claude API, Ollama, HuggingFace) |
| `Hailo_for_Pi/` | Hailo-10H AI accelerator support for Raspberry Pi |
| `TRS80_BASIC_REFERENCE.md` | Language reference for the supported BASIC dialect |
| `requirements.txt` | Python dependencies |

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
| `hangman.bas` | Hangman word game |
| `Midway_Campaign_TRS80.bas` | *Midway Campaign* (Battle of Midway): `PRINT@` map, T/A/L/CA/CL, help; listed in the web **Examples** menu (GitHub raw) |
| `Midway_Campaign_Atari8_LISTING.txt` | ASCII listing of *Midway Campaign* detokenized from **Atari BASIC** (see note below — not for this TRS-80 simulator) |
| `complex_test_suite.bas` | Comprehensive BASIC feature tests |

Run with: click **LOAD** (or type `LOAD` on the green screen), select a `.bas` file, then click **RUN**.

**Atari 8-bit tokenized `.bas` files:** A file saved from Atari BASIC is usually **binary** (tokenized), not plain text — editors show garbage. To convert it to a readable listing, use a detokenizer such as [atariconv](https://github.com/mistalro/atariconv) (`make` in `src` produces the `atari` tool; run it on the tokenized file). The program uses Atari-specific statements (`GRAPHICS`, `POSITION`, `POKE` to Atari locations, etc.) and will **not** run in this TRS-80 simulator without a manual port.

---

## BASIC Dialect Notes

The simulator targets TRS-80 Model I Level II BASIC:

- Every program line needs a line number. Keywords must be uppercase.
- `PRINT@` uses screen positions (0-1023).
- `RND`, `RND(0)`, `RND(1)` all return a new random float 0.0–0.9999 (for probability checks). `RND(n)` where n>1 returns a random integer 1–n (for coordinates/dice).
- Comparisons return `-1` (true) or `0` (false).
- `AND`, `OR`, `NOT` work as logical operators on -1/0 values.
- `STR$(n)` includes a leading space for the sign placeholder.
- `PEEK(14400)` polls the keyboard buffer (primary method for game input).
- Multiple statements per line: `10 A=1: B=2: PRINT A+B`
- `IF ... THEN ... ELSE ...` — colons after THEN/ELSE stay in the IF clause.
- `INPUT#-1` / `PRINT#-1` for sequential tape I/O.

See `TRS80_BASIC_REFERENCE.md` for the full language reference.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` or `Ctrl+C` | BREAK — stop running program |
| `Ctrl+R` | Emergency reset to immediate mode |
| Right-click | Copy/paste context menu |
| Click green screen | Auto-recover immediate mode if lost |

---

## Debugging Tools

- **Debug window** — Toggle with the Debug button. Shows a timestamped execution trace (line number, step count, variable assignments, errors).
- **Variables window** — Live view of scalars, arrays, FOR loops, and GOSUB stack.
- **Step mode** — Single-step through execution with the STEP button.
- **LLM companion** — Send debug output or program state to an AI assistant (Claude, Ollama, or local HuggingFace models).

---

## How the Interpreter Works

The interpreter turns BASIC source text into execution through a five-stage pipeline.

### Stage 1 — Editing & Storage

The user types BASIC lines into either:
- The **green screen** (immediate mode, `>` prompt) — numbered lines are stored; bare commands execute immediately.
- The **input area** (text area below the screen) — edited as plain text, synced on every keystroke.

Lines are always kept sorted by line number.

### Stage 2 — Preprocessing

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

Colons inside quoted strings and after `THEN`/`ELSE` are preserved. All `DATA` statements are pre-scanned into `data_values[]` so `READ` can access them in program order.

### Stage 3 — Execution Loop

`run_program` builds parallel arrays of line numbers, commands, and pre-extracted keywords. `execute_next_line` walks through them, calling `execute_command()` for each line.

| Return | Meaning |
|--------|---------|
| `None` | Advance to the next line |
| `int`/`float` | Branch to that line number (GOTO, GOSUB, FOR/NEXT loop-back) |
| *sets `waiting_for_input`* | Pause — return to event loop; resume on input |

### Stage 4 — Command Dispatch

The pre-extracted keyword is looked up in the command handler table (`PRINT`, `LET`, `FOR`, `NEXT`, `GOTO`, `GOSUB`, `IF`, etc.). If no keyword matches but the line contains `=`, it's treated as an implicit `LET`.

### Stage 5 — Expression Evaluation

Expressions go through: fast-path checks → quote-map building → INKEY$ replacement → keyword translation (AND/OR/MOD/^ → Python/JS operators) → function dispatch → array substitution → scalar substitution → comparison wrapping → eval.

---

## Troubleshooting

- **Ollama models don't appear:** Make sure Ollama is running (`ollama list`).
- **Anthropic API not working:** Set `ANTHROPIC_API_KEY` in your shell environment.
- **Graphics seem too small:** Use the `2X` button (not available on Raspberry Pi).
- **Screen seems frozen:** Click the green screen or press `Ctrl+R`.
- **Tape data not loading:** Make sure you click **Load Tape** and select the file. In the web version, you can pre-load the tape before running the program.

## Building a Standalone Executable (PyInstaller)

```bash
pyinstaller --onefile --console \
    --exclude-module torch --exclude-module transformers \
    --exclude-module tensorflow --exclude-module keras \
    --exclude-module numpy --exclude-module scipy \
    --exclude-module pandas --exclude-module matplotlib \
    --exclude-module sklearn --exclude-module scikit-learn \
    --exclude-module onnxruntime --exclude-module chromadb \
    --exclude-module llama_cpp --exclude-module huggingface_hub \
    --exclude-module tokenizers --exclude-module sentencepiece \
    --exclude-module safetensors --exclude-module accelerate \
    --exclude-module tqdm --exclude-module sympy \
    --exclude-module PIL --exclude-module cv2 \
    --name TRS80 \
    TRS80_March_30_26.py
```

**macOS Gatekeeper fix** — required after every build:
```bash
xattr -cr dist/
```
Without this, macOS will block the binary from running.

**Finder double-click wrapper** — create `dist/TRS80.command`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
./TRS80
```
Then `chmod +x dist/TRS80.command`. Double-click the `.command` file in Finder to launch.

> **Note:** The LLM companion (`TRS80LLMSupport.py`) is lazy-imported at runtime, so its heavy dependencies (torch, transformers, etc.) are excluded from the build. The simulator itself runs without them. If you need LLM support in the packaged build, remove the corresponding `--exclude-module` flags and expect a ~500 MB binary.

---

## License

This project is licensed under the MIT License. See `LICENSE`.
