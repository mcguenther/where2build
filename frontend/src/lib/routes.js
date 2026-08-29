/**
 * Route geometry for the destination cards.
 *
 * MOTIS answers with a real GeoJSON LineString per origin/destination/mode.
 * These helpers fit that line into the small SVG of a route card. Nothing here
 * invents a course: a card without geometry stays empty and says so.
 */

/** Modes in the order the cards list them, with their German labels. */
export const MODI = [
  { art: "car", name: "Auto" },
  { art: "bike", name: "Rad" },
  { art: "transit", name: "ÖPNV" }
];

const RAD = Math.PI / 180;

/**
 * Web Mercator, unscaled. Only ratios matter here, so the earth radius drops
 * out — but the latitude stretch does not, and dropping it would tilt every
 * route that runs north.
 */
function mercator([lon, lat]) {
  const phi = Math.max(-85.05, Math.min(85.05, lat)) * RAD;
  return { x: lon * RAD, y: Math.log(Math.tan(Math.PI / 4 + phi / 2)) };
}

/**
 * Bounding box over several lines at once, so all modes share one frame.
 * Carries the geographic extent alongside the projected one — the card needs
 * the first to draw and the second to label a scale.
 */
export function routeBounds(lines) {
  const koordinaten = lines.filter(Boolean).flat();
  if (!koordinaten.length) return null;
  const punkte = koordinaten.map(mercator);
  const lons = koordinaten.map(c => c[0]);
  const lats = koordinaten.map(c => c[1]);
  const xs = punkte.map(p => p.x);
  const ys = punkte.map(p => p.y);
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
  const mittlereBreite = ((bounds.minLat + bounds.maxLat) / 2) * RAD;
  return (bounds.maxLon - bounds.minLon) * RAD * 6378137 * Math.cos(mittlereBreite);
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
    const zusammen = geometry.coordinates.flat();
    return zusammen.length >= 2 ? zusammen : null;
  }
  return null;
}

/** The fastest mode that was actually reached — it decides a card's colour. */
export function fastestMode(weg) {
  if (!weg || !weg.modi) return null;
  const erreichbar = MODI
    .map(m => ({ art: m.art, ...(weg.modi[m.art] || {}) }))
    .filter(m => m.erreichbar && Number.isFinite(m.duration_s));
  if (!erreichbar.length) return null;
  return erreichbar.reduce((a, b) => (b.duration_s < a.duration_s ? b : a)).art;
}
