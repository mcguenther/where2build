#!/usr/bin/env python3
"""Turn a Saxony OpenStreetMap extract into the POI index the API serves.

    cd backend
    .venv/bin/pip install -e ".[poi]"
    .venv/bin/python scripts/build_poi_index.py --download

That downloads ``sachsen-latest.osm.pbf`` from Geofabrik, checks it against the
published MD5, converts it, and writes ``data/poi-sachsen.json``. An extract
already on disk is used instead:

    .venv/bin/python scripts/build_poi_index.py sachsen-latest.osm.pbf

Why an offline build rather than a query at request time: the public Overpass
instances name "an app for more than just OSM mappers relying on the public
instances as backend" as problematic behaviour in their own manual, and their
rate limit is per IP -- ours, shared by every user of the app. A build job that
runs on the order of once a quarter is squarely inside that policy, and so is a
self-hosted instance. See ``docs/research/poi.md`` § 2.2.

The output is a build artefact and is not committed. Without it the API answers
the six OSM categories with "kein Datenbestand eingerichtet", or -- when
``OVERPASS_ENABLED`` is set, which is a single-user prototype convenience and
not a deployment -- from a live Overpass query. Stops and stations come from the
timetable either way and need no extract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The tag mapping lives in the app package, not here: the live Overpass
# source (app/services/overpass.py) answers the same categories and must
# read the same tags. See docs/research/poi.md § 4 for every exclusion.
from app.poi_index import PoiEntry, categorise  # noqa: E402

DEFAULT_EXTRACT_URL = "https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf"
DEFAULT_OUTPUT = BACKEND_DIR / "data" / "poi-sachsen.json"


def _entry(
    osm_kind: str, osm_id: int, tags: dict[str, str], lat: float, lon: float
) -> PoiEntry | None:
    match = categorise(tags)
    if match is None:
        return None
    kategorie, art = match
    return PoiEntry(
        kategorie=kategorie,
        lat=round(float(lat), 6),
        lon=round(float(lon), 6),
        name=(tags.get("name") or "").strip() or None,
        art=art,
        # The Overpass spelling, so a user can look the object up: N…, W…, R….
        osm_id=f"{osm_kind}{osm_id}",
    )


def read_extract(path: Path) -> tuple[list[PoiEntry], str | None]:
    """Every wanted object in the extract, ways and relations at their centre.

    Areas collapse to one representative coordinate, which is what Overpass'
    ``out center`` does and what a "how far is it" question needs.
    """

    try:
        import osmium
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit(
            "pyosmium is required to read an OSM extract.\n"
            '  .venv/bin/pip install -e ".[poi]"   (or: pip install osmium)'
        ) from exc

    entries: list[PoiEntry] = []

    class _Handler(osmium.SimpleHandler):
        def node(self, node: Any) -> None:
            tags = dict(node.tags)
            entry = _entry("N", node.id, tags, node.location.lat, node.location.lon)
            if entry is not None:
                entries.append(entry)

        def area(self, area: Any) -> None:
            tags = dict(area.tags)
            if categorise(tags) is None:
                return
            centre = centroid(_ring_points(area))
            if centre is None:  # a ring whose nodes are not in the extract
                return
            # `orig_id` undoes libosmium's area numbering (way id x 2, relation
            # id x 2 + 1), so the id printed is the one osm.org shows.
            entry = _entry("W" if area.from_way() else "R", area.orig_id(), tags, *centre)
            if entry is not None:
                entries.append(entry)

    handler = _Handler()
    # `locations=True` gives ways their node coordinates; the `area` callback
    # makes apply_file run libosmium's multipolygon assembly first.
    handler.apply_file(str(path), locations=True, idx="flex_mem")

    return entries, _replication_timestamp(path)


def _replication_timestamp(path: Path) -> str | None:
    """The extract's own timestamp from the PBF header, when it carries one."""

    try:
        import osmium

        header = osmium.io.Reader(str(path)).header()
        return header.get("osmosis_replication_timestamp") or None
    except Exception:  # pragma: no cover - XML fixtures carry no header
        return None


def _ring_points(area: Any) -> Iterable[tuple[float, float]]:
    """The outer rings' vertices, without the node that closes each ring.

    Counting the closing node twice pulls the mean towards one corner.
    """

    for ring in area.outer_rings():
        nodes = [node for node in ring if node.location.valid()]
        if len(nodes) > 1 and nodes[0].ref == nodes[-1].ref:
            nodes = nodes[:-1]
        for node in nodes:
            yield node.lat, node.lon


def centroid(points: Iterable[tuple[float, float]]) -> tuple[float, float] | None:
    """Mean of a ring's vertices -- good enough to say how far away it is."""

    lats: list[float] = []
    lons: list[float] = []
    for lat, lon in points:
        lats.append(lat)
        lons.append(lon)
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def download(url: str, target: Path, verify_checksum: bool = True) -> Path:
    """Fetch the extract, resuming nothing and checking the published MD5."""

    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}", flush=True)
    started = time.monotonic()
    digest = hashlib.md5()
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
                digest.update(chunk)
    size = target.stat().st_size
    print(f"  {size / 1e6:.1f} MB in {time.monotonic() - started:.0f} s", flush=True)

    if verify_checksum:
        try:
            expected = httpx.get(f"{url}.md5", timeout=30.0, follow_redirects=True)
            expected.raise_for_status()
            wanted = expected.text.split()[0]
        except Exception as exc:
            print(f"  checksum not verified ({exc})", flush=True)
        else:
            if wanted != digest.hexdigest():
                raise SystemExit(
                    f"MD5 mismatch: expected {wanted}, got {digest.hexdigest()}. "
                    "The download is incomplete or corrupt."
                )
            print("  MD5 ok", flush=True)
    return target


def write_index(entries: list[PoiEntry], out: Path, source: str, datenstand: str | None) -> None:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.kategorie] = counts.get(entry.kategorie, 0) + 1
    payload: dict[str, Any] = {
        "erzeugt_am": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "quelle": source,
        "datenstand": datenstand,
        "lizenz": "OpenStreetMap contributors, ODbL",
        "anzahl": len(entries),
        "anzahl_je_kategorie": counts,
        "eintraege": [entry.as_dict() for entry in entries],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    if out.suffix == ".gz":
        import gzip

        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    else:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)

    print(f"\n{len(entries)} places -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    for kategorie in sorted(counts):
        print(f"  {kategorie:<14} {counts[kategorie]:>6}")
    if datenstand:
        print(f"  extract timestamp: {datenstand}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the POI index served by POST /api/nearby.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "extract",
        nargs="?",
        type=Path,
        help="An .osm.pbf (or .osm/.osm.bz2) file. Omit together with --download.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help=f"Fetch the extract first. Default source: {DEFAULT_EXTRACT_URL}",
    )
    parser.add_argument("--url", default=DEFAULT_EXTRACT_URL, help="Where --download fetches from.")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUTPUT, help=f"Output file (default: {DEFAULT_OUTPUT})."
    )
    parser.add_argument(
        "--keep-download",
        action="store_true",
        help="Keep the downloaded extract instead of deleting it afterwards.",
    )
    parser.add_argument("--no-checksum", action="store_true", help="Skip the MD5 check.")
    args = parser.parse_args(argv)

    if not args.download and args.extract is None:
        parser.error("Give an extract file, or --download to fetch one.")

    downloaded: Path | None = None
    extract = args.extract
    if args.download:
        # APP_CACHE_DIR when it is set: in a container the package directory is
        # not writable, and the scheduler runs this as an unprivileged user.
        cache_root = Path(os.environ.get("APP_CACHE_DIR") or (BACKEND_DIR / ".cache"))
        downloaded = extract or (cache_root / "osm" / Path(args.url).name)
        extract = download(args.url, downloaded, verify_checksum=not args.no_checksum)

    if not extract.is_file():
        raise SystemExit(f"No such extract: {extract}")

    print(f"Reading {extract} …", flush=True)
    started = time.monotonic()
    entries, datenstand = read_extract(extract)
    print(f"  {len(entries)} matching objects in {time.monotonic() - started:.0f} s", flush=True)

    write_index(
        entries,
        args.out,
        source=args.url if args.download else str(extract),
        datenstand=datenstand,
    )

    if downloaded is not None and not args.keep_download:
        downloaded.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
