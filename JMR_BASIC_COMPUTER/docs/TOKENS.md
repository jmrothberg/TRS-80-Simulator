# The architectural instruction set

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

## Statement keywords

| Opcode | Token |
|---|---|
| `0x80` | `LET` |
| `0x81` | `PRINT` |
| `0x82` | `INPUT` |
| `0x83` | `IF` |
| `0x85` | `GOTO` |
| `0x86` | `GOSUB` |
| `0x87` | `RETURN` |
| `0x88` | `FOR` |
| `0x8b` | `NEXT` |
| `0x8c` | `END` |
| `0x8d` | `REM` |

## Operators and punctuation

| Opcode | Token |
|---|---|
| `0x84` | `THEN` |
| `0x89` | `TO` |
| `0x8a` | `STEP` |
| `0x8e` | `+` |
| `0x8f` | `-` |
| `0x90` | `*` |
| `0x91` | `/` |
| `0x92` | `^` |
| `0x93` | `=` |
| `0x94` | `<>` |
| `0x95` | `<` |
| `0x96` | `>` |
| `0x97` | `<=` |
| `0x98` | `>=` |
| `0x99` | `(` |
| `0x9a` | `)` |
| `0x9b` | `,` |
| `0x9c` | `;` |
| `0x9d` | `:` |
| `0x9e` | `AND` |
| `0x9f` | `OR` |
| `0xa0` | `NOT` |
| `0xb0` | `@` |

## Remaining statement keywords

| Opcode | Token |
|---|---|
| `0xa2` | `READ` |
| `0xa3` | `DATA` |
| `0xa4` | `RESTORE` |
| `0xa5` | `DIM` |
| `0xa6` | `CLS` |
| `0xa7` | `SET` |
| `0xa8` | `RESET` |
| `0xa9` | `POKE` |
| `0xaa` | `SAVE` |
| `0xab` | `LOAD` |
| `0xac` | `RUN` |
| `0xad` | `LIST` |
| `0xae` | `NEW` |
| `0xaf` | `STOP` |

## Functions

| Opcode | Function | Arguments |
|---|---|---|
| `0xc0` | `POINT` | 2 |
| `0xc1` | `PEEK` | 1 |
| `0xc2` | `ABS` | 1 |
| `0xc3` | `INT` | 1 |
| `0xc4` | `SGN` | 1 |
| `0xc5` | `RND` | 1 |

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
