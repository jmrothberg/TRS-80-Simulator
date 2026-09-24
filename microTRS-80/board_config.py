"""Edit these values for your board. None disables the optional device."""

# SPI SD card: (sck_gpio, mosi_gpio, miso_gpio, cs_gpio).
# If your board already mounts an SD card at /sd, leave this as None.
SD_SPI_PINS = None
SD_MOUNT = '/sd'

# Piezo speaker GPIO, preferably connected through the board's audio circuit.
SPEAKER_PIN = None

# Supply display_driver.py with create_display() for your specific LCD.
# The display must implement fill(color), fill_rect(x,y,w,h,color),
# and optionally show(). WIDTH and HEIGHT must be set below to match.
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

# RGB565 16-color palette (FPGA color indices 0..15).
PALETTE = (0x0000, 0x0015, 0x0540, 0x0555,
           0xA800, 0xA815, 0xAAA0, 0xAD55,
           0x52AA, 0x52BF, 0x57EA, 0x57FF,
           0xFAAA, 0xFABF, 0xFFE0, 0xFFFF)
