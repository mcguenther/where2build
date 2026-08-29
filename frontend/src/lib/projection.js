/**
 * WGS84 ⇄ local metres.
 *
 * Every geometry routine works in projected metres, but ALKIS delivers, and
 * MapLibre expects, degrees. Rather than pull in proj4 for a single transform,
 * each plot carries an anchor (its own centroid) and its outline is expressed
 * as metres east/north of that anchor — a local ENU frame.
 *
 * Over a parcel, a few hundred metres at most, the error against a true UTM
 * projection stays well under a centimetre, which is far below the accuracy of
 * the cadastral outline itself.
 */

const EARTH_METRES_PER_DEGREE = 111320;

export const metresPerDegreeLon = lat => EARTH_METRES_PER_DEGREE * Math.cos((lat * Math.PI) / 180);

/** `[lon, lat]` pairs → `{x, y}` metres relative to `anchor`. */
export function toLocal(coordinates, anchor) {
  const scaleX = metresPerDegreeLon(anchor.lat);
  return coordinates.map(([lon, lat]) => ({
    x: (lon - anchor.lon) * scaleX,
    y: (lat - anchor.lat) * EARTH_METRES_PER_DEGREE
  }));
}

/** `{x, y}` metres relative to `anchor` → `[lon, lat]` pairs. */
export function toWgs84(ring, anchor) {
  const scaleX = metresPerDegreeLon(anchor.lat);
  return ring.map(p => [anchor.lon + p.x / scaleX, anchor.lat + p.y / EARTH_METRES_PER_DEGREE]);
}

/** Mean of the coordinates, good enough as an anchor for a parcel. */
export function anchorOf(coordinates) {
  const n = coordinates.length;
  return {
    lon: coordinates.reduce((s, c) => s + c[0], 0) / n,
    lat: coordinates.reduce((s, c) => s + c[1], 0) / n
  };
}

/**
 * Web Mercator resolution at a latitude, in metres per screen pixel.
 *
 * The constant is the equatorial circumference divided by MapLibre's tile size
 * of **512** pixels. The number usually quoted, 156543.034, assumes 256-pixel
 * tiles and puts the basemap at exactly twice the scale of the drawing — a
 * mismatch that looks plausible until you measure it.
 */
const METRES_PER_PIXEL_Z0 = 40075016.685578488 / 512;

export const resolutionAt = (lat, zoom) =>
  (METRES_PER_PIXEL_Z0 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;

/** The inverse: which zoom shows `metresPerPixel` at this latitude. */
export const zoomFor = (lat, metresPerPixel) =>
  Math.log2((METRES_PER_PIXEL_Z0 * Math.cos((lat * Math.PI) / 180)) / metresPerPixel);

/**
 * Camera for a basemap sitting under the drawing.
 *
 * The plan renders at a fixed framing, so the map is a backdrop rather than
 * something to pan: give it the same centre, the same metres-per-pixel and the
 * matching rotation, and the two agree pixel for pixel.
 *
 * `rotation` is how far the drawing is turned clockwise on screen. The compass
 * direction that ends up at the top is the negative of that, which is what
 * MapLibre calls the bearing.
 */
export function cameraFor({ anchor, centreMetres, metresPerPixel, rotation = 0 }) {
  const scaleX = metresPerDegreeLon(anchor.lat);
  return {
    center: [anchor.lon + centreMetres.x / scaleX, anchor.lat + centreMetres.y / EARTH_METRES_PER_DEGREE],
    zoom: zoomFor(anchor.lat, metresPerPixel),
    bearing: -rotation
  };
}

/**
 * Where a coordinate lands on screen under that camera — the same maths
 * MapLibre applies internally. Used to prove the overlay and the basemap agree.
 */
export function projectWithCamera([lon, lat], camera, container) {
  const worldSize = 512 * 2 ** camera.zoom;
  const toWorld = ([lo, la]) => {
    const rad = (la * Math.PI) / 180;
    return {
      x: (worldSize * (lo + 180)) / 360,
      y: (worldSize * (0.5 - Math.log(Math.tan(Math.PI / 4 + rad / 2)) / (2 * Math.PI)))
    };
  };
  const p = toWorld([lon, lat]);
  const c = toWorld(camera.center);
  const r = (-camera.bearing * Math.PI) / 180;   // bearing turns the map the other way
  const dx = p.x - c.x, dy = p.y - c.y;
  return {
    x: container.width / 2 + dx * Math.cos(r) - dy * Math.sin(r),
    y: container.height / 2 + dx * Math.sin(r) + dy * Math.cos(r)
  };
}
