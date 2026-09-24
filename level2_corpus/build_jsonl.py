# Turn downloaded BASIC bytes into train.jsonl / val.jsonl for continued pretraining.
# One row is one program: {"text": "<listing>"}.
# Qwen/Qwen3.8-27B trainers (Unsloth, LLaMA-Factory stage pt, Axolotl completion)
# read the text field and ignore nothing else because there is nothing else.

import hashlib
import json
import os
import re

from detokenize import to_source

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "out")

# A listing line starts with a line number. Three of those is enough to keep a file.
_LINE_NO = re.compile(r"^\s*\d{1,5}\b", re.M)


def _keep(text):
    if not text:
        return False
    if len(text) > 2_000_000:
        return False
    if len(_LINE_NO.findall(text)) < 3:
        return False
    sample = text[:8000]
    bad = sum(1 for ch in sample if ord(ch) < 9 or (13 < ord(ch) < 32))
    if bad / max(1, len(sample)) > 0.02:
        return False
    return True


_SKIP_NAMES = {
    "willus_index.html",
    "catalog.jsonl",
    "provenance.jsonl",
    "manifest.txt",
}


def _iter_files():
    if not os.path.isdir(RAW):
        return
    for dirpath, dirnames, filenames in os.walk(RAW):
        # These folders are other dialects. They have their own JSONL files.
        # A Level II rebuild must not pull them in untagged.
        dirnames[:] = [d for d in dirnames if d not in (
            "__pycache__", "gw", "mbasic", "cbm", "cbm_prg", "model100")]
        for name in filenames:
            if name in _SKIP_NAMES or name == ".ok":
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(dirpath).startswith(os.path.join(RAW, "local")):
                src = "local"
            elif os.path.abspath(dirpath).startswith(os.path.join(RAW, "willus")):
                src = "willus"
            elif "classiccmp" in dirpath:
                src = "classiccmp"
            else:
                src = "other"
            yield src, path


def build():
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    train_path = os.path.join(OUT, "train.jsonl")
    val_path = os.path.join(OUT, "val.jsonl")
    counts = {"files": 0, "kept": 0, "dupes": 0, "dropped": 0, "train": 0, "val": 0, "bytes": 0}
    by_src = {}
    # Write straight through so a huge corpus does not sit in memory twice.
    with open(train_path, "w", encoding="utf-8") as train_f, \
            open(val_path, "w", encoding="utf-8") as val_f:
        for src, path in _iter_files():
            counts["files"] += 1
            try:
                data = open(path, "rb").read()
            except OSError:
                counts["dropped"] += 1
                continue
            text = to_source(data)
            if not _keep(text):
                counts["dropped"] += 1
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen:
                counts["dupes"] += 1
                continue
            seen.add(digest)
            row = '{"text": ' + _json_string(text) + "}\n"
            # 1% holdout by hash. This is a file split, not a run of the program.
            bucket = int(digest[:8], 16) % 100
            if bucket == 0:
                val_f.write(row)
                counts["val"] += 1
            else:
                train_f.write(row)
                counts["train"] += 1
            counts["kept"] += 1
            counts["bytes"] += len(text.encode("utf-8"))
            by_src[src] = by_src.get(src, 0) + 1
            if counts["files"] % 2000 == 0:
                print("scanned", counts["files"], "kept", counts["kept"], flush=True)
    manifest = os.path.join(OUT, "manifest.txt")
    lines = [
        "Level II BASIC continued-pretraining corpus",
        "target checkpoint: Qwen/Qwen3.8-27B",
        "row shape: {\"text\": \"<one program>\"}",
        "files_seen %d" % counts["files"],
        "programs_kept %d" % counts["kept"],
        "exact_dupes %d" % counts["dupes"],
        "dropped %d" % counts["dropped"],
        "train_rows %d" % counts["train"],
        "val_rows %d" % counts["val"],
        "text_bytes %d" % counts["bytes"],
        "from_repo %d" % by_src.get("local", 0),
        "from_willus %d" % by_src.get("willus", 0),
        "from_classiccmp %d" % by_src.get("classiccmp", 0),
    ]
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return counts


_GW_TAG = "0 REM DIALECT GW-BASIC\n"
_GW_EXT = {".bas", ".asc", ".txt", ".basica"}


def build_gw():
    """Pack raw/gw listings into a second JSONL. Does not touch the Level II files."""
    folder = os.path.join(RAW, "gw")
    os.makedirs(OUT, exist_ok=True)
    from detokenize import gw_to_source
    seen = set()
    counts = {"files": 0, "kept": 0, "dupes": 0, "dropped": 0, "train": 0, "val": 0, "bytes": 0}
    train_path = os.path.join(OUT, "gwbasic_train.jsonl")
    val_path = os.path.join(OUT, "gwbasic_val.jsonl")
    with open(train_path, "w", encoding="utf-8") as train_f, \
            open(val_path, "w", encoding="utf-8") as val_f:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext not in _GW_EXT:
                    continue
                counts["files"] += 1
                path = os.path.join(dirpath, name)
                try:
                    data = open(path, "rb").read()
                except OSError:
                    counts["dropped"] += 1
                    continue
                text = gw_to_source(data)
                # One numbered line is enough. GW-BASIC one-liners are real programs.
                if not text or len(_LINE_NO.findall(text)) < 1 or len(text) > 2_000_000:
                    counts["dropped"] += 1
                    continue
                sample = text[:8000]
                bad = sum(1 for ch in sample if ord(ch) < 9 or (13 < ord(ch) < 32))
                if bad / max(1, len(sample)) > 0.02:
                    counts["dropped"] += 1
                    continue
                body = text.replace("\r\n", "\n")
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if digest in seen:
                    counts["dupes"] += 1
                    continue
                seen.add(digest)
                tagged = _GW_TAG + body
                row = '{"text": ' + _json_string(tagged) + "}\n"
                if int(digest[:8], 16) % 100 == 0:
                    val_f.write(row)
                    counts["val"] += 1
                else:
                    train_f.write(row)
                    counts["train"] += 1
                counts["kept"] += 1
                counts["bytes"] += len(tagged.encode("utf-8"))
    manifest = os.path.join(OUT, "gwbasic_manifest.txt")
    lines = [
        "GW-BASIC continued-pretraining corpus",
        "dialect tag: 0 REM DIALECT GW-BASIC",
        "target checkpoint: Qwen/Qwen3.8-27B",
        "row shape: {\"text\": \"<one program>\"}",
        "source: robhagemans/hoard-of-gwbasic",
        "files_seen %d" % counts["files"],
        "programs_kept %d" % counts["kept"],
        "exact_dupes %d" % counts["dupes"],
        "dropped %d" % counts["dropped"],
        "train_rows %d" % counts["train"],
        "val_rows %d" % counts["val"],
        "text_bytes %d" % counts["bytes"],
    ]
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return counts


def _load_hashes(paths):
    seen = set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    text = json.loads(line).get("text", "")
                except json.JSONDecodeError:
                    continue
                seen.add(hashlib.sha256(text.encode("utf-8")).hexdigest())
    return seen


def merge_new_level2(folder):
    """Append Level II listings that are not already in train.jsonl or val.jsonl."""
    import json as _json
    from detokenize import to_source
    os.makedirs(OUT, exist_ok=True)
    train_path = os.path.join(OUT, "train.jsonl")
    val_path = os.path.join(OUT, "val.jsonl")
    seen = _load_hashes([train_path, val_path])
    added = {"train": 0, "val": 0, "dupes": 0, "dropped": 0, "files": 0}
    with open(train_path, "a", encoding="utf-8") as train_f, \
            open(val_path, "a", encoding="utf-8") as val_f:
        for dirpath, dirnames, filenames in os.walk(folder):
            for name in filenames:
                path = os.path.join(dirpath, name)
                if not os.path.isfile(path):
                    continue
                added["files"] += 1
                try:
                    data = open(path, "rb").read()
                except OSError:
                    added["dropped"] += 1
                    continue
                text = to_source(data)
                if not _keep(text):
                    added["dropped"] += 1
                    continue
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest in seen:
                    added["dupes"] += 1
                    continue
                seen.add(digest)
                row = '{"text": ' + _json.dumps(text, ensure_ascii=False) + "}\n"
                if int(digest[:8], 16) % 100 == 0:
                    val_f.write(row)
                    added["val"] += 1
                else:
                    train_f.write(row)
                    added["train"] += 1
                if added["files"] % 2000 == 0:
                    print("merge", added, flush=True)
    print("merged", added, flush=True)
    return added


_MBASIC_TAG = "0 REM DIALECT MBASIC\n"


def build_mbasic():
    """CP/M Microsoft BASIC-80 / MBASIC listings. Close to Level II, tagged."""
    folder = os.path.join(RAW, "mbasic")
    os.makedirs(OUT, exist_ok=True)
    from detokenize import gw_to_source
    seen = set()
    counts = {"files": 0, "kept": 0, "dupes": 0, "dropped": 0, "train": 0, "val": 0}
    train_path = os.path.join(OUT, "mbasic_train.jsonl")
    val_path = os.path.join(OUT, "mbasic_val.jsonl")
    with open(train_path, "w", encoding="utf-8") as train_f, \
            open(val_path, "w", encoding="utf-8") as val_f:
        if not os.path.isdir(folder):
            print("no mbasic folder", flush=True)
            return counts
        for name in os.listdir(folder):
            ext = os.path.splitext(name)[1].lower()
            if ext not in {".bas", ".asc", ".txt"}:
                continue
            counts["files"] += 1
            data = open(os.path.join(folder, name), "rb").read()
            if data[:1] == b"\xff":
                text = gw_to_source(data)
            else:
                text = data.decode("cp437", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                if not text.endswith("\n"):
                    text += "\n"
            if not text or len(_LINE_NO.findall(text)) < 3:
                counts["dropped"] += 1
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen:
                counts["dupes"] += 1
                continue
            seen.add(digest)
            tagged = _MBASIC_TAG + text
            row = '{"text": ' + _json_string(tagged) + "}\n"
            if int(digest[:8], 16) % 100 == 0:
                val_f.write(row)
                counts["val"] += 1
            else:
                train_f.write(row)
                counts["train"] += 1
            counts["kept"] += 1
    print("mbasic", counts, flush=True)
    return counts


_CBM_TAG = "0 REM DIALECT CBM-BASIC\n"


def build_cbm():
    """VIC-20 / C64 / PET BASIC games. Microsoft BASIC 2.0, tagged."""
    folder = os.path.join(RAW, "cbm")
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    counts = {"files": 0, "kept": 0, "dupes": 0, "dropped": 0, "train": 0, "val": 0}
    train_path = os.path.join(OUT, "cbm_train.jsonl")
    val_path = os.path.join(OUT, "cbm_val.jsonl")
    with open(train_path, "w", encoding="utf-8") as train_f, \
            open(val_path, "w", encoding="utf-8") as val_f:
        if not os.path.isdir(folder):
            print("no cbm folder", flush=True)
            return counts
        for dirpath, dirnames, filenames in os.walk(folder):
            for name in filenames:
                if os.path.splitext(name)[1].lower() not in {".bas", ".txt"}:
                    continue
                counts["files"] += 1
                data = open(os.path.join(dirpath, name), "rb").read()
                text = data.decode("latin1", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                if not text.endswith("\n"):
                    text += "\n"
                if len(_LINE_NO.findall(text)) < 3 or len(text) > 2_000_000:
                    counts["dropped"] += 1
                    continue
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest in seen:
                    counts["dupes"] += 1
                    continue
                seen.add(digest)
                tagged = _CBM_TAG + text
                row = '{"text": ' + _json_string(tagged) + "}\n"
                if int(digest[:8], 16) % 100 == 0:
                    val_f.write(row)
                    counts["val"] += 1
                else:
                    train_f.write(row)
                    counts["train"] += 1
                counts["kept"] += 1
    print("cbm", counts, flush=True)
    return counts


def _json_string(text):
    """JSON string escape without pulling in a second encoder style."""
    import json
    return json.dumps(text, ensure_ascii=False)
