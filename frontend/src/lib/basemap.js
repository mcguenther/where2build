/**
 * Map styles for anything that needs ground under a drawing.
 *
 * Every backdrop comes through our own backend. The vector style is rewritten
 * server-side so each URL inside it points back at /api/basemap/; the raster
 * layers are the authority's own WMS behind /api/tiles/. The browser therefore
 * needs no route to the internet, which is what makes this work behind a
 * firewall — and what stopped it working when the style was loaded directly.
 */

const MAP_STYLE_URL = "/api/basemap/style.json";

/**
 * The proxy answers with relative URLs, because only the browser knows which
 * origin it reached this API on. MapLibre needs them expanded before it can
 * use them: it rejects a relative `sprite` outright ("must be absolute"), and
 * handed a style object it has no base to resolve a source's TileJSON — and
 * then the relative tile URLs inside that TileJSON go nowhere, which is a
 * silent failure: the style never finishes loading and no tile is ever asked
 * for. So every URL is made absolute here, against this page.
 */
export async function vectorStyle() {
  // A style that does not arrive means no backdrop, not a page that waits
  // forever: the drawing is what matters and it needs no network at all.
  const signal = AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined;
  const response = await fetch(MAP_STYLE_URL, { signal });
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

/** What each backdrop offers. `none` keeps the drawing on plain paper. */
export const BACKDROPS = {
  map: vectorStyle,
  aerial: async () => rasterStyle("dop", GEOSN),
  cadastre: async () => rasterStyle("alkis", GEOSN)
};
