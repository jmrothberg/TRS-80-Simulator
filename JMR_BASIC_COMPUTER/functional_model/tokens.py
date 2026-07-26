"""The architectural instruction set: one byte per BASIC token.

Constitution, BASIC TOKENS:

    Every token has: one opcode, one dispatch table entry, one implementation.

This module is the opcode definition only.  The dispatch table (opcode ->
microcode entry address) is built in `dispatch.py`; the implementations are the
microcode routines in `microcode.py`.

Encoding, matching the BASIC TOKEN STRUCTURE panel of the architecture diagram:

    0x00        end of statement
    0x01 lo hi  integer literal (16-bit signed)
    0x02 n ...  string literal, n characters follow
    0x0D a b    variable reference, two name characters (b = 0 when absent)
    0x20..0x7E  a literal character that is not part of the language
    0x80..0xFF  keywords, operators and functions

The diagram fixes two opcodes: PRINT is 0x81 and "+" is 0x8E.  The table below
is laid out around them.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Structural tokens
# --------------------------------------------------------------------------

T_EOS = 0x00  # end of statement / end of line record
T_INTEGER = 0x01  # followed by two bytes, little endian, signed
T_STRING = 0x02  # followed by a length byte then that many characters
T_VARIABLE = 0x0D  # followed by two name bytes

# --------------------------------------------------------------------------
# Statement keywords
# --------------------------------------------------------------------------

T_LET = 0x80
T_PRINT = 0x81
T_INPUT = 0x82
T_IF = 0x83
T_THEN = 0x84
T_GOTO = 0x85
T_GOSUB = 0x86
T_RETURN = 0x87
T_FOR = 0x88
T_TO = 0x89
T_STEP = 0x8A
T_NEXT = 0x8B
T_END = 0x8C
T_REM = 0x8D

# --------------------------------------------------------------------------
# Operators and punctuation
# --------------------------------------------------------------------------

T_PLUS = 0x8E
T_MINUS = 0x8F
T_STAR = 0x90
T_SLASH = 0x91
T_CARET = 0x92
T_EQUAL = 0x93
T_NOT_EQUAL = 0x94
T_LESS = 0x95
T_GREATER = 0x96
T_LESS_EQUAL = 0x97
T_GREATER_EQUAL = 0x98
T_LPAREN = 0x99
T_RPAREN = 0x9A
T_COMMA = 0x9B
T_SEMICOLON = 0x9C
T_COLON = 0x9D
T_AND = 0x9E
T_OR = 0x9F
T_NOT = 0xA0

# Internal: unary minus, produced by the Expression Engine, never tokenized.
T_NEGATE = 0xA1

# --------------------------------------------------------------------------
# Remaining statement keywords
# --------------------------------------------------------------------------

T_READ = 0xA2
T_DATA = 0xA3
T_RESTORE = 0xA4
T_DIM = 0xA5
T_CLS = 0xA6
T_SET = 0xA7
T_RESET = 0xA8
T_POKE = 0xA9
T_SAVE = 0xAA
T_LOAD = 0xAB
T_RUN = 0xAC
T_LIST = 0xAD
T_NEW = 0xAE
T_STOP = 0xAF
T_AT = 0xB0  # the "@" of PRINT@

# --------------------------------------------------------------------------
# Functions (evaluated by the Expression Engine)
# --------------------------------------------------------------------------

T_POINT = 0xC0
T_PEEK = 0xC1
T_ABS = 0xC2
T_INT = 0xC3
T_SGN = 0xC4
T_RND = 0xC5


#: Spelling -> opcode.  Longest match wins, so "<=" is found before "<".
KEYWORDS: dict[str, int] = {
    "PRINT": T_PRINT,
    "INPUT": T_INPUT,
    "LET": T_LET,
    "IF": T_IF,
    "THEN": T_THEN,
    "GOTO": T_GOTO,
    "GOSUB": T_GOSUB,
    "RETURN": T_RETURN,
    "FOR": T_FOR,
    "TO": T_TO,
    "STEP": T_STEP,
    "NEXT": T_NEXT,
    "END": T_END,
    "REM": T_REM,
    "READ": T_READ,
    "DATA": T_DATA,
    "RESTORE": T_RESTORE,
    "DIM": T_DIM,
    "CLS": T_CLS,
    "SET": T_SET,
    "RESET": T_RESET,
    "POINT": T_POINT,
    "PEEK": T_PEEK,
    "POKE": T_POKE,
    "SAVE": T_SAVE,
    "LOAD": T_LOAD,
    "RUN": T_RUN,
    "LIST": T_LIST,
    "NEW": T_NEW,
    "STOP": T_STOP,
    "ABS": T_ABS,
    "INT": T_INT,
    "SGN": T_SGN,
    "RND": T_RND,
    "AND": T_AND,
    "OR": T_OR,
    "NOT": T_NOT,
    "<=": T_LESS_EQUAL,
    ">=": T_GREATER_EQUAL,
    "=<": T_LESS_EQUAL,
    "=>": T_GREATER_EQUAL,
    "<>": T_NOT_EQUAL,
    "><": T_NOT_EQUAL,
    "+": T_PLUS,
    "-": T_MINUS,
    "*": T_STAR,
    "/": T_SLASH,
    "^": T_CARET,
    "=": T_EQUAL,
    "<": T_LESS,
    ">": T_GREATER,
    "(": T_LPAREN,
    ")": T_RPAREN,
    ",": T_COMMA,
    ";": T_SEMICOLON,
    ":": T_COLON,
    "@": T_AT,
    "?": T_PRINT,  # Level II shorthand
}

#: opcode -> the text LIST prints.  The first spelling in KEYWORDS wins, so the
#: aliases ("?", "=<", "><") list as their canonical form.
SPELLING: dict[int, str] = {}
for _text, _opcode in KEYWORDS.items():
    SPELLING.setdefault(_opcode, _text)

#: Keywords that may start a statement.  Every one needs a dispatch entry.
STATEMENT_TOKENS = (
    T_LET,
    T_PRINT,
    T_INPUT,
    T_IF,
    T_GOTO,
    T_GOSUB,
    T_RETURN,
    T_FOR,
    T_NEXT,
    T_END,
    T_REM,
    T_READ,
    T_DATA,
    T_RESTORE,
    T_DIM,
    T_CLS,
    T_SET,
    T_RESET,
    T_POKE,
    T_SAVE,
    T_LOAD,
    T_RUN,
    T_LIST,
    T_NEW,
    T_STOP,
)

#: Tokens the Expression Engine treats as functions: FN "(" args ")".
FUNCTION_TOKENS = {
    T_POINT: 2,
    T_PEEK: 1,
    T_ABS: 1,
    T_INT: 1,
    T_SGN: 1,
    T_RND: 1,
}

#: Binary operators: token -> (precedence, right associative).
BINARY_OPERATORS = {
    T_OR: (1, False),
    T_AND: (2, False),
    T_EQUAL: (4, False),
    T_NOT_EQUAL: (4, False),
    T_LESS: (4, False),
    T_GREATER: (4, False),
    T_LESS_EQUAL: (4, False),
    T_GREATER_EQUAL: (4, False),
    T_PLUS: (5, False),
    T_MINUS: (5, False),
    T_STAR: (6, False),
    T_SLASH: (6, False),
    T_CARET: (8, True),
}

#: Unary operators, higher precedence than any binary operator they follow.
UNARY_OPERATORS = {
    T_NOT: 3,
    T_NEGATE: 7,
}


def is_keyword(opcode: int) -> bool:
    return opcode >= 0x80


def token_length(opcode: int, operand_byte: int = 0) -> int:
    """Total bytes this token occupies, including its inline operand."""
    if opcode == T_INTEGER:
        return 3
    if opcode == T_VARIABLE:
        return 3
    if opcode == T_STRING:
        return 2 + operand_byte
    return 1
