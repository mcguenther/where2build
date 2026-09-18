"""FastAPI application for "Grundstücks-Check Sachsen".

The backend deliberately serves data only: every geometry operation (buffer,
rotation, collision) happens in the browser with Turf.js. What lives here is
the part a browser cannot do -- talking to the authority services, keeping
their answers in a cache, and turning pages into structured suggestions.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .address_index import AddressIndex
from .errors import AppError
from .routers import (
    auth,
    basemap,
    gemarkungen,
    geocode,
    housetypes,
    landvalue,
    listings,
    nearby,
    neighbours,
    parcels,
    reachability,
    search,
    sitechecks,
    shares,
    lehrbuch,
    storage,
    tiles,
)
from .deps import (
    address_index,
    gemarkung_directory,
    map_budget,
    nearby_service,
    service_budget,
    storage_service,
)
from .ratelimit import allowance_text, tile_allowance_text, window_text
from .services import ocr
from .services.storage import mib
from .schemas import DienstStatus, HealthResponse
from .settings import Settings, get_settings
from .validation import readable_validation_error

logger = logging.getLogger(__name__)

DESCRIPTION = (
    "Datendienste für den Grundstücks-Check Sachsen: amtliche Flurstücke (ALKIS), "
    "Bodenrichtwerte (BORIS), multimodale Erreichbarkeit (MOTIS), Kartenkacheln "
    "der GeoSN-WMS, die Vektor-Hintergrundkarte sowie das Auslesen von Inseraten "
    "und Haustypen."
)

# The framework answers these itself, in English; the browser shows whatever is
# in `detail`, so they get a German sentence like every other error.
FRAMEWORK_MESSAGES = {
    404: "Diese Adresse gibt es auf dem Server nicht.",
    405: "Diese Adresse nimmt diese Anfrageart nicht entgegen.",
    413: "Die Anfrage ist zu groß.",
    422: "Die Anfrage ist unvollständig oder ungültig.",
}


def _poi_hinweis(status: dict[str, Any]) -> str:
    """What /api/health says about the six OpenStreetMap categories.

    The point of the sentence is the difference the frontend has to be able to
    make: no source is "not set up here", never "nothing nearby". So the message
    names the categories that go dark and the command that fills it.
    """

    kategorien = "Schule, Kindergarten, Park, Spielplatz, Supermarkt und Arztpraxis"
    fahrplan = "Haltestellen und Bahnhöfe kommen aus dem Fahrplan (MOTIS)."
    overpass = status.get("overpass") or {}
    if not status["konfiguriert"]:
        reason = (
            f" Die vorhandene Datei ist unbrauchbar: {status['fehler']}."
            if status.get("fehler")
            else ""
        )
        return (
            f"Kein Umgebungsverzeichnis vorhanden — {kategorien} können nicht "
            "beantwortet werden; Haltestellen und Bahnhöfe kommen aus dem "
            "Fahrplan und funktionieren weiterhin. Erzeugen mit: "
            "python scripts/build_poi_index.py --download — oder für den "
            f"Prototyp OVERPASS_ENABLED=true setzen.{reason}"
        )
    if status.get("quelle") == "overpass":
        return (
            f"Kein lokales Verzeichnis — {kategorien} werden bei jeder Anfrage "
            f"live über Overpass ({overpass.get('endpunkt')}) geholt und "
            "zwischengespeichert. Das ist eine Prototyp-Abkürzung: für den "
            "Dauerbetrieb ein eigenes Verzeichnis erzeugen "
            f"(python scripts/build_poi_index.py --download) oder eine eigene "
            f"Overpass-Instanz eintragen. {fahrplan}"
        )
    datenstand = status.get("datenstand")
    stand = f", Stand {datenstand}" if datenstand else ""
    return f"{status['anzahl']} Orte aus OpenStreetMap{stand} für {kategorien}. {fahrplan}"


def _ocr_hinweis(status: dict[str, Any]) -> str:
    """What /api/health says about reading a listing's images.

    Same distinction as the POI sentence: absent is "not set up here", never
    "the listing had nothing". The search falls back to the text, which is
    where most listings say it anyway.
    """

    if not status["konfiguriert"]:
        missing = (
            "Tesseract ist nicht installiert"
            if not status["pfad"]
            else "die deutschen Sprachdaten fehlen"
        )
        return (
            f"Bilder von Inseraten werden nicht gelesen — {missing}. Ein beigelegter "
            "Katasterauszug nennt Gemarkung und Flurstück oft im Klartext; ohne "
            "Texterkennung sucht /api/parcels/search allein über den Anzeigentext. "
            "Nachrüsten mit: apt-get install tesseract-ocr tesseract-ocr-deu"
        )
    return (
        "Bilder eines Inserats werden auf „Flurstück“ und „Gemarkung“ gelesen "
        f"(Tesseract, Sprachen: {', '.join(status['sprachen'])}). Gemessen: von sieben "
        "Bildern eines echten Inserats trug eines den Katasterauszug, die übrigen "
        "sechs lieferten nichts — deshalb wird jedes Bild gelesen und nach Muster "
        "gefiltert, statt Bilder vorher zu sortieren."
    )


def _anmeldung_hinweis(settings: Settings) -> str:
    """What /api/health says about signing in.

    Same shape as the POI and OCR sentences: absent is "not set up here", never
    a fault. Without a provider the app keeps every plot in the browser and
    works exactly as before, so the message says that first and names the
    variables that are still missing second.
    """

    missing = settings.oidc.missing
    if missing:
        return (
            "Keine Anmeldung eingerichtet; die Anwendung ist ohne Konto vollständig "
            "benutzbar und die Grundstücke bleiben im Browser. Zum Einrichten fehlt: "
            f"{', '.join(missing)}. Der Anbieter ist frei wählbar (Authentik, Keycloak, Google); "
            "die Endpunkte kommen aus <OIDC_ISSUER>/.well-known/openid-configuration."
        )
    return (
        f"Anmeldung über {settings.oidc.issuer} (Authorization Code mit PKCE, "
        f"Scopes: {settings.oidc.scopes}). Der Browser bekommt kein Token, sondern "
        "ein signiertes HttpOnly-Cookie; gespeichert werden nur Issuer, Subject und "
        "Anzeigename. Ohne Anmeldung bleibt alles wie bisher."
    )


def _speicher_hinweis(settings: Settings) -> str:
    """What /api/health says about the server-side storage.

    Same shape as the sign-in and the OCR sentence: absent is "not set up
    here", never a fault. Without a database the application keeps every plot
    in the browser and works exactly as it always has, so the message says that
    first and what to set second.
    """

    storage_settings = settings.storage
    if not storage_settings.configured:
        return (
            "Kein Serverspeicher eingerichtet; die Grundstücke bleiben in dem Browser, "
            "in dem sie angelegt wurden, und die Anwendung ist damit vollständig "
            "benutzbar. Zum Einrichten DATABASE_URL auf eine Postgres-Datenbank setzen "
            "(postgresql://nutzer:passwort@host:5432/where2build); die Tabellen legt "
            "der Server beim Start selbst an."
        )
    return (
        "Grundstücke, Haustypen und Ziele liegen je Konto in Postgres und stehen damit "
        "auf jedem Gerät zur Verfügung; der Browser behält seine eigene Kopie. Grenzen "
        f"je Konto: höchstens {storage_settings.max_plots_per_account} Grundstücke, "
        f"ein Eintrag höchstens {mib(storage_settings.max_document_bytes)}. Ohne Anmeldung "
        "bleibt alles im Browser."
    )


def _kontingent_hinweis(settings: Settings) -> str:
    """What /api/health says about the per-account request budget.

    Same shape as the sentences above: the interesting half is what applies
    here, not that a feature exists. Off is a legitimate deployment (one
    person, one machine), so that reads as a setting and not as a gap.
    """

    limits = settings.rate_limit
    fenster = window_text(limits.window_s)
    if not limits.enabled:
        return (
            "Kein Abrufkontingent; jeder Zugang darf beliebig viele Abrufe an die "
            "fremden Dienste auslösen. Das ist die Einstellung für den Einzelplatz. "
            "Für einen Betrieb mit Konten RATELIMIT_ENABLED=true setzen: die fremden "
            "Dienste (Overpass, Transitous) sind mitbenutzt, nicht gemietet."
        )
    zurechnung = (
        "Nicht angemeldete Abrufe zählen auf die Gegenstelle der Verbindung "
        "(APP_PROXY_HOPS=0, also kein eigener Proxy davor)."
        if settings.app.proxy_hops == 0
        else (
            "Nicht angemeldete Abrufe zählen auf die Adresse, die der eigene Proxy "
            f"einträgt (APP_PROXY_HOPS={settings.app.proxy_hops})."
        )
    )
    return (
        f"Je Konto höchstens {allowance_text(limits.service_calls)} {fenster} an die fremden "
        f"Dienste (Kataster, Bodenrichtwert, Standort, Routing, Umgebung, Inserate) "
        f"und {tile_allowance_text(limits.map_tiles)} {fenster}; darüber antwortet der Server "
        f"429 mit Retry-After. {zurechnung} Gezählt wird im Arbeitsspeicher dieses "
        "Prozesses, die Grenze gilt also je Arbeitsprozess."
    )


def _adressen_hinweis(index: AddressIndex | None) -> str:
    """What /api/health says about the official Hauskoordinaten.

    Same distinction the POI sentence makes: absent is "not set up here", never
    "Saxony has no addresses". Naming the fallback matters too — geocoding does
    not stop working without this file, it only stops being official.
    """

    if index is None:
        return (
            "Keine amtlichen Hauskoordinaten auf diesem Server — die Adresssuche "
            "beantwortet /api/geocode allein über den Routing-Geocoder (MOTIS), "
            "dessen Koordinaten nicht amtlich sind. Erzeugen mit: "
            "python scripts/build_address_index.py --download"
        )
    stand = f", Stand {index.stand}" if index.stand else ""
    return (
        f"{index.count} amtliche Adressen des GeoSN in {index.street_count} Straßen"
        f"{stand}. Sie beantworten /api/geocode zuerst; Haltestellen, Orte und "
        "alles außerhalb Sachsens kommen weiterhin aus MOTIS."
    )


def _llm_hinweis(current: Settings) -> str:
    """Which provider answered, and what is missing where nothing can.

    The provider is named because it is now a choice: „auto" resolves it off
    the endpoint, and somebody who pasted a URL should be able to see which of
    the two wire formats their server is about to speak.
    """

    llm = current.llm
    if not llm.configured:
        return (
            f"Anbieter {llm.provider}, aber kein LLM_API_KEY gesetzt — "
            "Seiten können nicht ausgelesen werden."
        )
    fetch = (
        "kann Seiten selbst abrufen"
        if llm.provider in ("openrouter", "anthropic")
        else "kann Seiten nicht selbst abrufen — dafür das Einfügen-Feld"
    )
    key = "" if llm.needs_key else ", ohne Schlüssel"
    return f"Anbieter {llm.provider}{key}, Modell {llm.model_id}; {fetch}."


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Open the server storage, or do nothing at all.

    Without DATABASE_URL there is no connection attempt: a development machine
    must not need Postgres before it can resolve a parcel, and a start-up that
    fails on a database nobody configured would make the whole backend look
    broken. With one, the schema is applied here (CREATE TABLE IF NOT EXISTS,
    see app/schema.sql) so the first request finds its tables.

    A database that is configured but unreachable is logged and nothing more.
    Everything else this backend does -- parcels, tiles, routing, the search --
    works without it, and refusing to start would take all of that down over
    one feature. The first request that needs a connection tries again and
    answers 502 with a German sentence if it still cannot get one.
    """

    store = storage_service()
    try:
        await store.start()
    except AppError as exc:
        logger.warning("Server storage did not open at start-up: %s", exc.message)
    try:
        yield
    finally:
        await store.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Grundstücks-Check Sachsen — Backend",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=False,
        # PUT and DELETE are the account storage; everything else is GET or POST.
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        # `body` is the sentence for almost every error and a little more for
        # a write conflict, which has to carry what is stored.
        return JSONResponse(
            status_code=exc.status_code, content=exc.body, headers=exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Starlette's own answers ("Not Found", "Method Not Allowed") are
        # English and reach the browser like any other error would.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": FRAMEWORK_MESSAGES.get(exc.status_code, str(exc.detail))},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # The frontend shows `detail`, so `detail` carries the sentence that
        # says what to change; `felder` keeps the machine-readable part.
        return JSONResponse(status_code=422, content=readable_validation_error(exc.errors()))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Never let a stack trace reach the browser.
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Unerwarteter Fehler im Server."},
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["Betrieb"], summary="Zustand")
    async def health() -> HealthResponse:
        current = get_settings()
        poi = nearby_service().index_status()
        ocr_status = ocr.status()
        verzeichnis = gemarkung_directory()
        adressen = address_index()
        return HealthResponse(
            version=__version__,
            dienste=[
                DienstStatus(
                    name="alkis",
                    konfiguriert=bool(current.alkis.wfs_url),
                    endpunkt=current.alkis.wfs_url,
                    hinweis="Flurstücke, amtliche Fläche aus dem Attribut „flaeche“.",
                ),
                DienstStatus(
                    name="gemarkungen",
                    konfiguriert=verzeichnis is not None,
                    endpunkt=str(current.alkis.gemarkung_index_path),
                    hinweis=(
                        f"{len(verzeichnis)} Gemarkungen, Stand {verzeichnis.stand}, "
                        "für die Auswahlliste bei der Flurstückseingabe."
                        if verzeichnis is not None
                        else "Kein Gemarkungsverzeichnis vorhanden — erzeugen mit: "
                        "python scripts/build_gemarkung_index.py"
                    ),
                ),
                DienstStatus(
                    name="hauskoordinaten",
                    konfiguriert=adressen is not None,
                    endpunkt=str(current.addresses.index_path),
                    hinweis=_adressen_hinweis(adressen),
                ),
                DienstStatus(
                    name="boris",
                    konfiguriert=bool(current.boris.wms_url),
                    endpunkt=current.boris.wms_url,
                    hinweis="Bodenrichtwerte über GetFeatureInfo; Endpunkt trägt das Stichtagsjahr.",
                ),
                DienstStatus(
                    name="luis",
                    konfiguriert=bool(current.luis.base_url),
                    endpunkt=current.luis.base_url,
                    hinweis=(
                        "Lärm, Trinkwasserschutz, Schutzgebiete, Hochwasser, Radon, "
                        "Hangneigung und Baugrund über /api/site-checks — gefragt wird "
                        "mit dem Flurstücksumring, nicht mit einem Punkt."
                    ),
                ),
                DienstStatus(
                    name="luftqualitaet",
                    konfiguriert=bool(current.air_quality.base_url),
                    endpunkt=f"{current.air_quality.base_url}/stations/json",
                    hinweis=(
                        "Messwerte der nächstgelegenen Station, die tatsächlich "
                        f"antwortet, im Umkreis von {current.air_quality.max_distance_km:.0f} km."
                    ),
                ),
                DienstStatus(
                    name="motis",
                    konfiguriert=bool(current.motis.base_url),
                    endpunkt=f"{current.motis.base_url.rstrip('/')}/api/v6/plan",
                    hinweis=(
                        "Routing (/api/reachability) und in /api/geocode alles, was die "
                        "amtlichen Hauskoordinaten nicht beantworten: Haltestellen, Orte "
                        "und Adressen außerhalb Sachsens. Öffentliche Instanz nur für "
                        "den Prototyp."
                    ),
                ),
                DienstStatus(
                    name="poi",
                    konfiguriert=poi["konfiguriert"],
                    endpunkt=(
                        poi["overpass"]["endpunkt"]
                        if poi.get("quelle") == "overpass"
                        else poi["pfad"]
                    ),
                    hinweis=_poi_hinweis(poi),
                ),
                DienstStatus(
                    name="tiles",
                    konfiguriert=bool(current.tiles.dop_url),
                    endpunkt=current.tiles.dop_url,
                    hinweis=(
                        "Ebenen: dop, webatlas, alkis (GeoSN-WMS) sowie laerm und "
                        "laerm-nacht (Lärmkartierung über den ArcGIS-export-Endpunkt, "
                        "der selbst nach Web Mercator rechnet)."
                    ),
                ),
                DienstStatus(
                    name="basemap",
                    konfiguriert=bool(current.basemap.upstream_url),
                    endpunkt=(
                        f"{current.basemap.upstream_url.rstrip('/')}/"
                        f"{current.basemap.style_path.lstrip('/')}"
                    ),
                    hinweis=(
                        "Vektor-Hintergrundkarte über /api/basemap/style.json; der Browser "
                        "spricht nur mit diesem Backend."
                    ),
                ),
                DienstStatus(
                    name="texterkennung",
                    konfiguriert=ocr_status["konfiguriert"],
                    endpunkt=ocr_status["pfad"],
                    hinweis=_ocr_hinweis(ocr_status),
                ),
                DienstStatus(
                    name="anmeldung",
                    konfiguriert=current.oidc.configured,
                    endpunkt=current.oidc.issuer or None,
                    hinweis=_anmeldung_hinweis(current),
                ),
                DienstStatus(
                    name="kontingent",
                    konfiguriert=current.rate_limit.enabled,
                    endpunkt=None,
                    hinweis=_kontingent_hinweis(current),
                ),
                DienstStatus(
                    name="speicher",
                    konfiguriert=current.storage.configured,
                    endpunkt=current.storage.endpoint,
                    hinweis=_speicher_hinweis(current),
                ),
                DienstStatus(
                    name="llm",
                    konfiguriert=current.llm.configured,
                    # The endpoint actually in play, with the provider's own
                    # default filled in — a deployment that named only a
                    # provider would otherwise see an empty field and think
                    # nothing was set.
                    endpunkt=current.llm.endpoint,
                    hinweis=_llm_hinweis(current),
                ),
            ],
        )

    # Three groups, and the grouping *is* the decision about who pays into the
    # per-account budget (see app/ratelimit.py and § 5 of
    # docs/entscheidungen/startseite-und-konten.md).
    #
    # Every one of these turns one request into at least one request to
    # somebody else's server: the cadastral WFS, BORIS, the LUIS environmental
    # server, the UBA, MOTIS/Transitous, a portal page, an Overpass instance or
    # the model. `search` is the most expensive of them by far -- one call is a
    # whole staircase of WFS requests -- and still counts as one, which is why
    # the budget is set well below what the upstreams would tolerate.
    for module in (
        parcels,
        search,
        listings,
        housetypes,
        landvalue,
        geocode,
        reachability,
        sitechecks,
        nearby,
        neighbours,
    ):
        app.include_router(module.router, dependencies=[Depends(service_budget)])

    # Tiles go outward too, so exempting them would be a hole rather than a
    # decision -- but one screen is dozens of them and the disk cache is shared
    # across everybody, so the second view of an area costs nothing upstream.
    # They get their own, far wider budget instead of the same one. Worth
    # knowing: a 429 here shows as a missing tile, not as a sentence, because
    # MapLibre and <img> read the status and not the body. That is the other
    # reason the number is generous.
    for module in (tiles, basemap):
        app.include_router(module.router, dependencies=[Depends(map_budget)])

    # And these ask nothing of anybody, so they pay nothing:
    # `gemarkungen` is served from a committed file and never touches the WFS,
    # `storage` speaks only to our own Postgres and has limits of its own
    # (200 plots, 2 MiB per document), and `auth` does talk to the identity
    # provider -- but that is this deployment's own provider, not a service
    # being borrowed, and a budget on signing in would lock people out of the
    # very thing that gives them a budget.
    # `shares` is in here for the same reason as `storage`: it speaks only to
    # our own database. Worth knowing that one of its routes has no session at
    # all -- a shared link is meant to be opened by whoever was sent it, so the
    # token is the access. See the module docstring.
    # `lehrbuch` is in here too: it reads our own divergence log, which is
    # either our own Postgres or a file on this machine.
    for module in (auth, gemarkungen, storage, shares, lehrbuch):
        app.include_router(module.router)

    return app


app = create_app()
