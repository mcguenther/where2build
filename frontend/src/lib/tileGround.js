/**
 * Raster tiles as the ground under a drawing in local metres, and a way to ask
 * for them before the drawing exists.
 *
 * The layout lives here rather than in `SitePlan` so that whatever warms the
 * cache computes exactly the URLs the drawing will ask for — a prefetch of
 * almost the same tiles is a prefetch of none of them.
 */
import { metresPerDegreeLon } from "./projection.js";
import { tileCover, tileUrl } from "./routes.js";

/**
 * Which tiles lie under a drawing, and where each goes in its rotated group.
 *
 * `view` is the drawing's projection: pixels per metre and the metre point at
 * the frame's centre. Local metres and Web Mercator share one scale factor
 * around the anchor, which is what makes this a linear map. The cover is asked
 * for the frame's diagonal on every side, since a turned drawing shows ground
 * from beyond the unturned frame's corners.
 */
export function groundTileLayout(anchor, view, width, height, layer) {
  if (!anchor || !(view?.scale > 0)) return [];
  const { lat, lon } = anchor;
  const radians = Math.PI / 180;
  const metresPerUnit = metresPerDegreeLon(lat) / radians;
  const scale = view.scale * metresPerUnit;
  const phi = lat * radians;
  const pad = Math.hypot(width, height) / 2;
  const padX = pad - width / 2, padY = pad - height / 2;
  const fit = {
    scale,
    dx: width / 2 - view.mx * view.scale - lon * radians * scale + padX,
    dy: height / 2 + view.my * view.scale
      + Math.log(Math.tan(Math.PI / 4 + phi / 2)) * scale + padY
  };
  const cover = tileCover(fit, 2 * pad, 2 * pad);
  if (!cover) return [];
  // A hair of overlap, or the antialiased tile edges draw a lattice.
  return cover.tiles.map(tile => ({
    key: tile.key, href: tileUrl(tile, layer),
    x: tile.left - padX, y: tile.top - padY, size: tile.size + 0.6
  }));
}

/* Asked for once per page life. The browser cache answers a repeat anyway; this
 * only saves building the request. */
const requested = new Set();
/* Held until they settle: an Image nobody references may be collected and its
 * request dropped with it. */
const inFlight = new Set();

/**
 * Ask for tiles nobody is looking at yet, so they are in the backend's disk
 * cache and the browser's own when a drawing does ask. Low priority, so a page
 * that is loading something the user is waiting for keeps its connections.
 */
export function prefetchTiles(urls) {
  if (typeof Image === "undefined") return 0;
  let started = 0;
  for (const url of urls) {
    if (requested.has(url)) continue;
    requested.add(url);
    const image = new Image();
    image.fetchPriority = "low";
    image.decoding = "async";
    const settle = () => inFlight.delete(image);
    image.onload = settle;
    // A failed tile may be asked for again by the drawing itself; no retry here.
    image.onerror = settle;
    inFlight.add(image);
    image.src = url;
    started += 1;
  }
  return started;
}

/** Forget what was asked for. Tests only: a page never needs to. */
export function resetPrefetch() {
  requested.clear();
  inFlight.clear();
}
