#!/usr/bin/env python3
"""Generate docs/TOKENS.md from the opcode table.

    python3 tools/gen_tokens.py

The token table is code first: `functional_model/tokens.py` is the authority,
and this keeps the document that the SystemVerilog decoder will be written from
in step with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from functional_model import tokens as tk  # noqa: E402

HEADER = """# The architectural instruction set

Every BASIC token is one byte. This is the machine's opcode table: there is no
layer below it. The two opcodes fixed by the architecture diagram are
`PRINT = 0x81` and `+ = 0x8E`; the rest of the table is laid out around them.

Generated from `functional_model/tokens.py` by `tools/gen_tokens.py`; edit the
table there, not here. This document is the authority for anyone writing the
SystemVerilog decoder.

## Structural tokens

| Opcode | Meaning | Operand |
|---|---|---|
| `0x00` | end of statement | - |
| `0x01` | integer literal | 2 bytes, little endian, signed |
| `0x02` | string literal | 1 length byte, then that many characters |
| `0x0D` | variable reference | 2 name bytes (second is 0 when absent) |

A stored line is `[line# lo][line# hi][length][token ...][0x00]`.
"""

FOOTER = """
## Precedence

| Level | Operators |
|---|---|
| 8 | `^` (right associative) |
| 7 | unary `-` |
| 6 | `*` `/` |
| 5 | `+` `-` |
| 4 | `=` `<>` `<` `>` `<=` `>=` |
| 3 | `NOT` |
| 2 | `AND` |
| 1 | `OR` |

`AND`, `OR` and `NOT` are bitwise on 16-bit values, as on a Level II machine; a
true comparison yields `-1` and a false one `0`, so the bitwise and logical
readings agree.

## Notes on compatibility

* Keyword recognition is greedy, exactly as on a Level II machine: the longest
  keyword spelling that matches wins, even inside a name. `FORT=1` really does
  tokenize as `FOR T=1`. This is authentic and is kept deliberately.
* `?` is accepted as a spelling of `PRINT`, and `=<`, `=>`, `><` as spellings of
  `<=`, `>=`, `<>`. Aliases share the opcode of the token they spell, so `LIST`
  prints the canonical form.
* Only the first two characters of a variable name are significant.
* Integer literals may be written up to 65535 so that hardware addresses are
  typeable (`POKE 45056,42`). Above 32767 the value is stored as its 16-bit
  pattern and reads back negative until the floating point milestone.
"""


def table(rows: list[tuple[int, str]]) -> str:
    out = ["| Opcode | Token |", "|---|---|"]
    out += [f"| `{opcode:#04x}` | `{name}` |" for opcode, name in rows]
    return "\n".join(out) + "\n"


def build() -> str:
    statements = [(token, tk.SPELLING[token]) for token in sorted(tk.STATEMENT_TOKENS)]
    operators = sorted(
        set(tk.BINARY_OPERATORS)
        | {
            tk.T_NOT, tk.T_LPAREN, tk.T_RPAREN, tk.T_COMMA, tk.T_SEMICOLON,
            tk.T_COLON, tk.T_AT, tk.T_TO, tk.T_STEP, tk.T_THEN,
        }
    )

    parts = [HEADER, "\n## Statement keywords\n\n"]
    parts.append(table([row for row in statements if row[0] < tk.T_PLUS]))
    parts.append("\n## Operators and punctuation\n\n")
    parts.append(table([(token, tk.SPELLING[token]) for token in operators]))
    parts.append("\n## Remaining statement keywords\n\n")
    parts.append(table([row for row in statements if row[0] > tk.T_PLUS]))
    parts.append("\n## Functions\n\n")
    parts.append("| Opcode | Function | Arguments |\n|---|---|---|\n")
    for token in sorted(tk.FUNCTION_TOKENS):
        parts.append(f"| `{token:#04x}` | `{tk.SPELLING[token]}` | {tk.FUNCTION_TOKENS[token]} |\n")
    parts.append(FOOTER)
    return "".join(parts)


if __name__ == "__main__":
    target = ROOT / "docs" / "TOKENS.md"
    target.write_text(build())
    print(f"wrote {target.relative_to(ROOT)}")
