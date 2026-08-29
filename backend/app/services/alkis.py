"""ALKIS WFS of the GeoSN: parcels by point, by cadastral identifier, by parcel key.

Two traps this module works around, both live-verified in
``docs/research/geodaten-sachsen.md``:

* every stored query except ``GetFeatureById`` requires the ``CRS`` parameter,
* ad-hoc ``fes:Filter`` must reference attributes with the ``ave:`` prefix.

Both failures come back as the same generic HTML 400 page, so parsing the
error text is pointless -- the request has to be right in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable
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
    "kreis",
    "aktualit",
    "flaeche",
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
