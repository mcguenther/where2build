/**
 * The one way a plot is drawn small — on a card, in the comparison, wherever a
 * plot is a picture rather than a workspace. Kept in one place so two lists
 * cannot drift into two drawings of the same plot.
 *
 * Turned to its street, with the street along the bottom, and with a ring of
 * the surroundings around it: the street and the neighbouring buildings, held
 * back in grey so the plot itself is the only coloured shape in the frame.
 */
import { fitScale, streetDownRotation, turnedBox } from "./geometry.js";
import { groundBlock } from "./tileGround.js";

/** Relative room on every side of the outline: enough for the neighbours to
 *  read as neighbours, little enough that the plot stays the subject. */
export const THUMBNAIL_PADDING = 0.4;

/** Pixel margin inside the frame, as the compact plan has always had. */
export const THUMBNAIL_MARGIN = 6;

/** The web atlas without its lettering: the street the plot is turned to, and
 *  the buildings either side. The ALKIS render was measured too and draws
 *  parcel numbers and boundary points at full size — at 300 pixels that is
 *  noise, and upside down whenever the street lies to the north. */
export const THUMBNAIL_GROUND = "umgebung";

/** The two frames a plot is drawn small in: its card in the list, and its
 *  column in the comparison. Named here so the drawing and the warm-up below
 *  cannot disagree about a pixel — a different frame is a different zoom and
 *  therefore a different block. */
export const CARD_FRAME = { width: 300, height: 196 };
export const COMPARE_FRAME = { width: 220, height: 280 };

/** How far the thumbnail of this plot is turned. */
export const thumbnailRotation = plot => streetDownRotation(plot.polygon, plot.streetEdge ?? 0);

/**
 * One scale for several thumbnails side by side: the smallest of their own
 * fits, so the largest plot still fits and a comparison does not lie about
 * size. Measured on the box each plot has once turned, as it is drawn.
 */
export function sharedThumbnailScale(plots, width, height) {
  if (!plots.length) return null;
  return Math.min(...plots.map(plot =>
    fitScale(plot.polygon, width, height, THUMBNAIL_MARGIN, THUMBNAIL_PADDING, thumbnailRotation(plot))));
}

/**
 * The projection a thumbnail is drawn with: the plot's turned box centred and
 * fitted, or held to a scale shared with its neighbours. The same arithmetic
 * `SitePlan` runs for a compact plan with this padding, restated so the tiles
 * can be known without mounting one.
 */
export function thumbnailView(plot, width, height, scale = null) {
  const rotation = thumbnailRotation(plot);
  const { centre } = turnedBox(plot.polygon, rotation);
  const fitted = Number.isFinite(scale) && scale > 0
    ? scale
    : fitScale(plot.polygon, width, height, THUMBNAIL_MARGIN, THUMBNAIL_PADDING, rotation);
  return { scale: fitted, mx: centre.x, my: centre.y };
}

/** The ground image the thumbnail of this plot draws, placed as it places
 *  it, or `null`. */
export function thumbnailGround(plot, { width, height }, scale = null) {
  if (!plot?.anchor || !(plot.polygon?.length >= 3)) return null;
  return groundBlock(plot.anchor, thumbnailView(plot, width, height, scale), width, height, THUMBNAIL_GROUND);
}

/**
 * Every ground block the list and the comparison will want for these plots:
 * each card at its own fit, and the ones ticked for comparison at the scale
 * they will share there. A freshly created plot is otherwise first drawn with
 * its ground still to be fetched from the GeoSN, at a second or more per tile.
 * As the backend is told about them: see `warmBlocks`.
 */
export function wantedThumbnailGrounds(plots, selection = []) {
  const wanted = new Map();
  const add = ground => { if (ground) wanted.set(ground.href, ground.ref); };
  for (const plot of plots) add(thumbnailGround(plot, CARD_FRAME));
  // Outlines only: this runs on every page, and a plot without one must not
  // take the shell down with it.
  const compared = plots.filter(plot => selection.includes(plot.id) && plot.polygon?.length >= 3);
  const shared = sharedThumbnailScale(compared, COMPARE_FRAME.width, COMPARE_FRAME.height);
  for (const plot of compared) add(thumbnailGround(plot, COMPARE_FRAME, shared));
  return [...wanted.values()];
}
