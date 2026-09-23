/**
 * Which side of a plot faces its street, read off the cadastre.
 *
 * The side used to be guessed as the longest edge. That is right for the
 * common deep plot with a long street front and wrong for everything else:
 * Kirchstraße 4 in Liebertwolkwitz fronts the Kirchstraße with its short west
 * side, and "Straßenparallel" put a neighbour's fence at the bottom of every
 * drawing of it. In ALKIS a street is a parcel of its own, so the front is the
 * boundary the plot shares with one — and the register also says what that
 * street is called, which settles a corner plot: the front is the street of
 * its own address, not whichever kerb happens to be longer.
 *
 * `/api/parcels/streets` answers the traffic parcels; everything here is the
 * browser measuring its own outline against them.
 */
import { polygonEdges, pointInPolygon, distanceToSegment, boundingBox } from "./geometry.js";
import { toLocal } from "./projection.js";
import { streetParcels } from "./api.js";

/** How far a boundary may lie from a street parcel and still be its kerb.
 *  Shared boundaries are the same coordinates in both outlines; the slack
 *  covers the metres-from-degrees conversion and a tidied vertex. */
const KERB_TOLERANCE_M = 0.6;

/** Spacing of the points each edge is tested at. */
const SAMPLE_STEP_M = 0.5;

/** A corner that merely touches a street is not a front: the first and last
 *  stretch of every edge is left out of the count. */
const CORNER_CLEARANCE_M = 1;

/** Below this much shared boundary a contact is a corner, not a front. */
const MIN_FRONT_M = 2;

/** „Kirchstraße 8, 8a" and „Radeburger Straße, Ortsteil Moritzburg" to the
 *  bare street name, lower-cased and with „Str." spelt out. */
export function streetNames(lagebezeichnung) {
  return String(lagebezeichnung ?? "")
    .split(";")
    .map(part => part.split(",")[0]
      .replace(/\s+\d+\s*[a-z]?(\s*[-/]\s*\d+\s*[a-z]?)?$/i, "")
      .replace(/str\.$/i, "straße")
      .replace(/strasse$/i, "straße")
      .trim()
      .toLowerCase())
    .filter(name => name && name !== "ohne lage");
}

/** Every outer ring of a GeoJSON polygon or multipolygon, in local metres. */
function localRings(geometry, anchor) {
  const polygons = geometry?.type === "Polygon" ? [geometry.coordinates]
    : geometry?.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons
    .map(polygon => polygon?.[0] ?? [])
    .filter(ring => ring.length >= 4)
    .map(ring => toLocal(ring, anchor));
}

/**
 * The plot's street edge, measured against the traffic parcels around it.
 *
 * Returns `{ edge, street, length }` — the index into `polygon`, the name the
 * register gives that street (or null) and the metres of that edge along it —
 * or `null` when no edge shares a boundary with traffic land, in which case
 * the caller keeps its guess. `ownKeys` are the plot's own parcels: a private
 * access way that belongs to the plot is not its street.
 */
export function streetFront(polygon, anchor, parcels, lagebezeichnung, ownKeys = []) {
  if (!polygon?.length || !anchor || !parcels?.length) return null;
  const own = new Set(ownKeys.filter(Boolean));
  const address = new Set(streetNames(lagebezeichnung));

  const streets = parcels
    .filter(feature => !own.has(feature.properties?.kennzeichen))
    .flatMap(feature => localRings(feature.geometry, anchor).map(ring => {
      const box = boundingBox(ring);
      const names = streetNames(feature.properties?.lagebezeichnung);
      return {
        ring,
        edges: polygonEdges(ring),
        box,
        names,
        onAddress: names.some(name => address.has(name))
      };
    }));
  if (!streets.length) return null;

  const touching = point => streets.filter(street =>
    point.x >= street.box.minX - KERB_TOLERANCE_M && point.x <= street.box.maxX + KERB_TOLERANCE_M
    && point.y >= street.box.minY - KERB_TOLERANCE_M && point.y <= street.box.maxY + KERB_TOLERANCE_M
    && (pointInPolygon(point, street.ring)
      || street.edges.some(e => distanceToSegment(point, e.a, e.b) <= KERB_TOLERANCE_M)));

  const measured = polygonEdges(polygon).map((edge, index) => {
    const usable = edge.length - 2 * CORNER_CLEARANCE_M;
    const result = { edge: index, length: 0, addressLength: 0, names: new Map() };
    if (usable <= 0) return result;
    const samples = Math.max(1, Math.round(usable / SAMPLE_STEP_M));
    const share = usable / samples;
    for (let i = 0; i < samples; i++) {
      const t = (CORNER_CLEARANCE_M + (i + 0.5) * share) / edge.length;
      const hits = touching({ x: edge.a.x + t * edge.dx, y: edge.a.y + t * edge.dy });
      if (!hits.length) continue;
      result.length += share;
      if (hits.some(street => street.onAddress)) result.addressLength += share;
      const name = (hits.find(street => street.onAddress) ?? hits.find(street => street.names.length))?.names[0];
      if (name) result.names.set(name, (result.names.get(name) ?? 0) + share);
    }
    return result;
  });

  // The street of the plot's own address first; any street when none borders it.
  const onAddress = measured.filter(m => m.addressLength >= MIN_FRONT_M);
  const pool = onAddress.length ? onAddress : measured.filter(m => m.length >= MIN_FRONT_M);
  if (!pool.length) return null;
  const key = onAddress.length ? "addressLength" : "length";
  const best = pool.reduce((a, b) => (b[key] > a[key] ? b : a));
  const street = [...best.names.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  return { edge: best.edge, street: displayName(street, parcels), length: best[key] };
}

/** The register's own spelling of a name that was lower-cased for comparing. */
function displayName(name, parcels) {
  if (!name) return null;
  for (const feature of parcels) {
    const raw = String(feature.properties?.lagebezeichnung ?? "").split(";")
      .map(part => part.split(",")[0].trim())
      .find(part => part.toLowerCase() === name);
    if (raw) return raw;
  }
  return name;
}

/** How far past the plot's own reach the box for its streets extends: a street
 *  parcel is rarely narrower, and only its near kerb has to be in the box. */
const STREET_REACH_M = 20;

/** The backend's ceiling for that box, and the size of a large field. */
const MAX_BOX_M = 1000;

/**
 * Ask the cadastre for the plot's street and write the answer onto the plot.
 *
 * `streetFront` becomes `{ street, length }` when a front was found — and the
 * edge moves to it — or `null` when nothing borders traffic land, which keeps
 * the guess and records that the question was asked. A failed request throws
 * and leaves the field unset, so the next load asks again.
 */
export async function settleStreetFront(plot, fetchStreets = streetParcels) {
  if (!plot?.anchor || !plot.polygon?.length) return plot;
  const reach = Math.max(...plot.polygon.map(v => Math.max(Math.abs(v.x), Math.abs(v.y))));
  const box = Math.min(MAX_BOX_M, Math.max(10, Math.ceil(reach + STREET_REACH_M)));
  const answer = await fetchStreets(plot.anchor.lat, plot.anchor.lon, box);
  const front = streetFront(plot.polygon, plot.anchor, answer?.features ?? [],
    plot.lagebezeichnung, [plot.kennzeichen]);
  if (front) {
    plot.streetEdge = front.edge;
    plot.streetFront = { street: front.street, length: Math.round(front.length * 10) / 10 };
  } else {
    plot.streetFront = null;
  }
  return plot;
}
