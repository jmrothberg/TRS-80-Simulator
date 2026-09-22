# BASIC training set

Continued-pretraining data for `Qwen/Qwen3.8-27B`. The same files work for Qwen3.5-27B and Qwen3.6-27B. Programs are downloaded and detokenized. They are not run in the simulator.

## Files

| File | What it is |
|------|------------|
| `level2_corpus/out/train.jsonl` | 10,354 TRS-80 Model I / III / 4 BASIC programs |
| `level2_corpus/out/val.jsonl` | 99 programs, about 1%, split by hash of the text |
| `level2_corpus/out/manifest.txt` | Counts from the last full Level II build |
| `level2_corpus/out/mbasic_train.jsonl` | 203 Microsoft BASIC-80 / MBASIC programs |
| `level2_corpus/out/mbasic_val.jsonl` | 2 MBASIC programs, about 1% |
| `level2_corpus/out/gwbasic_train.jsonl` | 2,257 GW-BASIC programs |
| `level2_corpus/out/gwbasic_val.jsonl` | 24 GW-BASIC programs, about 1% |
| `level2_corpus/out/gwbasic_manifest.txt` | Counts from the last GW-BASIC build |
| `level2_corpus/out/cbm_train.jsonl` | 956 Commodore BASIC games and demos |
| `level2_corpus/out/cbm_val.jsonl` | 18 Commodore BASIC programs, about 1% |
| `level2_corpus/raw/` | Downloaded archives. Gitignored. |

10,453 unique Level II programs, about 65 MB of BASIC text. Sources: ClassicCMP `[BAS]` zips (Model I, Model III, Model 4), cassette `[CAS]` images, TRSDOS 2.3 and NEWDOS/80 disk images (including the LOAD-80 magazine program disks), a partial Willus pull, 84 portable games from the 1978 *BASIC Computer Games* type-ins, and the `.bas` files in this repo. The rest of the Willus catalog is the same programs as the ClassicCMP zips, so it was not pulled in full. Most of the other disk images are machine-language programs, not BASIC.

205 unique MBASIC programs, from the Walnut Creek CP/M library, including Kaypro and Osborne disks. MBASIC is the close dialect: Microsoft's CP/M BASIC from the same era as Level II. Each MBASIC program starts with:

```basic
0 REM DIALECT MBASIC
```

2,281 unique GW-BASIC programs, about 17 MB, from [robhagemans/hoard-of-gwbasic](https://github.com/robhagemans/hoard-of-gwbasic). Tokenized files were detokenized. Each GW-BASIC program starts with:

```basic
0 REM DIALECT GW-BASIC
```

974 unique Commodore BASIC 2.0 programs, about 5 MB, from the VIC-20 and PET game and demo archives at zimmers.net. This is Microsoft BASIC from the same years as Level II. `FOR`/`NEXT`, `GOTO`, `GOSUB`, `IF`/`THEN`, and `PRINT` match. The extra words are `GET`, `SYS`, and `CLR`, plus `POKE` addresses for the VIC and PET. Each program starts with:

```basic
0 REM DIALECT CBM-BASIC
```

Train the Level II file for most of the steps. MBASIC is the close extra set. Commodore BASIC and GW-BASIC are farther dialects, kept in their own files so they can be left out. Level II rows do not carry a dialect tag.

## Row format

One JSON object per line. One program per row. No chat template.

```json
{"text": "10 REM HAMURABI\n20 CLS\n"}
```

## Build

```bash
python level2_corpus/build.py
```

That refreshes the two JSONL files and `manifest.txt`.

## Train

Point the trainer at `level2_corpus/out/train.jsonl` and the text field.

**Unsloth** continued pretraining: `load_dataset("json", data_files="level2_corpus/out/train.jsonl")` and `dataset_text_field="text"`.

**LLaMA-Factory** stage `pt`: register the file in `dataset_info` with column `text`.

**Axolotl:**

```yaml
base_model: Qwen/Qwen3.8-27B
datasets:
  - path: level2_corpus/out/train.jsonl
    type: completion
    field: text
```

Use `level2_corpus/out/val.jsonl` as the eval set when the trainer asks for one.

MBASIC and GW-BASIC use the same row shape. Point extra datasets at `level2_corpus/out/mbasic_train.jsonl` and `level2_corpus/out/gwbasic_train.jsonl`. Rebuild those files, without touching the Level II JSONL, with:

```bash
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_mbasic()"
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_gw()"
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_cbm()"
```

New Level II programs from a folder of cassette or disk listings are appended, leaving the existing rows in place, with:

```bash
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.merge_new_level2('level2_corpus/raw/dsk')"
```
