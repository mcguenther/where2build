#!/usr/bin/env python3
"""Turn the Saxon Hauskoordinaten into the address index the API serves.

    cd backend
    .venv/bin/python scripts/build_address_index.py --download

That fetches ``hk_sn_ascii.zip`` from the GeoSN's open-data share, reads the one
text file inside it, projects every coordinate from ETRS89/UTM33 to WGS84 and
writes ``data/hauskoordinaten-sachsen.json.gz``. A ZIP already on disk is used
instead:

    .venv/bin/python scripts/build_address_index.py hk_sn_ascii.zip

Why an offline build. The download is one file for the whole state, refreshed
quarterly, and there is no query interface in front of it -- the alternative to
a build step is not a live service, it is 51 MB per request. The output is far
too big to commit (see --out below), so it is a build artefact like the POI
index: without it ``POST /api/geocode`` answers from MOTIS alone, exactly as it
did before this script existed, and ``/api/health`` says which of the two is
answering.

Licence: Datenlizenz Deutschland Namensnennung 2.0, source "GeoSN".
Download page: https://www.geodaten.sachsen.de/downloadbereich-hauskoordinaten-4172.html
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The field names and the number spelling live in the app package: the endpoint
# reads what this writes, and the two must not drift apart.
from app.address_index import (  # noqa: E402
    MICRODEGREES,
    _NUMBER_SEPARATOR,
    house_number,
)
from app.settings import get_settings  # noqa: E402

DEFAULT_OUTPUT = BACKEND_DIR / "data" / "hauskoordinaten-sachsen.json.gz"

# Columns of hk_sn_adressen_*.txt, verified against the file's own header row.
# `zone` is read only to be checked: the whole state is UTM zone 33, and a row
# that says otherwise would be silently projected into the wrong hemisphere.
REQUIRED_COLUMNS = (
    "str",
    "hnr",
    "adz",
    "zone",
    "ostwert",
    "nordwert",
    "postplz",
    "postonm",
    "postott",
    "gmd",
)
EXPECTED_ZONE = "33"
UTM_ZONE_33 = "EPSG:25833"

# hk_sn_adressen_20260702.txt -- the data's own currency, not the day it was
# fetched. Shown next to a hit, so it has to be the former.
_DATE_IN_NAME = re.compile(r"(\d{4})(\d{2})(\d{2})")


def datenstand(member: str) -> str | None:
    """The date the file names itself after, as ISO."""

    match = _DATE_IN_NAME.search(Path(member).stem)
    return "-".join(match.groups()) if match else None


def download(url: str, target: Path, *, user_agent: str) -> Path:
    """Fetch the ZIP to ``target``, writing a ``.part`` until it is complete.

    HEAD is not used anywhere here: this share answers 401 to it and 200 to the
    GET it serves happily (docs/research/geodaten-sachsen.md § 4.1).
    """

    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    print(f"Downloading {url}", flush=True)
    started = time.monotonic()
    with httpx.stream(
        "GET", url, timeout=300.0, follow_redirects=True, headers={"User-Agent": user_agent}
    ) as response:
        response.raise_for_status()
        with part.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    size = part.stat().st_size
    if size < 1_000_000:
        part.unlink(missing_ok=True)
        raise SystemExit(f"{url} answered {size} bytes -- that is not the address archive.")
    part.replace(target)
    print(f"  {size / 1e6:.1f} MB in {time.monotonic() - started:.0f} s", flush=True)
    return target


def open_member(archive: Path) -> tuple[str, Any]:
    """The single text file inside the ZIP, and its name."""

    zf = zipfile.ZipFile(archive)
    members = [info.filename for info in zf.infolist() if not info.is_dir()]
    text_files = [name for name in members if name.lower().endswith(".txt")]
    if len(text_files) != 1:
        raise SystemExit(
            f"{archive} holds {len(text_files)} .txt files ({members}) -- expected exactly one."
        )
    return text_files[0], zf.open(text_files[0])


def read_rows(archive: Path) -> tuple[Iterator[dict[str, str]], str]:
    member, handle = open_member(archive)
    stream = io.TextIOWrapper(handle, encoding="utf-8", newline="")
    reader = csv.DictReader(stream, delimiter=";")
    missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(
            f"{member} is missing the columns {missing}. Its header is "
            f"{reader.fieldnames} -- the published layout has changed."
        )
    return reader, member


def group_rows(rows: Iterator[dict[str, str]]) -> tuple[dict[tuple[str, ...], list[Any]], int]:
    """Collect every address under its street, keeping the source order.

    Grouped by the columns a user sees, not by the cadastral street key: two
    keys spelling one street in one postal place are one entry in a picklist,
    and one key split over two postcodes is two.
    """

    groups: dict[tuple[str, ...], list[Any]] = defaultdict(list)
    total = 0
    for row in rows:
        if row.get("zone") != EXPECTED_ZONE:
            raise SystemExit(
                f"Row {total + 1} carries zone={row.get('zone')!r}, not {EXPECTED_ZONE}. "
                "The whole file is assumed to be UTM zone 33 -- refusing to guess."
            )
        street = (row.get("str") or "").strip()
        if not street:
            continue
        key = (
            street,
            (row.get("postplz") or "").strip(),
            (row.get("postonm") or "").strip(),
            (row.get("postott") or "").strip(),
            (row.get("gmd") or "").strip(),
        )
        groups[key].append(
            (
                house_number(row.get("hnr") or "", row.get("adz") or ""),
                float(row["ostwert"]),
                float(row["nordwert"]),
            )
        )
        total += 1
    return groups, total


def project(groups: dict[tuple[str, ...], list[Any]]) -> list[dict[str, Any]]:
    """Project every coordinate to WGS84 in one pass and lay out the entries.

    pyproj transforms whole arrays far faster than points one at a time, and
    there are a million of them, so the eastings and northings are collected
    across all streets first and handed over once.
    """

    from pyproj import Transformer

    eastings: list[float] = []
    northings: list[float] = []
    for entries in groups.values():
        for _, easting, northing in entries:
            eastings.append(easting)
            northings.append(northing)

    transformer = Transformer.from_crs(UTM_ZONE_33, "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(eastings, northings)

    strassen: list[dict[str, Any]] = []
    offset = 0
    for (street, postplz, postonm, postott, gmd), entries in groups.items():
        count = len(entries)
        window = slice(offset, offset + count)
        offset += count
        # Sorted so the numbers of a street read in order in the artefact and
        # a query for "12" finds "12" before "12a".
        order = sorted(range(count), key=lambda i: _number_key(entries[i][0]))
        street_lats = list(lats[window])
        street_lons = list(lons[window])
        strassen.append(
            {
                "str": street,
                "postplz": postplz,
                "postonm": postonm,
                "postott": postott,
                "gmd": gmd,
                "hnr": _NUMBER_SEPARATOR.join(entries[i][0] for i in order),
                "lat": [round(street_lats[i] * MICRODEGREES) for i in order],
                "lon": [round(street_lons[i] * MICRODEGREES) for i in order],
            }
        )
    strassen.sort(key=lambda item: (item["str"], item["postplz"], item["postott"]))
    return strassen


def _number_key(written: str) -> tuple[int, str]:
    digits = "".join(c for c in written if c.isdigit())
    return (int(digits) if digits else 0), written


def write_index(
    strassen: list[dict[str, Any]],
    out: Path,
    *,
    source: str,
    stand: str | None,
    anzahl: int,
) -> None:
    payload: dict[str, Any] = {
        "erzeugt_am": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quelle": source,
        "stand": stand,
        "lizenz": "GeoSN, dl-de/by-2-0",
        "anzahl": anzahl,
        "anzahl_strassen": len(strassen),
        # 1e-6 degrees. Named in the file so a reader of the artefact does not
        # have to infer it from the magnitude of the numbers.
        "koordinaten_faktor": MICRODEGREES,
        "strassen": strassen,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    if out.suffix == ".gz":
        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    else:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    print(
        f"\n{anzahl} Adressen in {len(strassen)} Straßen -> {out} "
        f"({out.stat().st_size / 1e6:.1f} MB)"
    )
    if stand:
        print(f"  Datenstand {stand}")


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Build the official address index used by POST /api/geocode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "archive",
        nargs="?",
        type=Path,
        help="The hk_sn_ascii.zip on disk. Omit together with --download.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help=f"Fetch the archive first. Default source: {settings.addresses.download_url}",
    )
    parser.add_argument(
        "--url",
        default=settings.addresses.download_url,
        help="Where --download fetches from.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--keep-download",
        action="store_true",
        help="Keep the downloaded archive instead of deleting it afterwards.",
    )
    args = parser.parse_args(argv)

    if not args.download and args.archive is None:
        parser.error("Give a hk_sn_ascii.zip, or --download to fetch one.")

    downloaded: Path | None = None
    archive = args.archive
    if args.download:
        downloaded = archive or (BACKEND_DIR / ".cache" / "hauskoordinaten" / Path(args.url).name)
        archive = download(args.url, downloaded, user_agent=settings.app.user_agent)

    if not archive.is_file():
        raise SystemExit(f"No such archive: {archive}")

    print(f"Reading {archive} …", flush=True)
    started = time.monotonic()
    rows, member = read_rows(archive)
    groups, total = group_rows(rows)
    if not total:
        raise SystemExit(f"{member} held no address rows -- nothing written.")
    print(f"  {total} rows, {len(groups)} streets in {time.monotonic() - started:.0f} s", flush=True)

    strassen = project(groups)
    write_index(
        strassen,
        args.out,
        source=args.url if args.download else str(archive),
        stand=datenstand(member),
        anzahl=total,
    )
    print(f"  {time.monotonic() - started:.0f} s total", flush=True)

    if downloaded is not None and not args.keep_download:
        downloaded.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
