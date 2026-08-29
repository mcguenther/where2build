/**
 * Route geometry for the destination cards.
 *
 * MOTIS answers with a real GeoJSON LineString per origin/destination/mode.
 * These helpers fit that line into the small SVG of a route card. Nothing here
 * invents a course: a card without geometry stays empty and says so.
 */

/** Modes in the order the cards list them, with their German labels. */
export const MODES = [
  { mode: "car", name: "Auto" },
  { mode: "bike", name: "Rad" },
  { mode: "transit", name: "ÖPNV" }
];

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
