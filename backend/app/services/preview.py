"""The picture a chat shows when somebody pastes a shared link.

A preview bot runs no JavaScript and takes no screenshot: it reads the ``og:``
tags out of the HTML and fetches whatever ``og:image`` names. So the card is
drawn here, server-side, with Pillow -- the same library the tile proxy already
uses to scale an oversized WMS render back to a tile.

Three properties the drawing has to keep:

* **It draws the document it was handed, and nothing else.** The shared document
  has already been cut by ``Storage.for_sharing``, so a price on the card is a
  price somebody switched on. No lookups, no defaults, no invented figures.
* **The ground is best effort.** The card is one request in a chat window; a
  slow or broken WMS must cost the plot's outline nothing, so a failed ground
  leaves paper behind the drawing rather than an error.
* **It is the app's own drawing, not a second one.** Paper, ink, the halo under
  every line and the typeface come from `tokens.css` and from the same npm
  packages the browser loads -- see ``FONT_DIR``.
"""

from __future__ import annotations

import asyncio
import io
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

from ..cache import DiskCache
from .tiles import TileService

# What every scraper crops to. Facebook, Slack, WhatsApp, Signal and Mastodon
# all state 1.91:1; 1200 x 630 is that ratio at the size they all accept.
CARD = (1200, 630)

# The band along the bottom that carries the name. Paper, not a wash over the
# map: text over a photograph or a street grid is the one thing a preview must
# stay readable through, and it is read at thumbnail size.
BAND_H = 148

# The drawing's own margin inside what is left. A plot that touches the frame
# reads as a crop of something bigger.
PAD = 44

# From `frontend/src/styles/tokens.css`, light. A preview has no viewer whose
# theme could be asked -- it is fetched by a server -- so the card is the light
# one, always.
PAPER = (241, 235, 225)
SURFACE = (250, 247, 241)
INK = (30, 26, 22)
MUTED = (111, 103, 92)
LINE = (220, 211, 198)
LODEN = (47, 74, 58)
HALO = (255, 255, 255)
PARCEL_FILL = (239, 237, 231)
BUILDING = (181, 129, 60)
BUILDING_EDGE = (124, 86, 32)

# The same npm packages the browser loads, vendored as .woff because that is
# the format FreeType reads without brotli. Fontsource ships both; the browser
# takes the .woff2 next door.
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _mercator_px(lon: float, lat: float, zoom: int, tile_size: int) -> tuple[float, float]:
    """Web Mercator pixel coordinates of a point, at this zoom."""

    span = tile_size * 2**zoom
    x = (lon + 180.0) / 360.0 * span
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * span
    return x, y


def _to_wgs84(ring: Iterable[dict[str, float]], anchor: dict[str, float]) -> list[tuple[float, float]]:
    """Local metres east/north of the anchor back to (lon, lat).

    The inverse of `frontend/src/lib/projection.js`, with the same constant:
    the plot's outline is stored in its own local frame and only the anchor
    says where on the earth that frame sits.
    """

    metres_per_degree = 111320.0
    scale_x = metres_per_degree * math.cos(math.radians(anchor["lat"]))
    return [
        (anchor["lon"] + point["x"] / scale_x, anchor["lat"] + point["y"] / metres_per_degree)
        for point in ring
    ]


def _ring(document: dict[str, Any]) -> list[dict[str, float]] | None:
    """The plot outline, if the document carries a usable one."""

    polygon = document.get("polygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None
    ring: list[dict[str, float]] = []
    for point in polygon:
        if not isinstance(point, dict):
            return None
        try:
            ring.append({"x": float(point["x"]), "y": float(point["y"])})
        except (KeyError, TypeError, ValueError):
            return None
    return ring


def _anchor(document: dict[str, Any]) -> dict[str, float] | None:
    anchor = document.get("anchor")
    if not isinstance(anchor, dict):
        return None
    try:
        lat, lon = float(anchor["lat"]), float(anchor["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"lat": lat, "lon": lon} if -90 <= lat <= 90 and -180 <= lon <= 180 else None


class _Frame:
    """The map view: which zoom, and where its top left pixel sits.

    Everything is in Web Mercator pixels at one integer zoom, which is what the
    tiles are cut on. Working in the tiles' own grid is what keeps the outline
    on its own parcel -- deriving a scale first and hunting for a matching zoom
    afterwards is how a drawing ends up half a step off its ground.

    A zoom is a factor of two, so fitting to one leaves a plot filling anything
    between a third and the whole frame. The frame is therefore rendered
    *oversized* at the zoom that fits and scaled back afterwards -- the same
    move `tiles.py` makes to get under a WMS scale limit -- so every plot sits
    in the same proportion of the card whatever its size.
    """

    #: How much of the card the outline itself takes. The rest is the
    #: neighbourhood, which is what makes a plot recognisable at all.
    SLACK = 0.78

    def __init__(
        self,
        points: list[tuple[float, float]],
        width: int,
        height: int,
        tile_size: int,
        max_zoom: int,
    ):
        self.tile_size = tile_size
        for zoom in range(min(20, max_zoom), 9, -1):
            xs = [_mercator_px(lon, lat, zoom, tile_size)[0] for lon, lat in points]
            ys = [_mercator_px(lon, lat, zoom, tile_size)[1] for lon, lat in points]
            span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
            scale = min(
                self.SLACK * width / max(span_x, 1e-6),
                self.SLACK * height / max(span_y, 1e-6),
            )
            if scale <= 1:
                self.zoom = zoom
                self.scale = scale
                self.width = round(width / scale)
                self.height = round(height / scale)
                self.left = (min(xs) + max(xs)) / 2 - self.width / 2
                self.top = (min(ys) + max(ys)) / 2 - self.height / 2
                return
        # Either a shape too big for any sensible map, or one so small that even
        # the deepest zoom cannot fill the card. Both are drawn without a
        # ground rather than framed dishonestly.
        raise ValueError("Der Umriss passt in keine sinnvolle Kartenansicht.")

    def place(self, lon: float, lat: float) -> tuple[float, float]:
        """Where a point lands on the finished card, after the scaling back."""

        x, y = _mercator_px(lon, lat, self.zoom, self.tile_size)
        return (x - self.left) * self.scale, (y - self.top) * self.scale

    def tiles(self) -> list[tuple[int, int, int, int]]:
        """(x, y, offset_x, offset_y) for every tile the oversized frame touches."""

        size = self.tile_size
        first_x, first_y = math.floor(self.left / size), math.floor(self.top / size)
        last_x = math.floor((self.left + self.width) / size)
        last_y = math.floor((self.top + self.height) / size)
        limit = 2**self.zoom
        return [
            (x, y, int(x * size - self.left), int(y * size - self.top))
            for x in range(first_x, last_x + 1)
            for y in range(first_y, last_y + 1)
            if 0 <= x < limit and 0 <= y < limit
        ]


async def _ground(frame: _Frame, tiles: TileService, layer: str, box: tuple[int, int]) -> Image.Image | None:
    """The map under the drawing, or nothing.

    Nothing is a real outcome, not an error: a card whose ground did not arrive
    is a card on paper, and that is far better than a chat showing a broken
    image because a WMS was slow.
    """

    wanted = frame.tiles()
    if not wanted:
        return None
    results = await asyncio.gather(
        *(tiles.tile(layer, frame.zoom, x, y) for x, y, _, _ in wanted),
        return_exceptions=True,
    )
    ground = Image.new("RGB", (frame.width, frame.height), PAPER)
    drawn = 0
    for (_, _, offset_x, offset_y), result in zip(wanted, results):
        if isinstance(result, BaseException):
            continue
        try:
            tile = Image.open(io.BytesIO(result[0])).convert("RGBA")
        except OSError:
            continue
        ground.paste(tile, (offset_x, offset_y), tile)
        drawn += 1
    return ground.resize(box, Image.LANCZOS) if drawn else None


def _outline(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], *, width: int) -> None:
    """A line with the halo the site plan draws under every one of its own.

    Over a photograph or a street grid an unhaloed hairline disappears; this is
    the technique `SitePlan` uses, at the same proportions.
    """

    draw.line([*points, points[0]], fill=HALO, width=width + 6, joint="curve")
    draw.line([*points, points[0]], fill=INK, width=width, joint="curve")


def _shorten(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, room: int) -> str:
    if draw.textlength(text, font=font) <= room:
        return text
    while text and draw.textlength(text + "…", font=font) > room:
        text = text[:-1]
    return text.rstrip() + "…"


def _band(image: Image.Image, title: str, subtitle: str) -> None:
    """The name along the bottom, on paper rather than over the map."""

    draw = ImageDraw.Draw(image)
    top = CARD[1] - BAND_H
    draw.rectangle([0, top, CARD[0], CARD[1]], fill=SURFACE)
    draw.line([(0, top), (CARD[0], top)], fill=LINE, width=2)

    mark = _font("archivo-700.woff", 27)
    mark_text = "where2build"
    mark_width = draw.textlength(mark_text, font=mark)
    draw.text((CARD[0] - PAD - mark_width, top + 54), mark_text, font=mark, fill=LODEN)

    room = int(CARD[0] - 2 * PAD - mark_width - 40)
    name = _font("archivo-700.woff", 46)
    draw.text((PAD, top + 30), _shorten(draw, title, name, room), font=name, fill=INK)
    if subtitle:
        small = _font("public-sans-400.woff", 25)
        draw.text((PAD, top + 92), _shorten(draw, subtitle, small, room), font=small, fill=MUTED)


def _draw_plot(image: Image.Image, document: dict[str, Any], frame: _Frame, anchor: dict[str, float]) -> None:
    ring = _ring(document) or []
    points = [frame.place(lon, lat) for lon, lat in _to_wgs84(ring, anchor)]

    fill = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(fill).polygon(points, fill=(*PARCEL_FILL, 107))   # .42, as in SitePlan
    image.alpha_composite(fill)

    draw = ImageDraw.Draw(image)
    _outline(draw, points, width=4)

    building = document.get("placedBuilding")
    if isinstance(building, dict):
        corners = _building_corners(building)
        if corners:
            placed = [frame.place(lon, lat) for lon, lat in _to_wgs84(corners, anchor)]
            solid = Image.new("RGBA", image.size, (0, 0, 0, 0))
            ImageDraw.Draw(solid).polygon(placed, fill=(*BUILDING, 224), outline=(*BUILDING_EDGE, 255))
            image.alpha_composite(solid)


def _building_corners(building: dict[str, Any]) -> list[dict[str, float]] | None:
    """The footprint's four corners in the plot's local frame.

    The same rectangle the browser draws: a width and a depth about a centre,
    turned by the rotation the user left it at.
    """

    try:
        width = float(building["width"])
        depth = float(building["depth"])
        cx = float(building.get("cx", 0.0))
        cy = float(building.get("cy", 0.0))
        rotation = math.radians(float(building.get("rotation", 0.0)))
    except (KeyError, TypeError, ValueError):
        return None
    if not (width > 0 and depth > 0):
        return None
    cos, sin = math.cos(rotation), math.sin(rotation)
    half_w, half_d = width / 2, depth / 2
    return [
        {"x": cx + dx * cos - dy * sin, "y": cy + dx * sin + dy * cos}
        for dx, dy in ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))
    ]


async def card(
    document: dict[str, Any],
    tiles: TileService | None = None,
    *,
    layer: str = "dop",
) -> bytes:
    """The 1200 x 630 card for one shared plot, as JPEG.

    The ground is the orthophoto, not the street map: at the size a chat shows
    this, the photograph is what makes a plot look like a place -- trees, the
    neighbours' roofs, whether the ground is cleared. The outline carries the
    halo the site plan draws for exactly that reason.
    """

    image = Image.new("RGBA", CARD, PAPER)
    map_box = (CARD[0] - 2 * PAD, CARD[1] - BAND_H - 2 * PAD)

    ring, anchor = _ring(document), _anchor(document)
    frame = None
    if ring and anchor:
        try:
            frame = _Frame(
                _to_wgs84(ring, anchor),
                map_box[0],
                map_box[1],
                tiles.settings.tile_size if tiles else 256,
                tiles.settings.max_zoom if tiles else 20,
            )
        except ValueError:
            frame = None

    if frame is not None:
        panel = Image.new("RGBA", map_box, PARCEL_FILL)
        ground = await _ground(frame, tiles, layer, map_box) if tiles else None
        if ground is not None:
            panel.paste(ground, (0, 0))
        _draw_plot(panel, document, frame, anchor)
        image.alpha_composite(_rounded(panel), (PAD, PAD))

    _band(image, _title(document), _subtitle(document))

    out = io.BytesIO()
    # JPEG, and the quality is not a matter of taste. The same card as a PNG is
    # 574 kB because the ground is a photograph, and several clients -- WhatsApp
    # among them -- simply show no preview above a few hundred kilobytes, with
    # nothing to see anywhere. At 86 this is ~100 kB and the band's type stays
    # clean; below ~80 the lettering starts to fringe.
    image.convert("RGB").save(out, format="JPEG", quality=86, optimize=True, progressive=True)
    return out.getvalue()


def _rounded(panel: Image.Image, radius: int = 14) -> Image.Image:
    """The panel's corners, as every panel in the app has them."""

    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, panel.width - 1, panel.height - 1], radius, fill=255)
    ImageDraw.Draw(panel).rounded_rectangle(
        [0, 0, panel.width - 1, panel.height - 1], radius, outline=LINE, width=2
    )
    panel.putalpha(mask)
    return panel


def _title(document: dict[str, Any]) -> str:
    return str(document.get("name") or "Geteiltes Grundstück").strip() or "Geteiltes Grundstück"


def _subtitle(document: dict[str, Any]) -> str:
    """Gemarkung, parcels and the official area -- whatever of it is there.

    A missing figure is left out rather than dashed: on a card the size of a
    thumbnail a dash reads as a value nobody could measure.
    """

    parts: list[str] = []
    gemarkung = str(document.get("gemarkung") or "").strip()
    if gemarkung:
        parts.append(gemarkung)
    parcels = document.get("flurstuecke")
    if isinstance(parcels, list) and parcels:
        listed = " · ".join(str(p) for p in parcels[:3])
        parts.append(f"Flurstück {listed}" + (" …" if len(parcels) > 3 else ""))
    area = document.get("officialArea")
    if isinstance(area, (int, float)) and area > 0:
        parts.append(f"{_german(round(area))} m²")
    return " · ".join(parts)


def _german(value: int) -> str:
    return f"{value:,}".replace(",", ".")


# Bumped whenever the drawing changes, and that includes the file format. A
# cache key that does not name what produced the answer outlives the fix --
# three times now in this repo, the third being this very card: switching it
# from PNG to JPEG kept serving the stored PNG under `Content-Type:
# image/jpeg`, which every client renders anyway, so nothing looked wrong and
# the file was still five times too big for a WhatsApp preview. A card is kept
# for the life of the share, so without this a corrected drawing would never
# reach the links already handed out.
CARD_VERSION = 2


class PreviewService:
    """Draws a card once per share and keeps it.

    A shared document never changes, so neither does its card; a link that gets
    passed around a group chat is then one file read per scraper rather than a
    fresh run at the orthophoto.
    """

    def __init__(self, tiles: TileService, cache_dir: Path) -> None:
        self.tiles = tiles
        # No TTL: the share itself expires, and the sweeper enforces the size
        # ceiling over the whole cache tree.
        self.cache = DiskCache(cache_dir / "vorschau", ttl_s=None)

    async def card(self, token: str, document: dict[str, Any]) -> bytes:
        key = f"{CARD_VERSION}/{token}"
        cached = self.cache.get_bytes(key)
        if cached is not None:
            return cached
        drawn = await card(document, self.tiles)
        self.cache.set_bytes(key, drawn)
        return drawn
