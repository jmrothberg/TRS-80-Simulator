"""Graphics Engine.

Constitution, SHARED ENGINES:

    SET / RESET / POINT share one Graphics Engine.

All three commands are the same address decode with a different action on the
block bit, so the decode lives in exactly one place (the Video Engine's
`_decode_point`) and this engine is the BASIC-facing side of it.

Coordinates are 0..127 horizontally and 0..47 vertically.  Anything outside
that is ?FC ERROR, as on a Level II machine.
"""

from __future__ import annotations

from .. import memory_map as mm
from ..errors import BasicError, ILLEGAL_FUNCTION_CALL
from .video_engine import VideoEngine


class GraphicsEngine:
    def __init__(self, video: VideoEngine) -> None:
        self.video = video

    def set(self, x: int, y: int) -> None:
        self._check(x, y)
        self.video.set_point(x, y, True)

    def reset(self, x: int, y: int) -> None:
        self._check(x, y)
        self.video.set_point(x, y, False)

    def point(self, x: int, y: int) -> int:
        """POINT returns -1 (true) when the block is lit, 0 when it is not."""
        self._check(x, y)
        return -1 if self.video.get_point(x, y) else 0

    @staticmethod
    def _check(x: int, y: int) -> None:
        if not (0 <= x < mm.GRAPHICS_WIDTH and 0 <= y < mm.GRAPHICS_HEIGHT):
            raise BasicError(ILLEGAL_FUNCTION_CALL, f"({x},{y}) is off screen")
