"""Pydantic models -- the contract between extraction, geodata services and the UI.

Deliberately absent: any contact detail from a listing (agent, phone, name).
The project decided not to hold personal data, so the schema does not carry
those fields in the first place.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

Dachform = Literal["satteldach", "walmdach", "pultdach", "flachdach", "zeltdach"]

# Fallback side ratio when a manufacturer page gives only the built-up area:
# 96.88 m2 -> 11.4 x 8.5 m. The UI offers a slider on top of this estimate.
DEFAULT_SIDE_RATIO = 1.35


T = TypeVar("T")


class Vorschlag(BaseModel, Generic[T]):
    """An extracted value on its way to the UI.

    Never a fact: the model answers even when the page does not carry the
    number, so every value travels with its source and stays unconfirmed until
    a human says otherwise.
    """

    wert: T | None = None
    quelle_url: HttpUrl | None = None
    bestaetigt: bool = False


W = TypeVar("W", bound=BaseModel)


def as_vorschlaege(source: BaseModel, wrapper: type[W], quelle_url: str | None) -> W:
    """Wrap every field of ``source`` that ``wrapper`` declares into a Vorschlag."""

    data: dict[str, Any] = {}
    for name in wrapper.model_fields:
        if not hasattr(source, name):
            continue
        data[name] = {
            "wert": getattr(source, name),
            "quelle_url": quelle_url,
            "bestaetigt": False,
        }
    return wrapper.model_validate(data)


# --------------------------------------------------------------------------
# Extraction schemas (spec section "Extraktionsschemata")
# --------------------------------------------------------------------------


class Flurstueckskennung(BaseModel):
    """Cadastral parcel identifier as written in a listing."""

    gemarkung: str | None = None  # name or number, derivable from the location
    flur: str | None = None  # frequently unused in Saxony
    zaehler: int
    # Text, not a number: letter denominators (41/e, 207/b) are in regular use.
    nenner: str | None = None

    @field_validator("nenner", mode="before")
    @classmethod
    def _denominator_as_text(cls, value: Any) -> Any:
        return str(value) if isinstance(value, int) else value


class InseratFelder(BaseModel):
    """The listing fields a page can supply.

    Separate from ``Inserat`` because this is what the model fills in: at that
    point a missing locator is a normal outcome, not a validation error.
    """

    adresse: str | None = None  # street + number + postcode + town
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    flurstuecke: list[Flurstueckskennung] = Field(default_factory=list)
    kaufpreis_eur: int | None = Field(default=None, ge=0)
    grundstuecksflaeche_m2: int | None = Field(default=None, ge=0)


class Inserat(InseratFelder):
    """A property listing, as far as it could be read."""

    quelle_url: HttpUrl | None = None  # absent when pasted from the clipboard

    @model_validator(mode="after")
    def _needs_a_locator(self) -> "Inserat":
        has_coordinates = self.lat is not None and self.lon is not None
        if not (self.adresse or has_coordinates or self.flurstuecke):
            raise ValueError(
                "Mindestens Adresse, Koordinate oder Flurstück muss angegeben sein."
            )
        return self


class HaustypFelder(BaseModel):
    """The house-type fields a manufacturer page can supply.

    The plausibility bounds are the second line of defence behind the human
    confirmation: a footprint under 30 m2 or a wall under 4 m is an extraction
    error, not a house.
    """

    hersteller: str
    typenbezeichnung: str
    # Built-up area, NOT living area -- manufacturers advertise the latter
    # across all storeys (ELK All in One 159: 159.21 m2 living, 96.88 m2 built).
    bebaute_flaeche_m2: float = Field(ge=30, le=400)
    wohnflaeche_gesamt_m2: float | None = Field(default=None, ge=0)
    wohnflaeche_eg_m2: float | None = Field(default=None, ge=0)
    wohnflaeche_og_m2: float | None = Field(default=None, ge=0)
    aussenmass_laenge_m: float | None = Field(default=None, ge=4, le=30)
    aussenmass_breite_m: float | None = Field(default=None, ge=4, le=30)
    dachformen: list[Dachform] = Field(default_factory=list)
    traufhoehe_m: float | None = Field(default=None, ge=0, le=30)  # for the 0.4 H rule, SächsBO § 6
    firsthoehe_m: float | None = Field(default=None, ge=0, le=40)
    grundstueck_ab_m2: int | None = Field(default=None, ge=0)
    preis_ab_eur: int | None = Field(default=None, ge=0)


class Haustyp(HaustypFelder):
    """A house type including its provenance."""

    quelle_url: HttpUrl
    gelesen_am: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def abgeleitete_masse(self, seitenverhaeltnis: float = DEFAULT_SIDE_RATIO) -> tuple[float, float]:
        """Length and width of a rectangle with the built-up area.

        Used only when the data sheet gives no real dimensions; real ones win.
        """

        if self.aussenmass_laenge_m and self.aussenmass_breite_m:
            return self.aussenmass_laenge_m, self.aussenmass_breite_m
        breite = (self.bebaute_flaeche_m2 / seitenverhaeltnis) ** 0.5
        return round(breite * seitenverhaeltnis, 2), round(breite, 2)


class InseratVorschlaege(BaseModel):
    """The listing as unconfirmed suggestions."""

    adresse: Vorschlag[str] = Vorschlag()
    lat: Vorschlag[float] = Vorschlag()
    lon: Vorschlag[float] = Vorschlag()
    flurstuecke: Vorschlag[list[Flurstueckskennung]] = Vorschlag()
    kaufpreis_eur: Vorschlag[int] = Vorschlag()
    grundstuecksflaeche_m2: Vorschlag[int] = Vorschlag()


class HaustypVorschlaege(BaseModel):
    """The house type as unconfirmed suggestions."""

    hersteller: Vorschlag[str] = Vorschlag()
    typenbezeichnung: Vorschlag[str] = Vorschlag()
    bebaute_flaeche_m2: Vorschlag[float] = Vorschlag()
    wohnflaeche_gesamt_m2: Vorschlag[float] = Vorschlag()
    wohnflaeche_eg_m2: Vorschlag[float] = Vorschlag()
    wohnflaeche_og_m2: Vorschlag[float] = Vorschlag()
    aussenmass_laenge_m: Vorschlag[float] = Vorschlag()
    aussenmass_breite_m: Vorschlag[float] = Vorschlag()
    dachformen: Vorschlag[list[Dachform]] = Vorschlag()
    traufhoehe_m: Vorschlag[float] = Vorschlag()
    firsthoehe_m: Vorschlag[float] = Vorschlag()
    grundstueck_ab_m2: Vorschlag[int] = Vorschlag()
    preis_ab_eur: Vorschlag[int] = Vorschlag()


Extraktionsweg = Literal["meta-tags", "llm", "eingefuegter-text"]


class ListingExtractRequest(BaseModel):
    url: HttpUrl | None = None
    # A pasted page, or a whole document handed over by the bookmarklet. The
    # cap was 400 000 while the clipboard was the only way in; a portal's
    # `document.documentElement.outerHTML` runs past a megabyte, and there is
    # no safe place to cut it -- JSON-LD is routinely the last thing in the
    # body. `PASTE_LIMIT` in the wizard is the same number, and nginx needs a
    # `client_max_body_size` above it.
    text: str | None = Field(default=None, max_length=3_000_000)

    @model_validator(mode="after")
    def _url_or_text(self) -> "ListingExtractRequest":
        if not self.url and not (self.text or "").strip():
            raise ValueError("Entweder eine URL oder ein eingefügter Text wird benötigt.")
        return self


class ListingExtractResponse(BaseModel):
    felder: InseratVorschlaege
    quelle_url: HttpUrl | None = None
    weg: Extraktionsweg
    hinweis: str | None = None
    # The listing's images, largest variant each. The search reads them for a
    # cadastral extract; nothing else in the app uses them.
    bilder: list[str] = Field(default_factory=list)
    # The listing's own description, as the page carries it. Not an extracted
    # field and never part of a stored plot: it travels so the parcel search can
    # read the cadastral district, the street and the relation between the
    # places named -- all of which live in the prose and in no attribute.
    # Capped, because a whole page of it is of no use to anything downstream.
    beschreibung: str | None = Field(default=None, max_length=20_000)


class HousetypeExtractRequest(BaseModel):
    url: HttpUrl


class HousetypeExtractResponse(BaseModel):
    felder: HaustypVorschlaege
    quelle_url: HttpUrl
    gelesen_am: datetime
    abgeleitete_laenge_m: float
    abgeleitete_breite_m: float
    weg: Extraktionsweg
    hinweis: str | None = None


# --------------------------------------------------------------------------
# Parcels
# --------------------------------------------------------------------------


# The official geoportal shows one "Flurstücksnummer" per parcel -- 476, 85/1,
# 41/e -- while ALKIS stores numerator and denominator in two attributes. The
# denominator is not always a number: letter denominators such as 41/e or 207/b
# are in regular use and valid.
_FLURSTUECKSNUMMER = re.compile(r"^(\d{1,6})(?:\s*/\s*([0-9A-Za-zÄÖÜäöüß]{1,6}))?$")
_NENNER = re.compile(r"^[0-9A-Za-zÄÖÜäöüß]{1,6}$")

FLURSTUECKSNUMMER_HINT = (
    "Erwartet wird eine Zahl wie „476“ oder eine Zahl mit Nenner wie „85/1“ oder „41/e“."
)


def parse_flurstuecksnummer(value: str) -> tuple[int, str | None]:
    """Split a parcel number into numerator and denominator.

    ``85/1`` -> ``(85, "1")``, ``476`` -> ``(476, None)``, ``41/e`` -> ``(41, "e")``.
    The denominator stays a string: ALKIS compares it as text and letters occur.
    """

    match = _FLURSTUECKSNUMMER.match(" ".join(str(value).split()))
    if not match:
        raise ValueError(
            f"„{value}“ ist keine gültige Flurstücksnummer. {FLURSTUECKSNUMMER_HINT}"
        )
    return int(match.group(1)), match.group(2) or None


class ParcelResolveRequest(BaseModel):
    """One of four ways in: address, coordinate, cadastral identifier, or keys.

    The cadastral way in accepts both spellings: the two ALKIS attributes
    (``zaehler`` plus optional ``nenner``) and the single ``flurstuecksnummer``
    the official geoportal prints.

    A coordinate may be given the way the cadastre itself writes it. The Saxon
    geoportal shows ETRS89/UTM33N, so a user copying a position out of it has
    ``easting``/``northing`` in front of them and no way to turn those into
    degrees in a browser -- the projection lives here.
    """

    address: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    easting: float | None = Field(
        default=None, ge=180_000, le=900_000,
        description="Rechtswert in ETRS89/UTM33N (EPSG:25833), wie im Geoportal.",
    )
    northing: float | None = Field(
        default=None, ge=5_200_000, le=6_100_000,
        description="Hochwert in ETRS89/UTM33N (EPSG:25833).",
    )
    gemarkung: str | None = Field(default=None, max_length=120)
    zaehler: int | None = Field(default=None, ge=0)
    # A denominator may be a letter (41/e), so it travels as text; an integer
    # is accepted and normalised for callers that send one.
    nenner: int | str | None = Field(default=None)
    flurstuecksnummer: str | None = Field(
        default=None,
        max_length=20,
        description="Flurstücksnummer wie im Geoportal, etwa „85/1“, „476“ oder „41/e“.",
    )
    # A plot is a set of parcels, and the user assembles that set by clicking:
    # this is that set, as the parcel keys `/nearby` answered with. The union
    # and the summed official areas are the same code every other way in uses.
    kennzeichen: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Flurstückskennzeichen, die zusammen ein Grundstück bilden.",
    )
    # The same set named the way a listing names it: one Gemarkung, several
    # numbers. The keys above come from `/nearby`, these from what was read.
    flurstuecksnummern: list[str] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Mehrere Flurstücksnummern derselben Gemarkung, die zusammen ein "
            "Grundstück bilden. Die Umringe werden vereinigt, die amtlichen "
            "Flächen summiert."
        ),
    )
    # What the listing says the plot measures. Only ever used to judge the
    # answer, never to filter it -- see app/plausibility.py.
    expected_area_m2: int | None = Field(
        default=None,
        ge=1,
        le=10_000_000,
        description=(
            "Erwartete Grundstücksfläche in m², etwa aus dem Inserat. Wird nur zur "
            "Plausibilitätsprüfung der Antwort verwendet."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_way_in(self) -> "ParcelResolveRequest":
        if self.flurstuecksnummern:
            cleaned = [number.strip() for number in self.flurstuecksnummern if number.strip()]
            if not cleaned:
                raise ValueError("Die Liste der Flurstücksnummern ist leer.")
            if self.flurstuecksnummer or self.zaehler is not None:
                raise ValueError(
                    "Bitte entweder eine einzelne Flurstücksnummer angeben oder die Liste, "
                    "nicht beides."
                )
            if not self.gemarkung:
                raise ValueError(
                    "Zu Flurstücksnummern wird die Gemarkung benötigt — "
                    "dieselbe Nummer gibt es in jeder Gemarkung."
                )
            # Validated here so a typo is a 422 with the number in it rather
            # than a request that finds nothing and says the parcel is unknown.
            for number in cleaned:
                parse_flurstuecksnummer(number)
            # Duplicates would double the summed area, which is the one figure
            # every price comparison rests on.
            seen: list[str] = []
            for number in cleaned:
                if number not in seen:
                    seen.append(number)
            self.flurstuecksnummern = seen
            return self

        if self.flurstuecksnummer is not None and self.flurstuecksnummer.strip():
            if self.zaehler is not None or self.nenner is not None:
                raise ValueError(
                    "Bitte entweder die Flurstücksnummer oder Zähler und Nenner angeben, "
                    "nicht beides."
                )
            self.zaehler, self.nenner = parse_flurstuecksnummer(self.flurstuecksnummer)
        elif self.nenner is not None:
            nenner = str(self.nenner).strip()
            if not _NENNER.match(nenner):
                raise ValueError(
                    f"„{self.nenner}“ ist kein gültiger Nenner einer Flurstücksnummer. "
                    "Erlaubt sind bis zu sechs Ziffern oder Buchstaben, etwa „1“ oder „e“."
                )
            self.nenner = nenner

        if (self.easting is None) != (self.northing is None):
            raise ValueError("Rechtswert und Hochwert müssen gemeinsam angegeben werden.")
        if self.easting is not None:
            if self.lat is not None:
                raise ValueError(
                    "Bitte entweder lat/lon oder Rechts- und Hochwert angeben, nicht beides."
                )
            # Imported here: schemas.py is otherwise free of the projection
            # stack, and importing pyproj at module scope would drag it into
            # every process that only wants the models.
            from . import geo

            self.lon, self.lat = geo.utm33_to_wgs84(self.easting, self.northing)

        by_address = bool(self.address and self.address.strip())
        by_point = self.lat is not None and self.lon is not None
        by_parcel = bool(self.gemarkung and self.zaehler is not None)
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat und lon müssen gemeinsam angegeben werden.")
        if self.zaehler is not None and not self.gemarkung:
            raise ValueError(
                "Zu einer Flurstücksnummer wird die Gemarkung benötigt — "
                "dieselbe Nummer gibt es in jeder Gemarkung."
            )
        by_keys = bool(self.kennzeichen)
        if by_keys:
            keys = [key.strip() for key in self.kennzeichen if key and key.strip()]
            if not keys:
                raise ValueError("Ein Flurstückskennzeichen darf nicht leer sein.")
            # A set of parcels, not a list: the same key twice would be counted
            # twice in the official area.
            self.kennzeichen = list(dict.fromkeys(keys))
        chosen = [by_address, by_point, by_parcel, by_keys]
        if sum(chosen) == 0:
            raise ValueError(
                "Bitte Adresse, Koordinate (lat/lon), Gemarkung mit Flurstücksnummer "
                "oder Flurstückskennzeichen angeben."
            )
        if sum(chosen) > 1:
            raise ValueError(
                "Bitte nur einen Weg angeben: Adresse, Koordinate, Gemarkung mit "
                "Flurstücksnummer oder Flurstückskennzeichen."
            )
        return self


class ParcelsAroundRequest(BaseModel):
    """The parcels near a coordinate, for choosing between them.

    Deliberately separate from `/resolve`: that answers with *the* plot, as one
    union, while this answers with the candidates so the user can say which one
    is theirs. The distinction matters because an address coordinate is not a
    parcel — the register places it on the building, and a metre either way puts
    it in the neighbour's.
    """

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    umkreis_m: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Halbe Kantenlänge des Suchfensters um die Koordinate.",
    )


class Geometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon", "LineString", "Point"]
    coordinates: Any


class ParcelProperties(BaseModel):
    kennzeichen: str | None = None
    gemarkung: str | None = None
    gemarkungsnummer: str | None = None
    flur: str | None = None
    zaehler: str | None = None
    nenner: str | None = None
    # The official area from the ALKIS attribute -- never derived from the polygon.
    flaeche_amtlich_m2: float | None = None
    # Derived from the polygon in EPSG:25833, for shape analysis only.
    flaeche_berechnet_m2: float | None = None
    lagebezeichnung: str | None = None
    gemeinde: str | None = None
    aktualitaet: date | None = None


class ParcelFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | None = None
    geometry: Geometry
    properties: ParcelProperties


class GrundstueckProperties(BaseModel):
    """The union of all parcels -- a plot is a set of parcels, not one parcel."""

    anzahl_flurstuecke: int
    kennzeichen: list[str] = Field(default_factory=list)
    flaeche_amtlich_m2: float
    flaeche_berechnet_m2: float
    gemarkung: str | None = None
    gemeinde: str | None = None


class GrundstueckFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry
    properties: GrundstueckProperties


PlausibilityIssue = Literal[
    "area_too_large",
    "area_too_small",
    "shape_atypical",
    "address_is_not_a_street_address",
]


class Plausibility(BaseModel):
    """Whether the answer can be the plot the caller expected.

    Never an error and never a filter: the parcel is returned either way. The
    frontend needs to tell "this is your plot" from "this is the field your
    district address landed in", and that is what ``issues`` is for --
    ``warning`` is the same finding as one German sentence to show.
    """

    plausible: bool
    issues: list[PlausibilityIssue] = Field(default_factory=list)
    # The listing's area as it came in, so the frontend can show both sides.
    expected_area_m2: int | None = None
    # The official ALKIS area of the whole plot, the number the factor uses.
    flaeche_amtlich_m2: float | None = None
    area_factor: float | None = None
    # Sides of the tightest (rotated) rectangle around the plot, in metres.
    longest_extent_m: float | None = None
    shortest_extent_m: float | None = None
    elongation: float | None = None
    warning: str | None = None


class ParcelCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    crs_hinweis: str = "EPSG:4326 (WGS84); Längen und Flächen wurden in EPSG:25833 gerechnet."
    features: list[ParcelFeature]
    grundstueck: GrundstueckFeature
    quelle: str = "Landesamt für Geobasisinformation Sachsen (GeoSN), dl-de/by-2-0"
    hinweis: str | None = None
    plausibility: Plausibility | None = None


# --------------------------------------------------------------------------
# Land value
# --------------------------------------------------------------------------


class LandValue(BaseModel):
    euro_per_sqm: float
    zone: str | None = None
    reference_date: date | None = None
    source_url: str
    nutzung: str | None = None
    entwicklungszustand: str | None = None
    gutachterausschuss: str | None = None
    # The size of the notional plot the value is quoted for. BORIS carries it
    # as `FLAECHE_TEXT = 'f800'` and links the Gutachterausschuss' own
    # conversion table beside it -- so a 650 m² parcel is not simply 650 × the
    # zone value, and the interface can say so instead of implying it.
    richtwertgrundstueck_m2: float | None = None
    umrechnungstabelle_url: str | None = None
    hinweis: str = (
        "Zonenwert nach § 196 BauGB. Nach § 15 Abs. 2 ImmoWertV kann ein einzelnes "
        "Grundstück innerhalb der Zone abweichend genutzt werden — dann gilt der "
        "Zonenwert für dieses Grundstück nicht."
    )
    quelle: str = "Gutachterausschüsse für Grundstückswerte im Freistaat Sachsen (BORIS Sachsen)"


# --------------------------------------------------------------------------
# Reachability
# --------------------------------------------------------------------------

# Mode names follow MOTIS semantics. The three intermodal ones differ only in
# how the first stop is reached -- the far end is always on foot, see
# ``Zubringer`` below. "transit_auto" is not a mode the router knows: it asks
# this service to pick one of the three, per destination.
Modus = Literal[
    "car",
    "bike",
    "walk",
    "transit",        # on foot to the first stop
    "bike_transit",   # by bike to the first stop, bike parked there
    "car_transit",    # by car to a park-and-ride, on foot to the platform
    "transit_auto",
]

# How the traveller reaches the first stop, fixed per destination. "automatic"
# hands the decision to the ladder in services/motis.py; the other three pin it,
# which is what "cycling to the office from the station is not worth it" means
# in data. Absent on destinations stored before this field existed, and the
# default is what those get.
Zubringer = Literal["automatic", "walk", "bike", "car"]

# What each pinned value routes as. The far end stays WALK in all three.
ZUBRINGER_MODI: dict[str, Modus] = {
    "walk": "transit",
    "bike": "bike_transit",
    "car": "car_transit",
}


class Koordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Ziel(Koordinate):
    id: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=200)
    # Only read when "transit_auto" is among the requested modes.
    zubringer: Zubringer = "automatic"


Geocodeart = Literal["adresse", "haltestelle", "ort", "sonstiges"]

GEOCODE_HINWEIS = (
    "Die Koordinaten stammen aus dem Routing-Geocoder (Transitous, OpenStreetMap "
    "und Fahrplandaten), nicht aus den amtlichen Hauskoordinaten des GeoSN. Bitte "
    "den gefundenen Ort auf der Karte prüfen und gegebenenfalls einen anderen "
    "Treffer wählen."
)


class GeocodeRequest(BaseModel):
    """Free text to coordinates.

    ``lat``/``lon`` are an optional bias: results near that point rank higher.
    Passing the plot's coordinate turns "Am Kirschberg" from a village in
    Bavaria into the stop around the corner.
    """

    text: str = Field(min_length=2, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _bias_needs_both_halves(self) -> "GeocodeRequest":
        if (self.lat is None) != (self.lon is None):
            raise ValueError(
                "lat und lon müssen gemeinsam angegeben werden — sie sind nur ein "
                "Bezugspunkt, damit nahe Treffer vorn stehen."
            )
        return self


class GeocodeTreffer(Koordinate):
    """One candidate, with the label the geocoder actually matched.

    The label matters as much as the coordinate: this geocoder answers
    "Am Kirschberg" with a village 300 km away and does so with confidence, so
    the user has to be able to see what was found.
    """

    name: str
    beschreibung: str | None = None  # place context that tells two hits apart
    art: Geocodeart = "sonstiges"


# What the answer says once the official addresses are on this server. The
# routing geocoder is still named: it contributes the stops, the places and
# everything outside Saxony, and a mixed list has to say which half is which.
GEOCODE_HINWEIS_AMTLICH = (
    "Treffer mit dem Zusatz „amtliche Hauskoordinate“ stammen aus den Hauskoordinaten "
    "des GeoSN{stand} und sind die vom Kataster geführte Koordinate des Hauses. Die "
    "übrigen kommen aus dem Routing-Geocoder (Transitous, OpenStreetMap und "
    "Fahrplandaten) — die bitte auf der Karte prüfen."
)
GEOCODE_QUELLE = "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
GEOCODE_QUELLE_AMTLICH = "Amtliche Hauskoordinaten (GeoSN, dl-de/by-2-0)"


class GeocodeResponse(BaseModel):
    treffer: list[GeocodeTreffer]
    hinweis: str = GEOCODE_HINWEIS
    quelle: str = GEOCODE_QUELLE


class ReachabilityRequest(BaseModel):
    origin: Koordinate
    destinations: list[Ziel] = Field(min_length=1, max_length=20)
    modes: list[Modus] = Field(
        default_factory=lambda: ["car", "bike", "transit_auto"], min_length=1
    )
    # Departure time; MOTIS defaults to "now" when omitted.
    time: datetime | None = None


class Teilstrecke(BaseModel):
    mode: str
    duration_s: int
    von: str | None = None
    nach: str | None = None


class RouteErgebnis(BaseModel):
    destination_id: str
    # The mode that was actually routed. For a "transit_auto" request this is
    # the variant the ladder settled on, so the caller can key by it and label
    # the row without a second lookup.
    mode: Modus
    # What the caller asked for, which is the only way to tell a "transit"
    # answer that was pinned from one the ladder chose.
    angefragter_modus: Modus | None = None
    erreichbar: bool
    duration_s: int | None = None
    umstiege: int | None = None
    startzeit: datetime | None = None
    ankunftszeit: datetime | None = None
    geometry: Geometry | None = None
    teilstrecken: list[Teilstrecke] = Field(default_factory=list)
    hinweis: str | None = None


class ReachabilityResponse(BaseModel):
    ergebnisse: list[RouteErgebnis]
    quelle: str = "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"


# --------------------------------------------------------------------------
# Nearby -- "wie weit ist die nächste Schule"
# --------------------------------------------------------------------------

# Six categories come from the local OpenStreetMap index, four from the MOTIS
# timetable. They are one enum because a caller asks one question of them.
Kategorie = Literal[
    "schule",
    "kindergarten",
    "park",
    "spielplatz",
    "supermarkt",
    "arzt",
    "tram",
    "sbahn",
    "bus",
    "bahnhof",
]

ALLE_KATEGORIEN: tuple[Kategorie, ...] = (
    "schule",
    "kindergarten",
    "park",
    "spielplatz",
    "supermarkt",
    "arzt",
    "tram",
    "sbahn",
    "bus",
    "bahnhof",
)

# What a user reads for each. Kept here so the endpoint, the health report and
# every message use the same word for the same thing.
KATEGORIE_LABELS: dict[str, str] = {
    "schule": "Schule",
    "kindergarten": "Kindergarten",
    "park": "Park",
    "spielplatz": "Spielplatz",
    "supermarkt": "Supermarkt",
    "arzt": "Arztpraxis",
    "tram": "Straßenbahnhaltestelle",
    "sbahn": "S-Bahn-Haltestelle",
    "bus": "Bushaltestelle",
    "bahnhof": "Bahnhof",
}

# one-to-many routes on the street network only; public transport is not a way
# of getting to the nearest playground.
Umgebungsmodus = Literal["walk", "bike"]

UMGEBUNG_HINWEIS = (
    "Die Gehzeiten stammen aus dem Fußwegenetz von OpenStreetMap und sind "
    "Schätzwerte, keine Messwerte — sortiert wird danach und nicht nach "
    "Luftlinie, weil der nächstgelegene Ort oft der weitere Weg ist. "
    "Schule, Kindergarten, Park, Spielplatz, Supermarkt und Arztpraxis stammen "
    "aus OpenStreetMap und damit aus ehrenamtlicher Kartierung, nicht aus einem "
    "amtlichen Verzeichnis; die Schulart wird aus dem Namen abgeleitet und ist "
    "zu prüfen. Haltestellen und Bahnhöfe kommen aus dem Fahrplan und zeigen, "
    "was dort tatsächlich hält."
)


class NearbyRequest(BaseModel):
    """One coordinate, one question: was ist in der Nähe?"""

    origin: Koordinate
    kategorien: list[Kategorie] = Field(
        default_factory=lambda: list(ALLE_KATEGORIEN),
        min_length=1,
        max_length=len(ALLE_KATEGORIEN),
        description="Welche Kategorien gesucht werden; ohne Angabe alle.",
    )
    modus: Umgebungsmodus = "walk"
    umkreis_m: int = Field(
        default=3000,
        ge=200,
        le=15000,
        description=(
            "Luftlinien-Umkreis, in dem nach Kandidaten gesucht wird. Nur ein "
            "Vorfilter — angezeigt wird die Gehzeit."
        ),
    )
    treffer_je_kategorie: int = Field(
        default=2, ge=1, le=10, description="Wie viele Treffer je Kategorie zurückkommen."
    )
    linien: bool = Field(
        default=False,
        description=(
            "Zusätzlich die Linien abfragen, die an einer gefundenen Haltestelle "
            "halten. Kostet je Haltestelle eine weitere Anfrage an den Fahrplandienst."
        ),
    )

    @model_validator(mode="after")
    def _no_duplicate_categories(self) -> "NearbyRequest":
        seen: list[Kategorie] = []
        for kategorie in self.kategorien:
            if kategorie not in seen:
                seen.append(kategorie)
        self.kategorien = seen
        return self


class UmgebungTreffer(BaseModel):
    """One place found, with the walking time that put it in this position."""

    # The category this row is labelled with. One stop can serve several, and
    # then this is the longest-range one among those that were asked for.
    kategorie: Kategorie
    # The requested categories this hit was found for, `kategorie` included --
    # a stop among the nearest for both `sbahn` and `bahnhof` is listed once and
    # carries both, instead of appearing twice. Not every mode that calls here:
    # a stop can serve buses and still be too far to be one of the nearest bus
    # stops. `art` is what lists the modes.
    kategorien: list[Kategorie] = Field(default_factory=list)
    # Absent is normal, not an error: most Saxon playgrounds carry no name.
    name: str | None = None
    # "Grundschule", "Straßenbahn, Bus" -- what kind of thing this is.
    art: str | None = None
    lat: float
    lon: float
    erreichbar: bool
    # MOTIS' pedestrian routing cost. It charges for crossings and turns, so it
    # is NOT distance divided by a walking speed -- do not derive one.
    duration_s: int | None = None
    distance_m: int | None = None
    # Kept so the "not reachable on foot" case still has a number to show.
    luftlinie_m: int
    # ``None`` means "not asked for", an empty list means "asked, and nothing
    # calls here in this category". The same distinction the whole endpoint is
    # built on, one level down.
    linien: list[str] | None = None
    # Which source answered: the locally built index, a live Overpass query, or
    # the timetable. All three are shown to the user differently.
    quelle: Literal["osm", "overpass", "motis"]
    osm_id: str | None = None
    stop_id: str | None = None
    hinweis: str | None = None


class KategorieStatus(BaseModel):
    """Whether a category could be answered at all.

    The distinction this exists for: "der Server hat dazu keine Daten" is not
    the same statement as "in der Nähe gibt es nichts", and an empty list reads
    as the second one. ``verfuegbar: false`` covers both ways the first can
    happen -- no index built here, and no source that answered right now.
    """

    kategorie: Kategorie
    verfuegbar: bool
    # How many returned hits carry this category in `kategorien` -- which is not
    # the number of rows labelled with it in `kategorie`. A stop listed once
    # under `bahnhof` still counts for `sbahn` when it is among the nearest
    # S-Bahn stops, so this never says "nichts gefunden" about something that
    # was in fact found. Never more than `treffer_je_kategorie`.
    anzahl: int = 0
    hinweis: str | None = None


class NearbyResponse(BaseModel):
    treffer: list[UmgebungTreffer] = Field(default_factory=list)
    kategorien: list[KategorieStatus] = Field(default_factory=list)
    # Timestamp of the OSM extract the index was built from, when there is one.
    datenstand: str | None = None
    quelle: str = "OpenStreetMap (ODbL) und MOTIS / Transitous (DELFI-GTFS)"
    hinweis: str = UMGEBUNG_HINWEIS


# --------------------------------------------------------------------------
# Neighbouring buildings
# --------------------------------------------------------------------------


# The wall height is what § 6 Abs. 5 SächsBO measures from, and neither source
# carries one: the simplified ALKIS has no storeys at all, and OSM had them for
# 11 of 59 buildings around Mölkau 204. So both sentences say the same thing
# about what is computable and differ only in where the outlines came from.
NACHBARN_HINWEIS_KATASTER = (
    "Umrisse aus dem Liegenschaftskataster (ALKIS), ohne Wandhöhen — daraus "
    "lässt sich nur das Mindestmaß von 3 m nach § 6 Abs. 5 SächsBO rechnen, nie "
    "0,4 H. Ein Hinweis, keine bauordnungsrechtliche Prüfung."
)

NACHBARN_HINWEIS = (
    "Umrisse aus OpenStreetMap, ohne Wandhöhen — daraus lässt sich nur das "
    "Mindestmaß von 3 m nach § 6 Abs. 5 SächsBO rechnen, nie 0,4 H. Ein "
    "Hinweis, keine bauordnungsrechtliche Prüfung."
)


class Nachbargebaeude(BaseModel):
    """One building outline, from the cadastre or from OpenStreetMap."""

    id: str = Field(description="Objekt-ID der Quelle — ALKIS-OID oder OSM-Weg.")
    umriss: list[list[float]] = Field(
        description="Geschlossener Ring in [lon, lat], WGS84.", min_length=4
    )
    adresse: str | None = None
    funktion: str | None = Field(
        default=None, description="Gebäudefunktion, wie ALKIS sie führt."
    )
    aktualitaet: str | None = Field(
        default=None, description="Fortführungsdatum des Objekts im Kataster."
    )
    geschosse: int | None = Field(
        default=None,
        description="Nur wenn die Quelle es führt; ALKIS-vereinfacht führt es nie "
        "und OSM in sächsischen Wohnlagen fast nie.",
    )


class NachbarnRequest(BaseModel):
    origin: Koordinate
    umkreis_m: int = Field(
        default=80,
        ge=20,
        le=300,
        description="Luftlinien-Umkreis um den Ankerpunkt des Grundstücks.",
    )


class NachbarnResponse(BaseModel):
    gebaeude: list[Nachbargebaeude]
    quelle: str | None = None
    datenstand: str | None = None
    hinweis: str = NACHBARN_HINWEIS


# --------------------------------------------------------------------------
# Standortprüfungen
#
# The field names are German because they are the wire format and they mirror
# the authorities' own vocabulary -- a `Wasserschutzgebiet` has no English name
# in the register it comes from. What the services answer travels untranslated:
# `Lden5559`, `LK_IV`, the area's own name. Turning a class key into a sentence
# is the browser's job (`frontend/src/lib/findings.js`), and turning it into a
# sentence *here* would put German UI copy in a Python module and make it
# unreviewable in one place.
# --------------------------------------------------------------------------

STANDORT_HINWEIS = (
    "Die Prüfungen sind eine Recherche, keine behördliche Auskunft. Sie ersetzen "
    "weder eine Bauvoranfrage noch ein Baugrundgutachten; maßgeblich sind die "
    "Auskünfte der zuständigen Behörden."
)


class StandortRequest(BaseModel):
    """One parcel outline, in WGS84, as `[lon, lat]` pairs.

    A ring rather than a point, and deliberately no point alternative: a plot
    straddles isophones and zone boundaries, and asking with its centre would
    answer for one square metre of it. Measured on Flurstück 204 in Mölkau --
    50-54 dB(A) at the building point, 50-59 dB(A) across the 650 m².
    """

    ring: list[tuple[float, float]] = Field(
        min_length=3,
        max_length=2000,
        description="Umring des Grundstücks als [lon, lat]-Paare in WGS84.",
    )

    @field_validator("ring")
    @classmethod
    def _inside_saxony(cls, ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
        # Generous bounds around Germany: the services are Saxon, and a ring
        # somewhere else is a mistake worth naming rather than a slow 0-hit.
        for lon, lat in ring:
            if not (5.6 <= lon <= 15.3 and 47.0 <= lat <= 55.2):
                raise ValueError(
                    "Der Umring liegt außerhalb Deutschlands — bitte [lon, lat] in WGS84 senden."
                )
        return ring


class Laerm(BaseModel):
    """Noise bands per source, as 5 dB categories.

    `tag` is L_DEN over 24 hours, `nacht` is L_night. A source that answers with
    an empty list is mapped and quiet there; a source that is absent from the
    dict was not asked.
    """

    tag: dict[str, list[str]] = Field(default_factory=dict)
    nacht: dict[str, list[str]] = Field(default_factory=dict)
    kartiert_umkreis: bool = False
    umkreis_m: int
    unterste_stufe_db: int
    quelle: str
    fehler: str | None = None


class Gebiet(BaseModel):
    """One designated area, with the category it was designated under."""

    name: str | None = None
    kategorie: str | None = None


class Ausweisung(BaseModel):
    """A designation the plot either sits in or does not.

    `abstand_von_m`/`abstand_bis_m` are a bracket, not a measurement: the
    service answers whether something lies within a radius, so the distance is
    only known to the width of the rung it was found on.
    """

    betroffen: bool = False
    gebiete: list[Gebiet] = Field(default_factory=list)
    naechstes: Gebiet | None = None
    abstand_von_m: float | None = None
    abstand_bis_m: float | None = None
    weitere_im_umkreis: int = 0
    umkreis_m: int | None = None
    quelle: str
    fehler: str | None = None


class Bohrung(BaseModel):
    entfernung_m: float
    endteufe_m: float | None = None
    jahr: int | None = None
    url: str | None = None


class Baugrund(BaseModel):
    """The soil map's own wording, the air capacity class, and what was drilled.

    Nothing in here says anything about bearing capacity: a soil map at
    1:50 000 is not a ground investigation, and the finding says so.
    """

    bodenart_text: str | None = None
    luftkapazitaet_stufe: str | None = None
    bohrungen_umkreis: int = 0
    bohrungen_naher_umkreis: int = 0
    # Whether the borehole layer answered at all. Without it, a refused query
    # and a genuinely undrilled neighbourhood both arrive as zero.
    bohrungen_gefragt: bool = True
    umkreis_m: int
    naher_umkreis_m: int
    naechste: Bohrung | None = None
    tiefste: Bohrung | None = None
    quelle: str
    fehler: str | None = None


class Luftqualitaet(BaseModel):
    """Measured pollutants, and how far away the station that answered is.

    `uebersprungen` counts the nearer stations that carried no values at all --
    without it, "4,6 km" looks like carelessness rather than the only station
    that answers.
    """

    station: str | None = None
    entfernung_km: float | None = None
    werte: dict[str, float] = Field(default_factory=dict)
    stunden: int | None = None
    stand: str | None = None
    uebersprungen: int = 0
    quelle: str
    fehler: str | None = None


class StandortPruefungen(BaseModel):
    laerm: Laerm
    trinkwasserschutz: Ausweisung
    schutzgebiet: Ausweisung
    hochwasser: Ausweisung
    radon: Ausweisung
    hangneigung: Ausweisung
    baugrund: Baugrund
    luftqualitaet: Luftqualitaet
    abgerufen_am: datetime
    hinweis: str = STANDORT_HINWEIS


# --------------------------------------------------------------------------
# Cadastral districts
# --------------------------------------------------------------------------


class Gemarkung(BaseModel):
    """One cadastral district, as ALKIS spells it.

    ``name`` is not unique -- 5 339 districts share 4 880 names -- so a picklist
    has to show the key and the municipality alongside it.
    """

    name: str
    schluessel: str
    gemeinde: str | None = None


class GemarkungenResponse(BaseModel):
    stand: str | None = Field(
        default=None, description="Tag, an dem das Verzeichnis vom Katasterdienst geholt wurde."
    )
    gemarkungen: list[Gemarkung]


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


class DienstStatus(BaseModel):
    name: str
    konfiguriert: bool
    endpunkt: str | None = None
    hinweis: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    dienste: list[DienstStatus]


# --------------------------------------------------------------------------
# Sign-in (GET /api/auth/me)
# --------------------------------------------------------------------------


class AnmeldungStatus(BaseModel):
    """Three states, not two.

    A deployment with no provider configured is not "signed out" -- there is
    nothing to sign in to, and the frontend then shows no account area at all
    rather than a button that leads to a 503. Hence ``eingerichtet`` next to
    ``angemeldet``.
    """

    eingerichtet: bool = Field(
        description="Ob auf diesem Server überhaupt eine Anmeldung eingerichtet ist."
    )
    angemeldet: bool = Field(description="Ob diese Sitzung angemeldet ist.")
    name: str | None = Field(
        default=None,
        description="Anzeigename, falls der Anmeldedienst einen liefert, sonst null.",
    )
    kennung: str | None = Field(
        default=None,
        description=(
            "Stabile, nicht sprechende Kennung des Kontos; aus Issuer und Subject "
            "gebildet, damit keine Kennung des Anmeldedienstes selbst nach außen geht."
        ),
    )


# --------------------------------------------------------------------------
# Server storage for an account (GET/PUT /api/plots, GET/PUT /api/settings)
#
# The field names are the frontend's own: `dokument` is its document, verbatim,
# and `geaendert_am` the stand it was last written at. The backend does not look
# inside `dokument` -- see app/services/storage.py for why that is a decision
# and not an omission.
# --------------------------------------------------------------------------


def _aware(value: datetime | None) -> datetime | None:
    """A moment with a time zone. A naive one is read as UTC.

    The frontend echoes back exactly the string it was given, which always
    carries an offset. A hand-written request may not, and comparing a naive
    moment against a `timestamptz` is an error rather than a mismatch.
    """

    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class GespeichertesGrundstueck(BaseModel):
    """One stored plot: what was written, under which id, at which stand."""

    id: str
    geaendert_am: datetime = Field(
        description="Stand des gespeicherten Eintrags; wird beim Schreiben zurückgeschickt."
    )
    dokument: dict[str, Any] = Field(
        description="Das Dokument des Frontends, unverändert."
    )


class GrundstueckeAntwort(BaseModel):
    eintraege: list[GespeichertesGrundstueck] = Field(
        description="Alle Grundstücke dieses Kontos, zuletzt geändertes zuerst."
    )


class KontoAntwort(BaseModel):
    """What is held about the signed-in account, for the person it is about.

    Deliberately the whole of it and not a summary: this is the answer to
    "what do you have about me", so a field that exists in the database
    appears here, and a person can check that the list is short.
    """

    anbieter: str = Field(
        description="Der OpenID-Anbieter, der diese Anmeldung bestätigt hat (issuer)."
    )
    kennung: str = Field(
        description="Die Kennung, unter der der Anbieter diese Person führt (subject). "
        "Sie stammt vom Anbieter, nicht von uns."
    )
    anzeigename: str | None = Field(
        default=None,
        description="Der Name, den der Anbieter mitgegeben hat; null, wenn er keinen gab.",
    )
    angelegt: datetime = Field(
        description="Wann hier zum ersten Mal etwas für dieses Konto gespeichert wurde."
    )
    grundstuecke: int = Field(description="Wie viele Grundstücke im Konto liegen.")
    groesse_bytes: int = Field(
        description="Wie viel Platz die gespeicherten Dokumente zusammen belegen."
    )


class FreigabeUmfang(BaseModel):
    """What a link may carry beyond the plot itself.

    Every switch defaults to *off*: a shared link is public, and the safe
    default for a public thing is the least it can be. What is always in it --
    the outline, the official area, the Gemarkung, the Bodenrichtwert -- are
    facts about a piece of land that the registers publish anyway.
    """

    preis: bool = Field(default=False, description="Kaufpreis und der Vergleich damit.")
    haus: bool = Field(default=False, description="Der geplante Baukörper und sein Haustyp.")
    wege: bool = Field(
        default=False,
        description="Ziele und Wegezeiten. Die Ziele sind Arbeitsplatz, Schule und "
        "Ähnliches, also die persönlichste Angabe am ganzen Grundstück.",
    )
    notiz: bool = Field(default=False, description="Die persönliche Notiz.")


class FreigabeAnfrage(BaseModel):
    """A plot to freeze under a link."""

    dokument: dict[str, Any] = Field(
        description="Das Grundstücksdokument. Was nicht im Umfang steht, wird beim "
        "Anlegen entfernt und gar nicht erst gespeichert."
    )
    umfang: FreigabeUmfang = Field(
        default_factory=FreigabeUmfang,
        description="Was zusätzlich mitgeteilt wird. Fehlt es, wird nichts davon geteilt.",
    )


class FreigabeAngelegt(BaseModel):
    """A link that exists, from its owner's side."""

    id: str = Field(description="Der Schlüssel für den Link.")
    angelegt: datetime
    laeuft_ab: datetime = Field(
        description="Ab hier antwortet der Link, als gäbe es ihn nicht."
    )
    name: str | None = Field(
        default=None, description="Name des Grundstücks, damit die Liste lesbar ist."
    )
    grundstueck: str | None = Field(
        default=None,
        description="Die Kennung des geteilten Grundstücks, damit dessen Seite die "
        "eigenen Links zeigen kann.",
    )
    umfang: FreigabeUmfang | None = Field(
        default=None,
        description="Was der Link tatsächlich trägt, gelesen am gespeicherten "
        "Dokument statt an den damals gesetzten Schaltern.",
    )


class FreigabenAntwort(BaseModel):
    eintraege: list[FreigabeAngelegt] = Field(
        description="Alle offenen Freigaben dieses Kontos, neueste zuerst."
    )


class FreigabeAntwort(BaseModel):
    """What somebody with the link gets: the snapshot, and until when."""

    dokument: dict[str, Any] = Field(
        description="Das Grundstück, wie es beim Teilen aussah, beschränkt auf den "
        "gewählten Umfang."
    )
    angelegt: datetime = Field(description="Wann geteilt wurde; der Stand ist von da.")
    laeuft_ab: datetime


class SpeicherAnfrage(BaseModel):
    """A write, with the stand it builds on."""

    dokument: dict[str, Any] = Field(
        description="Das zu speichernde Dokument. Muss ein Objekt sein; der Inhalt bleibt unangetastet."
    )
    geaendert_am: datetime | None = Field(
        default=None,
        description=(
            "Der Stand, auf dem der Absender aufsetzt. null heißt „neu anlegen“. "
            "Weicht er vom gespeicherten ab, antwortet der Server mit 409 und dem "
            "aktuellen Stand, statt zu überschreiben."
        ),
    )

    @field_validator("geaendert_am")
    @classmethod
    def _with_time_zone(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class GrundstueckGespeichert(BaseModel):
    id: str
    geaendert_am: datetime = Field(
        description="Der neue Stand. Er gehört in die nächste Änderung dieses Eintrags."
    )


class EinstellungenAntwort(BaseModel):
    """The rest of the document: house types, destinations, the selection."""

    dokument: dict[str, Any] = Field(
        description="Das gespeicherte Dokument; ein leeres Objekt, solange nichts abgelegt wurde."
    )
    geaendert_am: datetime | None = Field(
        default=None,
        description="null, solange für dieses Konto nichts gespeichert ist.",
    )


class EinstellungenGespeichert(BaseModel):
    geaendert_am: datetime


# --------------------------------------------------------------------------
# Parcel search (POST /api/parcels/search)
#
# The search is a staircase that stops as early as it can, and it reports every
# step so the map can grow while it runs. Three kinds of object cross the wire:
# an *Indiz* (one statement about where the plot is, with the evidence for it),
# a *Kandidat* (one parcel that survived the hard filters), and the *Hülle* (the
# smallest unit every surviving candidate shares, for when no single parcel can
# be named). See docs/strategie/suchalgorithmus.html.
# --------------------------------------------------------------------------

# What an Indiz says something about.
IndizArt = Literal[
    "gemarkung",
    "flurstueck",
    "flaeche",
    "strasse",
    "gemeinde",
    "ort",
    "nutzung",
    "entfernung",
    "pin",
]

# Where it came from. The order is the order of trust, and it is the rule that
# settles a contradiction: an official extract outranks the attribute list,
# which outranks the body text, which outranks the platform's own pin.
IndizQuelle = Literal[
    "nutzer",
    "bild",
    "attribut",
    "fliesstext",
    "modell",
    "standortfeld",
    "pin",
]

# How a place named in the text relates to the plot. Measured: counting
# mentions picks the wrong place -- "Grimma" is named three times precisely
# because the plot is 6 km away from it -- so the relation is extracted and the
# frequency is not.
Ortsbeziehung = Literal["liegt_in", "liegt_an", "entfernt_von", "erwaehnt"]

SuchStatus = Literal["bestaetigt", "mehrdeutig", "erfolglos"]


class Entfernungsband(BaseModel):
    """The ring a stated distance admits, around a reference that is a *set*.

    „ca. 6 km bis Grimma" is not a radius. Measured from the parcel actually
    offered: the geocoder's point for Grimma lies 5.32 km away, the edge of the
    built-up area 5.32 km, its middle 6.25 km and the car route 7.37 km. So the
    reference is resolved to an outline rather than a point, the candidate
    carries the whole interval that outline admits, and the two are tested for
    overlap. ``innen_m`` and ``aussen_m`` are the statement's own interval.

    ``umriss`` is the built-up area the distance is measured from, in WGS 84.
    It travels because the band is only honest if it can be seen: the drawing
    -- the buffer outwards and the circle inwards -- belongs to the browser,
    like every other piece of geometry in this project.
    """

    meter: float
    innen_m: float
    aussen_m: float
    bezug: str
    # „strecke" for a plain kilometre figure, „auto", „fuss", „rad" or „zeit"
    # where the wording said how it was measured.
    modus: str
    # False when the reference could not be resolved to an outline -- a class
    # („Bushaltestelle"), a shop, or a name the cadastral directory does not
    # carry. Then the band is shown and nothing is computed from it.
    aufgeloest: bool = False
    umriss: dict[str, Any] | None = None
    mitte: dict[str, Any] | None = None


class Indiz(BaseModel):
    """One statement about where the plot is, with what backs it up.

    ``beleg`` is not decoration. A contradiction the user cannot look up is a
    contradiction they cannot resolve, so every Indiz carries the sentence it
    was read from -- or, for an image, the rectangle it was read out of.
    """

    id: str
    art: IndizArt
    wert: str
    # What the interface writes next to it. German, composed from a template,
    # never from a model -- see frontend/src/lib/findings.js for the rule.
    text: str
    beleg: str | None = None
    quelle: IndizQuelle
    sicherheit: float = Field(ge=0, le=1)
    beziehung: Ortsbeziehung | None = None
    # Key for a Gemarkung, municipality key for a Gemeinde: what the search
    # actually queries with, as opposed to what the text said.
    schluessel: str | None = None
    # Set when the user switched it off, or when a stronger Indiz refuted it.
    verworfen: bool = False
    # Why it was dropped, in one German sentence. Never silent.
    verworfen_grund: str | None = None
    # The picture this was read out of. A Beleg for an image is a line of OCR
    # text, which is the least checkable evidence in the whole search -- so when
    # a reading has to be *chosen*, the image travels with it and the choice is
    # made against the sheet rather than against a transcription of it.
    bild_url: str | None = None
    # The compound place name this district was taken out of, where it was one.
    # „Burghausen-Rückmarsdorf“ is no Gemarkung and both its halves are, so the
    # two readings are one statement admitting two districts -- not a
    # contradiction, and never a question. Same rule as several parcel numbers
    # from one source, which are a plot rather than a dispute.
    teil_von: str | None = None
    # The ring a stated distance admits, for an Indiz of art „entfernung“. It
    # may order the candidates and it may object; it may never confirm.
    band: Entfernungsband | None = None


class Konflikt(BaseModel):
    """Two or more Indizien of the same kind that cannot both be true.

    The search does not resolve this quietly. It follows the most trustworthy
    reading, says so, and offers the alternatives: a map extract naming one
    district and a location field naming another can both be honest -- the
    seller may have attached the wrong extract.
    """

    art: IndizArt
    frage: str
    # The Indiz ids in play, most trustworthy first.
    optionen: list[str]
    gewaehlt: str
    # Set once a hard filter settled it without asking -- a parcel number that
    # exists in exactly one of the contested districts, for instance.
    aufgeloest_durch: str | None = None


class KandidatProperties(BaseModel):
    kennzeichen: str | None = None
    gemarkung: str | None = None
    gemarkungsnummer: str | None = None
    flurstuecksnummer: str | None = None
    flaeche_amtlich_m2: float | None = None
    lagebezeichnung: str | None = None
    gemeinde: str | None = None
    nutzung: str | None = None


class Kandidat(BaseModel):
    """One parcel that survived every hard filter.

    ``punkte`` orders the list and nothing else. The verdict comes from the
    hard filters alone, which is why uncalibrated weights here cannot produce a
    wrong answer -- only an unhelpful ordering.
    """

    id: str
    geometry: dict[str, Any] | None = None
    properties: KandidatProperties
    punkte: float = 0.0
    # One German phrase per contribution: „an der Wiesenstraße", „Wohnbaufläche".
    begruendung: list[str] = Field(default_factory=list)


class Huelle(BaseModel):
    """The smallest unit every surviving candidate shares.

    "Ambiguous" is not a failure as long as the answer says what is settled.
    Five candidates on one street *is* an answer -- for the land value and for
    travel times it is often the whole answer.
    """

    art: Literal["flurstueck", "strasse", "gemarkung", "gemeinde", "offen"]
    text: str
    geometry: dict[str, Any] | None = None


class Suchgebiet(BaseModel):
    """One cadastral district the search is prepared to look in.

    Sent before any candidate exists, so the map has something to frame on
    while the staircase runs — and so the answer to "where could this be" is
    visible from the first second rather than only at the end. The outline is
    the district's own ``ave:KatasterBezirk`` boundary.
    """

    schluessel: str
    name: str
    anzahl: int | None = None
    geometry: dict[str, Any] | None = None


class SuchEreignis(BaseModel):
    """One line of the NDJSON stream.

    One object per line, four kinds. The map needs ``indiz`` and ``kandidaten``,
    the protocol needs ``phase``, and ``ergebnis`` closes the run. NDJSON over a
    chunked POST rather than Server-Sent Events: EventSource can only GET, so
    the indicia would have to be filed under an id first, and this backend has
    no database to file them in.
    """

    art: Literal["phase", "indiz", "konflikt", "gebiete", "kandidaten", "ergebnis", "fehler"]
    phase: str | None = None
    text: str | None = None
    indiz: Indiz | None = None
    konflikt: Konflikt | None = None
    # The live candidate set. Sent whole rather than as a delta: the map frames
    # itself on this set, and a frame derived from a patch is a frame that can
    # silently drift out of step with what is drawn.
    kandidaten: list[Kandidat] | None = None
    anzahl: int | None = None
    huelle: Huelle | None = None
    status: SuchStatus | None = None
    # The district wash under the candidates, when one district is settled.
    gemarkung_umriss: dict[str, Any] | None = None
    # The districts still in play, with their outlines. The search space, drawn.
    gebiete: list[Suchgebiet] | None = None
    anfragen: int | None = None


class ParcelSearchRequest(BaseModel):
    """Everything known about the listing, and nothing about who is selling it."""

    text: str | None = Field(default=None, max_length=200_000)
    titel: str | None = Field(default=None, max_length=500)
    adresse: str | None = Field(default=None, max_length=300)
    # The platform's own pin. Measured 6 235 m from the parcel actually offered,
    # because the platform geocodes its location field -- so it never narrows
    # the search, it only ever refutes a candidate.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    flaeche_m2: float | None = Field(default=None, gt=0, le=10_000_000)
    # The area exactly as the listing writes it („502 m²", „ca. 500 m²",
    # „ab 450 m²"). The wording decides where the tolerance staircase starts,
    # so it travels alongside the number.
    flaeche_text: str | None = Field(default=None, max_length=120)
    gemarkung: str | None = Field(default=None, max_length=120)
    flurstuecksnummer: str | None = Field(default=None, max_length=20)
    # The listing's images. Read only when the text carries no parcel number:
    # a seller who attaches a Geoportal print has already answered the question,
    # and Tesseract reads that print's title block reliably. Measured on a real
    # advert: one of seven images yielded „Flurstück 790/11", the other six
    # yielded nothing at all -- which is what makes reading every image and
    # filtering by pattern safer than classifying images first.
    bilder: list[str] = Field(default_factory=list, max_length=24)
    # Indicia the caller gathered elsewhere. Accepted as input so a channel
    # this server cannot run -- an image the browser holds but the backend
    # cannot fetch -- still has a way in.
    indizien: list[Indiz] = Field(default_factory=list)
    # Indiz ids the user switched off. The search runs again without them.
    verworfen: list[str] = Field(default_factory=list)
    # Which option of a conflict the user picked, as {art: indiz_id}.
    entscheidungen: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _something_to_go_on(self) -> "ParcelSearchRequest":
        if not any(
            (
                self.text,
                self.adresse,
                self.gemarkung,
                self.flurstuecksnummer,
                self.indizien,
                self.lat is not None and self.lon is not None,
            )
        ):
            raise ValueError(
                "Zum Suchen wird mindestens eine Angabe gebraucht: Anzeigentext, "
                "Adresse, Gemarkung, Flurstücksnummer oder eine Koordinate."
            )
        return self


class ParcelSearchResponse(BaseModel):
    """The whole run at once, for callers that cannot read a stream."""

    status: SuchStatus
    indizien: list[Indiz]
    konflikte: list[Konflikt]
    kandidaten: list[Kandidat]
    huelle: Huelle
    gemarkung_umriss: dict[str, Any] | None = None
    gebiete: list[Suchgebiet] = Field(default_factory=list)
    anfragen: int
    hinweis: str | None = None
