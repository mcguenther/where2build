/**
 * What the drawings of the neighbourhood share: the plan, the boundary strips,
 * the key graphic and the sections all read the same analysis
 * (`analyseNeighbourhood`) and must name and colour a building the same way.
 * Nothing here computes a finding; it only places what the analysis found.
 */
import { CLASS_ACCESSORY, CLASS_OWN, BAND_MIN_UNKNOWN_AREA_M2 } from "./neighbourhood.js";

/** A point on a polyline at arc length `s`; past either end the end segment
 *  runs on straight, as `projectOnBoundary` measures it. */
export function pointAlong(points, s) {
  if (!points?.length) return null;
  if (points.length === 1) return { ...points[0] };
  let from = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    const last = i === points.length - 2;
    if (s <= from + length || last) {
      const t = length ? (s - from) / length : 0;
      const clamped = i === 0 && t < 0 ? t : last ? t : Math.max(0, t);
      return { x: a.x + (b.x - a.x) * clamped, y: a.y + (b.y - a.y) * clamped };
    }
    from += length;
  }
  return { ...points[points.length - 1] };
}

/** The piece of a polyline between two arc lengths, cut to the polyline. */
export function sliceAlong(points, from, to) {
  if (!points?.length || !(to > from)) return [];
  const out = [pointAlong(points, Math.max(0, from))];
  let s = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    s += Math.hypot(b.x - a.x, b.y - a.y);
    if (s > from && s < to) out.push({ ...b });
  }
  out.push(pointAlong(points, Math.min(to, polylineLength(points))));
  return out;
}

export function polylineLength(points) {
  let s = 0;
  for (let i = 0; i < (points?.length ?? 0) - 1; i++) {
    s += Math.hypot(points[i + 1].x - points[i].x, points[i + 1].y - points[i].y);
  }
  return s;
}

/** „Lessingweg 42" → „42", „Lessingweg 50a" → „50a"; null without a number. */
export function houseNumber(address) {
  const match = /\s(\d+\s*[a-zA-Z]?)$/.exec(String(address ?? "").split(",")[0].trim());
  return match ? match[1].replace(/\s+/g, "") : null;
}

/** The short name a drawing writes beside a building. */
export function shortName(building) {
  const number = houseNumber(building?.address);
  if (number) return `Nr. ${number}`;
  return building?.class === CLASS_ACCESSORY ? "Nebengebäude" : (building?.use || "Gebäude");
}

/**
 * How a building is drawn: „own" for Bestand on our plot, „aux" for garages,
 * sheds and small outlines without a function, „main" for everything else.
 * The same split the § 34 band uses, so a building never reads as a house in
 * one drawing and as a shed in the next.
 */
export function drawnKind(building) {
  if (!building) return "main";
  if (building.class === CLASS_OWN) return building.useKind === "residential" ? "own" : "own-aux";
  if (building.class === CLASS_ACCESSORY || building.useKind === "accessory") return "aux";
  if (building.useKind === "unknown" && building.area < BAND_MIN_UNKNOWN_AREA_M2) return "aux";
  return "main";
}

/** Area-weighted centre of a ring, for labels and markers. */
export function ringCentre(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length];
    const cross = p.x * q.y - q.x * p.y;
    a += cross; cx += (p.x + q.x) * cross; cy += (p.y + q.y) * cross;
  }
  if (Math.abs(a) < 1e-9) {
    return ring.reduce((s, p) => ({ x: s.x + p.x / ring.length, y: s.y + p.y / ring.length }), { x: 0, y: 0 });
  }
  return { x: cx / (3 * a), y: cy / (3 * a) };
}

/**
 * A boundary straightened out: `u` runs along it from its street end (scaled
 * so the chord measures the boundary's own length), `w` is the distance from
 * it, positive on the neighbour's side. Exact for a straight boundary; a
 * slightly bent one reads as its chord, which is what a strip can show.
 */
export function stripFrame(boundary, parcel) {
  const points = boundary?.points ?? [];
  if (points.length < 2) return null;
  const from = points[0], to = points[points.length - 1];
  const chord = Math.hypot(to.x - from.x, to.y - from.y);
  if (!(chord > 0)) return null;
  const dir = { x: (to.x - from.x) / chord, y: (to.y - from.y) / chord };
  let normal = { x: -dir.y, y: dir.x };
  const centre = ringCentre(parcel);
  if ((centre.x - from.x) * normal.x + (centre.y - from.y) * normal.y > 0) normal = { x: -normal.x, y: -normal.y };
  const k = boundary.length / chord;
  return {
    length: boundary.length,
    u: p => ((p.x - from.x) * dir.x + (p.y - from.y) * dir.y) * k,
    w: p => (p.x - from.x) * normal.x + (p.y - from.y) * normal.y
  };
}

/** Which boundary a finding looks at, and which section, if any. */
export function findingTargets(finding, analysis) {
  if (!finding?.buildingId || !analysis?.buildings) return { boundary: null, section: null };
  const building = analysis.buildings.find(b => b.id === finding.buildingId);
  const boundary = building?.facing?.boundary ?? null;
  const section = (analysis.sections ?? []).findIndex(s => s.buildingId === finding.buildingId);
  return { boundary, section: section >= 0 ? section : null };
}

/** The German name of a boundary, as a heading. */
export const BOUNDARY_NAMES = {
  street: "Zur Straße",
  right: "Rechte Seite",
  rear: "Hinten",
  left: "Linke Seite"
};

/** What a strip's axis is measured from. */
export const STRIP_ORIGINS = {
  street: "Meter ab der linken Ecke",
  right: "Meter ab der Straßenecke",
  rear: "Meter ab der rechten Ecke",
  left: "Meter ab der Straßenecke"
};
