"""Remove shared links that are past their end.

A shared plot is a copy, so the table only grows: every link ever made would
sit there for ever without something removing it. `STORAGE_SHARE_DAYS` puts an
end on each row and this is what acts on it.

Nothing here is a safety net for the reader -- `Storage.share()` already
refuses an expired token, so a row that outlives its date is invisible either
way. What this reclaims is disk, and what it removes is a snapshot of somebody's
plot that nobody can reach any more, which is a reason of its own to not keep
it.

A deployment without `DATABASE_URL` has no such table; the job says so and
exits cleanly rather than treating a complete deployment as a failure.

    python scripts/sweep_shares.py [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.storage import Storage  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def sweep() -> int:
    storage = Storage(get_settings().storage)
    try:
        return await storage.sweep_shares()
    finally:
        await storage.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben.")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.storage.configured:
        report = {"status": "kein-speicher", "entfernt": 0}
        print(json.dumps(report) if args.json else "Kein Serverspeicher eingerichtet, nichts zu tun.")
        return 0

    removed = asyncio.run(sweep())
    if args.json:
        print(json.dumps({"status": "ok", "entfernt": removed}))
    else:
        print(f"{removed} abgelaufene Freigaben entfernt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
