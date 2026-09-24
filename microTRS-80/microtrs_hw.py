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
        try:
            os.listdir(cfg.SD_MOUNT)
            return
        except OSError:
            pass
        if cfg.SD_SPI_PINS is None:
            return
        from machine import Pin, SDCard
        sck, mosi, miso, cs = cfg.SD_SPI_PINS
        card = SDCard(slot=2, sck=Pin(sck), mosi=Pin(mosi),
                      miso=Pin(miso), cs=Pin(cs))
        try:
            os.mkdir(cfg.SD_MOUNT)
        except OSError:
            pass
        os.mount(card, cfg.SD_MOUNT)

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
        d.fill(bg)
        for y in range(48):
            for x in range(128):
                bit = y * 128 + x
                if machine.pixels[bit // 8] & (1 << (bit % 8)):
                    px = left + x * scale_x // 2
                    py = top + y * scale_y // 3
                    color = cfg.PALETTE[machine.pixel_colors.get(bit, machine.color_fg)]
                    d.fill_rect(px, py, max(1, scale_x // 2), max(1, scale_y // 3), color)
        for row in range(16):
            for col in range(64):
                character = machine.screen[row][col]
                glyph = FONT.get(character)
                if glyph:
                    px, py = left + col * scale_x, top + row * scale_y
                    ink = cfg.PALETTE[machine.text_colors[row * 64 + col]]
                    for gx, bits in enumerate(glyph):
                        for gy in range(8):
                            if bits & (1 << gy):
                                d.fill_rect(px + gx, py + gy, 1, 1, ink)
        if hasattr(d, 'show'):
            d.show()


def storage_path(name):
    """Restrict BASIC filenames to the SD root, no traversal or subfolders."""
    name = name.strip().strip('"')
    if not name or len(name) > 64 or '/' in name or '\\' in name or '..' in name:
        raise ValueError('invalid filename')
    return cfg.SD_MOUNT + '/' + name
