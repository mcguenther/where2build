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
    # Ceiling over the whole cache tree, swept by scripts/sweep_cache.py on a
    # schedule rather than on every write: measuring the tree costs a walk, and
    # the answers being evicted are cheap to fetch again. The sweeper reads the
    # same APP_CACHE_MAX_BYTES, so both agree without either importing the other.
    cache_max_bytes: int = 100 * 1024 * 1024
    # Sent to every upstream service. Deliberately carries no contact address:
    # a mail address in here would travel to ALKIS, BORIS, the tile servers and
    # the extraction provider alike, none of which asks for one.
    user_agent: str = "GrundstuecksCheckSachsen/0.1 (+https://github.com/mcguenther/where2build)"
    # Transitous is the one upstream whose usage policy demands a way of contact
    # ("Name of the application / Version of the client / A way of contact"), so
    # it is kept separate and appended for that service alone. Empty means the
    # plain user agent goes out everywhere.
    contact: str = ""
    # Listing portals answer a plain library user agent with a challenge page,
    # so requests to them identify as a browser instead.
    portal_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
    http_timeout_s: float = 30.0
    # How many reverse proxies of our own stand in front of this process, and
    # therefore how far from the right of ``X-Forwarded-For`` the real peer is.
    # Zero means none, and then the header is not read at all -- a browser can
    # write it, so believing it without a proxy having put it there lets anyone
    # spend somebody else's request budget or dodge their own. The bundled
    # docker compose deployment serves the API through nginx
    # (``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for``) and
    # therefore sets this to 1; a plain ``uvicorn`` run leaves it at 0.
    proxy_hops: int = Field(default=0, ge=0, le=8)

    @property
    def contact_user_agent(self) -> str:
        """The user agent for services that require a way of contact."""
        return f"{self.user_agent} ({self.contact})" if self.contact else self.user_agent


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
    # The cadastral district directory served by GET /api/gemarkungen. Built
    # from this same WFS by scripts/build_gemarkung_index.py and committed --
    # see app/gemarkung_index.py for why it is not queried per request.
    gemarkung_index_path: Path = _BACKEND_DIR / "data" / "gemarkungen-sachsen.json"
    # Browser cache for that answer. Districts change on the order of a
    # municipal reform, and a redeploy ships a new file anyway.
    gemarkung_cache_ttl_s: int = 24 * 3600


class AddressSettings(BaseSettings):
    """Official Saxon address coordinates (env prefix ``ADDRESSES_``).

    The GeoSN publishes every address in the state with its cadastral
    coordinate as one quarterly download. ``scripts/build_address_index.py``
    turns that into the file named here, and ``POST /api/geocode`` answers from
    it before it falls back to the routing geocoder. The file is a build
    artefact and may legitimately be absent -- see ``app/address_index.py``.
    """

    model_config = SettingsConfigDict(env_prefix="ADDRESSES_", env_file=_ENV_FILE, extra="ignore")

    index_path: Path = _BACKEND_DIR / "data" / "hauskoordinaten-sachsen.json.gz"
    # Nextcloud share of the GeoSN open-data area. Answers 401 to HEAD and 200
    # to GET, so a reachability check has to be a GET with a Range header.
    download_url: str = (
        "https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/"
        "B3HnXbDDgAkw69a/hk_sn_ascii.zip"
    )
    # How many official hits may take the front of a geocode answer. Four of
    # five, so a matching stop or place is never pushed off the list entirely.
    max_candidates: int = 4


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
    # Eight, because that is what a default request can produce: two hits for
    # each of the four transit categories. A lower cap would leave the last
    # stops of an ordinary answer without their lines.
    max_line_lookups: int = 8


class OverpassSettings(BaseSettings):
    """Live OpenStreetMap queries through an Overpass instance (env prefix ``OVERPASS_``).

    Off by default and deliberately so. This is the prototype convenience that
    makes ``/api/nearby`` answer schools, parks and the rest on a machine where
    ``scripts/build_poi_index.py`` has never run. The Overpass manual names
    "setting up an app for more than just OSM mappers and relying on the public
    instances as backend" as problematic behaviour and asks for at most ~10 000
    requests and 1 GB a day; a single-user prototype behind a 30-day cache is
    far inside that, an app with users is not. Point ``url`` at your own
    instance and the question does not arise.
    """

    model_config = SettingsConfigDict(env_prefix="OVERPASS_", env_file=_ENV_FILE, extra="ignore")

    enabled: bool = False
    url: str = "https://overpass-api.de/api/interpreter"
    # Goes into the query itself as `[timeout:N]`, which is what the server
    # enforces. It answers with a "runtime error" remark when it runs out.
    query_timeout_s: int = 25
    # Longer than the query timeout on purpose: the manual says a request stays
    # enqueued for up to 15 s before a slot frees, and that wait comes on top.
    timeout_s: float = 60.0
    # A plot does not move and its surroundings change on the order of months --
    # the offline index the README recommends is refreshed quarterly. 30 days
    # keeps the live source no staler than that while making repeat views of the
    # same plot free.
    cache_ttl_s: int = 30 * 24 * 3600
    # One query in flight at a time. The public instances hand out execution
    # slots per IP address, and ours is one address for the whole deployment.
    max_concurrency: int = 1
    # The radius is rounded up to a multiple of this before it goes out, so
    # 2 000 m and 2 500 m share one cached answer.
    radius_step_m: int = 1000
    # Decimal places the query centre is rounded to for the same reason. Three
    # is about 110 m north-south, so every point on one plot shares an entry.
    origin_precision: int = 3
    # Safety margin added to the queried radius to cover that rounding.
    origin_margin_m: int = 200
    # Building outlines are asked for in tens of metres, not kilometres, so the
    # rounding above would turn an 80 m question into a 1 200 m answer -- 1 670
    # buildings for one plot, measured against Mölkau. Four decimal places is
    # about 11 m, and the margin covers that.
    building_origin_precision: int = 4
    building_radius_step_m: int = 50
    building_origin_margin_m: int = 25


class LuisSettings(BaseSettings):
    """Saxon environmental data (env prefix ``LUIS_``).

    One open ArcGIS REST server carries noise, water, nature, soil, geology and
    radon for the whole state. It is a different host from the cadastre: maps
    and parcels live on ``geodienste.sachsen.de``, the environmental record on
    this one, and guessing a name on the wrong host answers 403 in a way that
    reads like a block.

    Facts are asked with ``/<layer>/query`` and the parcel outline, never with
    ``identify`` -- that measures its tolerance in *pixels*, so at a plausible
    extent 3 px was about 7 m and the service reported a neighbouring polygon
    as a hit.
    """

    model_config = SettingsConfigDict(env_prefix="LUIS_", env_file=_ENV_FILE, extra="ignore")

    base_url: str = "https://luis.sachsen.de/arcgis/rest/services"
    # Native spatial reference of these services; the parcel ring goes out in it.
    srid: int = 25833
    # A designation changes when a Rechtsverordnung does, which is rare.
    cache_ttl_s: int = 30 * 24 * 3600
    timeout_s: float = 45.0
    # How far to look for a mapped noise polygon before "no value" may be read
    # as "quiet". Environmental noise mapping covers agglomerations and major
    # routes only: a village gets no polygon at all, and that is not silence.
    noise_coverage_radius_m: int = 2000
    # Widest ring the nearest protected area is looked for in. Beyond a
    # kilometre the answer stops being about this plot.
    protection_radius_m: int = 1000
    # Boreholes: the wider ring is the count, the narrower one the neighbourhood.
    borehole_radius_m: int = 500
    borehole_near_radius_m: int = 300
    # A single answer may not carry more features than this. Only counts and
    # names are read, so the cap protects the request, not the meaning.
    max_features: int = 200


class RapisSettings(BaseSettings):
    """RAPIS Sachsen, the Landesdirektion's planning register (env prefix ``RAPIS_``).

    An open ArcGIS REST server with the plan areas of every Saxon municipality:
    Bebauungspläne in force and in procedure, the §§ 34/35 statutes and the
    effective FNP. Asked with ``/<layer>/query`` and the plot outline, like LUIS.
    See docs/research/bebauungsplaene-sachsen.md.
    """

    model_config = SettingsConfigDict(env_prefix="RAPIS_", env_file=_ENV_FILE, extra="ignore")

    base_url: str = "https://rapis.ipm-gis.de/arcgis/rest/services"
    # Where the source credit links to, and where a user can look by hand.
    portal_url: str = "https://rapis.sachsen.de"
    srid: int = 25833
    # A week, not the month the environmental layers get: RAPIS is uploaded
    # weekly (DAT_RAPIS read "ROK 21.09.2026" on 25.09. and "ROK 28.09.2026" on
    # 30.09.), and a plan that came into force is exactly the change this
    # answer exists to report. Plan areas themselves change far more slowly, so
    # a week of staleness costs nothing a user would notice.
    cache_ttl_s: int = 7 * 24 * 3600
    timeout_s: float = 30.0


class AirQualitySettings(BaseSettings):
    """UBA air data (env prefix ``AIRQUALITY_``).

    Nationwide, no key. The documented path on ``umweltbundesamt.de`` is a 301
    to this host, and spells ``air-data`` rather than ``air_data`` -- following
    neither is how the API comes to look dead.
    """

    model_config = SettingsConfigDict(
        env_prefix="AIRQUALITY_", env_file=_ENV_FILE, extra="ignore"
    )

    base_url: str = "https://luftdaten.umweltbundesamt.de/api/air-data/v3"
    # A station is built about as often as a road is; the list is 550 kB.
    stations_cache_ttl_s: int = 7 * 24 * 3600
    # Measurements arrive hourly, so a shorter life -- but not per request.
    measures_cache_ttl_s: int = 3 * 3600
    # How many of the nearest stations to try. The list mixes in research and
    # historic sites whose "active to" is empty and which answer nothing at
    # all: around Moelkau the three nearest (1,9-3,0 km) are silent and
    # Leipzig-Mitte at 4,6 km is the one with values.
    max_stations: int = 8
    # Past this a station describes another place, not this plot's air.
    max_distance_km: float = 25.0
    # Hours averaged. Two days smooths a single calm night without turning
    # into a monthly mean.
    hours: int = 48
    timeout_s: float = 30.0


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
    # The parcels themselves, with the buildings for orientation. The land-use
    # layers (`tatsaechliche_nutzung`, `verkehr`, `siedlung`) draw areas that
    # cut straight across parcel boundaries, which is the opposite of what a
    # ground called "Kataster" is for.
    alkis_layers: str = "adv_alkis_flurstuecke,adv_alkis_gebaeude"
    # And the parcels stop being drawn at 1:2000 -- an empty image, no error.
    # A WMS derives the scale of a request from the standard 0,28 mm pixel, and
    # MAP_RESOLUTION is how a caller says the pixel is a different size, so the
    # threshold can be steered. Measured on a z18 tile over Liebertwolkwitz on
    # 05.09.2026: without it the tile is blank, MAP_RESOLUTION=85 draws, 86 is
    # blank again -- exactly where the scale reaches 1:2000.
    alkis_min_scale: float = 2000.0
    # The Liegenschaftskarte itself, for laying over an orthophoto at plot
    # scale: boundaries, parcel numbers in the register's stacked notation,
    # boundary points and street names, all as line work on transparent ground.
    # Measured over Liebertwolkwitz -- the street names ride along with the
    # parcels, no second layer needed. It is a different picture from the one
    # below, not a spelling of it: the oversampled render draws its labels at
    # the enlarged size and they come back a fifth of their height, so at plot
    # scale that ground has outlines and no numbers.
    cadastral_map_layers: str = "adv_alkis_flurstuecke"
    # Parcel outlines for laying over an orthophoto. „Gelb“ is the service's own
    # overlay style -- contours, no fills. The layer carries
    # MaxScaleDenominator 2000 and answers 200 with an empty PNG above it, so
    # the floor is measured rather than chosen: z18 is 1:2133 and blank, z19 is
    # 1:1066 and draws.
    parcel_layers: str = "adv_alkis_flurstuecke"
    parcel_styles: str = "Gelb"
    # The layer's own MaxScaleDenominator, read from its GetCapabilities. The
    # proxy renders each tile at whatever pixel size puts the denominator under
    # this and scales the result back down, so the outlines draw far above the
    # zoom the service would otherwise start at.
    parcel_max_scale_denominator: float = 2000
    # z14 would need 4368 px for one tile and the service refuses anything over
    # 4000, so that is where oversampling runs out. z15 is the floor.
    parcel_min_zoom: int = 15
    # Roads and their names, transparent at every zoom measured (13 to 19).
    street_layers: str = "Verkehr,Beschriftung"
    # The web atlas without its lettering: streets, buildings, green and water
    # as a quiet ground under a plot's thumbnail. A thumbnail is turned to its
    # street, often by more than a quarter turn, and street names would then
    # stand on their heads -- at that size they are noise either way.
    surroundings_layers: str = "Vegetation,Siedlung,Gewaesser,Verkehr"
    # The noise survey is not a WMS tile source: its service offers EPSG:4326
    # and 25833 but not 3857, so MapLibre's {bbox-epsg-3857} raster source gets
    # nothing at all. The ArcGIS ``export`` endpoint reprojects server-side.
    noise_url: str = (
        "https://luis.sachsen.de/arcgis/rest/services/laerm/laermkartierung/MapServer/export"
    )
    noise_layers: str = "show:4"
    noise_night_layers: str = "show:5"
    # Both noise layers carry ``minScale: 50000`` and draw an empty image --
    # not an error -- above it. ArcGIS derives the scale from the request as
    # (bbox_width_m / image_width_px) * dpi / 0.0254, so the dpi is what keeps
    # the layer under the threshold. Measured: at 10 km and 512 px, dpi 65 gives
    # 1:49 982 and draws, dpi 66 gives 1:50 750 and returns a blank PNG.
    noise_min_scale: float = 50000.0
    # XYZ tiles are Web Mercator. Should a service reject EPSG:3857, EPSG:4326
    # also works -- the axis order is handled per CRS.
    crs: str = "EPSG:3857"
    image_format: str = "image/png"
    tile_size: int = 256
    transparent: bool = True
    # What the service will render in one request. `MaxWidth`/`MaxHeight` in the
    # ALKIS capabilities; asking for more is refused outright.
    max_render_size: int = 4000
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
    # The same map for a dark interface. A drawing sits *on* the backdrop, so a
    # near-white ground under a dark page is not a preference but a glare
    # source. OpenFreeMap serves two dark styles: `dark` is a neutral near-black
    # (rgb(12,12,12)), `fiord` a blue-grey (#45516E) -- the former is the one
    # that sits next to this app's warm near-black paper without a colour cast.
    dark_style_path: str = "styles/dark"
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


# Which extraction provider a deployment points at. Four names and one escape
# hatch, because three of the four speak the same wire protocol and one does
# not:
#
# * **openrouter**, **openai**, **ollama** and anything else OpenAI-compatible
#   answer ``POST /chat/completions`` with a ``response_format`` of
#   ``json_schema``. One transport serves all of them; only the base URL and
#   the model id differ, and Ollama additionally needs no key at all.
# * **anthropic** answers ``POST /v1/messages``. Different path, different auth
#   header (``x-api-key`` plus ``anthropic-version``, not ``Authorization:
#   Bearer``), different place for the schema (``output_config.format``) and a
#   different answer shape. It gets its own adapter rather than a shim: a
#   translation layer that pretends one API is the other is exactly the thing
#   that breaks silently the first time either side changes.
#
# „auto" reads the provider off the base URL, which is what a person who only
# pastes a key and an endpoint expects.
LLMAnbieter = Literal["auto", "openai", "anthropic", "openrouter", "ollama", "kompatibel"]

# What each provider answers at, and what it wants to be called with, when the
# deployment gives nothing but a key. A base URL set by hand always wins.
LLM_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-opus-5"),
    # Measured 18.09.2026 over the 16 recorded adverts, through the real
    # extraction path: 16/16 schema-conformant, 2,5 s and $0,0005 per advert.
    # The alternatives lose on one of the three -- `mistral-small-24b` is
    # cheaper and misses areas, and every reasoning model (deepseek-v4-flash,
    # gpt-5-nano, glm-4.7-flash) spends 50 to 85 seconds per advert in a call
    # the assistant makes while the user waits. See `docs/claude/services.md`.
    "openrouter": ("https://openrouter.ai/api/v1", "google/gemini-2.5-flash-lite"),
    # A local Ollama needs no key and is the one provider where the default
    # endpoint is on this machine.
    "ollama": ("http://127.0.0.1:11434/v1", "llama3.1"),
}


class LLMSettings(BaseSettings):
    """The extraction provider (env prefix ``LLM_``).

    A deployment sets three things at most: ``LLM_ANBIETER``, ``LLM_API_KEY``
    and — where it is not one of the four known hosts — ``LLM_BASE_URL``. The
    model has a default per provider and is worth setting; everything else has
    one that works.
    """

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=_ENV_FILE, extra="ignore")

    anbieter: LLMAnbieter = "auto"
    base_url: str = ""
    api_key: SecretStr | None = None
    model: str = ""
    fetch_engine: Literal["openrouter", "exa", "parallel", "native", "auto"] = "openrouter"
    # The price list behind the cost column in the administration area. A file
    # rather than a constant, because a price is a claim about somebody else's
    # price list and goes stale; ``scripts/update_llm_prices.py`` writes it
    # from the provider's own endpoint and it is committed, so every change is
    # a diff. Absent, the tokens are still counted and the money column says
    # so -- never 0,00 €.
    prices_path: Path = Path("ops/llm-preise.json")
    timeout_s: int = 120
    max_content_tokens: int = 50000
    # The dated contract the Anthropic API requires on every request. Pinned
    # rather than left to the server's default: an API that versions itself by
    # header is one whose answer shape can change under an unpinned client.
    anthropic_version: str = "2023-06-01"

    @property
    def provider(self) -> str:
        """The provider actually in play, with „auto" resolved from the host.

        Reading it off the URL is what somebody who pasted an endpoint and a
        key expects to happen — and it is only ever a default: naming the
        provider outright always wins.
        """

        if self.anbieter != "auto":
            return self.anbieter
        host = self.base_url.lower()
        for name in ("anthropic", "openrouter", "ollama"):
            if name in host:
                return name
        if "openai.com" in host:
            return "openai"
        # Ollama's own default endpoint is „localhost:11434" and carries its
        # name nowhere; the port is the only signal a pasted URL gives. Named
        # as a host it is caught above, which is the shape a compose file uses.
        if ":11434" in host:
            return "ollama"
        return "kompatibel" if self.base_url else "openrouter"

    @property
    def endpoint(self) -> str:
        """Where to send a request, with the provider's own default filled in."""

        if self.base_url:
            return self.base_url.rstrip("/")
        return LLM_DEFAULTS.get(self.provider, LLM_DEFAULTS["openrouter"])[0]

    @property
    def model_id(self) -> str:
        if self.model:
            return self.model
        return LLM_DEFAULTS.get(self.provider, LLM_DEFAULTS["openrouter"])[1]

    @property
    def needs_key(self) -> bool:
        """Whether this provider needs one at all.

        A local Ollama does not, and demanding one would make the one provider
        that costs nothing the only one a person cannot try.
        """

        return self.provider != "ollama"

    @property
    def configured(self) -> bool:
        if not self.needs_key:
            return bool(self.endpoint)
        return self.api_key is not None and bool(self.api_key.get_secret_value())


class StorageSettings(BaseSettings):
    """Server-side storage for signed-in accounts (env prefix ``STORAGE_``).

    ``DATABASE_URL`` is deliberately unprefixed: it is the name every hosting
    platform and every Postgres client already uses, and a deployment that has
    a database has it under that name.

    Absent, this whole feature is absent. No pool is opened, no schema is
    applied, ``/api/plots`` and ``/api/settings`` answer 503 with a German
    sentence and the frontend keeps every plot in the browser, exactly as it
    did before there was a database at all. Same shape as the sign-in: a
    development machine must not need Postgres before it can resolve a parcel.

    What is stored is the frontend's own document, verbatim, as ``jsonb``. The
    backend does not read it, and the two limits below are the only thing it
    says about it -- see ``app/services/storage.py``.
    """

    model_config = SettingsConfigDict(env_prefix="STORAGE_", env_file=_ENV_FILE, extra="ignore")

    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    # Both numbers are picked, not derived: nobody has 200 plots under
    # appraisal, and no plot document measured so far comes near two megabytes
    # (the largest recorded one, with routes and site checks, is ~40 kB). They
    # exist so one account cannot fill the disk, not because a measurement
    # pointed here, and a deployment that wants other numbers sets them.
    max_plots_per_account: int = 200
    max_document_bytes: int = 2 * 1024 * 1024
    # A shared link is a copy that outlives the sharing, so the table would
    # grow for ever without an end date. Ninety days is long enough for a
    # purchase to run its course and short enough that an abandoned link does
    # not sit there indefinitely; the sweep job removes what is past it.
    share_days: int = Field(default=90, ge=1)
    # And a ceiling per account for the same reason as the one on plots: so one
    # account cannot fill the table.
    max_shares_per_account: int = 50
    # A prototype's pool. Small on purpose: every request holds a connection
    # for one or two statements, and Postgres' own default is 100 backends.
    pool_min_size: int = 1
    pool_max_size: int = 8
    # Applies to opening a connection and to each statement. A database that
    # does not answer in ten seconds is down, and saying so beats hanging the
    # tab that is trying to save.
    timeout_s: float = 10.0

    @property
    def configured(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def endpoint(self) -> str | None:
        """The connection target without its password, for ``/api/health``.

        A DSN carries credentials and the health answer is public, so the
        password is replaced rather than shortened: a truncated secret is still
        a secret.
        """

        url = self.database_url.strip()
        if not url:
            return None
        head, separator, tail = url.rpartition("@")
        if not separator:
            return url
        scheme, _, userinfo = head.rpartition("//")
        user = userinfo.split(":", 1)[0]
        return f"{scheme}//{user}@{tail}" if user else url


class RateLimitSettings(BaseSettings):
    """How many calls one account may send outward (env prefix ``RATELIMIT_``).

    This backend answers nothing of its own: every request it serves becomes a
    request to the cadastre, to BORIS, to the LUIS environmental server, to
    Transitous or to a public Overpass instance. A single-seat prototype asking
    those now and then is what their policies allow; a deployment with accounts
    is what the Overpass manual means by "relying on the public instances as
    backend". Hence a per-account ceiling, in the same step as the sign-in.

    Both numbers are picked, not derived, and both are picked so that a single
    person working normally never meets one. See ``app/ratelimit.py`` for how
    they are counted and why the count lives in this process's memory.
    """

    model_config = SettingsConfigDict(env_prefix="RATELIMIT_", env_file=_ENV_FILE, extra="ignore")

    # Off is the single-seat setting: one person on their own machine is the
    # case the upstream policies already permit, and a limit there only gets in
    # the way (the screenshot run alone is a few thousand requests).
    enabled: bool = True
    window_s: int = Field(default=3600, ge=1)
    # Everything that asks an authority, the router or the model a question.
    # Picked rather than derived, but with one measurement beside it:
    # ``scripts/screenshots.mjs`` drives every view of the app in one pass --
    # two themes, a narrow pass, three listing searches, one plot appraised end
    # to end, both print sheets -- and spends 59 of these (measured 09.09.2026
    # on a cold cache). A search over a listing counts as one however many WFS
    # requests it makes inside, which is why the ceiling sits well below what
    # the upstreams would tolerate. So 600 an hour is ten full drive-throughs
    # of the whole application per hour: nothing a person does by hand comes
    # near it, and a scan still meets it.
    service_calls: int = Field(default=600, ge=1)
    # Map tiles are a different order of magnitude -- one screen is dozens, a
    # pan is dozens more -- and they are the one thing the shared disk cache
    # really covers, so the second view of an area costs nothing upstream at
    # all. The same screenshot run spends 1 007 of these against 59 of the
    # above, which is the ratio the two numbers are set by. 6 000 an hour is a
    # hundred a minute sustained for an hour: past any amount of looking at
    # maps, and still a ceiling on a scan.
    map_tiles: int = Field(default=6000, ge=1)
    # How many clients are remembered at once. Each costs at most one timestamp
    # per call in the window, so the worst case here is a few megabytes; the
    # least recently seen is dropped first.
    max_clients: int = Field(default=20000, ge=1)


class AdminSettings(BaseSettings):
    """The administration area (env prefix ``ADMIN_``).

    Two things are configured here and they answer two different questions.

    **Who gets in.** ``ADMIN_ACCOUNTS`` is a comma-separated list of account
    keys -- the same stable, non-speaking identifier ``/api/auth/me`` reports
    and the account page shows. It is the bootstrap and nothing else: everybody
    else is promoted in the interface, and the flag for that lives in the
    database. Configuration rather than a first-one-wins rule because an
    instance on the open internet would otherwise hand the area to whoever
    signed up first, and configuration rather than a group claim from the
    provider because this deployment asks for ``openid profile`` and nothing
    more. An account key is not a secret -- it identifies, it does not
    authenticate -- so a list of them in the environment grants nothing to
    anyone who cannot already sign in as that person.

    **What is counted.** Nothing was, before this: the request budget counts in
    memory and forgets, and a deployment could not say what it had done. The
    counters below are aggregates -- an hour, a service, an outcome -- and the
    per-account half is the one that answers "who is doing this" when something
    is wrong. Both are swept after ``retention_days``.

    The burst window is the part that has to be fast. An hourly counter cannot
    stop anything: by the time it shows the hour, the hour has happened. So the
    recorder watches a short window per account, and an account that crosses
    ``burst_calls`` in it is blocked for ``auto_block_minutes`` -- in this
    process immediately, and in the database within one flush, which is where
    the other workers and the interface read it.
    """

    model_config = SettingsConfigDict(env_prefix="ADMIN_", env_file=_ENV_FILE, extra="ignore")

    # Comma-separated account keys. Empty means the area exists but nobody is
    # let in by configuration -- which is the right default for a machine that
    # is not a deployment.
    accounts: str = ""
    # How often the in-process counters are written out, and the blocks read
    # back. Short enough that "letzte Stunde" in the interface is current and
    # that a block reaches the other workers quickly, long enough that a busy
    # minute is one UPDATE per bucket rather than one per request.
    flush_s: int = Field(default=30, ge=1)
    # How long counters, errors and the audit trail are kept. The same ninety
    # days a shared link gets, for the same reason: every row needs an end.
    retention_days: int = Field(default=90, ge=1)
    # The short window, and what crossing it costs. 300 calls in five minutes
    # is one a second sustained -- far past anything a person clicking produces
    # (the whole screenshot run is 59 service calls), and far below the hourly
    # ceiling, which is the point: this is the guard that acts inside the hour.
    burst_window_s: int = Field(default=300, ge=1)
    burst_calls: int = Field(default=300, ge=1)
    auto_block_minutes: int = Field(default=60, ge=1)
    # The error log the interface shows and offers as a download, kept in this
    # process as well so a deployment without a database is not silent about
    # its own failures. Bounded: an outage produces one of these per request.
    error_buffer: int = Field(default=500, ge=1)
    # The recurring jobs, as the administration area shows them. The list is
    # the same file the scheduler reads and the records are the same directory
    # it writes -- see ``app/jobs.py`` for why a "run now" here writes a
    # request instead of running anything itself.
    jobs_file: Path = Field(default=Path("ops/jobs.json"), validation_alias="JOBS_FILE")
    state_dir: Path = Field(default=Path("/state"), validation_alias="JOBS_STATE_DIR")

    @property
    def bootstrap_accounts(self) -> tuple[str, ...]:
        """The configured account keys, split and cleaned."""

        return tuple(
            part.strip() for part in self.accounts.replace(";", ",").split(",") if part.strip()
        )


class OidcSettings(BaseSettings):
    """Sign-in through an OpenID Connect provider (env prefix ``OIDC_``).

    No provider is hard-wired, the same way none is for the LLM: issuer, client
    id and secret decide whether this is Authentik, Keycloak or Google, and the
    endpoints come from the issuer's discovery document rather than from a
    guessed path.

    Absent, the whole feature is absent: ``configured`` is false, ``/api/auth/me``
    says so, and every other route works exactly as it did before. A development
    machine must not need an identity provider before it can resolve a parcel.

    This is a backend-for-frontend, so the browser never sees a token. What it
    gets is a signed, HttpOnly cookie holding issuer, subject, display name and
    an expiry; the access token lives no longer than the request that fetched it.
    """

    model_config = SettingsConfigDict(env_prefix="OIDC_", env_file=_ENV_FILE, extra="ignore")

    issuer: str = ""
    client_id: str = ""
    client_secret: SecretStr | None = None
    # "openid" alone would authenticate but hand out no name to greet anyone
    # with. Deliberately no "email": the project stores no contact detail, so
    # asking for one would collect what must not be kept.
    scopes: str = "openid profile"
    # Signs the session cookie and the short-lived login cookie. No default:
    # a shipped one would be a public key everyone could forge sessions with.
    session_secret: SecretStr | None = None
    # Off only for a plain-HTTP development server. A session cookie without
    # Secure travels over any http:// request to the same host.
    cookie_secure: bool = True
    cookie_name: str = "w2b_sitzung"
    # The cookie that carries state, nonce and the PKCE verifier from /login to
    # /callback. Separate from the session, and gone the moment it is used.
    login_cookie_name: str = "w2b_anmeldung"
    # Where this backend reaches the provider, when that is not where the
    # browser reaches it. An *origin* -- scheme, host, port -- and no path.
    #
    # An issuer is one string doing two jobs: it is the address the browser is
    # sent to, and it is the name an ID token is checked against. Inside a
    # container network those two come apart -- the browser knows
    # `http://localhost:9000`, and from in here that is this container itself.
    # Set this to the origin that works from the server side
    # (`http://authentik:9000`) and the discovery document, the token endpoint
    # and userinfo are fetched there; the authorization URL and the `iss`
    # check keep the public issuer, because those belong to the browser and to
    # the token. Every provider deployed this way needs it -- Keycloak calls
    # the same thing a "frontend URL".
    internal_base_url: str = ""
    # Origin the provider redirects back to, e.g. https://where2build.example.
    # Empty derives it from the request, which is right for a local dev server
    # and wrong behind a reverse proxy that terminates TLS: the request then
    # says "http" and the redirect_uri stops matching the registered one.
    public_base_url: str = ""
    # How long a session lasts. There is no refresh token kept anywhere, so
    # this is simply how long until the next sign-in.
    session_ttl_s: int = 14 * 24 * 3600
    # How long the handshake may take. Ten minutes is generous for typing a
    # password and short enough that a stolen login cookie is worth little.
    login_ttl_s: int = 600
    # The discovery document changes when a provider is reconfigured, which is
    # rare, but a key rotation must not need a restart to be noticed.
    discovery_cache_ttl_s: int = 3600
    timeout_s: float = 15.0

    @property
    def missing(self) -> list[str]:
        """Which env variables a deployment still has to set, in order."""

        secrets = {
            "OIDC_CLIENT_SECRET": self.client_secret,
            "OIDC_SESSION_SECRET": self.session_secret,
        }
        return [
            *(["OIDC_ISSUER"] if not self.issuer else []),
            *(["OIDC_CLIENT_ID"] if not self.client_id else []),
            *(name for name, value in secrets.items() if not (value and value.get_secret_value())),
        ]

    @property
    def configured(self) -> bool:
        return not self.missing


class Settings(BaseSettings):
    """Aggregate of all setting groups."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    alkis: AlkisSettings = Field(default_factory=AlkisSettings)
    addresses: AddressSettings = Field(default_factory=AddressSettings)
    boris: BorisSettings = Field(default_factory=BorisSettings)
    luis: LuisSettings = Field(default_factory=LuisSettings)
    rapis: RapisSettings = Field(default_factory=RapisSettings)
    air_quality: AirQualitySettings = Field(default_factory=AirQualitySettings)
    motis: MotisSettings = Field(default_factory=MotisSettings)
    nearby: NearbySettings = Field(default_factory=NearbySettings)
    overpass: OverpassSettings = Field(default_factory=OverpassSettings)
    tiles: TilesSettings = Field(default_factory=TilesSettings)
    basemap: BasemapSettings = Field(default_factory=BasemapSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    oidc: OidcSettings = Field(default_factory=OidcSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
