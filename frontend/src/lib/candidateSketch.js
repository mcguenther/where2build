/**
 * The small picture on each candidate's card: the parcel on the orthophoto,
 * with the cadastre's own lines and a little of the neighbourhood around it.
 *
 * Its job is recognition — a listing's photographs show a roof, a hedge, a
 * shed, and those are found faster on four small pictures than by flying one
 * big map from candidate to candidate. So it is a picture, not a map: nothing
 * zooms, nothing pans, and it is drawn the way the route cards draw theirs —
 * proxied raster tiles as <image> in an SVG. A MapLibre instance per card
 * would hit the browser's WebGL context limit at a dozen candidates, and the
 * contexts past it go blank without a word.
 */
import { fitBounds, routeBounds, tileCover, tileUrl, toScreen } from "./routes.js";
import { PARCEL_OUTLINE_MIN_ZOOM } from "./basemap.js";

/** The drawing, in SVG user units. About the size it renders at on a card, so
 *  the zoom `tileCover` picks from it is the one that looks sharp there. */
export const SKETCH_WIDTH = 320;
export const SKETCH_HEIGHT = 200;

/** How much ground the picture shows at the least, as a half-width: a plot and
 *  a neighbour either side, which is what makes a photograph comparable. */
export const MIN_HALF_WIDTH_M = 60;

const EARTH_RADIUS_M = 6378137;
const RADIANS_PER_DEGREE = Math.PI / 180;

/** Every ring of a Polygon or MultiPolygon, as coordinate lists. */
function ringsOf(geometry) {
  if (geometry?.type === "Polygon") return geometry.coordinates;
  if (geometry?.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

/**
 * Grow a Mercator box so it covers at least `halfWidthM` either side of its
 * centre, and takes the frame's proportions — a box of the parcel's own shape
 * letterboxed into the card would leave paper where the context should be.
 */
function contextBounds(bounds, halfWidthM, aspect) {
  const latitude = ((bounds.minLat + bounds.maxLat) / 2) * RADIANS_PER_DEGREE;
  // One metre of ground in unscaled Mercator, at this latitude.
  const perMetre = 1 / (EARTH_RADIUS_M * Math.cos(latitude));
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  // The parcel itself gets a margin too: a contour on the frame's edge is a
  // contour whose neighbours cannot be seen.
  let half = Math.max((bounds.maxX - bounds.minX) * 0.7, halfWidthM * perMetre);
  let halfY = Math.max((bounds.maxY - bounds.minY) * 0.7, half / aspect);
  half = Math.max(half, halfY * aspect);
  halfY = half / aspect;
  return { ...bounds, minX: cx - half, maxX: cx + half, minY: cy - halfY, maxY: cy + halfY };
}

/**
 * Everything a card needs to draw its candidate, or `null` without a geometry.
 *
 * The cadastre is laid over the photo only from the zoom the search map draws
 * it at: further out it is a mesh, and on a picture this small a mesh is all
 * there would be.
 */
export function candidateSketch(geometry, { width = SKETCH_WIDTH, height = SKETCH_HEIGHT } = {}) {
  const rings = ringsOf(geometry).filter(ring => ring.length >= 3);
  if (!rings.length) return null;
  const bounds = routeBounds(rings);
  if (!bounds) return null;
  const framed = contextBounds(bounds, MIN_HALF_WIDTH_M, width / height);
  const fit = fitBounds(framed, width, height, 0);
  if (!fit) return null;

  const cover = tileCover(fit, width, height);
  const tiles = cover ? cover.tiles : [];
  const cadastre = cover && cover.zoom >= PARCEL_OUTLINE_MIN_ZOOM;
  const path = rings
    .map(ring => ring
      .map((coordinate, i) => {
        const p = toScreen(coordinate, fit);
        return `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
      })
      .join(" ") + " Z")
    .join(" ");
  const groundWidthM = (width / fit.scale) * EARTH_RADIUS_M
    * Math.cos(((bounds.minLat + bounds.maxLat) / 2) * RADIANS_PER_DEGREE);

  return {
    viewBox: `0 0 ${width} ${height}`,
    width,
    height,
    photo: tiles.map(tile => ({ ...tile, href: tileUrl(tile, "dop") })),
    cadastre: cadastre ? tiles.map(tile => ({ ...tile, href: tileUrl(tile, "liegenschaftskarte") })) : [],
    path,
    groundWidthM
  };
}

/** The caption under the picture. An honest scale beats none: a field and a
 *  garden plot look alike at this size. */
export function sketchCaption(groundWidthM) {
  if (!(groundWidthM > 0)) return "";
  return groundWidthM >= 1000
    ? `Bildbreite rund ${(Math.round(groundWidthM / 100) / 10).toLocaleString("de-DE")} km`
    : `Bildbreite rund ${Math.max(10, Math.round(groundWidthM / 10) * 10)} m`;
}
