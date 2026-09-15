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

/** Douglas–Peucker. The marching-squares contour has a vertex per cell edge;
 *  this brings it down to something a renderer and a person can handle. */
export function simplify(ring, tolerance) {
  if (ring.length < 3) return ring;
  const offset = (p, a, b) => {
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy);
    if (len < 1e-12) return Math.hypot(p.x - a.x, p.y - a.y);
    return Math.abs((p.x - a.x) * dy - (p.y - a.y) * dx) / len;
  };
  const split = (from, to, keep) => {
    let worst = 0, index = -1;
    for (let i = from + 1; i < to; i++) {
      const d = offset(ring[i], ring[from], ring[to]);
      if (d > worst) { worst = d; index = i; }
    }
    if (worst > tolerance) { split(from, index, keep); keep.add(index); split(index, to, keep); }
  };
  const keep = new Set([0, ring.length - 1]);
  split(0, ring.length - 1, keep);
  return [...keep].sort((a, b) => a - b).map(i => ring[i]);
}

/** True when every turn goes the same way. Half-plane clipping is only a
 *  correct inward offset for convex rings. */
export function isConvex(ring) {
  if (ring.length < 4) return true;
  let sign = 0;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length], c = ring[(i + 2) % ring.length];
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cross) < 1e-9) continue;
    const s = Math.sign(cross);
    if (!sign) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

/** Clearance at a point: how much room is left beyond the required setback,
 *  negative outside the parcel or inside any setback strip. */
function clearance(point, ring, edges, depths) {
  if (!pointInPolygon(point, ring)) return -1;
  let worst = Infinity;
  for (let i = 0; i < edges.length; i++) {
    const slack = distanceToSegment(point, edges[i].a, edges[i].b) - (depths[i] ?? 3);
    if (slack < worst) worst = slack;
  }
  return worst;
}

/**
 * Marching squares over the clearance field. Used for concave parcels, where
 * clipping half-planes would cut away far too much — an L-shaped plot comes out
 * empty. Accuracy follows the grid step, which is well inside what the
 * pre-project note asks of this drawing: the binding numbers come from ALKIS.
 */
/* The clearance field costs one point-to-edge distance per cell per boundary
 * segment, so the work grows with area times vertex count. A real cadastral
 * parcel can be a 1583 x 198 m strip with 159 boundary points: at 0.4 m that is
 * two million cells and 314 million distance computations, which locks the tab
 * up long enough for the browser to offer to stop the script.
 *
 * Cap the cell count and let the step grow instead. Coarsening stays safe by
 * construction: the inward bias is derived from the step, so a coarser grid
 * yields a smaller envelope, never a more permissive one. A plot of ordinary
 * size stays at the requested resolution — the cap only bites on land nobody
 * plans a house on to the decimetre. */
const MAX_GRID_CELLS = 120_000;

function gridStep(box, wanted) {
  const cells = (box.width / wanted) * (box.height / wanted);
  return cells <= MAX_GRID_CELLS ? wanted : wanted * Math.sqrt(cells / MAX_GRID_CELLS);
}

function insetByGrid(ring, depths, step, safety) {
  const box = boundingBox(ring);
  const edges = polygonEdges(ring);
  const cols = Math.ceil(box.width / step) + 3;
  const rows = Math.ceil(box.height / step) + 3;
  const x0 = box.minX - step, y0 = box.minY - step;
  const at = (i, j) => ({ x: x0 + i * step, y: y0 + j * step });

  const field = new Float64Array(cols * rows);
  for (let j = 0; j < rows; j++)
    for (let i = 0; i < cols; i++) field[j * cols + i] = clearance(at(i, j), ring, edges, depths) - safety;

  // One segment per cell crossing, then chained into a ring.
  const segments = [];
  const between = (pa, pb, va, vb) => {
    const t = va / (va - vb);
    return { x: pa.x + t * (pb.x - pa.x), y: pa.y + t * (pb.y - pa.y) };
  };
  for (let j = 0; j < rows - 1; j++) {
    for (let i = 0; i < cols - 1; i++) {
      const v = [field[j * cols + i], field[j * cols + i + 1],
                 field[(j + 1) * cols + i + 1], field[(j + 1) * cols + i]];
      const p = [at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)];
      const crossings = [];
      for (let k = 0; k < 4; k++) {
        const a = k, b = (k + 1) % 4;
        if ((v[a] > 0) !== (v[b] > 0)) crossings.push(between(p[a], p[b], v[a], v[b]));
      }
      if (crossings.length === 2) segments.push(crossings);
    }
  }
  if (!segments.length) return [];

  // Chain segments end to end; keep the longest closed ring.
  const key = q => `${Math.round(q.x / (step / 8))},${Math.round(q.y / (step / 8))}`;
  const openEnds = new Map();
  segments.forEach((segment, idx) => {
    for (const end of [0, 1]) {
      const k = key(segment[end]);
      if (!openEnds.has(k)) openEnds.set(k, []);
      openEnds.get(k).push({ idx, end });
    }
  });
  const used = new Set();
  let best = [];
  for (let start = 0; start < segments.length; start++) {
    if (used.has(start)) continue;
    const chain = [segments[start][0], segments[start][1]];
    used.add(start);
    for (let hop = 0; hop < segments.length; hop++) {
      const k = key(chain[chain.length - 1]);
      const next = (openEnds.get(k) || []).find(e => !used.has(e.idx));
      if (!next) break;
      used.add(next.idx);
      chain.push(segments[next.idx][1 - next.end]);
    }
    if (chain.length > best.length) best = chain;
  }
  const simplified = simplify(best, step * 0.6);
  return simplified.length >= 3 ? simplified : [];
}

/**
 * The envelope a building may occupy: the parcel inset by a setback depth that
 * is given **per boundary segment**. § 6 SächsBO measures the depth from wall
 * height and treats 3 m as a floor rather than a rule, so a single global inset
 * would be wrong for most plots.
 *
 * Convex parcels take the exact half-plane route; concave ones — L-shapes and
 * flag lots, both common in a real cadastre — go through the grid, because
 * clipping half-planes there would cut away most of the plot.
 *
 * Returns `[]` when the setbacks consume the parcel entirely.
 */
/* The envelope is asked for by the plan, the key figures, the comparison and the
 * house-type fit check, all for the same plot. On a concave parcel each answer
 * costs a grid sweep, so the last few are kept. */
const envelopeCache = new Map();
const CACHE_LIMIT = 64;

function cacheKey(ring, depths, options) {
  const p = ring.map(v => `${v.x.toFixed(2)},${v.y.toFixed(2)}`).join(";");
  const d = Array.isArray(depths) ? depths.join(",") : String(depths);
  return `${p}|${d}|${options.step ?? ""}|${options.safety ?? ""}`;
}

/**
 * A plain copy of a ring.
 *
 * Vue hands components their props as reactive proxies, and a proxy charges a
 * trap for every single property read. The clearance field reads two numbers
 * per cell per boundary segment — hundreds of millions of reads on a real
 * parcel — and measured 23.5x slower through a proxy than on plain objects:
 * 26 seconds instead of one. That is what froze the tab.
 *
 * One O(n) copy at the door buys it all back, and keeps the geometry module
 * free of any dependency on the framework that happens to own the data.
 */
function plainRing(ring) {
  const out = new Array(ring.length);
  for (let i = 0; i < ring.length; i++) {
    const v = ring[i];
    out[i] = Array.isArray(v) ? { x: v[0], y: v[1] } : { x: v.x, y: v.y };
  }
  return out;
}

/** The same, for the per-segment setback depths. */
function plainDepths(depths, length) {
  if (!Array.isArray(depths)) return Number(depths);
  /* One depth per boundary segment. A short array would silently leave the
     remaining segments at NaN, and a NaN clearance makes the whole envelope
     vanish, so the statutory 3 m fills any gap. */
  const out = new Array(length);
  for (let i = 0; i < length; i++) {
    const value = Number(depths[i]);
    out[i] = Number.isFinite(value) ? value : 3;
  }
  return out;
}

export function buildableArea(ring, depths, options = {}) {
  const key = cacheKey(ring, depths, options);
  const cached = envelopeCache.get(key);
  if (cached) return cached;
  const envelope = computeBuildableArea(
    plainRing(ring), plainDepths(depths, ring.length), options
  );
  if (envelopeCache.size >= CACHE_LIMIT) envelopeCache.delete(envelopeCache.keys().next().value);
  envelopeCache.set(key, envelope);
  return envelope;
}

function computeBuildableArea(ring, depths, options) {
  const poly = asCounterClockwise(ring);
  const offsets = Array.isArray(depths) ? depths : poly.map(() => depths);

  if (!isConvex(poly)) {
    /* The grid and the simplification both carry error. Bias the contour inward
       by the same order of magnitude, so an approximate envelope is always a
       little too strict rather than a little too permissive — being generous
       here would let a house sit closer to the boundary than the law allows. */
    const step = gridStep(boundingBox(poly), options.step ?? 0.4);
    return insetByGrid(poly, offsets, step, options.safety ?? step * 0.55);
  }

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
/* Same reasoning as the envelope cache: the catalogue asks the same question
 * for every render of the same plot. */
const placementCache = new Map();

export function findPlacement(envelope, width, depth, options = {}) {
  if (!envelope.length) return null;
  const key = `${envelope.map(v => `${v.x.toFixed(1)},${v.y.toFixed(1)}`).join(";")}|${width.toFixed(2)}|${depth.toFixed(2)}|${options.rotation ?? ""}|${options.near ? `${options.near.x.toFixed(1)},${options.near.y.toFixed(1)}` : ""}|${options.step ?? ""}`;
  if (placementCache.has(key)) return placementCache.get(key);
  const placement = searchPlacement(plainRing(envelope), width, depth, options);
  if (placementCache.size >= CACHE_LIMIT) placementCache.delete(placementCache.keys().next().value);
  placementCache.set(key, placement);
  return placement;
}

function searchPlacement(envelope, width, depth, options) {
  const { rotation, near, step = 0.75, angleStep = 6 } = options;
  const box = boundingBox(envelope);

  /* Two cheap impossibilities first. Real parcels are large and their envelopes
     carry many vertices, so a full sweep costs millions of point-in-polygon
     tests; most "does it fit" questions are answered without one. */
  if (width * depth > polygonArea(envelope) + 1e-9) return null;
  if (Math.min(width, depth) > Math.min(box.width, box.height) + 1e-9) return null;
  const angles = Number.isFinite(rotation)
    ? [rotation]
    : Array.from({ length: Math.ceil(180 / angleStep) }, (_, i) => i * angleStep);

  let best = null;
  for (const angle of angles) {
    for (let cx = box.minX; cx <= box.maxX; cx += step) {
      for (let cy = box.minY; cy <= box.maxY; cy += step) {
        // The centre of a rectangle inside a polygon is inside it too, and one
        // test costs a quarter of four.
        if (!pointInPolygon({ x: cx, y: cy }, envelope)) continue;
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

/** All four corners inside: the whole validity test for a placed footprint. */
function insideEnvelope(placement, envelope) {
  const corners = rectangleCorners(placement);
  for (let i = 0; i < 4; i++) if (!pointInPolygon(corners[i], envelope)) return false;
  return true;
}

/* Sixteen halvings leave the stop within a ten-thousandth of the requested
 * move — far below a pixel at any scale this plan is drawn at, and a fixed
 * cost so a pointer move never gets slower the further it travels. */
const SLIDE_STEPS = 16;

/**
 * The far end of the longest part of `dx, dy` that keeps the footprint inside.
 * The whole move first, then bisection between the last position known to be
 * legal and the requested one.
 */
function reachAlong(envelope, shape, from, dx, dy) {
  const at = t => ({ ...shape, cx: from.cx + dx * t, cy: from.cy + dy * t });
  if (insideEnvelope(at(1), envelope)) return { cx: from.cx + dx, cy: from.cy + dy };
  let legal = 0, blocked = 1;
  for (let i = 0; i < SLIDE_STEPS; i++) {
    const middle = (legal + blocked) / 2;
    if (insideEnvelope(at(middle), envelope)) legal = middle; else blocked = middle;
  }
  return { cx: from.cx + dx * legal, cy: from.cy + dy * legal };
}

/**
 * Where a footprint dragged from `placement` towards `wanted` is allowed to end
 * up: the position closest to `wanted` that still has all four corners in the
 * envelope. Returns `{cx, cy}`.
 *
 * Three candidates are tried — the whole move, the move in x alone, the move in
 * y alone — each cut back to the part of it that stays legal, and the one that
 * comes nearest to `wanted` wins. That is what makes the footprint slide along
 * a boundary it is pushed into instead of stopping dead against it, and it
 * leaves a drag far past the boundary standing at the boundary rather than
 * snapping back to where it started.
 *
 * The constraint gives itself up wherever there is nothing to enforce: an
 * envelope of fewer than three points, a footprint that fits nowhere at this
 * angle, or one that is already outside. Holding a drag inside a window that
 * does not exist would only mean the house could not be moved at all; the
 * violation markers say what is wrong instead.
 */
export function constrainToEnvelope(envelope, placement, wanted) {
  const target = { cx: wanted.cx, cy: wanted.cy };
  if (!envelope || envelope.length < 3) return target;

  /* Both of these are read a few thousand times below, and a Vue prop charges
     a proxy trap per property read. Copy once at the door — see plainRing. */
  const ring = plainRing(envelope);
  const shape = { width: placement.width, depth: placement.depth, rotation: placement.rotation };
  if (insideEnvelope({ ...shape, ...target }, ring)) return target;

  if (!findPlacement(ring, shape.width, shape.depth, { rotation: shape.rotation })) return target;

  const from = { cx: placement.cx, cy: placement.cy };
  // A slide needs somewhere legal to slide from.
  if (!insideEnvelope({ ...shape, ...from }, ring)) return target;

  const dx = target.cx - from.cx, dy = target.cy - from.cy;
  let best = from;
  let shortest = Math.hypot(dx, dy);
  for (const [mx, my] of [[dx, dy], [dx, 0], [0, dy]]) {
    if (!mx && !my) continue;
    const candidate = reachAlong(ring, shape, from, mx, my);
    const distance = Math.hypot(target.cx - candidate.cx, target.cy - candidate.cy);
    if (distance < shortest) { shortest = distance; best = candidate; }
  }
  return best;
}

/* § 6 Abs. 5 SächsBO: 0,4 H, at least 3 m. The floor is all that can be used
   for a neighbour, because no OSM tag gives a wall height — see
   docs/research/abstandsflaechen-nachbargebaeude.md. */
const NEIGHBOUR_MINIMUM_M = 3;

/** Beyond this from the boundary a neighbouring wall cannot reach onto us. */
const NEIGHBOUR_REACH_M = 25;

/** Shortest distance between two segments, or 0 where they cross. */
function segmentDistance(a1, a2, b1, b2) {
  return Math.min(
    distanceToSegment(a1, b1, b2), distanceToSegment(a2, b1, b2),
    distanceToSegment(b1, a1, a2), distanceToSegment(b2, a1, a2)
  );
}

/**
 * Per boundary segment, how close the nearest neighbouring building comes to
 * it. `Infinity` where nothing is near enough to matter.
 *
 * Indexed like everything `buildableArea` consumes: by the edges of the ring
 * turned counter-clockwise, not of the ring as it came in.
 */
export function neighbourDistances(ring, buildings, options = {}) {
  const reach = options.reach ?? NEIGHBOUR_REACH_M;
  const poly = asCounterClockwise(plainRing(ring));
  const edges = polygonEdges(poly);
  const distances = edges.map(() => Infinity);
  if (!Array.isArray(buildings) || !buildings.length) return distances;

  const outlines = [];
  for (const building of buildings) {
    const outline = plainRing(Array.isArray(building) ? building : building.ring ?? []);
    if (outline.length < 3) continue;
    /* Our own house, if OSM has it, is not a neighbour. A footprint whose
       centre lies inside the parcel is on this plot, not next to it. */
    if (pointInPolygon(polygonCentroid(outline), poly)) continue;
    outlines.push(outline);
  }

  for (let i = 0; i < edges.length; i++) {
    const { a, b } = edges[i];
    for (const outline of outlines) {
      for (let j = 0; j < outline.length; j++) {
        const c = outline[j], d = outline[(j + 1) % outline.length];
        const gap = segmentDistance(a, b, c, d);
        if (gap < distances[i]) distances[i] = gap;
      }
    }
    if (distances[i] > reach) distances[i] = Infinity;
  }
  return distances;
}

/**
 * The setback depths as they would have to be for the neighbouring building's
 * own minimum setback to clear ours.
 *
 * Not a legal requirement, and the interface must not present it as one:
 * § 6 Abs. 2 SächsBO puts each building's setback area on its own plot, so a
 * neighbour standing too close is their problem, not a deeper obligation for
 * us. What this marks is the strip where the two areas would overlap — where
 * the pair of buildings ends up closer than the 3 + 3 m the statute produces
 * in its minimal case, which is a question for the building authority.
 *
 * `depth[i] + max(0, 3 − d[i])`: exactly how far the neighbour's own minimum
 * reaches across the boundary onto us. Where the neighbour is 3 m clear or
 * nothing is near, this is the ordinary setback and nothing extra is drawn.
 */
export function neighbourSetbackDepths(ring, depths, buildings, options = {}) {
  const minimum = options.minimum ?? NEIGHBOUR_MINIMUM_M;
  const own = plainDepths(depths, ring.length);
  const distances = neighbourDistances(ring, buildings, options);
  return distances.map((distance, i) => {
    const base = Array.isArray(own) ? own[i] : own;
    return Number.isFinite(distance) ? base + Math.max(0, minimum - distance) : base;
  });
}

/** Does any segment ask for more than the statutory setback? */
export const hasNeighbourHint = (own, hint) =>
  Array.isArray(hint) && hint.some((depth, i) => depth > (Array.isArray(own) ? own[i] : own) + 1e-9);

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
 * north is rotated against the drawing, so boundaries read "Ost · Nachbar"
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

/**
 * The minimum rotated rectangle as four corners, counter-clockwise, starting at
 * the corner that is lowest in its own frame.
 *
 * `minimumRotatedRectangle` answers with the measurements only, and a dimension
 * chain has to be drawn on the actual sides. Side `0→1` is `width` long, side
 * `1→2` is `height`. Returns `null` for a degenerate ring.
 */
export function minimumRotatedRectangleCorners(ring) {
  if (!ring || ring.length < 3) return null;
  const best = minimumRotatedRectangle(ring);
  if (!best) return null;
  const c = Math.cos(-best.angle), s = Math.sin(-best.angle);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of ring) {
    const x = p.x * c - p.y * s, y = p.x * s + p.y * c;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const back = (x, y) => ({ x: x * c + y * s, y: -x * s + y * c });
  return {
    ...best,
    corners: [back(minX, minY), back(maxX, minY), back(maxX, maxY), back(minX, maxY)]
  };
}
