"""A value read from files, read again when one of them changes.

The POI index, the address index and the model price list are rebuilt by the
scheduler in a container of its own, into a volume the backend reads. Nothing
tells the backend: there is no Docker socket on purpose (see the scheduler in
docker-compose.yml), so a signal is not available. Before this, a quarterly
rebuild therefore changed nothing until somebody restarted the backend -- up
to three months of answers from the old index, with nothing to say so.

Looking is cheap: one ``stat`` per file, at most once per ``check_every``
seconds. Reading is not -- the address index is tens of megabytes -- so it
happens only when a file's modification time or size actually moved.

Three rules keep a rebuild from ever making an answer worse:

* **While a reload runs, others keep the old value.** Only the first load,
  when there is nothing to hand out yet, makes a caller wait.
* **A reload that fails keeps the old value.** A half-written or broken file is
  logged and ignored until the file changes again. The builders write to a
  temporary file and rename it, so this should not happen; it must not hurt
  when it does.
* **A file that disappears is a change like any other**, so a deleted index
  reads as "not built here" -- the state ``/api/health`` already describes.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Generic, Iterable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

Signature = tuple[tuple[int, int] | None, ...]


def file_signature(paths: Iterable[Path | str | None]) -> Signature:
    """Modification time and size of each file; ``None`` for one that is absent."""

    out: list[tuple[int, int] | None] = []
    for path in paths:
        if path is None:
            out.append(None)
            continue
        try:
            stat = Path(path).stat()
        except OSError:
            out.append(None)
            continue
        out.append((stat.st_mtime_ns, stat.st_size))
    return tuple(out)


class FileBacked(Generic[T]):
    """``get()`` returns what ``load()`` made of the files, kept current."""

    def __init__(
        self,
        paths: Iterable[Path | str | None],
        load: Callable[[], T],
        *,
        check_every: float = 10.0,
        name: str = "file",
    ) -> None:
        self.paths = list(paths)
        self._load = load
        self.check_every = check_every
        self.name = name
        self._lock = threading.Lock()
        self._value: T | None = None
        self._loaded = False
        self._signature: Signature | None = None
        self._checked_at = float("-inf")
        self.error: str | None = None
        self.loaded_at: float | None = None

    def get(self) -> T:
        now = time.monotonic()
        if self._loaded and now - self._checked_at < self.check_every:
            return self._value  # type: ignore[return-value]

        signature = file_signature(self.paths)
        self._checked_at = now
        if self._loaded and signature == self._signature:
            return self._value  # type: ignore[return-value]

        # Somebody else is already reading the new files: hand out the old value
        # rather than queue behind a load of tens of megabytes.
        if self._loaded and not self._lock.acquire(blocking=False):
            return self._value  # type: ignore[return-value]
        if not self._loaded:
            self._lock.acquire()
        try:
            if self._loaded and file_signature(self.paths) == self._signature:
                return self._value  # type: ignore[return-value]
            self._reload(file_signature(self.paths))
        finally:
            self._lock.release()
        return self._value  # type: ignore[return-value]

    def _reload(self, signature: Signature) -> None:
        first = not self._loaded
        try:
            value = self._load()
        except (OSError, ValueError) as exc:
            # Remembered, so a broken file is not parsed again on every request;
            # the next change to it is the next attempt.
            self._signature = signature
            self.error = str(exc)
            if first:
                self._value = None
                self._loaded = True
            logger.warning("%s at %s unusable, keeping the previous one: %s", self.name, self.paths, exc)
            return
        self._value = value
        self._signature = signature
        self._loaded = True
        self.error = None
        self.loaded_at = time.time()
        if not first:
            logger.info("%s reloaded from %s", self.name, self.paths)
