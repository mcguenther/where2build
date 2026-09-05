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
    text: str | None = Field(default=None, max_length=400_000)

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
    """One of three ways in: address, coordinate, or cadastral identifier.

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
        chosen = [by_address, by_point, by_parcel]
        if sum(chosen) == 0:
            raise ValueError(
                "Bitte Adresse, Koordinate (lat/lon) oder Gemarkung mit Flurstücksnummer angeben."
            )
        if sum(chosen) > 1:
            raise ValueError(
                "Bitte nur einen Weg angeben: Adresse, Koordinate oder Gemarkung "
                "mit Flurstücksnummer."
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


NACHBARN_HINWEIS = (
    "Umrisse aus OpenStreetMap, ohne Wandhöhen — daraus lässt sich nur das "
    "Mindestmaß von 3 m nach § 6 Abs. 5 SächsBO rechnen, nie 0,4 H. Ein "
    "Hinweis, keine bauordnungsrechtliche Prüfung."
)


class Nachbargebaeude(BaseModel):
    """One mapped building outline, as OpenStreetMap has it."""

    osm_id: str
    umriss: list[list[float]] = Field(
        description="Geschlossener Ring in [lon, lat], WGS84.", min_length=4
    )
    adresse: str | None = None
    geschosse: int | None = Field(
        default=None,
        description="Nur wenn OSM es führt; in sächsischen Wohnlagen fast nie.",
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
