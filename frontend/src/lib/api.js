/**
 * Talks to the FastAPI backend.
 *
 * The backend proxies ALKIS, BORIS, MOTIS and the extraction model. When one of
 * them is unavailable this module **throws**; it never substitutes an example.
 * Showing invented figures next to cadastral ones is worse than showing nothing,
 * because nothing on screen distinguishes them afterwards.
 */

const BASIS = "/api";
const ZEITGRENZE = 180000;   // the extraction model fetches a page first

/** Error carrying the backend's own German explanation. */
export class DienstFehler extends Error {
  constructor(nachricht, status) {
    super(nachricht);
    this.name = "DienstFehler";
    this.status = status;
  }
}

async function hole(pfad, optionen = {}) {
  const abbruch = new AbortController();
  const uhr = setTimeout(() => abbruch.abort(), ZEITGRENZE);
  let antwort;
  try {
    antwort = await fetch(`${BASIS}${pfad}`, {
      headers: { "Content-Type": "application/json" },
      signal: abbruch.signal,
      ...optionen
    });
  } catch (fehler) {
    throw new DienstFehler(
      fehler?.name === "AbortError"
        ? "Der Dienst hat zu lange nicht geantwortet."
        : "Das Backend ist nicht erreichbar. Läuft der Server?",
      0
    );
  } finally {
    clearTimeout(uhr);
  }

  if (!antwort.ok) {
    const koerper = await antwort.json().catch(() => null);
    throw new DienstFehler(
      koerper?.detail || `Der Dienst antwortete mit HTTP ${antwort.status}.`,
      antwort.status
    );
  }
  return antwort.json();
}

export async function backendZustand() {
  try {
    return await hole("/health");
  } catch {
    return null;
  }
}

export const inseratLesen = url => hole("/listings/extract", { method: "POST", body: JSON.stringify({ url }) });
export const seiteLesen = text => hole("/listings/extract", { method: "POST", body: JSON.stringify({ text }) });
export const haustypLesen = url => hole("/housetypes/extract", { method: "POST", body: JSON.stringify({ url }) });

/** Address, coordinate, or Gemarkung plus the parcel number as written (`85/1`). */
export const flurstueckSuchen = eingabe =>
  hole("/parcels/resolve", { method: "POST", body: JSON.stringify(eingabe) });

export const bodenrichtwert = (lat, lon) =>
  hole(`/landvalue?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);

export const erreichbarkeit = (origin, destinations, modes) =>
  hole("/reachability", { method: "POST", body: JSON.stringify({ origin, destinations, modes }) });

/**
 * Address to coordinate, via the routing geocoder. Returns candidates, not an
 * answer: the same street name matches in Thüringen, Bayern and Burgenland, so
 * the user picks. A reference point pulls nearby matches to the front.
 */
export const geokodieren = (text, bezug) =>
  hole("/geocode", {
    method: "POST",
    body: JSON.stringify(bezug ? { text, lat: bezug.lat, lon: bezug.lon } : { text })
  });
