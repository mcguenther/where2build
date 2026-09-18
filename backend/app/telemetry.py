"""What this deployment did, counted in memory and written out in batches.

Nothing was counted before this. The request budget in ``app/ratelimit.py``
keeps a sliding log per client and forgets it, so an operator could not say how
many calls had gone to the cadastre yesterday, how many listings had been read,
or what the model had cost -- and neither could anybody looking at a bill.

Three shapes of the same act of counting live here, and they are separate
because they answer different questions:

* **Aggregates per hour, with nobody in them** (``count``): an hour, an area, a
  service, an outcome. This is the statistics page. A row per request would
  hold the same numbers at a thousand times the size while also recording when
  each single call happened, which nobody needs and everybody would then have
  to protect.
* **Aggregates per hour and account** (``spend``): the same, keyed by the
  account key. This is the half that answers "who", which is the question an
  operator has when something is wrong.
* **The single failure** (``error``): the one place where the individual case
  is the point, kept as a ring in this process as well, so a deployment without
  a database can still say what went wrong.

**The burst guard is why this is not simply a table.** An hourly counter cannot
stop anything -- by the time the hour is visible, the hour has happened. So
``spend`` also keeps a short sliding window per account, and an account that
crosses it is blocked here, immediately, in the process that saw it. The
database is the durable and shared copy: the flush writes local blocks out and
reads every block back, so a second worker follows within one flush interval.

Everything in this module is per process and lost on restart, by design -- the
flush is what makes it durable, and losing at most one flush interval of
counters on a crash is not worth a write per request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

logger = logging.getLogger(__name__)

# The three areas a count can belong to. Code, not wire format -- the interface
# translates them -- but they are stored, so they never change without a
# migration.
AREA_REQUEST = "anfrage"
AREA_SERVICE = "dienst"
AREA_MODEL = "modell"
# How a parcel search ended -- „bestaetigt", „mehrdeutig", „erfolglos" or
# „abgebrochen" in place of the service name. The one area here that is about
# the product rather than the machine: nothing failed when a search comes back
# empty, and no error log would ever show it.
AREA_SEARCH = "suche"

# And the three outcomes. "limit" is its own rather than an error: a refused
# call is the budget working, and counting it as a failure would make a healthy
# deployment look broken.
RESULT_OK = "ok"
RESULT_ERROR = "fehler"
RESULT_LIMIT = "limit"


def hour_of(moment: datetime) -> datetime:
    """The UTC hour a moment falls in. The bucket key, everywhere."""

    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


@dataclass
class Counter:
    """One bucket's numbers. Summed, never averaged -- see the migration."""

    anzahl: int = 0
    dauer_ms: int = 0
    tokens_ein: int = 0
    tokens_aus: int = 0

    def add(self, *, anzahl: int = 1, dauer_ms: int = 0, tokens_ein: int = 0, tokens_aus: int = 0) -> None:
        self.anzahl += anzahl
        self.dauer_ms += dauer_ms
        self.tokens_ein += tokens_ein
        self.tokens_aus += tokens_aus


@dataclass
class AccountCounter:
    anzahl: int = 0
    fehler: int = 0
    tokens_ein: int = 0
    tokens_aus: int = 0


@dataclass(frozen=True)
class ErrorEntry:
    """One failure, in the words the caller was given."""

    zeit: datetime
    bereich: str
    dienst: str | None
    status: int | None
    route: str | None
    kennung: str | None
    meldung: str

    def as_row(self) -> dict[str, object]:
        """The shape the API and the download both use."""

        return {
            "zeit": self.zeit.isoformat(),
            "bereich": self.bereich,
            "dienst": self.dienst,
            "status": self.status,
            "route": self.route,
            "kennung": self.kennung,
            "meldung": self.meldung,
        }


@dataclass(frozen=True)
class Block:
    """An account that is not let through, and until when."""

    kennung: str
    bis: datetime
    grund: str
    automatisch: bool
    durch: str | None = None


@dataclass
class Snapshot:
    """What one flush carries out of the process."""

    usage: dict[tuple[datetime, str, str, str], Counter] = field(default_factory=dict)
    accounts: dict[tuple[datetime, str], AccountCounter] = field(default_factory=dict)
    errors: list[ErrorEntry] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.usage or self.accounts or self.errors or self.blocks)


class Recorder:
    """The process-wide tally. Every method is safe to call from any thread.

    A lock rather than an atomic-free design: the counting happens inside the
    event loop for the most part, but ``upstream`` runs in worker threads for
    nothing and the tile proxy does its scaling in one, so "mostly single
    threaded" is the kind of assumption that holds until it does not.
    """

    def __init__(
        self,
        *,
        burst_calls: int = 300,
        burst_window_s: int = 300,
        auto_block_minutes: int = 60,
        error_buffer: int = 500,
        max_accounts: int = 20000,
        now=lambda: datetime.now(timezone.utc),
        clock=time.monotonic,
    ) -> None:
        self.burst_calls = max(1, burst_calls)
        self.burst_window_s = max(1, burst_window_s)
        self.auto_block_minutes = max(1, auto_block_minutes)
        self.max_accounts = max(1, max_accounts)
        self.now = now
        self.clock = clock
        self._lock = threading.Lock()
        self._usage: dict[tuple[datetime, str, str, str], Counter] = {}
        self._accounts: dict[tuple[datetime, str], AccountCounter] = {}
        # Written out and kept: the ring is what the interface shows where
        # there is no database, the pending list is what the flush drains.
        self._errors: deque[ErrorEntry] = deque(maxlen=max(1, error_buffer))
        self._pending_errors: list[ErrorEntry] = []
        # The short window per account, bounded the same way the request budget
        # is: the least recently seen account is dropped first.
        self._recent: OrderedDict[str, deque[float]] = OrderedDict()
        self._blocks: dict[str, Block] = {}
        self._new_blocks: list[Block] = []

    # -- counting ----------------------------------------------------------

    def count(
        self,
        bereich: str,
        dienst: str,
        ergebnis: str = RESULT_OK,
        *,
        duration_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        key = (hour_of(self.now()), bereich, dienst[:120], ergebnis)
        with self._lock:
            self._usage.setdefault(key, Counter()).add(
                dauer_ms=max(0, int(duration_ms)),
                tokens_ein=max(0, int(tokens_in)),
                tokens_aus=max(0, int(tokens_out)),
            )

    def spend(
        self,
        kennung: str | None,
        *,
        failed: bool = False,
        tokens_in: int = 0,
        tokens_out: int = 0,
        burst: bool = True,
    ) -> Block | None:
        """Count one call against an account -- and say when it went too fast.

        Returns the block that was just placed, or ``None``. The caller does
        not have to act on it: the block is already in force here, and the
        answer exists so the request that crossed the line can be refused
        rather than served and then blocked.

        A signed-out caller has no account key and is not counted here at all.
        They are counted in the aggregate like everybody else, and what limits
        them is the peer-address budget in ``app/ratelimit.py``.

        ``burst`` is false for map tiles. One screen of a map is dozens of
        them, a pan is dozens more, and a window sized for calls to the
        cadastre would fire on somebody simply looking at the map. Tiles are
        still counted in the account's total, and what bounds them is their own
        far wider ceiling in ``app/ratelimit.py``.
        """

        if not kennung:
            return None
        bucket = (hour_of(self.now()), kennung)
        with self._lock:
            entry = self._accounts.setdefault(bucket, AccountCounter())
            entry.anzahl += 1
            entry.fehler += 1 if failed else 0
            entry.tokens_ein += max(0, int(tokens_in))
            entry.tokens_aus += max(0, int(tokens_out))
            return self._note_burst(kennung) if burst else None

    def _note_burst(self, kennung: str) -> Block | None:
        """The short window. Called with the lock held."""

        now = self.clock()
        calls = self._recent.get(kennung)
        if calls is None:
            calls = deque()
            self._recent[kennung] = calls
        self._recent.move_to_end(kennung)
        horizon = now - self.burst_window_s
        while calls and calls[0] <= horizon:
            calls.popleft()
        calls.append(now)
        while len(self._recent) > self.max_accounts:
            self._recent.popitem(last=False)
        if len(calls) < self.burst_calls:
            return None
        existing = self._blocks.get(kennung)
        if existing is not None and existing.bis > self.now():
            return None
        block = Block(
            kennung=kennung,
            bis=self.now() + timedelta(minutes=self.auto_block_minutes),
            grund=(
                f"Automatisch gesperrt: mehr als {self.burst_calls} Anfragen in "
                f"{self.burst_window_s // 60 or 1} Minuten."
            ),
            automatisch=True,
        )
        self._blocks[kennung] = block
        self._new_blocks.append(block)
        logger.warning("Account %s blocked automatically until %s", kennung, block.bis)
        return block

    def error(
        self,
        bereich: str,
        meldung: str,
        *,
        dienst: str | None = None,
        status: int | None = None,
        route: str | None = None,
        kennung: str | None = None,
    ) -> None:
        entry = ErrorEntry(
            zeit=self.now(),
            bereich=bereich,
            dienst=dienst,
            status=status,
            route=route,
            kennung=kennung,
            # Bounded here rather than in the column: a message this long is a
            # stack trace somebody pasted, and the row is for reading.
            meldung=(meldung or "")[:2000],
        )
        with self._lock:
            self._errors.append(entry)
            self._pending_errors.append(entry)

    def recent_errors(self, limit: int = 100) -> list[ErrorEntry]:
        """The last failures this process saw, newest first."""

        with self._lock:
            return list(reversed(self._errors))[: max(0, limit)]

    # -- blocks ------------------------------------------------------------

    def blocked(self, kennung: str | None) -> Block | None:
        """The block in force for this account, if any."""

        if not kennung:
            return None
        with self._lock:
            block = self._blocks.get(kennung)
            if block is None:
                return None
            if block.bis <= self.now():
                del self._blocks[kennung]
                return None
            return block

    def set_block(self, block: Block) -> None:
        """Place a block here and mark it to be written out."""

        with self._lock:
            self._blocks[block.kennung] = block
            self._new_blocks.append(block)

    def clear_block(self, kennung: str) -> None:
        """Lift a block -- and forget the window that caused it.

        Without the second half, lifting an automatic block does nothing an
        operator can see: the short window still holds the calls that tripped
        it, so the next request from that account crosses the line again and
        the block reappears with no explanation. Lifting one means the counting
        starts over.
        """

        with self._lock:
            self._blocks.pop(kennung, None)
            self._recent.pop(kennung, None)
            self._new_blocks = [entry for entry in self._new_blocks if entry.kennung != kennung]

    def adopt_blocks(self, blocks: Iterable[Block]) -> None:
        """Replace what is in force here with what the database says.

        Everything, not a merge: a block lifted in the interface has to
        disappear from every worker, and the only way a worker learns that is
        by being told the whole list. Blocks placed here since the flush began
        are kept -- they are on their way out in the same round trip.
        """

        with self._lock:
            adopted = {block.kennung: block for block in blocks}
            for block in self._new_blocks:
                adopted[block.kennung] = block
            self._blocks = adopted

    # -- flushing ----------------------------------------------------------

    def drain(self) -> Snapshot:
        """Take everything that has accumulated, leaving the tally empty."""

        with self._lock:
            snapshot = Snapshot(
                usage=self._usage,
                accounts=self._accounts,
                errors=self._pending_errors,
                blocks=self._new_blocks,
            )
            self._usage = {}
            self._accounts = {}
            self._pending_errors = []
            self._new_blocks = []
            return snapshot

    def put_back(self, snapshot: Snapshot) -> None:
        """Return a snapshot the flush could not write.

        Without this a database that is down for a minute loses the minute.
        The errors are put back too, but only as far as the ring reaches --
        a flush that keeps failing must not grow this list without end.
        """

        with self._lock:
            for key, counter in snapshot.usage.items():
                target = self._usage.setdefault(key, Counter())
                target.add(
                    anzahl=counter.anzahl,
                    dauer_ms=counter.dauer_ms,
                    tokens_ein=counter.tokens_ein,
                    tokens_aus=counter.tokens_aus,
                )
            for account_key, account in snapshot.accounts.items():
                target_account = self._accounts.setdefault(account_key, AccountCounter())
                target_account.anzahl += account.anzahl
                target_account.fehler += account.fehler
                target_account.tokens_ein += account.tokens_ein
                target_account.tokens_aus += account.tokens_aus
            keep = self._errors.maxlen or 500
            self._pending_errors = (snapshot.errors + self._pending_errors)[-keep:]
            self._new_blocks = snapshot.blocks + self._new_blocks

    # -- what the interface reads straight out of this process -------------

    def live_hours(self) -> dict[tuple[datetime, str, str, str], Counter]:
        """The buckets not yet written out, so the current hour is current."""

        with self._lock:
            return {key: Counter(**vars(counter)) for key, counter in self._usage.items()}

    def live_accounts(self) -> dict[tuple[datetime, str], AccountCounter]:
        with self._lock:
            return {key: AccountCounter(**vars(value)) for key, value in self._accounts.items()}


_recorder: Recorder | None = None
_recorder_lock = threading.Lock()


def recorder() -> Recorder:
    """The one tally of this process.

    A module-level singleton rather than a dependency, because the two places
    that know the most -- ``app/upstream.py`` and the model client -- are two
    layers below any request object, and threading a recorder through every
    service constructor would be a large change for a counter.
    """

    global _recorder
    if _recorder is None:
        with _recorder_lock:
            if _recorder is None:
                from .settings import get_settings

                settings = get_settings().admin
                _recorder = Recorder(
                    burst_calls=settings.burst_calls,
                    burst_window_s=settings.burst_window_s,
                    auto_block_minutes=settings.auto_block_minutes,
                    error_buffer=settings.error_buffer,
                )
    return _recorder


def reset_recorder() -> None:
    """Drop the tally (used when tests change the environment)."""

    global _recorder
    with _recorder_lock:
        _recorder = None
