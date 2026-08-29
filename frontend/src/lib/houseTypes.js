/**
 * Maps the backend's house-type extraction onto the catalogue entry.
 *
 * The distinction that matters: `bebaute_flaeche_m2` is the footprint,
 * `wohnflaeche_gesamt_m2` is living space across all storeys. Manufacturers
 * advertise the second; putting it on the map draws a house with nearly twice
 * the footprint. Only the first ever reaches the drawing.
 */
import { newId } from "./store.js";

export function haustypAusAntwort(antwort) {
  const wert = name => antwort?.felder?.[name]?.wert ?? null;
  const bebaut = wert("bebaute_flaeche_m2");
  if (!Number.isFinite(bebaut)) {
    throw new Error("Auf der Seite stand keine bebaute Fläche. Bitte die Maße von Hand eintragen.");
  }
  const laenge = wert("aussenmass_laenge_m");
  const breite = wert("aussenmass_breite_m");
  const dachformen = wert("dachformen");

  return {
    id: newId("ht"),
    hersteller: wert("hersteller") || "unbekannt",
    name: wert("typenbezeichnung") || "ohne Bezeichnung",
    bebauteFlaeche: bebaut,
    wohnflaeche: wert("wohnflaeche_gesamt_m2"),
    wohnflaecheEg: wert("wohnflaeche_eg_m2"),
    wohnflaecheOg: wert("wohnflaeche_og_m2"),
    laenge,
    breite,
    dachform: Array.isArray(dachformen) && dachformen.length
      ? dachformen.map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(" oder ")
      : "—",
    preisAb: wert("preis_ab_eur"),
    grundstueckAb: wert("grundstueck_ab_m2"),
    traufhoehe: wert("traufhoehe_m"),
    firsthoehe: wert("firsthoehe_m"),
    // Only meaningful when the data sheet gave no dimensions; the backend derives it.
    verhaeltnis: laenge && breite ? laenge / breite : 1.35,
    quelle: antwort?.quelle_url ?? null,
    gelesenAm: (antwort?.gelesen_am ?? new Date().toISOString()).slice(0, 10),
    hinweis: antwort?.hinweis ?? null,
    eigen: false
  };
}
