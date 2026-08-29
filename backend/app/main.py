"""FastAPI application for "Grundstücks-Check Sachsen".

The backend deliberately serves data only: every geometry operation (buffer,
rotation, collision) happens in the browser with Turf.js. What lives here is
the part a browser cannot do -- talking to the authority services, keeping
their answers in a cache, and turning pages into structured suggestions.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .errors import AppError
from .routers import (
    basemap,
    geocode,
    housetypes,
    landvalue,
    listings,
    nearby,
    parcels,
    reachability,
    tiles,
)
from .deps import nearby_service
from .schemas import DienstStatus, HealthResponse
from .settings import get_settings
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


def _poi_hinweis(status: dict[str, object]) -> str:
    """What /api/health says about the local POI index.

    The point of the sentence is the difference the frontend has to be able to
    make: a missing index is "not set up here", never "nothing nearby". So the
    message names the categories that go dark and the command that fills it.
    """

    kategorien = "Schule, Kindergarten, Park, Spielplatz, Supermarkt und Arztpraxis"
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
            f"python scripts/build_poi_index.py --download.{reason}"
        )
    datenstand = status.get("datenstand")
    stand = f", Stand {datenstand}" if datenstand else ""
    return (
        f"{status['anzahl']} Orte aus OpenStreetMap{stand} für {kategorien}. "
        "Haltestellen und Bahnhöfe kommen aus dem Fahrplan (MOTIS)."
    )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Grundstücks-Check Sachsen — Backend",
        version=__version__,
        description=DESCRIPTION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

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
                    name="boris",
                    konfiguriert=bool(current.boris.wms_url),
                    endpunkt=current.boris.wms_url,
                    hinweis="Bodenrichtwerte über GetFeatureInfo; Endpunkt trägt das Stichtagsjahr.",
                ),
                DienstStatus(
                    name="motis",
                    konfiguriert=bool(current.motis.base_url),
                    endpunkt=f"{current.motis.base_url.rstrip('/')}/api/v6/plan",
                    hinweis=(
                        "Routing (/api/reachability) und Adresssuche (/api/geocode); "
                        "öffentliche Instanz nur für den Prototyp."
                    ),
                ),
                DienstStatus(
                    name="poi",
                    konfiguriert=poi["konfiguriert"],
                    endpunkt=poi["pfad"],
                    hinweis=_poi_hinweis(poi),
                ),
                DienstStatus(
                    name="tiles",
                    konfiguriert=bool(current.tiles.dop_url),
                    endpunkt=current.tiles.dop_url,
                    hinweis="Ebenen: dop, webatlas, alkis.",
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
                    name="llm",
                    konfiguriert=current.llm.configured,
                    endpunkt=current.llm.base_url,
                    hinweis=(
                        f"Modell {current.llm.model}, Fetch-Engine {current.llm.fetch_engine}."
                        if current.llm.configured
                        else "Kein LLM_API_KEY gesetzt — Seiten können nicht ausgelesen werden."
                    ),
                ),
            ],
        )

    for module in (
        parcels,
        listings,
        housetypes,
        landvalue,
        geocode,
        reachability,
        nearby,
        tiles,
        basemap,
    ):
        app.include_router(module.router)

    return app


app = create_app()
