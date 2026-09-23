# ESP32 MicroPython TRS-80 BASIC

This is a standalone microcontroller implementation of the core interpreter in
`TRS80_Aug_10_26.py`. BASIC statements execute **on the ESP32**. The host computer
provides only a USB serial terminal; no desktop Python process is required.

## Hardware and installation

Use an ESP32-S3 development board with at least 8 MB flash and a MicroPython
build for that board. The code itself also works on many other ESP32 boards if
they have sufficient free RAM and a working serial REPL. No display, keyboard,
SD card, or external libraries are required for this first edition.

1. Flash current MicroPython firmware for your specific ESP32 board.
2. Copy `main.py` to the board as `main.py`, for example with
   `mpremote connect auto fs cp esp32/main.py :main.py` from the repository root.
3. Reset the board and connect a USB serial terminal at the baud rate used by
   your board firmware. The `READY>` prompt accepts numbered BASIC lines.

Example:

```basic
10 CLS
20 FOR I=1 TO 5
30 PRINT "HELLO ";I
40 NEXT I
50 END
RUN
```

`Ctrl-C` interrupts a running program. `LIST`, `RUN`, `RUN line`, `NEW`,
`SCREEN`, and `HELP` are immediate commands. Program lines live in RAM and are
lost on reset. The `SCREEN` command dumps the 64×16 text buffer; `PRINT@` writes
to that buffer. `SET`, `RESET`, and `POINT` use a separate 128×48 bitmapped
graphics buffer. These buffers are available to future LCD/VGA drivers but the
serial console does not render graphics pixels.

Implemented statements include `LET`, `PRINT`, `PRINT@`, `CLS`, `IF ... THEN ...
ELSE`, `FOR`/`NEXT`, `GOTO`, `GOSUB`/`RETURN`, `INPUT`, `DIM`, `DATA`/`READ`/
`RESTORE`, `SET`/`RESET`, `REM`, `STOP`, and `END`. Expressions support numbers,
strings, scalar variables, one-dimensional arrays, arithmetic, comparisons
(true is -1), bitwise `AND`/`OR`/`NOT`, `RND(0)` and `RND(n)`, common math
functions, string functions, and `POINT`.

## Current limits

This is an initial embedded port, **not yet feature compatible** with the
desktop simulator or its Scott Adams adventure program. It has no GUI,
debugger, tape or disk I/O, color, sound, `PEEK`/`POKE`, `INKEY$`, persistent
program storage, or frame display driver. Complex programs that depend on
these features need further porting. Input is blocking, and program size is
bounded by available heap. The execution speed is intentionally unthrottled.

To run the core smoke checks on a computer before flashing:

```sh
python esp32/smoke_test.py
```
