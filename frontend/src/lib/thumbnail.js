/**
 * The one way a plot is drawn small — on a card, in the comparison, wherever a
 * plot is a picture rather than a workspace. Kept in one place so two lists
 * cannot drift into two drawings of the same plot.
 *
 * Turned to its street, with the street along the bottom, and with a ring of
 * the surroundings around it: the street and the neighbouring buildings, held
 * back in grey so the plot itself is the only coloured shape in the frame.
 */
import { fitScale, streetDownRotation } from "./geometry.js";

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
