"""Service instances shared across requests.

Cached rather than rebuilt per request so the MOTIS concurrency limit and the
cache handles stay process-wide. ``reset_services`` exists for tests.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from .address_index import AddressIndex, load_index as load_address_index
from .errors import AppError, ForbiddenError, RateLimitedError, UnauthorizedError
from .gemarkung_index import GemarkungDirectory, load_directory
from .ratelimit import RateLimiter, client_key, denied_message
from .telemetry import recorder, reset_recorder
from .services.admin import AdminStore
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
from .services.preview import PreviewService
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
def preview_service() -> PreviewService:
    """Draws and keeps the card a chat shows for a shared link."""

    return PreviewService(tile_service(), get_settings().app.cache_dir)


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


def signed_in(request: Request, service: OidcService = Depends(oidc_service)) -> Identity:
    """Who is signed in -- or a 401. Says nothing about what they may do.

    Checked before the storage routes ask whether this deployment even has a
    database: a request has to say who it is before the server tells it
    anything about itself, and "not signed in" is the answer the caller can
    actually act on.
    """

    identity = service.session_identity(request.cookies.get(service.settings.cookie_name))
    if identity is None:
        raise UnauthorizedError(NOT_SIGNED_IN)
    return identity


def current_account(identity: Identity = Depends(signed_in)) -> Identity:
    """Signed in, and not blocked.

    Every route that stores, shares or spends something takes this one. The
    administration area deliberately takes ``signed_in`` instead: an
    administrator whom the burst guard caught must still be able to reach the
    page that lifts the block, and a lockout with no way back in would be the
    one failure this whole feature cannot repair.
    """

    refuse_if_blocked(identity)
    return identity


@lru_cache(maxsize=1)
def admin_store() -> AdminStore:
    """The administration statements, over the storage pool."""

    return AdminStore(storage_service())


BLOCKED = (
    "Dieser Zugang ist vorübergehend gesperrt, weil in kurzer Zeit außergewöhnlich "
    "viele Anfragen von ihm kamen. Die Sperre endet von selbst; bei einem Irrtum "
    "hilft die Verwaltung des Betreibers weiter."
)


def refuse_if_blocked(identity: Identity | None) -> None:
    """A blocked account gets no further, on any route that spends anything.

    Read out of this process rather than out of the database: a check per
    request against Postgres would put a round trip in front of every call, and
    the block reaches the other workers on the next flush anyway -- at most
    ``ADMIN_FLUSH_S`` seconds, against an automatic block that is measured in
    an hour.
    """

    if identity is None:
        return
    block = recorder().blocked(identity.account_key)
    if block is not None:
        raise ForbiddenError(f"{BLOCKED} ({block.grund})")


async def current_admin(
    identity: Identity = Depends(signed_in),
    store: AdminStore = Depends(admin_store),
) -> Identity:
    """Who is signed in, if they administer this deployment -- or a 403.

    Two sources, and the configured one comes first on purpose: it is what
    survives an empty ``users`` table, which is exactly the state the red
    button leaves behind. A database that is unreachable therefore does not
    lock the configured administrator out of the area that would tell them so.
    """

    if await is_admin(identity, store):
        return identity
    raise ForbiddenError()


async def is_admin(identity: Identity, store: AdminStore) -> bool:
    if identity.account_key in get_settings().admin.bootstrap_accounts:
        return True
    if not store.configured:
        return False
    try:
        return await store.is_admin(identity.account_key)
    except AppError:
        # The database is down. Nobody is promoted while it is, and the
        # configured administrators above still get in.
        return False


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
    identity = service.session_identity(request.cookies.get(service.settings.cookie_name))
    # Before the budget, and regardless of whether the budget is switched on at
    # all: a block is not a quota, and a deployment that runs without a ceiling
    # is exactly the one that needs the block to still bite.
    refuse_if_blocked(identity)
    if not settings.rate_limit.enabled:
        return
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
        preview_service,
        basemap_service,
        llm_client,
        oidc_service,
        storage_service,
        service_limiter,
        map_limiter,
        admin_store,
    ):
        factory.cache_clear()
    reset_recorder()
