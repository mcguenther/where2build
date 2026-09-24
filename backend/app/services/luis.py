"""LUIS Sachsen: the environmental record of one parcel.

Everything here is one ArcGIS REST server, ``luis.sachsen.de/arcgis``, which
carries noise, water, nature, soil, geology and radon for the whole state. It
is not the host the cadastre lives on -- parcels and base maps are on
``geodienste.sachsen.de`` -- and a guessed layer name on the wrong host answers
403, which reads like a block and is a wrong path.

Three rules shape this module, each of them measured rather than assumed:

* **Ask with the parcel outline, never with a point.** A plot straddles
  isophones: Moelkau 204 is ``Lden5054`` at the building point and
  ``Lden5054`` + ``Lden5559`` across its 650 m². The ring we already fetch from
  ALKIS goes in as ``esriGeometryPolygon``.
* **Use ``/<layer>/query``, never ``identify``.** ``identify`` measures its
  tolerance in *pixels* and demands a ``mapExtent`` the question is not about;
  at ``tolerance=3`` and a plausible extent, 3 px was about 7 m and the service
  reported a neighbouring polygon as a hit.
* **A zero answer is only "not affected" once a control point has shown the
  layer answering at all.** Verified on 05.09.2026: flood HQ100 is empty at
  Moelkau and returns "Vereinigte Mulde" at Grimma; the radon layer is empty at
  Moelkau and names Johanngeorgenstadt; the water-protection layer is empty at
  Moelkau and names a Dresden zone. Without that, "0 features" and "the layer
  is broken" look the same.

What this module does *not* do is decide what a finding says. It answers with
the survey's own categories -- ``Lden5559``, ``LK_IV``, a name and a distance
bracket -- and the sentence is composed in the browser from
``frontend/src/lib/findings.js``. A class key must never reach the interface
untranslated.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any, Iterable, Sequence

from shapely.geometry import Point, Polygon

from .. import geo
from ..cache import DiskCache
from ..errors import AppError, UpstreamError
from ..schemas import Ausweisung, Baugrund, Bohrung, Gebiet, Laerm
from ..settings import AppSettings, LuisSettings
from ..upstream import request

logger = logging.getLogger(__name__)

SERVICE_NAME = "Der Umweltdatendienst des Freistaats Sachsen (LUIS)"
PORTAL_URL = "https://www.umwelt.sachsen.de/umwelt/infosysteme/luis/"
ADVICE = (
    f"Die Standortprüfungen bleiben leer; unter {PORTAL_URL} lassen sich dieselben "
    "Karten von Hand ansehen. Fläche, Bodenrichtwert und Bebauungsplanung sind "
    "davon nicht betroffen."
)

# --------------------------------------------------------------------------
# The layer table
#
# Ids and names read from the services themselves on 05.09.2026. They are a
# domain table rather than configuration: swapping one for another is a change
# to what the check *means*, not to where it is deployed.
# --------------------------------------------------------------------------

NOISE_SERVICE = "laerm/laermkartierung"
# Keyed by the source of the noise, because that is what the finding names.
NOISE_LAYERS: dict[str, dict[str, int]] = {
    "tag": {"strasse": 4, "strassenbahn": 55, "flughafen": 37},
    "nacht": {"strasse": 5, "strassenbahn": 56, "flughafen": 36},
}
# The lowest band the road survey holds anywhere. It proves nothing about a
# plot in no band: Lden4549 exists only around Zwickau (4 266 polygons, all
# inside 12.42-12.57 E, 50.65-50.80 N, measured 24.09.2026), and the survey
# maps main roads only, so the street in front of such a plot is not in it.
NOISE_LOWEST_BAND_DB = 45
NOISE_SOURCE = "LfULG Umgebungslärmkartierung (Sachsen), Flurstücksumring"

WATER_SERVICE = "wasser/wasserschutzgebiete"
WATER_LAYERS = (0, 1, 2, 3)
WATER_SOURCE = "LfULG Wasserschutzgebiete, 4 Ebenen"

# Every category the state designates, so "in a protected area" is answered for
# all of them and not only for the two common ones.
PROTECTION_SERVICE = "natur/schutzgebiete"
PROTECTION_LAYERS: dict[int, str] = {
    0: "Biosphärenreservat",
    1: "Naturpark",
    2: "Flächennaturdenkmal",
    3: "Nationalpark",
    4: "Naturschutzgebiet",
    5: "Landschaftsschutzgebiet",
}
PROTECTION_SOURCE = "LfULG Schutzgebiete Sachsen"
# The rungs a distance may be reported between. A band is the honest answer:
# the service says whether something is within a radius, not how far away it
# is, and reporting "380 m" from a 400 m hit would be a number nobody measured.
PROTECTION_LADDER = (100, 200, 300, 400, 500, 750, 1000)

# Layer 0 of `hochwasserrisikogebiete` is the same trap as `Kartierungsgebiet`
# in the noise service: a polyline of watercourses, which no area query hits.
# The flood *extents* are these, and they go further than grundradar, which
# reports "HQ100 data not available" for Saxony.
FLOOD_SERVICE = "wasser/hochwassergefaehrdung"
FLOOD_LAYERS: dict[int, str] = {
    6: "Überschwemmungsgebiet HQ20/25",
    7: "Überschwemmungsgebiet HQ50",
    8: "Überschwemmungsgebiet HQ100",
    9: "Überschwemmungsgebiet HQ200/300",
    10: "Extremhochwassergebiet",
}
FLOOD_SOURCE = "LfULG Hochwassergefährdung (HQ20 bis Extremhochwasser)"

RADON_SERVICE = "luft/radonvorsorgegebiete"
RADON_LAYERS: dict[int, str] = {0: "Radonvorsorgegebiet"}
RADON_SOURCE = "LfULG Radonvorsorgegebiete nach § 121 StrlSchG"

SLOPE_SERVICE = "landwirtschaft/hangneigung_ausbringung"
SLOPE_LAYERS: dict[int, str] = {0: "Fläche über 20 % Neigung"}
SLOPE_SOURCE = "LfULG Hangneigungskulisse (Düngerecht)"

SOIL_SERVICE = "boden/bk50"
SOIL_LAYER = 0
# The air capacity class, whose legend the service publishes itself.
SOIL_PARAMETER_SERVICE = "boden/bodenkennwerte"
SOIL_PARAMETER_LAYER = 5
BOREHOLE_SERVICE = "geologie/bohrungen"
BOREHOLE_LAYER = 0
GROUND_SOURCE = "LfULG BK50, Bodenkennwerte und Aufschlussdatenbank"

# Field names as the services spell them.
_NAME_FIELDS = ("NAME", "GEBIETSNAME", "GEB_NAME", "BEZEICHNUNG")
_SOIL_TEXT_FIELD = "LEG_TXT"
_AIR_CAPACITY_FIELD = "LK_STUFE"
_BOREHOLE_EASTING = "RECHTSWERT_UTM"
_BOREHOLE_NORTHING = "HOCHWERT_UTM"
_BOREHOLE_DEPTH = "ENDTEUFE"
_BOREHOLE_LABEL = "AKBEZ"
_BOREHOLE_URL = "URL"


def _clockwise(ring: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """The ring the way ArcGIS reads an outer boundary: clockwise.

    ALKIS delivers counter-clockwise rings, and ArcGIS takes one of those for a
    *hole* -- a polygon that is nothing but a hole has no area to work with.
    Measured on 05.09.2026: Flurstück 263/7 in Mölkau (86 m², 5 points) makes
    every ``distance`` query on the borehole and protected-area layers answer
    ``{"code": 400, "message": ""}``; the same ring reversed answers with 114
    boreholes. Flurstück 204 (650 m²) survives either way, which is exactly what
    makes this worth doing centrally -- the fault shows on some parcels and not
    on others, and the empty error message says nothing about why.
    """

    points = list(ring)
    # Shoelace, in a right-handed frame: positive means counter-clockwise.
    twice_area = sum(
        points[i][0] * points[i + 1][1] - points[i + 1][0] * points[i][1]
        for i in range(len(points) - 1)
    )
    return points[::-1] if twice_area > 0 else points


def _name_of(attributes: dict[str, Any]) -> str | None:
    """The area's own name, whichever field this service keeps it in."""

    for field in _NAME_FIELDS:
        value = attributes.get(field)
        if isinstance(value, str) and value.strip():
            # Several services join two spellings of the same zone with a
            # semicolon; the first is the one the Verordnung uses.
            return value.split(";")[0].strip()
    return None


def _year_of(label: str | None) -> int | None:
    """The drilling year out of an Aufschluss label like ``B...22....1972``."""

    if not label:
        return None
    digits = "".join(character if character.isdigit() else " " for character in label).split()
    for token in reversed(digits):
        if len(token) == 4 and 1800 <= int(token) <= date.today().year:
            return int(token)
    return None


class LuisService:
    def __init__(self, settings: LuisSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "luis", ttl_s=settings.cache_ttl_s)

    # -- the one request shape -------------------------------------------

    async def _query(
        self,
        service: str,
        layer: int,
        ring: Sequence[tuple[float, float]],
        *,
        distance_m: float = 0,
        out_fields: str = "*",
        count_only: bool = False,
    ) -> dict[str, Any]:
        """One ``/<layer>/query`` against the parcel outline.

        POST rather than GET: a ring is long, and a field of 159 boundary
        points would put the request past what a URL may carry. The cache key
        is built from the parameters instead of from the URL for the same
        reason.
        """

        geometry = {
            "rings": [[[x, y] for x, y in _clockwise(ring)]],
            "spatialReference": {"wkid": self.settings.srid},
        }
        params = {
            "geometry": json.dumps(geometry, separators=(",", ":")),
            "geometryType": "esriGeometryPolygon",
            "inSR": str(self.settings.srid),
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "resultRecordCount": str(self.settings.max_features),
            "f": "json",
        }
        if distance_m:
            params["distance"] = str(distance_m)
            params["units"] = "esriSRUnit_Meter"
        if count_only:
            params["returnCountOnly"] = "true"
        else:
            params["outFields"] = out_fields

        key = f"{service}/{layer}/{distance_m}/{out_fields}/{count_only}/{params['geometry']}"
        cached = self.cache.get_json(key)
        if cached is not None:
            return cached

        response = await request(
            "POST",
            f"{self.settings.base_url}/{service}/MapServer/{layer}/query",
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.settings.timeout_s,
            user_agent=self.app_settings.user_agent,
            data=params,
        )
        try:
            answer = response.json()
        except ValueError as exc:  # pragma: no cover - a proxy page, not JSON
            raise UpstreamError(
                f"{SERVICE_NAME} hat keine verwertbare Antwort geliefert. {ADVICE}"
            ) from exc
        if "error" in answer:
            # ArcGIS reports its own failures with HTTP 200, so the status code
            # alone would have called this a success.
            message = (answer["error"] or {}).get("message") or "ohne Angabe"
            raise UpstreamError(
                f"{SERVICE_NAME} hat die Abfrage abgelehnt ({message}). {ADVICE}"
            )
        self.cache.set_json(key, answer)
        return answer

    async def _features(self, service: str, layer: int, ring, **kwargs) -> list[dict[str, Any]]:
        answer = await self._query(service, layer, ring, **kwargs)
        return [feature.get("attributes") or {} for feature in answer.get("features", [])]

    async def _count(self, service: str, layer: int, ring, **kwargs) -> int:
        answer = await self._query(service, layer, ring, count_only=True, **kwargs)
        return int(answer.get("count") or 0)

    # -- the checks -------------------------------------------------------

    async def _noise(self, ring) -> Laerm:
        """Noise, with the coverage question asked separately.

        A hit gives the bands. No hit is no value, whether or not the survey
        mapped something within the radius -- the radius only says how far the
        nearest mapped main road is. Measured: 109 road-noise polygons within
        300 m in Leipzig, 94 in Dresden, 0 in Geithain, and for the
        Bahnhofstraße in Naunhof none within 300 m but 30 within 2 km.
        """

        async def bands(period: str, source: str, layer: int) -> tuple[str, str, list[str]]:
            rows = await self._features(
                NOISE_SERVICE, layer, ring, out_fields="CATEGORY"
            )
            return period, source, [row["CATEGORY"] for row in rows if row.get("CATEGORY")]

        jobs = [
            bands(period, source, layer)
            for period, layers in NOISE_LAYERS.items()
            for source, layer in layers.items()
        ]
        results = await asyncio.gather(*jobs)

        found: dict[str, dict[str, list[str]]] = {"tag": {}, "nacht": {}}
        for period, source, categories in results:
            found[period][source] = categories

        # Only asked when nothing was found: with a hit, coverage is settled.
        mapped_nearby = any(found["tag"].values()) or any(found["nacht"].values())
        if not mapped_nearby:
            mapped_nearby = (
                await self._count(
                    NOISE_SERVICE,
                    NOISE_LAYERS["tag"]["strasse"],
                    ring,
                    distance_m=self.settings.noise_coverage_radius_m,
                )
                > 0
            )
        return Laerm(
            tag=found["tag"],
            nacht=found["nacht"],
            kartiert_umkreis=mapped_nearby,
            umkreis_m=self.settings.noise_coverage_radius_m,
            unterste_stufe_db=NOISE_LOWEST_BAND_DB,
            quelle=NOISE_SOURCE,
        )

    async def _designation(
        self,
        service: str,
        layers: dict[int, str] | Iterable[int],
        ring,
        *,
        quelle: str,
        with_distance: bool = False,
    ) -> Ausweisung:
        """Is the plot inside one of these areas -- and if not, how near is one?

        The distance is a *bracket*, because that is what the service can
        answer: it says whether anything lies within a radius, and the rungs of
        the ladder are the resolution. Reporting a single figure from a 400 m
        hit would state a measurement nobody made.
        """

        names: dict[int, str | None] = (
            dict(layers) if isinstance(layers, dict) else {layer: None for layer in layers}
        )

        hits = await asyncio.gather(
            *(self._features(service, layer, ring) for layer in names)
        )
        inside = [
            Gebiet(name=_name_of(row), kategorie=names[layer])
            for layer, rows in zip(names, hits)
            for row in rows
        ]
        if inside:
            return Ausweisung(betroffen=True, gebiete=inside, quelle=quelle)
        if not with_distance:
            return Ausweisung(betroffen=False, quelle=quelle)

        radius = self.settings.protection_radius_m
        near = await asyncio.gather(
            *(self._features(service, layer, ring, distance_m=radius) for layer in names)
        )
        candidates = [
            (layer, row) for layer, rows in zip(names, near) for row in rows
        ]
        if not candidates:
            return Ausweisung(betroffen=False, umkreis_m=radius, quelle=quelle)

        nearest_layer, band_from, band_to = await self._nearest_band(
            service, [layer for layer, _ in candidates], ring, radius
        )
        nearest = next(row for layer, row in candidates if layer == nearest_layer)
        return Ausweisung(
            betroffen=False,
            naechstes=Gebiet(name=_name_of(nearest), kategorie=names[nearest_layer]),
            abstand_von_m=band_from,
            abstand_bis_m=band_to,
            weitere_im_umkreis=len(candidates) - 1,
            umkreis_m=radius,
            quelle=quelle,
        )

    async def _nearest_band(
        self, service: str, layers: Sequence[int], ring, radius: float
    ) -> tuple[int, float | None, float]:
        """Walk the ladder down to the narrowest rung that still holds a hit.

        A binary search rather than a sweep: the ladder has seven rungs, so
        three requests settle it instead of seven.
        """

        rungs = [rung for rung in PROTECTION_LADDER if rung < radius]
        low, high = 0, len(rungs)
        hit_layer = layers[0]
        while low < high:
            middle = (low + high) // 2
            found = await asyncio.gather(
                *(
                    self._count(service, layer, ring, distance_m=rungs[middle])
                    for layer in layers
                )
            )
            if any(found):
                hit_layer = next(layer for layer, count in zip(layers, found) if count)
                high = middle
            else:
                low = middle + 1
        band_to = rungs[low] if low < len(rungs) else radius
        band_from = rungs[low - 1] if low else None
        return hit_layer, band_from, band_to

    async def _ground(self, ring) -> Baugrund:
        """Soil, its air capacity, and what has been drilled nearby.

        The soil map's own wording is precise and useless to a buyer; the grain
        sizes inside it are the practical part, and the browser classifies them.
        Nothing here says anything about bearing capacity -- a 1:50 000 soil map
        is not a ground investigation.
        """

        # Three separate facts, so three separate failures: a borehole query the
        # service refuses must not take the soil classification with it. Only an
        # upstream failure counts as a missing part -- a bug in here keeps
        # travelling rather than reading as "the authority did not answer".
        answers = await asyncio.gather(
            self._features(SOIL_SERVICE, SOIL_LAYER, ring, out_fields=_SOIL_TEXT_FIELD),
            self._features(
                SOIL_PARAMETER_SERVICE, SOIL_PARAMETER_LAYER, ring,
                out_fields=_AIR_CAPACITY_FIELD,
            ),
            self._features(
                BOREHOLE_SERVICE, BOREHOLE_LAYER, ring,
                distance_m=self.settings.borehole_radius_m,
            ),
            return_exceptions=True,
        )
        for answer in answers:
            if isinstance(answer, BaseException) and not isinstance(answer, AppError):
                raise answer
        soil, capacity, boreholes = [
            [] if isinstance(answer, BaseException) else answer for answer in answers
        ]
        # "0 boreholes" and "nobody answered" are different sentences.
        boreholes_answered = not isinstance(answers[2], BaseException)
        outline = Polygon(ring)
        near_radius = self.settings.borehole_near_radius_m

        measured: list[tuple[float, Bohrung]] = []
        for row in boreholes:
            easting, northing = row.get(_BOREHOLE_EASTING), row.get(_BOREHOLE_NORTHING)
            if not isinstance(easting, (int, float)) or not isinstance(northing, (int, float)):
                continue
            # Distance from the parcel's own edge, not from a centre: a plot is
            # an area, and a borehole at its boundary is not 20 m away.
            distance = outline.distance(Point(easting, northing))
            depth = row.get(_BOREHOLE_DEPTH)
            measured.append((
                distance,
                Bohrung(
                    entfernung_m=round(distance, 1),
                    endteufe_m=float(depth) if isinstance(depth, (int, float)) else None,
                    jahr=_year_of(row.get(_BOREHOLE_LABEL)),
                    url=row.get(_BOREHOLE_URL) or None,
                ),
            ))
        measured.sort(key=lambda entry: entry[0])
        with_depth = [entry for entry in measured if entry[1].endteufe_m]

        return Baugrund(
            bodenart_text=(soil[0].get(_SOIL_TEXT_FIELD) if soil else None) or None,
            luftkapazitaet_stufe=(capacity[0].get(_AIR_CAPACITY_FIELD) if capacity else None) or None,
            bohrungen_umkreis=len(measured),
            bohrungen_naher_umkreis=sum(1 for distance, _ in measured if distance <= near_radius),
            umkreis_m=self.settings.borehole_radius_m,
            naher_umkreis_m=near_radius,
            bohrungen_gefragt=boreholes_answered,
            naechste=measured[0][1] if measured else None,
            tiefste=(
                max(with_depth, key=lambda entry: entry[1].endteufe_m or 0)[1]
                if with_depth
                else None
            ),
            quelle=GROUND_SOURCE,
        )

    # -- the whole battery ------------------------------------------------

    async def site_checks(self, ring_wgs84: Sequence[Sequence[float]]) -> dict[str, Any]:
        """Every check this server can answer, for one parcel outline.

        The checks run together and fail apart: a service that is down costs
        its own row, not the page. Each block therefore carries either data or
        a German ``fehler``, and the interface shows the second as an open
        check rather than as a green one.

        Answers with the blocks rather than the whole document: air quality
        comes from another authority entirely, and the router puts the two
        together.
        """

        ring = [geo.wgs84_to_utm33(lon, lat) for lon, lat in ring_wgs84]

        jobs = {
            "laerm": self._noise(ring),
            "trinkwasserschutz": self._designation(
                WATER_SERVICE, WATER_LAYERS, ring, quelle=WATER_SOURCE
            ),
            "schutzgebiet": self._designation(
                PROTECTION_SERVICE, PROTECTION_LAYERS, ring,
                quelle=PROTECTION_SOURCE, with_distance=True,
            ),
            "hochwasser": self._designation(
                FLOOD_SERVICE, FLOOD_LAYERS, ring, quelle=FLOOD_SOURCE
            ),
            "radon": self._designation(
                RADON_SERVICE, RADON_LAYERS, ring, quelle=RADON_SOURCE
            ),
            "hangneigung": self._designation(
                SLOPE_SERVICE, SLOPE_LAYERS, ring, quelle=SLOPE_SOURCE
            ),
            "baugrund": self._ground(ring),
        }
        empty = {
            "laerm": lambda message: Laerm(
                umkreis_m=self.settings.noise_coverage_radius_m,
                unterste_stufe_db=NOISE_LOWEST_BAND_DB,
                quelle=NOISE_SOURCE,
                fehler=message,
            ),
            "trinkwasserschutz": lambda message: Ausweisung(quelle=WATER_SOURCE, fehler=message),
            "schutzgebiet": lambda message: Ausweisung(quelle=PROTECTION_SOURCE, fehler=message),
            "hochwasser": lambda message: Ausweisung(quelle=FLOOD_SOURCE, fehler=message),
            "radon": lambda message: Ausweisung(quelle=RADON_SOURCE, fehler=message),
            "hangneigung": lambda message: Ausweisung(quelle=SLOPE_SOURCE, fehler=message),
            "baugrund": lambda message: Baugrund(
                umkreis_m=self.settings.borehole_radius_m,
                naher_umkreis_m=self.settings.borehole_near_radius_m,
                quelle=GROUND_SOURCE,
                fehler=message,
            ),
        }

        answered = await asyncio.gather(*jobs.values(), return_exceptions=True)
        blocks: dict[str, Any] = {}
        for name, result in zip(jobs, answered):
            if isinstance(result, AppError):
                logger.warning("LUIS check %s failed: %s", name, result.message)
                blocks[name] = empty[name](result.message)
            elif isinstance(result, BaseException):
                raise result
            else:
                blocks[name] = result

        return blocks
