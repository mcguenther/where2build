/**
 * Map styles for anything that needs ground under a drawing.
 *
 * Every backdrop comes through our own backend. The vector style is rewritten
 * server-side so each URL inside it points back at /api/basemap/; the raster
 * layers are the authority's own WMS behind /api/tiles/. The browser therefore
 * needs no route to the internet, which is what makes this work behind a
 * firewall — and what stopped it working when the style was loaded directly.
 */

import { darkTheme } from "./store.js";

const MAP_STYLE_URL = "/api/basemap/style.json";

/**
 * The proxy answers with relative URLs, because only the browser knows which
 * origin it reached this API on. MapLibre needs them expanded before it can
 * use them: it rejects a relative `sprite` outright ("must be absolute"), and
 * handed a style object it has no base to resolve a source's TileJSON — and
 * then the relative tile URLs inside that TileJSON go nowhere, which is a
 * silent failure: the style never finishes loading and no tile is ever asked
 * for. So every URL is made absolute here, against this page.
 *
 * The palette follows the interface. A drawing sits *on* the backdrop, so a
 * near-white ground under a dark page is not a matter of taste — it is a glare
 * source with the plot outline lost in it. The variant travels in the URL, so
 * the two documents cache separately.
 */
export async function vectorStyle(dark = darkTheme()) {
  // A style that does not arrive means no backdrop, not a page that waits
  // forever: the drawing is what matters and it needs no network at all.
  const signal = AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined;
  const response = await fetch(`${MAP_STYLE_URL}?variant=${dark ? "dark" : "light"}`, { signal });
  if (!response.ok) throw new Error(`Kartenstil nicht ladbar (HTTP ${response.status})`);
  const style = await response.json();
  const origin = window.location.origin;
  const absolute = value => (typeof value === "string" && value.startsWith("/") ? `${origin}${value}` : value);

  if (style.glyphs) style.glyphs = absolute(style.glyphs);
  if (style.sprite) {
    style.sprite = Array.isArray(style.sprite)
      ? style.sprite.map(e => ({ ...e, url: absolute(e.url) }))
      : absolute(style.sprite);
  }
  // A source that points at a TileJSON is resolved here instead of by MapLibre:
  // the tile URLs inside that document are relative too, and MapLibre does not
  // resolve those against the source URL. Inlining them ends the guesswork.
  await Promise.all(Object.values(style.sources || {}).map(async source => {
    if (Array.isArray(source.tiles)) source.tiles = source.tiles.map(absolute);
    if (!source.url) return;
    const tilejson = await fetch(absolute(source.url), { signal }).then(r => (r.ok ? r.json() : null));
    if (!tilejson || !Array.isArray(tilejson.tiles)) return;
    delete source.url;
    Object.assign(source, tilejson, { type: source.type, tiles: tilejson.tiles.map(absolute) });
  }));
  return style;
}

/** A minimal raster style around one of the proxied WMS layers. */
export const rasterStyle = (layer, attribution) => ({
  version: 8,
  sources: {
    [layer]: {
      type: "raster",
      tiles: [`${window.location.origin}/api/tiles/${layer}/{z}/{x}/{y}.png`],
      tileSize: 256,
      maxzoom: 20,
      attribution
    }
  },
  layers: [{ id: layer, type: "raster", source: layer }]
});

export const GEOSN = "© GeoSN, dl-de/by-2-0";
export const LFULG = "Umgebungslärmkartierung © LfULG";

/**
 * Raster layers that go *on top of* a backdrop rather than instead of one.
 *
 * The noise survey is not a WMS tile source — its own service speaks EPSG:4326
 * and 25833 but not 3857, so MapLibre's `{bbox-epsg-3857}` raster source would
 * get nothing at all and say nothing about it. `/api/tiles/laerm/…` goes
 * through the ArcGIS `export` endpoint instead, which reprojects server-side
 * and, with the dpi the proxy computes, never falls silently under the layer's
 * own scale threshold.
 *
 * Over the aerial photograph the veil is thinner: at full strength the bands
 * hide exactly the thing somebody switched the photo on to see.
 */
export const OVERLAYS = {
  laerm: { name: "Lärm (Straße, 24 h)", attribution: LFULG },
  "laerm-nacht": { name: "Lärm (Straße, nachts)", attribution: LFULG }
};

const OVERLAY_OPACITY = { aerial: 0.45, other: 0.62 };

/**
 * The bands the noise layer actually draws, in the service's own colours.
 *
 * Read off the layer's renderer (`MapServer/4?f=json`), not chosen here, so the
 * key beside the map is the map. Note what is missing from it: the data holds a
 * `Lden4549` band that the renderer has no entry for — the survey has measured
 * 45 to 49 dB(A) and draws nothing for it. So the check text can say "below
 * 45 dB(A)" while the key starts at 50, and both are correct.
 */
export const NOISE_BANDS = {
  laerm: [
    { label: "50–54", colour: "rgb(184,214,209)" },
    { label: "55–59", colour: "rgb(226,242,191)" },
    { label: "60–64", colour: "rgb(243,198,131)" },
    { label: "65–69", colour: "rgb(205,70,62)" },
    { label: "70–74", colour: "rgb(117,8,92)" },
    { label: "ab 75", colour: "rgb(67,10,74)" }
  ]
};

/** Put an overlay's source and layer on top of a style document. */
export function withOverlay(style, id, backdrop = "map") {
  const overlay = OVERLAYS[id];
  if (!overlay || !style?.sources) return style;
  return {
    ...style,
    sources: {
      ...style.sources,
      [id]: {
        type: "raster",
        tiles: [`${window.location.origin}/api/tiles/${id}/{z}/{x}/{y}.png`],
        tileSize: 256,
        maxzoom: 20,
        attribution: overlay.attribution
      }
    },
    layers: [
      ...style.layers,
      {
        id,
        type: "raster",
        source: id,
        paint: {
          "raster-opacity": backdrop === "aerial" ? OVERLAY_OPACITY.aerial : OVERLAY_OPACITY.other
        }
      }
    ]
  };
}

/** What each backdrop offers. `none` keeps the drawing on plain paper. */
export const BACKDROPS = {
  map: () => vectorStyle(),
  aerial: async () => rasterStyle("dop", GEOSN),
  cadastre: async () => rasterStyle("alkis", GEOSN)
};
