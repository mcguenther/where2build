/**
 * Planar geometry for parcels and building footprints.
 *
 * Everything here works in projected metres (EPSG:25833), never in degrees.
 * Turf computes on WGS84 with approximations that are visibly wrong at parcel
 * scale, so the rule for the whole project is: compute in 25833, transform only
 * to display. Points are `{x, y}` with y pointing north.
 *
 * Polygons are closed implicitly — the last vertex connects back to the first,
 * and no duplicate closing vertex is expected.
 */

/** Signed twice-area. Positive when the ring winds counter-clockwise. */
function shoelace(ring) {
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const b = ring[(i + 1) % ring.length];
    sum += ring[i].x * b.y - b.x * ring[i].y;
  }
  return sum;
}

export const polygonArea = ring => Math.abs(shoelace(ring)) / 2;
export const isCounterClockwise = ring => shoelace(ring) > 0;

/** Force counter-clockwise winding; the half-plane maths below depends on it. */
export const asCounterClockwise = ring => (isCounterClockwise(ring) ? ring : [...ring].reverse());

export function polygonEdges(ring) {
  return ring.map((a, i) => {
    const b = ring[(i + 1) % ring.length];
    const dx = b.x - a.x, dy = b.y - a.y;
    const length = Math.hypot(dx, dy);
    return { a, b, dx, dy, length, angle: Math.atan2(dy, dx) };
  });
}

export const polygonPerimeter = ring => polygonEdges(ring).reduce((s, e) => s + e.length, 0);

/** Vertex average, not the centre of mass — good enough for framing a view. */
export const polygonCentroid = ring =>
  ring.reduce((s, p) => ({ x: s.x + p.x / ring.length, y: s.y + p.y / ring.length }), { x: 0, y: 0 });

export const translatePolygon = (ring, dx, dy) => ring.map(p => ({ x: p.x + dx, y: p.y + dy }));

export function boundingBox(ring) {
  const xs = ring.map(p => p.x), ys = ring.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  return { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY };
}

/** Sutherland–Hodgman clip against `dot(normal, p - point) >= 0`. */
export function clipToHalfPlane(ring, point, normal) {
  const side = p => (p.x - point.x) * normal.x + (p.y - point.y) * normal.y;
  const out = [];
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    const da = side(a), db = side(b);
    if (da >= -1e-9) out.push(a);
    if ((da >= -1e-9) !== (db >= -1e-9)) {
      const t = da / (da - db);
      out.push({ x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) });
    }
  }
  return out;
}

/**
 * The envelope a building may occupy: the parcel inset by a setback depth that
 * is given **per boundary segment**. § 6 SächsBO measures the depth from wall
 * height and treats 3 m as a floor rather than a rule, so a single global inset
 * would be wrong for most plots.
 *
 * Returns `[]` when the setbacks consume the parcel entirely.
 */
export function buildableArea(ring, depths) {
  const poly = asCounterClockwise(ring);
  const offsets = Array.isArray(depths) ? depths : poly.map(() => depths);
  let envelope = poly;
  polygonEdges(poly).forEach((edge, i) => {
    if (envelope.length < 3) return;
    // Inward normal of a counter-clockwise ring.
    const normal = { x: -edge.dy / edge.length, y: edge.dx / edge.length };
    const depth = Number.isFinite(offsets[i]) ? offsets[i] : 3;
    envelope = clipToHalfPlane(
      envelope,
      { x: edge.a.x + normal.x * depth, y: edge.a.y + normal.y * depth },
      normal
    );
  });
  return envelope.length >= 3 ? envelope : [];
}

/**
 * Smallest enclosing rectangle over all rotations. For a convex ring the
 * optimum always aligns with one of its edges, so testing the edges suffices.
 */
export function minimumRotatedRectangle(ring) {
  let best = null;
  for (const edge of polygonEdges(ring)) {
    const c = Math.cos(-edge.angle), s = Math.sin(-edge.angle);
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const p of ring) {
      const x = p.x * c - p.y * s, y = p.x * s + p.y * c;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    const width = maxX - minX, height = maxY - minY, area = width * height;
    if (!best || area < best.area) best = { area, width, height, angle: edge.angle };
  }
  return best;
}

/** Polygon area over the area of its minimum rotated rectangle: 1 is a rectangle. */
export const rectangularity = ring => polygonArea(ring) / minimumRotatedRectangle(ring).area;

/** Thresholds from the pre-project note. */
export function shapeClass(value) {
  if (value > 0.95) return "rechteckig";
  if (value >= 0.85) return "fast rechteckig";
  return "komplex";
}

export function pointInPolygon(point, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const yi = ring[i].y, yj = ring[j].y;
    if ((yi > point.y) !== (yj > point.y) &&
        point.x < ((ring[j].x - ring[i].x) * (point.y - yi)) / (yj - yi) + ring[i].x) {
      inside = !inside;
    }
  }
  return inside;
}

export function closestPointOnSegment(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, lengthSq = dx * dx + dy * dy;
  const t = lengthSq ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSq)) : 0;
  return { x: a.x + t * dx, y: a.y + t * dy };
}

export function distanceToSegment(p, a, b) {
  const q = closestPointOnSegment(p, a, b);
  return Math.hypot(p.x - q.x, p.y - q.y);
}

export const distanceToBoundary = (p, ring) =>
  Math.min(...polygonEdges(ring).map(e => distanceToSegment(p, e.a, e.b)));

/** Nearest point on the ring plus its distance — used to draw the tightest gap. */
export function closestBoundaryPoint(p, ring) {
  let best = { distance: Infinity, point: null };
  for (const edge of polygonEdges(ring)) {
    const q = closestPointOnSegment(p, edge.a, edge.b);
    const d = Math.hypot(p.x - q.x, p.y - q.y);
    if (d < best.distance) best = { distance: d, point: q };
  }
  return best;
}

/**
 * Corners of a placed footprint, counter-clockwise.
 * `placement` is `{cx, cy, width, depth, rotation}` with rotation in degrees.
 */
export function rectangleCorners({ cx, cy, width, depth, rotation }) {
  const r = (rotation * Math.PI) / 180;
  const c = Math.cos(r), s = Math.sin(r);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => {
    const x = (sx * width) / 2, y = (sy * depth) / 2;
    return { x: cx + x * c - y * s, y: cy + x * s + y * c };
  });
}

/** How many corners of the footprint fall outside the envelope. */
export function cornersOutside(placement, envelope) {
  if (!envelope.length) return 4;
  return rectangleCorners(placement).filter(p => !pointInPolygon(p, envelope)).length;
}

/** Smallest distance from any footprint corner to the parcel boundary. */
export const smallestSetback = (placement, ring) =>
  Math.min(...rectangleCorners(placement).map(p => distanceToBoundary(p, ring)));

/** Derive footprint edges from a built area when the data sheet gives no dimensions. */
export function footprintFromArea(builtArea, ratio) {
  const width = Math.sqrt(builtArea * ratio);
  return { width, depth: builtArea / width };
}

/**
 * Search for a placement of a `width × depth` footprint inside `envelope`.
 *
 * `rotation` pins the angle (used after aligning to the street); leaving it
 * undefined sweeps every angle. `near` biases the result towards a preferred
 * centre so an existing house does not jump across the plot. Returns `null`
 * when nothing fits.
 */
export function findPlacement(envelope, width, depth, options = {}) {
  if (!envelope.length) return null;
  const { rotation, near, step = 0.5, angleStep = 5 } = options;
  const box = boundingBox(envelope);
  const angles = Number.isFinite(rotation)
    ? [rotation]
    : Array.from({ length: Math.ceil(180 / angleStep) }, (_, i) => i * angleStep);

  let best = null;
  for (const angle of angles) {
    for (let cx = box.minX; cx <= box.maxX; cx += step) {
      for (let cy = box.minY; cy <= box.maxY; cy += step) {
        const placement = { cx, cy, width, depth, rotation: angle };
        if (cornersOutside(placement, envelope)) continue;
        if (!near) return placement;
        const cost = Math.hypot(cx - near.x, cy - near.y);
        if (!best || cost < best.cost) best = { cost, placement };
      }
    }
  }
  return best ? best.placement : null;
}

/** Does this footprint fit anywhere at all? Cheaper to read than findPlacement. */
export const fitsAnywhere = (envelope, width, depth) => findPlacement(envelope, width, depth) !== null;

/**
 * Rotation in degrees that lays the footprint's long side parallel to a parcel
 * edge — normally the street front, which is what people actually build to.
 * Normalised to (-90, 90] so the slider stays in range.
 */
export function alignmentToEdge(ring, edgeIndex = 0) {
  const edge = polygonEdges(ring)[edgeIndex];
  let degrees = (edge.angle * 180) / Math.PI;
  while (degrees > 90) degrees -= 180;
  while (degrees <= -90) degrees += 180;
  return degrees;
}

/**
 * Align to an edge and, if the rotated footprint no longer fits, slide it back
 * inside without changing the angle. Returns the new placement, or the rotated
 * placement unchanged when nothing valid exists.
 */
export function alignToEdge(ring, envelope, placement, edgeIndex = 0) {
  const rotation = alignmentToEdge(ring, edgeIndex);
  const rotated = { ...placement, rotation };
  if (!cornersOutside(rotated, envelope)) return rotated;
  const reseated = findPlacement(envelope, placement.width, placement.depth, {
    rotation,
    near: { x: placement.cx, y: placement.cy },
    step: 0.25
  });
  return reseated ?? rotated;
}

const COMPASS = ["Nord", "Nordost", "Ost", "Südost", "Süd", "Südwest", "West", "Nordwest"];

/**
 * Compass name of the outward side of an edge. `northOffset` is how far true
 * north is rotated against the drawing, so boundaries read "Ost — Nachbar"
 * rather than "Grenze 2".
 */
export function edgeCompass(ring, edgeIndex, northOffset = 0) {
  const edge = polygonEdges(asCounterClockwise(ring))[edgeIndex];
  const outward = (Math.atan2(-edge.dx, edge.dy) * 180) / Math.PI;
  const azimuth = (((90 + northOffset - outward) % 360) + 360) % 360;
  return COMPASS[Math.round(azimuth / 45) % 8];
}

/**
 * Pixels per metre that fit `ring` into a frame, with a margin in pixels and a
 * relative padding around the outline. Exported so several plans can agree on
 * one scale — a comparison drawn at four different scales is a lie.
 */
export function fitScale(ring, frameWidth, frameHeight, margin = 40, padding = 0.16) {
  const box = boundingBox(ring);
  const width = box.width * (1 + padding * 2);
  const height = box.height * (1 + padding * 2);
  return Math.min((frameWidth - margin * 2) / width, (frameHeight - margin * 2) / height);
}
