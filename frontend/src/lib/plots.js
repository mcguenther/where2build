/**
 * Builds a plot from what the services actually returned.
 *
 * Nothing here invents a value. A field the cadastre did not deliver stays
 * empty, and the interface has to cope with that rather than filling the gap.
 */
import { toLocal, anchorOf } from "./projection.js";
import { polygonArea, polygonEdges } from "./geometry.js";
import { newId, CUSTOM_SIZE, DEFAULT_FOOTPRINT } from "./store.js";

/**
 * Outer ring of a GeoJSON Polygon, or the one part of a MultiPolygon that is
 * meant: the piece around `near` when a caller names a point, else the biggest.
 *
 * A plot of parcels that do not touch comes back as a MultiPolygon, and taking
 * whichever part the register listed first drew the outline around the parcel
 * that had just been added rather than around the one the user started from.
 */
export function outerRing(geometry, near = null) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates[0] ?? [];
  if (geometry.type !== "MultiPolygon") return [];
  const rings = (geometry.coordinates ?? []).map(part => part?.[0] ?? []).filter(r => r.length >= 3);
  if (!rings.length) return [];
  if (near) {
    const hit = rings.find(ring => pointInRing(near, ring));
    if (hit) return hit;
  }
  return rings.reduce((a, b) => (Math.abs(ringArea(b)) > Math.abs(ringArea(a)) ? b : a));
}

/** Twice the signed area of a `[lon, lat]` ring — for comparing parts only. */
const ringArea = ring => ring.reduce((sum, [x, y], i) => {
  const [nx, ny] = ring[(i + 1) % ring.length];
  return sum + (x * ny - nx * y);
}, 0);

/** Even-odd test in degrees; the parts are far enough apart for that to hold. */
const pointInRing = ([x, y], ring) => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
};

/** GeoJSON rings repeat the first vertex and often carry near-duplicates. */
export function tidyRing(ring, minimumGap = 0.1) {
  const out = [];
  for (const p of ring) {
    if (!out.length || Math.hypot(p.x - out[out.length - 1].x, p.y - out[out.length - 1].y) > minimumGap) out.push(p);
  }
  if (out.length > 1 && Math.hypot(out[0].x - out[out.length - 1].x, out[0].y - out[out.length - 1].y) < minimumGap) out.pop();
  return out;
}

/**
 * Which boundary segment faces the street.
 *
 * The proper answer comes from the ALKIS `Nutzung` layer — the shared edge with
 * a Verkehrsfläche. Until that is wired up, the longest edge is the better guess
 * than "the first one": building plots are usually wider along the road than
 * along a side boundary. The user can still align to any edge afterwards.
 */
export function guessStreetEdge(ring) {
  const edges = polygonEdges(ring);
  let best = 0;
  edges.forEach((e, i) => { if (e.length > edges[best].length) best = i; });
  return best;
}

/**
 * Turn a `/api/parcels/resolve` FeatureCollection into a plot.
 * `extra` carries what the cadastre cannot know: asking price, land value, name.
 */
export function plotFromCadastre(response, extra = {}) {
  const features = response?.features ?? [];
  const merged = response?.grundstueck ?? features[0];
  const wgs = outerRing(merged?.geometry, extra.near ?? null);
  if (wgs.length < 4) throw new Error("Die Antwort des Katasterdienstes enthält keine brauchbare Geometrie.");

  const anchor = anchorOf(wgs);
  const polygon = tidyRing(toLocal(wgs, anchor));
  if (polygon.length < 3) throw new Error("Der Flurstücksumriss hat zu wenige Punkte.");

  const officialArea = features.reduce((sum, f) => sum + (f.properties?.flaeche_amtlich_m2 ?? 0), 0);
  const first = features[0]?.properties ?? {};
  const numbers = features
    .map(f => {
      const p = f.properties ?? {};
      return p.nenner ? `${p.zaehler}/${p.nenner}` : String(p.zaehler ?? "");
    })
    .filter(Boolean);

  return {
    id: newId("plot"),
    name: extra.name || (first.lagebezeichnung || "").split(";")[0].trim() || `Flurstück ${numbers[0] ?? ""}`.trim(),
    municipality: extra.municipality || first.gemeinde || "",
    gemarkung: first.gemarkung ?? "",
    // The key, not just the name: two Gemarkungen share a name (Plagwitz is in
    // Leipzig and in Machern), so adding a parcel later has to ask with this.
    gemarkungsnummer: first.gemarkungsnummer ?? null,
    flurstuecke: numbers,
    kennzeichen: first.kennzeichen ?? null,
    lagebezeichnung: first.lagebezeichnung ?? null,
    anchor,
    northOffset: 0,
    officialArea: Math.round(officialArea) || null,
    askingPrice: extra.askingPrice ?? null,
    bodenrichtwert: extra.bodenrichtwert ?? null,
    brwZone: extra.brwZone ?? null,
    brwReferenceDate: extra.brwReferenceDate ?? null,
    brwReferencePlotArea: extra.brwReferencePlotArea ?? null,
    brwConversionUrl: extra.brwConversionUrl ?? null,
    polygon,
    divisionLine: null,
    streetEdge: guessStreetEdge(polygon),
    /* A plot arrives with its own dimensions rather than with no house type at
     * all: the plan draws a footprint either way, and "nothing selected" in the
     * form beside it is not a state the user asked for. The caller replaces
     * this with a catalogue entry when there is one. `house` is centred here
     * and seated properly once the footprint is settled — see `seatHouse`. */
    houseTypeId: extra.houseTypeId ?? CUSTOM_SIZE,
    customSize: { ...DEFAULT_FOOTPRINT },
    house: centrePlacement(polygon),
    ratio: 1.35,
    wallHeight: 6.4,
    setbacks: polygon.map(() => 3),
    source: response?.quelle ?? "ALKIS",
    readAt: new Date().toISOString(),
    note: extra.note ?? "",
    routes: {}
  };
}

/**
 * Which of these parcels the cadastre says carries this address.
 *
 * `ave:lagebeztxt` holds what the register calls the parcel's location, often
 * several spellings joined by a semicolon ("Lessingweg; Lessingweg 42"). A
 * house number matches only as a whole token: "Lessingweg 4" must not answer
 * for "Lessingweg 46". Returns null when nothing matches — a guess here would
 * be worse than the point-in-polygon answer it would override.
 */
export function parcelForAddress(features, address) {
  const wanted = String(address ?? "").trim().toLowerCase();
  if (!wanted) return null;
  const matches = (features ?? []).filter(feature => {
    const location = String(feature.properties?.lagebezeichnung ?? "").toLowerCase();
    return location.split(";").some(part => part.trim() === wanted);
  });
  // Two parcels claiming the same address is not a tie to break here.
  return matches.length === 1 ? matches[0] : null;
}

function centrePlacement(ring) {
  const n = ring.length;
  return {
    cx: ring.reduce((s, p) => s + p.x, 0) / n,
    cy: ring.reduce((s, p) => s + p.y, 0) / n,
    rotation: 0
  };
}

