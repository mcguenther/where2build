/**
 * Maps the backend's house-type extraction onto the catalogue entry.
 *
 * The distinction that matters: `bebaute_flaeche_m2` is the footprint,
 * `wohnflaeche_gesamt_m2` is living space across all storeys. Manufacturers
 * advertise the second; putting it on the map draws a house with nearly twice
 * the footprint. Only the first ever reaches the drawing.
 */
import { newId } from "./store.js";

export function houseTypeFromResponse(response) {
  const field = name => response?.felder?.[name]?.wert ?? null;
  const builtArea = field("bebaute_flaeche_m2");
  if (!Number.isFinite(builtArea)) {
    throw new Error("Auf der Seite stand keine bebaute Fläche. Bitte die Maße von Hand eintragen.");
  }
  const length = field("aussenmass_laenge_m");
  const width = field("aussenmass_breite_m");
  const roofShapes = field("dachformen");

  return {
    id: newId("house"),
    manufacturer: field("hersteller") || "unbekannt",
    name: field("typenbezeichnung") || "ohne Bezeichnung",
    builtArea,
    livingArea: field("wohnflaeche_gesamt_m2"),
    livingAreaGround: field("wohnflaeche_eg_m2"),
    livingAreaUpper: field("wohnflaeche_og_m2"),
    length,
    width,
    roofShape: Array.isArray(roofShapes) && roofShapes.length
      ? roofShapes.map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(" oder ")
      : "—",
    priceFrom: field("preis_ab_eur"),
    minimumPlotArea: field("grundstueck_ab_m2"),
    eavesHeight: field("traufhoehe_m"),
    ridgeHeight: field("firsthoehe_m"),
    // Only meaningful when the data sheet gave no dimensions; the backend derives it.
    ratio: length && width ? length / width : 1.35,
    source: response?.quelle_url ?? null,
    readAt: (response?.gelesen_am ?? new Date().toISOString()).slice(0, 10),
    note: response?.hinweis ?? null,
    custom: false
  };
}
