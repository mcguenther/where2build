"""POST /api/parcels/resolve -- address, coordinate or cadastral identifier to parcels."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import alkis_service, motis_service
from ..errors import NotFoundError
from ..plausibility import assess
from ..schemas import GeocodeTreffer, ParcelCollection, ParcelResolveRequest
from ..services.alkis import AlkisService, Flurstueck, expand_gemarkung_key, to_collection
from ..services.motis import MotisService

router = APIRouter(prefix="/api/parcels", tags=["Flurstücke"])

GEOCODING_HINT = (
    "Die Adresse wurde über den Routing-Geocoder aufgelöst. Verbindlich sind die "
    "amtlichen Hauskoordinaten des GeoSN; bitte die Lage auf der Karte prüfen."
)

SHORT_KEY_HINT = (
    "Der Gemarkungsschlüssel „{eingegeben}“ wurde als „{vollstaendig}“ gesucht: in "
    "Sachsen ist er sechsstellig und beginnt mit der Landesnummer 14. Die Kartenebene "
    "„Flurstück“ im Geoportal zeigt nur die letzten vier Stellen."
)

NOT_FOUND_BY_IDENTIFIER = (
    "In der Gemarkung „{gemarkung}“ wurde die Flurstücksnummer {nummer} nicht "
    "gefunden. {schluessel}Bitte Gemarkung und Nummer prüfen (Schreibweise wie im "
    "Geoportal, etwa „85/1“) oder die Lage auf der Karte anklicken."
)

SHORT_KEY_EXPLANATION = (
    "Gesucht wurde mit dem vollständigen Schlüssel „{vollstaendig}“, denn in Sachsen "
    "ist der Gemarkungsschlüssel sechsstellig und beginnt mit der Landesnummer 14. "
)


def _ambiguous_number_hint(parcels: list[Flurstueck], zaehler: int) -> str | None:
    """Warn when a number without a denominator matched several parcels.

    A plot is normally a set of parcels, so the union itself is right -- but
    here the set is an artefact of an incomplete search key: 604 alone also
    finds 604/1 to 604/c. Say so rather than quietly summing five areas.
    """

    if len(parcels) < 2:
        return None
    nummern = sorted(
        f"{parcel.attributes.get('flstnrzae', '')}"
        + (f"/{parcel.attributes['flstnrnen']}" if parcel.attributes.get("flstnrnen") else "")
        for parcel in parcels
    )
    return (
        f"Zur Nummer „{zaehler}“ ohne Nenner gibt es in dieser Gemarkung mehrere "
        f"Flurstücke ({', '.join(nummern)}). Gezeigt wird ihre Vereinigung — bitte "
        "die vollständige Flurstücksnummer mit Nenner angeben, wenn nur eines gemeint ist."
    )


def _parcel_number(zaehler: int, nenner: int | str | None) -> str:
    return f"{zaehler}/{nenner}" if nenner is not None else str(zaehler)


@router.post("/resolve", response_model=ParcelCollection, summary="Flurstücke auflösen")
async def resolve(
    payload: ParcelResolveRequest,
    alkis: AlkisService = Depends(alkis_service),
    motis: MotisService = Depends(motis_service),
) -> ParcelCollection:
    hinweise: list[str] = []
    address_match: GeocodeTreffer | None = None

    if payload.gemarkung and payload.zaehler is not None:
        expanded = expand_gemarkung_key(payload.gemarkung)
        if expanded != payload.gemarkung.strip():
            hinweise.append(
                SHORT_KEY_HINT.format(
                    eingegeben=payload.gemarkung.strip(), vollstaendig=expanded
                )
            )
        parcels = await alkis.by_gemarkung(payload.gemarkung, payload.zaehler, payload.nenner)
        if not parcels:
            # The generic "nothing found" would send the user back to guessing,
            # which is what the short key cost one already.
            raise NotFoundError(
                NOT_FOUND_BY_IDENTIFIER.format(
                    gemarkung=payload.gemarkung.strip(),
                    nummer=_parcel_number(payload.zaehler, payload.nenner),
                    schluessel=(
                        SHORT_KEY_EXPLANATION.format(vollstaendig=expanded)
                        if expanded != payload.gemarkung.strip()
                        else ""
                    ),
                )
            )
        if payload.nenner is None:
            hint = _ambiguous_number_hint(parcels, payload.zaehler)
            if hint:
                hinweise.append(hint)
    elif payload.lat is not None and payload.lon is not None:
        parcels = await alkis.by_point(payload.lat, payload.lon)
    else:
        assert payload.address is not None
        # The candidate rather than the bare coordinate: what the geocoder
        # matched -- a place, a stop, a house number -- decides whether the
        # answer can be a plot at all.
        treffer = await motis.geocode_candidates(payload.address, limit=1)
        if not treffer:
            raise NotFoundError("Zu dieser Adresse wurde keine Koordinate gefunden.")
        address_match = treffer[0]
        parcels = await alkis.by_point(address_match.lat, address_match.lon)
        hinweise.append(GEOCODING_HINT)

    return to_collection(
        parcels,
        hinweis=" ".join(hinweise) or None,
        plausibility=assess(parcels, payload.expected_area_m2, address_match),
    )
