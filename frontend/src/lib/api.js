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

/** Error carrying the backend's own German explanation, and the body it came
 *  with: a 409 from the store holds the stand that is on the server, and the
 *  interface cannot show a conflict without it. */
export class ServiceError extends Error {
  constructor(message, status, body = null) {
    super(message);
    this.name = "ServiceError";
    this.status = status;
    this.body = body;
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
      response.status,
      body
    );
  }
  // An endpoint that answers "done" and nothing else sends 204; asking that
  // for JSON throws on an empty body.
  if (response.status === 204) return null;
  return response.json();
}

export async function backendHealth() {
  try {
    return await request("/health");
  } catch {
    return null;
  }
}

/**
 * Who is signed in, and whether signing in exists here at all.
 *
 * Three states, not two: without a configured provider the backend answers
 * `eingerichtet: false`, and then the app is what it has always been, a thing
 * that keeps its work in this browser. An unreachable backend reads the same
 * way, because that is what it means for the person in front of it.
 */
export async function authState() {
  try {
    return await request("/auth/me");
  } catch {
    return { eingerichtet: false, angemeldet: false, name: null, kennung: null, verwalter: false };
  }
}

/**
 * What this deployment currently says to everybody: a maintenance window, an
 * outage, anything the operator typed. Answers an empty, invisible
 * announcement when there is nothing to say, so a healthy deployment produces
 * no error in the console on every page load.
 */
export async function announcement() {
  try {
    return await request("/ansage");
  } catch {
    // A banner that cannot be fetched is not worth an error on the page it
    // would have sat on.
    return { text: "", art: "hinweis", sichtbar: false };
  }
}

/** Where to send the browser to sign in, coming back to where it started. */
export const signInUrl = (target = "/") => `${BASE}/auth/login?ziel=${encodeURIComponent(target)}`;

export const signOut = () => request("/auth/logout", { method: "POST" });

/* ---------- The account's copy of the document ----------
 * Only reachable while signed in; without a configured store the backend
 * answers 503 and the app stays what it is, a thing that keeps its work in
 * this browser. */
/** Everything held about the signed-in account. 404 means nothing is stored
 *  under this sign-in yet, which is a state and not a failure. */
export const accountOnServer = () => request("/account");
/** Erase the account and everything under it. The backend ends the session in
 *  the same answer, so whoever calls this has to reload who is signed in. */
export const deleteAccountOnServer = () => request("/account", { method: "DELETE" });

/* ---------- Sharing a plot by link ----------
 * Three of these need the account; `sharedPlot` deliberately does not, because
 * the token in the link is the access. */
export const createShare = (dokument, umfang) =>
  request("/shares", { method: "POST", body: JSON.stringify({ dokument, umfang }) });
export const sharesOnServer = () => request("/shares");
export const deleteShare = token => request(`/shares/${encodeURIComponent(token)}`, { method: "DELETE" });
export const sharedPlot = token => request(`/shares/${encodeURIComponent(token)}`);

/* ---------- The administration area ----------
 * Every one of these answers 403 for somebody who is not an administrator, so
 * the interface may draw the way in from `authState().verwalter` and still not
 * be what grants anything. 503 means this deployment has no database: the
 * statistics need one, the error list deliberately does not.
 *
 * The period is passed as two ISO moments rather than as "last week", because
 * the picker offers a free range and a server that parsed „letzte Woche" would
 * have to agree with the browser about where the week starts. */
const period = (von, bis) =>
  `?von=${encodeURIComponent(von.toISOString())}&bis=${encodeURIComponent(bis.toISOString())}`;

/** A page, as every list in the administration area asks for one. */
const page = ({ limit = 25, offset = 0, suche = "" } = {}) =>
  `limit=${limit}&offset=${offset}${suche ? `&suche=${encodeURIComponent(suche)}` : ""}`;

export const adminOverview = () => request("/verwaltung/uebersicht");
export const adminStatistics = (von, bis, raster = "stunde", vergleich = false) =>
  request(`/verwaltung/statistik${period(von, bis)}&raster=${raster}&vergleich=${vergleich}`);
export const adminAccounts = (von, bis, options = {}) =>
  request(
    `/verwaltung/konten${period(von, bis)}&${page(options)}` +
      `&sortierung=${options.sortierung || "anfragen"}`
  );
/** The whole record of one account, for the Auskunft somebody is entitled to.
 *  A link rather than a fetch, so the browser saves it under the name the
 *  server sends. */
export const adminRecordUrl = kennung =>
  `${BASE}/verwaltung/konten/${encodeURIComponent(kennung)}/auskunft`;
export const adminSetRole = (kennung, ist_admin) =>
  request(`/verwaltung/konten/${encodeURIComponent(kennung)}/rolle`, {
    method: "POST",
    body: JSON.stringify({ ist_admin })
  });
export const adminBlock = (kennung, minuten, grund) =>
  request(`/verwaltung/konten/${encodeURIComponent(kennung)}/sperre`, {
    method: "POST",
    body: JSON.stringify({ minuten, grund })
  });
export const adminUnblock = kennung =>
  request(`/verwaltung/konten/${encodeURIComponent(kennung)}/sperre`, { method: "DELETE" });
export const adminDeleteAccount = kennung =>
  request(`/verwaltung/konten/${encodeURIComponent(kennung)}`, { method: "DELETE" });
export const adminErrors = (von, bis, options = {}) =>
  request(`/verwaltung/fehler${period(von, bis)}&${page(options)}`);
/** The download is a plain link, not a fetch: the browser saves it under the
 *  name the Content-Disposition carries, and a blob built here would not. */
export const adminErrorDownloadUrl = (von, bis) => `${BASE}/verwaltung/fehler.ndjson${period(von, bis)}`;
export const adminShares = (options = {}) => request(`/verwaltung/freigaben?${page(options)}`);
export const adminDeleteShare = token =>
  request(`/verwaltung/freigaben/${encodeURIComponent(token)}`, { method: "DELETE" });
export const adminSweepShares = () => request("/verwaltung/freigaben/aufraeumen", { method: "POST" });
export const adminServices = () => request("/verwaltung/dienste");
export const adminClearCache = name =>
  request("/verwaltung/cache/leeren", { method: "POST", body: JSON.stringify({ name }) });
export const adminAudit = (options = {}) => request(`/verwaltung/protokoll?${page(options)}`);
export const adminJobs = () => request("/verwaltung/jobs");
export const adminStartJob = name =>
  request(`/verwaltung/jobs/${encodeURIComponent(name)}/starten`, { method: "POST" });
/** The banner, as the operator sees it — including while it is switched off. */
export const adminAnnouncement = () => request("/verwaltung/ansage");
export const putAnnouncement = ansage =>
  request("/verwaltung/ansage", { method: "PUT", body: JSON.stringify(ansage) });
export const adminPrepareWipe = () => request("/verwaltung/datenbank/vorbereiten", { method: "POST" });
export const adminWipe = (schluessel, bestaetigung, umfang) =>
  request("/verwaltung/datenbank/leeren", {
    method: "POST",
    body: JSON.stringify({ schluessel, bestaetigung, umfang })
  });

export const plotsOnServer = () => request("/plots");

/** Tiles the backend should fetch into its cache before anything draws them. */
export const warmTilesOnServer = kacheln =>
  request("/tiles/warm", { method: "POST", body: JSON.stringify({ kacheln }) });
export const putPlot = (id, dokument, geaendert_am) =>
  request(`/plots/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ dokument, geaendert_am })
  });
export const deletePlotOnServer = id =>
  request(`/plots/${encodeURIComponent(id)}`, { method: "DELETE" });
export const settingsOnServer = () => request("/settings");
export const putSettings = (dokument, geaendert_am) =>
  request("/settings", { method: "PUT", body: JSON.stringify({ dokument, geaendert_am }) });

export const readListing = url => request("/listings/extract", { method: "POST", body: JSON.stringify({ url }) });
/** How much page content travels to the reader, capped in one place.
 *
 *  Raised from 400 000 when the bookmarklet arrived: that hands over
 *  `document.documentElement.outerHTML`, and a portal exposé runs past a
 *  megabyte. The old cap came with the assumption that everything the
 *  extraction wants sits in the first part of the document, which is not true
 *  of a whole one -- JSON-LD is routinely the last thing in the body. The
 *  endpoint's own `max_length` is the same number, and nginx needs a
 *  `client_max_body_size` above it.
 *
 *  Cut here rather than at each caller: two callers hand a page over -- the
 *  paste field and the bookmarklet -- and a cap one of them forgets is a 422
 *  with a German sentence about a length nobody typed. */
export const PAGE_LIMIT = 3000000;
export const readPage = text =>
  request("/listings/extract", { method: "POST", body: JSON.stringify({ text: String(text).slice(0, PAGE_LIMIT) }) });
export const readHouseType = url => request("/housetypes/extract", { method: "POST", body: JSON.stringify({ url }) });

/** Address, coordinate, or Gemarkung plus the parcel number as written (`85/1`). */
export const resolveParcel = query =>
  request("/parcels/resolve", { method: "POST", body: JSON.stringify(query) });

/**
 * The parcels around a coordinate, for the user to choose between.
 *
 * `resolveParcel` answers with *the* plot; this answers with the candidates.
 * An address coordinate is not a parcel boundary — the register puts it on the
 * building, and a few metres either way is the neighbour's — so the choice is
 * shown rather than made.
 */
export const nearbyParcels = (lat, lon, umkreis_m = 60) =>
  request("/parcels/nearby", { method: "POST", body: JSON.stringify({ lat, lon, umkreis_m }) });

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

/* The street, way and square parcels in a box around a plot, which its street
 * front is measured against — see lib/streetFront.js. */
export const streetParcels = (lat, lon, umkreis_m) =>
  request("/parcels/streets", { method: "POST", body: JSON.stringify({ lat, lon, umkreis_m }) });

/* Mapped building outlines around a plot, for the neighbour hint. One question
 * per plot, and the backend caches the answer for a month — an outline moves
 * about as often as the house it belongs to. */
export const neighbourBuildings = (lat, lon, umkreis_m = 80) =>
  request("/neighbours", {
    method: "POST",
    body: JSON.stringify({ origin: { lat, lon }, umkreis_m })
  });

/**
 * The environmental record of one parcel: noise, water protection, protected
 * areas, flood, radon, slope, ground and air.
 *
 * Takes the outline, not a point, because that is the question — a plot
 * straddles isophones and zone boundaries, and its centre answers for one
 * square metre of it. `ring` is `[lon, lat]` pairs in WGS84; `toWgs84` in
 * `projection.js` turns a stored plot into one.
 *
 * Each check in the answer carries either data or its own `fehler`: a service
 * that is down costs one row, not the page.
 */
export const siteChecks = ring =>
  request("/site-checks", { method: "POST", body: JSON.stringify({ ring }) });

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
