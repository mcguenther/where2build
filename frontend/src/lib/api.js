/**
 * Talks to the FastAPI backend.
 *
 * The backend proxies ALKIS, BORIS and the extraction model — none of which the
 * browser may call directly (no CORS on the authority services, and the API key
 * must not leave the server). When it is not running, every call falls back to
 * a worked example and flags itself as `simuliert`, so the interface can say so
 * instead of pretending the numbers came from somewhere.
 */

const BASIS = "/api";
const ZEITGRENZE = 20000;

async function hole(pfad, optionen = {}) {
  const abbruch = new AbortController();
  const uhr = setTimeout(() => abbruch.abort(), ZEITGRENZE);
  try {
    const antwort = await fetch(`${BASIS}${pfad}`, {
      headers: { "Content-Type": "application/json" },
      signal: abbruch.signal,
      ...optionen
    });
    if (!antwort.ok) {
      // The backend explains itself in German; pass that through rather than
      // replacing it with a status code the user cannot act on.
      const koerper = await antwort.json().catch(() => null);
      throw new Error(koerper?.detail || `Der Dienst antwortete mit HTTP ${antwort.status}.`);
    }
    return await antwort.json();
  } finally {
    clearTimeout(uhr);
  }
}

export async function backendErreichbar() {
  try {
    await hole("/health");
    return true;
  } catch {
    return false;
  }
}

/** A field the model proposed: value plus the source it came from, unconfirmed. */
const vorschlag = (feld, wert, quelle, bestaetigt = false) => ({ feld, wert, quelle, bestaetigt });

/** Why the worked example is showing. Network failure and a service that
 *  declined are different things, and the interface should say which. */
const grundFuer = fehler =>
  fehler?.name === "AbortError"
    ? "Der Abruf hat zu lange gedauert."
    : fehler?.message && !/^Failed to fetch$/.test(fehler.message)
      ? fehler.message
      : "Das Backend ist nicht erreichbar.";

const BEISPIEL_INSERAT = () => ({
  simuliert: true,
  name: "Sommerfelder Weg",
  ort: "04316 Leipzig-Baalsdorf",
  gemarkung: "Baalsdorf",
  felder: [
    vorschlag("Adresse", "Sommerfelder Weg, 04316 Leipzig", "og:title · kleinanzeigen.de", true),
    vorschlag("Koordinate", "51.34012, 12.48307", "og:latitude / og:longitude — kein Geocoding nötig", true),
    vorschlag("Flurstücke", "61/3, 61/4, 62", "Beschreibungstext: „drei Flurstücke, zusammen ca. 1.104 m²“"),
    vorschlag("Kaufpreis", "212.000 €", "Preisangabe im Kopfbereich der Anzeige"),
    vorschlag("Grundstücksfläche", "1.104 m²", "Beschreibungstext — durch ALKIS zu ersetzen"),
    vorschlag("Baujahr", "", "Kein Beleg gefunden — bleibt leer statt geraten", null)
  ]
});

const BEISPIEL_FLURSTUECK = (gemarkung, zaehler, nenner) => ({
  simuliert: true,
  name: `Gemarkung ${gemarkung} ${zaehler}${nenner ? "/" + nenner : ""}`,
  ort: `Gemarkung ${gemarkung}`,
  gemarkung,
  felder: [
    vorschlag("Kennzeichen", `143xxx__${String(zaehler).padStart(5, "0")}__${nenner || "_"}`,
      "Stored Query „Flurstücke anhand Kennzeichen“", true),
    vorschlag("Amtliche Fläche", "1.104 m²", "ALKIS-Attribut flaeche — maßgeblich für €/m²", true),
    vorschlag("Gemarkung", gemarkung, "ALKIS ave:Flurstueck", true),
    vorschlag("Kaufpreis", "", "Aus dem Kataster nicht ableitbar — bitte eintragen", null)
  ]
});

const BEISPIEL_EINGEFUEGT = () => ({
  simuliert: true,
  name: "Aus Einfügetext",
  ort: "04316 Leipzig-Baalsdorf",
  gemarkung: "Baalsdorf",
  felder: [
    vorschlag("Adresse", "Sommerfelder Weg, 04316 Leipzig", "clipboardData text/html"),
    vorschlag("Kaufpreis", "212.000 €", "Preiszeile im eingefügten Text"),
    vorschlag("Grundstücksfläche", "1.104 m²", "Eckdatentabelle im eingefügten Text"),
    vorschlag("Koordinate", "", "Im Einfügetext nicht enthalten — Geocoding über Hauskoordinaten", null)
  ]
});

const BEISPIEL_HAUSTYP = url => ({
  simuliert: true,
  hersteller: "Neu gelesen",
  name: "Bungalow 100",
  bebauteFlaeche: 112.4,
  wohnflaeche: 100.2,
  wohnflaecheEg: 100.2,
  wohnflaecheOg: null,
  laenge: null,
  breite: null,
  dachform: "Walmdach",
  preisAb: 298000,
  verhaeltnis: 1.35,
  quelle: url
});

export async function inseratLesen(url) {
  try {
    return { ...(await hole("/listings/extract", { method: "POST", body: JSON.stringify({ url }) })), simuliert: false };
  } catch (fehler) {
    return { ...BEISPIEL_INSERAT(), grund: grundFuer(fehler) };
  }
}

export async function seiteLesen(text) {
  try {
    return { ...(await hole("/listings/extract", { method: "POST", body: JSON.stringify({ text }) })), simuliert: false };
  } catch (fehler) {
    return { ...BEISPIEL_EINGEFUEGT(), grund: grundFuer(fehler) };
  }
}

export async function flurstueckSuchen(gemarkung, zaehler, nenner) {
  try {
    return {
      ...(await hole("/parcels/resolve", { method: "POST", body: JSON.stringify({ gemarkung, zaehler, nenner }) })),
      simuliert: false
    };
  } catch (fehler) {
    return { ...BEISPIEL_FLURSTUECK(gemarkung, zaehler, nenner), grund: grundFuer(fehler) };
  }
}

export async function haustypLesen(url) {
  try {
    return { ...(await hole("/housetypes/extract", { method: "POST", body: JSON.stringify({ url }) })), simuliert: false };
  } catch (fehler) {
    return { ...BEISPIEL_HAUSTYP(url), grund: grundFuer(fehler) };
  }
}
