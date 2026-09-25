/** Derived figures for a plot. Kept out of the components so the overview,
 *  the detail view and the comparison always agree on the same numbers. */
import { polygonArea, minimumRotatedRectangle, rectangularity, shapeClass, polygonEdges } from "./geometry.js";

/** Half the width of the band the price panel draws around the land value,
 *  as a fraction. The chip, the marker and the coloured line all read their
 *  stage off it, so they cannot disagree with the band they sit on. */
export const PRICE_BAND = 0.15;

/** "below", "within" or "above" the band, from a deviation in per cent; null
 *  when there is no deviation because there is no asking price. */
export function priceStage(deviation) {
  if (!Number.isFinite(deviation)) return null;
  if (deviation < -PRICE_BAND * 100) return "below";
  if (deviation > PRICE_BAND * 100) return "above";
  return "within";
}

export function plotMetrics(plot) {
  const computed = polygonArea(plot.polygon);
  const mrr = minimumRotatedRectangle(plot.polygon);
  const shape = rectangularity(plot.polygon);
  // A plot without an asking price has no price per square metre and no
  // deviation from the land value. Dividing anyway turns a missing figure into
  // "0,00 €" and "-100 %", which reads like a finding rather than a gap.
  const perSqm = Number.isFinite(plot.askingPrice) && plot.officialArea > 0
    ? plot.askingPrice / plot.officialArea
    : null;
  const deviation = perSqm !== null && Number.isFinite(plot.bodenrichtwert) && plot.bodenrichtwert > 0
    ? (perSqm / plot.bodenrichtwert - 1) * 100
    : null;
  return {
    computedArea: computed,
    mrr,
    rectangularity: shape,
    shapeClass: shapeClass(shape),
    /* The comparison is drawn against the official area, never the computed one:
       the two differ by a few square metres and only the official figure counts. */
    pricePerSqm: perSqm,
    deviation,
    priceStage: priceStage(deviation),
    /* The modifier of a `chip--…` CSS class, from the same three stages the
       plot page draws, so a card and the page it opens never disagree.
       "neutral" and "unknown" have no rule of their own: a plain chip. */
    deviationClass: { below: "good", within: "neutral", above: "error" }[priceStage(deviation)] ?? "unknown",
    /* The edge the plot itself calls its street front, not the one the ring
       happens to start with: a union of two parcels starts wherever the two
       outlines meet, and that was a 2,04 m stub reported as the frontage. */
    streetFrontage: (polygonEdges(plot.polygon)[plot.streetEdge ?? 0]
      ?? polygonEdges(plot.polygon)[0]).length
  };
}
