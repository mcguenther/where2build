"""Service instances shared across requests.

Cached rather than rebuilt per request so the MOTIS concurrency limit and the
cache handles stay process-wide. ``reset_services`` exists for tests.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from .address_index import AddressIndex, load_index as load_address_index
from .errors import RateLimitedError, UnauthorizedError
from .gemarkung_index import GemarkungDirectory, load_directory
from .ratelimit import RateLimiter, client_key, denied_message
from .services.airquality import AirQualityService
from .services.alkis import AlkisService
from .services.basemap import BasemapService
from .services.boris import BorisService
from .services.llm import LLMClient
from .services.luis import LuisService
from .services.motis import MotisService
from .services.nearby import NearbyService
from .services.oidc import Identity, OidcService
from .services.overpass import OverpassService
from .services.storage import Storage
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
def address_index() -> AddressIndex | None:
    """The official Hauskoordinaten, read from disk once per process.

    Tens of megabytes of JSON: parsing it per request would cost more than the
    upstream call it replaces. ``None`` when the file was never built here.
    """

    return load_address_index(get_settings().addresses.index_path)


@lru_cache(maxsize=1)
def boris_service() -> BorisService:
    settings = get_settings()
    return BorisService(settings.boris, settings.app)


@lru_cache(maxsize=1)
def luis_service() -> LuisService:
    settings = get_settings()
    return LuisService(settings.luis, settings.app)


@lru_cache(maxsize=1)
def air_quality_service() -> AirQualityService:
    settings = get_settings()
    return AirQualityService(settings.air_quality, settings.app)


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
def oidc_service() -> OidcService:
    settings = get_settings()
    return OidcService(settings.oidc, settings.app)


@lru_cache(maxsize=1)
def storage_service() -> Storage:
    """The account's copy of the document. Opens nothing until it is used."""

    return Storage(get_settings().storage)


NOT_SIGNED_IN = (
    "Für diesen Bereich ist eine Anmeldung nötig. Ohne Konto bleiben die "
    "Grundstücke in diesem Browser und lassen sich dort unverändert weiter "
    "bearbeiten."
)


def current_account(
    request: Request, service: OidcService = Depends(oidc_service)
) -> Identity:
    """Who is signed in -- or a 401.

    Checked before the storage routes ask whether this deployment even has a
    database: a request has to say who it is before the server tells it
    anything about itself, and "not signed in" is the answer the caller can
    actually act on.
    """

    identity = service.session_identity(request.cookies.get(service.settings.cookie_name))
    if identity is None:
        raise UnauthorizedError(NOT_SIGNED_IN)
    return identity


@lru_cache(maxsize=1)
def service_limiter() -> RateLimiter:
    """The budget for everything that asks an external service a question."""

    limits = get_settings().rate_limit
    return RateLimiter(
        limit=limits.service_calls, window_s=limits.window_s, max_clients=limits.max_clients
    )


@lru_cache(maxsize=1)
def map_limiter() -> RateLimiter:
    """The budget for map tiles, which are far more numerous and far cheaper."""

    limits = get_settings().rate_limit
    return RateLimiter(
        limit=limits.map_tiles, window_s=limits.window_s, max_clients=limits.max_clients
    )


def _spend(limiter: RateLimiter, request: Request, service: OidcService) -> None:
    """Draw one call from whoever is calling, or refuse with a 429.

    The identity is read here rather than through ``current_account`` because
    being signed out is not an error on these routes: it only changes whose
    budget is spent, from the account to the peer.
    """

    settings = get_settings()
    if not settings.rate_limit.enabled:
        return
    identity = service.session_identity(request.cookies.get(service.settings.cookie_name))
    decision = limiter.check(client_key(request, identity, settings.app.proxy_hops))
    if not decision.allowed:
        raise RateLimitedError(denied_message(decision), retry_after_s=decision.retry_after_s)


def service_budget(request: Request, service: OidcService = Depends(oidc_service)) -> None:
    _spend(service_limiter(), request, service)


def map_budget(request: Request, service: OidcService = Depends(oidc_service)) -> None:
    _spend(map_limiter(), request, service)


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
        address_index,
        boris_service,
        luis_service,
        air_quality_service,
        motis_service,
        overpass_service,
        nearby_service,
        tile_service,
        basemap_service,
        llm_client,
        oidc_service,
        storage_service,
        service_limiter,
        map_limiter,
    ):
        factory.cache_clear()
