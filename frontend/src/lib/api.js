/**
 * Talks to the FastAPI backend.
 *
 * The backend proxies ALKIS, BORIS, MOTIS and the extraction model. When one of
 * them is unavailable this module **throws**; it never substitutes an example.
 * Showing invented figures next to cadastral ones is worse than showing nothing,
 * because nothing on screen distinguishes them afterwards.
 */

const BASE = "/api";
const TIMEOUT_MS = 180000;   // the extraction model fetches a page first

/** Error carrying the backend's own German explanation. */
export class ServiceError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ServiceError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options
    });
  } catch (error) {
    throw new ServiceError(
      error?.name === "AbortError"
        ? "Der Dienst hat zu lange nicht geantwortet."
        : "Das Backend ist nicht erreichbar. Läuft der Server?",
      0
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ServiceError(
      body?.detail || `Der Dienst antwortete mit HTTP ${response.status}.`,
      response.status
    );
  }
  return response.json();
}

export async function backendHealth() {
  try {
    return await request("/health");
  } catch {
    return null;
  }
}

export const readListing = url => request("/listings/extract", { method: "POST", body: JSON.stringify({ url }) });
export const readPage = text => request("/listings/extract", { method: "POST", body: JSON.stringify({ text }) });
export const readHouseType = url => request("/housetypes/extract", { method: "POST", body: JSON.stringify({ url }) });

/** Address, coordinate, or Gemarkung plus the parcel number as written (`85/1`). */
export const resolveParcel = query =>
  request("/parcels/resolve", { method: "POST", body: JSON.stringify(query) });

/**
 * The directory of Saxon Gemarkungen — about 5 300 entries, some 250 kB.
 *
 * Fetched whole, once, and filtered in the browser: a request per keystroke
 * would be slower and no more correct, and the list changes about as often as
 * the cadastre is redrawn. The pending promise is the cache, so two fields
 * asking at the same moment share one request. A failure is not cached — the
 * next attempt tries the service again instead of remembering the outage.
 */
let directoryRequest = null;
export function cadastralDistricts() {
  if (!directoryRequest) {
    directoryRequest = request("/gemarkungen").catch(error => {
      directoryRequest = null;
      throw error;
    });
  }
  return directoryRequest;
}

/* Mapped building outlines around a plot, for the neighbour hint. One question
 * per plot, and the backend caches the answer for a month — an outline moves
 * about as often as the house it belongs to. */
export const neighbourBuildings = (lat, lon, umkreis_m = 80) =>
  request("/neighbours", {
    method: "POST",
    body: JSON.stringify({ origin: { lat, lon }, umkreis_m })
  });

export const landValue = (lat, lon) =>
  request(`/landvalue?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);

export const reachability = (origin, destinations, modes) =>
  request("/reachability", { method: "POST", body: JSON.stringify({ origin, destinations, modes }) });

/**
 * Address to coordinate, via the routing geocoder. Returns candidates, not an
 * answer: the same street name matches in Thüringen, Bayern and Burgenland, so
 * the user picks. A reference point pulls nearby matches to the front.
 */
export const geocode = (text, near) =>
  request("/geocode", {
    method: "POST",
    body: JSON.stringify(near ? { text, lat: near.lat, lon: near.lon } : { text })
  });

/**
 * The nearest school, park, tram stop and so on, ranked by walking time —
 * never by air distance, which is misleading wherever a railway or a river
 * lies between. Categories the server has no data for come back marked as
 * such, so "not configured" never reads as "there is none nearby".
 */
export const nearby = (origin, options = {}) =>
  request("/nearby", { method: "POST", body: JSON.stringify({ origin, ...options }) });
