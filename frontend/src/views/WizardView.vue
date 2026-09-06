<template>
  <div class="stack">
    <nav class="breadcrumb" aria-label="Pfad">
      <RouterLink :to="{ name: 'plots' }">Grundstücke</RouterLink>
      <span aria-hidden="true">›</span>
      <span>Grundstück hinzufügen</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Aufnahme</p>
        <h1>Grundstück hinzufügen</h1>
      </div>
      <div class="spacer"></div>
      <button type="button" class="btn btn--quiet" @click="$router.push({ name: 'plots' })">Abbrechen</button>
    </div>

    <ol class="steps" aria-label="Schritte">
      <li v-for="(s, i) in steps" :key="s.id"
          :class="{ 'is-current': i === stageIndex, 'is-done': i < stageIndex }"
          :aria-current="i === stageIndex ? 'step' : null">
        <span class="steps__number">{{ i < stageIndex ? "✓" : i + 1 }}</span>
        <span class="steps__name">{{ s.name }}</span>
      </li>
    </ol>

    <p v-if="lost" class="notice notice--error" role="alert">
      Der begonnene Entwurf ist nicht mehr vorhanden — beim Neuladen der Seite bleibt er
      nicht erhalten. Bitte noch einmal mit der Quelle beginnen.
    </p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <!-- 1 · Quelle. Also what a stage without its data falls back to, so the
         redirect in `checkStage` never renders a step that has nothing. -->
    <section v-if="stageIndex === 0 || !reachable" class="stack">
      <p class="subtitle">Vier Wege hinein. Welcher passt zu dem, was vorliegt?</p>
      <div class="sources">
        <label v-for="s in sources" :key="s.id" class="source" :class="{ 'source--selected': source === s.id }">
          <input type="radio" name="source" :value="s.id" v-model="source">
          <span class="source__name">{{ s.name }}</span>
          <span class="source__text">{{ s.text }}</span>
        </label>
      </div>

      <div class="panel">
        <div class="panel__body stack">
          <template v-if="source === 'search'">
            <PlotSearch @select="searchPicked" />
            <p class="hint">
              Was getippt wurde, wird zuerst gelesen und dann nachgeschlagen: eine deutsche
              Adresse beginnt nie mit einer Ziffer, eine Koordinate sind zwei Zahlen, und ein
              Nenner (<span class="mono">85/1</span>) kommt in keiner Adresse vor. Bleiben zwei
              Lesarten möglich, werden beide Verzeichnisse gefragt statt eine geraten.
            </p>
          </template>

          <template v-else-if="source === 'url'">
            <div class="field">
              <label for="q-url">Adresse der Anzeige</label>
              <input id="q-url" type="text" v-model="url" placeholder="https://…">
            </div>
            <p class="hint">
              Die Seite wird auf dem Server geholt und ausgelesen. ImmoScout24 lässt das
              nicht zu — dort den Weg über „Seite einfügen“ nehmen.
            </p>
          </template>

          <template v-else-if="source === 'parcel'">
            <div class="field-pair">
              <CadastralDistrictPicker v-model="gemarkung" @select="gemarkungEntry = $event" />
              <div class="field">
                <label for="q-parcel-number">Flurstücksnummer</label>
                <input id="q-parcel-number" type="text" v-model="flurstuecksnummer" placeholder="85/1">
              </div>
            </div>
            <p class="hint">
              <b>Gemarkung:</b> tippen und aus dem Verzeichnis wählen — der Name
              (<span class="mono">Moritzburg</span>) oder der Gemarkungsschlüssel, den die
              Sachdatenabfrage je nach Kartenebene vierstellig (<span class="mono">3044</span>)
              oder sechsstellig (<span class="mono">143044</span>) zeigt. Beides wird angenommen,
              auch ohne Eintrag im Verzeichnis.
              <br>
              <b>Flurstücksnummer:</b> so, wie sie im Geoportal steht —
              <span class="mono">85/1</span>, <span class="mono">476</span> oder
              <span class="mono">41/e</span>. Der Nenner darf ein Buchstabe sein.
            </p>
          </template>

          <template v-else>
            <div class="field">
              <label for="q-paste">Anzeige hier einfügen</label>
              <textarea id="q-paste" v-model="pastedText"
                        placeholder="Strg+V — die kopierte Anzeigenseite"></textarea>
            </div>
          </template>

          <div v-if="source !== 'search'" class="row">
            <button type="button" class="btn" :disabled="busy || !ready" @click="read">
              {{ busy ? "Wird gelesen …" : source === "parcel" ? "Nachschlagen" : "Lesen" }}
            </button>
            <span v-if="busy" class="hint">Der Abruf kann eine Minute dauern.</span>
          </div>
          <p v-else-if="busy" class="hint">Das Kataster wird gefragt …</p>
        </div>
      </div>
    </section>

    <!-- 2 · Gelesene Werte -->
    <section v-else-if="stageIndex === 1" class="stack">
      <p class="subtitle">
        Jedes Feld führt die Quelle mit, aus der es stammt. Erst nach Bestätigung wandern die
        Werte in die Planung — das Modell antwortet auch dann, wenn die Seite die Zahl gar nicht hergibt.
      </p>

      <div class="suggestions">
        <div v-for="f in readFields" :key="f.key" class="suggestion" :class="{ 'suggestion--empty': !f.value }">
          <span class="suggestion__head">
            <span class="field-label">{{ f.label }}</span>
            <span class="suggestion__tag">{{ f.value ? "automatisch gelesen" : "nicht belegt" }}</span>
          </span>
          <input type="text" v-model="f.value" :aria-label="f.label"
                 :placeholder="f.value ? '' : 'steht nicht auf der Seite'">
          <span class="suggestion__source">{{ f.source }}</span>
        </div>
      </div>

      <div class="row">
        <button type="button" class="btn" :disabled="busy" @click="lookUpParcel">
          {{ busy ? "Kataster wird abgefragt …" : "Flurstück nachschlagen" }}
        </button>
        <button type="button" class="btn btn--quiet" @click="stepBack(0)">Zurück</button>
      </div>
    </section>

    <!-- 3 · Grundstück: die Flurstücke und die Angaben dazu -->
    <section v-else class="stack">
      <p class="subtitle">
        So liegen die Flurstücke im Kataster. Ein Klick nimmt eines dazu oder wieder
        heraus — ein Grundstück kann aus mehreren bestehen. Den Ausschnitt bewegt die
        gedrückte Maustaste, das Mausrad zoomt, ein Doppelklick setzt ihn zurück.
      </p>

      <!-- The service found something implausible for this listing. Not an
           error — the parcel is real — but the user has to see it before the
           next click turns it into a plot they plan a house on. -->
      <div v-if="doubt" class="notice notice--error doubt-note">
        <b>Das ist vermutlich nicht das richtige Flurstück.</b>
        {{ doubt }}
      </div>

      <!-- An address coordinate is not a parcel boundary: the register puts it
           on the building, and a few metres either way is the neighbour's. So
           the neighbours are on the map and the choice is the user's. -->
      <p v-if="corrected" class="notice" role="status">
        <b>Zur gesuchten Adresse gehört ein anderes Flurstück als das unter der Koordinate.</b>
        Gewählt ist {{ corrected }} — die Lagebezeichnung im Kataster nennt genau diese
        Adresse. Ein Klick auf ein anderes Flurstück ändert das.
      </p>

      <div class="check-grid">
        <div class="panel">
          <!-- No house here: this step is about the parcel's outline, and a
               body nobody has planned yet only distracts from it. -->
          <!-- No dimension chains: the question here is which parcel, not how
               long each of its edges is, and the chains sat on the numbers of
               the neighbours they were meant to help pick between. The measures
               are in the table beside it. -->
          <!-- The photograph with the cadastre's line work over it: what is
               actually on the ground, and where the boundaries run. `hold-frame`
               keeps the camera still when another parcel is picked — the point
               of the click is to see which outline moved. -->
          <SitePlan :plot="draft" :width="640" :height="440" backdrop="aerial"
                    overlay="flurstuecke" north-up hold-frame
                    :show-building="false" :show-dimensions="false" navigable
                    :parcels="choices" :chosen-parcels="selection"
                    @choose="toggleParcel" />
          <p v-if="selectionNote" class="notice" role="status">{{ selectionNote }}</p>
          <p class="panel__footnote">
            <template v-if="choices.length > 1">
              {{ choices.length }} Flurstücke im Umkreis — die Katasterlinien beschriften
              jedes mit seiner Nummer, ein Klick nimmt es dazu oder heraus.
            </template>
            Luftbild und Kataster: © GeoSN, dl-de/by-2-0
          </p>
        </div>
        <div class="panel">
          <div class="panel__head"><h3>Was übernommen wird</h3><div class="spacer"></div><span class="chip">ALKIS</span></div>
          <dl class="value-list">
            <dt>Gemarkung</dt><dd>{{ draft.gemarkung || "—" }}</dd>
            <dt>Flurstücke</dt><dd>{{ draft.flurstuecke.join(" · ") || "—" }}</dd>
            <dt>Lage</dt><dd>{{ draft.lagebezeichnung || "—" }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(draft.officialArea) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(computedArea, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ draft.polygon.length }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ draft.bodenrichtwert ? euroPerSqm(draft.bodenrichtwert) : "—" }}</dd>
          </dl>
          <p class="panel__footnote">{{ draft.source }}</p>
        </div>
      </div>

      <!-- The fields that the cadastre cannot supply. They used to be a step of
           their own, which meant a second page for three inputs and a "Passt"
           in between that decided nothing. -->
      <div class="panel">
        <div class="panel__body stack">
          <div class="field-pair">
            <div class="field">
              <label for="q-name">Name in der Übersicht</label>
              <input id="q-name" type="text" v-model="draft.name">
            </div>
            <div class="field">
              <label for="q-price">Kaufpreis in Euro</label>
              <input id="q-price" type="number" min="0" step="1000" v-model.number="draft.askingPrice"
                     placeholder="ohne Angabe kein €/m²-Vergleich">
            </div>
          </div>
          <div class="field">
            <label for="q-note">Notiz</label>
            <input id="q-note" type="text" v-model="draft.note" placeholder="Optional — was auffiel">
          </div>
          <p v-if="!draft.bodenrichtwert" class="notice">
            Für dieses Grundstück ließ sich kein Bodenrichtwert abrufen. Die Preiseinordnung
            bleibt dann leer; nachtragen lässt sie sich später.
          </p>
          <div class="row">
            <button type="button" :class="doubt ? 'btn btn--secondary' : 'btn'"
                    :disabled="busy" @click="create">
              {{ doubt ? "Trotzdem anlegen" : "Anlegen und öffnen" }}
            </button>
            <button type="button" class="btn btn--quiet" @click="stepBack(returnStage)">Zurück</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import CadastralDistrictPicker from "../components/CadastralDistrictPicker.vue";
import PlotSearch from "../components/PlotSearch.vue";
import { state, addPlot, autoSeatHouse } from "../lib/store.js";
import { WIZARD_STAGES, wizardStage } from "../router/stages.js";
import { readListing, readPage, resolveParcel, landValue, nearbyParcels } from "../lib/api.js";
import { plotFromCadastre, parcelForAddress } from "../lib/plots.js";
import { polygonArea } from "../lib/geometry.js";
import { area, euroPerSqm, num } from "../lib/format.js";

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
  components: { SitePlan, CadastralDistrictPicker, PlotSearch },
  props: {
    /** The stage's URL segment; the route only matches the four known ones. */
    stage: { type: String, required: true }
  },
  data() {
    return {
      returnStage: 0,
      lost: false,
      // How many history entries this wizard pushed; see `stepBack`.
      ownEntries: 0,
      source: "search",
      url: "",
      gemarkung: "",
      // The directory entry the text stands for, once one does. Null while
      // the text is free-hand — which stays a valid way to look one up.
      gemarkungEntry: null,
      flurstuecksnummer: "",
      pastedText: "",
      busy: false,
      error: "",
      readFields: [],
      draft: null,
      doubt: null,
      /** The parcels around the resolved point, for the user to choose from. */
      choices: [],
      /** The keys of the parcels the plot is made of. A plot is a set of
       *  parcels, so this is what the map's clicks add to and take from. */
      selection: [],
      /** Why the last click did not do what it looked like it would. */
      selectionNote: null,
      /** The address the search picked, so the cadastre's own Lagebezeichnung
       *  can be checked against it rather than the coordinate being trusted. */
      searchedAddress: null,
      /** The parcel number a Lagebezeichnung match put in place of the one the
       *  coordinate landed in. Null unless it actually differed. */
      corrected: null,
      // The labels for the stages in `WIZARD_STAGES`, in that order. The
      // parcel and the fields are one step: the fields are three inputs, and
      // the "Passt" between them decided nothing.
      steps: [
        { id: "source", name: "Quelle" },
        { id: "fields", name: "Gelesene Werte" },
        { id: "parcel", name: "Flurstück und Angaben" }
      ],
      sources: [
        { id: "search", name: "Suchen",
          text: "Adresse, Flurstück oder Koordinate. Vorschläge kommen aus den amtlichen Hauskoordinaten und dem Gemarkungsverzeichnis." },
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
    stageIndex() { return WIZARD_STAGES.indexOf(this.stage); },
    /* What each stage needs in order to have anything to show. Only the first
     * one stands on its own: the read fields and the draft live in this
     * component and are gone after a reload. */
    reachable() {
      if (this.stageIndex <= 0) return true;
      return this.stageIndex === 1 ? this.readFields.length > 0 : Boolean(this.draft);
    },
    ready() {
      // The search has no button: picking a suggestion is the action.
      if (this.source === "search") return false;
      if (this.source === "url") return /^https?:\/\/\S{6,}/.test(this.url.trim());
      if (this.source === "parcel") return this.gemarkung.trim() && this.flurstuecksnummer.trim();
      return this.pastedText.trim().length > 20;
    },
    computedArea() { return this.draft ? polygonArea(this.draft.polygon) : 0; },
    /** What the cadastre is asked for: the key of the chosen entry, which is
     *  unambiguous where two districts share a name, else the plain text. */
    gemarkungQuery() { return this.gemarkungEntry?.schluessel || this.gemarkung.trim(); }
  },
  created() { this.checkStage(); },
  watch: { stage() { this.checkStage(); } },
  methods: {
    area, euroPerSqm, num,

    /** A stage reached without the data behind it — a reload, or the back
     *  button after the plot was created — sends the user back to the start
     *  with a reason rather than showing an empty step. */
    checkStage() {
      if (this.reachable) return;
      this.lost = true;
      this.$router.replace(wizardStage(0));
    },

    goToStage(stage) {
      this.lost = false;
      this.ownEntries++;
      this.$router.push(wizardStage(stage));
    },

    /** The "Zurück" buttons leave the entry this wizard pushed instead of
     *  adding another one, so they and the browser's own back button do the
     *  same thing. The entry behind is always the stage that was left — the
     *  wizard pushed it — so it is the one `stage` names. A stage opened
     *  directly has nothing to step out of and gets a plain push. */
    stepBack(stage) {
      if (!this.ownEntries) return this.goToStage(stage);
      this.ownEntries--;
      this.$router.back();
    },

    /** A suggestion was picked: it already carries the cadastral query. */
    async searchPicked({ query, label, address }) {
      this.busy = true;
      this.error = "";
      try {
        this.returnStage = 0;
        this.searchedAddress = address ?? null;
        await this.queryCadastre(query, { note: `Gesucht: ${label}` });
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async read() {
      this.busy = true;
      this.error = "";
      try {
        if (this.source === "parcel") {
          this.returnStage = 0;
          await this.queryCadastre({
            gemarkung: this.gemarkungQuery,
            flurstuecksnummer: this.flurstuecksnummer.trim()
          });
          return;
        }
        const response = this.source === "url"
          ? await readListing(this.url.trim())
          : await readPage(this.pastedText);
        this.readFields = fieldsFromResponse(response);
        this.returnStage = 1;
        this.goToStage(1);
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
      else if (numbers.length) query = { gemarkung: this.gemarkungQuery || undefined, flurstuecksnummer: numbers[0] };
      else if (read("adresse")) query = { address: read("adresse") };

      // The listing's own plot area lets the service judge whether the parcel
      // it found can plausibly be the one being sold. A district address lands
      // in the field next door, and nothing else would say so.
      const statedArea = numberFrom(read("grundstuecksflaeche_m2"));
      if (query && Number.isFinite(statedArea)) query.expected_area_m2 = statedArea;

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

    /** The parcels around this draft, and the one the address actually names.
     *
     * Two different things can put the wrong parcel in front of the user: an
     * address coordinate that lands next door, and a plot that is simply not
     * the one they meant. The first is corrected here against the cadastre's
     * own Lagebezeichnung; the second is theirs to fix with a click. Neither
     * is worth failing the step over, so a refusal only costs the choice. */
    async loadChoices(plot, extra) {
      if (!plot.anchor) return;
      try {
        const answer = await nearbyParcels(plot.anchor.lat, plot.anchor.lon);
        this.choices = answer?.features ?? [];
      } catch {
        this.choices = [];
        return;
      }
      const named = parcelForAddress(this.choices, this.searchedAddress);
      if (!named || named.properties?.kennzeichen === plot.kennzeichen) return;
      const corrected = plotFromCadastre(
        { features: [named], grundstueck: named, quelle: plot.source }, extra
      );
      this.corrected = `Flurstück ${corrected.flurstuecke.join(" · ")}`;
      this.selection = [named.properties.kennzeichen];
      this.draft = { ...corrected, bodenrichtwert: plot.bodenrichtwert, brwZone: plot.brwZone,
                     brwReferenceDate: plot.brwReferenceDate,
                     brwReferencePlotArea: plot.brwReferencePlotArea,
                     brwConversionUrl: plot.brwConversionUrl,
                     houseTypeId: plot.houseTypeId, ratio: plot.ratio };
    },

    /** A click on the map: the parcel joins the plot or leaves it.
     *
     * A plot is a set of parcels — that is the normal case, not the exception —
     * so this toggles membership and asks the cadastre for the new set. The
     * union and the summed official areas come from there, the same way every
     * other route into this wizard gets them. */
    async toggleParcel(kennzeichen) {
      if (this.busy || !this.choices.length) return;
      const taken = this.selection.includes(kennzeichen);
      if (taken && this.selection.length === 1) {
        this.selectionNote = "Ein Grundstück besteht aus mindestens einem Flurstück. "
          + "Erst ein anderes dazunehmen, dann lässt sich dieses abwählen.";
        return;
      }
      await this.applySelection(taken
        ? this.selection.filter(key => key !== kennzeichen)
        : [...this.selection, kennzeichen]);
    },

    /** Resolve a set of parcel keys into the draft, keeping what the cadastre
     *  cannot know: the name and price the user typed, and the note. */
    async applySelection(keys) {
      this.busy = true;
      this.selectionNote = null;
      try {
        const answer = await resolveParcel({ kennzeichen: keys });
        /* Two parcels that do not touch are a real plot in the register and a
           shape this drawing cannot hold: the outline would be one of the two
           parts, silently. So the click is refused with the reason. */
        if (answer?.grundstueck?.geometry?.type === "MultiPolygon") {
          this.selectionNote = "Diese Flurstücke grenzen nicht aneinander. Der Lageplan "
            + "zeichnet einen zusammenhängenden Umriss — bitte nur benachbarte Flurstücke "
            + "zusammenfassen.";
          return;
        }
        const kept = {
          name: this.draft.name, askingPrice: this.draft.askingPrice, note: this.draft.note
        };
        const plot = await this.withLandValue(plotFromCadastre(answer, kept));
        this.draft = { ...plot, houseTypeId: this.draft.houseTypeId, ratio: this.draft.ratio };
        this.selection = keys;
        this.corrected = null;
        this.doubt = null;
      } catch (error) {
        this.selectionNote = error.message;
      } finally {
        this.busy = false;
      }
    },

    /** The land value for a plot's own centre. A separate register, and a plot
     *  without one is still usable — so a failure only empties the fields. */
    async withLandValue(plot) {
      try {
        const value = await landValue(plot.anchor.lat, plot.anchor.lon);
        plot.bodenrichtwert = value?.euro_per_sqm ?? null;
        plot.brwZone = value?.zone ?? null;
        plot.brwReferenceDate = value?.reference_date ?? null;
        // The notional plot the zone value is quoted for. Without it a reader
        // multiplies the value by their own area, which is exactly the step
        // the Gutachterausschuss publishes a conversion table for.
        plot.brwReferencePlotArea = value?.richtwertgrundstueck_m2 ?? null;
        plot.brwConversionUrl = value?.umrechnungstabelle_url ?? null;
      } catch { /* leave it empty and say so on the same step */ }
      return plot;
    },

    async queryCadastre(query, extra = {}) {
      const answer = await resolveParcel(query);
      const plot = await this.withLandValue(plotFromCadastre(answer, extra));
      // Not an error: the parcel is real and the user may still want it. It is
      // a judgement they have to make, so it is put in front of them.
      this.doubt = answer.plausibility?.plausible === false
        ? answer.plausibility.warning
        : null;
      /* A catalogue entry when the user has one, and otherwise the plot's own
       * dimensions — anything rather than a "Baukörper" box with nothing chosen
       * in it while the plan already draws a house. */
      const first = state.data.houseTypes[0];
      if (first) {
        plot.houseTypeId = first.id;
        if (first.ratio) plot.ratio = first.ratio;
      }
      this.draft = plot;
      this.choices = [];
      this.corrected = null;
      this.selectionNote = null;
      this.selection = (answer.features ?? [])
        .map(feature => feature.properties?.kennzeichen)
        .filter(Boolean);
      this.goToStage(2);
      // After the step is on screen: the choice is an aid, not a precondition.
      await this.loadChoices(plot, extra);
    },

    create() {
      // Seated here, not at the Flurstück step: until the plot exists nobody
      // has chosen a house type, so a footprint there is a placeholder the
      // user never asked for — and "no room for it" a finding about nothing.
      autoSeatHouse(this.draft);
      const plot = addPlot(this.draft);
      // Replace: the last stage of a finished wizard is not a place to return to.
      this.$router.replace({ name: "plot", params: { id: plot.id } });
    }
  }
};
</script>

<style scoped>
.doubt-note{ display: block; line-height: 1.5; }
.doubt-note b{ display: block; margin-bottom: 2px; }
.subtitle{ color: var(--w2b-graphite); font-size: var(--w2b-text-s); max-width: 70ch; }
.hint{ color: var(--w2b-muted); font-size: var(--w2b-text-s); }

.steps{ display: flex; gap: var(--w2b-space-2); flex-wrap: wrap; list-style: none; margin: 0; padding: 0; }
.steps li{
  display: flex; align-items: center; gap: var(--w2b-space-2);
  padding: 9px var(--w2b-space-4) 9px 10px; border-radius: var(--w2b-radius-full);
  border: 1px solid var(--w2b-line); background: var(--w2b-surface);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-s); color: var(--w2b-muted);
}
.steps__number{
  display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
  background: var(--w2b-line-faint); color: var(--w2b-graphite);
  font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs);
}
.steps .is-current{ border-color: var(--w2b-primary); color: var(--w2b-ink); }
.steps .is-current .steps__number{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.steps .is-done{ color: var(--w2b-primary); border-color: var(--w2b-primary-veil); }
.steps .is-done .steps__number{ background: var(--w2b-primary-veil); color: var(--w2b-primary); }

.sources{ display: grid; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr)); gap: var(--w2b-space-3); }
.source{
  display: flex; flex-direction: column; gap: var(--w2b-space-2); cursor: pointer;
  padding: var(--w2b-space-4); border: 1.5px solid var(--w2b-line); border-radius: var(--w2b-radius-m);
  background: var(--w2b-surface);
}
.source input{ position: absolute; opacity: 0; pointer-events: none; }
.source--selected{ border-color: var(--w2b-primary); background: var(--w2b-primary-veil); }
.source__name{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-l); }
.source__text{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }

.field-pair{ display: grid; grid-template-columns: 1fr 1fr; gap: var(--w2b-space-3); }
@media (max-width: 560px){ .field-pair{ grid-template-columns: 1fr; } }

.suggestions{ display: grid; grid-template-columns: repeat(auto-fill, minmax(244px, 1fr)); gap: var(--w2b-space-3); }
.suggestion{
  display: flex; flex-direction: column; gap: var(--w2b-space-2);
  padding: var(--w2b-space-3) var(--w2b-space-4);
  border: 1.5px dashed var(--w2b-secondary); border-radius: var(--w2b-radius-m);
  background: var(--w2b-secondary-veil);
}
.suggestion--empty{ border-color: var(--w2b-error); background: var(--w2b-error-surface); }
.suggestion__head{ display: flex; align-items: center; gap: var(--w2b-space-2); flex-wrap: wrap; }
.suggestion__tag{
  font-family: var(--w2b-font-mono); font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase;
  padding: 1px 7px; border-radius: var(--w2b-radius-full);
  border: 1px solid var(--w2b-secondary-text); color: var(--w2b-secondary-text);
}
.suggestion--empty .suggestion__tag{ border-color: var(--w2b-error); color: var(--w2b-error); }
.suggestion__source{ font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted); overflow-wrap: anywhere; line-height: 1.45; }

.check-grid{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: var(--w2b-space-4); align-items: start; }
@media (max-width: 900px){ .check-grid{ grid-template-columns: 1fr; } }
.value-list{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.value-list dt, .value-list dd{ padding: 8px var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line-faint); margin: 0; display: flex; align-items: center; }
.value-list dt{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.value-list dd{ justify-content: flex-end; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-s); font-variant-numeric: tabular-nums; text-align: right; }
/* No rule above it here: the value list it follows is the panel's whole body. */
.panel__footnote{ border-top: 0; }
</style>
