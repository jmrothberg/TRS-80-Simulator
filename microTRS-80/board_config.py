"""Edit these values for your board. None disables the optional device."""

# CrowPanel 5.79 microSD socket, SPI: CLK, MOSI, MISO, CS.
# GPIO 42 turns the socket power on. Same FAT32 cards as the FPGA.
SD_SPI_PINS = (39, 40, 13, 10)
SD_POWER_PIN = 42
SD_MOUNT = '/sd'

# Piezo speaker GPIO, preferably connected through the board's audio circuit.
SPEAKER_PIN = None

# PS/2 keyboard on the 2x10 header. C1 is clock, D1 is data.
# Power the breakout from the header 3.3 V pin. 5 V will damage the ESP32.
# D2 and C2 are the second port; leave them empty. None disables the keyboard.
PS2_CLOCK_PIN = 15
PS2_DATA_PIN = 16

# Supply display_driver.py with create_display() for your specific LCD.
# The display must implement fill(color), fill_rect(x,y,w,h,color),
# and optionally show(). WIDTH and HEIGHT must be set below to match.
# CrowPanel 5.79 e-ink. The 64x16 console is drawn in the center.
DISPLAY_WIDTH = 792
DISPLAY_HEIGHT = 272

# RGB565 16-color palette (FPGA color indices 0..15).
PALETTE = (0x0000, 0x0015, 0x0540, 0x0555,
           0xA800, 0xA815, 0xAAA0, 0xAD55,
           0x52AA, 0x52BF, 0x57EA, 0x57FF,
           0xFAAA, 0xFABF, 0xFFE0, 0xFFFF)
