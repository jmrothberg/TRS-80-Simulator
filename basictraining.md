# BASIC training set

Continued-pretraining data for `Qwen/Qwen3.8-27B`. The same files work for Qwen3.5-27B and Qwen3.6-27B. Programs are downloaded and detokenized. They are not run in the simulator.

## Files

| File | What it is |
|------|------------|
| `level2_corpus/out/train.jsonl` | 11,819 TRS-80 Model I / III / 4 BASIC programs |
| `level2_corpus/out/val.jsonl` | 115 programs, about 1%, split by hash of the text |
| `level2_corpus/out/manifest.txt` | Counts from the last full Level II build |
| `level2_corpus/out/mbasic_train.jsonl` | 203 Microsoft BASIC-80 / MBASIC programs |
| `level2_corpus/out/mbasic_val.jsonl` | 2 MBASIC programs, about 1% |
| `level2_corpus/out/gwbasic_train.jsonl` | 2,257 GW-BASIC programs |
| `level2_corpus/out/gwbasic_val.jsonl` | 24 GW-BASIC programs, about 1% |
| `level2_corpus/out/gwbasic_manifest.txt` | Counts from the last GW-BASIC build |
| `level2_corpus/out/cbm_train.jsonl` | 956 Commodore BASIC games and demos |
| `level2_corpus/out/cbm_val.jsonl` | 18 Commodore BASIC programs, about 1% |
| `level2_corpus/out/model100_train.jsonl` | 447 Model 100 / 102 / 200 BASIC programs |
| `level2_corpus/out/model100_val.jsonl` | 3 Model 100 programs, about 1% |
| `level2_corpus/raw/` | Downloaded archives. Gitignored. |

11,934 unique Level II programs. Sources: ClassicCMP `[BAS]` zips (Model I, Model III, Model 4), cassette `[CAS]` images, TRSDOS 2.3 and NEWDOS/80 disk images (including the LOAD-80 magazine program disks), a second pass over 937 disks whose directories had no readable `/BAS` file (CLOAD, SoftSide, and similar images keep tokenized programs where the first reader did not look; that pass added 1,119 programs that were not already in the set), a partial Willus pull, portable games from the 1978 *BASIC Computer Games* type-ins, 75 more from the 1979 *More BASIC Computer Games* type-ins (Microsoft BASIC, the dialect the book says runs on Level II; 10 files that use `MAT`, `CHANGE`, `SLEEP`, or `WHILE` were left out), Terry Stewart's System 80 / Model I disk and cassette archive, and the `.bas` files in this repo. The rest of the Willus catalog is the same programs as the ClassicCMP zips, so it was not pulled in full. Machine-language games (`/CMD`) are not BASIC, so they are not in this file. Book-page OCR is not in this file. Hugging Face has no TRS-80 dataset; its `visual-basic` split is Visual Basic and was not added.

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

450 unique TRS-80 Model 100 / 102 / 200 programs, from the Club 100 library on ftp.whtech.com. This is Microsoft BASIC from 1983, line-numbered, with the same `PRINT` / `GOTO` / `FOR` core and a few laptop words (`MAXFILES`, `COM`, `MENU`). Files that use `SCREEN`, `LOCATE`, `WHILE`, or `SUB` were left out. Each program starts with:

```basic
0 REM DIALECT MODEL-100
```

The files are `level2_corpus/out/model100_train.jsonl` (447) and `level2_corpus/out/model100_val.jsonl` (3).

Train the Level II file for most of the steps. MBASIC is the close extra set. Model 100 is the next closest. Commodore BASIC and GW-BASIC are farther dialects, kept in their own files so they can be left out. Level II rows do not carry a dialect tag.

## How a program becomes a training row

The trainers never see a disk image or a tokenized `.BAS`. They see one JSON object per line, one program per row, and nothing else. There is no chat template and no invented instruction.

```json
{"text": "10 REM HAMURABI\n20 CLS\n"}
```

That shape is what continued pretraining, a full fine-tune, and a LoRA all want. The model learns to continue BASIC text. A chat row would teach it to talk about BASIC instead.

The steps in `level2_corpus/`:

1. Download the archive into `level2_corpus/raw/`. Those files are gitignored.
2. Turn bytes into a listing. A tokenized Level II program starts with `0xFF`. Each line is a RAM pointer, a line number, keyword bytes `0x80`–`0xFB`, and a `0x00`. `detokenize.py` writes those keywords out as `PRINT`, `GOTO`, `CLS`, and the rest of the Model I list. Cassettes are the same token stream after the `0xA5` sync. ASCII listings are kept as text. Disk BASIC is read from a TRSDOS 2.3 directory or a NEWDOS/80 directory. If neither directory yields a program, each sector that starts with `0xFF` is detokenized on its own. That second pass is what recovered the CLOAD and SoftSide programs.
3. Drop a listing with fewer than three numbered lines, more than about 2% control characters in the first 8000 characters, or a size over 2 MB. The disk sector pass is stricter: at least five numbered lines, line numbers that do not jump backward, a Level II keyword near the start, and a printable last line.
4. Dedupe on the SHA-256 of the listing text. The same game from two archives becomes one row.
5. If the first eight hex digits of that hash, read as an integer, are divisible by 100, the row goes to `val.jsonl`. Everything else goes to `train.jsonl`. That is about 1%, and the same program always lands in the same file.

Close dialects are the same row shape with one extra first line, and they stay in their own files:

```basic
0 REM DIALECT MBASIC
```

Level II rows have no dialect tag. A full Level II rebuild (`python level2_corpus/build.py`) walks `raw/` and rewrites `train.jsonl` and `val.jsonl`. It skips `gw`, `mbasic`, `cbm`, `cbm_prg`, and `model100` so those dialects are not mixed in untagged. New Level II listings are appended, leaving the existing rows in place, with:

```bash
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.merge_new_level2('level2_corpus/raw/dsk')"
```

Rebuild the dialect files, without touching the Level II JSONL, with:

```bash
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_mbasic()"
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_gw()"
python -c "import sys; sys.path.insert(0, 'level2_corpus'); import build_jsonl; build_jsonl.build_cbm()"
```

## Fine-tune, small models, and LoRA

Use `level2_corpus/out/train.jsonl` for training and `level2_corpus/out/val.jsonl` when the trainer asks for an eval set. The text field is `text`. The same two files are the dataset for a 27B full fine-tune, a QLoRA, and a smaller Qwen. Only the base-model name changes.

Train Level II for most of the steps. Add `mbasic_train.jsonl` if you want the closest extra dialect, then `model100_train.jsonl`. Leave `gwbasic_train.jsonl` and `cbm_train.jsonl` out unless you want those dialects.

**Axolotl**, QLoRA on the 27B. For a smaller model, change `base_model` and keep the dataset block.

```yaml
base_model: Qwen/Qwen3.8-27B
load_in_4bit: true
adapter: lora
lora_r: 16
lora_alpha: 32
datasets:
  - path: level2_corpus/out/train.jsonl
    type: completion
    field: text
val_set_size: 0.0
```

Point the eval set at `level2_corpus/out/val.jsonl` instead of `val_set_size` when you want the fixed split. Drop `adapter`, `lora_r`, and `lora_alpha` for a full fine-tune. A 27B full fine-tune needs several GPUs. A rank-16 4-bit LoRA is the practical way to train the 27B; a 7B or 8B Qwen is the one that fits comfortably on a 24 GB GPU. The JSONL does not change.

**Unsloth** QLoRA. Load the base model in 4-bit, attach a LoRA, and train with `dataset_text_field="text"`. Do not apply a chat template.

```python
from unsloth import FastLanguageModel
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained(
    "Qwen/Qwen3.8-27B",
    max_seq_length=2048,
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
)
ds = load_dataset("json", data_files={
    "train": "level2_corpus/out/train.jsonl",
    "validation": "level2_corpus/out/val.jsonl",
})
# SFTTrainer(..., dataset_text_field="text")
```

A 7B or 8B Qwen uses that same `ds`. Change the `from_pretrained` name.

**LLaMA-Factory**: stage `pt` (pretrain, not supervised chat), `finetuning_type: lora` for a LoRA or `full` for a full fine-tune, and a dataset registered with column `text`.
