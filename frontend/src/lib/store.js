/**
 * Application state and its persistence.
 *
 * Everything lives in this browser: no account, no server round trip for the
 * user's own data. `localStorage` is the store; JSON is the way in and out.
 * Storage can throw (private windows, quota) — every access is guarded, and a
 * failure degrades to an in-memory session rather than breaking the app.
 */
import { reactive } from "vue";
import { emptyState } from "./sample.js";
import { polygonCentroid, footprintFromArea } from "./geometry.js";
import { coordinatesOf } from "./routes.js";

/** Centre of a ring in the shape a placement expects. The centroid returns
 *  {x, y}; spreading that into a placement silently yields cx/cy of undefined. */
export const centreOf = ring => {
  const c = polygonCentroid(ring);
  return { cx: c.x, cy: c.y, rotation: 0 };
};

const STORAGE_KEY = "where2build.v1";
const THEME_KEY = "where2build.theme";

export const state = reactive({
  daten: emptyState(),
  ansicht: "grundstuecke",   // grundstuecke | grundstueck | aufnahme | vergleich | haustypen | ziele | daten
  offenesGrundstueck: null,
  darstellung: "system",
  plan: { grund: "karte", genordet: true, masse: true, saum: true, messen: false }
});

/* ---------- Validation ----------
 * Imported files come from outside. Accept only what has shape and meaning, and
 * refuse the whole file otherwise — a half-applied import is worse than none.
 * Throws an Error whose message is shown to the user, so it is German. */
export function validate(input) {
  if (!input || typeof input !== "object") throw new Error("Die Datei enthält kein Objekt.");
  if (!Array.isArray(input.grundstuecke)) throw new Error("Das Feld „grundstuecke“ fehlt.");

  const plots = input.grundstuecke.filter(
    p => p && Array.isArray(p.polygon) && p.polygon.length >= 3 &&
         p.polygon.every(v => Number.isFinite(v?.x) && Number.isFinite(v?.y))
  );
  if (input.grundstuecke.length && !plots.length) {
    throw new Error("Kein Grundstück mit brauchbarer Geometrie gefunden.");
  }

  // Same plausibility window the extraction schema uses.
  const houseTypes = Array.isArray(input.haustypen)
    ? input.haustypen.filter(h => h && h.id && h.bebauteFlaeche >= 30 && h.bebauteFlaeche <= 400)
    : [];
  const destinations = (Array.isArray(input.ziele) ? input.ziele.filter(z => z && z.id && z.name) : [])
    .map(z => {
      const ziel = { id: z.id, name: z.name, adresse: typeof z.adresse === "string" ? z.adresse : "" };
      // A destination only counts as located once both coordinates survived.
      if (Number.isFinite(z.lat) && Number.isFinite(z.lon)) {
        ziel.lat = z.lat;
        ziel.lon = z.lon;
        if (typeof z.treffer === "string") ziel.treffer = z.treffer;
      }
      return ziel;
    });

  plots.forEach(p => {
    p.id ||= `gs-${Math.random().toString(36).slice(2, 9)}`;
    p.tiefen = Array.isArray(p.tiefen) && p.tiefen.length === p.polygon.length
      ? p.tiefen.map(t => Math.min(20, Math.max(0, Number(t) || 0)))
      : p.polygon.map(() => 3);
    p.haus = p.haus && Number.isFinite(p.haus.cx)
      ? { cx: p.haus.cx, cy: p.haus.cy, rotation: Number(p.haus.rotation) || 0 }
      : centreOf(p.polygon);
    p.verhaeltnis = Math.min(2.2, Math.max(1, Number(p.verhaeltnis) || 1.35));
    if (p.eigenmass) {
      // Same plausibility limits the extraction schema uses: outside 4-30 m it is a typo, not a house.
      p.eigenmass = {
        laenge: Math.min(30, Math.max(4, Number(p.eigenmass.laenge) || 11.4)),
        breite: Math.min(30, Math.max(4, Number(p.eigenmass.breite) || 8.5))
      };
    }
    p.wandhoehe = Math.min(12, Math.max(2.5, Number(p.wandhoehe) || 6.4));
    p.nordVersatz = Number(p.nordVersatz) || 0;
    p.strassenkante = Number.isInteger(p.strassenkante) && p.strassenkante < p.polygon.length ? p.strassenkante : 0;
    if (p.anker && Number.isFinite(p.anker.lat) && Number.isFinite(p.anker.lon)) {
      p.anker = { lat: p.anker.lat, lon: p.anker.lon };
    } else {
      delete p.anker;   // no georeference: the plan falls back to its synthetic surroundings
    }
    p.flurstuecke = Array.isArray(p.flurstuecke) ? p.flurstuecke : [];
    p.wege = pruefeWege(p.wege, destinations);
  });

  return {
    version: 1,
    grundstuecke: plots,
    haustypen: houseTypes,
    ziele: destinations,
    auswahl: Array.isArray(input.auswahl) ? input.auswahl.filter(id => plots.some(p => p.id === id)) : []
  };
}

/**
 * Routes are kept exactly as the backend answered, minus anything that cannot
 * be trusted after a round trip through a JSON file a user may have edited.
 * A route to a destination that no longer exists is dropped rather than kept
 * as an orphan.
 */
function pruefeWege(wege, destinations) {
  if (!wege || typeof wege !== "object") return {};
  const bekannt = new Set(destinations.map(z => z.id));
  const sauber = {};

  Object.entries(wege).forEach(([zielId, weg]) => {
    if (!bekannt.has(zielId) || !weg || typeof weg !== "object") return;
    // The mockup stored an array of invented minutes here. It is not a route
    // and cannot be repaired into one; it goes.
    if (Array.isArray(weg) || !weg.modi || typeof weg.modi !== "object") return;

    const modi = {};
    Object.entries(weg.modi).forEach(([art, m]) => {
      if (!m || typeof m !== "object") return;
      const eintrag = { erreichbar: m.erreichbar === true };
      if (Number.isFinite(m.duration_s) && m.duration_s >= 0) eintrag.duration_s = Math.round(m.duration_s);
      if (Number.isInteger(m.umstiege) && m.umstiege >= 0) eintrag.umstiege = m.umstiege;
      if (typeof m.hinweis === "string") eintrag.hinweis = m.hinweis;
      const linie = coordinatesOf(m.geometry);
      if (linie) eintrag.geometry = { type: "LineString", coordinates: linie };
      // Without a duration there is nothing to show and nothing to compare.
      if (eintrag.erreichbar && eintrag.duration_s === undefined) return;
      modi[art] = eintrag;
    });

    if (!Object.keys(modi).length) return;
    sauber[zielId] = {
      modi,
      berechnet_am: typeof weg.berechnet_am === "string" ? weg.berechnet_am : null,
      quelle: typeof weg.quelle === "string" ? weg.quelle : null
    };
  });

  return sauber;
}

export function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) state.daten = validate(JSON.parse(raw));
  } catch {
    // Corrupt, absent or unreadable — the sample data already in place stands.
  }
  try {
    state.darstellung = localStorage.getItem(THEME_KEY) || "system";
  } catch {
    state.darstellung = "system";
  }
  applyTheme(state.darstellung);
}

export function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.daten));
  } catch {
    // Quota or a private window: keep running, the session is still usable.
  }
}

export function applyTheme(choice) {
  state.darstellung = choice;
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  try { localStorage.setItem(THEME_KEY, choice); } catch { /* not essential */ }
}

/** Clears everything this browser holds. There is nothing to fall back to. */
export function leeren() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* not essential */ }
  state.daten = emptyState();
  save();
}

export const exportJson = () => JSON.stringify(state.daten, null, 2);

/** Replaces the whole state. Throws with a German message when the input is unusable. */
export function importJson(text) {
  if (!text || !text.trim()) throw new Error("Es wurde nichts zum Einlesen angegeben.");
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("Das ist kein gültiges JSON.");
  }
  state.daten = validate(parsed);
  save();
  return state.daten;
}

/* ---------- Lookups and mutations ---------- */
/** Time alone collides when two things are created in the same millisecond —
 *  a double click on "Ziel hinzufügen" was enough. */
export const newId = prefix =>
  `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export const plotById = id => state.daten.grundstuecke.find(p => p.id === id) || null;
export const houseTypeById = id => state.daten.haustypen.find(h => h.id === id) || null;

/** Sentinel house type: dimensions typed straight into the plot. */
export const EIGENMASS = "eigen";

export function houseFootprint(plot) {
  if (plot.haustypId === EIGENMASS) {
    const eigen = plot.eigenmass || { laenge: 11.4, breite: 8.5 };
    return { width: eigen.laenge, depth: eigen.breite, estimated: false, eigen: true };
  }
  const type = houseTypeById(plot.haustypId);
  if (!type) return { width: 10, depth: 8, estimated: true };
  if (type.laenge && type.breite) return { width: type.laenge, depth: type.breite, estimated: false };
  return { ...footprintFromArea(type.bebauteFlaeche, plot.verhaeltnis), estimated: true };
}

/** The footprint as the plan component wants it: dimensions plus placement. */
export const placement = plot => ({
  ...houseFootprint(plot),
  cx: plot.haus.cx,
  cy: plot.haus.cy,
  rotation: plot.haus.rotation
});

export function addPlot(plot) {
  state.daten.grundstuecke.push(plot);
  state.daten.auswahl = [...new Set([...state.daten.auswahl, plot.id])];
  save();
  return plot;
}

export function removePlot(id) {
  state.daten.grundstuecke = state.daten.grundstuecke.filter(p => p.id !== id);
  state.daten.auswahl = state.daten.auswahl.filter(a => a !== id);
  if (state.offenesGrundstueck === id) state.offenesGrundstueck = null;
  save();
}

export function toggleSelection(id, on) {
  state.daten.auswahl = on
    ? [...new Set([...state.daten.auswahl, id])]
    : state.daten.auswahl.filter(a => a !== id);
  save();
}

export function addHouseType(type) {
  state.daten.haustypen.push(type);
  save();
  return type;
}

export function removeHouseType(id) {
  state.daten.haustypen = state.daten.haustypen.filter(h => h.id !== id);
  // Plots pointing at the removed type fall back to the first one left.
  const fallback = state.daten.haustypen[0]?.id ?? null;
  state.daten.grundstuecke.forEach(p => { if (p.haustypId === id) p.haustypId = fallback; });
  save();
}

/** Attach a looked-up coordinate to a destination; `treffer` is what the
 *  geocoder actually matched, which the user needs to see to judge it. */
export function locateDestination(id, { lat, lon, treffer }) {
  const ziel = state.daten.ziele.find(z => z.id === id);
  if (!ziel) return null;
  ziel.lat = lat;
  ziel.lon = lon;
  ziel.treffer = treffer || null;
  // The old routes started somewhere else; they are no longer this route.
  state.daten.grundstuecke.forEach(p => { delete p.wege[id]; });
  save();
  return ziel;
}

/** Drop a coordinate again — used when the address is edited. */
export function unlocateDestination(id) {
  const ziel = state.daten.ziele.find(z => z.id === id);
  if (!ziel || ziel.lat === undefined) return;
  delete ziel.lat;
  delete ziel.lon;
  delete ziel.treffer;
  state.daten.grundstuecke.forEach(p => { delete p.wege[id]; });
  save();
}

/** Store what the routing service answered for one plot. */
export function setRoutes(plotId, wege, quelle) {
  const plot = state.daten.grundstuecke.find(p => p.id === plotId);
  if (!plot) return;
  const stempel = new Date().toISOString();
  Object.entries(wege).forEach(([zielId, modi]) => {
    plot.wege[zielId] = { modi, berechnet_am: stempel, quelle: quelle || null };
  });
  save();
}

export function addDestination() {
  const ziel = { id: newId("zl"), name: "Neues Ziel", adresse: "" };
  state.daten.ziele.push(ziel);
  save();
  return ziel;
}

export function removeDestination(id) {
  state.daten.ziele = state.daten.ziele.filter(z => z.id !== id);
  state.daten.grundstuecke.forEach(p => { delete p.wege[id]; });
  save();
}

