/**
 * Neighbouring parcels and buildings for the site plan.
 *
 * Until ALKIS delivers the real surroundings, the context is derived from the
 * parcel itself: copies shifted sideways along the street front plus one at the
 * rear, each nudged by a seeded jitter so a row does not look stamped. A plan
 * without context reads as a floating shape and gives no sense of scale.
 *
 * Replace `neighbourhood()` with the ALKIS response once the backend serves it;
 * the shape of the return value is what the plan component consumes.
 */
import { polygonEdges, polygonCentroid, translatePolygon, asCounterClockwise } from "./geometry.js";

/** Deterministic pseudo-random in [-0.5, 0.5), so a plan never jitters between renders. */
function seeded(seed) {
  let state = Math.abs(Math.round(seed)) % 233280 || 1;
  return () => {
    state = (state * 9301 + 49297) % 233280;
    return state / 233280 - 0.5;
  };
}

export function neighbourhood(ring, seed = 1, frontIndex = 0) {
  const poly = asCounterClockwise(ring);
  const random = seeded(seed);
  const front = polygonEdges(poly)[frontIndex];
  const along = { x: front.dx / front.length, y: front.dy / front.length };
  const inward = { x: -along.y, y: along.x };
  const depth = Math.max(...poly.map(p => (p.x - front.a.x) * inward.x + (p.y - front.a.y) * inward.y));
  const frontAngle = (Math.atan2(along.y, along.x) * 180) / Math.PI;

  const parcels = [];
  const buildings = [];

  const place = (across, back) => {
    const jitterX = random() * 1.4, jitterY = random() * 1.4;
    const dx = along.x * across + inward.x * back + jitterX;
    const dy = along.y * across + inward.y * back + jitterY;
    const shape = translatePolygon(poly, dx, dy);
    parcels.push(shape);
    const middle = polygonCentroid(shape);
    const setBack = depth * (0.2 + random() * 0.12);
    buildings.push({
      cx: middle.x - inward.x * (depth / 2 - setBack),
      cy: middle.y - inward.y * (depth / 2 - setBack),
      width: front.length * (0.46 + random() * 0.14),
      depth: depth * (0.22 + random() * 0.08),
      rotation: frontAngle + random() * 6
    });
  };

  place(-front.length * 1.06, 0);
  place(-front.length * 2.12, 0);
  place(front.length * 1.06, 0);
  place(front.length * 2.12, 0);
  place(front.length * 0.1, depth * 1.06);

  // The carriageway runs along the front edge, offset outwards.
  const street = [
    { x: front.a.x - along.x * 70 - inward.x * 0.8, y: front.a.y - along.y * 70 - inward.y * 0.8 },
    { x: front.b.x + along.x * 70 - inward.x * 0.8, y: front.b.y + along.y * 70 - inward.y * 0.8 },
    { x: front.b.x + along.x * 70 - inward.x * 8.5, y: front.b.y + along.y * 70 - inward.y * 8.5 },
    { x: front.a.x - along.x * 70 - inward.x * 8.5, y: front.a.y - along.y * 70 - inward.y * 8.5 }
  ];

  return { parcels, buildings, street, front, along, inward, depth };
}
