# microTRS-80 for ESP32

The interpreter runs on the CrowPanel. The window on the computer is only a keyboard and a copy of the 64×16 panel. Close that window before a reset or a file copy. It owns `/dev/ttyUSB0`.

Use `/usr/bin/python3`, not the `python3` inside the project `.venv`. If a command says permission denied, that terminal is not in group `dialout`. A normal desktop terminal is. Cursor's terminal is not.

## Stored in flash

The BASIC interpreter is the Python files on the ESP32 flash chip. Copying them once writes them into that flash. Unplugging power leaves them there. The next time the panel gets power, MicroPython starts and runs `main.py` by itself. Wait for the e-ink refresh. The panel then shows:

```text
TRS-80 BASIC
Type HELP.
READY
>
```

`READY` is its own line, and only at startup and when a program breaks. The next line is `>`.

The window on the computer is not stored on the board. Open it again when you want that copy of the screen. A BASIC program you typed is in RAM until you `SAVE` it to the microSD card. The SD card keeps its files across power loss too. `SAVE` is what keeps a program. The flash copy is what keeps the interpreter.

## Open the window

BASIC is already on the board. This only opens the keyboard and the screen copy.

```sh
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

Esc stops a running program. At the `>` prompt:

```basic
LOAD "STARTREK"
RUN
```

```basic
LOAD "ADVENT"
RUN
```

## Set up a new board

CrowPanel 5.79 (ESP32-S3, 8 MB flash, 8 MB octal PSRAM). Close any window that has `/dev/ttyUSB0` first.

1. Flash MicroPython for `ESP32_GENERIC_S3` with **octal** PSRAM (`SPIRAM_OCT`). The plain S3 image and the quad-PSRAM image will not match this module. Erase is only for a board that does not already have this BASIC. It wipes the flash filesystem.

```sh
cd /home/jonathan/TRS-80-Simulator/microTRS-80
esptool.py --chip esp32s3 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyUSB0 --baud 460800 write_flash -z 0 ESP32_GENERIC_S3-SPIRAM_OCT.bin
```

2. A new MicroPython flash has no `main.py`, so the board sits at the `>>>` prompt and the copy can go straight on. One file per command. These six files are the interpreter.

```sh
~/.local/bin/mpremote connect /dev/ttyUSB0 cp main.py :main.py
~/.local/bin/mpremote connect /dev/ttyUSB0 cp board_config.py :board_config.py
~/.local/bin/mpremote connect /dev/ttyUSB0 cp microtrs_hw.py :microtrs_hw.py
~/.local/bin/mpremote connect /dev/ttyUSB0 cp font5x8.py :font5x8.py
~/.local/bin/mpremote connect /dev/ttyUSB0 cp display_driver.py :display_driver.py
~/.local/bin/mpremote connect /dev/ttyUSB0 cp CrowPanel.py :CrowPanel.py
```

3. Reset. `main.py` runs from flash and stays there after every power cycle.

```sh
/usr/bin/python3 -c 'import serial,time; s=serial.Serial("/dev/ttyUSB0",115200); s.dtr=False; s.rts=True; time.sleep(0.05); s.rts=False; time.sleep(0.3); s.close()'
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

## Update the Python on a board that already runs BASIC

Close the window first. BASIC catches Ctrl-C once it is at the prompt, so the reset below sends Ctrl-C while the display is still starting. That is the moment MicroPython will stop at `>>>`. Copy one file per command. The last reset lets `main.py` run again from flash.

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

## Restart

Same flash contents. The board boots to `READY` and `>`, then the window opens. Close the old window first.

```sh
/usr/bin/python3 -c 'import serial,time; s=serial.Serial("/dev/ttyUSB0",115200); s.dtr=False; s.rts=True; time.sleep(0.05); s.rts=False; time.sleep(0.3); s.close()'
/usr/bin/python3 /home/jonathan/TRS-80-Simulator/microTRS-80/console_gui.py
```

## PS/2 keyboard

A keyboard on the GPIO header types into BASIC the same way the window does. Clock is IO15 (`PS2_CLOCK_PIN`) and data is IO16 (`PS2_DATA_PIN`) in `board_config.py`. Letters are capitals. Esc or Ctrl-C stops a running program. Wire the keyboard, then reset the panel so `main.py` sees it from power-up.

Power comes from the header **3.3 V** pin, and ground from GND. The ESP32 pins are 3.3 V pins. The keyboard pulls clock and data up to whatever voltage is on its power pin, so that power pin has to be 3.3 V. Leave the second port empty (mouse data and mouse clock).

Each plug below is the same four signals. A keyboard that only speaks USB stays silent on this wiring. A round PS/2 keyboard works. So does an older USB keyboard that types through a passive purple PS/2 adapter, because that adapter is just these four wires.

### Labeled PS/2 breakout (D1, C1, GND, VB)

```text
  breakout                         CrowPanel header
  --------                         ----------------
  C1   clock  -------------------> IO15
  D1   data   -------------------> IO16
  GND         -------------------> GND
  VB   power  -------------------> 3.3 V

  D2 and C2 are the mouse port. Leave them empty.
```

### USB breakout

Female USB-A, the four pins a passive PS/2 adapter uses. D+ is clock and D− is data.

```text
  USB breakout                     CrowPanel header
  ------------                     ----------------
  D+   (often green)  -----------> IO15   clock
  D-   (often white)  -----------> IO16   data
  GND  (often black)  -----------> GND
  VCC  (often red)    -----------> 3.3 V

  Looking into the USB-A socket, tongue down, left to right:

      1 VCC    2 D-    3 D+    4 GND
      (3.3 V)  (IO16)  (IO15)  (GND)
```

### Round PS/2 plug (6-pin mini-DIN)

Pin 1 is data, pin 5 is clock, pin 4 is power, pin 3 is ground. Pins 2 and 6 are the mouse wires on a combo plug. Leave them empty.

```text
  round plug                       CrowPanel header
  ----------                       ----------------
  pin 5  clock  -----------------> IO15
  pin 1  data   -----------------> IO16
  pin 3  GND    -----------------> GND
  pin 4  VCC    -----------------> 3.3 V
  pin 2          (empty)
  pin 6          (empty)
```

The keyboard cable's plug is the male, pins facing you. A round socket on a breakout is the female, looking into the holes. The two faces are mirror images. Follow the pin numbers.

```text
  male plug, pins toward you          female socket, looking into the holes

        6       5                           5       6

     4             3                     3             4

        2       1                           1       2

     pin 1 data -> IO16                 pin 1 data -> IO16
     pin 5 clock -> IO15                pin 5 clock -> IO15
     pin 3 GND, pin 4 3.3 V             pin 3 GND, pin 4 3.3 V
```

This edition runs the BASIC interpreter **on the ESP32**, using MicroPython.
It has a 64×16 character screen buffer and a separate 128×48 graphics buffer.
It accepts keyboard input over USB serial and from a PS/2 keyboard on the GPIO header, and can render to an attached LCD
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
Set `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` to the panel's pixel dimensions.
On this CrowPanel that is **792 × 272**.

### Text and graphics scaling

The console is always a logical **64 × 16** character grid. The draw path in
`microtrs_hw.py` picks cell size from the panel:

- `scale_x = DISPLAY_WIDTH // 64` (here `792 // 64` → **12**)
- `scale_y = DISPLAY_HEIGHT // 16` (here `272 // 16` → **17**)
- Text block size: `64 * scale_x` by `16 * scale_y` → **768 × 272**
- Centering: leftover pixels are split left/right (here **12** on each side).
  Top/bottom leftover is 0 on this panel because `16 * 17` fills the height.

So the glyphs use **768 of 792** horizontal pixels, not 640. A scale of 10
would be 640 wide and leave ~152 px free for a side badge; that is not what
runs on the board today. The PC window may show a decorative TRS-80 badge for
layout experiments; that does not change the panel math until the draw path
is updated on purpose.

`SET` / `RESET` / `POINT` use the same `scale_x` / `scale_y`. The Level II
graphics grid is **128 × 48** (two pixels across each character cell, three
down), so each graphics pixel is drawn as:

- width `scale_x // 2`, height `scale_y // 3`
- origin `left + x * (scale_x // 2)`, `top + y * (scale_y // 3)`

Text cells and `SET` pixels therefore stay locked to the same center and scale.

The included `microtrs_hw.py` draws 5×8 glyphs and those graphics pixels into
that centered viewport. A particular panel still needs its own
initialization code and bus driver; the board model is needed to supply it.

## Installation

For this CrowPanel, follow **Set up a new board** above. That flash of MicroPython plus the six `mpremote` copies is the whole install. The files stay in flash after power is removed.

On a different ESP32, fill in `board_config.py` for the SD pins and the optional speaker pin, and supply a `display_driver.py` whose `create_display()` returns a driver with `fill` and `fill_rect`. Copy those files the same way, then reset. At the `>` prompt, enter numbered BASIC lines or commands. Esc in the window interrupts execution.

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
