/**
 * Raster tiles as the ground under a drawing in local metres, fetched as one
 * composed image, and a way to have the backend build that image before the
 * drawing exists.
 *
 * The layout lives here rather than in `SitePlan` so that whatever warms the
 * cache names exactly the block the drawing will ask for — warming almost the
 * same block is warming none of it.
 */
import { metresPerDegreeLon } from "./projection.js";
import { tileCover } from "./routes.js";
import { warmBlocksOnServer } from "./api.js";

/** Where the backend serves a block of tiles as one image. */
export const blockUrl = ref =>
  `/api/tiles/${ref.ebene}/block/${ref.z}/${ref.west}/${ref.nord}/${ref.ost}/${ref.sued}.png`;

/**
 * The block of tiles under a drawing, as one image, and where it goes in its
 * rotated group — or `null` when there is no sensible cover.
 *
 * `view` is the drawing's projection: pixels per metre and the metre point at
 * the frame's centre. Local metres and Web Mercator share one scale factor
 * around the anchor, which is what makes this a linear map. The cover is asked
 * for the frame's diagonal on every side, since a turned drawing shows ground
 * from beyond the unturned frame's corners. One image has no seams, so it
 * needs none of the overlap separate tiles did.
 */
export function groundBlock(anchor, view, width, height, layer) {
  if (!anchor || !(view?.scale > 0)) return null;
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
  if (!cover?.tiles.length) return null;
  // `tileCover` lists column by column from the north-west corner.
  const first = cover.tiles[0], last = cover.tiles[cover.tiles.length - 1];
  const ref = { ebene: layer, z: cover.zoom, west: first.x, nord: first.y, ost: last.x, sued: last.y };
  return {
    href: blockUrl(ref),
    x: first.left - padX, y: first.top - padY,
    width: (last.x - first.x + 1) * cover.size,
    height: (last.y - first.y + 1) * cover.size,
    // What /api/tiles/warm is told: the same block as the href, as data.
    ref
  };
}

/** The most one warm-up request may name; the backend's own ceiling. */
export const MAX_WARM_BLOCKS = 100;

/* Named to the backend once per page life. What it already has costs it a
 * look at the disk, but a list redrawn on every keystroke need not ask. */
const announced = new Set();

/**
 * Have the backend compose grounds nobody is looking at yet into its disk
 * cache, so that when a drawing does ask, the finished image is ready there —
 * whichever browser asks, and whether or not this page is still open by then.
 * The browser downloads nothing: it names the blocks and the backend answers
 * at once, building after it has answered.
 *
 * A failed request is forgotten rather than reported: nothing on screen waits
 * for it, and a block that did not warm is built when it is drawn, as it
 * always was. Forgotten also means the next change asks again.
 */
export async function warmBlocks(refs, send = warmBlocksOnServer) {
  const fresh = [];
  for (const ref of refs) {
    const key = blockUrl(ref);
    if (announced.has(key)) continue;
    announced.add(key);
    fresh.push(ref);
  }
  for (let i = 0; i < fresh.length; i += MAX_WARM_BLOCKS) {
    const batch = fresh.slice(i, i + MAX_WARM_BLOCKS);
    try {
      await send(batch);
    } catch {
      batch.forEach(ref => announced.delete(blockUrl(ref)));
    }
  }
  return fresh.length;
}

/** Forget what was named. Tests only: a page never needs to. */
export function resetWarmBlocks() {
  announced.clear();
}
