/**
 * Route geometry for the destination cards.
 *
 * MOTIS answers with a real GeoJSON LineString per origin/destination/mode.
 * These helpers fit that line into the small SVG of a route card. Nothing here
 * invents a course: a card without geometry stays empty and says so.
 */

/**
 * Modes in the order the cards list them, with their German labels.
 *
 * The last three are one row, not three: a destination is routed with exactly
 * one of them, and which one is either pinned on the destination or chosen by
 * the backend. They are listed separately because the label has to say which
 * feeder the number belongs to — "32 min ÖPNV" reads differently once it turns
 * out to start with a 15-minute bike ride.
 */
export const MODES = [
  { mode: "car", name: "Auto" },
  { mode: "bike", name: "Rad" },
  { mode: "transit", name: "ÖPNV" },
  { mode: "bike_transit", name: "Rad + ÖPNV" },
  { mode: "car_transit", name: "Auto + ÖPNV" }
];

/**
 * How the first stop is reached, as it is stored on a destination.
 *
 * `wert` is the value of the destination's `zubringer` field — the wire format,
 * shared with the backend's `Zubringer` enum. `name` is what a picker shows.
 * "automatic" is the default and what every destination stored before the field
 * existed falls back to.
 */
export const ZUBRINGER = [
  { wert: "automatic", name: "Automatisch" },
  { wert: "walk", name: "Zu Fuß zum ÖPNV" },
  { wert: "bike", name: "Rad zum ÖPNV" },
  { wert: "car", name: "Auto zum ÖPNV" }
];

const ZUBRINGER_VALUES = ZUBRINGER.map(z => z.wert);

/** A destination's stored feeder choice, or the default when it has none. */
export function zubringerOf(destination) {
  const stored = destination && destination.zubringer;
  return ZUBRINGER_VALUES.includes(stored) ? stored : "automatic";
}

const RADIANS_PER_DEGREE = Math.PI / 180;

/**
 * Web Mercator, unscaled. Only ratios matter here, so the earth radius drops
 * out — but the latitude stretch does not, and dropping it would tilt every
 * route that runs north.
 */
function mercator([lon, lat]) {
  const phi = Math.max(-85.05, Math.min(85.05, lat)) * RADIANS_PER_DEGREE;
  return { x: lon * RADIANS_PER_DEGREE, y: Math.log(Math.tan(Math.PI / 4 + phi / 2)) };
}

/**
 * Bounding box over several lines at once, so all modes share one frame.
 * Carries the geographic extent alongside the projected one — the card needs
 * the first to draw and the second to label a scale.
 */
export function routeBounds(lines) {
  const coordinates = lines.filter(Boolean).flat();
  if (!coordinates.length) return null;
  const points = coordinates.map(mercator);
  const lons = coordinates.map(c => c[0]);
  const lats = coordinates.map(c => c[1]);
  const xs = points.map(p => p.x);
  const ys = points.map(p => p.y);
  return {
    minX: Math.min(...xs), maxX: Math.max(...xs),
    minY: Math.min(...ys), maxY: Math.max(...ys),
    minLon: Math.min(...lons), maxLon: Math.max(...lons),
    minLat: Math.min(...lats), maxLat: Math.max(...lats)
  };
}

/** How wide the drawn frame is on the ground, in metres. */
export function groundWidth(bounds) {
  if (!bounds) return 0;
  const meanLatitude = ((bounds.minLat + bounds.maxLat) / 2) * RADIANS_PER_DEGREE;
  return (bounds.maxLon - bounds.minLon) * RADIANS_PER_DEGREE * 6378137 * Math.cos(meanLatitude);
}

/**
 * How wide the fitted frame is on the ground, in metres — the box, not the
 * route inside it. A route running due north spans almost no longitude, so the
 * extent of its bounding box says nothing about the picture drawn around it.
 */
export function frameGroundWidth(bounds, fit, width) {
  if (!bounds || !fit || !(fit.scale > 0)) return 0;
  const meanLatitude = ((bounds.minLat + bounds.maxLat) / 2) * RADIANS_PER_DEGREE;
  return (width / fit.scale) * 6378137 * Math.cos(meanLatitude);
}

/**
 * The proportions of a route: the projected box's width over its height.
 * Above 1 it runs east-west, below it north-south. This is what decides how
 * tall a card's drawing has to be — a frame of one fixed shape gives a route
 * due north two empty margins and a motorway run to the next town a strip.
 */
export function routeAspect(bounds) {
  if (!bounds) return 1;
  const w = Math.max(bounds.maxX - bounds.minX, 1e-9);
  const h = Math.max(bounds.maxY - bounds.minY, 1e-9);
  return w / h;
}

/**
 * A drawing frame, in SVG user units, that follows the route's own shape.
 *
 * The bounds are clamped before they become a frame: followed exactly, a
 * commute along the B6 would be a 30-unit strip and a route due north a column
 * taller than the screen. Inside the clamp the frame is exact, so the fit does
 * not letterbox and the raster ground fills the picture rather than the paper
 * colour. The padding is a fraction of the width, not a constant: the same
 * 12 units that keep a line off the edge of a 300-unit card are invisible on a
 * 960-unit one.
 */
export function sketchFrame(bounds, width, minAspect = 0.8, maxAspect = 2.2) {
  const padding = Math.round(width / 25);
  const aspect = Math.min(maxAspect, Math.max(minAspect, routeAspect(bounds)));
  return { width, height: Math.round((width - 2 * padding) / aspect) + 2 * padding, padding, aspect };
}

/**
 * Fit the bounding box into `width` x `height` without distorting it: one
 * scale for both axes, the shorter one centred. A stretched map is a wrong map.
 */
export function fitBounds(bounds, width, height, padding = 12) {
  if (!bounds) return null;
  const w = Math.max(bounds.maxX - bounds.minX, 1e-9);
  const h = Math.max(bounds.maxY - bounds.minY, 1e-9);
  const scale = Math.min((width - 2 * padding) / w, (height - 2 * padding) / h);
  return {
    scale,
    dx: (width - (bounds.maxX + bounds.minX) * scale) / 2,
    // Screen y grows downward, Mercator y grows northward.
    dy: (height + (bounds.maxY + bounds.minY) * scale) / 2
  };
}

/** One WGS84 coordinate to SVG user units. */
export function toScreen(coordinate, fit) {
  const m = mercator(coordinate);
  return { x: m.x * fit.scale + fit.dx, y: fit.dy - m.y * fit.scale };
}

/** A LineString as an SVG points list, ready for <polyline>. */
export function toPolyline(line, fit) {
  if (!line || line.length < 2) return "";
  return line.map(c => {
    const p = toScreen(c, fit);
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(" ");
}

/** Coordinates out of a GeoJSON geometry; anything else yields nothing. */
export function coordinatesOf(geometry) {
  if (!geometry) return null;
  if (geometry.type === "LineString" && Array.isArray(geometry.coordinates)) {
    return geometry.coordinates.length >= 2 ? geometry.coordinates : null;
  }
  if (geometry.type === "MultiLineString" && Array.isArray(geometry.coordinates)) {
    const joined = geometry.coordinates.flat();
    return joined.length >= 2 ? joined : null;
  }
  return null;
}

/** The fastest mode that was actually reached — it decides a card's colour. */
export function fastestMode(route) {
  if (!route || !route.modes) return null;
  const reached = MODES
    .map(m => ({ mode: m.mode, ...(route.modes[m.mode] || {}) }))
    .filter(m => m.erreichbar && Number.isFinite(m.duration_s));
  if (!reached.length) return null;
  return reached.reduce((a, b) => (b.duration_s < a.duration_s ? b : a)).mode;
}

/* ---------------------------------------------------------------------------
 * The ground under the sketch
 *
 * A route card is not a site plan. A plot page carries one card per destination
 * — up to twenty — and a MapLibre instance each would exhaust the browser's
 * WebGL contexts long before that, silently: contexts past the limit are
 * evicted and those maps go blank with nothing in the console. So the backdrop
 * here is not MapLibre. It is the same raster tiles the WMS proxy already
 * serves, placed as <image> elements inside the SVG that is drawn anyway.
 *
 * That buys three things beyond the context limit: it prints (a WebGL canvas
 * needs `preserveDrawingBuffer` and often still prints blank, which is why
 * SitePlan sets it at construction), a tile that never arrives is one empty
 * <image> rather than a torn-down map, and the placement is arithmetic that can
 * be tested without a browser.
 * ------------------------------------------------------------------------- */

/** Web Mercator raster tiles are 256 pixels; MapLibre's vector zoom is not. */
const TILE_PIXELS = 256;

/** Deepest zoom the WMS proxy is configured for. */
const MAX_ZOOM = 19;

/** Above this the card is asking for traffic, not for detail — measured on the
 *  300 x 150 frame the cards started out with. A larger frame covers
 *  proportionally more ground at the same zoom, because the zoom is picked to
 *  keep a tile around 256 units wide either way, so the budget grows with the
 *  frame's area rather than holding a card alone in its row to the same two
 *  dozen tiles as one of three. */
const MAX_TILES = 24;
const BASE_FRAME_AREA = 300 * 150;

const tileBudget = (width, height) =>
  Math.max(MAX_TILES, Math.round((MAX_TILES * width * height) / BASE_FRAME_AREA));

/**
 * Which raster tiles cover the drawn frame, and where each one belongs.
 *
 * `fit` maps unscaled Mercator onto SVG user units, so one whole world is 2π of
 * those times `fit.scale` — and that is what fixes both the zoom and the size a
 * tile has to be drawn at. Returns `null` when there is no sensible cover,
 * which leaves the flat ground the card already had.
 */
export function tileCover(fit, width, height, maxTiles = tileBudget(width, height)) {
  if (!fit || !(fit.scale > 0)) return null;
  const world = 2 * Math.PI * fit.scale;              // SVG units for the whole world
  const zoom = Math.max(0, Math.min(MAX_ZOOM, Math.round(Math.log2(world / TILE_PIXELS))));
  const columns = 2 ** zoom;
  const size = world / columns;

  // Screen back to tile index: x grows east with the drawing, y grows south.
  const clamp = value => Math.max(0, Math.min(columns - 1, Math.floor(value)));
  const columnAt = x => (((x - fit.dx) / fit.scale / Math.PI + 1) / 2) * columns;
  const rowAt = y => (0.5 - (fit.dy - y) / fit.scale / (2 * Math.PI)) * columns;

  const west = clamp(columnAt(0));
  const east = clamp(columnAt(width));
  const north = clamp(rowAt(0));
  const south = clamp(rowAt(height));
  if ((east - west + 1) * (south - north + 1) > maxTiles) return null;

  const tiles = [];
  for (let x = west; x <= east; x += 1) {
    for (let y = north; y <= south; y += 1) {
      tiles.push({
        key: `${zoom}/${x}/${y}`,
        z: zoom, x, y,
        // North-west corner of the tile, in the frame the routes are drawn in.
        left: ((2 * x) / columns - 1) * Math.PI * fit.scale + fit.dx,
        top: fit.dy - Math.PI * (1 - (2 * y) / columns) * fit.scale,
        size
      });
    }
  }
  return { zoom, size, tiles };
}

/** Where one tile is fetched from. Our own proxy, so no key and no CORS. */
export const tileUrl = (tile, layer = "webatlas") =>
  `/api/tiles/${layer}/${tile.z}/${tile.x}/${tile.y}.png`;
