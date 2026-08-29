/** Derived figures for a plot. Kept out of the components so the overview,
 *  the detail view and the comparison always agree on the same numbers. */
import { polygonArea, minimumRotatedRectangle, rectangularity, shapeClass, polygonEdges } from "./geometry.js";

export function plotMetrics(plot) {
  const gerechnet = polygonArea(plot.polygon);
  const mrr = minimumRotatedRectangle(plot.polygon);
  const form = rectangularity(plot.polygon);
  const jeQm = plot.kaufpreis / plot.flaecheAmtlich;
  const abweichung = (jeQm / plot.bodenrichtwert - 1) * 100;
  return {
    flaecheGerechnet: gerechnet,
    mrr,
    rechteckigkeit: form,
    formklasse: shapeClass(form),
    /* The comparison is drawn against the official area, never the computed one:
       the two differ by a few square metres and only the official figure counts. */
    jeQuadratmeter: jeQm,
    abweichung,
    abweichungKlasse: Math.abs(abweichung) <= 5 ? "gut" : abweichung > 15 ? "fehler" : "warn",
    strassenfront: polygonEdges(plot.polygon)[0].length
  };
}
