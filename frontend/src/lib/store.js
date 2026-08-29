/**
 * Application state and its persistence.
 *
 * Everything lives in this browser: no account, no server round trip for the
 * user's own data. `localStorage` is the store; JSON is the way in and out.
 * Storage can throw (private windows, quota) — every access is guarded, and a
 * failure degrades to an in-memory session rather than breaking the app.
 */
import { reactive } from "vue";
import { emptyState, SCHEMA_VERSION } from "./sample.js";
import { polygonCentroid, footprintFromArea } from "./geometry.js";
import { coordinatesOf } from "./routes.js";

/** Centre of a ring in the shape a placement expects. The centroid returns
 *  {x, y}; spreading that into a placement silently yields cx/cy of undefined. */
export const centreOf = ring => {
  const c = polygonCentroid(ring);
  return { cx: c.x, cy: c.y, rotation: 0 };
};

/* The key still says v1: it names the slot, not the schema. Renaming it would
 * hide every document already stored under it, which is the one thing the
 * migration below exists to prevent. */
const STORAGE_KEY = "where2build.v1";
const THEME_KEY = "where2build.theme";

export const state = reactive({
  data: emptyState(),
  view: "plots",   // plots | plot | wizard | compare | houseTypes | destinations | data
  openPlotId: null,
  theme: "system",
  plan: { backdrop: "map", northUp: true, showDimensions: true, showSetbacks: true, measuring: false }
});

/* ---------- Migration from the version-1 document ----------
 * Version 1 named its fields in German. Those names are gone from the code, but
 * a user's exported file — or what is already in their browser — still carries
 * them, and dropping their plots over a rename would be indefensible. Every
 * version-1 document is therefore translated key by key before validation.
 * Field names that belong to an authority's schema (`gemarkung`,
 * `bodenrichtwert`, `kennzeichen`, `lagebezeichnung`, `flurstuecke`) never
 * changed and are carried over untouched. */
const PLOT_KEYS_V1 = {
  "ort": "municipality",
  "anker": "anchor",
  "nordVersatz": "northOffset",
  "flaecheAmtlich": "officialArea",
  "kaufpreis": "askingPrice",
  "brwStichtag": "brwReferenceDate",
  "teilung": "divisionLine",
  "strassenkante": "streetEdge",
  "haustypId": "houseTypeId",
  "haus": "house",
  "eigenmass": "customSize",
  "verhaeltnis": "ratio",
  "wandhoehe": "wallHeight",
  "tiefen": "setbacks",
  "quelle": "source",
  "gelesenAm": "readAt",
  "notiz": "note",
  "wege": "routes"
};

const HOUSE_TYPE_KEYS_V1 = {
  "hersteller": "manufacturer",
  "bebauteFlaeche": "builtArea",
  "wohnflaeche": "livingArea",
  "wohnflaecheEg": "livingAreaGround",
  "wohnflaecheOg": "livingAreaUpper",
  "laenge": "length",
  "breite": "width",
  "dachform": "roofShape",
  "preisAb": "priceFrom",
  "grundstueckAb": "minimumPlotArea",
  "traufhoehe": "eavesHeight",
  "firsthoehe": "ridgeHeight",
  "verhaeltnis": "ratio",
  "quelle": "source",
  "gelesenAm": "readAt",
  "hinweis": "note",
  "eigen": "custom"
};

const DESTINATION_KEYS_V1 = { "adresse": "address", "treffer": "match" };

/** The sentinel that stood in `haustypId` for "dimensions typed by hand". */
const CUSTOM_SIZE_V1 = "eigen";

const renameKeys = (object, map) => {
  if (!object || typeof object !== "object") return object;
  const out = {};
  for (const [key, value] of Object.entries(object)) out[map[key] ?? key] = value;
  return out;
};

function migratePlot(plot) {
  if (!plot || typeof plot !== "object") return plot;
  const out = renameKeys(plot, PLOT_KEYS_V1);
  if (out.houseTypeId === CUSTOM_SIZE_V1) out.houseTypeId = CUSTOM_SIZE;
  if (out.customSize && typeof out.customSize === "object") {
    out.customSize = { length: out.customSize.laenge, width: out.customSize.breite };
  }
  if (out.routes && typeof out.routes === "object" && !Array.isArray(out.routes)) {
    out.routes = Object.fromEntries(Object.entries(out.routes).map(([id, route]) => [
      id,
      // The per-mode entries are the routing service's own answer and keep its
      // field names; only the wrapper around them was ours to rename.
      route && typeof route === "object" && !Array.isArray(route)
        ? { modes: route.modi, calculatedAt: route.berechnet_am, source: route.quelle }
        : route
    ]));
  }
  return out;
}

/**
 * Which schema a document follows. Files written before the field existed carry
 * no version at all, so the old container name decides for them.
 */
function schemaVersion(input) {
  if (Number.isFinite(input.version)) return input.version;
  return Array.isArray(input.grundstuecke) ? 1 : SCHEMA_VERSION;
}

function migrate(input) {
  return {
    version: SCHEMA_VERSION,
    plots: (Array.isArray(input.grundstuecke) ? input.grundstuecke : []).map(migratePlot),
    houseTypes: (Array.isArray(input.haustypen) ? input.haustypen : [])
      .map(h => renameKeys(h, HOUSE_TYPE_KEYS_V1)),
    destinations: (Array.isArray(input.ziele) ? input.ziele : [])
      .map(z => renameKeys(z, DESTINATION_KEYS_V1)),
    selection: input.auswahl
  };
}

/* ---------- Validation ----------
 * Imported files come from outside. Accept only what has shape and meaning, and
 * refuse the whole file otherwise — a half-applied import is worse than none.
 * Throws an Error whose message is shown to the user, so it is German. */
export function validate(raw) {
  if (!raw || typeof raw !== "object") throw new Error("Die Datei enthält kein Objekt.");
  const version = schemaVersion(raw);
  if (version > SCHEMA_VERSION) {
    throw new Error(`Die Datei stammt aus einer neueren Fassung (Version ${version}). Bitte die Anwendung aktualisieren.`);
  }
  const input = version < SCHEMA_VERSION ? migrate(raw) : raw;
  if (!Array.isArray(input.plots)) throw new Error("Das Feld „plots“ fehlt.");

  const plots = input.plots.filter(
    p => p && Array.isArray(p.polygon) && p.polygon.length >= 3 &&
         p.polygon.every(v => Number.isFinite(v?.x) && Number.isFinite(v?.y))
  );
  if (input.plots.length && !plots.length) {
    throw new Error("Kein Grundstück mit brauchbarer Geometrie gefunden.");
  }

  // Same plausibility window the extraction schema uses.
  const houseTypes = Array.isArray(input.houseTypes)
    ? input.houseTypes.filter(h => h && h.id && h.builtArea >= 30 && h.builtArea <= 400)
    : [];
  const destinations = (Array.isArray(input.destinations) ? input.destinations.filter(d => d && d.id && d.name) : [])
    .map(d => {
      const destination = { id: d.id, name: d.name, address: typeof d.address === "string" ? d.address : "" };
      // A destination only counts as located once both coordinates survived.
      if (Number.isFinite(d.lat) && Number.isFinite(d.lon)) {
        destination.lat = d.lat;
        destination.lon = d.lon;
        if (typeof d.match === "string") destination.match = d.match;
      }
      return destination;
    });

  plots.forEach(p => {
    p.id ||= `plot-${Math.random().toString(36).slice(2, 9)}`;
    p.setbacks = Array.isArray(p.setbacks) && p.setbacks.length === p.polygon.length
      ? p.setbacks.map(t => Math.min(20, Math.max(0, Number(t) || 0)))
      : p.polygon.map(() => 3);
    p.house = p.house && Number.isFinite(p.house.cx)
      ? { cx: p.house.cx, cy: p.house.cy, rotation: Number(p.house.rotation) || 0 }
      : centreOf(p.polygon);
    p.ratio = Math.min(2.2, Math.max(1, Number(p.ratio) || 1.35));
    if (p.customSize) {
      // Same plausibility limits the extraction schema uses: outside 4-30 m it is a typo, not a house.
      p.customSize = {
        length: Math.min(30, Math.max(4, Number(p.customSize.length) || 11.4)),
        width: Math.min(30, Math.max(4, Number(p.customSize.width) || 8.5))
      };
    }
    p.wallHeight = Math.min(12, Math.max(2.5, Number(p.wallHeight) || 6.4));
    p.northOffset = Number(p.northOffset) || 0;
    p.streetEdge = Number.isInteger(p.streetEdge) && p.streetEdge < p.polygon.length ? p.streetEdge : 0;
    if (p.anchor && Number.isFinite(p.anchor.lat) && Number.isFinite(p.anchor.lon)) {
      p.anchor = { lat: p.anchor.lat, lon: p.anchor.lon };
    } else {
      delete p.anchor;   // no georeference: the plan falls back to its synthetic surroundings
    }
    p.flurstuecke = Array.isArray(p.flurstuecke) ? p.flurstuecke : [];
    p.routes = checkRoutes(p.routes, destinations);
  });

  return {
    version: SCHEMA_VERSION,
    plots,
    houseTypes,
    destinations,
    selection: Array.isArray(input.selection) ? input.selection.filter(id => plots.some(p => p.id === id)) : []
  };
}

/**
 * Routes are kept exactly as the backend answered, minus anything that cannot
 * be trusted after a round trip through a JSON file a user may have edited.
 * A route to a destination that no longer exists is dropped rather than kept
 * as an orphan.
 */
function checkRoutes(routes, destinations) {
  if (!routes || typeof routes !== "object") return {};
  const known = new Set(destinations.map(d => d.id));
  const clean = {};

  Object.entries(routes).forEach(([destinationId, route]) => {
    if (!known.has(destinationId) || !route || typeof route !== "object") return;
    // The mockup stored an array of invented minutes here. It is not a route
    // and cannot be repaired into one; it goes.
    if (Array.isArray(route) || !route.modes || typeof route.modes !== "object") return;

    const modes = {};
    Object.entries(route.modes).forEach(([mode, m]) => {
      if (!m || typeof m !== "object") return;
      const entry = { erreichbar: m.erreichbar === true };
      if (Number.isFinite(m.duration_s) && m.duration_s >= 0) entry.duration_s = Math.round(m.duration_s);
      if (Number.isInteger(m.umstiege) && m.umstiege >= 0) entry.umstiege = m.umstiege;
      if (typeof m.hinweis === "string") entry.hinweis = m.hinweis;
      const line = coordinatesOf(m.geometry);
      if (line) entry.geometry = { type: "LineString", coordinates: line };
      // Without a duration there is nothing to show and nothing to compare.
      if (entry.erreichbar && entry.duration_s === undefined) return;
      modes[mode] = entry;
    });

    if (!Object.keys(modes).length) return;
    clean[destinationId] = {
      modes,
      calculatedAt: typeof route.calculatedAt === "string" ? route.calculatedAt : null,
      source: typeof route.source === "string" ? route.source : null
    };
  });

  return clean;
}

export function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) state.data = validate(JSON.parse(raw));
  } catch {
    // Corrupt, absent or unreadable — whatever is already in place stands.
  }
  try {
    state.theme = localStorage.getItem(THEME_KEY) || "system";
  } catch {
    state.theme = "system";
  }
  applyTheme(state.theme);
}

export function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.data));
  } catch {
    // Quota or a private window: keep running, the session is still usable.
  }
}

export function applyTheme(choice) {
  state.theme = choice;
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  try { localStorage.setItem(THEME_KEY, choice); } catch { /* not essential */ }
}

/** Clears everything this browser holds. There is nothing to fall back to. */
export function clear() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* not essential */ }
  state.data = emptyState();
  save();
}

export const exportJson = () => JSON.stringify(state.data, null, 2);

/** Replaces the whole state. Throws with a German message when the input is unusable. */
export function importJson(text) {
  if (!text || !text.trim()) throw new Error("Es wurde nichts zum Einlesen angegeben.");
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("Das ist kein gültiges JSON.");
  }
  state.data = validate(parsed);
  save();
  return state.data;
}

/* ---------- Lookups and mutations ---------- */
/** Time alone collides when two things are created in the same millisecond —
 *  a double click on "Ziel hinzufügen" was enough. */
export const newId = prefix =>
  `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export const plotById = id => state.data.plots.find(p => p.id === id) || null;
export const houseTypeById = id => state.data.houseTypes.find(h => h.id === id) || null;

/** Sentinel house type: dimensions typed straight into the plot. */
export const CUSTOM_SIZE = "custom";

export function houseFootprint(plot) {
  // A house type is measured length × width; on the plan that is the footprint's
  // width along its own axis and its depth across it.
  if (plot.houseTypeId === CUSTOM_SIZE) {
    const size = plot.customSize || { length: 11.4, width: 8.5 };
    return { width: size.length, depth: size.width, estimated: false, custom: true };
  }
  const type = houseTypeById(plot.houseTypeId);
  if (!type) return { width: 10, depth: 8, estimated: true };
  if (type.length && type.width) return { width: type.length, depth: type.width, estimated: false };
  return { ...footprintFromArea(type.builtArea, plot.ratio), estimated: true };
}

/** The footprint as the plan component wants it: dimensions plus placement. */
export const placement = plot => ({
  ...houseFootprint(plot),
  cx: plot.house.cx,
  cy: plot.house.cy,
  rotation: plot.house.rotation
});

export function addPlot(plot) {
  state.data.plots.push(plot);
  state.data.selection = [...new Set([...state.data.selection, plot.id])];
  save();
  return plot;
}

export function removePlot(id) {
  state.data.plots = state.data.plots.filter(p => p.id !== id);
  state.data.selection = state.data.selection.filter(s => s !== id);
  if (state.openPlotId === id) state.openPlotId = null;
  save();
}

export function toggleSelection(id, on) {
  state.data.selection = on
    ? [...new Set([...state.data.selection, id])]
    : state.data.selection.filter(s => s !== id);
  save();
}

export function addHouseType(type) {
  state.data.houseTypes.push(type);
  save();
  return type;
}

export function removeHouseType(id) {
  state.data.houseTypes = state.data.houseTypes.filter(h => h.id !== id);
  // Plots pointing at the removed type fall back to the first one left.
  const fallback = state.data.houseTypes[0]?.id ?? null;
  state.data.plots.forEach(p => { if (p.houseTypeId === id) p.houseTypeId = fallback; });
  save();
}

/** Attach a looked-up coordinate to a destination; `match` is what the
 *  geocoder actually matched, which the user needs to see to judge it. */
export function locateDestination(id, { lat, lon, match }) {
  const destination = state.data.destinations.find(d => d.id === id);
  if (!destination) return null;
  destination.lat = lat;
  destination.lon = lon;
  destination.match = match || null;
  // The old routes started somewhere else; they are no longer this route.
  state.data.plots.forEach(p => { delete p.routes[id]; });
  save();
  return destination;
}

/** Drop a coordinate again — used when the address is edited. */
export function unlocateDestination(id) {
  const destination = state.data.destinations.find(d => d.id === id);
  if (!destination || destination.lat === undefined) return;
  delete destination.lat;
  delete destination.lon;
  delete destination.match;
  state.data.plots.forEach(p => { delete p.routes[id]; });
  save();
}

/** Store what the routing service answered for one plot. */
export function setRoutes(plotId, routes, source) {
  const plot = state.data.plots.find(p => p.id === plotId);
  if (!plot) return;
  const stamp = new Date().toISOString();
  Object.entries(routes).forEach(([destinationId, modes]) => {
    plot.routes[destinationId] = { modes, calculatedAt: stamp, source: source || null };
  });
  save();
}

export function addDestination() {
  const destination = { id: newId("dest"), name: "Neues Ziel", address: "" };
  state.data.destinations.push(destination);
  save();
  return destination;
}

export function removeDestination(id) {
  state.data.destinations = state.data.destinations.filter(d => d.id !== id);
  state.data.plots.forEach(p => { delete p.routes[id]; });
  save();
}
