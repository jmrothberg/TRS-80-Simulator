# TRS-80 BASIC Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project is a desktop TRS-80 Model I Level II BASIC simulator written in Python with a Tkinter UI. It is aimed at running and debugging vintage-style BASIC programs while keeping the workflow practical on a modern machine.

## Current Code At A Glance

- `TRS80_March_17_26.py` is the main simulator application.
- `TRS80LLMSupport.py` provides the optional companion window for code help and debugging help.
- `Basic_Code_Examples/` contains working sample programs and game experiments for the simulator.
- The simulator currently uses a 128x48 graphics screen, a 64x16 text layout, and a green-on-black TRS-80 style display.

## What The Simulator Currently Supports

- Immediate mode and stored-program editing in the main input area.
- Program execution controls for `RUN`, `STOP`, `STEP`, and `LIST`.
- Toolbar actions that now match BASIC terminology more closely:
  - `CLEAR` clears variables and runtime state.
  - `NEW` clears the current program and memory state.
  - `SAVE` and `LOAD` work from the toolbar.
- Numeric line sorting for loaded, listed, and saved BASIC programs.
- Multiple BASIC statements on a single line separated by colons.
- Debug output with BASIC line context and clearer execution/error tracing.
- A separate program-state window for variables and arrays.
- Optional `2X` screen scaling on non-Raspberry Pi systems.
- Keyboard polling support used by games via `PEEK(14400)`.

## BASIC Dialect Notes

The simulator is intentionally closer to TRS-80 Model I Level II BASIC than to modern BASIC dialects. A few important behavior rules matter when writing programs for it:

- Every program line should have a line number.
- Keywords should be uppercase.
- `IF ... THEN` with a destination line should use `GOTO`.
- `PRINT@` uses 1-based screen positions.
- `RND(n)` is treated as `1` through `n`.
- `INT(x)` is expected to behave like TRS-80 BASIC floor behavior.
- `PEEK(14400)` is the practical way to poll keys for action games in this simulator.

## Graphics And Runtime Behavior

- Graphics commands include `SET`, `RESET`, `POINT`, and `CLS`.
- The simulator tracks active pixels and batches graphics updates to reduce redraw cost.
- Example arcade-style BASIC programs use erase-and-redraw loops instead of full-screen `CLS` in the main frame loop for smoother animation.
- Recent game work in this repo includes `asteroid.bas`, `Snake.bas`, `Invaders_V.bas`, and `Invaders_VI.bas`.

## Debugging Tools

- A dedicated debug window can show execution progress and runtime diagnostics.
- The debug UI includes search, copy, program analysis, and buttons to send debug/state context to the companion window.
- A separate variables window shows current program state while debugging.
- The debug output has been tuned to be more useful for both a human reader and an LLM helper.

## LLM Companion

The optional companion window can help write and debug TRS-80 BASIC code. The current code supports:

- Claude via Anthropic API
- Ollama local models
- Local Hugging Face / Transformers models

The companion window includes:

- Separate input and output panes
- Model selection
- Temperature and length controls
- `Send`, `Transfer`, and `Append` actions
- Prompting tuned for this simulator's stricter BASIC rules

## Running The Simulator

1. Install dependencies:
   ```bash
   pip install -r TRS_80_requirements.txt
   ```
2. Launch the main application:
   ```bash
   python TRS80_March_17_26.py
   ```

## Example Programs In This Repo

- `Basic_Code_Examples/Snake.bas`
- `Basic_Code_Examples/asteroid.bas`
- `Basic_Code_Examples/Invaders_IV.bas`
- `Basic_Code_Examples/Invaders_V.bas`
- `Basic_Code_Examples/Invaders_VI.bas`
- `Basic_Code_Examples/Line_by_line_test.bas`

These are useful both as demos and as compatibility tests for graphics, input, timing, and BASIC syntax edge cases.

## Main Files

- `TRS80_March_17_26.py`: main simulator, interpreter, UI, debug window, and graphics handling
- `TRS80LLMSupport.py`: companion/assistant UI and model integration
- `TRS80_BASIC_REFERENCE.md`: project reference notes for TRS-80 BASIC behavior
- `Basic_Code_Examples/`: sample BASIC programs

## Troubleshooting

### Ollama models do not appear

- Make sure Ollama is installed and running.
- Check available models with `ollama list`.

### Anthropic access is not working

- Set `ANTHROPIC_API_KEY` in the shell environment before launching the simulator.

### Graphics seem too small

- Use the `2X` button when available.

## License

This project is licensed under the MIT License. See `LICENSE`.
