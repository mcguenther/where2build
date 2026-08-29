/**
 * Builds a plot from what the services actually returned.
 *
 * Nothing here invents a value. A field the cadastre did not deliver stays
 * empty, and the interface has to cope with that rather than filling the gap.
 */
import { toLocal, anchorOf } from "./projection.js";
import { polygonArea, polygonEdges } from "./geometry.js";
import { newId } from "./store.js";

/** Outer ring of a GeoJSON Polygon or the first ring of a MultiPolygon. */
export function outerRing(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates[0] ?? [];
  if (geometry.type === "MultiPolygon") return geometry.coordinates[0]?.[0] ?? [];
  return [];
}

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
 * `zusatz` carries what the cadastre cannot know: asking price, land value, name.
 */
export function plotAusKataster(antwort, zusatz = {}) {
  const merkmale = antwort?.features ?? [];
  const vereinigt = antwort?.grundstueck ?? merkmale[0];
  const wgs = outerRing(vereinigt?.geometry);
  if (wgs.length < 4) throw new Error("Die Antwort des Katasterdienstes enthält keine brauchbare Geometrie.");

  const anker = anchorOf(wgs);
  const polygon = tidyRing(toLocal(wgs, anker));
  if (polygon.length < 3) throw new Error("Der Flurstücksumriss hat zu wenige Punkte.");

  const amtlich = merkmale.reduce((summe, f) => summe + (f.properties?.flaeche_amtlich_m2 ?? 0), 0);
  const erstes = merkmale[0]?.properties ?? {};
  const nummern = merkmale
    .map(f => {
      const p = f.properties ?? {};
      return p.nenner ? `${p.zaehler}/${p.nenner}` : String(p.zaehler ?? "");
    })
    .filter(Boolean);

  return {
    id: newId("gs"),
    name: zusatz.name || (erstes.lagebezeichnung || "").split(";")[0].trim() || `Flurstück ${nummern[0] ?? ""}`.trim(),
    ort: zusatz.ort || erstes.gemeinde || "",
    gemarkung: erstes.gemarkung ?? "",
    flurstuecke: nummern,
    kennzeichen: erstes.kennzeichen ?? null,
    lagebezeichnung: erstes.lagebezeichnung ?? null,
    anker,
    nordVersatz: 0,
    flaecheAmtlich: Math.round(amtlich) || null,
    kaufpreis: zusatz.kaufpreis ?? null,
    bodenrichtwert: zusatz.bodenrichtwert ?? null,
    brwZone: zusatz.brwZone ?? null,
    brwStichtag: zusatz.brwStichtag ?? null,
    polygon,
    teilung: null,
    strassenkante: guessStreetEdge(polygon),
    haustypId: zusatz.haustypId ?? null,
    haus: mittelpunktLage(polygon),
    verhaeltnis: 1.35,
    wandhoehe: 6.4,
    tiefen: polygon.map(() => 3),
    quelle: antwort?.quelle ?? "ALKIS",
    gelesenAm: new Date().toISOString(),
    notiz: zusatz.notiz ?? "",
    wege: {}
  };
}

function mittelpunktLage(ring) {
  const n = ring.length;
  return {
    cx: ring.reduce((s, p) => s + p.x, 0) / n,
    cy: ring.reduce((s, p) => s + p.y, 0) / n,
    rotation: 0
  };
}

/** The official area is what counts; the polygon area is for shape analysis. */
export const flaechenVergleich = plot => ({
  amtlich: plot.flaecheAmtlich,
  gerechnet: polygonArea(plot.polygon)
});
