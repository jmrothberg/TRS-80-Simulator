"""CrowPanel 5.79 e-ink for microtrs_hw.draw().

The panel is black and white. Palette color 0 is the paper (white).
Any other palette color is ink (black). show() uses the fast refresh.
"""

import CrowPanel


class EInk:
    def __init__(self):
        self.panel = CrowPanel.Screen_579()

    def _mono(self, color):
        if color == 0:
            return CrowPanel.COLOR_WHITE
        return CrowPanel.COLOR_BLACK

    def fill(self, color):
        self.panel.fill(self._mono(color))

    def fill_rect(self, x, y, w, h, color):
        self.panel.fill_rect(x, y, w, h, self._mono(color))

    def show(self):
        # mode 1 is the fast full-panel update.
        self.panel.show(1)


def create_display():
    return EInk()
