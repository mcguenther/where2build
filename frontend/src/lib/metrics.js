/** Derived figures for a plot. Kept out of the components so the overview,
 *  the detail view and the comparison always agree on the same numbers. */
import { polygonArea, minimumRotatedRectangle, rectangularity, shapeClass, polygonEdges } from "./geometry.js";

export function plotMetrics(plot) {
  const gerechnet = polygonArea(plot.polygon);
  const mrr = minimumRotatedRectangle(plot.polygon);
  const form = rectangularity(plot.polygon);
  // A plot without an asking price has no price per square metre and no
  // deviation from the land value. Dividing anyway turns a missing figure into
  // "0,00 €" and "-100 %", which reads like a finding rather than a gap.
  const jeQm = Number.isFinite(plot.kaufpreis) && plot.flaecheAmtlich > 0
    ? plot.kaufpreis / plot.flaecheAmtlich
    : null;
  const abweichung = jeQm !== null && Number.isFinite(plot.bodenrichtwert) && plot.bodenrichtwert > 0
    ? (jeQm / plot.bodenrichtwert - 1) * 100
    : null;
  return {
    flaecheGerechnet: gerechnet,
    mrr,
    rechteckigkeit: form,
    formklasse: shapeClass(form),
    /* The comparison is drawn against the official area, never the computed one:
       the two differ by a few square metres and only the official figure counts. */
    jeQuadratmeter: jeQm,
    abweichung,
    abweichungKlasse: abweichung === null
      ? "unbekannt"
      : Math.abs(abweichung) <= 5 ? "gut" : abweichung > 15 ? "fehler" : "warn",
    strassenfront: polygonEdges(plot.polygon)[0].length
  };
}
