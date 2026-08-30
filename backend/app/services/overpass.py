"""Live OpenStreetMap queries through an Overpass instance -- the prototype
source for the six categories the local index otherwise answers.

The offline index (``scripts/build_poi_index.py``) stays the production answer.
This module exists so the feature is complete on a machine where that build has
never run, and it is **off unless ``OVERPASS_ENABLED`` is set.**

What the Overpass manual actually asks for (fetched 2026-08-29 from
``dev.overpass-api.de/overpass-doc/en/preface/commons.html``, quoted in
``docs/research/poi.md`` § 2.2):

* "Setting up an app for more than just OSM mappers and relying on the public
  instances as backend" is listed under *problematic behaviour*, and "only
  running your own instance sustainably serves your mission".
* "As a broad guideline to stay within safety margins, users are expected to
  send a maximum of about 10000 requests per day and keep their download volume
  below about 1 GB per day."
* "It is extremely unlikely that you will ever cause problems with manually put
  requests."
* Rate limiting is per IP address, by execution slots with a cooldown, and a
  request "stays enqueued up to 15 seconds" while it waits for one.

A single-user prototype issuing at most one query per view of a plot, behind a
30-day cache, is inside those numbers by three orders of magnitude. An app with
users is not, and no amount of caching changes that -- the shape of the usage is
what the policy objects to. Hence: opt-in, one query per request, a hard cache,
and ``OVERPASS_URL`` so pointing at a self-hosted instance is a settings change.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Sequence

from ..cache import DiskCache
from ..errors import UpstreamError
from ..poi_index import INCLUDE, PoiEntry, PoiIndex, categorise
from ..schemas import Koordinate
from ..settings import AppSettings, OverpassSettings
from ..upstream import request

logger = logging.getLogger(__name__)

SERVICE_NAME = "Der OpenStreetMap-Dienst (Overpass)"

# Every failure here costs the six OSM categories and nothing else, so the
# advice says exactly that -- and names the way out of depending on a public
# instance at all.
ADVICE = (
    "Haltestellen, Bahnhöfe und die Gehzeiten kommen aus dem Fahrplandienst und "
    "sind davon nicht betroffen. Dauerhaft unabhängig wird die Umgebungssuche "
    "mit einem eigenen Verzeichnis (python scripts/build_poi_index.py --download) "
    "oder einer eigenen Overpass-Instanz (OVERPASS_URL)."
)

# 429 is the documented answer when the caller is over its slot quota; the
# instances hand slots out per IP address, so ours is shared by everything this
# server does. 504 comes from the gateway in front of a busy instance.
STATUS_HINTS = {
    429: (
        "Der Overpass-Dienst hat die Anfrage wegen zu vieler Zugriffe abgewiesen "
        "(HTTP 429). Die öffentlichen Instanzen begrenzen je IP-Adresse; in "
        "einigen Minuten klappt es meist wieder."
    ),
    504: (
        "Der Overpass-Dienst war überlastet und hat die Anfrage nicht "
        "rechtzeitig beantwortet (HTTP 504)."
    ),
}

# Under load Overpass answers HTTP 200 with an empty `elements` array and says
# what went wrong in `remark`: "runtime error: Query timed out in \"query\" at
# line 1 after 26 seconds." Reading that as "nichts gefunden" would be the worst
# possible failure mode -- it is the answer this endpoint exists to avoid.
RUNTIME_ERROR = (
    "Der Overpass-Dienst hat die Abfrage abgebrochen ({remark}). Ein kleinerer "
    "Umkreis oder ein erneuter Versuch in einigen Minuten hilft meist."
)

# What a Saxon `overpass turbo` user would write by hand. `nwr` covers nodes,
# ways and relations; `center` gives the areas among them the one representative
# coordinate a "how far is it" question needs, and `tags` drops the node id list
# `body` would otherwise send for every way -- the download volume the usage
# policy asks callers to keep down. The recorded answer in
# tests/fixtures/overpass_liebertwolkwitz.json is a real overpass-api.de
# response in exactly this shape: 28 ways, each with `center` and `tags` and no
# geometry.
_QUERY = "[out:json][timeout:{timeout}];({body});out tags center;"

# How an element's type maps onto the id prefix the index and the UI use.
_OSM_PREFIX = {"node": "N", "way": "W", "relation": "R"}


def build_query(
    kategorien: Sequence[str], lat: float, lon: float, radius_m: int, timeout_s: int
) -> str:
    """One Overpass QL query covering every requested category.

    One query, not one per category: the policy counts requests, and a union
    block costs the server a single execution slot.
    """

    filters: list[str] = []
    for kategorie in kategorien:
        for key, value in INCLUDE.get(kategorie, ()):
            filters.append(f'nwr["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    return _QUERY.format(timeout=int(timeout_s), body="".join(filters))


def _coordinate(element: dict[str, Any]) -> tuple[float, float] | None:
    """A node's own position, or the centre `out center` computed for an area."""

    lat, lon = element.get("lat"), element.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        centre = element.get("center")
        if not isinstance(centre, dict):
            return None
        lat, lon = centre.get("lat"), centre.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return None
    return float(lat), float(lon)


def entries_from_elements(elements: Iterable[Any]) -> list[PoiEntry]:
    """Overpass elements -> the same ``PoiEntry`` the offline build writes.

    Categorised with the shared mapping, so an object excluded from the extract
    -- a driving school, a front garden tagged `leisure=garden`, a playground
    behind a fence -- is excluded here too.
    """

    entries: list[PoiEntry] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags")
        if not isinstance(tags, dict):
            continue
        match = categorise({str(key): str(value) for key, value in tags.items()})
        if match is None:
            continue
        position = _coordinate(element)
        if position is None:
            continue
        kategorie, art = match
        prefix = _OSM_PREFIX.get(str(element.get("type")))
        entries.append(
            PoiEntry(
                kategorie=kategorie,
                lat=round(position[0], 6),
                lon=round(position[1], 6),
                name=str(tags.get("name") or "").strip() or None,
                art=art,
                osm_id=f"{prefix}{element.get('id')}" if prefix else None,
            )
        )
    return entries


class OverpassService:
    """One cached Overpass query per request, or nothing at all."""

    def __init__(self, settings: OverpassSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "overpass", ttl_s=settings.cache_ttl_s)
        self._semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.url)

    def _query_area(self, origin: Koordinate, radius_m: int) -> tuple[float, float, int]:
        """Centre and radius the query actually uses, rounded for the cache.

        Two plots in the same street must share one cached answer, so the centre
        is rounded to ~110 m and the radius up to the next full step. The margin
        covers the rounding, and the true air distance is measured against the
        real origin afterwards -- the query is only a pre-filter.
        """

        precision = max(0, self.settings.origin_precision)
        step = max(1, self.settings.radius_step_m)
        rounded_radius = -(-max(1, radius_m) // step) * step
        return (
            round(origin.lat, precision),
            round(origin.lon, precision),
            rounded_radius + max(0, self.settings.origin_margin_m),
        )

    async def places(
        self, origin: Koordinate, radius_m: int, kategorien: Sequence[str]
    ) -> PoiIndex:
        """The wanted places around a point, as an index the caller can search.

        Returns the same ``PoiIndex`` the offline build produces, so ranking,
        the 60 m deduplication and the grid lookup behave identically whichever
        source answered.
        """

        wanted = sorted({kategorie for kategorie in kategorien if kategorie in INCLUDE})
        if not wanted:
            return PoiIndex([], quelle=self.settings.url)

        lat, lon, radius = self._query_area(origin, radius_m)
        query = build_query(wanted, lat, lon, radius, self.settings.query_timeout_s)
        cache_key = f"overpass:{self.settings.url}:{query}"

        payload = self.cache.get_json(cache_key)
        if payload is None:
            async with self._semaphore:
                response = await request(
                    "POST",
                    self.settings.url,
                    service=SERVICE_NAME,
                    advice=ADVICE,
                    status_hints=STATUS_HINTS,
                    timeout_s=self.settings.timeout_s,
                    # The manual asks for no particular User-Agent, unlike
                    # Transitous and the OSM API. Send the app's own anyway, so
                    # the traffic is attributable -- but not the contact
                    # address, which no policy here asks for.
                    user_agent=self.app_settings.user_agent,
                    data={"data": query},
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {ADVICE}"
                ) from exc
            self._raise_on_remark(payload)
            # Only a complete answer is worth keeping for 30 days.
            self.cache.set_json(cache_key, payload)
        else:
            self._raise_on_remark(payload)

        elements = payload.get("elements") if isinstance(payload, dict) else None
        entries = entries_from_elements(elements or [])
        return PoiIndex(
            entries,
            datenstand=self._datenstand(payload),
            quelle=self.settings.url,
        )

    @staticmethod
    def _raise_on_remark(payload: Any) -> None:
        """Turn Overpass' in-band error into an error, not into "nichts gefunden"."""

        remark = payload.get("remark") if isinstance(payload, dict) else None
        if not isinstance(remark, str) or not remark.strip():
            return
        if "error" in remark.casefold():
            raise UpstreamError(f"{RUNTIME_ERROR.format(remark=remark.strip())} {ADVICE}")
        # Anything else is a note about the query, not a failure of it.
        logger.info("Overpass remark: %s", remark.strip())

    @staticmethod
    def _datenstand(payload: Any) -> str | None:
        """`timestamp_osm_base` -- how current the answering instance's data is."""

        osm3s = payload.get("osm3s") if isinstance(payload, dict) else None
        stand = osm3s.get("timestamp_osm_base") if isinstance(osm3s, dict) else None
        return str(stand) if stand else None

    def status(self) -> dict[str, Any]:
        """What ``/api/health`` reports about this source."""

        return {"aktiv": self.enabled, "endpunkt": self.settings.url}


__all__ = ["OverpassService", "build_query", "entries_from_elements"]
