"""Optional SD, PWM audio, and display hooks for an ESP32 board."""
import os
import time

import board_config as cfg


class Hardware:
    def __init__(self, log=print):
        self.log = log
        self.display = None
        self.speaker = None
        self.mount_sd()
        try:
            from display_driver import create_display
            self.display = create_display()
        except ImportError:
            pass
        if cfg.SPEAKER_PIN is not None:
            from machine import Pin, PWM
            self.speaker = PWM(Pin(cfg.SPEAKER_PIN), freq=880, duty_u16=0)

    def mount_sd(self):
        # A missing card must not take the display down with it.
        try:
            ensure_sd()
        except Exception:
            pass

    def tone(self, frequency, milliseconds):
        if self.speaker is None:
            return
        if frequency == 0:
            self.speaker.duty_u16(0)
            return
        self.speaker.freq(max(1, frequency))
        self.speaker.duty_u16(16000)
        if milliseconds:
            time.sleep_ms(milliseconds)
            self.speaker.duty_u16(0)

    def draw(self, machine):
        d = self.display
        if d is None:
            return
        from font5x8 import FONT
        width, height = cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT
        scale_x, scale_y = max(1, width // 64), max(1, height // 16)
        left = (width - scale_x * 64) // 2
        top = (height - scale_y * 16) // 2
        fg = cfg.PALETTE[machine.color_fg]
        bg = cfg.PALETTE[machine.color_bg]
        # Read keys a few times while the glyphs are drawn. The panel paint is the long part.
        panel = getattr(d, 'panel', None)
        hook = getattr(panel, 'while_busy', None) if panel is not None else None
        # The keyboard clock is always held low outside ps2_keys(), so keys
        # typed during this paint wait inside the keyboard until the hook listens.
        d.fill(bg)
        for y in range(48):
            if hook is not None and y % 8 == 0:
                try:
                    hook()
                except Exception:
                    pass
            for x in range(128):
                bit = y * 128 + x
                if machine.pixels[bit // 8] & (1 << (bit % 8)):
                    px = left + x * scale_x // 2
                    py = top + y * scale_y // 3
                    color = cfg.PALETTE[machine.pixel_colors.get(bit, machine.color_fg)]
                    d.fill_rect(px, py, max(1, scale_x // 2), max(1, scale_y // 3), color)
        for row in range(16):
            if hook is not None and row % 4 == 0:
                try:
                    hook()
                except Exception:
                    pass
            for col in range(64):
                character = machine.screen[row][col]
                glyph = FONT.get(character)
                if glyph:
                    px, py = left + col * scale_x, top + row * scale_y
                    ink = cfg.PALETTE[machine.text_colors[row * 64 + col]]
                    # 5x8 glyph, plus a 1-pixel gap. Grow it to fill the cell
                    # so the console is readable in the center of a large panel.
                    gs = max(1, min(scale_x // 6, scale_y // 8))
                    for gx, bits in enumerate(glyph):
                        for gy in range(8):
                            if bits & (1 << gy):
                                d.fill_rect(px + gx * gs, py + gy * gs, gs, gs, ink)
        # Fast update always repaints the whole panel, so the cursor is a solid
        # block in the next-key cell. A blink would refresh the page every time.
        cur = machine.cursor
        if 0 <= cur < 1024:
            row, col = divmod(cur, 64)
            px, py = left + col * scale_x, top + row * scale_y
            # Any non-zero color is black ink on this panel.
            d.fill_rect(px, py, scale_x, scale_y, 1)
        if hasattr(d, 'show'):
            d.show()

    def draw_cells(self, machine, indexes):
        """Redraw only the cells that a key just changed, then a partial panel update."""
        d = self.display
        if d is None or not hasattr(d, 'show_rows'):
            return
        from font5x8 import FONT
        width, height = cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT
        scale_x, scale_y = max(1, width // 64), max(1, height // 16)
        left = (width - scale_x * 64) // 2
        top = (height - scale_y * 16) // 2
        bg = cfg.PALETTE[machine.color_bg]
        gs = max(1, min(scale_x // 6, scale_y // 8))
        y0, y1 = height, -1
        for index in indexes:
            if index < 0 or index >= 1024:
                continue
            row, col = divmod(index, 64)
            px, py = left + col * scale_x, top + row * scale_y
            d.fill_rect(px, py, scale_x, scale_y, bg)
            glyph = FONT.get(machine.screen[row][col])
            ink = cfg.PALETTE[machine.text_colors[index]]
            if glyph:
                for gx, bits in enumerate(glyph):
                    for gy in range(8):
                        if bits & (1 << gy):
                            d.fill_rect(px + gx * gs, py + gy * gs, gs, gs, ink)
            if py < y0:
                y0 = py
            bottom = py + scale_y - 1
            if bottom > y1:
                y1 = bottom
        if y1 >= y0:
            d.show_rows(y0, y1)


# Bare LOAD "STARTREK" tries these, same order as the FPGA card.
_LOAD_SUFFIXES = ('.BAS', '.DAT', '.JMR', '.TXT')

# os.mount succeeded. None when the FPGA's small FAT32 volume is mounted below.
_vol = None
_sd_card = None


def _card_mounted():
    """True when /sd is a different volume, not an empty folder on flash."""
    try:
        os.listdir(cfg.SD_MOUNT)
        return os.statvfs(cfg.SD_MOUNT)[2] != os.statvfs('/')[2]
    except OSError:
        return False


def ensure_sd():
    """Mount the microSD if it is not already the /sd volume."""
    global _vol, _sd_card
    if _vol is not None or _card_mounted():
        return
    if cfg.SD_SPI_PINS is None:
        raise ValueError('SD not mounted')
    from machine import Pin, SDCard
    if cfg.SD_POWER_PIN is not None:
        Pin(cfg.SD_POWER_PIN, Pin.OUT, value=1)
        time.sleep_ms(200)
    sck, mosi, miso, cs = cfg.SD_SPI_PINS
    card = SDCard(slot=2, sck=Pin(sck), mosi=Pin(mosi),
                  miso=Pin(miso), cs=Pin(cs), freq=1000000)
    # Keep the object alive. Dropping it frees the SPI bus.
    _sd_card = card
    try:
        os.mkdir(cfg.SD_MOUNT)
    except OSError:
        pass
    try:
        os.mount(card, cfg.SD_MOUNT)
    except OSError as err:
        errno = getattr(err, 'errno', None)
        # 16 is EBUSY: the socket is powered, but no card answered.
        if errno == 16:
            _release_card()
            raise ValueError('SD not ready')
        # 19 is ENODEV. FatFs maps FR_NO_FILESYSTEM to that. The FPGA image
        # is a real FAT32 volume with only a few thousand clusters, so FatFs
        # calls it FAT16 and then rejects it because the root-entry count is 0.
        if errno == 19:
            try:
                _vol = _FatVol(card)
            except OSError:
                _release_card()
                raise ValueError('SD not ready')
            return
        _release_card()
        raise


def _release_card():
    """Drop a card object that did not mount, so the next DIR can try again."""
    global _vol, _sd_card
    card = _sd_card
    _vol = None
    _sd_card = None
    if card is not None:
        try:
            card.deinit()
        except Exception:
            pass


def fat_name(name, write=False):
    """8.3 uppercase card name. Bare SAVE/OPEN-for-write becomes NAME.BAS."""
    name = name.strip().strip('"').upper()
    if not name or '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('invalid filename')
    if '.' in name:
        stem, ext = name.split('.', 1)
        if not stem or not ext or '.' in ext:
            raise ValueError('invalid filename')
        return stem[:8] + '.' + ext[:3]
    stem = name[:8]
    if write:
        return stem + '.BAS'
    return stem


def storage_path(name, write=False):
    """SD-root path. Reads try .BAS then .DAT .JMR .TXT when there is no dot."""
    fat = fat_name(name, write=write)
    root = cfg.SD_MOUNT
    if write or '.' in fat:
        return root + '/' + fat
    for suffix in _LOAD_SUFFIXES:
        candidate = root + '/' + fat + suffix
        try:
            os.stat(candidate)
            return candidate
        except OSError:
            continue
    return root + '/' + fat + '.BAS'


def list_sd():
    ensure_sd()
    if _vol is not None:
        return _vol.names()
    return sorted(item for item in os.listdir(cfg.SD_MOUNT) if item not in ('.', '..'))


def remove_sd(name):
    ensure_sd()
    if _vol is not None:
        if not _vol.remove(_card_name(name, write=False)):
            raise ValueError('file not found')
        return
    path = storage_path(name, write=False)
    try:
        os.remove(path)
    except OSError:
        raise ValueError('file not found')


def open_storage(name, write=False):
    """File object for LOAD/SAVE/OPEN. FPGA cards bypass os.mount."""
    ensure_sd()
    if _vol is None:
        return open(storage_path(name, write=write), 'w' if write else 'r')
    return _CardFile(_vol, _card_name(name, write=write), write)


def _card_name(name, write=False):
    """8.3 name on the manual volume. Reads try .BAS then .DAT .JMR .TXT."""
    fat = fat_name(name, write=write)
    if write or '.' in fat:
        return fat
    for suffix in _LOAD_SUFFIXES:
        candidate = fat + suffix
        if _vol.find(candidate) is not None:
            return candidate
    return fat + '.BAS'


class _CardFile:
    """Whole-file buffer. BASIC sources are small. Writes land on close or flush."""

    def __init__(self, vol, name, write):
        self.vol = vol
        self.name = name
        self.writing = write
        self.closed = False
        self.pos = 0
        if write:
            self.data = bytearray()
        else:
            self.data = vol.read(name)

    def write(self, text):
        if not self.writing:
            raise OSError(1)
        if isinstance(text, str):
            text = text.encode()
        self.data.extend(text)

    def flush(self):
        if self.writing and not self.closed:
            self.vol.write(self.name, self.data)

    def close(self):
        if not self.closed:
            self.flush()
            self.closed = True

    def readline(self):
        if self.pos >= len(self.data):
            return ''
        end = self.data.find(b'\n', self.pos)
        if end < 0:
            chunk = self.data[self.pos:]
            self.pos = len(self.data)
        else:
            chunk = self.data[self.pos:end + 1]
            self.pos = end + 1
        return bytes(chunk).decode()

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if line == '':
            raise StopIteration
        return line

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


class _FatVol:
    """Root-directory FAT32, same layout as the FPGA card image.

    FatFs will not mount it: too few clusters for its FAT32 rules.
    """

    def __init__(self, sd):
        self.sd = sd
        mbr = self._read(0)
        if mbr[510:512] != b'\x55\xaa':
            raise OSError(19)
        kind = mbr[450]
        part = mbr[454] | (mbr[455] << 8) | (mbr[456] << 16) | (mbr[457] << 24)
        if kind not in (0x0B, 0x0C, 0x0E) or part == 0:
            part = 0
        vbr = self._read(part)
        if vbr[510:512] != b'\x55\xaa' or vbr[82:87] != b'FAT32':
            raise OSError(19)
        self.part = part
        self.spc = vbr[13]
        reserved = vbr[14] | (vbr[15] << 8)
        self.fats = vbr[16]
        self.spf = vbr[36] | (vbr[37] << 8) | (vbr[38] << 16) | (vbr[39] << 24)
        self.root = vbr[44] | (vbr[45] << 8) | (vbr[46] << 16) | (vbr[47] << 24)
        self.fsinfo = vbr[48] | (vbr[49] << 8)
        if self.spc == 0 or self.spf == 0 or self.root < 2:
            raise OSError(19)
        self.fat_start = part + reserved
        self.data_start = self.fat_start + self.fats * self.spf

    def _read(self, lba):
        buf = bytearray(512)
        self.sd.readblocks(lba, buf)
        return buf

    def _write(self, lba, buf):
        self.sd.writeblocks(lba, buf)

    def _cluster_lba(self, cluster):
        return self.data_start + (cluster - 2) * self.spc

    def _fat_get(self, cluster):
        offset = cluster * 4
        buf = self._read(self.fat_start + offset // 512)
        off = offset % 512
        val = buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16) | (buf[off + 3] << 24)
        return val & 0x0FFFFFFF

    def _fat_set(self, cluster, value):
        value &= 0x0FFFFFFF
        offset = cluster * 4
        off = offset % 512
        for fat_i in range(self.fats):
            lba = self.fat_start + fat_i * self.spf + offset // 512
            buf = self._read(lba)
            old = buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16) | (buf[off + 3] << 24)
            new = (old & 0xF0000000) | value
            buf[off] = new & 0xFF
            buf[off + 1] = (new >> 8) & 0xFF
            buf[off + 2] = (new >> 16) & 0xFF
            buf[off + 3] = (new >> 24) & 0xFF
            self._write(lba, buf)

    def _chain(self, start):
        out = []
        cluster = start
        while 2 <= cluster < 0x0FFFFFF7 and len(out) < 256:
            if cluster in out:
                break
            out.append(cluster)
            cluster = self._fat_get(cluster)
        return out

    def _entries(self):
        """Yield (lba, offset, 32-byte entry) for the root directory."""
        for cluster in self._chain(self.root):
            base = self._cluster_lba(cluster)
            for sector in range(self.spc):
                lba = base + sector
                buf = self._read(lba)
                for offset in range(0, 512, 32):
                    yield lba, offset, buf[offset:offset + 32]

    def _pack(self, name):
        if '.' in name:
            stem, ext = name.split('.', 1)
        else:
            stem, ext = name, ''
        # Space-pad by hand. MicroPython str has no ljust.
        stem = stem[:8] + ' ' * (8 - len(stem[:8]))
        ext = ext[:3] + ' ' * (3 - len(ext[:3]))
        raw = (stem + ext).encode()
        return raw

    def _unpack(self, raw):
        stem = bytes(raw[0:8]).decode().rstrip()
        ext = bytes(raw[8:11]).decode().rstrip()
        return stem + '.' + ext if ext else stem

    def find(self, name):
        target = self._pack(name)
        for lba, offset, ent in self._entries():
            if ent[0] == 0x00:
                return None
            if ent[0] == 0xE5 or ent[11] == 0x0F or ent[11] & 0x08:
                continue
            if ent[0:11] == target:
                return lba, offset, ent
        return None

    def names(self):
        found = []
        for _lba, _offset, ent in self._entries():
            if ent[0] == 0x00:
                break
            if ent[0] == 0xE5 or ent[11] == 0x0F or ent[11] & 0x18:
                continue
            found.append(self._unpack(ent))
        return sorted(found)

    def _cluster_of(self, ent):
        return ent[26] | (ent[27] << 8) | (ent[20] << 16) | (ent[21] << 24)

    def _size_of(self, ent):
        return ent[28] | (ent[29] << 8) | (ent[30] << 16) | (ent[31] << 24)

    def read(self, name):
        found = self.find(name)
        if found is None:
            raise OSError(2)
        _lba, _offset, ent = found
        size = self._size_of(ent)
        start = self._cluster_of(ent)
        if size == 0 or start < 2:
            return bytearray()
        out = bytearray()
        for cluster in self._chain(start):
            lba = self._cluster_lba(cluster)
            for sector in range(self.spc):
                out.extend(self._read(lba + sector))
                if len(out) >= size:
                    return out[:size]
        return out[:size]

    def _alloc(self):
        limit = (self.spf * 512) // 4
        for cluster in range(2, limit):
            if self._fat_get(cluster) == 0:
                self._fat_set(cluster, 0x0FFFFFFF)
                blank = bytearray(512)
                lba = self._cluster_lba(cluster)
                for sector in range(self.spc):
                    self._write(lba + sector, blank)
                return cluster
        raise OSError(28)

    def _free(self, cluster):
        while 2 <= cluster < 0x0FFFFFF7:
            nxt = self._fat_get(cluster)
            self._fat_set(cluster, 0)
            if nxt < 2 or nxt >= 0x0FFFFFF8:
                break
            cluster = nxt

    def _put_entry(self, lba, offset, name, first, size):
        buf = self._read(lba)
        ent = bytearray(32)
        ent[0:11] = self._pack(name)
        ent[11] = 0x20
        ent[20] = (first >> 16) & 0xFF
        ent[21] = (first >> 24) & 0xFF
        ent[26] = first & 0xFF
        ent[27] = (first >> 8) & 0xFF
        ent[28] = size & 0xFF
        ent[29] = (size >> 8) & 0xFF
        ent[30] = (size >> 16) & 0xFF
        ent[31] = (size >> 24) & 0xFF
        buf[offset:offset + 32] = ent
        self._write(lba, buf)

    def _free_slot(self):
        last = None
        for lba, offset, ent in self._entries():
            last = (lba, offset)
            if ent[0] == 0x00 or ent[0] == 0xE5:
                return lba, offset
        if last is None:
            raise OSError(28)
        chain = self._chain(self.root)
        new_c = self._alloc()
        self._fat_set(chain[-1], new_c)
        self._fat_set(new_c, 0x0FFFFFFF)
        return self._cluster_lba(new_c), 0

    def write(self, name, data):
        if isinstance(data, str):
            data = data.encode()
        found = self.find(name)
        if found is not None:
            lba, offset, ent = found
            old = self._cluster_of(ent)
            if old >= 2:
                self._free(old)
        else:
            lba, offset = self._free_slot()
        if not data:
            self._put_entry(lba, offset, name, 0, 0)
            return
        per = self.spc * 512
        first = None
        prev = None
        pos = 0
        while pos < len(data):
            cluster = self._alloc()
            if first is None:
                first = cluster
            if prev is not None:
                self._fat_set(prev, cluster)
            self._fat_set(cluster, 0x0FFFFFFF)
            chunk = data[pos:pos + per]
            base = self._cluster_lba(cluster)
            for sector in range(self.spc):
                part = chunk[sector * 512:(sector + 1) * 512]
                buf = bytearray(512)
                buf[:len(part)] = part
                self._write(base + sector, buf)
            pos += per
            prev = cluster
        self._put_entry(lba, offset, name, first, len(data))

    def remove(self, name):
        found = self.find(name)
        if found is None:
            return False
        lba, offset, ent = found
        first = self._cluster_of(ent)
        buf = self._read(lba)
        buf[offset] = 0xE5
        self._write(lba, buf)
        if first >= 2:
            self._free(first)
        return True


# PS/2 set 2. The keyboard clocks one short frame per make or break.
# A Python pin interrupt on the ESP32 drops those edges, so the clock is
# watched in a tight loop only while BASIC is waiting for a key.
# ESP32-S3 GPIO_IN is 0x6000403C (pins 0-31). Clock and data must stay in that range.
_PS2_MAP = {
    0x1C: 'A', 0x32: 'B', 0x21: 'C', 0x23: 'D', 0x24: 'E', 0x2B: 'F', 0x34: 'G',
    0x33: 'H', 0x43: 'I', 0x3B: 'J', 0x42: 'K', 0x4B: 'L', 0x3A: 'M', 0x31: 'N',
    0x44: 'O', 0x4D: 'P', 0x15: 'Q', 0x2D: 'R', 0x1B: 'S', 0x2C: 'T', 0x3C: 'U',
    0x2A: 'V', 0x1D: 'W', 0x22: 'X', 0x35: 'Y', 0x1A: 'Z',
    0x45: '0', 0x16: '1', 0x1E: '2', 0x26: '3', 0x25: '4', 0x2E: '5', 0x36: '6',
    0x3D: '7', 0x3E: '8', 0x46: '9',
    0x0E: '`', 0x4E: '-', 0x55: '=', 0x5D: '\\', 0x54: '[', 0x5B: ']',
    0x4C: ';', 0x52: "'", 0x41: ',', 0x49: '.', 0x4A: '/', 0x29: ' ',
    0x5A: '\n', 0x66: '\x08', 0x76: '\x1b',
    0x70: '0', 0x69: '1', 0x72: '2', 0x7A: '3', 0x6B: '4', 0x73: '5',
    0x74: '6', 0x6C: '7', 0x75: '8', 0x7D: '9', 0x71: '.', 0x79: '+', 0x7B: '-', 0x7C: '*',
}
_PS2_SHIFT = {
    0x16: '!', 0x1E: '@', 0x26: '#', 0x25: '$', 0x2E: '%', 0x36: '^', 0x3D: '&',
    0x3E: '*', 0x46: '(', 0x45: ')', 0x0E: '~', 0x4E: '_', 0x55: '+', 0x5D: '|',
    0x54: '{', 0x5B: '}', 0x4C: ':', 0x52: '"', 0x41: '<', 0x49: '>', 0x4A: '?',
}
_ps2_on = False
_ps2_frame = None
_ps2_spin = None
_ps2_shift = False
_ps2_ctrl = False
_ps2_ext = False
_ps2_brk = False
_clk_bit = 0
_dat_bit = 0
_ps2_clk = None
_ps2_held = False
_Pin = None
_ps2_burst = None
_ps2_raw = bytearray(16)
_edge_spins = 1000
_spins_per_us = 1
_irq_disable = None
_irq_restore = None

try:
    import micropython

    @micropython.viper
    def _ps2_spin(n: int) -> int:
        # Same kind of loop as a frame read, so the timeout matches real edges.
        gpio = ptr32(0x6000403C)
        acc = 0
        i = n
        while i > 0:
            acc += gpio[0]
            i -= 1
        return acc

    @micropython.viper
    def _ps2_frame(clk_bit: int, dat_bit: int, edge_spins: int, wait_spins: int) -> int:
        # Start bit, 8 data bits LSB first, odd parity, stop. -1 if the clock stays idle.
        gpio = ptr32(0x6000403C)
        clk_mask = 1 << clk_bit
        dat_mask = 1 << dat_bit
        spins = wait_spins
        seen_high = 0
        while spins > 0:
            spins -= 1
            level = gpio[0]
            if (level & clk_mask) != 0:
                seen_high = 1
                continue
            if seen_high == 0:
                continue
            if (level & dat_mask) != 0:
                # Clock fell, but this is not a start bit.
                seen_high = 0
                continue
            bits = 0
            mask = 1
            bit_i = 0
            while bit_i < 8:
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) == 0:
                    hold -= 1
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) != 0:
                    hold -= 1
                if (gpio[0] & clk_mask) != 0:
                    return -1
                if (gpio[0] & dat_mask) != 0:
                    bits = bits | mask
                mask = mask << 1
                bit_i += 1
            # Parity, then stop.
            hold = edge_spins
            while hold > 0 and (gpio[0] & clk_mask) == 0:
                hold -= 1
            hold = edge_spins
            while hold > 0 and (gpio[0] & clk_mask) != 0:
                hold -= 1
            if (gpio[0] & clk_mask) != 0:
                return -1
            parity = 0
            if (gpio[0] & dat_mask) != 0:
                parity = 1
            hold = edge_spins
            while hold > 0 and (gpio[0] & clk_mask) == 0:
                hold -= 1
            hold = edge_spins
            while hold > 0 and (gpio[0] & clk_mask) != 0:
                hold -= 1
            if (gpio[0] & clk_mask) != 0:
                return -1
            if (gpio[0] & dat_mask) == 0:
                return -1
            ones = parity
            scan = bits
            while scan != 0:
                ones += scan & 1
                scan = scan >> 1
            if (ones & 1) == 0:
                return -1
            return bits
        return -1
except Exception:
    _ps2_frame = None
    _ps2_spin = None

try:
    @micropython.viper
    def _ps2_burst(clk_bit: int, dat_bit: int, edge_spins: int, first_spins: int, gap_spins: int, raw) -> int:
        # One IRQ-off stretch. A queued burst is make, break, make with almost no gap.
        # The byte loop stays here. A call out would hand back an object and drop the rest.
        buf = ptr8(raw)
        gpio = ptr32(0x6000403C)
        clk_mask = 1 << clk_bit
        dat_mask = 1 << dat_bit
        n = 0
        wait = first_spins
        while n < 16:
            spins = wait
            seen_high = 0
            got = 0
            while spins > 0:
                spins -= 1
                level = gpio[0]
                if (level & clk_mask) != 0:
                    seen_high = 1
                    continue
                if seen_high == 0:
                    continue
                if (level & dat_mask) != 0:
                    seen_high = 0
                    continue
                bits = 0
                mask = 1
                bit_i = 0
                ok = 1
                while bit_i < 8:
                    hold = edge_spins
                    while hold > 0 and (gpio[0] & clk_mask) == 0:
                        hold -= 1
                    hold = edge_spins
                    while hold > 0 and (gpio[0] & clk_mask) != 0:
                        hold -= 1
                    if (gpio[0] & clk_mask) != 0:
                        ok = 0
                        break
                    if (gpio[0] & dat_mask) != 0:
                        bits = bits | mask
                    mask = mask << 1
                    bit_i += 1
                if ok == 0:
                    return n
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) == 0:
                    hold -= 1
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) != 0:
                    hold -= 1
                if (gpio[0] & clk_mask) != 0:
                    return n
                parity = 0
                if (gpio[0] & dat_mask) != 0:
                    parity = 1
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) == 0:
                    hold -= 1
                hold = edge_spins
                while hold > 0 and (gpio[0] & clk_mask) != 0:
                    hold -= 1
                if (gpio[0] & clk_mask) != 0:
                    return n
                if (gpio[0] & dat_mask) == 0:
                    return n
                ones = parity
                scan = bits
                while scan != 0:
                    ones += scan & 1
                    scan = scan >> 1
                if (ones & 1) == 0:
                    return n
                buf[n] = bits
                n += 1
                got = 1
                break
            if got == 0:
                return n
            wait = gap_spins
        return n
except Exception:
    _ps2_burst = None


def _ps2_decode(code):
    """One set-2 scan byte becomes a character, or '' for a shift or a break."""
    global _ps2_shift, _ps2_ctrl, _ps2_ext, _ps2_brk
    if code == 0xE0:
        _ps2_ext = True
        return ''
    if code == 0xF0:
        _ps2_brk = True
        return ''
    ext = _ps2_ext
    brk = _ps2_brk
    _ps2_ext = False
    _ps2_brk = False
    # Left and right shift, and either Ctrl. A release must not type a character.
    if code == 0x12 or code == 0x59:
        _ps2_shift = not brk
        return ''
    if code == 0x14:
        _ps2_ctrl = not brk
        return ''
    if brk:
        return ''
    if ext:
        # Arrows match the window: 17 left, 18 right, 19 up, 20 down.
        if code == 0x5A:
            return '\n'
        if code == 0x6B:
            return '\x11'
        if code == 0x74:
            return '\x12'
        if code == 0x75:
            return '\x13'
        if code == 0x72:
            return '\x14'
        return ''
    if _ps2_shift and code in _PS2_SHIFT:
        ch = _PS2_SHIFT[code]
    else:
        ch = _PS2_MAP.get(code, '')
    if _ps2_ctrl and len(ch) == 1 and 'A' <= ch <= 'Z':
        return chr(ord(ch) - 64)
    return ch


def ps2_start():
    """Arm IO15/IO16. Safe to call when the keyboard is not plugged in."""
    global _ps2_on, _clk_bit, _dat_bit, _edge_spins, _spins_per_us
    global _irq_disable, _irq_restore, _ps2_clk, _ps2_held, _Pin
    if _ps2_on or _ps2_frame is None:
        return
    clk_pin = getattr(cfg, 'PS2_CLOCK_PIN', None)
    dat_pin = getattr(cfg, 'PS2_DATA_PIN', None)
    if clk_pin is None or dat_pin is None:
        return
    if clk_pin > 31 or dat_pin > 31:
        return
    try:
        from machine import Pin
        import machine
    except ImportError:
        return
    _Pin = Pin
    _ps2_clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
    _ps2_held = False
    Pin(dat_pin, Pin.IN, Pin.PULL_UP)
    _clk_bit = clk_pin
    _dat_bit = dat_pin
    _irq_disable = machine.disable_irq
    _irq_restore = machine.enable_irq
    state = _irq_disable()
    try:
        t0 = time.ticks_us()
        _ps2_spin(20000)
        dt = time.ticks_diff(time.ticks_us(), t0)
    finally:
        _irq_restore(state)
    if dt < 1:
        dt = 1
    _spins_per_us = 20000 // dt
    if _spins_per_us < 1:
        _spins_per_us = 1
    # A wild count would keep interrupts off long enough for the watchdog to reset the chip.
    if _spins_per_us > 40:
        _spins_per_us = 40
    # One edge is about 50 us. 400 us still finishes the frame if the count is a bit short.
    _edge_spins = _spins_per_us * 400
    _ps2_on = True
    # The clock is held low at all times except inside ps2_keys(). Held low,
    # the keyboard stores keys and resends any byte that was cut off, so keys
    # typed while BASIC is busy or the e-ink is painting are not lost.
    _ps2_inhibit()


def _ps2_inhibit():
    global _ps2_held
    _ps2_clk.init(_Pin.OUT)
    _ps2_clk.value(0)
    _ps2_held = True


def ps2_keys(wait_us=3000):
    """Release the clock, read what the keyboard sends, then hold it low again."""
    if not _ps2_on or _ps2_burst is None:
        return []
    if wait_us > 5000:
        wait_us = 5000
    # 2 ms of quiet after a byte ends the burst. Queued bytes follow each other faster.
    gap = _spins_per_us * 2000
    state = _irq_disable()
    try:
        # The keyboard needs the clock low at least 100 us to see it as held.
        # A back-to-back call could release it sooner and garble a byte.
        time.sleep_us(120)
        _ps2_clk.init(_Pin.IN, _Pin.PULL_UP)
        n = _ps2_burst(_clk_bit, _dat_bit, _edge_spins, wait_us * _spins_per_us, gap, _ps2_raw)
        _ps2_clk.init(_Pin.OUT)
        _ps2_clk.value(0)
    finally:
        _irq_restore(state)
    if n > 16:
        n = 16
    found = []
    i = 0
    while i < n:
        ch = _ps2_decode(_ps2_raw[i])
        if ch:
            found.append(ch)
        i += 1
    return found
