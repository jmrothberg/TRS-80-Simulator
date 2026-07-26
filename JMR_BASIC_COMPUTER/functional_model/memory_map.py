"""Memory map for the JMR BASIC Computer.

Constitution, MEMORY section:

    Memory map is documented.
    Never hard-code addresses throughout the design.

This module is the *only* place where an address literal may appear.  Every
other module imports the symbol it needs from here.  When the Python Hardware
Model and the SystemVerilog are written they consume the same map, so a region
can be moved in one place and the whole computer follows.

The map matches the MEMORY MAP (SUMMARY) panel of the architecture diagram.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Top level regions (see docs/MEMORY_MAP.md)
# --------------------------------------------------------------------------

ADDRESS_SPACE = 0x10000

SYSTEM_ROM_BASE = 0x0000  # Boot, console, fonts, microcode image
SYSTEM_ROM_TOP = 0x1FFF

PROGRAM_BASE = 0x2000  # Tokenized BASIC program (line directory + tokens)
PROGRAM_TOP = 0x5FFF

VARIABLE_BASE = 0x6000  # Scalar variables, array descriptors
VARIABLE_TOP = 0x7FFF

STRING_BASE = 0x8000  # String space (characters)
STRING_TOP = 0x9FFF

STACK_BASE = 0xA000  # Expression / FOR / GOSUB stacks
STACK_TOP = 0xAFFF

VRAM_BASE = 0xB000  # 64x16 text = 128x48 semigraphics
VRAM_TOP = 0xB3FF

IO_BASE = 0xB400  # Device registers
IO_TOP = 0xB7FF

WORK_RAM_BASE = 0xB800  # Buffers, system pointers
WORK_RAM_TOP = 0xBFFF

RESERVED_BASE = 0xC000  # Reserved / future expansion
RESERVED_TOP = 0xFFFF


# --------------------------------------------------------------------------
# Program memory
# --------------------------------------------------------------------------
# A stored line is one record:
#
#     [line# lo][line# hi][length][token ...][0x00 end of statement]
#
# `length` counts the token bytes including the terminating 0x00, so the whole
# record occupies LINE_HEADER_SIZE + length bytes.  Records are held in
# ascending line-number order with no gaps; the end of the program is marked by
# the SYSVAR_PROGRAM_END pointer.

LINE_HEADER_SIZE = 3
LINE_NUMBER_MAX = 65529
PROGRAM_SIZE = PROGRAM_TOP - PROGRAM_BASE + 1


# --------------------------------------------------------------------------
# Variable memory
# --------------------------------------------------------------------------
# One scalar slot is four bytes:
#
#     [name0][name1][value lo][value hi]
#
# name0 is the letter, name1 the optional second character (0 when absent).
# A slot whose name0 is 0 has never been allocated, which also terminates the
# linear search.  Stage 1 is 16-bit signed integer BASIC, so the value is two
# bytes; the floating point milestone widens the slot and updates this map.

SCALAR_SLOT_SIZE = 4
SCALAR_TABLE_BASE = VARIABLE_BASE
SCALAR_TABLE_TOP = 0x77FF
SCALAR_SLOT_COUNT = (SCALAR_TABLE_TOP - SCALAR_TABLE_BASE + 1) // SCALAR_SLOT_SIZE

# Array descriptors live above the scalars; the Array Engine milestone fills
# this in (implementation order step 18).
ARRAY_TABLE_BASE = 0x7800
ARRAY_TABLE_TOP = VARIABLE_TOP


# --------------------------------------------------------------------------
# Stacks
# --------------------------------------------------------------------------
# The Expression Engine keeps operands and operators in memory rather than in
# Python data structures so the hardware model can use the same layout.

EXPR_OPERAND_STACK_BASE = 0xA000
EXPR_OPERAND_SLOT_SIZE = 3  # [kind][lo][hi]
EXPR_OPERAND_DEPTH = 64

EXPR_OPERATOR_STACK_BASE = 0xA200
EXPR_OPERATOR_SLOT_SIZE = 2  # [token][argument count]
EXPR_OPERATOR_DEPTH = 64

FOR_STACK_BASE = 0xA400
FOR_FRAME_SIZE = 12  # see engines/flow_engine.py
FOR_STACK_DEPTH = 32

GOSUB_STACK_BASE = 0xA800
GOSUB_FRAME_SIZE = 4  # [line addr lo][line addr hi][token ptr lo][token ptr hi]
GOSUB_STACK_DEPTH = 64


# --------------------------------------------------------------------------
# Video memory
# --------------------------------------------------------------------------

TEXT_COLUMNS = 64
TEXT_ROWS = 16
VRAM_SIZE = TEXT_COLUMNS * TEXT_ROWS

GRAPHICS_WIDTH = 128
GRAPHICS_HEIGHT = 48

# A cell with bit 7 set is a semigraphics cell; bits 0..5 are the six blocks,
# numbered block_y * 2 + block_x as shown on the architecture diagram.
SEMIGRAPHICS_FLAG = 0x80
SEMIGRAPHICS_BLOCK_MASK = 0x3F


def vram_address(cell_row: int, cell_col: int) -> int:
    """VRAM Address = VRAM_BASE + (cell_row * 64 + cell_col)."""
    return VRAM_BASE + cell_row * TEXT_COLUMNS + cell_col


# --------------------------------------------------------------------------
# I/O registers
# --------------------------------------------------------------------------

IO_UART_TX_DATA = 0xB400
IO_UART_RX_DATA = 0xB401
IO_UART_STATUS = 0xB402  # bit0 = rx ready, bit1 = tx busy
UART_STATUS_RX_READY = 0x01
UART_STATUS_TX_BUSY = 0x02

IO_KEYBOARD_DATA = 0xB410
IO_KEYBOARD_STATUS = 0xB411  # bit0 = key available
KEYBOARD_STATUS_READY = 0x01

IO_CURSOR_LO = 0xB420  # cursor offset within VRAM
IO_CURSOR_HI = 0xB421

IO_RNG_LO = 0xB430
IO_RNG_HI = 0xB431

IO_STORAGE_STATUS = 0xB440  # bit0 = busy, bit1 = error


# --------------------------------------------------------------------------
# Work RAM
# --------------------------------------------------------------------------

INPUT_LINE_BUFFER = 0xB800  # raw characters from the console
INPUT_LINE_BUFFER_SIZE = 0x100

TOKENIZE_BUFFER = 0xB900  # tokenizer output before it is filed or executed
TOKENIZE_BUFFER_SIZE = 0x100

DIRECT_STATEMENT_BUFFER = 0xBA00  # one synthetic line record for direct mode
DIRECT_STATEMENT_BUFFER_SIZE = 0x100

STORAGE_BUFFER = 0xBB00  # Storage Engine sector / record buffer
STORAGE_BUFFER_SIZE = 0x200

# System pointers.  Architectural state that survives between statements and is
# visible to PEEK, exactly as the hardware registers will be.
SYSVAR_BASE = 0xBFF0
SYSVAR_PROGRAM_END = 0xBFF0  # first free byte of program memory
SYSVAR_DATA_POINTER = 0xBFF2  # next DATA item to READ
SYSVAR_DATA_LINE = 0xBFF4  # line record the DATA pointer sits in
SYSVAR_CURRENT_LINE = 0xBFF6  # line number being executed (0 = direct mode)
SYSVAR_INPUT_FIELD = 0xBFF8  # next unread character of the INPUT line buffer


REGIONS = (
    # (name, base, top)
    ("System ROM", SYSTEM_ROM_BASE, SYSTEM_ROM_TOP),
    ("Program Memory", PROGRAM_BASE, PROGRAM_TOP),
    ("Variable Memory", VARIABLE_BASE, VARIABLE_TOP),
    ("String Space", STRING_BASE, STRING_TOP),
    ("Stack Area", STACK_BASE, STACK_TOP),
    ("Video Memory", VRAM_BASE, VRAM_TOP),
    ("I/O Registers", IO_BASE, IO_TOP),
    ("Work RAM", WORK_RAM_BASE, WORK_RAM_TOP),
    ("Reserved", RESERVED_BASE, RESERVED_TOP),
)


def region_of(address: int) -> str:
    """Name the region an address falls in (used by tests and the monitor)."""
    for name, base, top in REGIONS:
        if base <= address <= top:
            return name
    return "Unmapped"
