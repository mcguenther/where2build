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
 * The aerial photograph is every Land's own survey, composed by the proxy, over
 * the BKG's Sentinel-2 mosaic. Several licences ask for the name *and* the
 * year of retrieval; the tiles are cached for a month, so this year is it.
 */
const YEAR = new Date().getFullYear();
export const AERIAL =
  `Luftbilder © LGL-BW, LDBV, GDI Berlin, GeoBasis-DE/LGB, Landesamt GeoInformation Bremen, `
  + `LGV Hamburg, HVBG, GeoBasis-DE/M-V, LGLN, Geobasis NRW, GeoBasis-DE/LVermGeoRP, LVGL, `
  + `GeoSN, GeoBasis-DE/LVermGeo ST, GeoBasis-DE/LVermGeo SH, GDI-Th (${YEAR}), `
  + `CC BY 4.0 und dl-de/by-2-0 · Übersicht: Europäische Union, enthält veränderte `
  + `Copernicus Sentinel-Daten (${YEAR})`;
export const LFULG = "Umgebungslärmkartierung © LfULG";

/**
 * The zoom the search map starts drawing the cadastre at. Chosen, not a limit
 * of the service.
 *
 * The proxy can make `adv_alkis_flurstuecke` draw from zoom 15 (see the
 * `flurstuecke` layer in `services/tiles.py`), and the search map used to ask
 * for it there. Over a district every hedge then carried a boundary, and an
 * ambiguous run's candidates disappeared among a few hundred outlines drawn in
 * the service's „Gelb“ style: the same colour as nothing the app means. So the
 * search map now asks for the same black Liegenschaftskarte the site plan lays
 * over its photograph, and only from 17, where a plot is some forty pixels wide.
 * The numbers become legible one step further in, at 18 (measured over Mölkau
 * on 23.09.2026; at 17 they are three pixels high).
 */
export const PARCEL_OUTLINE_MIN_ZOOM = 17;

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
  "laerm-nacht": { name: "Lärm (Straße, nachts)", attribution: LFULG },
  /* The cadastre as line work: boundaries, parcel numbers, boundary points and
     street names on transparent ground. It is drawn nearly opaque, because a
     line at 45 % over a photograph is a smudge — the veil setting below is for
     the noise bands, which are areas and must not hide what is under them.

     Not the oversampled `flurstuecke` layer: that one is rendered large so
     its outlines still draw across a district, and its labels come back
     scaled down with it. Over one plot the numbers are the whole point, so
     this asks for a plain tile and moves the scale limit instead. The search
     map's ground uses this one as well, from `PARCEL_OUTLINE_MIN_ZOOM`. */
  liegenschaftskarte: { name: "Flurstücke", attribution: GEOSN, opacity: 0.95 }
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
          "raster-opacity": overlay.opacity
            ?? (backdrop === "aerial" ? OVERLAY_OPACITY.aerial : OVERLAY_OPACITY.other)
        }
      }
    ]
  };
}

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
 * the authority's own transparent renderings, so nothing is drawn by hand. The
 * outlines are the Liegenschaftskarte, not the oversampled `flurstuecke`
 * contours, so they read the same as on the site plan.
 *
 * The photo is Germany's, not only Saxony's: the proxy composes every Land's
 * survey over a Sentinel-2 mosaic, so the search's first view of the state is
 * not an island on paper. The two overlays stay Saxon — outside, they are
 * transparent and the photo shows through alone.
 *
 * The outlines carry a floor; see `PARCEL_OUTLINE_MIN_ZOOM`.
 */
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
      luftbild: { ...source("luftbild"), maxzoom: 20, attribution: AERIAL },
      strassen: { ...source("strassen"), maxzoom: 20 },
      liegenschaftskarte: {
        ...source("liegenschaftskarte"), minzoom: PARCEL_OUTLINE_MIN_ZOOM, maxzoom: 20
      }
    },
    layers: [
      { id: "luftbild", type: "raster", source: "luftbild" },
      { id: "strassen", type: "raster", source: "strassen", paint: { "raster-opacity": 0.9 } },
      {
        id: "liegenschaftskarte",
        type: "raster",
        source: "liegenschaftskarte",
        minzoom: PARCEL_OUTLINE_MIN_ZOOM,
        paint: { "raster-opacity": OVERLAYS.liegenschaftskarte.opacity }
      }
    ]
  };
};

/** What each backdrop offers. `none` keeps the drawing on plain paper. */
export const BACKDROPS = {
  map: () => vectorStyle(),
  aerial: async () => rasterStyle("luftbild", AERIAL),
  cadastre: async () => rasterStyle("alkis", GEOSN),
  /** Photo, streets and parcel outlines together — the search map's ground. */
  site: async () => aerialCadastreStyle()
};
