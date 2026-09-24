#!/usr/bin/env python3
"""Fetch the two inputs the stack's own MOTIS is built from.

    python scripts/fetch_routing_data.py /data-input            # what compose runs
    python scripts/fetch_routing_data.py /data-input --refresh  # a new timetable

Writes ``osm.pbf`` (the street network, Saxony from Geofabrik) and
``timetable.gtfs.zip`` (the Germany-wide DELFI timetable) into the directory,
which is the pair ``motis/config.yml`` names. A file that is already there is
kept, so the second ``docker compose up`` downloads nothing; ``--refresh``
replaces both.

The same street network also feeds the POI index (``build_poi_index.py``), so
the extract is downloaded once for both.

Both are licensed and must be attributed wherever routes are shown:
  - OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)
  - DELFI e. V., CC-BY 4.0 (https://www.opendata-oepnv.de/)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.settings import get_settings  # noqa: E402

# Saxony only: the app never routes beyond the state, and the extract decides
# how long the import takes. A Germany extract works as well, at several times
# the import cost.
DEFAULT_OSM_URL = "https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf"
# The file Transitous itself feeds to MOTIS for Germany -- the raw DELFI
# "Deutschlandweite Sollfahrplandaten (GTFS)", republished so it can be fetched
# without the registration opendata-oepnv.de asks for. Updated weekly, Mondays.
DEFAULT_GTFS_URL = "https://api.transitous.org/gtfs/de_DELFI.gtfs.zip"

# The names motis/config.yml reads.
OSM_NAME = "osm.pbf"
GTFS_NAME = "timetable.gtfs.zip"


def download(url: str, target: Path, *, user_agent: str, md5_url: str | None = None) -> None:
    """Fetch into ``target.part`` and move it into place only once complete.

    A half-finished file under the final name would be taken for a finished
    one on the next start, and MOTIS would import a truncated network.
    """

    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    print(f"Downloading {url}", flush=True)
    started = time.monotonic()
    digest = hashlib.md5()
    with httpx.stream(
        "GET", url, timeout=300.0, follow_redirects=True, headers={"User-Agent": user_agent}
    ) as response:
        response.raise_for_status()
        with part.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
                digest.update(chunk)
    size = part.stat().st_size
    print(f"  {size / 1e6:.1f} MB in {time.monotonic() - started:.0f} s", flush=True)

    if md5_url:
        expected = httpx.get(md5_url, timeout=30.0, follow_redirects=True, headers={"User-Agent": user_agent})
        expected.raise_for_status()
        wanted = expected.text.split()[0]
        if wanted != digest.hexdigest():
            part.unlink(missing_ok=True)
            raise SystemExit(f"MD5 mismatch for {url}: expected {wanted}, got {digest.hexdigest()}.")
        print("  MD5 ok", flush=True)
    part.replace(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the OSM extract and the GTFS timetable for a local MOTIS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("directory", type=Path, help="Where osm.pbf and timetable.gtfs.zip go.")
    parser.add_argument("--refresh", action="store_true", help="Replace files that are already there.")
    parser.add_argument("--osm-url", default=os.environ.get("W2B_OSM_URL") or DEFAULT_OSM_URL)
    parser.add_argument("--gtfs-url", default=os.environ.get("W2B_GTFS_URL") or DEFAULT_GTFS_URL)
    args = parser.parse_args(argv)

    settings = get_settings()
    user_agent = settings.app.user_agent
    # The GTFS copy is Transitous', whose usage policy asks for a way of
    # contact -- the same agent the routing requests carry.
    gtfs_agent = settings.app.contact_user_agent

    # Geofabrik publishes an MD5 next to every extract; a custom source may not.
    osm_md5 = f"{args.osm_url}.md5" if "download.geofabrik.de" in args.osm_url else None
    wanted = [
        (args.osm_url, args.directory / OSM_NAME, user_agent, osm_md5),
        (args.gtfs_url, args.directory / GTFS_NAME, gtfs_agent, None),
    ]
    for url, target, agent, md5_url in wanted:
        if target.is_file() and not args.refresh:
            print(f"{target} is there ({target.stat().st_size / 1e6:.1f} MB) -- kept.", flush=True)
            continue
        download(url, target, user_agent=agent, md5_url=md5_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
