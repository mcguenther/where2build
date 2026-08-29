/** Derived figures for a plot. Kept out of the components so the overview,
 *  the detail view and the comparison always agree on the same numbers. */
import { polygonArea, minimumRotatedRectangle, rectangularity, shapeClass, polygonEdges } from "./geometry.js";

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
    // The value goes straight into a `chip--…` CSS class, which stays German.
    deviationClass: deviation === null
      ? "unbekannt"
      : Math.abs(deviation) <= 5 ? "gut" : deviation > 15 ? "fehler" : "warn",
    streetFrontage: polygonEdges(plot.polygon)[0].length
  };
}
