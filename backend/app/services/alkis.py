"""ALKIS WFS of the GeoSN: parcels by point, by cadastral identifier, by parcel key.

Two traps this module works around, both live-verified in
``docs/research/geodaten-sachsen.md``:

* every stored query except ``GetFeatureById`` requires the ``CRS`` parameter,
* ad-hoc ``fes:Filter`` must reference attributes with the ``ave:`` prefix.

Both failures come back as the same generic HTML 400 page, so parsing the
error text is pointless -- the request has to be right in the first place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from .. import geo
from ..cache import DiskCache
from ..errors import NotFoundError, UpstreamError
from ..schemas import (
    GrundstueckFeature,
    GrundstueckProperties,
    ParcelCollection,
    ParcelFeature,
    ParcelProperties,
    Plausibility,
)
from ..settings import AlkisSettings, AppSettings
from ..upstream import request

AVE_NS = "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/2.0"
SERVICE_NAME = "Der Katasterdienst (ALKIS) des GeoSN"
# Appended to every ALKIS failure: the parcel is the one thing a user can
# supply without us.
ADVICE = (
    "Das Flurstück lässt sich auch von Hand eintragen: Fläche und Grenzen "
    "stehen im Kaufvertrag oder im Auszug aus dem Liegenschaftskataster."
)

STORED_QUERY_BY_KENNZEICHEN = (
    "http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/flst-by-kennzeichen"
)

# Attributes carried over from ave:GebaeudeBauwerk. No height and no storeys:
# the simplified ALKIS carries neither, which is why only § 6's 3 m floor is
# computable -- the same limit OSM has, from an official register.
_BUILDING_FIELDS = ("lagebeztxt", "funktion", "gebnutzbez", "aktualit")

# Attributes carried over from ave:Flurstueck.
_TEXT_FIELDS = (
    "flstkennz",
    "gemarkung",
    "gemaschl",
    "flur",
    "flstnrzae",
    "flstnrnen",
    "lagebeztxt",
    "gemeinde",
    "gmdschl",
    "kreis",
    "aktualit",
    "flaeche",
    # The actual land use with its area share -- "Wohnbaufläche;502" for a
    # building plot, "Straßenverkehr;1062" for a carriageway. It rides along
    # with every feature and the search reads it; see app/search/scoring.py.
    "tntxt",
)


# Saxony's Land prefix in the six-digit Gemarkungsschlüssel. Verified against
# the service on 29.08.2026: all 5 339 ``ave:KatasterBezirk`` features of art
# "Gemarkung" carry a six-digit ``schluessel``, every one of them starting
# with 14, and their four-digit tails are all distinct -- so expanding a short
# key is unambiguous.
LAND_PREFIX = "14"
GEMARKUNG_NUMBER_LENGTH = 4


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def expand_gemarkung_key(value: str) -> str:
    """A short cadastral district number to the six-digit key ALKIS stores.

    The Geoportal prints the same district two ways: its 'Gemarkung' layer
    shows the full key (Moritzburg: 143044), its 'Flurstueck' layer shows only
    the four-digit Gemarkungsnummer out of the parcel key (3044). A user
    reading the second one has no way to know the first exists, so the short
    form is expanded here rather than answering 404.

    Expanded up front instead of retried after an empty result: no six-digit
    key can be confused with a short one -- they all start with 14 -- so there
    is nothing to disambiguate and no reason to spend a request finding out.

    Numbers below four digits are zero-padded. The service always presents the
    four digits padded ('0101' for Borna, 183 of 5 339 districts start with a
    zero), but a key that has been through a spreadsheet or a number field has
    lost the padding, and no valid Gemarkungsnummer is below 0101 -- so padding
    can only ever turn a dead input into the right one.
    """

    key = value.strip()
    if not key.isdigit() or len(key) > GEMARKUNG_NUMBER_LENGTH:
        return key
    return LAND_PREFIX + key.zfill(GEMARKUNG_NUMBER_LENGTH)


def _axis_swapped(srs_name: str | None) -> bool:
    """True when the CRS states latitude before longitude.

    Geographic CRS in URN notation (``urn:ogc:def:crs:EPSG::4326``) are
    latitude-first; the projected ones we ask for are not.
    """

    if not srs_name:
        return False
    return any(code in srs_name for code in ("::4326", "::4258", "CRS84", "CRS:84"))


def _coords(text: str, swap: bool) -> list[tuple[float, float]]:
    numbers = [float(value) for value in text.split()]
    if len(numbers) % 2:
        raise UpstreamError(
            f"{SERVICE_NAME} hat eine unvollständige Geometrie geliefert. {ADVICE}"
        )
    pairs = list(zip(numbers[0::2], numbers[1::2]))
    return [(b, a) for a, b in pairs] if swap else pairs


def _ring_coords(ring_parent: ElementTree.Element, swap: bool) -> list[tuple[float, float]]:
    for element in ring_parent.iter():
        name = _local(element.tag)
        if name == "posList" and element.text:
            return _coords(element.text, swap)
        if name == "coordinates" and element.text:
            # GML 2 style, "x,y x,y"
            pairs = [tuple(float(v) for v in token.split(",")[:2]) for token in element.text.split()]
            return [(b, a) for a, b in pairs] if swap else pairs  # type: ignore[misc]
    positions: list[tuple[float, float]] = []
    for element in ring_parent.iter():
        if _local(element.tag) == "pos" and element.text:
            positions.extend(_coords(element.text, swap))
    return positions


def _parse_polygon(polygon_element: ElementTree.Element, swap: bool) -> Polygon | None:
    exterior: list[tuple[float, float]] = []
    interiors: list[list[tuple[float, float]]] = []
    for child in polygon_element:
        name = _local(child.tag)
        if name in ("exterior", "outerBoundaryIs"):
            exterior = _ring_coords(child, swap)
        elif name in ("interior", "innerBoundaryIs"):
            ring = _ring_coords(child, swap)
            if len(ring) >= 4:
                interiors.append(ring)
    if len(exterior) < 4:
        return None
    return Polygon(exterior, interiors)


def _parse_geometry(feature: ElementTree.Element, default_srs: str | None) -> Polygon | MultiPolygon:
    srs_name = default_srs
    for element in feature.iter():
        candidate = element.get("srsName")
        if candidate:
            srs_name = candidate
            break
    swap = _axis_swapped(srs_name)

    polygons: list[Polygon] = []
    for element in feature.iter():
        if _local(element.tag) == "Polygon":
            polygon = _parse_polygon(element, swap)
            if polygon is not None and not polygon.is_empty:
                polygons.append(polygon)
    if not polygons:
        raise UpstreamError(
            f"{SERVICE_NAME} hat ein Flurstück ohne Geometrie geliefert. {ADVICE}"
        )
    # A single ring stays a Polygon; only genuinely split parcels become multi.
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.rstrip("Z")[:10])
    except ValueError:
        return None


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        return None


@dataclass
class Flurstueck:
    """One ALKIS parcel, geometry still in the source CRS (EPSG:25833)."""

    gml_id: str | None
    attributes: dict[str, str] = field(default_factory=dict)
    geometry: Any = None

    @property
    def flaeche_amtlich_m2(self) -> float | None:
        """The official area from the ``flaeche`` attribute.

        Never the polygon area: the two differ by a few square metres as a
        rule, and the price comparison has to use the official number.
        """

        return _as_float(self.attributes.get("flaeche"))


def parse_feature_collection(xml: bytes | str) -> list[Flurstueck]:
    """Turn a WFS GetFeature GML response into parcels."""

    try:
        root = ElementTree.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise UpstreamError(f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}") from exc

    if _local(root.tag) in ("ServiceExceptionReport", "ExceptionReport", "html"):
        raise UpstreamError(f"{SERVICE_NAME} hat die Anfrage abgelehnt. {ADVICE}")

    default_srs = root.get("srsName")
    parcels: list[Flurstueck] = []
    for element in root.iter():
        if _local(element.tag) != "Flurstueck":
            continue
        attributes: dict[str, str] = {}
        for child in element:
            name = _local(child.tag)
            if name in _TEXT_FIELDS and child.text is not None:
                attributes[name] = child.text.strip()
        parcels.append(
            Flurstueck(
                gml_id=next(
                    (v for k, v in element.attrib.items() if _local(k) == "id"),
                    None,
                ),
                attributes=attributes,
                geometry=_parse_geometry(element, default_srs),
            )
        )
    return parcels


def parse_buildings(xml: bytes | str) -> list[dict[str, object]]:
    """A GetFeature answer for ``ave:GebaeudeBauwerk`` -> outlines in WGS84.

    The rings are closed here so no caller has to wonder whether they are, and
    the geometry travels as `[lon, lat]` because that is what the drawing wants.
    """

    try:
        root = ElementTree.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise UpstreamError(f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}") from exc
    if _local(root.tag) in ("ServiceExceptionReport", "ExceptionReport", "html"):
        raise UpstreamError(f"{SERVICE_NAME} hat die Anfrage abgelehnt. {ADVICE}")

    default_srs = root.get("srsName")
    buildings: list[dict[str, object]] = []
    for element in root.iter():
        if _local(element.tag) != "GebaeudeBauwerk":
            continue
        attributes = {
            _local(child.tag): (child.text or "").strip()
            for child in element
            if _local(child.tag) in _BUILDING_FIELDS and child.text
        }
        try:
            geometry = _parse_geometry(element, default_srs)
        except UpstreamError:
            # One outline without geometry is not a reason to lose the street.
            continue
        wgs84 = geo.reproject_geometry(geometry, geo.UTM33, geo.WGS84)
        # A building in two parts is rare and this is a hint: the larger part
        # is the outline worth drawing.
        outline = wgs84 if wgs84.geom_type == "Polygon" else max(wgs84.geoms, key=lambda g: g.area)
        ring = [[round(x, 7), round(y, 7)] for x, y in outline.exterior.coords]
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        buildings.append({
            "id": next((v for k, v in element.attrib.items() if _local(k) == "id"), None)
            or attributes.get("lagebeztxt", "")
            or "unbekannt",
            "umriss": ring,
            "adresse": attributes.get("lagebeztxt"),
            "funktion": attributes.get("funktion"),
            "aktualitaet": attributes.get("aktualit"),
        })
    return buildings


def to_collection(
    parcels: Iterable[Flurstueck],
    hinweis: str | None = None,
    plausibility: Plausibility | None = None,
) -> ParcelCollection:
    """Build the API answer: every parcel plus their union.

    A plot is a set of parcels -- geometries are unioned and the *official*
    areas summed. The computed area travels along for shape analysis only.
    """

    parcels = list(parcels)
    if not parcels:
        raise NotFoundError(
            "Zu dieser Angabe wurde kein Flurstück gefunden. Bitte Gemarkung und "
            "Flurstücksnummer prüfen (Schreibweise wie im Geoportal, etwa „85/1“) "
            "oder die Lage auf der Karte anklicken."
        )

    features: list[ParcelFeature] = []
    official_total = 0.0
    kennzeichen: list[str] = []
    for parcel in parcels:
        official = parcel.flaeche_amtlich_m2
        if official is not None:
            official_total += official
        key = parcel.attributes.get("flstkennz")
        if key:
            kennzeichen.append(key)
        wgs84 = geo.reproject_geometry(parcel.geometry, geo.UTM33, geo.WGS84)
        features.append(
            ParcelFeature(
                id=parcel.gml_id,
                geometry=geo.to_geojson(wgs84),
                properties=ParcelProperties(
                    kennzeichen=key,
                    gemarkung=parcel.attributes.get("gemarkung"),
                    gemarkungsnummer=parcel.attributes.get("gemaschl"),
                    flur=parcel.attributes.get("flur"),
                    zaehler=parcel.attributes.get("flstnrzae"),
                    nenner=parcel.attributes.get("flstnrnen"),
                    flaeche_amtlich_m2=official,
                    flaeche_berechnet_m2=round(parcel.geometry.area, 2),
                    lagebezeichnung=parcel.attributes.get("lagebeztxt"),
                    gemeinde=parcel.attributes.get("gemeinde"),
                    aktualitaet=_as_date(parcel.attributes.get("aktualit")),
                ),
            )
        )

    union = unary_union([parcel.geometry for parcel in parcels])
    union_wgs84 = geo.reproject_geometry(union, geo.UTM33, geo.WGS84)
    return ParcelCollection(
        features=features,
        grundstueck=GrundstueckFeature(
            geometry=geo.to_geojson(union_wgs84),
            properties=GrundstueckProperties(
                anzahl_flurstuecke=len(parcels),
                kennzeichen=kennzeichen,
                flaeche_amtlich_m2=round(official_total, 2),
                flaeche_berechnet_m2=round(union.area, 2),
                gemarkung=parcels[0].attributes.get("gemarkung"),
                gemeinde=parcels[0].attributes.get("gemeinde"),
            ),
        ),
        hinweis=hinweis,
        plausibility=plausibility,
    )


# --------------------------------------------------------------------------
# Filter primitives for the parcel search
#
# The search asks the same service a great many narrow questions instead of one
# broad one: how many parcels does this district hold, how many of those measure
# 502 m2, does this parcel number exist in that district. Each is one ad-hoc
# ``fes:Filter``, so the conditions are built as strings and combined here.
#
# Every one of these was measured against the live service on 05.09.2026; the
# counts are in docs/research/flurstueck-identifikation.md.
# --------------------------------------------------------------------------

# ``fes:And`` needs at least two operands. A single condition wrapped in one
# comes back as the generic Geoportal HTML 400 page with no usable error, which
# is why this is a function and not string concatenation at the call site.
def _combine(conditions: Sequence[str]) -> str:
    if not conditions:
        raise ValueError("A parcel filter needs at least one condition.")
    if len(conditions) == 1:
        return conditions[0]
    return f"<fes:And>{''.join(conditions)}</fes:And>"


def equals(name: str, value: Any) -> str:
    """``ave:<name>`` is exactly ``value``."""

    return (
        "<fes:PropertyIsEqualTo>"
        f"<fes:ValueReference>ave:{name}</fes:ValueReference>"
        f"<fes:Literal>{escape(str(value))}</fes:Literal>"
        "</fes:PropertyIsEqualTo>"
    )


def between(name: str, lower: float, upper: float) -> str:
    """``ave:<name>`` lies in a closed band -- the tolerance staircase's rung."""

    return (
        "<fes:PropertyIsBetween>"
        f"<fes:ValueReference>ave:{name}</fes:ValueReference>"
        f"<fes:LowerBoundary><fes:Literal>{lower:g}</fes:Literal></fes:LowerBoundary>"
        f"<fes:UpperBoundary><fes:Literal>{upper:g}</fes:Literal></fes:UpperBoundary>"
        "</fes:PropertyIsBetween>"
    )


def like(name: str, pattern: str) -> str:
    """Wildcard match, ``*`` being the wildcard.

    Used on ``ave:tntxt`` for the land use and on ``ave:lagebeztxt`` for the
    street. Both are soft signals -- see ``app/search/scoring.py`` for why
    neither may ever exclude a candidate.
    """

    return (
        '<fes:PropertyIsLike wildCard="*" singleChar="#" escapeChar="!">'
        f"<fes:ValueReference>ave:{name}</fes:ValueReference>"
        f"<fes:Literal>{escape(pattern)}</fes:Literal>"
        "</fes:PropertyIsLike>"
    )


# The built-up area of a settlement -- what „6 km bis Grimma" is measured from
# when the reading is "to the edge of the town" rather than "to its middle".
#
# Measured 16.09.2026 against the live service. `ave:Nutzung` carries the
# recorded land use as polygons with `nutzart` in plain text, and a POST can
# carry a BBOX and a property filter at once. Around Grimma a 2 km box holds
# 486 `Wohnbaufläche` polygons, 674 kB in 1.8 s.
#
# Three numbers behind the constants, all measured on that box:
#
# * **Wohnbaufläche alone, not the wider settlement classes.** Adding mixed and
#   industrial use stretches the outline along the works and moves the near
#   edge from 5.32 km to 3.16 km -- and the advert's own „ca. 6 km" then falls
#   *outside* the interval the readings span. The narrow set is the better
#   model of what a seller calls "the town".
# * **A 25 m closing.** The polygons stop at the street, so without one the
#   union is 484 fragments whose largest is 0.07 km². At 15 m it is 78
#   fragments, at 25 m 55 around a 1.91 km² core, and at 50 m the gaps between
#   neighbouring hamlets start closing too and the near edge jumps 0.7 km.
# * **A 2 km radius** holds a small town whole: Grimma's core measures
#   2.9 x 2.3 km, Borna's 3.0 x 2.6 km, Bad Lausick's 3.2 x 2.3 km.
# * **A count of its own.** The service-wide `max_features` of 200 truncates
#   this query and nothing says so: 200 of Grimma's 431 polygons close into a
#   0.35 km² fragment instead of the 1.65 km² town, and the near edge reads
#   5.4 km where the whole town reads 5.3 km -- a plausible number from an
#   outline that is a tenth of the place. Measured 16.09.2026; 1 500 is well
#   above what a 2 km box has returned anywhere.
BUILT_UP_RADIUS_M = 2000.0
BUILT_UP_CLOSING_M = 25.0
BUILT_UP_KIND = "Wohnbau*"
BUILT_UP_MAX_FEATURES = 1500


@dataclass(frozen=True, slots=True)
class BuiltUpArea:
    """One settlement's built-up outline, assembled from its land-use polygons.

    Not an ALKIS object -- the cadastre records land use surface by surface and
    knows nothing of "a town". The union is ours, which is why this name is
    English while ``Flurstueck`` and ``KatasterBezirk`` keep the service's own.
    """

    geometry: Any
    parts: int
    pieces: int

    @property
    def area_m2(self) -> float:
        return float(self.geometry.area)


def _bbox_filter(easting: float, northing: float, radius_m: float, crs: str) -> str:
    """A square box as a filter condition, for the POSTs that need both.

    A WFS GET cannot carry a BBOX and a property filter at once; ``fes:BBOX``
    on ``ave:geometrie`` in a POST body can, and that is what keeps the
    land-use query from returning every kind of surface in the box.
    """

    return (
        "<fes:BBOX>"
        "<fes:ValueReference>ave:geometrie</fes:ValueReference>"
        f'<gml:Envelope srsName="{crs}">'
        f"<gml:lowerCorner>{easting - radius_m:.0f} {northing - radius_m:.0f}</gml:lowerCorner>"
        f"<gml:upperCorner>{easting + radius_m:.0f} {northing + radius_m:.0f}</gml:upperCorner>"
        "</gml:Envelope>"
        "</fes:BBOX>"
    )


def parse_land_use(xml: bytes | str) -> list[Polygon]:
    """The polygons of an ``ave:Nutzung`` response.

    The response puts its feature elements in the *default* namespace, so
    ``nutzart`` arrives without the ``ave:`` prefix the filter needs -- which
    is why this does not go through ``parse_feature_collection``.
    """

    try:
        root = ElementTree.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise UpstreamError(f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}") from exc

    default_srs = root.get("srsName")
    out: list[Polygon] = []
    for element in root.iter():
        if _local(element.tag) != "Nutzung":
            continue
        srs_name = next(
            (child.get("srsName") for child in element.iter() if child.get("srsName")),
            default_srs,
        )
        swap = _axis_swapped(srs_name)
        for polygon_element in element.iter():
            if _local(polygon_element.tag) != "Polygon":
                continue
            polygon = _parse_polygon(polygon_element, swap)
            if polygon is not None and not polygon.is_empty:
                out.append(polygon)
    return out


@dataclass(frozen=True, slots=True)
class KatasterBezirk:
    """One cadastral district with its outline.

    The committed directory (``app/gemarkung_index.py``) drops the geometry on
    purpose -- an input mask has no use for a boundary. The search does: the
    map has to wash the district the candidates share, and that wash is this
    outline. Measured 05.09.2026: Gemarkung Großbothen comes back as 16.5 kB
    with 637 boundary points, one request, so it is fetched when needed rather
    than added to the 490 kB the directory already ships.
    """

    schluessel: str
    name: str | None
    gemeinde: str | None
    geometry: Any


def _number_matched(xml: bytes) -> int:
    match = re.search(rb'numberMatched="(\d+)"', xml)
    if match is None:
        raise UpstreamError(
            f"{SERVICE_NAME} hat auf eine Zählanfrage keine Anzahl geliefert. {ADVICE}"
        )
    return int(match.group(1))


class AlkisService:
    """Queries against the simplified ALKIS WFS."""

    def __init__(self, settings: AlkisSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "alkis", ttl_s=settings.cache_ttl_s)

    @property
    def _crs_urn(self) -> str:
        return f"urn:ogc:def:crs:EPSG::{self.settings.srid}"

    async def _get(self, params: dict[str, str]) -> bytes:
        cache_key = repr(sorted(params.items()))
        cached = self.cache.get_bytes(cache_key)
        if cached is not None:
            return cached
        response = await request(
            "GET",
            self.settings.wfs_url,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.app_settings.http_timeout_s,
            user_agent=self.app_settings.user_agent,
            params=params,
        )
        self.cache.set_bytes(cache_key, response.content)
        return response.content

    async def _post(self, body: str) -> bytes:
        cached = self.cache.get_bytes(body)
        if cached is not None:
            return cached
        response = await request(
            "POST",
            self.settings.wfs_url,
            service=SERVICE_NAME,
            advice=ADVICE,
            timeout_s=self.app_settings.http_timeout_s,
            user_agent=self.app_settings.user_agent,
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
        )
        self.cache.set_bytes(body, response.content)
        return response.content

    async def by_point(self, lat: float, lon: float) -> list[Flurstueck]:
        """Parcels at a WGS84 coordinate."""

        easting, northing = geo.wgs84_to_utm33(lon, lat)
        buffer_m = self.settings.point_buffer_m
        params = {
            "SERVICE": "WFS",
            "VERSION": self.settings.version,
            "REQUEST": "GetFeature",
            "TYPENAMES": "ave:Flurstueck",
            "SRSNAME": self._crs_urn,
            "BBOX": (
                f"{easting - buffer_m},{northing - buffer_m},"
                f"{easting + buffer_m},{northing + buffer_m},{self._crs_urn}"
            ),
            "COUNT": str(self.settings.max_features),
        }
        parcels = parse_feature_collection(await self._get(params))
        # The bounding box also catches neighbours; keep the parcel the point
        # actually sits in when there is one.
        point = Point(easting, northing)
        hit = [parcel for parcel in parcels if parcel.geometry.covers(point)]
        return hit or parcels

    async def around(self, lat: float, lon: float, radius_m: float) -> list[Flurstueck]:
        """Every parcel whose outline meets a box of that half-edge.

        For choosing: a house coordinate lands where the address register put
        it, which is not always inside the parcel being sold -- measured on
        Lessingweg 44 in Mölkau, where the routing geocoder's point sits 7 m
        away, inside number 46. So the neighbours are offered and the user
        says which one is theirs, rather than the point deciding silently.

        The parcel the point sits in comes first, so a caller can preselect it.
        """

        easting, northing = geo.wgs84_to_utm33(lon, lat)
        params = {
            "SERVICE": "WFS",
            "VERSION": self.settings.version,
            "REQUEST": "GetFeature",
            "TYPENAMES": "ave:Flurstueck",
            "SRSNAME": self._crs_urn,
            "BBOX": (
                f"{easting - radius_m},{northing - radius_m},"
                f"{easting + radius_m},{northing + radius_m},{self._crs_urn}"
            ),
            "COUNT": str(self.settings.max_features),
        }
        parcels = parse_feature_collection(await self._get(params))
        point = Point(easting, northing)
        parcels.sort(key=lambda parcel: (not parcel.geometry.covers(point),
                                         parcel.geometry.distance(point)))
        return parcels

    async def buildings_around(self, lat: float, lon: float, radius_m: float) -> list[dict[str, object]]:
        """The building outlines around a point, from the cadastre itself.

        The same WFS the parcels come from carries ``ave:GebaeudeBauwerk`` --
        146 buildings in a 240 m box over Mölkau, with the register's own
        ``funktion`` and Lagebezeichnung. So the neighbour hint needs no
        OpenStreetMap source, no Overpass instance and no key: it is one more
        BBOX query on a service this app already proxies and caches.
        """

        easting, northing = geo.wgs84_to_utm33(lon, lat)
        params = {
            "SERVICE": "WFS",
            "VERSION": self.settings.version,
            "REQUEST": "GetFeature",
            "TYPENAMES": "ave:GebaeudeBauwerk",
            "SRSNAME": self._crs_urn,
            "BBOX": (
                f"{easting - radius_m},{northing - radius_m},"
                f"{easting + radius_m},{northing + radius_m},{self._crs_urn}"
            ),
            "COUNT": str(self.settings.max_features),
        }
        return parse_buildings(await self._get(params))

    async def by_kennzeichen(self, kennzeichen: str) -> list[Flurstueck]:
        """Parcels by the 20-character AdV parcel key (stored query)."""

        params = {
            "SERVICE": "WFS",
            "VERSION": self.settings.version,
            "REQUEST": "GetFeature",
            "STOREDQUERY_ID": STORED_QUERY_BY_KENNZEICHEN,
            "CRS": self._crs_urn,  # mandatory, see module docstring
            "kennzeichen": kennzeichen,
        }
        return parse_feature_collection(await self._get(params))

    async def by_gemarkung(
        self, gemarkung: str, zaehler: int, nenner: int | str | None = None
    ) -> list[Flurstueck]:
        """Parcels by cadastral district plus numerator (and denominator).

        There is no stored query for this combination, hence the ad-hoc filter.
        A purely numeric district is matched against the district number,
        anything else against the district name. The denominator is compared as
        text because ALKIS stores it as text -- 41/e is a valid parcel number.
        """

        district = expand_gemarkung_key(gemarkung)
        district_attribute = "gemaschl" if district.isdigit() else "gemarkung"
        conditions = [
            (district_attribute, district),
            ("flstnrzae", str(zaehler)),
        ]
        if nenner is not None and str(nenner).strip():
            conditions.append(("flstnrnen", str(nenner).strip()))

        comparisons = "".join(
            "<fes:PropertyIsEqualTo>"
            f"<fes:ValueReference>ave:{name}</fes:ValueReference>"
            f"<fes:Literal>{escape(value)}</fes:Literal>"
            "</fes:PropertyIsEqualTo>"
            for name, value in conditions
        )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:fes="http://www.opengis.net/fes/2.0" '
            f'xmlns:ave="{AVE_NS}" service="WFS" '
            f'version="{self.settings.version}" count="{self.settings.max_features}">'
            f'<wfs:Query typeNames="ave:Flurstueck" srsName="{self._crs_urn}">'
            f"<fes:Filter><fes:And>{comparisons}</fes:And></fes:Filter>"
            "</wfs:Query></wfs:GetFeature>"
        )
        return parse_feature_collection(await self._post(body))

    # ------------------------------------------------------------------
    # The search primitives
    # ------------------------------------------------------------------

    def _envelope(
        self,
        conditions: Sequence[str],
        *,
        result_type: str,
        count: int,
        type_names: str = "ave:Flurstueck",
    ) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:fes="http://www.opengis.net/fes/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2" '
            f'xmlns:ave="{AVE_NS}" service="WFS" version="{self.settings.version}" '
            f'resultType="{result_type}" count="{count}">'
            f'<wfs:Query typeNames="{type_names}" srsName="{self._crs_urn}">'
            f"<fes:Filter>{_combine(conditions)}</fes:Filter>"
            "</wfs:Query></wfs:GetFeature>"
        )

    async def count(self, conditions: Sequence[str]) -> int:
        """How many parcels match, without fetching one.

        ``resultType=hits`` is what makes the tolerance staircase affordable:
        the answer is a few hundred bytes whatever the count, so a rung that
        comes back empty costs nothing but a round trip. Every rung, every
        anchor and every parcel-number probe goes through here; only the set
        that survives is ever fetched with its geometry.
        """

        body = self._envelope(conditions, result_type="hits", count=1)
        return _number_matched(await self._post(body))

    async def search(
        self, conditions: Sequence[str], *, limit: int | None = None
    ) -> list[Flurstueck]:
        """The matching parcels themselves, geometry included.

        ALKIS cannot be asked for attributes without geometry -- ``PROPERTYNAME``
        is either rejected or ignored -- so this is the expensive call and the
        reason ``count`` exists. Measured 05.09.2026: 25 parcels come to
        35.6 kB in 1.5 s, about 1.4 kB each.
        """

        body = self._envelope(
            conditions,
            result_type="results",
            count=limit or self.settings.max_features,
        )
        return parse_feature_collection(await self._post(body))

    async def districts_around(
        self, lat: float, lon: float, radius_m: float
    ) -> list[KatasterBezirk]:
        """The cadastral districts whose outline meets a box around a point.

        This is what turns a place a listing names into anchors the cadastre can
        be asked about, and it closes the gap a Stadtteil leaves: a city
        district is usually *not* a Gemarkung. „Grünau-Siedlung" in Leipzig is
        none, and the two Saxon Gemarkungen called „Grünau" are 80 km away in
        the Erzgebirge — so reading the name as a district anchors the search in
        the wrong half of the state, which is why `collect_indicia` refuses a
        bare place name at all.

        Measured 09.09.2026, one request each:

        * around Grünau-Siedlung — Lausen, Schönau, Großzschocher,
          Kleinzschocher. Four anchors against Stadt Leipzig's 76, and with the
          listing's exact 742 m² they leave 3 candidates where the Gemeinde
          alone leaves 24.
        * around the Kleinanzeigen pin of the Lobstädt advert, the one measured
          6 235 m from the parcel actually offered: ±1500 m gives 8 districts
          and Lobstädt is among them; ±3000 m gives 23; ±7000 m gives 69.

        The trade is therefore reliability against set size, and it is safe in
        one direction only — which is what makes it usable at all. A box too
        small to contain the plot's district means every anchor counts zero and
        the run reports that it found nothing. It cannot produce a *wrong*
        parcel, only no parcel, so the radius may be chosen without a corpus.

        `art` is filtered here rather than in the request: a WFS GET cannot
        carry a BBOX and a filter at once. The outlines come back either way --
        `ave:KatasterBezirk` will not drop its geometry, about 5 kB a district --
        which is the reason this is asked around a point and never for a state.
        """

        easting, northing = geo.wgs84_to_utm33(lon, lat)
        params = {
            "SERVICE": "WFS",
            "VERSION": self.settings.version,
            "REQUEST": "GetFeature",
            "TYPENAMES": "ave:KatasterBezirk",
            "SRSNAME": self._crs_urn,
            "BBOX": (
                f"{easting - radius_m},{northing - radius_m},"
                f"{easting + radius_m},{northing + radius_m},{self._crs_urn}"
            ),
            "COUNT": str(self.settings.max_features),
        }
        xml = await self._get(params)
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}"
            ) from exc
        default_srs = root.get("srsName")
        found: list[KatasterBezirk] = []
        seen: set[str] = set()
        for element in root.iter():
            if _local(element.tag) != "KatasterBezirk":
                continue
            values = {
                _local(child.tag): (child.text or "").strip()
                for child in element
                if child.text
            }
            # A Flur is a subdivision, not a container the search can filter by.
            if values.get("art") != "Gemarkung":
                continue
            key = values.get("schluessel")
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(
                KatasterBezirk(
                    schluessel=key,
                    name=values.get("name") or None,
                    gemeinde=values.get("gemeinde") or None,
                    geometry=_parse_geometry(element, default_srs),
                )
            )
        return found

    async def district_outlines(self, schluessel: Sequence[str]) -> list[KatasterBezirk]:
        """Several districts in one request, for a place filed as many Flure.

        „Kitzen" is eleven entries in the directory and one place on the map, so
        drawing it must not cost eleven requests. An ``fes:Or`` over the keys
        answers all of them at once -- the same move the parcel search makes to
        count them.
        """

        keys = [expand_gemarkung_key(key) for key in schluessel]
        if not keys:
            return []
        matches = (
            equals("schluessel", keys[0])
            if len(keys) == 1
            else "<fes:Or>" + "".join(equals("schluessel", key) for key in keys) + "</fes:Or>"
        )
        body = self._envelope(
            [matches, equals("art", "Gemarkung")],
            result_type="results",
            count=len(keys),
            type_names="ave:KatasterBezirk",
        )
        xml = await self._post(body)
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}"
            ) from exc
        default_srs = root.get("srsName")
        out: list[KatasterBezirk] = []
        for element in root.iter():
            if _local(element.tag) != "KatasterBezirk":
                continue
            values = {
                _local(child.tag): (child.text or "").strip()
                for child in element
                if child.text
            }
            out.append(
                KatasterBezirk(
                    schluessel=values.get("schluessel", ""),
                    name=values.get("name") or None,
                    gemeinde=values.get("gemeinde") or None,
                    geometry=_parse_geometry(element, default_srs),
                )
            )
        return out

    async def district_outline(self, schluessel: str) -> KatasterBezirk | None:
        """One cadastral district with its boundary, for the map.

        ``None`` when the key names no district: the search shows what it has
        rather than failing over a wash it cannot draw.
        """

        key = expand_gemarkung_key(schluessel)
        body = self._envelope(
            [equals("schluessel", key), equals("art", "Gemarkung")],
            result_type="results",
            count=1,
            type_names="ave:KatasterBezirk",
        )
        xml = await self._post(body)
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges GML geliefert. {ADVICE}"
            ) from exc
        default_srs = root.get("srsName")
        for element in root.iter():
            if _local(element.tag) != "KatasterBezirk":
                continue
            values = {
                _local(child.tag): (child.text or "").strip()
                for child in element
                if child.text
            }
            return KatasterBezirk(
                schluessel=values.get("schluessel", key),
                name=values.get("name") or None,
                gemeinde=values.get("gemeinde") or None,
                geometry=_parse_geometry(element, default_srs),
            )
        return None

    async def built_up_area(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: float = BUILT_UP_RADIUS_M,
        closing_m: float = BUILT_UP_CLOSING_M,
        largest: bool = False,
    ) -> BuiltUpArea | None:
        """The built-up outline of the settlement at a coordinate.

        What a distance in a listing is measured *from* is not one point.
        „6 km bis Grimma" can mean the middle of the town or its edge, and the
        two are kilometres apart -- so the search wants both, and the edge is
        what this answers. Measured 16.09.2026 from Flurstück 790/11: 5.32 km
        to the edge of Grimma's built-up area, 6.25 km to its middle, and the
        advert says „ca. 6 km" -- inside that interval and outside every
        single-point reading.

        The cadastral district is not a substitute, and measuring refuted it:
        Gemarkung Grimma reaches to within 1.22 km of that same parcel, because
        a district is farmland too.

        Answers the connected piece the coordinate falls in -- or the largest
        one, when the point sits just outside, which is what a village edge
        does. ``largest`` asks for the biggest piece regardless, which is what
        a *named* reference wants: seeded from Grimma's market square, the
        piece under the seed is a 0.48 km² island of housing inside a centre
        the cadastre records as mixed use, while the town is the 1.65 km² belt
        around it. Measured from Flurstück 790/11, the island reads 4.6 to
        5.1 km and the belt 5.3 to 6.1 km -- and it is the belt the advert's
        „ca. 6 km" is about.

        The union stops at the largest piece either way. Taking every piece in
        the box instead pulls the near edge from 5.3 km to 2.9 km, because the
        box also holds the hamlets around the town -- the same failure that
        made the cloud of stops named after a town useless as a proxy for it.
        """

        easting, northing = geo.wgs84_to_utm33(lon, lat)
        body = self._envelope(
            [
                _bbox_filter(easting, northing, radius_m, self._crs_urn),
                like("nutzart", BUILT_UP_KIND),
            ],
            result_type="results",
            count=BUILT_UP_MAX_FEATURES,
            type_names="ave:Nutzung",
        )
        polygons = parse_land_use(await self._post(body))
        if not polygons:
            return None

        # Assembled here rather than in the browser for the same reason the
        # common envelope is: one datum about the world, made of many the
        # service returns, and the search ranks with it. The drawing geometry
        # still belongs to the frontend.
        closed = unary_union([polygon.buffer(closing_m) for polygon in polygons])
        closed = closed.buffer(-closing_m)
        parts = [
            part
            for part in (closed.geoms if isinstance(closed, MultiPolygon) else [closed])
            if not part.is_empty
        ]
        if not parts:
            return None
        parts.sort(key=lambda part: -part.area)
        point = Point(easting, northing)
        core = (
            parts[0]
            if largest
            else next((part for part in parts if part.covers(point)), parts[0])
        )
        return BuiltUpArea(geometry=core, parts=len(parts), pieces=len(polygons))
