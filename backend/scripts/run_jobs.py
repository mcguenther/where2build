#!/usr/bin/env python3
"""Runs the recurring jobs listed in ``ops/jobs.json``.

    python scripts/run_jobs.py list          what is defined, and when it next runs
    python scripts/run_jobs.py run NAME      run one now, whatever its schedule says
    python scripts/run_jobs.py serve         the loop the scheduler container runs

Why a loop of our own rather than cron: the jobs here all run *inside this
image* against the shared volumes, so nothing needs the Docker socket — and
mounting that socket is handing a container root on the host, which is a steep
price for four timed commands. The one job that genuinely needs host privileges
is the MOTIS refresh, because it stops a service and replaces a volume; that
one stays a host-side command and is documented as such in the README rather
than pretended to be solved here.

State lives next to the job list as ``<state-dir>/<name>.json`` — last start,
last exit code, last duration. That is what makes ``list`` able to answer "when
did this last run, and did it work", which is the question an operator actually
has.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Where the job list and the records live, and how a run is asked for from
# outside, all live in `app/jobs.py` -- the API shows the same records and the
# administration area writes those requests, and two spellings of one file name
# is how the two sides stop agreeing.
from app.jobs import (  # noqa: E402
    DEFAULT_JOBS_FILE as DEFAULT_JOBS,
    DEFAULT_STATE_DIR as DEFAULT_STATE,
    beat,
    read_state,
    state_file,
    take_request,
    write_state as store_state,
)

# How often the loop wakes to see whether a minute with work in it has passed.
# Cron's resolution is the minute, so anything finer only burns cycles.
TICK_S = 20


class Job:
    def __init__(self, raw: dict) -> None:
        self.name: str = raw["name"]
        self.schedule: str = raw["schedule"]
        self.command: list[str] = list(raw["command"])
        self.why: str = raw.get("why", "")
        self.fields = parse_schedule(self.schedule)


def parse_schedule(expression: str) -> list[set[int]]:
    """The five cron fields as explicit sets of allowed values.

    Supports ``*``, ``a-b``, ``a,b``, ``*/n`` and ``a-b/n`` — everything the
    job list uses and nothing it does not. An expression this does not
    understand raises rather than silently matching nothing, because a job that
    never fires is the failure nobody notices.
    """

    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(f"{expression!r} is not five cron fields")

    fields = []
    for part, (low, high) in zip(parts, ranges):
        allowed: set[int] = set()
        for piece in part.split(","):
            step = 1
            if "/" in piece:
                piece, _, raw_step = piece.partition("/")
                step = int(raw_step)
            if piece in ("*", ""):
                start, end = low, high
            elif "-" in piece:
                raw_start, _, raw_end = piece.partition("-")
                start, end = int(raw_start), int(raw_end)
            else:
                start = end = int(piece)
            if not (low <= start <= high and low <= end <= high and start <= end):
                raise ValueError(f"{part!r} is outside {low}-{high}")
            allowed.update(range(start, end + 1, step))
        if not allowed:
            raise ValueError(f"{part!r} matches nothing")
        fields.append(allowed)
    return fields


def due(job: Job, when: datetime) -> bool:
    minute, hour, day, month, weekday = job.fields
    # Cron's own quirk, kept deliberately: with both day-of-month and day-of-week
    # restricted, either matching is enough.
    day_restricted = len(day) < 31
    weekday_restricted = len(weekday) < 7
    day_ok = when.day in day
    weekday_ok = when.isoweekday() % 7 in weekday
    if day_restricted and weekday_restricted:
        days = day_ok or weekday_ok
    else:
        days = day_ok and weekday_ok
    return when.minute in minute and when.hour in hour and days and when.month in month


def load(path: Path) -> list[Job]:
    document = json.loads(path.read_text(encoding="utf-8"))
    jobs = [Job(raw) for raw in document["jobs"]]
    names = [j.name for j in jobs]
    duplicate = {n for n in names if names.count(n) > 1}
    if duplicate:
        raise ValueError(f"two jobs share a name: {', '.join(sorted(duplicate))}")
    return jobs


def write_state(state_dir: Path, name: str, state: dict) -> None:
    problem = store_state(state_dir, name, state)
    if problem:
        # Losing the record is not worth losing the run over.
        log(name, f"state not written: {problem}")


def log(name: str, message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{stamp} [{name}] {message}", flush=True)


def run(job: Job, state_dir: Path) -> int:
    """Run one job, unless it is already running. Returns its exit code."""

    lock = state_dir / f"{job.name}.lock"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        # O_EXCL is the whole lock: the import takes six minutes and a second
        # copy of it would fight the first over the same volume.
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        log(job.name, "skipped: already running (remove the lock if that is wrong)")
        return 75          # EX_TEMPFAIL: not a failure of the job itself
    except OSError as error:
        log(job.name, f"could not take the lock: {error}")
        return 1

    started = time.time()
    os.write(handle, f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n".encode())
    os.close(handle)
    log(job.name, f"start: {' '.join(job.command)}")
    try:
        completed = subprocess.run(job.command, cwd=BACKEND_DIR, check=False)
        code = completed.returncode
    except OSError as error:
        # A job whose command does not exist must be loud and must not take the
        # loop down with it.
        log(job.name, f"FAILED to start: {error}")
        code = 127
    finally:
        lock.unlink(missing_ok=True)

    seconds = round(time.time() - started, 1)
    log(job.name, ("done" if code == 0 else f"FAILED with exit {code}") + f" after {seconds} s")
    write_state(state_dir, job.name, {
        "last_start": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "last_exit_code": code,
        "last_duration_s": seconds,
    })
    return code


def command_list(jobs: list[Job], state_dir: Path) -> int:
    for job in jobs:
        state = read_state(state_dir, job.name)
        if not state:
            last = "never run"
        else:
            code = state.get("last_exit_code")
            outcome = "ok" if code == 0 else f"exit {code}"
            last = f"{state.get('last_start', '?')} — {outcome}, {state.get('last_duration_s', '?')} s"
        print(f"{job.name:<16} {job.schedule:<14} {last}")
        if job.why:
            print(f"{'':<16} {job.why}")
    return 0


def command_serve(jobs: list[Job], state_dir: Path) -> int:
    log("scheduler", f"{len(jobs)} jobs: {', '.join(j.name for j in jobs)}")
    fired: set[tuple[str, str]] = set()
    while True:
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y-%m-%dT%H:%M")
        # The heartbeat first, so it is written even on a tick where a job
        # takes minutes: the administration area reads it to say whether
        # anything is here to pick a request up at all.
        beat(state_dir)
        for job in jobs:
            # A run asked for in the administration area. Claimed before the
            # schedule is looked at, and claimed by *removing* the request, so
            # a job that fails is not started again every twenty seconds.
            asked = take_request(state_dir, job.name)
            if asked is not None:
                log(job.name, f"run requested ({asked or 'ohne Angabe'})")
                run(job, state_dir)
                continue
            if (job.name, stamp) in fired or not due(job, now):
                continue
            fired.add((job.name, stamp))
            # A failing job must not stop the others, or one broken import
            # silently takes the whole schedule with it.
            run(job, state_dir)
        # The set only needs the current minute; anything older cannot fire again.
        fired = {entry for entry in fired if entry[1] == stamp}
        time.sleep(TICK_S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["list", "run", "serve"])
    parser.add_argument("name", nargs="?", help="Which job, for `run`.")
    parser.add_argument("--jobs", type=Path, default=Path(os.environ.get("JOBS_FILE", DEFAULT_JOBS)))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)

    try:
        jobs = load(args.jobs)
    except (OSError, ValueError, KeyError) as error:
        print(f"Job list unusable ({args.jobs}): {error}", file=sys.stderr)
        return 2

    if args.action == "list":
        return command_list(jobs, args.state_dir)
    if args.action == "run":
        if not args.name:
            print("Which job? See `list`.", file=sys.stderr)
            return 2
        for job in jobs:
            if job.name == args.name:
                return run(job, args.state_dir)
        print(f"No job called {args.name!r}. See `list`.", file=sys.stderr)
        return 2
    return command_serve(jobs, args.state_dir)


if __name__ == "__main__":
    raise SystemExit(main())
