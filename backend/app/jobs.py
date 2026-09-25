"""The recurring jobs, as the API sees them.

``scripts/run_jobs.py`` owns the schedule and the running; this module owns the
three things both sides have to agree on -- where the job list is, where a
job's record of itself is, and how a run is asked for from outside. The runner
imports it, so there is one spelling of each rather than two that drift.

**Why the API does not run the jobs itself.** The heavy ones rebuild an index
into ``backend/data``, which the API mounts read-only, and they take minutes:
a "run now" that shelled out here would need a writable data mount and would
put a six-minute download inside the process serving requests. So the button
writes a *request* into the state directory both containers share, and the
scheduler picks it up on its next tick -- in the container that already has the
privileges, the writable mount and the lock. Without a scheduler running,
nothing happens, and the interface says so instead of pretending: the scheduler
leaves a heartbeat next to the records, and a request that sits unclaimed is
visible as one.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Where the two containers meet. Both are overridden in the compose file; the
# defaults are what a checkout has.
DEFAULT_JOBS_FILE = Path(__file__).resolve().parent.parent.parent / "ops" / "jobs.json"
DEFAULT_STATE_DIR = Path(os.environ.get("JOBS_STATE_DIR", "/state"))

# The scheduler's own record, so "is anybody there" is answerable. Not a job.
HEARTBEAT = "scheduler.json"
# How long a heartbeat counts as current. Three ticks of the runner's twenty
# seconds, so a single slow tick does not report the scheduler as gone.
HEARTBEAT_STALE_S = 90


@dataclass(frozen=True)
class Job:
    """One entry of ``ops/jobs.json``, plus what is known about its last run."""

    name: str
    schedule: str
    why: str
    command: list[str]
    last_start: str | None = None
    last_exit_code: int | None = None
    last_duration_s: float | None = None
    running: bool = False
    requested: str | None = None


def state_file(state_dir: Path, name: str) -> Path:
    return state_dir / f"{name}.json"


def request_file(state_dir: Path, name: str) -> Path:
    return state_dir / f"{name}.angefordert"


def lock_file(state_dir: Path, name: str) -> Path:
    return state_dir / f"{name}.lock"


def read_state(state_dir: Path, name: str) -> dict[str, Any]:
    try:
        return json.loads(state_file(state_dir, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state_dir: Path, name: str, state: dict[str, Any]) -> str | None:
    """Store a job's record. Returns the problem, if there was one.

    Losing the record is not worth losing the run over, so the caller logs and
    carries on.
    """

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        target = state_file(state_dir, name)
        temporary = target.with_suffix(".part")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(target)
        return None
    except OSError as error:
        return str(error)


def load_jobs(path: Path | str) -> list[dict[str, Any]]:
    """The job list as written, unvalidated beyond being a list of objects."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = raw["jobs"]
    if not isinstance(jobs, list):
        raise ValueError("„jobs“ ist keine Liste.")
    return jobs


def describe(path: Path | str, state_dir: Path | str) -> list[Job]:
    """Every job with what is known about it. A missing state dir is empty."""

    directory = Path(state_dir)
    found: list[Job] = []
    for entry in load_jobs(path):
        state = read_state(directory, entry["name"])
        requested = request_file(directory, entry["name"])
        found.append(
            Job(
                name=entry["name"],
                schedule=entry.get("schedule", ""),
                why=entry.get("why", ""),
                command=list(entry.get("command", [])),
                last_start=state.get("last_start"),
                last_exit_code=state.get("last_exit_code"),
                last_duration_s=state.get("last_duration_s"),
                running=lock_file(directory, entry["name"]).exists(),
                requested=_requested_at(requested),
            )
        )
    return found


def _requested_at(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def request_run(state_dir: Path | str, name: str, *, by: str) -> None:
    """Ask the scheduler to run this job on its next tick.

    A file rather than a queue: both containers already share this directory,
    the request survives a restart of either of them, and a second request
    while one is pending is the same request.
    """

    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    request_file(directory, name).write_text(f"{stamp} {by}\n", encoding="utf-8")


def take_request(state_dir: Path | str, name: str) -> str | None:
    """Claim a pending request, if there is one. Called by the scheduler."""

    path = request_file(Path(state_dir), name)
    try:
        asked = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    path.unlink(missing_ok=True)
    return asked or ""


def beat(state_dir: Path | str) -> None:
    """The scheduler saying it is there. Called on every tick."""

    directory = Path(state_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / HEARTBEAT).write_text(
            json.dumps({"zuletzt": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}),
            encoding="utf-8",
        )
    except OSError:
        # A scheduler that cannot write its heartbeat still runs its jobs.
        pass


def scheduler_seen(state_dir: Path | str) -> str | None:
    """When a scheduler last said it was there, or ``None``.

    ``None`` is the state a deployment without the ``scheduler`` service is
    in -- which is a complete deployment, and the reason the interface says
    "nothing will pick this up" rather than showing a button that does nothing.
    """

    try:
        raw = json.loads((Path(state_dir) / HEARTBEAT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw.get("zuletzt")


def scheduler_alive(state_dir: Path | str, *, now: datetime | None = None) -> bool:
    seen = scheduler_seen(state_dir)
    if not seen:
        return False
    try:
        moment = datetime.fromisoformat(seen)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - moment).total_seconds() < HEARTBEAT_STALE_S
