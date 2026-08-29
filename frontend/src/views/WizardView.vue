<template>
  <div class="stapel">
    <nav class="krume" aria-label="Pfad">
      <button type="button" @click="abbrechen">Grundstücke</button>
      <span aria-hidden="true">›</span>
      <span>Grundstück hinzufügen</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Aufnahme</p>
        <h1>Grundstück hinzufügen</h1>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still" @click="abbrechen">Abbrechen</button>
    </div>

    <ol class="schrittleiste" aria-label="Schritte">
      <li v-for="(s, i) in schritte" :key="s.id"
          :class="{ 'ist-hier': i === schritt, 'ist-fertig': i < schritt }"
          :aria-current="i === schritt ? 'step' : null">
        <span class="schrittleiste__zahl">{{ i < schritt ? "✓" : i + 1 }}</span>
        <span class="schrittleiste__name">{{ s.name }}</span>
      </li>
    </ol>

    <p v-if="fehler" class="band band--fehler" role="alert">{{ fehler }}</p>

    <!-- 1 · Quelle -->
    <section v-if="schritt === 0" class="stapel">
      <p class="unterzeile">Drei Wege hinein. Welcher passt zu dem, was vorliegt?</p>
      <div class="quellen">
        <label v-for="q in quellen" :key="q.id" class="quelle" :class="{ 'quelle--gewaehlt': quelle === q.id }">
          <input type="radio" name="quelle" :value="q.id" v-model="quelle">
          <span class="quelle__name">{{ q.name }}</span>
          <span class="quelle__text">{{ q.text }}</span>
        </label>
      </div>

      <div class="tafel">
        <div class="tafel__leib stapel">
          <template v-if="quelle === 'url'">
            <div class="feld">
              <label for="q-url">Adresse der Anzeige</label>
              <input id="q-url" type="text" v-model="url" placeholder="https://…">
            </div>
            <p class="hinweis">
              Die Seite wird auf dem Server geholt und ausgelesen. ImmoScout24 lässt das
              nicht zu — dort den Weg über „Seite einfügen“ nehmen.
            </p>
          </template>

          <template v-else-if="quelle === 'flurstueck'">
            <div class="zwei">
              <div class="feld">
                <label for="q-gemarkung">Gemarkung</label>
                <input id="q-gemarkung" type="text" v-model="gemarkung" placeholder="Liebertwolkwitz">
              </div>
              <div class="feld">
                <label for="q-nummer">Flurstücksnummer</label>
                <input id="q-nummer" type="text" v-model="flurstuecksnummer" placeholder="85/1">
              </div>
            </div>
            <p class="hinweis">
              So, wie sie im Geoportal steht: <span class="daten">85/1</span>,
              <span class="daten">476</span> oder <span class="daten">41/e</span>.
              Der Nenner darf ein Buchstabe sein.
            </p>
          </template>

          <template v-else>
            <div class="feld">
              <label for="q-paste">Anzeige hier einfügen</label>
              <textarea id="q-paste" v-model="einfuegetext"
                        placeholder="Strg+V — die kopierte Anzeigenseite"></textarea>
            </div>
          </template>

          <div class="reihe">
            <button type="button" class="knopf" :disabled="laeuft || !bereit" @click="lesen">
              {{ laeuft ? "Wird gelesen …" : quelle === "flurstueck" ? "Nachschlagen" : "Lesen" }}
            </button>
            <span v-if="laeuft" class="hinweis">Der Abruf kann eine Minute dauern.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 2 · Gelesene Werte -->
    <section v-else-if="schritt === 1" class="stapel">
      <p class="unterzeile">
        Jedes Feld führt die Quelle mit, aus der es stammt. Erst nach Bestätigung wandern die
        Werte in die Planung — das Modell antwortet auch dann, wenn die Seite die Zahl gar nicht hergibt.
      </p>

      <div class="vorschlaege">
        <div v-for="f in gelesen" :key="f.feld" class="vorschlag" :class="{ 'vorschlag--leer': !f.wert }">
          <span class="vorschlag__kopf">
            <span class="feldname">{{ f.feld }}</span>
            <span class="vorschlag__marke">{{ f.wert ? "automatisch gelesen" : "nicht belegt" }}</span>
          </span>
          <input type="text" v-model="f.wert" :aria-label="f.feld"
                 :placeholder="f.wert ? '' : 'steht nicht auf der Seite'">
          <span class="vorschlag__quelle">{{ f.quelle }}</span>
        </div>
      </div>

      <div class="reihe">
        <button type="button" class="knopf" :disabled="laeuft" @click="flurstueckHolen">
          {{ laeuft ? "Kataster wird abgefragt …" : "Flurstück nachschlagen" }}
        </button>
        <button type="button" class="knopf knopf--still" @click="schritt = 0">Zurück</button>
      </div>
    </section>

    <!-- 3 · Flurstück -->
    <section v-else-if="schritt === 2" class="stapel">
      <p class="unterzeile">
        So liegt das Flurstück im Kataster. Stimmt der Zuschnitt, geht es weiter;
        sonst zurück und die Angaben korrigieren.
      </p>
      <div class="pruefgitter">
        <div class="tafel">
          <SitePlan :plot="entwurf" :koerper="entwurfKoerper" :breite="640" :hoehe="440" grund="karte" genordet />
        </div>
        <div class="tafel">
          <div class="tafel__kopf"><h3>Was übernommen wird</h3><div class="dehnen"></div><span class="chip">ALKIS</span></div>
          <dl class="werteliste">
            <dt>Gemarkung</dt><dd>{{ entwurf.gemarkung || "—" }}</dd>
            <dt>Flurstücke</dt><dd>{{ entwurf.flurstuecke.join(" · ") || "—" }}</dd>
            <dt>Lage</dt><dd>{{ entwurf.lagebezeichnung || "—" }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(entwurf.flaecheAmtlich) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(gerechneteFlaeche, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ entwurf.polygon.length }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ entwurf.bodenrichtwert ? euroPerSqm(entwurf.bodenrichtwert) : "—" }}</dd>
          </dl>
          <p class="tafel__fussnote">{{ entwurf.quelle }}</p>
        </div>
      </div>
      <div class="reihe">
        <button type="button" class="knopf" @click="schritt = 3">Passt</button>
        <button type="button" class="knopf knopf--still" @click="schritt = herkunftsschritt">Zurück</button>
      </div>
    </section>

    <!-- 4 · Angaben -->
    <section v-else class="stapel">
      <div class="tafel">
        <div class="tafel__leib stapel">
          <div class="zwei">
            <div class="feld">
              <label for="q-name">Name in der Übersicht</label>
              <input id="q-name" type="text" v-model="entwurf.name">
            </div>
            <div class="feld">
              <label for="q-preis">Kaufpreis in Euro</label>
              <input id="q-preis" type="number" min="0" step="1000" v-model.number="entwurf.kaufpreis"
                     placeholder="ohne Angabe kein €/m²-Vergleich">
            </div>
          </div>
          <div class="feld">
            <label for="q-notiz">Notiz</label>
            <input id="q-notiz" type="text" v-model="entwurf.notiz" placeholder="Optional — was auffiel">
          </div>
          <p v-if="!entwurf.bodenrichtwert" class="band">
            Für dieses Grundstück ließ sich kein Bodenrichtwert abrufen. Die Preiseinordnung
            bleibt dann leer; nachtragen lässt sie sich später.
          </p>
          <div class="reihe">
            <button type="button" class="knopf" @click="anlegen">Anlegen und öffnen</button>
            <button type="button" class="knopf knopf--still" @click="schritt = 2">Zurück</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import { state, addPlot, placement } from "../lib/store.js";
import { inseratLesen, seiteLesen, flurstueckSuchen, bodenrichtwert } from "../lib/api.js";
import { plotAusKataster } from "../lib/plots.js";
import { polygonArea } from "../lib/geometry.js";
import { area, euroPerSqm } from "../lib/format.js";

/** "212.000 €" and "1.104 m²" as a German listing writes them. */
function zahlAus(text) {
  if (text === null || text === undefined || text === "") return null;
  const treffer = String(text).replace(/\./g, "").replace(",", ".").match(/-?\d+(\.\d+)?/);
  return treffer ? parseFloat(treffer[0]) : null;
}

/** The backend answers with {feld: {wert, quelle_url, bestaetigt}}. */
function felderAusAntwort(antwort) {
  const felder = antwort?.felder ?? {};
  const beschriftung = {
    adresse: "Adresse", lat: "Breitengrad", lon: "Längengrad",
    flurstuecke: "Flurstücke", kaufpreis_eur: "Kaufpreis",
    grundstuecksflaeche_m2: "Grundstücksfläche"
  };
  return Object.entries(felder).map(([schluessel, eintrag]) => ({
    schluessel,
    feld: beschriftung[schluessel] ?? schluessel,
    wert: Array.isArray(eintrag?.wert)
      ? eintrag.wert.map(v => (typeof v === "object" ? [v.zaehler, v.nenner].filter(Boolean).join("/") : v)).join(", ")
      : eintrag?.wert ?? "",
    quelle: eintrag?.quelle_url || antwort?.hinweis || "aus der gelesenen Seite"
  }));
}

export default {
  name: "WizardView",
  components: { SitePlan },
  data() {
    return {
      schritt: 0,
      herkunftsschritt: 0,
      quelle: "url",
      url: "",
      gemarkung: "",
      flurstuecksnummer: "",
      einfuegetext: "",
      laeuft: false,
      fehler: "",
      gelesen: [],
      entwurf: null,
      schritte: [
        { id: "quelle", name: "Quelle" },
        { id: "werte", name: "Gelesene Werte" },
        { id: "flurstueck", name: "Flurstück" },
        { id: "angaben", name: "Angaben" }
      ],
      quellen: [
        { id: "url", name: "Link einwerfen",
          text: "Adresse einer Anzeige. Der Server holt die Seite und liest Adresse, Flurstück, Kaufpreis und Fläche heraus." },
        { id: "flurstueck", name: "Flurstück direkt",
          text: "Gemarkung und Flurstücksnummer, so wie sie im Geoportal stehen." },
        { id: "einfuegen", name: "Seite einfügen",
          text: "Für Portale, die keinen Serverabruf zulassen. Die kopierte Anzeigenseite einfügen." }
      ]
    };
  },
  computed: {
    bereit() {
      if (this.quelle === "url") return /^https?:\/\/\S{6,}/.test(this.url.trim());
      if (this.quelle === "flurstueck") return this.gemarkung.trim() && this.flurstuecksnummer.trim();
      return this.einfuegetext.trim().length > 20;
    },
    entwurfKoerper() { return this.entwurf ? placement(this.entwurf) : null; },
    gerechneteFlaeche() { return this.entwurf ? polygonArea(this.entwurf.polygon) : 0; }
  },
  methods: {
    area, euroPerSqm,
    abbrechen() { state.ansicht = "grundstuecke"; window.scrollTo({ top: 0 }); },

    async lesen() {
      this.laeuft = true;
      this.fehler = "";
      try {
        if (this.quelle === "flurstueck") {
          this.herkunftsschritt = 0;
          await this.katasterAbfragen({
            gemarkung: this.gemarkung.trim(),
            flurstuecksnummer: this.flurstuecksnummer.trim()
          });
          return;
        }
        const antwort = this.quelle === "url"
          ? await inseratLesen(this.url.trim())
          : await seiteLesen(this.einfuegetext);
        this.gelesen = felderAusAntwort(antwort);
        this.herkunftsschritt = 1;
        this.schritt = 1;
      } catch (fehler) {
        this.fehler = fehler.message;
      } finally {
        this.laeuft = false;
      }
    },

    /** Turn what was read into a cadastral query: coordinate first, else the parcel number. */
    async flurstueckHolen() {
      const wert = name => this.gelesen.find(f => f.schluessel === name)?.wert;
      const lat = zahlAus(wert("lat")), lon = zahlAus(wert("lon"));
      const nummern = String(wert("flurstuecke") ?? "").split(/[,;]/).map(s => s.trim()).filter(Boolean);

      let anfrage = null;
      if (Number.isFinite(lat) && Number.isFinite(lon)) anfrage = { lat, lon };
      else if (nummern.length) anfrage = { gemarkung: this.gemarkung.trim() || undefined, flurstuecksnummer: nummern[0] };
      else if (wert("adresse")) anfrage = { address: wert("adresse") };

      if (!anfrage) {
        this.fehler = "Aus der Seite ließ sich weder eine Koordinate noch ein Flurstück lesen. "
          + "Bitte den Weg „Flurstück direkt“ nehmen.";
        return;
      }
      this.laeuft = true;
      this.fehler = "";
      try {
        await this.katasterAbfragen(anfrage, {
          kaufpreis: zahlAus(wert("kaufpreis_eur")),
          notiz: wert("adresse") ? `Aus der Anzeige: ${wert("adresse")}` : ""
        });
      } catch (fehler) {
        this.fehler = fehler.message;
      } finally {
        this.laeuft = false;
      }
    },

    async katasterAbfragen(anfrage, zusatz = {}) {
      const antwort = await flurstueckSuchen(anfrage);
      const plot = plotAusKataster(antwort, zusatz);
      // The land value is a separate register; a plot without one is still usable.
      try {
        const brw = await bodenrichtwert(plot.anker.lat, plot.anker.lon);
        plot.bodenrichtwert = brw?.euro_per_sqm ?? null;
        plot.brwZone = brw?.zone ?? null;
        plot.brwStichtag = brw?.reference_date ?? null;
      } catch { /* leave it empty and say so on the next step */ }
      plot.haustypId = state.daten.haustypen[0]?.id ?? null;
      this.entwurf = plot;
      this.schritt = 2;
    },

    anlegen() {
      const plot = addPlot(this.entwurf);
      state.offenesGrundstueck = plot.id;
      state.ansicht = "grundstueck";
      window.scrollTo({ top: 0 });
    }
  }
};
</script>

<style scoped>
.krume{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.krume button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font: inherit; }
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.unterzeile{ color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 70ch; }
.hinweis{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }

.schrittleiste{ display: flex; gap: var(--w2b-raum-2); flex-wrap: wrap; list-style: none; margin: 0; padding: 0; }
.schrittleiste li{
  display: flex; align-items: center; gap: var(--w2b-raum-2);
  padding: 9px var(--w2b-raum-4) 9px 10px; border-radius: var(--w2b-radius-voll);
  border: 1px solid var(--w2b-linie); background: var(--w2b-flaeche);
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-s); color: var(--w2b-gedaempft);
}
.schrittleiste__zahl{
  display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
  background: var(--w2b-linie-zart); color: var(--w2b-graphit);
  font-family: var(--w2b-daten); font-size: var(--w2b-schrift-xs);
}
.schrittleiste .ist-hier{ border-color: var(--w2b-primaer); color: var(--w2b-tinte); }
.schrittleiste .ist-hier .schrittleiste__zahl{ background: var(--w2b-primaer); color: var(--w2b-primaer-auf); }
.schrittleiste .ist-fertig{ color: var(--w2b-primaer); border-color: var(--w2b-primaer-schleier); }
.schrittleiste .ist-fertig .schrittleiste__zahl{ background: var(--w2b-primaer-schleier); color: var(--w2b-primaer); }

.quellen{ display: grid; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr)); gap: var(--w2b-raum-3); }
.quelle{
  display: flex; flex-direction: column; gap: var(--w2b-raum-2); cursor: pointer;
  padding: var(--w2b-raum-4); border: 1.5px solid var(--w2b-linie); border-radius: var(--w2b-radius-m);
  background: var(--w2b-flaeche);
}
.quelle input{ position: absolute; opacity: 0; pointer-events: none; }
.quelle--gewaehlt{ border-color: var(--w2b-primaer); background: var(--w2b-primaer-schleier); }
.quelle__name{ font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-l); }
.quelle__text{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }

.zwei{ display: grid; grid-template-columns: 1fr 1fr; gap: var(--w2b-raum-3); }
@media (max-width: 560px){ .zwei{ grid-template-columns: 1fr; } }

.vorschlaege{ display: grid; grid-template-columns: repeat(auto-fill, minmax(244px, 1fr)); gap: var(--w2b-raum-3); }
.vorschlag{
  display: flex; flex-direction: column; gap: var(--w2b-raum-2);
  padding: var(--w2b-raum-3) var(--w2b-raum-4);
  border: 1.5px dashed var(--w2b-sekundaer); border-radius: var(--w2b-radius-m);
  background: var(--w2b-sekundaer-schleier);
}
.vorschlag--leer{ border-color: var(--w2b-fehler); background: var(--w2b-fehler-flaeche); }
.vorschlag__kopf{ display: flex; align-items: center; gap: var(--w2b-raum-2); flex-wrap: wrap; }
.vorschlag__marke{
  font-family: var(--w2b-daten); font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase;
  padding: 1px 7px; border-radius: var(--w2b-radius-voll);
  border: 1px solid var(--w2b-sekundaer-text); color: var(--w2b-sekundaer-text);
}
.vorschlag--leer .vorschlag__marke{ border-color: var(--w2b-fehler); color: var(--w2b-fehler); }
.vorschlag__quelle{ font-family: var(--w2b-daten); font-size: 10px; color: var(--w2b-gedaempft); overflow-wrap: anywhere; line-height: 1.45; }

.pruefgitter{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: var(--w2b-raum-4); align-items: start; }
@media (max-width: 900px){ .pruefgitter{ grid-template-columns: 1fr; } }
.werteliste{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.werteliste dt, .werteliste dd{ padding: 8px var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie-zart); margin: 0; display: flex; align-items: center; }
.werteliste dt{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.werteliste dd{ justify-content: flex-end; font-family: var(--w2b-daten); font-size: var(--w2b-schrift-s); font-variant-numeric: tabular-nums; text-align: right; }
.tafel__fussnote{ padding: var(--w2b-raum-3) var(--w2b-raum-4); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
</style>
