/**
 * Application state and its persistence.
 *
 * Everything lives in this browser: the user's own data makes no round trip to
 * a server, whether or not this deployment has accounts. `localStorage` is the
 * store; JSON is the way in and out. (Server-side storage is Etappe 4 of
 * `docs/entscheidungen/startseite-und-konten.md`; signing in changes who the
 * backend thinks you are, not yet where the plots live.)
 * Storage can throw (private windows, quota) — every access is guarded, and a
 * failure degrades to an in-memory session rather than breaking the app.
 */
import { reactive } from "vue";
import { emptyState, SCHEMA_VERSION } from "./sample.js";
import {
  polygonCentroid, footprintFromArea, buildableArea, findPlacement,
  alignmentToEdge, boundingBox
} from "./geometry.js";
import { coordinatesOf, zubringerOf } from "./routes.js";
import { authState } from "./api.js";
import { settleStreetFront } from "./streetFront.js";
import * as server from "./serverStore.js";

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

/* Navigation is not in here: which view is open, and which plot, is what the
 * URL says. See `src/router/`. */
export const state = reactive({
  data: emptyState(),
  theme: "system",
  /* What "system" currently resolves to. Kept in the state rather than read
   * where it is needed, so anything that has to follow the palette — the map
   * backdrop, above all — can watch it like any other reactive value. */
  systemDark: false,
  plan: { backdrop: "map", northUp: true, showDimensions: true, showSetbacks: true, measuring: false },
  /* Who is signed in. Not part of the document and never stored: the backend
   * is the only one who knows, and it says so on every load. `eingerichtet`
   * false means this deployment has no accounts at all, which is the state the
   * app shipped in and still works in. */
  account: { eingerichtet: false, angemeldet: false, name: null, kennung: null, verwalter: false },
  /* The account's copy, and how it is doing. `active` false covers both a
   * deployment without a store and a signed-out browser, which behave the
   * same way from here: everything stays local. `adoption` is set once, when
   * a signed-in account is empty and this browser is not. */
  sync: { active: false, busy: false, error: "", conflicts: [], savedAt: null, adoption: null }
});

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** Ask the backend who is signed in. Called once when the app starts; the
 *  answer is a fact about the server, so nothing caches it in storage. */
export async function loadAccount() {
  state.account = await authState();
  return state.account;
}

/* Who was asked last, so the adoption question is asked once per account and
 * not again on the next reload. The answer is worth remembering across
 * reloads; the key carries the account so two people on one browser do not
 * inherit each other's decision. */
const ADOPTED_KEY = kennung => `where2build.uebernommen.${kennung}`;

const remembered = key => {
  try { return localStorage.getItem(key); } catch { return null; }
};
const remember = (key, value) => {
  try { localStorage.setItem(key, value); } catch { /* not essential */ }
};

/**
 * Bring the account's copy in, if there is an account and a store behind it.
 *
 * Three outcomes, and the third is the interesting one: the server answers
 * with a document, or it has none and this browser does (then the user is
 * asked whether to take it along), or there is no store at all and everything
 * stays exactly as it was.
 */
export async function loadFromAccount() {
  state.sync.adoption = null;
  if (!state.account.angemeldet) {
    state.sync.active = false;
    server.forget();
    return;
  }
  try {
    const stored = await server.pull();
    state.sync.active = true;
    if (stored) {
      state.data = validate({ ...stored.settings, plots: stored.plots });
      saveLocal();
      return;
    }
    // The account is empty. Offer to take this browser's work along, once.
    const local = state.data.plots.length;
    if (local && remembered(ADOPTED_KEY(state.account.kennung)) !== "nein") {
      state.sync.adoption = { plots: local };
    }
  } catch (error) {
    // 503 is "this deployment has no store" and 404 is a backend that predates
    // one. Neither is a failure: the app was a thing that keeps its work in
    // this browser long before it was anything else. Everything else is said
    // out loud rather than swallowed into local mode.
    state.sync.active = false;
    state.sync.error = [404, 503].includes(error.status) ? "" : (error.message || "");
  }
}

/** Take this browser's document into the account. */
export async function adoptLocal() {
  state.sync.busy = true;
  try {
    await server.push(state.data);
    state.sync.active = true;
    state.sync.adoption = null;
    state.sync.error = "";
  } catch (error) {
    state.sync.error = error.message || "Der Stand konnte nicht übernommen werden.";
  } finally {
    state.sync.busy = false;
  }
}

/** Leave it here. Asked once; the answer holds for this account. */
export function declineAdoption() {
  remember(ADOPTED_KEY(state.account.kennung), "nein");
  state.sync.adoption = null;
}

server.onReport(report => {
  Object.assign(state.sync, report);
});

/** Whether the interface is dark right now, choice and system setting folded
 *  into one answer. Reactive: reading it inside a computed tracks both. */
export function darkTheme() {
  return state.theme === "dark" || (state.theme === "system" && state.systemDark);
}

/** Follow the system setting for as long as the page lives. Idempotent, and a
 *  browser without `matchMedia` simply stays light. */
export function watchSystemTheme() {
  const query = window.matchMedia?.(DARK_QUERY);
  if (!query) return;
  state.systemDark = query.matches;
  if (watchSystemTheme.attached) return;
  watchSystemTheme.attached = true;
  const update = event => { state.systemDark = event.matches; };
  // Safari before 14 has only the deprecated spelling.
  if (query.addEventListener) query.addEventListener("change", update);
  else query.addListener(update);
}

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
  /* A name is not what makes a destination real — its identity and its
   * coordinate are. The name field starts empty on purpose, so filtering on it
   * would throw away exactly the destination the user just created. */
  const destinations = (Array.isArray(input.destinations) ? input.destinations.filter(d => d && d.id) : [])
    .map(d => {
      const destination = {
        id: d.id,
        name: typeof d.name === "string" ? d.name : "",
        address: typeof d.address === "string" ? d.address : ""
      };
      /* The feeder to the first stop, when one was pinned. Absent is the
       * default and means "automatisch", so only a real choice is written down
       * — but it has to be written down: rebuilding the destination without it
       * is how a picker comes to work and then forget. */
      const zubringer = zubringerOf(d);
      if (zubringer !== "automatic") destination.zubringer = zubringer;
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
    /* A house type the catalogue does not hold — never chosen, deleted since,
     * or dropped by the filter above — used to leave `houseTypeId` pointing at
     * nothing. The plan still drew a footprint, but the "Baukörper" box showed
     * no selection, so the drawing and the form disagreed about what was on the
     * plot. Such a plot falls back to its own dimensions, which is what the
     * footprint was all along. */
    if (p.houseTypeId !== CUSTOM_SIZE && !houseTypes.some(h => h.id === p.houseTypeId)) {
      p.houseTypeId = CUSTOM_SIZE;
      p.customSize ||= { ...DEFAULT_FOOTPRINT };
    }
    if (p.customSize) {
      // Same plausibility limits the extraction schema uses: outside 4-30 m it is a typo, not a house.
      p.customSize = {
        length: Math.min(30, Math.max(4, Number(p.customSize.length) || DEFAULT_FOOTPRINT.length)),
        width: Math.min(30, Math.max(4, Number(p.customSize.width) || DEFAULT_FOOTPRINT.width))
      };
    }
    p.wallHeight = Math.min(12, Math.max(2.5, Number(p.wallHeight) || 6.4));
    p.northOffset = Number(p.northOffset) || 0;
    p.streetEdge = Number.isInteger(p.streetEdge) && p.streetEdge < p.polygon.length ? p.streetEdge : 0;
    /* Absent: never asked, so the edge is the longest-edge guess. Null: asked,
     * and no boundary borders traffic land. See lib/streetFront.js. */
    if (p.streetFront && Number.isFinite(p.streetFront.length)) {
      p.streetFront = {
        street: typeof p.streetFront.street === "string" ? p.streetFront.street : null,
        length: p.streetFront.length
      };
    } else if (p.streetFront !== null) {
      delete p.streetFront;
    }
    if (p.anchor && Number.isFinite(p.anchor.lat) && Number.isFinite(p.anchor.lon)) {
      p.anchor = { lat: p.anchor.lat, lon: p.anchor.lon };
    } else {
      delete p.anchor;   // no georeference: the plan falls back to its synthetic surroundings
    }
    p.flurstuecke = Array.isArray(p.flurstuecke) ? p.flurstuecke : [];
    p.routes = checkRoutes(p.routes, destinations);
    const readings = checkReadings(p.neighbourReadings);
    if (readings) p.neighbourReadings = readings; else delete p.neighbourReadings;
    /* The old „Nachbarn" switch. The neighbourhood is a tab now and loads
       when it is opened, so a stored flag would mean nothing. */
    delete p.showNeighbours;
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
 * The reading chosen per Grenzbebauung, by the building's cadastral id: the
 * user's choice, like the other plot settings. Only the two known values
 * survive a round trip; anything else falls back to the cautious default by
 * being left out. Null when nothing is left, so a plot nobody chose for
 * carries no empty field.
 */
function checkReadings(readings) {
  if (!readings || typeof readings !== "object" || Array.isArray(readings)) return null;
  const kept = Object.fromEntries(Object.entries(readings)
    .filter(([id, value]) => id && (value === "setback" || value === "boundary")));
  return Object.keys(kept).length ? kept : null;
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
  watchSystemTheme();
}

function saveLocal() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.data));
  } catch {
    // Quota or a private window: keep running, the session is still usable.
  }
}

/**
 * Keep the document.
 *
 * Still synchronous, and still writing to this browser first: thirty-odd call
 * sites say `save()` and none of them should have to know whether an account
 * exists. The account's copy follows when there is one, collected rather than
 * per call, because dragging a building calls this per frame.
 */
export function save() {
  saveLocal();
  if (state.sync.active) server.schedule(state.data);
}

/** Write now, without waiting out the quiet period. For leaving the page. */
export function flushSave() {
  if (state.sync.active) return server.flush(state.data);
  return Promise.resolve();
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

/** Nothing has been entered here yet -- the state somebody arrives in, and
 *  the state they are back in once they clear everything out.
 *
 *  Deliberately all three lists and not only the plots: after deleting the
 *  plots but keeping a destination, the app is still in use and the sections
 *  still lead somewhere. Being signed in is a fourth reason to be past this
 *  point, because an account is a stand of its own even while it is empty. */
export const isFresh = () =>
  !state.account.angemeldet &&
  state.data.plots.length === 0 &&
  state.data.houseTypes.length === 0 &&
  state.data.destinations.length === 0;

export const plotById = id => state.data.plots.find(p => p.id === id) || null;
export const houseTypeById = id => state.data.houseTypes.find(h => h.id === id) || null;

/** Sentinel house type: dimensions typed straight into the plot. */
export const CUSTOM_SIZE = "custom";

/* The footprint a plot starts with while the catalogue is still empty. It is a
 * placeholder to drag and retype, not a figure read from anywhere — which is
 * why it arrives as "Eigene Maße" with the numbers in editable fields, and not
 * as a house type with a manufacturer's name on it. Two defaults used to
 * disagree here (10 x 8 in the footprint fallback, 11,4 x 8,5 in the custom
 * one), so the drawing changed size the moment the user opened the fields. */
export const DEFAULT_FOOTPRINT = { length: 11.4, width: 8.5 };

export function houseFootprint(plot) {
  // A house type is measured length × width; on the plan that is the footprint's
  // width along its own axis and its depth across it.
  if (plot.houseTypeId === CUSTOM_SIZE) {
    const size = plot.customSize || DEFAULT_FOOTPRINT;
    return { width: size.length, depth: size.width, estimated: false, custom: true };
  }
  const type = houseTypeById(plot.houseTypeId);
  if (!type) return { width: DEFAULT_FOOTPRINT.length, depth: DEFAULT_FOOTPRINT.width, estimated: true };
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

/* A placement search sweeps a grid at up to thirty angles, and a district
 * address really does resolve to a 1583 x 198 m field — a fixed 0,25 m step
 * would be five million cells per angle there. Same answer as the envelope
 * grid: cap the cell count and let the step grow. A seat is a starting point
 * the user drags, so a coarse one on a field is no loss; an ordinary parcel
 * stays at the fine step. */
const MAX_SEAT_CELLS = 20_000;

function seatStep(envelope) {
  const box = boundingBox(envelope);
  return Math.max(0.25, Math.sqrt((box.width * box.height) / MAX_SEAT_CELLS));
}

/**
 * Where this plot's footprint actually fits: parallel to the street front, and
 * as near the middle of the buildable envelope as that angle allows.
 *
 * Returns `null` when the footprint fits nowhere. That is a real answer on a
 * narrow plot and the interface has to say it, because the alternative — a
 * house drawn across the setback strip with nothing pointing it out — reads as
 * a plan rather than as the conflict it is.
 */
export function seatHouse(plot) {
  const envelope = buildableArea(plot.polygon, plot.setbacks);
  if (!envelope.length) return null;
  const { width, depth } = houseFootprint(plot);
  const step = seatStep(envelope);
  const near = polygonCentroid(envelope);
  const rotation = alignmentToEdge(plot.polygon, plot.streetEdge ?? 0);

  /* Street-parallel first: it is how the neighbours stand and what the user
   * would turn it to anyway. A plot too tight for that angle may still hold the
   * house at another one, and a seat askew beats no house at all — that search
   * takes the first fit rather than the most central, because without a
   * preferred centre it stops at the first hit instead of sweeping every angle
   * across the whole envelope. */
  const seat = findPlacement(envelope, width, depth, { rotation, near, step })
    ?? findPlacement(envelope, width, depth, { step });
  return seat
    ? { cx: seat.cx, cy: seat.cy, rotation: Math.round(seat.rotation * 10) / 10 }
    : null;
}

/** Seat the house, and say whether it worked. A footprint that fits nowhere
 *  leaves the placement alone: the drawing then shows the conflict instead of
 *  hiding it. */
export function autoSeatHouse(plot) {
  const seat = seatHouse(plot);
  if (seat) plot.house = seat;
  return Boolean(seat);
}

/**
 * Read the street front off the cadastre for every plot that was stored with
 * the longest-edge guess. One plot after another, and quietly: a failed
 * request leaves the guess standing and the next load asks again. The house
 * stays where it is — it may be where the user put it.
 */
export async function settleStoredStreetFronts() {
  for (const plot of state.data.plots) {
    if (!plot.anchor || plot.streetFront !== undefined) continue;
    try {
      await settleStreetFront(plot);
      save();
    } catch {
      // The guess stays; nothing on screen depends on this having worked.
    }
  }
}

export function addPlot(plot) {
  state.data.plots.push(plot);
  state.data.selection = [...new Set([...state.data.selection, plot.id])];
  save();
  return plot;
}

export function removePlot(id) {
  state.data.plots = state.data.plots.filter(p => p.id !== id);
  state.data.selection = state.data.selection.filter(s => s !== id);
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
  // Nobody has to name a destination to use it. Once it is located it appears
  // on route cards, in the comparison and on the map, and what the geocoder
  // matched is a real name for it — better than a placeholder everywhere.
  if (!(destination.name || "").trim() && destination.match) destination.name = destination.match;
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

/** A new destination arrives nameless: "Neues Ziel" is the suggestion in the
 *  empty field, not a value the user has to select and delete first. */
export function addDestination() {
  const destination = { id: newId("dest"), name: "", address: "" };
  state.data.destinations.push(destination);
  save();
  return destination;
}

/** What a destination without a name is called wherever it is shown. One
 *  decision in one place: an empty heading names nothing, and the field is
 *  allowed to be empty. */
export const UNNAMED_DESTINATION = "Ziel ohne Namen";

export const destinationName = destination =>
  (destination?.name || "").trim() || UNNAMED_DESTINATION;

export function removeDestination(id) {
  state.data.destinations = state.data.destinations.filter(d => d.id !== id);
  state.data.plots.forEach(p => { delete p.routes[id]; });
  save();
}
