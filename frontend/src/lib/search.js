/**
 * Reading the parcel search as it runs.
 *
 * The endpoint answers NDJSON over a chunked POST: one JSON object per line,
 * written as soon as it is known. The map has to grow while the search is
 * going, and a search that shows nothing for two minutes is a search nobody
 * trusts.
 *
 * Not Server-Sent Events: `EventSource` can only GET, so the indicia would
 * have to be filed on the server under an id and fetched back — job state, in a
 * backend that deliberately has no database to clean it up with.
 *
 * A line may still arrive after the answer: the last one carries the verdict,
 * and a stream that simply stops is a failure this module reports rather than
 * hides.
 */

import { ServiceError } from "./api.js";

const ENDPOINT = "/api/parcels/search";

/** Split a growing buffer into whole lines, keeping the unfinished tail. */
export function splitLines(buffer) {
  const parts = buffer.split("\n");
  return { lines: parts.slice(0, -1).filter(line => line.trim()), rest: parts[parts.length - 1] };
}

/**
 * Run a search, calling `onEvent` for every line as it arrives.
 *
 * Resolves with the closing `ergebnis` event. Throws a `ServiceError` carrying
 * the backend's own German sentence — the same contract as `api.js`, so a
 * caller handles both the same way.
 */
export async function runSearch(query, onEvent, { signal } = {}) {
  let response;
  try {
    response = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(query),
      signal
    });
  } catch (error) {
    throw new ServiceError(
      error?.name === "AbortError"
        ? "Die Suche wurde abgebrochen."
        : "Das Backend ist nicht erreichbar. Läuft der Server?",
      0
    );
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ServiceError(
      body?.detail || `Die Suche antwortete mit HTTP ${response.status}.`,
      response.status
    );
  }

  let last = null;
  const handle = line => {
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      // One unreadable line is not a reason to throw away a whole run.
      return;
    }
    if (event.art === "fehler") throw new ServiceError(event.text, 502);
    if (event.art === "ergebnis") last = event;
    onEvent(event);
  };

  // `body.getReader()` is what makes this a stream. Some environments (jsdom,
  // an old Safari) hand back a response without one; there the whole text
  // arrives at once, which is slower to appear but never wrong.
  if (!response.body?.getReader) {
    const text = await response.text();
    text.split("\n").filter(line => line.trim()).forEach(handle);
    return last;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { lines, rest } = splitLines(buffer);
    buffer = rest;
    lines.forEach(handle);
  }
  if (buffer.trim()) handle(buffer);

  if (!last) {
    throw new ServiceError(
      "Die Suche hat kein Ergebnis geliefert — die Verbindung brach ab, bevor sie fertig war.",
      502
    );
  }
  return last;
}

/**
 * What the wizard's read fields become as a search query.
 *
 * Deliberately forgiving: everything is optional and the backend decides what
 * is worth a request. The one thing that must travel intact is the area *as
 * written*, because the tolerance staircase starts where the wording says.
 */
export function queryFromFields(fields, extra = {}) {
  const read = name => fields.find(field => field.key === name)?.value ?? "";
  const number = value => {
    const match = String(value).replace(/\./g, "").replace(",", ".").match(/-?\d+(\.\d+)?/);
    return match ? parseFloat(match[0]) : null;
  };
  const lat = number(read("lat"));
  const lon = number(read("lon"));
  const area = number(read("grundstuecksflaeche_m2"));
  const parcels = String(read("flurstuecke")).split(/[,;]/).map(s => s.trim()).filter(Boolean);

  return {
    ...(read("adresse") ? { adresse: read("adresse") } : {}),
    ...(Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : {}),
    ...(Number.isFinite(area) ? { flaeche_m2: area } : {}),
    ...(read("grundstuecksflaeche_m2") ? { flaeche_text: String(read("grundstuecksflaeche_m2")) } : {}),
    ...(parcels.length ? { flurstuecksnummer: parcels[0] } : {}),
    ...extra
  };
}

/** The German word for a verdict, for the heading above the map. */
export const STATUS_LABEL = {
  bestaetigt: "Bestätigt",
  mehrdeutig: "Mehrdeutig",
  erfolglos: "Nicht gefunden"
};

/**
 * The sentence under the heading. Composed from a template, never written by a
 * model — the same rule the findings follow, and for the same reason: the same
 * plot has to read the same way twice.
 */
export function verdictSentence(status, count, huelle) {
  if (status === "bestaetigt") {
    return `Ein Flurstück, und es hält den amtlichen Prüfungen stand. ${huelle?.text ?? ""}`.trim();
  }
  if (status === "mehrdeutig") {
    const plural = count === 1 ? "ein mögliches Flurstück" : `${count} mögliche Flurstücke`;
    return `Kein eindeutiges Ergebnis — ${plural}. ${huelle?.text ?? ""}`.trim();
  }
  return (
    huelle?.text && huelle.art !== "offen"
      ? `Kein Flurstück gefunden. Feststeht bisher: ${huelle.text}`
      : "Kein Flurstück gefunden. Die Angaben reichen nicht aus, um die Lage einzugrenzen."
  );
}
