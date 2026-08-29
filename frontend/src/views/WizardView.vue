<template>
  <div class="stapel">
    <nav class="krume" aria-label="Pfad">
      <button type="button" @click="cancel">Grundstücke</button>
      <span aria-hidden="true">›</span>
      <span>Grundstück hinzufügen</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Aufnahme</p>
        <h1>Grundstück hinzufügen</h1>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still" @click="cancel">Abbrechen</button>
    </div>

    <ol class="schrittleiste" aria-label="Schritte">
      <li v-for="(s, i) in steps" :key="s.id"
          :class="{ 'ist-hier': i === step, 'ist-fertig': i < step }"
          :aria-current="i === step ? 'step' : null">
        <span class="schrittleiste__zahl">{{ i < step ? "✓" : i + 1 }}</span>
        <span class="schrittleiste__name">{{ s.name }}</span>
      </li>
    </ol>

    <p v-if="error" class="band band--fehler" role="alert">{{ error }}</p>

    <!-- 1 · Quelle -->
    <section v-if="step === 0" class="stapel">
      <p class="unterzeile">Drei Wege hinein. Welcher passt zu dem, was vorliegt?</p>
      <div class="quellen">
        <label v-for="s in sources" :key="s.id" class="quelle" :class="{ 'quelle--gewaehlt': source === s.id }">
          <input type="radio" name="quelle" :value="s.id" v-model="source">
          <span class="quelle__name">{{ s.name }}</span>
          <span class="quelle__text">{{ s.text }}</span>
        </label>
      </div>

      <div class="tafel">
        <div class="tafel__leib stapel">
          <template v-if="source === 'url'">
            <div class="feld">
              <label for="q-url">Adresse der Anzeige</label>
              <input id="q-url" type="text" v-model="url" placeholder="https://…">
            </div>
            <p class="hinweis">
              Die Seite wird auf dem Server geholt und ausgelesen. ImmoScout24 lässt das
              nicht zu — dort den Weg über „Seite einfügen“ nehmen.
            </p>
          </template>

          <template v-else-if="source === 'parcel'">
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
              <textarea id="q-paste" v-model="pastedText"
                        placeholder="Strg+V — die kopierte Anzeigenseite"></textarea>
            </div>
          </template>

          <div class="reihe">
            <button type="button" class="knopf" :disabled="busy || !ready" @click="read">
              {{ busy ? "Wird gelesen …" : source === "parcel" ? "Nachschlagen" : "Lesen" }}
            </button>
            <span v-if="busy" class="hinweis">Der Abruf kann eine Minute dauern.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 2 · Gelesene Werte -->
    <section v-else-if="step === 1" class="stapel">
      <p class="unterzeile">
        Jedes Feld führt die Quelle mit, aus der es stammt. Erst nach Bestätigung wandern die
        Werte in die Planung — das Modell antwortet auch dann, wenn die Seite die Zahl gar nicht hergibt.
      </p>

      <div class="vorschlaege">
        <div v-for="f in readFields" :key="f.key" class="vorschlag" :class="{ 'vorschlag--leer': !f.value }">
          <span class="vorschlag__kopf">
            <span class="feldname">{{ f.label }}</span>
            <span class="vorschlag__marke">{{ f.value ? "automatisch gelesen" : "nicht belegt" }}</span>
          </span>
          <input type="text" v-model="f.value" :aria-label="f.label"
                 :placeholder="f.value ? '' : 'steht nicht auf der Seite'">
          <span class="vorschlag__quelle">{{ f.source }}</span>
        </div>
      </div>

      <div class="reihe">
        <button type="button" class="knopf" :disabled="busy" @click="lookUpParcel">
          {{ busy ? "Kataster wird abgefragt …" : "Flurstück nachschlagen" }}
        </button>
        <button type="button" class="knopf knopf--still" @click="step = 0">Zurück</button>
      </div>
    </section>

    <!-- 3 · Flurstück -->
    <section v-else-if="step === 2" class="stapel">
      <p class="unterzeile">
        So liegt das Flurstück im Kataster. Stimmt der Zuschnitt, geht es weiter;
        sonst zurück und die Angaben korrigieren.
      </p>
      <div class="pruefgitter">
        <div class="tafel">
          <SitePlan :plot="draft" :building="draftBuilding" :width="640" :height="440" backdrop="map" north-up />
        </div>
        <div class="tafel">
          <div class="tafel__kopf"><h3>Was übernommen wird</h3><div class="dehnen"></div><span class="chip">ALKIS</span></div>
          <dl class="werteliste">
            <dt>Gemarkung</dt><dd>{{ draft.gemarkung || "—" }}</dd>
            <dt>Flurstücke</dt><dd>{{ draft.flurstuecke.join(" · ") || "—" }}</dd>
            <dt>Lage</dt><dd>{{ draft.lagebezeichnung || "—" }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(draft.officialArea) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(computedArea, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ draft.polygon.length }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ draft.bodenrichtwert ? euroPerSqm(draft.bodenrichtwert) : "—" }}</dd>
          </dl>
          <p class="tafel__fussnote">{{ draft.source }}</p>
        </div>
      </div>
      <div class="reihe">
        <button type="button" class="knopf" @click="step = 3">Passt</button>
        <button type="button" class="knopf knopf--still" @click="step = returnStep">Zurück</button>
      </div>
    </section>

    <!-- 4 · Angaben -->
    <section v-else class="stapel">
      <div class="tafel">
        <div class="tafel__leib stapel">
          <div class="zwei">
            <div class="feld">
              <label for="q-name">Name in der Übersicht</label>
              <input id="q-name" type="text" v-model="draft.name">
            </div>
            <div class="feld">
              <label for="q-preis">Kaufpreis in Euro</label>
              <input id="q-preis" type="number" min="0" step="1000" v-model.number="draft.askingPrice"
                     placeholder="ohne Angabe kein €/m²-Vergleich">
            </div>
          </div>
          <div class="feld">
            <label for="q-notiz">Notiz</label>
            <input id="q-notiz" type="text" v-model="draft.note" placeholder="Optional — was auffiel">
          </div>
          <p v-if="!draft.bodenrichtwert" class="band">
            Für dieses Grundstück ließ sich kein Bodenrichtwert abrufen. Die Preiseinordnung
            bleibt dann leer; nachtragen lässt sie sich später.
          </p>
          <div class="reihe">
            <button type="button" class="knopf" @click="create">Anlegen und öffnen</button>
            <button type="button" class="knopf knopf--still" @click="step = 2">Zurück</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import { state, addPlot, placement } from "../lib/store.js";
import { readListing, readPage, resolveParcel, landValue } from "../lib/api.js";
import { plotFromCadastre } from "../lib/plots.js";
import { polygonArea } from "../lib/geometry.js";
import { area, euroPerSqm } from "../lib/format.js";

/** "212.000 €" and "1.104 m²" as a German listing writes them. */
function numberFrom(text) {
  if (text === null || text === undefined || text === "") return null;
  const match = String(text).replace(/\./g, "").replace(",", ".").match(/-?\d+(\.\d+)?/);
  return match ? parseFloat(match[0]) : null;
}

/** The backend answers with {feld: {wert, quelle_url, bestaetigt}}. */
function fieldsFromResponse(response) {
  const fields = response?.felder ?? {};
  const labels = {
    adresse: "Adresse", lat: "Breitengrad", lon: "Längengrad",
    flurstuecke: "Flurstücke", kaufpreis_eur: "Kaufpreis",
    grundstuecksflaeche_m2: "Grundstücksfläche"
  };
  return Object.entries(fields).map(([key, entry]) => ({
    key,
    label: labels[key] ?? key,
    value: Array.isArray(entry?.wert)
      ? entry.wert.map(v => (typeof v === "object" ? [v.zaehler, v.nenner].filter(Boolean).join("/") : v)).join(", ")
      : entry?.wert ?? "",
    source: entry?.quelle_url || response?.hinweis || "aus der gelesenen Seite"
  }));
}

export default {
  name: "WizardView",
  components: { SitePlan },
  data() {
    return {
      step: 0,
      returnStep: 0,
      source: "url",
      url: "",
      gemarkung: "",
      flurstuecksnummer: "",
      pastedText: "",
      busy: false,
      error: "",
      readFields: [],
      draft: null,
      steps: [
        { id: "source", name: "Quelle" },
        { id: "fields", name: "Gelesene Werte" },
        { id: "parcel", name: "Flurstück" },
        { id: "details", name: "Angaben" }
      ],
      sources: [
        { id: "url", name: "Link einwerfen",
          text: "Adresse einer Anzeige. Der Server holt die Seite und liest Adresse, Flurstück, Kaufpreis und Fläche heraus." },
        { id: "parcel", name: "Flurstück direkt",
          text: "Gemarkung und Flurstücksnummer, so wie sie im Geoportal stehen." },
        { id: "paste", name: "Seite einfügen",
          text: "Für Portale, die keinen Serverabruf zulassen. Die kopierte Anzeigenseite einfügen." }
      ]
    };
  },
  computed: {
    ready() {
      if (this.source === "url") return /^https?:\/\/\S{6,}/.test(this.url.trim());
      if (this.source === "parcel") return this.gemarkung.trim() && this.flurstuecksnummer.trim();
      return this.pastedText.trim().length > 20;
    },
    draftBuilding() { return this.draft ? placement(this.draft) : null; },
    computedArea() { return this.draft ? polygonArea(this.draft.polygon) : 0; }
  },
  methods: {
    area, euroPerSqm,
    cancel() { state.view = "plots"; window.scrollTo({ top: 0 }); },

    async read() {
      this.busy = true;
      this.error = "";
      try {
        if (this.source === "parcel") {
          this.returnStep = 0;
          await this.queryCadastre({
            gemarkung: this.gemarkung.trim(),
            flurstuecksnummer: this.flurstuecksnummer.trim()
          });
          return;
        }
        const response = this.source === "url"
          ? await readListing(this.url.trim())
          : await readPage(this.pastedText);
        this.readFields = fieldsFromResponse(response);
        this.returnStep = 1;
        this.step = 1;
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    /** Turn what was read into a cadastral query: coordinate first, else the parcel number. */
    async lookUpParcel() {
      const read = name => this.readFields.find(f => f.key === name)?.value;
      const lat = numberFrom(read("lat")), lon = numberFrom(read("lon"));
      const numbers = String(read("flurstuecke") ?? "").split(/[,;]/).map(s => s.trim()).filter(Boolean);

      let query = null;
      if (Number.isFinite(lat) && Number.isFinite(lon)) query = { lat, lon };
      else if (numbers.length) query = { gemarkung: this.gemarkung.trim() || undefined, flurstuecksnummer: numbers[0] };
      else if (read("adresse")) query = { address: read("adresse") };

      if (!query) {
        this.error = "Aus der Seite ließ sich weder eine Koordinate noch ein Flurstück lesen. "
          + "Bitte den Weg „Flurstück direkt“ nehmen.";
        return;
      }
      this.busy = true;
      this.error = "";
      try {
        await this.queryCadastre(query, {
          askingPrice: numberFrom(read("kaufpreis_eur")),
          note: read("adresse") ? `Aus der Anzeige: ${read("adresse")}` : ""
        });
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async queryCadastre(query, extra = {}) {
      const plot = plotFromCadastre(await resolveParcel(query), extra);
      // The land value is a separate register; a plot without one is still usable.
      try {
        const value = await landValue(plot.anchor.lat, plot.anchor.lon);
        plot.bodenrichtwert = value?.euro_per_sqm ?? null;
        plot.brwZone = value?.zone ?? null;
        plot.brwReferenceDate = value?.reference_date ?? null;
      } catch { /* leave it empty and say so on the next step */ }
      plot.houseTypeId = state.data.houseTypes[0]?.id ?? null;
      this.draft = plot;
      this.step = 2;
    },

    create() {
      const plot = addPlot(this.draft);
      state.openPlotId = plot.id;
      state.view = "plot";
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
