"""Pydantic models -- the contract between extraction, geodata services and the UI.

Deliberately absent: any contact detail from a listing (agent, phone, name).
The project decided not to hold personal data, so the schema does not carry
those fields in the first place.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, HttpUrl, model_validator

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
    nenner: int | None = None


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


class ParcelResolveRequest(BaseModel):
    """One of three ways in: address, coordinate, or cadastral identifier."""

    address: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    gemarkung: str | None = Field(default=None, max_length=120)
    zaehler: int | None = Field(default=None, ge=0)
    nenner: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _exactly_one_way_in(self) -> "ParcelResolveRequest":
        by_address = bool(self.address and self.address.strip())
        by_point = self.lat is not None and self.lon is not None
        by_parcel = bool(self.gemarkung and self.zaehler is not None)
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat und lon müssen gemeinsam angegeben werden.")
        chosen = [by_address, by_point, by_parcel]
        if sum(chosen) == 0:
            raise ValueError(
                "Bitte Adresse, Koordinate (lat/lon) oder Gemarkung mit Zähler angeben."
            )
        if sum(chosen) > 1:
            raise ValueError(
                "Bitte nur einen Weg angeben: Adresse, Koordinate oder Gemarkung mit Zähler."
            )
        return self


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


class ParcelCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    crs_hinweis: str = "EPSG:4326 (WGS84); Längen und Flächen wurden in EPSG:25833 gerechnet."
    features: list[ParcelFeature]
    grundstueck: GrundstueckFeature
    quelle: str = "Landesamt für Geobasisinformation Sachsen (GeoSN), dl-de/by-2-0"
    hinweis: str | None = None


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
    hinweis: str = (
        "Zonenwert nach § 196 BauGB. Nach § 15 Abs. 2 ImmoWertV kann ein einzelnes "
        "Grundstück innerhalb der Zone abweichend genutzt werden — dann gilt der "
        "Zonenwert für dieses Grundstück nicht."
    )
    quelle: str = "Gutachterausschüsse für Grundstückswerte im Freistaat Sachsen (BORIS Sachsen)"


# --------------------------------------------------------------------------
# Reachability
# --------------------------------------------------------------------------

# Mode names follow MOTIS semantics; "bike_transit" means bike to the first
# stop and public transport from there.
Modus = Literal["car", "bike", "walk", "transit", "bike_transit"]


class Koordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Ziel(Koordinate):
    id: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=200)


class ReachabilityRequest(BaseModel):
    origin: Koordinate
    destinations: list[Ziel] = Field(min_length=1, max_length=20)
    modes: list[Modus] = Field(default_factory=lambda: ["car", "bike", "transit"], min_length=1)
    # Departure time; MOTIS defaults to "now" when omitted.
    time: datetime | None = None


class Teilstrecke(BaseModel):
    mode: str
    duration_s: int
    von: str | None = None
    nach: str | None = None


class RouteErgebnis(BaseModel):
    destination_id: str
    mode: Modus
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
