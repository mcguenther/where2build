"""Service instances shared across requests.

Cached rather than rebuilt per request so the MOTIS concurrency limit and the
cache handles stay process-wide. ``reset_services`` exists for tests.
"""

from __future__ import annotations

from functools import lru_cache

from .gemarkung_index import GemarkungDirectory, load_directory
from .services.alkis import AlkisService
from .services.basemap import BasemapService
from .services.boris import BorisService
from .services.llm import LLMClient
from .services.motis import MotisService
from .services.nearby import NearbyService
from .services.overpass import OverpassService
from .services.tiles import TileService
from .settings import Settings, get_settings


@lru_cache(maxsize=1)
def alkis_service() -> AlkisService:
    settings = get_settings()
    return AlkisService(settings.alkis, settings.app)


@lru_cache(maxsize=1)
def gemarkung_directory() -> GemarkungDirectory | None:
    """The cadastral district list, read from disk once per process.

    Half a megabyte of JSON parsed and folded on every request would be the
    single most expensive thing this backend does; the file only changes when
    ``scripts/build_gemarkung_index.py`` runs again.
    """

    return load_directory(get_settings().alkis.gemarkung_index_path)


@lru_cache(maxsize=1)
def boris_service() -> BorisService:
    settings = get_settings()
    return BorisService(settings.boris, settings.app)


@lru_cache(maxsize=1)
def motis_service() -> MotisService:
    settings = get_settings()
    return MotisService(settings.motis, settings.app)


@lru_cache(maxsize=1)
def overpass_service() -> OverpassService:
    settings = get_settings()
    return OverpassService(settings.overpass, settings.app)


@lru_cache(maxsize=1)
def nearby_service() -> NearbyService:
    settings = get_settings()
    return NearbyService(settings.nearby, motis_service(), overpass_service())


@lru_cache(maxsize=1)
def tile_service() -> TileService:
    settings = get_settings()
    return TileService(settings.tiles, settings.app)


@lru_cache(maxsize=1)
def basemap_service() -> BasemapService:
    settings = get_settings()
    return BasemapService(settings.basemap, settings.app)


@lru_cache(maxsize=1)
def llm_client() -> LLMClient:
    settings = get_settings()
    return LLMClient(settings.llm, settings.app)


def settings_dep() -> Settings:
    return get_settings()


def reset_services() -> None:
    """Drop cached settings and services (used when tests change the env)."""

    get_settings.cache_clear()
    for factory in (
        alkis_service,
        gemarkung_directory,
        boris_service,
        motis_service,
        overpass_service,
        nearby_service,
        tile_service,
        basemap_service,
        llm_client,
    ):
        factory.cache_clear()
