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

from . import __version__
from .errors import AppError
from .routers import housetypes, landvalue, listings, parcels, reachability, tiles
from .schemas import DienstStatus, HealthResponse
from .settings import get_settings

logger = logging.getLogger(__name__)

DESCRIPTION = (
    "Datendienste für den Grundstücks-Check Sachsen: amtliche Flurstücke (ALKIS), "
    "Bodenrichtwerte (BORIS), multimodale Erreichbarkeit (MOTIS), Kartenkacheln "
    "der GeoSN-WMS sowie das Auslesen von Inseraten und Haustypen."
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

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep the machine-readable part, but lead with a sentence a user can read.
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Die Anfrage ist unvollständig oder ungültig.",
                "felder": [
                    {"pfad": [str(part) for part in error.get("loc", [])], "meldung": error.get("msg")}
                    for error in exc.errors()
                ],
            },
        )

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
                    hinweis="Routing und Geocoding; öffentliche Instanz nur für den Prototyp.",
                ),
                DienstStatus(
                    name="tiles",
                    konfiguriert=bool(current.tiles.dop_url),
                    endpunkt=current.tiles.dop_url,
                    hinweis="Ebenen: dop, webatlas, alkis.",
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

    for module in (parcels, listings, housetypes, landvalue, reachability, tiles):
        app.include_router(module.router)

    return app


app = create_app()
