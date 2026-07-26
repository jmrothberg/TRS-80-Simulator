# Memory map

One flat 64K address space. `functional_model/memory_map.py` is the single
source of truth; this document is its prose form. Nothing else in the design may
contain an address literal.

## Regions

| Range | Region | Contents |
|---|---|---|
| `0000-1FFF` | System ROM | boot, console, fonts, microcode image |
| `2000-5FFF` | Program Memory | tokenized BASIC, line directory |
| `6000-7FFF` | Variable Memory | scalar slots, array descriptors |
| `8000-9FFF` | String Space | characters |
| `A000-AFFF` | Stack Area | expression, FOR and GOSUB stacks |
| `B000-B3FF` | Video Memory | 64x16 text / 128x48 graphics |
| `B400-B7FF` | I/O Registers | UART, keyboard, cursor, RNG, storage |
| `B800-BFFF` | Work RAM | buffers and system pointers |
| `C000-FFFF` | Reserved | future expansion |

## Program Memory

A line is one record:

```
[line# lo][line# hi][length][token ...][0x00]
```

`length` counts the token bytes including the terminating `0x00`, so a record is
`3 + length` bytes. Records are stored in one contiguous ascending run from
`2000`; the first free byte is in `SYSVAR_PROGRAM_END`, so there is no sentinel
line number that a real program could collide with.

Inserting or deleting a line is one block move of the tail. The **line
directory** is a scan of these records rather than a second copy of the data, so
it cannot disagree with the token stream.

## Variable Memory

| Range | Contents |
|---|---|
| `6000-77FF` | scalar slots, 4 bytes each (2048 slots) |
| `7800-7FFF` | array descriptors (implementation step 18) |

A scalar slot is `[name0][name1][value lo][value hi]`. `name0 = 0` means the
slot has never been used, which also terminates the linear search. Names follow
Level II: the first two characters are significant.

The floating point milestone widens the value field; that change happens here
and in `memory_map.py`, not throughout the design.

## Stack Area

| Address | Stack | Frame |
|---|---|---|
| `A000` | expression operands | 3 bytes: `[kind][value lo][value hi]`, 64 deep |
| `A200` | expression operators | 2 bytes: `[token][argument count]`, 64 deep |
| `A400` | FOR | 12 bytes, 32 deep |
| `A800` | GOSUB return | 4 bytes, 64 deep |

FOR frame:

```
+0  variable slot address
+2  limit
+4  step
+6  resume line record address
+8  resume token pointer
+10 name0
+11 name1
```

GOSUB frame: `[line record address][token pointer]`.

All four use the same `MemoryStack` class, so there is one stack implementation
to port to hardware.

## Video Memory

1024 bytes, `VRAM address = B000 + (cell_row * 64 + cell_col)`.

A cell holds a character code, or — with bit 7 set — six graphics blocks in bits
0..5:

```
block_num = block_y * 2 + block_x

+---+---+
| 0 | 1 |
+---+---+
| 2 | 3 |
+---+---+
| 4 | 5 |
+---+---+
```

`SET(x, y)`, `RESET(x, y)` and `POINT(x, y)` decode to

```
cell_col = x // 2      (0..63)
cell_row = y // 3      (0..15)
block_x  = x %  2      (0 or 1)
block_y  = y %  3      (0, 1, 2)
block_num = block_y * 2 + block_x
```

which is why 128x48 graphics and 64x16 text are the same memory.

## I/O Registers

| Address | Register |
|---|---|
| `B400` | UART transmit data |
| `B401` | UART receive data |
| `B402` | UART status (bit0 rx ready, bit1 tx busy) |
| `B410` | keyboard data |
| `B411` | keyboard status (bit0 key available) |
| `B420` | cursor offset low |
| `B421` | cursor offset high |
| `B430` | RNG state low |
| `B431` | RNG state high |
| `B440` | storage status (bit0 busy) |

## Work RAM

| Address | Contents |
|---|---|
| `B800` | console input line buffer (256) |
| `B900` | tokenizer output buffer (256) |
| `BA00` | direct statement buffer (256) |
| `BB00` | storage buffer (512) |
| `BFF0` | program end pointer |
| `BFF2` | DATA pointer |
| `BFF4` | DATA line record address |
| `BFF6` | current line number (0 = direct mode) |
| `BFF8` | INPUT field pointer |

The system pointers are ordinary memory, so `PRINT PEEK(49142)` reports the line
number the machine is executing. Nothing is hidden from the programmer.
