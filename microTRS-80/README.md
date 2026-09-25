# microTRS-80 for ESP32

The interpreter runs on the CrowPanel. The green window is only the keyboard and a copy of the 64×16 panel. Close that window before a reset or a file copy. It owns `/dev/ttyUSB0`.

## Just the window

BASIC is already on the board. This only opens the keyboard. Use `/usr/bin/python3`, not the `python3` inside the project `.venv`.

```sh
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

If the window says permission denied, that terminal is not in group `dialout`. Cursor's terminal is not. Run the same command in a desktop terminal.

Esc stops a running program. At `READY>`:

```basic
LOAD "STARTREK"
RUN
```

```basic
LOAD "ADVENT"
RUN
```

## Restart fresh

Same files, board reboots to `READY>`, then the window opens. Close the old window first.

```sh
/usr/bin/python3 -c 'import serial,time; s=serial.Serial("/dev/ttyUSB0",115200); s.dtr=False; s.rts=True; time.sleep(0.05); s.rts=False; time.sleep(0.3); s.close()'
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

## Load BASIC onto the board

New board, or the Python on the computer changed. Close the window first. The reset-and-Ctrl-C drops MicroPython to `>>>` while the display is still starting, which is the only time Ctrl-C is not caught by BASIC. Copy one file per command. The last reset lets `main.py` run.

```sh
cd /home/jonathan/TRS-80-Simulator/microTRS-80
/usr/bin/python3 -c 'import serial,time; s=serial.Serial("/dev/ttyUSB0",115200,timeout=0.05); s.dtr=False; s.rts=True; time.sleep(0.05); s.rts=False; end=time.time()+2.5
while time.time()<end:
 s.write(b"\x03"); time.sleep(0.05)
s.close()'
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp main.py :main.py
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp board_config.py :board_config.py
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp microtrs_hw.py :microtrs_hw.py
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp font5x8.py :font5x8.py
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp display_driver.py :display_driver.py
~/.local/bin/mpremote connect /dev/ttyUSB0 resume cp CrowPanel.py :CrowPanel.py
/usr/bin/python3 -c 'import serial,time; s=serial.Serial("/dev/ttyUSB0",115200); s.dtr=False; s.rts=True; time.sleep(0.05); s.rts=False; time.sleep(0.3); s.close()'
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

If open says permission denied, that terminal is not in group `dialout`. A normal login terminal is. Log out and back in once if a new terminal still is not.

This edition runs the BASIC interpreter **on the ESP32**, using MicroPython.
It has a 64×16 character screen buffer and a separate 128×48 graphics buffer.
It accepts keyboard input over USB serial and can render to an attached LCD
through the board-specific display driver interface. Programs and tape data
are read and written on a microSD card.

## Board requirements

An ESP32-S3 with PSRAM and 8 MB or more of flash is recommended for larger
programs. Use a MicroPython firmware build for the **exact** board. The SD
socket, 4-inch LCD controller, LCD bus, touch controller, and speaker pins vary
between boards. Set the SD and speaker GPIOs in `board_config.py`. To enable
the LCD, add `display_driver.py` with a `create_display()` function that returns
an initialized driver with `fill(color)` and
`fill_rect(x, y, width, height, color)` methods and optional `show()`.
Set `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` to the LCD's pixel dimensions.
The included `microtrs_hw.py` draws 5×8 glyphs and graphics pixels in a
480×320 viewport by default. A particular LCD still needs its own
initialization code and bus driver; the board model is needed to supply it.

## Installation

1. Flash MicroPython for your board. Connect a USB serial terminal.
2. Copy `main.py`, `board_config.py`, `microtrs_hw.py`, and `font5x8.py` to the
   board's root filesystem. For the CrowPanel 5.79 also copy `display_driver.py`
   and `CrowPanel.py`. From this folder:

   ```sh
   mpremote connect auto fs cp main.py board_config.py microtrs_hw.py font5x8.py display_driver.py CrowPanel.py :
   ```

3. Fill in `board_config.py` for your SD pins and optional audio pin; add
   `display_driver.py` for your LCD and copy it to the board.
4. Reset the ESP32, or use **Restart fresh** above. At `READY>`, enter numbered BASIC lines or commands.
   Esc in the window interrupts execution.

The window shows the same 64×16 the panel last drew, not the serial monitor. The panel updates when a program waits for input, clears the screen, or stops. Esc in that window breaks a running program.

The CrowPanel microSD uses the same FAT32 cards as the FPGA. `LOAD "STARTREK"`
reads `STARTREK.BAS` (then `.DAT`, `.JMR`, `.TXT`). `SAVE "FOO"` writes
`FOO.BAS`. `DIR` lists the card root. `REMOVE "FOO"` deletes it.

If the board firmware already mounts the SD card at `/sd`, leave
`SD_SPI_PINS = None`. For a board with an SPI SD slot, set the tuple in the
order `(SCK, MOSI, MISO, CS)`. Some boards use SDMMC rather than SPI; mount
those cards in the board startup code at `/sd`, and leave the tuple unset.

Example:

```basic
10 CLS
20 COLOR 2,0
30 FOR I=1 TO 5
40 PRINT "HELLO ";I
50 SET(I,I,12)
60 NEXT I
70 END
RUN
SAVE "HELLO.BAS"
NEW
LOAD "HELLO.BAS"
RUN
```

The window shows the same 64×16 text the panel is showing. `PRINT@` writes directly into that buffer.
`SCREEN` dumps that buffer to the serial terminal. The panel updates when the program waits for input, on `CLS`, and when a command or program finishes, so a long program is not one full panel update per `PRINT`. Rapid
graphics loops do not yet animate smoothly. `INPUT` uses the serial keyboard. `INKEY$` and
`PEEK(14400)` poll the serial port when MicroPython exposes `select.poll` for
the USB stream. Touch is not configured without a board model.

## SD commands

`SAVE "FILE.BAS"` and `LOAD "FILE.BAS"` store numbered source lines in the
SD root. `TAPE "GAME.DAT"` opens an input tape for `INPUT#-1,V$` and
`INPUT#-1,N`. `TAPEOUT "FILE.DAT"` opens an output tape for
`PRINT#-1,expression`; `TAPECLOSE` closes it. `OPEN "I",#1,"FILE.DAT"`,
`OPEN "O",#1,"FILE.DAT"`, `LINE INPUT#1,V$`, `PRINT#1,expression`, and
`CLOSE` support sequential file access. Files are restricted to the SD root.
Programs are held in RAM during execution, and `SAVE` is needed to retain
changes after a reset.

## Language coverage and limits

Supported: `LET`, `PRINT`, `PRINT@`, `CLS`, `COLOR`, `SET`/`RESET`/`POINT`/
`COLORAT`, `IF ... THEN ... ELSE`, `FOR`/`NEXT`, `ON ... GOTO`/`GOSUB`,
`GOTO`, `GOSUB`/`RETURN`, `INPUT`, `DIM`, `DATA`/`READ`/`RESTORE`, `POKE`
for text memory, `PEEK` for text memory and keyboard, `SOUND`, `BEEP`,
`RANDOM`, `REM`, `STOP`, and `END`. Expressions include scalar variables,
one-dimensional arrays, numeric and string operations, comparison values
of -1 or 0, bitwise `AND`/`OR`/`NOT`, math functions, string functions,
`RND(0)`/`RND(n)`, `INKEY$`, and `POS`.

This remains a **partial port** of the much larger desktop interpreter. It
does not implement DEF FN, ON ERROR, PRINT USING, every Level II numeric
conversion and error code, two-dimensional arrays, in-memory debugger,
desktop AI companion, or full compatibility with SCOTTADV.BAS. Some programs
will need those features before they run. Audio tones currently block while
they play; the desktop sound queue is not present. A PSRAM board helps with
large program memory, but no maximum program size is guaranteed.

Run smoke checks before copying to the board:

```sh
python microTRS-80/smoke_test.py
```
