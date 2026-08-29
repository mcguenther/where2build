"""Configuration.

Every external service is addressed through settings only -- no provider is
hard-wired. Each group has its own env prefix so a deployment can swap, for
example, the LLM provider by changing LLM_BASE_URL and LLM_MODEL alone.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to the backend package, not the working directory: the documented
# start command runs uvicorn from the repository root, and a CWD-relative path
# would silently leave every key unset there.
_ENV_FILE = (Path(__file__).resolve().parent.parent / ".env", ".env")

# Same reasoning for the POI index: it is a build artefact next to the code,
# not something to look for in whatever directory uvicorn happened to start in.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class AppSettings(BaseSettings):
    """Process-wide settings (env prefix ``APP_``)."""

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=_ENV_FILE, extra="ignore")

    cors_origins: list[str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        description="Allowed browser origins; defaults cover the Vite dev and preview servers.",
    )
    cache_dir: Path = Path(".cache")
    # Sent to every upstream service. Transitous requires a contact address in the
    # User-Agent, so keep a real one here in deployments.
    user_agent: str = "GrundstuecksCheckSachsen/0.1 (+https://github.com/; kontakt@example.org)"
    # Listing portals answer a plain library user agent with a challenge page,
    # so requests to them identify as a browser instead.
    portal_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
    http_timeout_s: float = 30.0


class AlkisSettings(BaseSettings):
    """ALKIS WFS of the GeoSN (env prefix ``ALKIS_``)."""

    model_config = SettingsConfigDict(env_prefix="ALKIS_", env_file=_ENV_FILE, extra="ignore")

    wfs_url: str = "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs"
    version: str = "2.0.0"
    # ALKIS delivers ETRS89/UTM33N. Lengths and areas are computed here, the API
    # hands out WGS84 for the map.
    srid: int = 25833
    max_features: int = 200
    # Half-edge of the bounding box (metres) used when resolving a coordinate.
    point_buffer_m: float = 1.0
    cache_ttl_s: int = 7 * 24 * 3600


class BorisSettings(BaseSettings):
    """BORIS Sachsen WMS (env prefix ``BORIS_``)."""

    model_config = SettingsConfigDict(env_prefix="BORIS_", env_file=_ENV_FILE, extra="ignore")

    # The endpoint carries the reference year; re-check it once a year.
    wms_url: str = "https://www.landesvermessung.sachsen.de/fp/httpproxy/svcdep/wms/boris_2026"
    layer: str = "brw_2026"
    portal_url: str = "https://www.boris.sachsen.de/"
    cache_ttl_s: int = 30 * 24 * 3600


class MotisSettings(BaseSettings):
    """MOTIS / Transitous routing (env prefix ``MOTIS_``)."""

    model_config = SettingsConfigDict(env_prefix="MOTIS_", env_file=_ENV_FILE, extra="ignore")

    base_url: str = "https://api.transitous.org"
    timeout_s: float = 30.0
    # Transitous is a volunteer service; keep concurrent load low.
    max_concurrency: int = 2
    max_direct_time_s: int = 7200
    # Bike feeders need more than the MOTIS default of 900 s.
    max_pre_transit_time_s: int = 1800
    cache_ttl_s: int = 3600
    # Stop positions and the modes serving them change on the order of days,
    # so they get a far longer life than a routing answer.
    stops_cache_ttl_s: int = 24 * 3600
    # Walking times move with the street network, which moves slowly.
    matrix_cache_ttl_s: int = 7 * 24 * 3600


class NearbySettings(BaseSettings):
    """"Was ist in der Nähe?" -- POI index and its search budget (env prefix ``NEARBY_``).

    The transit half of this feature needs nothing here: it comes from the same
    MOTIS instance the routing uses. What is configured here is the local
    OpenStreetMap index for schools, parks and the rest, which is built by
    ``scripts/build_poi_index.py`` and may legitimately be absent.
    """

    model_config = SettingsConfigDict(env_prefix="NEARBY_", env_file=_ENV_FILE, extra="ignore")

    poi_index_path: Path = _BACKEND_DIR / "data" / "poi-sachsen.json"
    # The server's own cap on `one-to-many`; asking for more is a 422 from MOTIS.
    max_candidates: int = 128
    # Ceiling for the routing search. 90 minutes on foot is far past the point
    # where "the nearest one" still means anything.
    max_time_s: int = 5400
    # How far MOTIS may look for a street to attach a candidate point to.
    max_matching_distance_m: int = 250
    # Rounding of the stop bounding box, in degrees, so nearby plots share a
    # cache entry instead of each cutting its own.
    bbox_grid_deg: float = 0.02
    # Lines per stop are an extra request each; cap what one answer can cost.
    max_line_lookups: int = 6


class TilesSettings(BaseSettings):
    """WMS raster proxy (env prefix ``TILES_``).

    Authority WMS services are fronted by this proxy because a browser cannot
    reasonably talk to them directly (CORS varies, and every tile should be
    cached on disk rather than refetched per page view).
    """

    model_config = SettingsConfigDict(env_prefix="TILES_", env_file=_ENV_FILE, extra="ignore")

    dop_url: str = "https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest"
    dop_layers: str = "sn_dop_020"
    webatlas_url: str = "https://geodienste.sachsen.de/wms_geosn_webatlas-sn/guest"
    webatlas_layers: str = "Vegetation,Siedlung,Gewaesser,Verkehr,Administrative_Einheiten,Beschriftung"
    alkis_url: str = "https://geodienste.sachsen.de/wms_geosn_alkis-adv/guest"
    alkis_layers: str = "adv_alkis_tatsaechliche_nutzung,adv_alkis_verkehr,adv_alkis_siedlung"
    # XYZ tiles are Web Mercator. Should a service reject EPSG:3857, EPSG:4326
    # also works -- the axis order is handled per CRS.
    crs: str = "EPSG:3857"
    image_format: str = "image/png"
    tile_size: int = 256
    transparent: bool = True
    cache_ttl_s: int = 30 * 24 * 3600
    max_zoom: int = 21


class BasemapSettings(BaseSettings):
    """Vector basemap proxy (env prefix ``BASEMAP_``).

    MapLibre would otherwise talk to OpenFreeMap directly, which fails in a
    sealed network and behind a corporate firewall. With this proxy in front,
    the browser only ever addresses our own origin.
    """

    model_config = SettingsConfigDict(env_prefix="BASEMAP_", env_file=_ENV_FILE, extra="ignore")

    upstream_url: str = "https://tiles.openfreemap.org"
    # Path of the style document below the upstream, without a leading slash.
    style_path: str = "styles/liberty"
    # Prefix the rewritten URLs point at. Same-origin on purpose: the browser
    # must not need any host but ours.
    public_prefix: str = "/api/basemap"
    # Additional hosts whose absolute URLs are rewritten onto the proxy. The
    # upstream's own host is always rewritten; this list covers a self-hosted
    # upstream still serving a style that names OpenFreeMap.
    rewrite_hosts: list[str] = Field(default=["tiles.openfreemap.org"])
    # Tiles are immutable in practice -- OpenFreeMap serves them with a ten
    # year max-age. A week is a conservative floor.
    cache_ttl_s: int = 7 * 24 * 3600
    timeout_s: float = 30.0


class LLMSettings(BaseSettings):
    """OpenAI-compatible extraction provider (env prefix ``LLM_``)."""

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=_ENV_FILE, extra="ignore")

    base_url: str = "https://openrouter.ai/api/v1"
    api_key: SecretStr | None = None
    model: str = "openai/gpt-4o-mini"
    fetch_engine: Literal["openrouter", "exa", "parallel", "native", "auto"] = "openrouter"
    timeout_s: int = 120
    max_content_tokens: int = 50000

    @property
    def configured(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())


class Settings(BaseSettings):
    """Aggregate of all setting groups."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    alkis: AlkisSettings = Field(default_factory=AlkisSettings)
    boris: BorisSettings = Field(default_factory=BorisSettings)
    motis: MotisSettings = Field(default_factory=MotisSettings)
    nearby: NearbySettings = Field(default_factory=NearbySettings)
    tiles: TilesSettings = Field(default_factory=TilesSettings)
    basemap: BasemapSettings = Field(default_factory=BasemapSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
