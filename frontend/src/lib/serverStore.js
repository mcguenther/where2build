/**
 * The account's copy of the document.
 *
 * `localStorage` stays what it always was and keeps working unchanged; this
 * module puts the same document on the server for whoever is signed in, so it
 * is there on the next machine. The browser copy is then a cache and the way
 * back out when the server is unreachable, which is why nothing here ever
 * deletes it.
 *
 * Two rules shape the rest:
 *
 *  - **Writes are collected.** Dragging a building calls `save()` per frame;
 *    one PUT per frame would be absurd and would lose to itself. Changes are
 *    gathered and sent once the hand comes to rest, and once more when the tab
 *    goes away.
 *  - **A conflict is shown, never resolved quietly.** The same rule the search
 *    follows. If the row moved on since this browser last read it, the backend
 *    answers 409 with what is stored, and that lands in `state.sync.conflicts`
 *    for the interface to put to the user. Nothing is overwritten on a guess.
 */
import { plotsOnServer, putPlot, deletePlotOnServer, settingsOnServer, putSettings } from "./api.js";

/** Long enough to swallow a drag, short enough that closing the tab right
 *  afterwards still finds the work saved by the unload flush. */
const QUIET_MS = 800;

/** What the server last confirmed, per plot id: the stand to write against and
 *  the text that stand carried, so an unchanged plot is not sent again. */
const known = new Map();
let settingsStand = null;
let settingsText = null;
let timer = null;

/** Set by `store.js`; kept as a callback so this module does not import the
 *  state and the state does not import a server. */
let report = () => {};
export function onReport(fn) { report = fn; }

const textOf = value => JSON.stringify(value);

/** Read the account's document. Returns null when there is nothing stored for
 *  it yet, which is what the adoption question hangs on. */
export async function pull() {
  const [plots, settings] = await Promise.all([plotsOnServer(), settingsOnServer()]);
  known.clear();
  for (const entry of plots.eintraege) {
    known.set(entry.id, { stand: entry.geaendert_am, text: textOf(entry.dokument) });
  }
  settingsStand = settings.geaendert_am;
  settingsText = settings.geaendert_am ? textOf(settings.dokument) : null;
  const empty = plots.eintraege.length === 0 && !settings.geaendert_am;
  return empty ? null : { plots: plots.eintraege.map(e => e.dokument), settings: settings.dokument };
}

/** Everything this browser holds, written as if the account were new. Used by
 *  the adoption step and nowhere else: it writes against `null`, so it refuses
 *  rather than overwrites if something is already there. */
export async function push(data) {
  for (const plot of data.plots) {
    const answer = await putPlot(plot.id, plot, null);
    known.set(plot.id, { stand: answer.geaendert_am, text: textOf(plot) });
  }
  const rest = restOf(data);
  const answer = await putSettings(rest, null);
  settingsStand = answer.geaendert_am;
  settingsText = textOf(rest);
}

/** The document minus the plots: house types, destinations, the selection. */
const restOf = data => ({
  version: data.version,
  houseTypes: data.houseTypes,
  destinations: data.destinations,
  selection: data.selection
});

/** Note that something changed. Cheap and idempotent: the writing happens once
 *  the calls stop coming. */
export function schedule(data) {
  clearTimeout(timer);
  timer = setTimeout(() => { flush(data); }, QUIET_MS);
}

/** Write what differs from what the server confirmed. */
export async function flush(data) {
  clearTimeout(timer);
  const conflicts = [];
  let wrote = false;
  report({ busy: true, error: "", conflicts: [] });
  try {
    for (const plot of data.plots) {
      const text = textOf(plot);
      const seen = known.get(plot.id);
      if (seen && seen.text === text) continue;
      try {
        const answer = await putPlot(plot.id, plot, seen ? seen.stand : null);
        known.set(plot.id, { stand: answer.geaendert_am, text });
        wrote = true;
      } catch (error) {
        if (error.status !== 409) throw error;
        conflicts.push({ id: plot.id, name: plot.name, aktuell: error.body?.aktuell ?? null });
      }
    }

    // A plot the browser no longer has is one that was removed here. The
    // server is told; a plot that never arrived is not invented back.
    for (const id of [...known.keys()]) {
      if (data.plots.some(plot => plot.id === id)) continue;
      await deletePlotOnServer(id);
      known.delete(id);
      wrote = true;
    }

    const rest = restOf(data);
    const text = textOf(rest);
    if (text !== settingsText) {
      try {
        const answer = await putSettings(rest, settingsStand);
        settingsStand = answer.geaendert_am;
        settingsText = text;
        wrote = true;
      } catch (error) {
        if (error.status !== 409) throw error;
        conflicts.push({ id: "settings", name: "Haustypen und Ziele", aktuell: error.body?.aktuell ?? null });
      }
    }
    report({ busy: false, error: "", conflicts, savedAt: wrote ? new Date().toISOString() : undefined });
  } catch (error) {
    // The message is the backend's own German sentence; nothing is invented
    // here, and the browser copy is untouched, so nothing is lost either.
    report({ busy: false, error: error.message || "Der Stand konnte nicht gespeichert werden.", conflicts });
  }
}

/** Forget what the server said. Called on sign-out: the next account starts
 *  from its own answer, not from this one's. */
export function forget() {
  clearTimeout(timer);
  known.clear();
  settingsStand = null;
  settingsText = null;
}
