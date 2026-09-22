# Download TRS-80 BASIC listings into level2_corpus/raw/.
# Willus.com stores tokenized .BAS files. Action 13 on a catalog link is the raw bytes.
# Local .bas files in this repo are copied as-is. Nothing is executed.

import json
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
RAW = os.path.join(ROOT, "raw")
INDEX_PATH = os.path.join(RAW, "willus_index.html")
CATALOG_PATH = os.path.join(RAW, "catalog.jsonl")
PROVENANCE_PATH = os.path.join(RAW, "provenance.jsonl")
WILLUS = "https://willus.com"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
WORKERS = 24
# Extensions that are BASIC source, or text listings, on any catalog row.
_SOURCE_EXT = {"BAS", "ASC", "TXT", "BA", "B16"}

_thread = threading.local()


def _session():
    sess = getattr(_thread, "sess", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept": "*/*"})
        _thread.sess = sess
    return sess


def _get(url, timeout=60):
    resp = _session().get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def ensure_index():
    os.makedirs(RAW, exist_ok=True)
    if os.path.isfile(INDEX_PATH) and os.path.getsize(INDEX_PATH) > 1000000:
        return
    print("downloading Willus catalog", flush=True)
    resp = _get(WILLUS + "/trs80/", timeout=120)
    with open(INDEX_PATH, "wb") as f:
        f.write(resp.content)
    print("catalog bytes", len(resp.content), flush=True)


def parse_catalog():
    """BAS-row files plus any .BAS/.ASC/.TXT anywhere in the catalog."""
    html = open(INDEX_PATH, errors="replace").read()
    rows = re.findall(r"<tr>(.*?)</tr>", html, flags=re.S)
    seen = set()
    items = []
    for row in rows:
        type_match = re.search(r'<td class="entry [^"]* type">([^<]*)</td>', row)
        row_type = type_match.group(1).strip().upper() if type_match else ""
        files = re.findall(
            r'href="(/trs80/\?-d\+-a\+1\+-p\+(\d+)\+-f\+(\d+))"[^>]*>([^<]+)</a>',
            row,
        )
        for href, prog, file_n, name in files:
            ext = name.upper().rsplit(".", 1)[-1] if "." in name else ""
            if ext not in _SOURCE_EXT and not (ext == "" and "BAS" in row_type):
                continue
            key = (prog, file_n)
            if key in seen:
                continue
            seen.add(key)
            # a+1 is the catalog view. a+13 is the raw file bytes.
            raw_href = href.replace("-a+1+-", "-a+13+-", 1)
            items.append({
                "archive": "willus",
                "program": int(prog),
                "file": int(file_n),
                "name": name.strip(),
                "row_type": row_type,
                "url": urljoin(WILLUS, raw_href),
            })
    return items


def _dest_for(item):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", item["name"])[:80]
    return os.path.join(RAW, "willus", "%s_%s_%s" % (item["program"], item["file"], safe))


def _download_one(item):
    dest = _dest_for(item)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return "skip", item, dest
    try:
        resp = _get(item["url"], timeout=45)
    except Exception as exc:
        return "fail", item, str(exc)
    body = resp.content
    head = body[:200].lower()
    if body[:1] == b"<" and (b"html" in head or b"not acceptable" in head):
        return "fail", item, "html"
    if len(body) == 0:
        return "fail", item, "empty"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(body)
    return "ok", item, dest


def copy_local():
    """Copy .bas listings that already live in this repository."""
    dest_dir = os.path.join(RAW, "local")
    os.makedirs(dest_dir, exist_ok=True)
    copied = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        if os.path.abspath(dirpath).startswith(os.path.abspath(ROOT)):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in (".git", "raw", "__pycache__")]
        for name in filenames:
            if not name.lower().endswith(".bas"):
                continue
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, REPO).replace(os.sep, "__")
            dest = os.path.join(dest_dir, rel)
            shutil.copyfile(src, dest)
            copied.append({
                "archive": "repo",
                "name": rel,
                "url": "file:" + os.path.relpath(src, REPO),
                "path": dest,
            })
    return copied


CLASSICMP = "http://cpmarchives.classiccmp.org/trs80/Software/"
_MODELS = ["Model%201/", "Model%20III/", "Model%204/"]


def _list_hrefs(url):
    resp = _get(url, timeout=60)
    return re.findall(r'href="([^"?][^"]*)"', resp.text)


def classiccmp_zip_urls():
    """Every [BAS].zip under Model I, Model III, and Model 4."""
    urls = []
    seen = set()
    for model in _MODELS:
        model_url = CLASSICMP + model
        entries = _list_hrefs(model_url)
        # Model I/4 are split into letter folders. Model III lists zips on the model page.
        pages = [model_url]
        for href in entries:
            if href.endswith("/") and not href.startswith("/"):
                pages.append(urljoin(model_url, href))
        for page in pages:
            names = entries if page == model_url else _list_hrefs(page)
            for name in names:
                if not name.lower().endswith("%5bbas%5d.zip"):
                    continue
                full = urljoin(page, name)
                if full in seen:
                    continue
                seen.add(full)
                urls.append(full)
        print("classiccmp", model, "zips", len(urls), flush=True)
    return urls


def _download_zip(url):
    """Save one [BAS].zip and explode its members next to it."""
    tail = url.rstrip("/").split("/")[-1]
    # Percent-encoded title. Keep it filesystem-safe and unique.
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", requests.utils.unquote(tail))[:120]
    dest_dir = os.path.join(RAW, "classiccmp", safe.replace(".zip", ""))
    marker = os.path.join(dest_dir, ".ok")
    if os.path.isfile(marker):
        return "skip", url, dest_dir
    try:
        resp = _get(url, timeout=90)
    except Exception as exc:
        return "fail", url, str(exc)
    body = resp.content
    if len(body) < 22 or body[:2] != b"PK":
        return "fail", url, "notzip"
    os.makedirs(dest_dir, exist_ok=True)
    import io
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        return "fail", url, "badzip"
    wrote = 0
    for info in zf.infolist():
        if info.is_dir() or info.file_size > 1_500_000 or info.file_size == 0:
            continue
        member = info.filename.replace("\\", "/").split("/")[-1]
        if not member or member.startswith("."):
            continue
        out = os.path.join(dest_dir, re.sub(r"[^A-Za-z0-9._-]+", "_", member)[:80])
        with open(out, "wb") as f:
            f.write(zf.read(info))
        wrote += 1
    if wrote == 0:
        return "fail", url, "emptyzip"
    with open(marker, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    return "ok", url, dest_dir


def harvest_classiccmp():
    os.makedirs(RAW, exist_ok=True)
    urls = classiccmp_zip_urls()
    print("classiccmp zips to fetch", len(urls), flush=True)
    ok = skip = fail = 0
    with open(PROVENANCE_PATH, "a", encoding="utf-8") as prov, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_download_zip, url) for url in urls]
        done = 0
        for fut in as_completed(futures):
            status, url, info = fut.result()
            done += 1
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
            if status != "skip":
                prov.write(json.dumps({
                    "archive": "classiccmp",
                    "name": url.rsplit("/", 1)[-1],
                    "url": url,
                    "status": status,
                    "path": info if status == "ok" else "",
                    "error": "" if status == "ok" else info,
                }) + "\n")
                prov.flush()
            if done % 200 == 0 or done == len(urls):
                print("classiccmp %d/%d ok=%d skip=%d fail=%d" % (done, len(urls), ok, skip, fail), flush=True)
    return {"zips": len(urls), "ok": ok, "skip": skip, "fail": fail}


def cas_zip_urls():
    """Every [CAS].zip under Model I, Model III, and Model 4. Tape-only Level II."""
    urls = []
    seen = set()
    for model in _MODELS:
        model_url = CLASSICMP + model
        entries = _list_hrefs(model_url)
        pages = [model_url]
        for href in entries:
            if href.endswith("/") and not href.startswith("/"):
                pages.append(urljoin(model_url, href))
        for page in pages:
            names = entries if page == model_url else _list_hrefs(page)
            for name in names:
                if not name.lower().endswith("%5bcas%5d.zip"):
                    continue
                full = urljoin(page, name)
                if full in seen:
                    continue
                seen.add(full)
                urls.append(full)
        print("cas", model, "zips", len(urls), flush=True)
    return urls


def _download_cas_zip(url):
    """Save a [CAS].zip and write each Level II program out as a .bas listing."""
    from detokenize import cas_programs
    tail = url.rstrip("/").split("/")[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", requests.utils.unquote(tail))[:120]
    dest_dir = os.path.join(RAW, "cas", safe.replace(".zip", ""))
    marker = os.path.join(dest_dir, ".ok")
    if os.path.isfile(marker):
        return "skip", url, dest_dir
    try:
        resp = _get(url, timeout=90)
    except Exception as exc:
        return "fail", url, str(exc)
    body = resp.content
    if len(body) < 22 or body[:2] != b"PK":
        return "fail", url, "notzip"
    import io
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        return "fail", url, "badzip"
    os.makedirs(dest_dir, exist_ok=True)
    wrote = 0
    for info in zf.infolist():
        if info.is_dir() or info.file_size > 1_500_000 or info.file_size == 0:
            continue
        member = info.filename.replace("\\", "/").split("/")[-1]
        if not member.lower().endswith(".cas"):
            continue
        data = zf.read(info)
        for n, text in enumerate(cas_programs(data)):
            out = os.path.join(dest_dir, "prog_%d.bas" % n)
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            wrote += 1
    if wrote == 0:
        # Keep the marker so a machine-code tape is not fetched again.
        with open(marker, "w", encoding="utf-8") as f:
            f.write(url + "\n")
        return "ok", url, dest_dir
    with open(marker, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    return "ok", url, dest_dir


def harvest_cas():
    os.makedirs(os.path.join(RAW, "cas"), exist_ok=True)
    urls = cas_zip_urls()
    print("cas zips to fetch", len(urls), flush=True)
    ok = skip = fail = 0
    with open(PROVENANCE_PATH, "a", encoding="utf-8") as prov, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_download_cas_zip, url) for url in urls]
        done = 0
        for fut in as_completed(futures):
            status, url, info = fut.result()
            done += 1
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
            if status != "skip":
                prov.write(json.dumps({
                    "archive": "classiccmp-cas",
                    "name": url.rsplit("/", 1)[-1],
                    "url": url,
                    "status": status,
                    "path": info if status == "ok" else "",
                    "error": "" if status == "ok" else info,
                }) + "\n")
                prov.flush()
            if done % 100 == 0 or done == len(urls):
                print("cas %d/%d ok=%d skip=%d fail=%d" % (done, len(urls), ok, skip, fail), flush=True)
    return {"zips": len(urls), "ok": ok, "skip": skip, "fail": fail}


def dsk_zip_urls():
    """Every [DSK].zip under Model I, Model III, and Model 4."""
    urls = []
    seen = set()
    for model in _MODELS:
        model_url = CLASSICMP + model
        entries = _list_hrefs(model_url)
        pages = [model_url]
        for href in entries:
            if href.endswith("/") and not href.startswith("/"):
                pages.append(urljoin(model_url, href))
        for page in pages:
            names = entries if page == model_url else _list_hrefs(page)
            for name in names:
                if not name.lower().endswith("%5bdsk%5d.zip"):
                    continue
                full = urljoin(page, name)
                if full in seen:
                    continue
                seen.add(full)
                urls.append(full)
        print("dsk", model, "zips", len(urls), flush=True)
    return urls


def _download_dsk_zip(url):
    """Save BASIC programs found on a TRSDOS disk image."""
    from detokenize import disk_programs
    tail = url.rstrip("/").split("/")[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", requests.utils.unquote(tail))[:120]
    dest_dir = os.path.join(RAW, "dsk", safe.replace(".zip", ""))
    marker = os.path.join(dest_dir, ".ok")
    if os.path.isfile(marker):
        return "skip", url, dest_dir
    try:
        resp = _get(url, timeout=90)
    except Exception as exc:
        return "fail", url, str(exc)
    body = resp.content
    if len(body) < 22 or body[:2] != b"PK":
        return "fail", url, "notzip"
    import io
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        return "fail", url, "badzip"
    os.makedirs(dest_dir, exist_ok=True)
    wrote = 0
    for info in zf.infolist():
        if info.is_dir() or info.file_size > 2_000_000 or info.file_size < 8000:
            continue
        member = info.filename.replace("\\", "/").split("/")[-1].lower()
        if not (member.endswith(".dsk") or member.endswith(".dmk") or member.endswith(".jv3") or member.endswith(".jv1")):
            continue
        data = zf.read(info)
        for text in disk_programs(data):
            out = os.path.join(dest_dir, "prog_%d.bas" % wrote)
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            wrote += 1
    with open(marker, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    return "ok", url, dest_dir


def rescan_empty_dsk():
    """Re-read disk zips that had no BASIC. NEWDOS/80 listings live off track 17."""
    from detokenize import disk_programs
    import io
    import zipfile
    root = os.path.join(RAW, "dsk")
    urls = []
    for name in os.listdir(root):
        folder = os.path.join(root, name)
        marker = os.path.join(folder, ".ok")
        if not os.path.isdir(folder) or not os.path.isfile(marker):
            continue
        if any(fn.endswith(".bas") for fn in os.listdir(folder)):
            continue
        url = open(marker, encoding="utf-8").read().strip()
        if url:
            urls.append((url, folder))
    print("empty dsk to rescan", len(urls), flush=True)
    ok = fail = found = 0

    def one(item):
        url, folder = item
        try:
            resp = _get(url, timeout=90)
        except Exception:
            return 0
        body = resp.content
        if len(body) < 22 or body[:2] != b"PK":
            return 0
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile:
            return 0
        wrote = 0
        for info in zf.infolist():
            if info.is_dir() or info.file_size > 2_000_000 or info.file_size < 8000:
                continue
            member = info.filename.replace("\\", "/").split("/")[-1].lower()
            if not member.endswith((".dsk", ".dmk", ".jv3", ".jv1")):
                continue
            for text in disk_programs(zf.read(info)):
                out = os.path.join(folder, "prog_%d.bas" % wrote)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(text)
                wrote += 1
        return wrote

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, item) for item in urls]
        done = 0
        for fut in as_completed(futures):
            done += 1
            n = fut.result()
            if n:
                ok += 1
                found += n
            else:
                fail += 1
            if done % 100 == 0 or done == len(urls):
                print("rescan %d/%d disks=%d programs=%d empty=%d" % (done, len(urls), ok, found, fail), flush=True)
    return {"disks": ok, "programs": found, "empty": fail}


def harvest_dsk():
    os.makedirs(os.path.join(RAW, "dsk"), exist_ok=True)
    urls = dsk_zip_urls()
    print("dsk zips to fetch", len(urls), flush=True)
    ok = skip = fail = 0
    with open(PROVENANCE_PATH, "a", encoding="utf-8") as prov, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_download_dsk_zip, url) for url in urls]
        done = 0
        for fut in as_completed(futures):
            status, url, info = fut.result()
            done += 1
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
            if status != "skip":
                prov.write(json.dumps({
                    "archive": "classiccmp-dsk",
                    "name": url.rsplit("/", 1)[-1],
                    "url": url,
                    "status": status,
                    "path": info if status == "ok" else "",
                    "error": "" if status == "ok" else info,
                }) + "\n")
                prov.flush()
            if done % 100 == 0 or done == len(urls):
                print("dsk %d/%d ok=%d skip=%d fail=%d" % (done, len(urls), ok, skip, fail), flush=True)
    return {"zips": len(urls), "ok": ok, "skip": skip, "fail": fail}


def harvest():
    ensure_index()
    items = parse_catalog()
    print("willus files to fetch", len(items), flush=True)
    os.makedirs(os.path.join(RAW, "willus"), exist_ok=True)
    ok = skip = fail = 0
    with open(PROVENANCE_PATH, "a", encoding="utf-8") as prov, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_download_one, item) for item in items]
        done = 0
        for fut in as_completed(futures):
            status, item, info = fut.result()
            done += 1
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
            if status != "skip":
                rec = {
                    "archive": item["archive"],
                    "name": item["name"],
                    "url": item["url"],
                    "status": status,
                    "path": info if status == "ok" else "",
                    "error": "" if status == "ok" else info,
                }
                prov.write(json.dumps(rec) + "\n")
            if done % 500 == 0 or done == len(items):
                print("willus %d/%d ok=%d skip=%d fail=%d" % (done, len(items), ok, skip, fail), flush=True)
    local = copy_local()
    with open(PROVENANCE_PATH, "a", encoding="utf-8") as prov:
        for rec in local:
            prov.write(json.dumps({
                "archive": "repo",
                "name": rec["name"],
                "url": rec["url"],
                "status": "ok",
                "path": rec["path"],
                "error": "",
            }) + "\n")
    print("local bas", len(local), flush=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")
    return {"willus": len(items), "ok": ok, "skip": skip, "fail": fail, "local": len(local)}
