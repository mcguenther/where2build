/**
 * Raster tiles as the ground under a drawing in local metres, and a way to have
 * the backend fetch them before the drawing exists.
 *
 * The layout lives here rather than in `SitePlan` so that whatever warms the
 * cache names exactly the tiles the drawing will ask for — warming almost the
 * same tiles is warming none of them.
 */
import { metresPerDegreeLon } from "./projection.js";
import { tileCover, tileUrl } from "./routes.js";
import { warmTilesOnServer } from "./api.js";

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
    x: tile.left - padX, y: tile.top - padY, size: tile.size + 0.6,
    // What /api/tiles/warm is told: the same tile as the href, as data.
    ref: { ebene: layer, z: tile.z, x: tile.x, y: tile.y }
  }));
}

/** The most one warm-up request may name; the backend's own ceiling. */
export const MAX_WARM_TILES = 400;

const refKey = ref => `${ref.ebene}/${ref.z}/${ref.x}/${ref.y}`;

/* Named to the backend once per page life. What it already has costs it a
 * look at the disk, but a list redrawn on every keystroke need not ask. */
const announced = new Set();

/**
 * Have the backend fetch tiles nobody is looking at yet into its disk cache,
 * so that when a drawing does ask, the answer is ready there — whichever
 * browser asks, and whether or not this page is still open by then. The
 * browser downloads nothing: it names the tiles and the backend answers at
 * once, fetching after it has answered.
 *
 * A failed request is forgotten rather than reported: nothing on screen waits
 * for it, and a tile that did not warm is fetched when it is drawn, as it
 * always was. Forgotten also means the next change asks again.
 */
export async function warmTiles(refs, send = warmTilesOnServer) {
  const fresh = [];
  for (const ref of refs) {
    const key = refKey(ref);
    if (announced.has(key)) continue;
    announced.add(key);
    fresh.push(ref);
  }
  for (let i = 0; i < fresh.length; i += MAX_WARM_TILES) {
    const batch = fresh.slice(i, i + MAX_WARM_TILES);
    try {
      await send(batch);
    } catch {
      batch.forEach(ref => announced.delete(refKey(ref)));
    }
  }
  return fresh.length;
}

/** Forget what was named. Tests only: a page never needs to. */
export function resetWarmTiles() {
  announced.clear();
}
