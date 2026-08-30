/**
 * Deep links into public map services.
 *
 * A drawn route is a claim. Until someone can open it somewhere else and see
 * the same thing, it stays a claim — so every route and every nearby place
 * carries a link out. OpenStreetMap comes first because that is where the
 * geometry and the walking network come from; Google is offered because it is
 * the one most people already have open.
 */

/** Our mode names, in each service's vocabulary. */
const OSRM_PROFILE = { car: "car", bike: "bike", transit: "car", walk: "foot" };
const GOOGLE_MODE = { car: "driving", bike: "bicycling", transit: "transit", walk: "walking" };

const coordinate = point => `${point.lat.toFixed(6)},${point.lon.toFixed(6)}`;

/**
 * OpenStreetMap's own routing page. It has no public transport engine, so a
 * transit route is offered by car — saying so is the caller's job.
 */
export function openStreetMapRoute(from, to, mode = "car") {
  const profile = OSRM_PROFILE[mode] ?? "car";
  const engine = profile === "foot" ? "fossgis_osrm_foot"
    : profile === "bike" ? "fossgis_osrm_bike" : "fossgis_osrm_car";
  const middle = [(from.lat + to.lat) / 2, (from.lon + to.lon) / 2];
  const span = Math.max(Math.abs(from.lat - to.lat), Math.abs(from.lon - to.lon), 0.002);
  // Rough zoom for the span, clamped to what the map will accept.
  const zoom = Math.max(9, Math.min(17, Math.round(Math.log2(360 / span)) - 1));
  return `https://www.openstreetmap.org/directions?engine=${engine}`
    + `&route=${coordinate(from)}%3B${coordinate(to)}`
    + `#map=${zoom}/${middle[0].toFixed(5)}/${middle[1].toFixed(5)}`;
}

export function googleMapsRoute(from, to, mode = "car") {
  const params = new URLSearchParams({
    api: "1",
    origin: coordinate(from),
    destination: coordinate(to),
    travelmode: GOOGLE_MODE[mode] ?? "driving"
  });
  return `https://www.google.com/maps/dir/?${params}`;
}

/** True when the service can actually answer for this mode. */
export const routableOnOpenStreetMap = mode => mode !== "transit";
