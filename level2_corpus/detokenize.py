# Detokenize TRS-80 Model I / III Level II BASIC programs.
# Disk and cassette saves store keywords as one byte (0x80-0xFB) after a 0xFF
# header. Each line is: next-address (2), line number (2), tokens, 0x00.
# The next-address is a RAM pointer, not a file offset, so lines are read in order.

# Token 0x80 is END. Order matches the Model I Level II ROM, including the
# Tandy words RESET/SET/CLS/CMD/RANDOM that shift the rest of the Microsoft list.
_TOKEN_NAMES = [
    "END", "FOR", "RESET", "SET", "CLS", "CMD", "RANDOM", "NEXT",
    "DATA", "INPUT", "DIM", "READ", "LET", "GOTO", "RUN", "IF",
    "RESTORE", "GOSUB", "RETURN", "REM", "STOP", "ELSE", "TRON", "TROFF",
    "DEFSTR", "DEFINT", "DEFSNG", "DEFDBL", "LINE", "EDIT", "ERROR", "RESUME",
    "OUT", "ON", "OPEN", "FIELD", "GET", "PUT", "CLOSE", "LOAD",
    "MERGE", "NAME", "KILL", "LSET", "RSET", "SAVE", "SYSTEM", "LPRINT",
    "DEF", "POKE", "PRINT", "CONT", "LIST", "LLIST", "DELETE", "AUTO",
    "CLEAR", "CLOAD", "CSAVE", "NEW", "TAB(", "TO", "FN", "USING",
    "VARPTR", "USR", "ERL", "ERR", "STRING$", "INSTR", "POINT", "TIME$",
    "MEM", "INKEY$", "THEN", "NOT", "STEP", "+", "-", "*",
    "/", "^", "AND", "OR", ">", "=", "<", "SGN",
    "INT", "ABS", "FRE", "INP", "POS", "SQR", "RND", "LOG",
    "EXP", "COS", "SIN", "TAN", "ATN", "PEEK", "CVI", "CVS",
    "CVD", "EOF", "LOC", "LOF", "MKI$", "MKS$", "MKD$", "CINT",
    "CSNG", "CDBL", "FIX", "LEN", "STR$", "VAL", "ASC", "CHR$",
    "LEFT$", "RIGHT$", "MID$", "'",
]
TOKENS = {0x80 + i: name for i, name in enumerate(_TOKEN_NAMES)}

# These swallow the rest of the line as typed characters, not as further tokens.
_REST_OF_LINE = {"REM", "'"}


def _decode_chunk(chunk):
    """Turn one tokenized line body into source text."""
    out = []
    i = 0
    n = len(chunk)
    while i < n:
        b = chunk[i]
        if b == 0x22:
            j = i + 1
            while j < n and chunk[j] != 0x22:
                j += 1
            end = j + 1 if j < n else n
            out.append(chunk[i:end].decode("latin1"))
            i = end
            continue
        if b >= 0x80:
            name = TOKENS.get(b)
            if name is None:
                out.append("?&H%02X" % b)
                i += 1
                continue
            out.append(name)
            i += 1
            if name in _REST_OF_LINE:
                # The apostrophe remark is itself a token (0xFB). Inside a REM
                # it must stay a quote character, not a Latin-1 byte.
                rest = chunk[i:].replace(bytes([0xFB]), b"'")
                if name == "REM" and rest and rest[0:1] != b" ":
                    out.append(" ")
                out.append(rest.decode("latin1"))
                break
            continue
        out.append(chr(b))
        i += 1
    return "".join(out)


def _iter_token_lines(data):
    """Yield (line_number, text) from a tokenized image, or stop if it is not one."""
    if len(data) < 5:
        return
    i = 1 if data[0] == 0xFF else 0
    lines = 0
    while i + 4 <= len(data):
        nxt = data[i] | (data[i + 1] << 8)
        line_no = data[i + 2] | (data[i + 3] << 8)
        # A 0,0 record is the end of the program. A wild line number means
        # this was never tokenized BASIC, so the caller should try plain text.
        if nxt == 0 and line_no == 0:
            break
        if line_no > 65529:
            return
        i += 4
        end = data.find(b"\x00", i)
        if end < 0:
            chunk = data[i:]
            i = len(data)
        else:
            chunk = data[i:end]
            i = end + 1
        yield line_no, _decode_chunk(chunk)
        lines += 1
        if lines > 100000:
            return
        if nxt == 0:
            break


def detokenize(data):
    """Return source text for a tokenized program, or None if it does not look like one."""
    if not data:
        return None
    lines = list(_iter_token_lines(data))
    if len(lines) < 3:
        return None
    text = "\n".join("%d %s" % (n, body) for n, body in lines)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.count("?&H") > max(8, len(text) // 40):
        return None
    return text + "\n"


def decode_text(data):
    """Plain ASCII / Latin-1 listing. Newlines normalized to LF."""
    text = data.decode("latin1", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    if not text.endswith("\n"):
        text += "\n"
    return text


def to_source(data):
    """ASCII listing if the bytes are already text, otherwise detokenize."""
    if not data:
        return None
    sample = data[:4000]
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127)
    if printable / max(1, len(sample)) > 0.90:
        return decode_text(data)
    return detokenize(data)


_CAS_KEYWORDS = (
    " REM", " PRINT", " CLS", " GOTO", " FOR", " INPUT",
    " DATA", " IF", " DIM", " GOSUB", " POKE",
)


def cas_programs(data):
    """Level II programs inside an emulator .cas image. One tape can hold several."""
    if not data or data.find(b"\xa5") < 0:
        return []
    found = []
    i = 0
    n = len(data)
    while i < n and len(found) < 40:
        if data[i] != 0xA5:
            i += 1
            continue
        hit_at = None
        text = None
        for delta in range(1, 48):
            off = i + delta
            if off + 6 > n:
                break
            text = detokenize(data[off:])
            if not text:
                continue
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) < 3:
                continue
            nums = []
            for ln in lines[:8]:
                part = ln.split(" ", 1)[0]
                if not part.isdigit():
                    nums = []
                    break
                nums.append(int(part))
            if len(nums) < 3 or nums != sorted(nums):
                continue
            head = "\n".join(lines[:8])
            if not any(word in head for word in _CAS_KEYWORDS):
                continue
            hit_at = off
            break
        if hit_at is None:
            i += 1
            continue
        found.append(text)
        # Next program is after the blank leader that follows this one.
        j = hit_at
        i = n
        while j + 8 < n:
            if data[j:j + 8] == b"\x00" * 8:
                i = j
                break
            j += 1
    return found


# Commodore BASIC 2.0 tokens (VIC-20 / C64 / PET). Same line layout as Level II
# after a 2-byte load address. Keywords are 0x80-0xCB. This is not the Level II table.
_CBM = {
    0x80: "END", 0x81: "FOR", 0x82: "NEXT", 0x83: "DATA", 0x84: "INPUT#",
    0x85: "INPUT", 0x86: "DIM", 0x87: "READ", 0x88: "LET", 0x89: "GOTO",
    0x8A: "RUN", 0x8B: "IF", 0x8C: "RESTORE", 0x8D: "GOSUB", 0x8E: "RETURN",
    0x8F: "REM", 0x90: "STOP", 0x91: "ON", 0x92: "WAIT", 0x93: "LOAD",
    0x94: "SAVE", 0x95: "VERIFY", 0x96: "DEF", 0x97: "POKE", 0x98: "PRINT#",
    0x99: "PRINT", 0x9A: "CONT", 0x9B: "LIST", 0x9C: "CLR", 0x9D: "CMD",
    0x9E: "SYS", 0x9F: "OPEN", 0xA0: "CLOSE", 0xA1: "GET", 0xA2: "NEW",
    0xA3: "TAB(", 0xA4: "TO", 0xA5: "FN", 0xA6: "SPC(", 0xA7: "THEN",
    0xA8: "NOT", 0xA9: "STEP", 0xAA: "+", 0xAB: "-", 0xAC: "*", 0xAD: "/",
    0xAE: "^", 0xAF: "AND", 0xB0: "OR", 0xB1: ">", 0xB2: "=", 0xB3: "<",
    0xB4: "SGN", 0xB5: "INT", 0xB6: "ABS", 0xB7: "USR", 0xB8: "FRE",
    0xB9: "POS", 0xBA: "SQR", 0xBB: "RND", 0xBC: "LOG", 0xBD: "EXP",
    0xBE: "COS", 0xBF: "SIN", 0xC0: "TAN", 0xC1: "ATN", 0xC2: "PEEK",
    0xC3: "LEN", 0xC4: "STR$", 0xC5: "VAL", 0xC6: "ASC", 0xC7: "CHR$",
    0xC8: "LEFT$", 0xC9: "RIGHT$", 0xCA: "MID$", 0xCB: "GO",
}


def _petscii(b):
    """Letters, digits, and punctuation. Screen-graphics bytes are dropped."""
    if 32 <= b <= 90 or b in (91, 93, 95):
        return chr(b)
    if 97 <= b <= 122:
        return chr(b)
    return ""


def cbm_to_source(data):
    """Detokenize a Commodore .prg that is a BASIC program."""
    if not data or len(data) < 8:
        return None
    i = 2
    lines = []
    while i + 4 <= len(data) and len(lines) < 20000:
        nxt = data[i] | (data[i + 1] << 8)
        line_no = data[i + 2] | (data[i + 3] << 8)
        if nxt == 0:
            break
        if line_no > 63999:
            return None
        i += 4
        body, i = _cbm_line(data, i)
        lines.append("%d %s" % (line_no, body))
    if len(lines) < 3:
        return None
    # A one-line SYS stub plus garbage still has a rising line number. Require
    # a real statement in the first lines.
    head = "\n".join(lines[:8])
    if not any(word in head for word in (" PRINT", " GOTO", " FOR", " IF", " GOSUB", " INPUT", " POKE", " REM", " DATA")):
        return None
    return "\n".join(lines) + "\n"


def _cbm_line(data, i):
    out = []
    quote = False
    while i < len(data):
        b = data[i]
        i += 1
        if b == 0:
            break
        if b == 34:
            quote = not quote
            out.append('"')
            continue
        if not quote and b == 0x8F:
            rest = []
            while i < len(data) and data[i] != 0:
                rest.append(_petscii(data[i]) if data[i] != 34 else '"')
                i += 1
            if i < len(data) and data[i] == 0:
                i += 1
            text = "".join(rest)
            if text.startswith(" "):
                out.append("REM" + text)
            else:
                out.append("REM " + text)
            break
        if not quote and b in _CBM:
            name = _CBM[b]
            if out and out[-1] not in " (":
                out.append(" ")
            out.append(name)
            if not name.endswith(("(", "$", "#", "+", "-", "*", "/", "^", ">", "=", "<")):
                out.append(" ")
            continue
        ch = _petscii(b)
        if ch:
            out.append(ch)
    return "".join(out).strip(), i


# TRSDOS 2.3 keeps BASIC in a directory on track 17. A granule is 5 sectors.
# Extent byte: bits 5-7 are the starting granule, bits 0-4 are granule count minus 1.
_DISK_EXT = ("BAS", "TXT", "ASC", "DEM", "BA")


def _jv3_sectors(data):
    """JV3 image: 8704-byte sector table, then the sector bodies."""
    if len(data) < 8704 or (len(data) - 8704) % 256:
        return None
    sectors = {}
    off = 8704
    for n in range(2901):
        trk, sec, flg = data[n * 3:n * 3 + 3]
        if trk == 0xFF:
            continue
        size = (256, 128, 1024, 512)[flg & 3]
        if off + size > len(data):
            return None
        sectors[(trk, sec)] = data[off:off + size]
        off += size
    if off != len(data) or (17, 2) not in sectors:
        return None
    return sectors


def _jv1_sectors(data):
    """Raw sectors, 10 per track. 35-track images are 89600 bytes."""
    if len(data) % 2560:
        return None
    tracks = len(data) // 2560
    if tracks < 35 or tracks > 80:
        return None
    sectors = {}
    for trk in range(tracks):
        for sec in range(10):
            off = (trk * 10 + sec) * 256
            sectors[(trk, sec)] = data[off:off + 256]
    return sectors


def _dmk_sectors(data):
    """DMK image. Sector bodies are pulled out of the raw track."""
    if len(data) < 16:
        return None
    tracks = data[1]
    trklen = data[2] | (data[3] << 8)
    if not (35 <= tracks <= 80) or trklen < 300:
        return None
    if 16 + tracks * trklen != len(data):
        return None
    sectors = {}
    for trk in range(tracks):
        base = 16 + trk * trklen
        for i in range(0, 128, 2):
            word = data[base + i] | (data[base + i + 1] << 8)
            if word == 0:
                continue
            fe = base + (word & 0x3FFF)
            if fe + 8 >= len(data) or data[fe] != 0xFE:
                continue
            sec = data[fe + 3]
            ln = 128 << data[fe + 4] if data[fe + 4] < 4 else 256
            j = fe + 7
            limit = min(len(data), fe + 60)
            while j < limit and data[j] not in (0xFB, 0xF8, 0xF9, 0xFA):
                j += 1
            if j >= limit or j + 1 + ln > len(data):
                continue
            sectors[(trk, sec)] = data[j + 1:j + 1 + ln]
    if (17, 2) not in sectors:
        return None
    return sectors


def _trsdos_file(sectors, rec):
    """Bytes of one TRSDOS 2.3 file, or empty if the entry is not a file."""
    eof_byte = rec[3]
    rel = rec[0x14] | (rec[0x15] << 8)
    nsec = rel if eof_byte == 0 else max(0, rel - 1)
    if nsec <= 0 or nsec > 400:
        return b""
    chunks = []
    for i in range(0x16, 0x20, 2):
        track, desc = rec[i], rec[i + 1]
        if track >= 0xFE:
            break
        gran = (desc >> 5) & 7
        sec = gran * 5
        ngran = (desc & 0x1F) + 1
        trk = track
        for _ in range(ngran * 5):
            chunks.append(sectors.get((trk, sec), b"\xe5" * 256))
            sec += 1
            if sec >= 10:
                sec = 0
                trk += 1
            if len(chunks) >= nsec:
                break
        if len(chunks) >= nsec:
            break
    blob = b"".join(chunks[:nsec])
    if eof_byte:
        blob = blob[:(nsec - 1) * 256 + min(eof_byte, 256)]
    return blob


def disk_programs(data):
    """Level II programs stored on a TRSDOS 2.3 disk image (JV3, JV1, or DMK)."""
    sectors = _jv3_sectors(data) or _dmk_sectors(data) or _jv1_sectors(data)
    if not sectors:
        return []
    found = []
    for secno in range(2, 10):
        sec = sectors.get((17, secno))
        if not sec or len(sec) < 256:
            continue
        for i in range(0, 256, 32):
            rec = sec[i:i + 32]
            # Bit 4 set means the entry is in use. Bit 7 set means an extension record.
            if rec[0] & 0x80 or not (rec[0] & 0x10):
                continue
            ext = rec[13:16].decode("latin1").strip()
            if ext not in _DISK_EXT:
                continue
            text = detokenize(_trsdos_file(sectors, rec))
            if not text:
                continue
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) < 3:
                continue
            head = "\n".join(lines[:8])
            if not any(word in head for word in _CAS_KEYWORDS):
                continue
            found.append(text)
    found.extend(_newdos_programs(sectors))
    # The same listing can be reached by both directory layouts.
    unique = []
    seen = set()
    for text in found:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _numbered_lines(text):
    """Lines that start with a BASIC line number, not wrapped remark text."""
    out = []
    for line in text.split("\n"):
        raw = line.lstrip()
        j = 0
        while j < len(raw) and raw[j].isdigit():
            j += 1
        if 1 <= j <= 5 and (j == len(raw) or raw[j] == " "):
            out.append((int(raw[:j]), line))
    return out


def _trim_listing(text):
    """Drop the tail where the next file's bytes were read as more lines."""
    if not text:
        return None
    kept = []
    prev = 0
    started = False
    for line in text.split("\n"):
        raw = line.lstrip()
        j = 0
        while j < len(raw) and raw[j].isdigit():
            j += 1
        if not (1 <= j <= 5 and (j == len(raw) or raw[j] == " ")):
            if started:
                kept.append(line)
            continue
        num = int(raw[:j])
        jumped = started and num > prev + 4000 and not any(w in line for w in _CAS_KEYWORDS)
        if started and (num < prev or jumped):
            break
        started = True
        prev = num
        kept.append(line)
    if len(_numbered_lines("\n".join(kept))) < 5:
        return None
    return "\n".join(kept) + ("\n" if kept else "")


def _listing_ok(text):
    lines = _numbered_lines(text or "")
    if len(lines) < 5:
        return False
    nums = [n for n, _ in lines[:12]]
    if nums != sorted(nums):
        return False
    if not any(word in text[:2500] for word in _CAS_KEYWORDS):
        return False
    last = lines[-1][1]
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in last):
        return False
    if text.count("?&H") > 6:
        return False
    return True


def _newdos_programs(sectors):
    """BAS files on NEWDOS/80 disks. Granules are 5 sectors, GPL is 1, 2, or 3."""
    if not sectors:
        return []
    spt = max(sec for _, sec in sectors) + 1
    if spt < 10 or spt > 18:
        return []
    found = []
    seen = set()
    for blob in sectors.values():
        if len(blob) < 256:
            continue
        for i in range(0, 256, 32):
            rec = blob[i:i + 32]
            if rec[0] & 0x80 or not (rec[0] & 0x10):
                continue
            if rec[13:16] != b"BAS":
                continue
            name = rec[5:13]
            if not all(32 <= b < 127 for b in name):
                continue
            key = bytes(name)
            if key in seen:
                continue
            text = _best_newdos(sectors, rec, spt)
            if not text:
                continue
            seen.add(key)
            found.append(text)
    return found


def _best_newdos(sectors, rec, spt):
    e0, e1 = rec[22], rec[23]
    rel = rec[0x14] | (rec[0x15] << 8)
    gran = (e1 >> 5) & 7
    ngran = (e1 & 0x1F) + 1
    best = None
    best_key = None
    for gpl in (1, 2, 3):
        start = (e0 * gpl + gran) * 5
        for nsec in (ngran * 5, rel, max(1, rel - 1)):
            if not 1 <= nsec <= 80:
                continue
            parts = []
            missing = False
            for k in range(nsec):
                trk, sec = divmod(start + k, spt)
                piece = sectors.get((trk, sec))
                if not piece:
                    missing = True
                    break
                parts.append(piece)
            if missing:
                continue
            blob = b"".join(parts)
            if blob[:1] != b"\xff":
                continue
            text = _trim_listing(detokenize(blob))
            if not _listing_ok(text):
                continue
            # Prefer the length the directory asked for, then the longer listing.
            rank = (abs(nsec - (rel or nsec)), -len(_numbered_lines(text)))
            if best_key is None or rank < best_key:
                best_key = rank
                best = text
    return best


# GW-BASIC / BASICA tokens. One-byte keywords are 0x81 and up. 0xFD, 0xFE, and
# 0xFF introduce a second byte. Numbers 0-10 are the single bytes 0x11-0x1B.
# This is a different table from Model I Level II, so do not reuse TOKENS.
_GW_ONE = {
    0x81: "END", 0x82: "FOR", 0x83: "NEXT", 0x84: "DATA", 0x85: "INPUT",
    0x86: "DIM", 0x87: "READ", 0x88: "LET", 0x89: "GOTO", 0x8A: "RUN",
    0x8B: "IF", 0x8C: "RESTORE", 0x8D: "GOSUB", 0x8E: "RETURN", 0x8F: "REM",
    0x90: "STOP", 0x91: "PRINT", 0x92: "CLEAR", 0x93: "LIST", 0x94: "NEW",
    0x95: "ON", 0x96: "WAIT", 0x97: "DEF", 0x98: "POKE", 0x99: "CONT",
    0x9C: "OUT", 0x9D: "LPRINT", 0x9E: "LLIST", 0xA0: "WIDTH", 0xA1: "ELSE",
    0xA2: "TRON", 0xA3: "TROFF", 0xA4: "SWAP", 0xA5: "ERASE", 0xA6: "EDIT",
    0xA7: "ERROR", 0xA8: "RESUME", 0xA9: "DELETE", 0xAA: "AUTO", 0xAB: "RENUM",
    0xAC: "DEFSTR", 0xAD: "DEFINT", 0xAE: "DEFSNG", 0xAF: "DEFDBL", 0xB0: "LINE",
    0xB1: "WHILE", 0xB2: "WEND", 0xB3: "CALL", 0xB7: "WRITE", 0xB8: "OPTION",
    0xB9: "RANDOMIZE", 0xBA: "OPEN", 0xBB: "CLOSE", 0xBC: "LOAD", 0xBD: "MERGE",
    0xBE: "SAVE", 0xBF: "COLOR", 0xC0: "CLS", 0xC1: "MOTOR", 0xC2: "BSAVE",
    0xC3: "BLOAD", 0xC4: "SOUND", 0xC5: "BEEP", 0xC6: "PSET", 0xC7: "PRESET",
    0xC8: "SCREEN", 0xC9: "KEY", 0xCA: "LOCATE", 0xCC: "TO", 0xCD: "THEN",
    0xCE: "TAB(", 0xCF: "STEP", 0xD0: "USR", 0xD1: "FN", 0xD2: "SPC(",
    0xD3: "NOT", 0xD4: "ERL", 0xD5: "ERR", 0xD6: "STRING$", 0xD7: "USING",
    0xD8: "INSTR", 0xD9: "'", 0xDA: "VARPTR", 0xDB: "CSRLIN", 0xDC: "POINT",
    0xDD: "OFF", 0xDE: "INKEY$", 0xE6: ">", 0xE7: "=", 0xE8: "<",
    0xE9: "+", 0xEA: "-", 0xEB: "*", 0xEC: "/", 0xED: "^",
    0xEE: "AND", 0xEF: "OR", 0xF0: "XOR", 0xF1: "EQV", 0xF2: "IMP",
    0xF3: "MOD", 0xF4: "\\",
}
_GW_TWO = {
    (0xFD, 0x81): "CVI", (0xFD, 0x82): "CVS", (0xFD, 0x83): "CVD",
    (0xFD, 0x84): "MKI$", (0xFD, 0x85): "MKS$", (0xFD, 0x86): "MKD$",
    (0xFD, 0x8B): "EXTERR",
    (0xFE, 0x81): "FILES", (0xFE, 0x82): "FIELD", (0xFE, 0x83): "SYSTEM",
    (0xFE, 0x84): "NAME", (0xFE, 0x85): "LSET", (0xFE, 0x86): "RSET",
    (0xFE, 0x87): "KILL", (0xFE, 0x88): "PUT", (0xFE, 0x89): "GET",
    (0xFE, 0x8A): "RESET", (0xFE, 0x8B): "COMMON", (0xFE, 0x8C): "CHAIN",
    (0xFE, 0x8D): "DATE$", (0xFE, 0x8E): "TIME$", (0xFE, 0x8F): "PAINT",
    (0xFE, 0x90): "COM", (0xFE, 0x91): "CIRCLE", (0xFE, 0x92): "DRAW",
    (0xFE, 0x93): "PLAY", (0xFE, 0x94): "TIMER", (0xFE, 0x95): "ERDEV",
    (0xFE, 0x96): "IOCTL", (0xFE, 0x97): "CHDIR", (0xFE, 0x98): "MKDIR",
    (0xFE, 0x99): "RMDIR", (0xFE, 0x9A): "SHELL", (0xFE, 0x9B): "ENVIRON",
    (0xFE, 0x9C): "VIEW", (0xFE, 0x9D): "WINDOW", (0xFE, 0x9E): "PMAP",
    (0xFE, 0x9F): "PALETTE", (0xFE, 0xA0): "LCOPY", (0xFE, 0xA1): "CALLS",
    (0xFE, 0xA4): "NOISE", (0xFE, 0xA5): "PCOPY", (0xFE, 0xA6): "TERM",
    (0xFE, 0xA7): "LOCK", (0xFE, 0xA8): "UNLOCK",
    (0xFF, 0x81): "LEFT$", (0xFF, 0x82): "RIGHT$", (0xFF, 0x83): "MID$",
    (0xFF, 0x84): "SGN", (0xFF, 0x85): "INT", (0xFF, 0x86): "ABS",
    (0xFF, 0x87): "SQR", (0xFF, 0x88): "RND", (0xFF, 0x89): "SIN",
    (0xFF, 0x8A): "LOG", (0xFF, 0x8B): "EXP", (0xFF, 0x8C): "COS",
    (0xFF, 0x8D): "TAN", (0xFF, 0x8E): "ATN", (0xFF, 0x8F): "FRE",
    (0xFF, 0x90): "INP", (0xFF, 0x91): "POS", (0xFF, 0x92): "LEN",
    (0xFF, 0x93): "STR$", (0xFF, 0x94): "VAL", (0xFF, 0x95): "ASC",
    (0xFF, 0x96): "CHR$", (0xFF, 0x97): "PEEK", (0xFF, 0x98): "SPACE$",
    (0xFF, 0x99): "OCT$", (0xFF, 0x9A): "HEX$", (0xFF, 0x9B): "LPOS",
    (0xFF, 0x9C): "CINT", (0xFF, 0x9D): "CSNG", (0xFF, 0x9E): "CDBL",
    (0xFF, 0x9F): "FIX", (0xFF, 0xA0): "PEN", (0xFF, 0xA1): "STICK",
    (0xFF, 0xA2): "STRIG", (0xFF, 0xA3): "EOF", (0xFF, 0xA4): "LOC",
    (0xFF, 0xA5): "LOF",
}


def _mbf_single(raw):
    """Microsoft Binary Format 32-bit float, as stored in a tokenized number."""
    if raw[3] == 0:
        return "0"
    sign = -1.0 if raw[2] & 0x80 else 1.0
    exp = raw[3] - 129
    mant = raw[0] | (raw[1] << 8) | ((raw[2] & 0x7F) << 16) | 0x800000
    value = sign * (mant / 16777216.0) * (2.0 ** exp)
    return _trim_num(value)


def _trim_num(value):
    text = "%.8g" % value
    return text


def _gw_decode_chunk(chunk):
    """One tokenized GW-BASIC line body."""
    out = []
    i = 0
    n = len(chunk)
    while i < n:
        b = chunk[i]
        if b == 0x22:
            j = i + 1
            while j < n and chunk[j] != 0x22:
                j += 1
            end = j + 1 if j < n else n
            out.append(chunk[i:end].decode("cp437"))
            i = end
            continue
        if b in (0xFD, 0xFE, 0xFF) and i + 1 < n:
            name = _GW_TWO.get((b, chunk[i + 1]))
            if name:
                out.append(name)
                i += 2
                continue
        if b >= 0x80:
            name = _GW_ONE.get(b)
            if name is None:
                out.append("?&H%02X" % b)
                i += 1
                continue
            out.append(name)
            i += 1
            if name in ("REM", "'"):
                rest = chunk[i:]
                if name == "REM" and rest and rest[:1] != b" ":
                    out.append(" ")
                out.append(rest.decode("cp437"))
                break
            continue
        # Compressed numbers. The token is the value; digits are not also stored.
        if 0x11 <= b <= 0x1B:
            out.append(str(b - 0x11))
            i += 1
            continue
        if b in (0x0D, 0x0E) and i + 2 < n:
            out.append(str(chunk[i + 1] | (chunk[i + 2] << 8)))
            i += 3
            continue
        if b == 0x0F and i + 1 < n:
            out.append(str(chunk[i + 1]))
            i += 2
            continue
        if b == 0x1C and i + 2 < n:
            out.append(str(int.from_bytes(chunk[i + 1:i + 3], "little", signed=True)))
            i += 3
            continue
        if b == 0x1D and i + 4 < n:
            out.append(_mbf_single(chunk[i + 1:i + 5]))
            i += 5
            continue
        if b == 0x1F and i + 8 < n:
            out.append(_trim_num(_mbf_double(chunk[i + 1:i + 9])))
            i += 9
            continue
        if b == 0x0C and i + 2 < n:
            out.append("&H%X" % (chunk[i + 1] | (chunk[i + 2] << 8)))
            i += 3
            continue
        if b == 0x0B and i + 2 < n:
            out.append("&O%o" % (chunk[i + 1] | (chunk[i + 2] << 8)))
            i += 3
            continue
        out.append(bytes([b]).decode("cp437"))
        i += 1
    return "".join(out)


def _mbf_double(raw):
    """Microsoft Binary Format 64-bit float."""
    if raw[7] == 0:
        return 0.0
    sign = -1.0 if raw[6] & 0x80 else 1.0
    exp = raw[7] - 129
    mant = 0
    for k in range(7):
        mant |= raw[k] << (8 * k)
    mant = (mant & ((1 << 55) - 1)) | (1 << 55)
    return sign * (mant / float(1 << 56)) * (2.0 ** exp)


def _gw_line_end(data, i):
    """Index of the 0x00 that ends this line.

    Numeric tokens are allowed to contain 0x00 (the high byte of a small
    integer or line number), so a raw search for 0x00 would split the line.
    """
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0:
            return i
        if b == 0x22:
            i += 1
            while i < n and data[i] != 0 and data[i] != 0x22:
                i += 1
            i = min(n, i + 1)
            continue
        if b in (0xFD, 0xFE, 0xFF) and i + 1 < n and data[i + 1] >= 0x80:
            i += 2
            continue
        if b in (0x0B, 0x0C, 0x0D, 0x0E, 0x1C):
            i += 3
            continue
        if b == 0x0F:
            i += 2
            continue
        if b == 0x1D:
            i += 5
            continue
        if b == 0x1F:
            i += 9
            continue
        i += 1
    return n


def gw_to_source(data):
    """GW-BASIC listing. Tokenized files start with 0xFF. Plain files are CP437 text."""
    if not data:
        return None
    if data[0] != 0xFF:
        text = data.decode("cp437", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        if not text.endswith("\n"):
            text += "\n"
        return text
    i = 1
    lines = []
    while i + 4 <= len(data):
        nxt = data[i] | (data[i + 1] << 8)
        # Two zero bytes are the end of the program. The bytes after that are
        # often a Ctrl-Z (0x1A) and must not become another line.
        if nxt == 0:
            break
        line_no = data[i + 2] | (data[i + 3] << 8)
        if line_no > 65529:
            return None
        i += 4
        end = _gw_line_end(data, i)
        chunk = data[i:end]
        i = end + 1 if end < len(data) else len(data)
        lines.append("%d %s" % (line_no, _gw_decode_chunk(chunk)))
        if len(lines) > 100000:
            return None
    if not lines:
        return None
    text = "\n".join(lines) + "\n"
    if text.count("?&H") > max(8, len(text) // 40):
        return None
    return text
