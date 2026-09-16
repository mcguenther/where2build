/**
 * Drawing a distance band — the ring an „ca. 6 km bis Grimma" admits.
 *
 * The backend resolves the named reference to the town's built-up outline and
 * sends that outline, its middle, and the interval the sentence allows. What a
 * candidate has to satisfy is two conditions, and this module turns exactly
 * those two into a shape:
 *
 *   dist(x, Ortslage) ≤ außen   →  inside the outline offset outwards by außen
 *   dist(x, Mitte)    ≥ innen   →  outside the circle of radius innen
 *
 * So the band is an annulus with a town-shaped outer edge, and both of its
 * borders are drawn dashed: the band orders candidates and may object, it never
 * confirms, and a dashed border is what says so without a caption.
 *
 * The outer edge is offset from the outline's **convex hull**. A 6 km offset
 * swallows every notch a settlement boundary has — measured on Grimma, the
 * hull differs from the outline by under 300 m at its worst, against a band
 * 2,9 km wide — and the hull makes the offset an exact Minkowski sum rather
 * than an approximation that can self-intersect.
 */
import { anchorOf, toLocal, toWgs84 } from "./projection.js";

// Points per full turn on an arc. At 7,5 km a full circle of 96 points has
// 490 m between vertices and a sagitta of 4 m — invisible at any zoom that
// shows the whole band, and cheap enough to redraw while the search runs.
const ARC_STEPS = 96;

/** Every `[lon, lat]` pair in a GeoJSON geometry, however it is nested. */
export function coordinatesOf(geometry) {
  const out = [];
  const walk = node => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") return void out.push(node);
    node.forEach(walk);
  };
  walk(geometry?.coordinates);
  return out;
}

/** Andrew's monotone chain, counter-clockwise, without the repeated endpoint. */
export function convexHull(points) {
  if (points.length < 3) return [...points];
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const half = list => {
    const chain = [];
    for (const point of list) {
      while (chain.length >= 2 && cross(chain[chain.length - 2], chain[chain.length - 1], point) <= 0) {
        chain.pop();
      }
      chain.push(point);
    }
    chain.pop();
    return chain;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}

/**
 * A convex ring pushed outwards by `radius` — its Minkowski sum with a disc.
 *
 * Each edge moves out along its own normal and the vertices become arcs, which
 * is what keeps the corners round instead of spiking off to a mitre.
 */
export function offsetConvex(hull, radius) {
  const n = hull.length;
  if (!n) return [];
  if (n < 3) return circle(hull[0] ?? { x: 0, y: 0 }, radius);

  const normals = hull.map((point, index) => {
    const next = hull[(index + 1) % n];
    const dx = next.x - point.x;
    const dy = next.y - point.y;
    const length = Math.hypot(dx, dy) || 1;
    // Counter-clockwise, so the interior lies to the left and out is to the right.
    return { x: dy / length, y: -dx / length };
  });

  const out = [];
  for (let index = 0; index < n; index += 1) {
    const before = normals[(index - 1 + n) % n];
    const after = normals[index];
    const from = Math.atan2(before.y, before.x);
    let to = Math.atan2(after.y, after.x);
    while (to < from) to += 2 * Math.PI;
    const steps = Math.max(1, Math.ceil(((to - from) / (2 * Math.PI)) * ARC_STEPS));
    for (let step = 0; step <= steps; step += 1) {
      const angle = from + ((to - from) * step) / steps;
      out.push({
        x: hull[index].x + radius * Math.cos(angle),
        y: hull[index].y + radius * Math.sin(angle)
      });
    }
  }
  return out;
}

/** A circle as a ring of points, counter-clockwise. */
export function circle(centre, radius, steps = ARC_STEPS) {
  const out = [];
  for (let step = 0; step < steps; step += 1) {
    const angle = (2 * Math.PI * step) / steps;
    out.push({ x: centre.x + radius * Math.cos(angle), y: centre.y + radius * Math.sin(angle) });
  }
  return out;
}

const closed = ring => (ring.length ? [...ring, ring[0]] : ring);

/**
 * One distance band as a GeoJSON polygon with a hole.
 *
 * The hole is the point: a candidate nearer the middle than `innen_m` fails the
 * statement just as surely as one beyond `aussen_m`, and a filled disc would
 * say the opposite. Returns `null` for a band whose reference could not be
 * resolved — there is nothing to draw around a „Bushaltestelle".
 */
export function bandPolygon(band) {
  if (!band || !band.aufgeloest || !band.umriss || !band.mitte) return null;
  const points = coordinatesOf(band.umriss);
  const middle = coordinatesOf(band.mitte)[0];
  if (!points.length || !middle) return null;

  const anchor = anchorOf([middle]);
  const hull = convexHull(toLocal(points, anchor));
  const outer = offsetConvex(hull, band.aussen_m);
  const inner = circle({ x: 0, y: 0 }, band.innen_m);
  if (!outer.length) return null;

  return {
    type: "Polygon",
    coordinates: [
      closed(toWgs84(outer, anchor)),
      // Clockwise, as a hole is written.
      closed(toWgs84([...inner].reverse(), anchor))
    ]
  };
}

/** The bands of a list of Indizien, in the shape the map's source wants. */
export function bandFeatures(indicia) {
  return (indicia || [])
    .filter(indiz => indiz?.art === "entfernung" && !indiz.verworfen && indiz.band)
    .map(indiz => ({ indiz, geometry: bandPolygon(indiz.band) }))
    .filter(entry => entry.geometry)
    .map(({ indiz, geometry }) => ({
      type: "Feature",
      properties: { id: indiz.id, bezug: indiz.band.bezug },
      geometry
    }));
}
