"""RAPIS Sachsen: which Bauleitplanung the plot lies in, according to the state.

RAPIS is the Landesdirektion's planning register, served as an open ArcGIS
REST server. It holds the *area* of every plan it knows and the Art der
Nutzung inside it -- never Baugrenzen, GRZ or storeys. What it can answer is a
yes or a no per layer, and that is all this module asks it.

Measured on 25.09. and 30.09.2026 (docs/research/bebauungsplaene-sachsen.md):

* **The layer numbers are not the WMS's.** WMS layer "4 Satzungsbereiche" is
  REST layer 5; REST layer 4 answers 404.
* **``WFS_BPLAN`` is the wrong service.** Its "in Kraft" layers answer
  ``count: 0`` statewide; ``WMS_BPLAN`` is the one with the data.
* **Layer 5 mixes statuses and sub-areas.** Statutes in force and in
  procedure share it, and one statute arrives as several records (the
  statute's area plus a "Verkehrsfläche" or an "überbaubare Grundstücksfläche"
  inside it), so records are grouped by plan before they are reported.
* **The plan layers carry statutes too.** Layer 3 holds 1 427 records with
  PLANTYP "SATZ", E-276 in Gundorf among them, which layer 5 returns as well.
  PLANTYP alone does not tell them apart -- "SATZ" also marks § 8 and § 13
  plans -- so a plan is reported as a statute when layer 5 returned it too.
* **RAPIS is not complete.** Two of eight Leipzig plans in Mölkau are missing
  from it. An empty answer is "no known plan", and the response says so.

The one rule this module adds: **a failure is never an empty list.** If any
layer cannot be asked, the whole answer fails with a German ``detail``. A
partial answer with an empty ``bebauungsplaene`` would read as "kein
Bebauungsplan" -- the one sentence an error must not turn into.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from .. import geo
from ..cache import DiskCache
from ..errors import UpstreamError
from ..schemas import Bauleitplan, Flaechennutzungsplan, PlanungResponse
from ..settings import AppSettings, RapisSettings
from ..upstream import request
from .luis import _clockwise

SERVICE_NAME = "Das Raumplanungsinformationssystem Sachsen (RAPIS)"

# Domain table, read from the services on 30.09.2026. A different layer is a
# different question, not a different deployment, so these are not settings.
BPLAN_SERVICE = "WMS_BPLAN"
LAYER_IN_FORCE = 3
LAYER_IN_FORCE_USES = 2
LAYER_PLANNED = 1
LAYER_PLANNED_USES = 0
LAYER_STATUTES = 5
FNP_SERVICE = "RO_FNP_wirksam"
LAYER_FNP = 1

# The label layer 5 gives the statute's own area; every other THEMA_DET on that
# layer is a sub-area inside it and is worth reporting.
_STATUTE_AREA = "Satzungsgebiet nach §§34, 35 BauGB"
_IN_FORCE = "rechtskräftig"
# The layers declare ``dateFieldsTimeReference: Europe/Berlin``: a date is
# local midnight sent as epoch milliseconds, and read in UTC it is a day early.
# The FNP shows it -- dat_bekann read in UTC is 15.05.2015, its own info_vg
# says "wirksam 16.05.2015".
_LOCAL = ZoneInfo("Europe/Berlin")
_RAPIS_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def _text(value: Any) -> str | None:
    """RAPIS writes a single blank for an empty text field."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _date(value: Any) -> date | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=_LOCAL).date()
    return None


def _upload_date(value: Any) -> date | None:
    """``'LD Sachsen, ROK 28.09.2026, letzter RAPIS-Upload'`` -> 2026-09-28."""

    match = _RAPIS_DATE.search(value) if isinstance(value, str) else None
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _plan_key(attributes: dict[str, Any]) -> Any:
    """What identifies one plan across its polygons and its use records."""

    return attributes.get("ROK_NR") or attributes.get("rok_nr") or _text(
        attributes.get("NAME") or attributes.get("name")
    )


def _unique(values: Sequence[str | None]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _plans(
    records: list[dict[str, Any]],
    uses: list[dict[str, Any]],
    *,
    status: str | None = None,
) -> list[Bauleitplan]:
    """One entry per plan, with the uses that touch the plot attached.

    ``status`` fixes the status for a layer that means one thing; ``None``
    reads it off each record, which is what the mixed statute layer needs.
    """

    uses_by_plan: dict[Any, list[str | None]] = {}
    for use in uses:
        uses_by_plan.setdefault(_plan_key(use), []).append(_text(use.get("THEMA_DET")))

    grouped: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        if _text(record.get("NAME")) is None:
            continue
        grouped.setdefault(_plan_key(record), []).append(record)

    plans: list[Bauleitplan] = []
    for key, group in grouped.items():
        first = group[0]
        verfahrensstand = _text(first.get("STATUS"))
        details = [
            _text(record.get("THEMA_DET"))
            for record in group
            if _text(record.get("THEMA_DET")) != _STATUTE_AREA
        ]
        plans.append(
            Bauleitplan(
                name=_text(first.get("NAME")),
                status=status
                or ("in Kraft" if verfahrensstand == _IN_FORCE else "im Verfahren"),
                verfahrensstand=verfahrensstand,
                rechtsgrundlage=_text(first.get("RECHTSGRL")),
                plantyp=_text(first.get("PLANTYP")),
                gemeinde=_text(first.get("GEMEINDE")),
                standort=_text(first.get("STANDORT")),
                art_der_nutzung=_unique(uses_by_plan.get(key, []) + details),
                planstand=_text(first.get("PLAN")),
                genehmigt_am=_date(first.get("DAT_GENEHM")),
                bekanntgemacht_am=_date(first.get("DAT_BEKANN")),
                info=_text(first.get("INFO_VG")),
                rok_nr=first.get("ROK_NR"),
            )
        )
    return plans


def _land_use_plans(records: list[dict[str, Any]]) -> list[Flaechennutzungsplan]:
    """One entry per FNP. Its fields are spelt in lower case, unlike the B-Plans'."""

    grouped: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        if _text(record.get("name")) is None:
            continue
        grouped.setdefault(_plan_key(record), []).append(record)
    return [
        Flaechennutzungsplan(
            name=_text(group[0].get("name")),
            darstellungen=_unique([_text(record.get("thema_det")) for record in group]),
            gemeinde=_text(group[0].get("gemeinde")),
            bekanntgemacht_am=_date(group[0].get("dat_bekann")),
            info=_text(group[0].get("info_vg")),
        )
        for group in grouped.values()
    ]


class RapisService:
    def __init__(self, settings: RapisSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "rapis", ttl_s=settings.cache_ttl_s)

    @property
    def advice(self) -> str:
        return (
            "Ob hier ein Bebauungsplan gilt, bleibt damit offen — nachsehen lässt es "
            f"sich unter {self.settings.portal_url}, verbindlich beantwortet es die "
            "Gemeinde."
        )

    def _geometry(self, ring: Sequence[Sequence[float]]) -> str:
        """The outline as Esri JSON in the service's own CRS, clockwise.

        Rounded to the millimetre so the same plot always makes the same cache
        key, whatever float noise the browser's projection left in it.
        """

        projected = [geo.wgs84_to_utm33(lon, lat) for lon, lat in ring]
        points = [[round(x, 3), round(y, 3)] for x, y in _clockwise(projected)]
        if points[0] != points[-1]:
            points.append(points[0])
        return json.dumps(
            {"rings": [points], "spatialReference": {"wkid": self.settings.srid}},
            separators=(",", ":"),
        )

    def cache_key(self, service: str, layer: int, geometry: str) -> str:
        return f"{service}/{layer}/{geometry}"

    async def _query(self, service: str, layer: int, geometry: str) -> list[dict[str, Any]]:
        """The attributes of every record on one layer that touches the plot.

        POST, because a plot of several parcels has a long ring. An answer is
        cached only once it has been read as a real answer: an ArcGIS error
        arrives with HTTP 200, and caching that would make a passing fault
        into a week of "kein Plan".
        """

        key = self.cache_key(service, layer, geometry)
        answer = self.cache.get_json(key)
        if answer is None:
            response = await request(
                "POST",
                f"{self.settings.base_url}/{service}/MapServer/{layer}/query",
                service=SERVICE_NAME,
                advice=self.advice,
                timeout_s=self.settings.timeout_s,
                user_agent=self.app_settings.user_agent,
                data={
                    "geometry": geometry,
                    "geometryType": "esriGeometryPolygon",
                    "inSR": str(self.settings.srid),
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "*",
                    "returnGeometry": "false",
                    "f": "json",
                },
            )
            try:
                answer = response.json()
            except ValueError as exc:
                raise UpstreamError(
                    f"{SERVICE_NAME} hat keine verwertbare Antwort geliefert. {self.advice}"
                ) from exc
            if not isinstance(answer, dict):
                answer = {"error": {}}
            if "error" in answer:
                message = (answer["error"] or {}).get("message")
                raise UpstreamError(
                    f"{SERVICE_NAME} hat die Abfrage abgelehnt ({message or 'ohne Angabe'}). "
                    f"{self.advice}"
                )
            # No `features` at all is not the same as an empty list of them.
            if not isinstance(answer.get("features"), list):
                raise UpstreamError(
                    f"{SERVICE_NAME} hat eine Antwort ohne Treffermenge geliefert. "
                    f"{self.advice}"
                )
            self.cache.set_json(key, answer)
        return [feature.get("attributes") or {} for feature in answer["features"]]

    async def planning(self, ring: Sequence[Sequence[float]]) -> PlanungResponse:
        geometry = self._geometry(ring)
        in_force, in_force_uses, planned, planned_uses, statutes, fnp = await asyncio.gather(
            self._query(BPLAN_SERVICE, LAYER_IN_FORCE, geometry),
            self._query(BPLAN_SERVICE, LAYER_IN_FORCE_USES, geometry),
            self._query(BPLAN_SERVICE, LAYER_PLANNED, geometry),
            self._query(BPLAN_SERVICE, LAYER_PLANNED_USES, geometry),
            self._query(BPLAN_SERVICE, LAYER_STATUTES, geometry),
            self._query(FNP_SERVICE, LAYER_FNP, geometry),
        )

        uploads = [
            _upload_date(record.get("DAT_RAPIS") or record.get("dat_rapis"))
            for record in (*in_force, *in_force_uses, *planned, *planned_uses, *statutes, *fnp)
        ]
        known = [day for day in uploads if day is not None]
        datenstand = max(known) if known else None

        # Reported once, as what layer 5 says it is -- never dropped.
        statute_keys = {_plan_key(record) for record in statutes}
        in_force = [record for record in in_force if _plan_key(record) not in statute_keys]
        planned = [record for record in planned if _plan_key(record) not in statute_keys]

        return PlanungResponse(
            bebauungsplaene=_plans(in_force, in_force_uses, status="in Kraft")
            + _plans(planned, planned_uses, status="im Verfahren"),
            satzungen=_plans(statutes, []),
            fnp=_land_use_plans(fnp),
            datenstand=datenstand,
            quelle=(
                f"RAPIS Sachsen {datenstand:%m/%Y}" if datenstand else "RAPIS Sachsen"
            )
            + ", Landesdirektion Sachsen — dl-de/by-2-0",
            quelle_url=self.settings.portal_url,
        )
