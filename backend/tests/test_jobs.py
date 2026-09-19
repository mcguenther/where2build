"""The recurring-job runner.

Three things have to hold, and each of them is a way the thing could be useless
without anyone noticing: a schedule that never fires, a failure that looks like
a success, and two copies of a six-minute import fighting over one volume.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_jobs  # noqa: E402


def job_file(tmp_path: Path, **overrides) -> Path:
    entry = {
        "name": "example",
        "schedule": "0 3 * * *",
        "command": [sys.executable, "-c", "pass"],
        "why": "A job used by the tests.",
    }
    entry.update(overrides)
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [entry]}), encoding="utf-8")
    return path


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class TestSchedule:
    def test_a_daily_job_fires_at_its_minute_and_not_beside_it(self):
        job = run_jobs.Job({"name": "n", "schedule": "17 3 * * *", "command": ["true"]})
        assert run_jobs.due(job, at("2026-09-01T03:17:00"))
        assert not run_jobs.due(job, at("2026-09-01T03:16:00"))
        assert not run_jobs.due(job, at("2026-09-01T04:17:00"))

    def test_a_weekly_job_fires_on_its_weekday(self):
        # 2026-08-31 is a Monday, 2026-09-01 a Tuesday.
        job = run_jobs.Job({"name": "n", "schedule": "40 2 * * 1", "command": ["true"]})
        assert run_jobs.due(job, at("2026-08-31T02:40:00"))
        assert not run_jobs.due(job, at("2026-09-01T02:40:00"))

    def test_a_quarterly_job_fires_on_the_first_of_its_months(self):
        job = run_jobs.Job({"name": "n", "schedule": "20 4 1 */3 *", "command": ["true"]})
        assert run_jobs.due(job, at("2026-10-01T04:20:00"))
        assert not run_jobs.due(job, at("2026-11-01T04:20:00"))
        assert not run_jobs.due(job, at("2026-10-02T04:20:00"))

    @pytest.mark.parametrize("expression", ["99 * * * *", "* * * *", "* * * * 9", "5-2 * * * *", "x * * * *"])
    def test_an_expression_it_cannot_read_is_refused_rather_than_never_firing(self, expression):
        """A job that silently matches nothing is the failure nobody notices."""

        with pytest.raises(ValueError):
            run_jobs.parse_schedule(expression)


class TestRunning:
    def test_a_successful_job_records_what_it_did(self, tmp_path, capsys):
        state = tmp_path / "state"
        assert run_jobs.run(run_jobs.load(job_file(tmp_path))[0], state) == 0
        recorded = json.loads((state / "example.json").read_text())
        assert recorded["last_exit_code"] == 0
        assert "done" in capsys.readouterr().out

    def test_a_failing_job_is_loud_and_keeps_its_exit_code(self, tmp_path, capsys):
        path = job_file(tmp_path, command=[sys.executable, "-c", "raise SystemExit(3)"])
        assert run_jobs.run(run_jobs.load(path)[0], tmp_path / "state") == 3
        assert "FAILED with exit 3" in capsys.readouterr().out

    def test_a_command_that_does_not_exist_fails_instead_of_raising(self, tmp_path, capsys):
        path = job_file(tmp_path, command=["/definitely/not/here"])
        assert run_jobs.run(run_jobs.load(path)[0], tmp_path / "state") == 127
        assert "FAILED to start" in capsys.readouterr().out

    def test_a_second_copy_is_skipped_while_the_first_holds_the_lock(self, tmp_path, capsys):
        state = tmp_path / "state"
        state.mkdir()
        (state / "example.lock").touch()
        # 75 is EX_TEMPFAIL: nothing failed, the work was simply already in hand.
        assert run_jobs.run(run_jobs.load(job_file(tmp_path))[0], state) == 75
        assert "already running" in capsys.readouterr().out

    def test_the_lock_is_released_even_when_the_job_fails(self, tmp_path):
        state = tmp_path / "state"
        path = job_file(tmp_path, command=[sys.executable, "-c", "raise SystemExit(1)"])
        run_jobs.run(run_jobs.load(path)[0], state)
        assert not (state / "example.lock").exists()


class TestCommandLine:
    def test_list_says_when_each_job_last_ran(self, tmp_path, capsys):
        path = job_file(tmp_path)
        state = tmp_path / "state"
        assert run_jobs.main(["list", "--jobs", str(path), "--state-dir", str(state)]) == 0
        assert "never run" in capsys.readouterr().out

        run_jobs.main(["run", "example", "--jobs", str(path), "--state-dir", str(state)])
        capsys.readouterr()
        run_jobs.main(["list", "--jobs", str(path), "--state-dir", str(state)])
        assert "ok" in capsys.readouterr().out

    def test_an_unknown_job_name_is_refused(self, tmp_path, capsys):
        path = job_file(tmp_path)
        assert run_jobs.main(["run", "nope", "--jobs", str(path), "--state-dir", str(tmp_path)]) == 2
        assert "No job called" in capsys.readouterr().err

    def test_an_unreadable_job_list_is_refused_with_the_reason(self, tmp_path, capsys):
        broken = tmp_path / "jobs.json"
        broken.write_text('{"jobs": [{"name": "a", "schedule": "99 * * * *", "command": ["true"]}]}')
        assert run_jobs.main(["list", "--jobs", str(broken), "--state-dir", str(tmp_path)]) == 2
        assert "outside 0-59" in capsys.readouterr().err

    def test_two_jobs_may_not_share_a_name(self, tmp_path):
        path = tmp_path / "jobs.json"
        entry = {"name": "same", "schedule": "0 0 * * *", "command": ["true"]}
        path.write_text(json.dumps({"jobs": [entry, entry]}))
        with pytest.raises(ValueError, match="share a name"):
            run_jobs.load(path)


def test_the_shipped_job_list_is_valid():
    """The list that actually runs in the deployment, parsed for real."""

    shipped = Path(__file__).resolve().parent.parent.parent / "ops" / "jobs.json"
    jobs = run_jobs.load(shipped)
    assert {j.name for j in jobs} == {
        "cache-sweep", "freigaben-sweep", "poi-index", "address-index", "llm-preise"
    }
    # Every job explains itself; `list` prints this and an operator reads it.
    assert all(j.why for j in jobs)
