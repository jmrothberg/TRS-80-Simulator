"""Storage Engine.

Constitution, STORAGE:

    Phase 1   Host files -> UART -> Program RAM
    Phase 2   microSD -> Storage Engine -> Program RAM
    The BASIC CPU does not know which storage device is used.

So the engine is split in two: a device backend that moves bytes, and the
engine itself, which is all the BASIC side ever talks to.  Phase 2 adds a
`SdCardBackend` next to `HostFileBackend` and nothing above this line changes.

The engine transfers *raw images*.  It has no idea whether the bytes are a
tokenized program or text -- deciding that is the LOAD microcode's job, not the
storage device's.
"""

from __future__ import annotations

from pathlib import Path

from .. import memory_map as mm
from ..errors import BasicError, FILE_NOT_FOUND
from ..memory import Memory

#: Marks a saved image as a tokenized program rather than source text.
IMAGE_MAGIC = b"JMRB1"
DEFAULT_SUFFIX = ".jmr"


class StorageBackend:
    """The device interface.  Phase 1 is host files; phase 2 is a microSD card."""

    def exists(self, name: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self, name: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError

    def write(self, name: str, data: bytes) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def catalog(self) -> list[str]:  # pragma: no cover - interface
        raise NotImplementedError


class HostFileBackend(StorageBackend):
    """Phase 1: files on the development host, reached over the UART."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = Path(name).name  # a file name, never a path
        if not safe:
            raise BasicError(FILE_NOT_FOUND, "empty file name")
        if "." not in safe:
            safe += DEFAULT_SUFFIX
        return self.root / safe

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def read(self, name: str) -> bytes:
        path = self._path(name)
        if not path.is_file():
            raise BasicError(FILE_NOT_FOUND, name)
        return path.read_bytes()

    def write(self, name: str, data: bytes) -> None:
        self._path(name).write_bytes(data)

    def catalog(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_file())


class MemoryBackend(StorageBackend):
    """An in-memory device, used by the regression tests."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def exists(self, name: str) -> bool:
        return name.upper() in self.files

    def read(self, name: str) -> bytes:
        try:
            return self.files[name.upper()]
        except KeyError:
            raise BasicError(FILE_NOT_FOUND, name) from None

    def write(self, name: str, data: bytes) -> None:
        self.files[name.upper()] = data

    def catalog(self) -> list[str]:
        return sorted(self.files)


class StorageEngine:
    """BASIC-facing storage.  Moves images between a device and Program RAM."""

    def __init__(self, memory: Memory, backend: StorageBackend) -> None:
        self.memory = memory
        self.backend = backend

    def save_image(self, name: str, image: bytes) -> None:
        self._set_busy(True)
        try:
            self.backend.write(name, IMAGE_MAGIC + image)
        finally:
            self._set_busy(False)

    def load_image(self, name: str) -> bytes:
        """Return the file contents, magic header stripped when present."""
        self._set_busy(True)
        try:
            data = self.backend.read(name)
        finally:
            self._set_busy(False)
        # Records pass through the storage buffer on their way to Program RAM,
        # the way a sector will.
        window = data[: mm.STORAGE_BUFFER_SIZE]
        self.memory.write_block(mm.STORAGE_BUFFER, window.ljust(mm.STORAGE_BUFFER_SIZE, b"\0"))
        return data

    @staticmethod
    def is_program_image(data: bytes) -> bool:
        return data.startswith(IMAGE_MAGIC)

    @staticmethod
    def strip_magic(data: bytes) -> bytes:
        return data[len(IMAGE_MAGIC) :] if data.startswith(IMAGE_MAGIC) else data

    def catalog(self) -> list[str]:
        return self.backend.catalog()

    def _set_busy(self, busy: bool) -> None:
        self.memory.write(mm.IO_STORAGE_STATUS, 0x01 if busy else 0x00)
