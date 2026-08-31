#!/usr/bin/env python3
"""Pull the Saxon cadastral districts once and write the directory the API serves.

    cd backend
    .venv/bin/python scripts/build_gemarkung_index.py

That reads ``ave:KatasterBezirk`` from the ALKIS WFS page by page, keeps the
features whose ``art`` is "Gemarkung", and writes ``data/gemarkungen-sachsen.json``
-- name, six-digit key and municipality per district, plus the date of the run.
The file is committed; ``GET /api/gemarkungen`` reads it and never calls the WFS.

Why an offline build. The layer carries each district's boundary polygon and
there is no way to ask it not to: without the ``ave:`` prefix ``PROPERTYNAME``
is answered with ``ErrorInPropertyName``, with the prefix the request is
accepted and the geometry comes anyway. Measured on 30.08.2026: eleven pages
of 500, 56 MB of GML decoded, for the 503 kB of text an input mask needs. That
is fine once a quarter and absurd once a request.

Paging is ordered by ``SORTBY`` on purpose: WFS 2.0 gives no guarantee that two
``STARTINDEX`` windows of an unordered result do not overlap or skip.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator
from xml.etree import ElementTree

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The field names and the folding rules live in the app package: the endpoint
# reads what this writes, and the two must not drift apart.
from app.gemarkung_index import (  # noqa: E402
    GEMARKUNG_ART,
    SOURCE_FIELDS,
    GemarkungEntry,
    sort_key,
)
from app.settings import get_settings  # noqa: E402

DEFAULT_OUTPUT = BACKEND_DIR / "data" / "gemarkungen-sachsen.json"
# One page. Small enough that a dropped connection costs little, large enough
# that the whole state is a couple of dozen requests.
DEFAULT_PAGE_SIZE = 500


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_features(chunks: Iterable[bytes]) -> Iterator[dict[str, str]]:
    """The wanted attributes of every ``KatasterBezirk``, geometry discarded.

    Parsed as the bytes arrive and the tree is cleared after each feature, so
    peak memory is one district and not the whole 56 MB response.
    """

    parser = ElementTree.XMLPullParser(("start", "end"))
    root: ElementTree.Element | None = None
    for chunk in chunks:
        parser.feed(chunk)
        for event, element in parser.read_events():
            if event == "start":
                if root is None:
                    root = element
                    if _local(root.tag) in ("ServiceExceptionReport", "ExceptionReport", "html"):
                        raise SystemExit(
                            "The ALKIS WFS rejected the request "
                            f"(<{_local(root.tag)}>). Check TYPENAMES and SORTBY."
                        )
                continue
            if _local(element.tag) != "KatasterBezirk":
                continue
            yield {
                _local(child.tag): (child.text or "").strip()
                for child in element
                if _local(child.tag) in SOURCE_FIELDS
            }
            # Drops the finished member, geometry and all. The element just
            # yielded keeps its own reference until the caller is done with it.
            if root is not None:
                root.clear()
    parser.close()


def fetch_page(
    client: Any, url: str, *, start_index: int, count: int, version: str
) -> tuple[list[dict[str, str]], int]:
    """One ``STARTINDEX`` window. Returns the features and the bytes it cost."""

    params = {
        "SERVICE": "WFS",
        "VERSION": version,
        "REQUEST": "GetFeature",
        "TYPENAMES": "ave:KatasterBezirk",
        "SORTBY": "ave:schluessel",
        "COUNT": str(count),
        "STARTINDEX": str(start_index),
    }
    received = 0

    def _chunks(response: Any) -> Iterator[bytes]:
        nonlocal received
        for chunk in response.iter_bytes():
            received += len(chunk)
            yield chunk

    with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        features = list(parse_features(_chunks(response)))
    return features, received


def fetch_all(url: str, *, user_agent: str, page_size: int, version: str) -> list[dict[str, str]]:
    import httpx

    features: list[dict[str, str]] = []
    total_bytes = 0
    started = time.monotonic()
    with httpx.Client(
        timeout=180.0,
        follow_redirects=True,
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
    ) as client:
        start_index = 0
        while True:
            page, received = fetch_page(
                client, url, start_index=start_index, count=page_size, version=version
            )
            features.extend(page)
            total_bytes += received
            print(
                f"  {start_index:>5} + {len(page):<4} -> {len(features):>5} districts, "
                f"{total_bytes / 1e6:.1f} MB",
                flush=True,
            )
            # The service answers ``numberMatched="unknown"`` whenever COUNT is
            # set, so a short page is the only end-of-list signal there is.
            if len(page) < page_size:
                break
            start_index += page_size
    print(f"  {time.monotonic() - started:.0f} s total", flush=True)
    return features


def to_entries(features: Iterable[dict[str, str]]) -> tuple[list[GemarkungEntry], dict[str, int]]:
    """Keep the Gemarkungen, count what else the layer held, drop duplicates."""

    kinds: dict[str, int] = {}
    entries: dict[str, GemarkungEntry] = {}
    for feature in features:
        art = feature.get("art") or "ohne Angabe"
        kinds[art] = kinds.get(art, 0) + 1
        if art != GEMARKUNG_ART:
            continue
        name, schluessel = feature.get("name"), feature.get("schluessel")
        if not name or not schluessel:
            continue
        # Keyed by the district key: a page boundary must not be able to put
        # the same district in twice.
        entries[schluessel] = GemarkungEntry(
            name=name, schluessel=schluessel, gemeinde=feature.get("gemeinde") or None
        )
    ordered = sorted(entries.values(), key=lambda entry: sort_key(entry.name))
    return ordered, kinds


def write_directory(entries: list[GemarkungEntry], out: Path, *, source: str) -> None:
    payload: dict[str, Any] = {
        # The day the list was pulled. Shown in the UI next to the picklist, so
        # a user can see how old the choice they are offered is.
        "stand": date.today().isoformat(),
        "erzeugt_am": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quelle": source,
        "lizenz": "GeoSN, dl-de/by-2-0",
        "anzahl": len(entries),
        "gemarkungen": [entry.as_dict() for entry in entries],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    print(f"\n{len(entries)} Gemarkungen -> {out} ({out.stat().st_size / 1e3:.0f} kB)")


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Build the directory served by GET /api/gemarkungen.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url",
        default=settings.alkis.wfs_url,
        help=f"ALKIS WFS endpoint (default: {settings.alkis.wfs_url}).",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUTPUT, help=f"Output file (default: {DEFAULT_OUTPUT})."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Features per request (default: {DEFAULT_PAGE_SIZE}).",
    )
    args = parser.parse_args(argv)

    print(f"Reading ave:KatasterBezirk from {args.url} …", flush=True)
    features = fetch_all(
        args.url,
        user_agent=settings.app.user_agent,
        page_size=args.page_size,
        version=settings.alkis.version,
    )
    entries, kinds = to_entries(features)
    if not entries:
        raise SystemExit("No feature of art 'Gemarkung' came back -- nothing written.")
    for art in sorted(kinds):
        print(f"  art={art}: {kinds[art]}")
    write_directory(entries, args.out, source=args.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
