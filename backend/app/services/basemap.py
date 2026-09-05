"""Vector basemap proxy in front of OpenFreeMap.

MapLibre loads a style document, and that document points at a handful of
absolute URLs: a TileJSON, the glyph ranges, the sprite sheet, the raster
hillshade. In a sealed network -- and behind most corporate firewalls -- the
browser reaches none of them. So the style is rewritten on the way out until
every URL it carries points back at this API, and everything the map then asks
for travels through one generic passthrough.

Two details decide whether the passthrough works at all:

* vector tiles arrive gzip-compressed and must **not** be decompressed on the
  way through -- the raw byte stream and the original ``Content-Encoding``
  travel together, or the browser sees garbage;
* the TileJSON behind ``sources[*].url`` carries absolute tile URLs of its own,
  so JSON answers are rewritten as well, not only the style.
"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from ..cache import DiskCache
from ..errors import BadRequestError, NotFoundError, UpstreamError, UpstreamTimeout
from ..settings import AppSettings, BasemapSettings

SERVICE_NAME = "Der Kartenhintergrund (OpenFreeMap)"

# Every basemap failure is survivable: the plot, the setback envelope and the
# official layers are drawn by us, only the background stays grey.
ADVICE = (
    "Die Karte bleibt ohne Hintergrund nutzbar; Luftbild und Katasterkarte "
    "kommen von einem anderen Dienst."
)

# Characters that may stay literal in a proxied path. Everything else is
# percent-encoded, so a font stack with spaces survives the round trip.
_PATH_SAFE = "/@:,;=+$&~-_.!*'()"
_MAX_PATH_LENGTH = 512
# A sprite sheet is the largest thing OpenFreeMap serves at ~50 kB; the cap is
# there to keep a misrouted upstream from filling the disk cache.
_MAX_BODY_BYTES = 16 * 1024 * 1024
# Constrained on purpose: only gzip or identity can come back, so the raw
# stream that reaches the browser is always something it can decode.
_ACCEPT_ENCODING = "gzip"


@dataclass(frozen=True)
class ProxiedBody:
    """One upstream answer on its way to the browser, headers included."""

    body: bytes
    content_type: str
    content_encoding: str | None
    from_cache: bool

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type

    def decoded(self) -> bytes:
        """The body with the transfer compression removed."""

        encoding = (self.content_encoding or "identity").lower()
        if encoding in ("", "identity"):
            return self.body
        try:
            if encoding == "gzip":
                return gzip.decompress(self.body)
            if encoding == "deflate":
                return zlib.decompress(self.body)
        except (OSError, zlib.error) as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat eine beschädigte Antwort geliefert. {ADVICE}"
            ) from exc
        raise UpstreamError(
            f"{SERVICE_NAME} hat die Antwort unerwartet komprimiert ({encoding}). {ADVICE}"
        )


def safe_relative_path(path: str) -> str:
    """Validate a proxied path.

    Only a relative path below the configured upstream may pass: no absolute
    target from the request, no ``..``, no scheme, no host. Otherwise this
    endpoint would be an open redirect wearing a tile proxy's clothes.
    """

    candidate = path.strip()
    if not candidate:
        raise BadRequestError("Es wurde kein Pfad auf dem Kartendienst angegeben.")
    if len(candidate) > _MAX_PATH_LENGTH:
        raise BadRequestError("Der angefragte Kartenpfad ist zu lang.")
    if "\\" in candidate or "://" in candidate or candidate.startswith("/"):
        raise BadRequestError(
            "Es lassen sich nur Pfade des konfigurierten Kartendienstes abrufen, "
            "keine vollständigen Adressen."
        )
    if any(segment in ("", ".", "..") for segment in candidate.split("/")):
        raise BadRequestError("Der angefragte Kartenpfad ist ungültig.")
    return candidate



class BasemapService:
    def __init__(self, settings: BasemapSettings, app_settings: AppSettings) -> None:
        self.settings = settings
        self.app_settings = app_settings
        self.cache = DiskCache(app_settings.cache_dir / "basemap", ttl_s=settings.cache_ttl_s)

    @property
    def upstream(self) -> str:
        return self.settings.upstream_url.rstrip("/")

    @property
    def public_prefix(self) -> str:
        return "/" + self.settings.public_prefix.strip("/")

    @property
    def rewrite_hosts(self) -> set[str]:
        hosts = {host.strip().lower() for host in self.settings.rewrite_hosts if host.strip()}
        upstream_host = urlsplit(self.upstream).hostname
        if upstream_host:
            hosts.add(upstream_host.lower())
        return hosts

    # -- URL rewriting -----------------------------------------------------

    def rewrite_url(self, value: str) -> str | None:
        """A single absolute upstream URL as a path on this API, else None."""

        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        if parts.hostname.lower() not in self.rewrite_hosts:
            return None
        rewritten = f"{self.public_prefix}/{parts.path.lstrip('/')}"
        return f"{rewritten}?{parts.query}" if parts.query else rewritten

    def rewrite(self, node: Any) -> Any:
        """Rewrite every absolute upstream URL in a decoded JSON document.

        Deliberately a walk over the whole tree rather than a list of known
        fields: it covers ``sources[*].url``, ``sources[*].tiles[]``,
        ``glyphs``, both spellings of ``sprite`` -- string and
        ``[{id, url}]`` -- and the tile URLs inside a TileJSON alike. Strings
        that merely mention the host, such as the HTML in ``attribution``, are
        not URLs and stay untouched.
        """

        if isinstance(node, str):
            return self.rewrite_url(node) or node
        if isinstance(node, list):
            return [self.rewrite(item) for item in node]
        if isinstance(node, dict):
            return {key: self.rewrite(value) for key, value in node.items()}
        return node

    # -- fetching ----------------------------------------------------------

    def target_url(self, path: str, query: str = "") -> str:
        relative = safe_relative_path(path)
        url = f"{self.upstream}/{quote(relative, safe=_PATH_SAFE)}"
        if query:
            url = f"{url}?{query}"
        # Belt and braces: whatever the path did, it must not have moved the
        # request off the configured upstream.
        if urlsplit(url).hostname != urlsplit(self.upstream).hostname:
            raise BadRequestError("Der angefragte Kartenpfad verlässt den Kartendienst.")
        return url

    async def fetch(self, path: str, query: str = "") -> ProxiedBody:
        """Fetch one upstream resource, from the disk cache when it is fresh."""

        url = self.target_url(path, query)
        cache_key = f"{self.upstream}|{path}|{query}"
        cached = self.cache.get_bytes(cache_key)
        if cached is not None:
            return _unpack(cached, from_cache=True)

        headers = {
            "User-Agent": self.app_settings.user_agent,
            "Accept-Encoding": _ACCEPT_ENCODING,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout_s, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    # A redirect must not carry the request to a host we do not
                    # proxy for: the path comes from the browser, and an open
                    # redirect on the upstream would otherwise become ours.
                    if (response.url.host or "").lower() not in self.rewrite_hosts:
                        raise UpstreamError(
                            f"{SERVICE_NAME} hat auf einen fremden Server verwiesen. {ADVICE}"
                        )
                    if response.status_code == 404:
                        raise NotFoundError(
                            f"{SERVICE_NAME} kennt diese Kachel nicht."
                        )
                    if response.status_code >= 400:
                        raise UpstreamError(
                            f"{SERVICE_NAME} hat die Anfrage mit Status "
                            f"{response.status_code} abgelehnt. {ADVICE}"
                        )
                    chunks: list[bytes] = []
                    size = 0
                    # aiter_raw, not aiter_bytes: the compressed stream has to
                    # stay compressed all the way to the browser.
                    async for chunk in response.aiter_raw():
                        size += len(chunk)
                        if size > _MAX_BODY_BYTES:
                            raise UpstreamError(
                                f"{SERVICE_NAME} hat eine unerwartet große Antwort geliefert. {ADVICE}"
                            )
                        chunks.append(chunk)
                    proxied = ProxiedBody(
                        body=b"".join(chunks),
                        content_type=response.headers.get(
                            "content-type", "application/octet-stream"
                        ),
                        content_encoding=response.headers.get("content-encoding"),
                        from_cache=False,
                    )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(
                f"{SERVICE_NAME} hat nicht rechtzeitig geantwortet. {ADVICE}"
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{SERVICE_NAME} ist derzeit nicht erreichbar. {ADVICE}") from exc

        self.cache.set_bytes(cache_key, _pack(proxied))
        return proxied

    def style_path(self, *, dark: bool = False) -> str:
        """Which upstream style document a variant asks for.

        A dark variant that is not configured falls back to the light one
        rather than 404-ing: a backdrop with the wrong palette is still a
        backdrop, and losing the map entirely is the worse outcome.
        """

        if dark and self.settings.dark_style_path:
            return self.settings.dark_style_path
        return self.settings.style_path

    async def style(self, *, dark: bool = False) -> tuple[Any, bool]:
        """The style document with every upstream URL pointing back at us.

        Every URL comes out relative. The browser is the only party that knows
        the origin it reached this API on -- behind a dev proxy or a reverse
        proxy that is not the origin FastAPI sees -- so it does the expanding.
        """

        proxied = await self.fetch(self.style_path(dark=dark))
        document = self.json_document(proxied)
        if not isinstance(document, dict) or "layers" not in document:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein Stildokument geliefert. {ADVICE}"
            )
        return document, proxied.from_cache

    def json_document(self, proxied: ProxiedBody) -> Any:
        """A JSON answer (style, TileJSON, sprite index) with its URLs rewritten."""

        try:
            document = json.loads(proxied.decoded().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise UpstreamError(
                f"{SERVICE_NAME} hat kein gültiges JSON geliefert. {ADVICE}"
            ) from exc
        return self.rewrite(document)


# The disk cache stores bytes, and the two headers that decide how the browser
# reads them belong with those bytes. One JSON line, then the raw body.


def _pack(proxied: ProxiedBody) -> bytes:
    meta = json.dumps(
        {"content_type": proxied.content_type, "content_encoding": proxied.content_encoding}
    )
    return meta.encode("utf-8") + b"\n" + proxied.body


def _unpack(raw: bytes, *, from_cache: bool) -> ProxiedBody:
    head, _, body = raw.partition(b"\n")
    try:
        meta = json.loads(head.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # An entry written by an older version: serve it as opaque bytes.
        meta = {}
    return ProxiedBody(
        body=body,
        content_type=meta.get("content_type") or "application/octet-stream",
        content_encoding=meta.get("content_encoding"),
        from_cache=from_cache,
    )
