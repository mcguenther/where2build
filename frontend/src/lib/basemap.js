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

/**
 * Whether this browser can draw a MapLibre map at all.
 *
 * Asked before one is constructed, because a backdrop that needs no network —
 * the raster grounds do not — otherwise builds a half-initialised map wherever
 * there is no WebGL, and only says so on the way out, where `remove()` throws
 * inside the library. That is exactly what happens under jsdom, and it is also
 * what a browser with WebGL switched off does.
 */
export function canRenderMap() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * The orthophoto with the cadastre drawn on it: what a listing's own
 * photographs can be compared against.
 *
 * Three layers, and the order is the whole trick — the photo underneath, the
 * roads and their names over it, the parcel outlines on top. Both overlays are
 * the authority's own transparent renderings, so nothing is drawn by hand.
 *
 * `minzoom` on the outlines is measured, not chosen. `adv_alkis_flurstuecke`
 * carries `MaxScaleDenominator: 2000` and answers HTTP 200 with a fully
 * transparent PNG above it, which at a 256 px tile would mean nothing below
 * zoom 19. The proxy gets round that by rendering each tile larger — the
 * denominator is (bbox / image width) / 0,00028, so a bigger image over the
 * same box falls under the limit — and scaling it back to a tile. That works
 * down to zoom 15; zoom 14 would need 4368 px for one tile and the service
 * refuses anything over 4000. Below the floor the layer is left out, because a
 * transparent tile looks like a broken overlay rather than a scale.
 */
export const PARCEL_OUTLINE_MIN_ZOOM = 15;

export const aerialCadastreStyle = () => {
  const origin = window.location.origin;
  const source = layer => ({
    type: "raster",
    tiles: [`${origin}/api/tiles/${layer}/{z}/{x}/{y}.png`],
    tileSize: 256,
    attribution: GEOSN
  });
  return {
    version: 8,
    sources: {
      dop: { ...source("dop"), maxzoom: 20 },
      strassen: { ...source("strassen"), maxzoom: 20 },
      flurstuecke: { ...source("flurstuecke"), minzoom: PARCEL_OUTLINE_MIN_ZOOM, maxzoom: 20 }
    },
    layers: [
      { id: "dop", type: "raster", source: "dop" },
      { id: "strassen", type: "raster", source: "strassen", paint: { "raster-opacity": 0.9 } },
      {
        id: "flurstuecke",
        type: "raster",
        source: "flurstuecke",
        minzoom: PARCEL_OUTLINE_MIN_ZOOM
      }
    ]
  };
};

/** What each backdrop offers. `none` keeps the drawing on plain paper. */
export const BACKDROPS = {
  map: () => vectorStyle(),
  aerial: async () => rasterStyle("dop", GEOSN),
  cadastre: async () => rasterStyle("alkis", GEOSN),
  /** Photo, streets and parcel outlines together — the search map's ground. */
  site: async () => aerialCadastreStyle()
};
