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
    <section v-if="stage === 'quelle' || !reachable" class="stack">
      <p class="subtitle">Drei Wege hinein. Welcher passt zu dem, was vorliegt?</p>
      <div class="sources">
        <label v-for="s in sources" :key="s.id" class="source" :class="{ 'source--selected': source === s.id }">
          <input type="radio" name="source" :value="s.id" v-model="source">
          <span class="source__name">{{ s.name }}</span>
          <span class="source__text">{{ s.text }}</span>
        </label>
      </div>

      <div class="panel">
        <div class="panel__body stack">
          <template v-if="source === 'url'">
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

          <template v-else-if="source === 'text'">
            <div class="field">
              <label for="q-text">Beschreibung aus der Anzeige</label>
              <textarea id="q-text" v-model="listingText"
                        placeholder="Den Beschreibungstext der Anzeige einfügen — mit Ortsteil, Fläche und Straße"></textarea>
            </div>
            <p class="hint">
              Dieser Weg braucht kein Modell. Gesucht wird über Muster und das
              Gemarkungsverzeichnis: eine Flurstücksnummer im Text, ein Ortsteil mit
              seiner Beziehung („OT von“, „am Ortsrand von“, „6 km entfernt“), die
              Fläche so, wie sie dasteht, und die Straße. Was daraus folgt, steht
              anschließend Zeile für Zeile im Protokoll.
            </p>
          </template>

          <template v-else>
            <div class="field">
              <label for="q-paste">Anzeige hier einfügen</label>
              <textarea id="q-paste" v-model="pastedText"
                        placeholder="Strg+V — die kopierte Anzeigenseite"></textarea>
            </div>
          </template>

          <div class="row">
            <button type="button" class="btn" :disabled="busy || !ready" @click="read">
              {{ busy ? "Wird gelesen …" : readLabel }}
            </button>
            <span v-if="busy" class="hint">Der Abruf kann eine Minute dauern.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 2 · Gelesene Werte -->
    <section v-else-if="stage === 'werte'" class="stack">
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
          {{ busy ? "Kataster wird abgefragt …" : "Flurstück suchen" }}
        </button>
        <button type="button" class="btn btn--quiet" @click="stepBack('quelle')">Zurück</button>
      </div>
    </section>

    <!-- 3 · Flurstück suchen. The listing named a place, not a parcel; this
         step turns the one into the other and shows what it stood on. -->
    <section v-else-if="stage === 'suche'" class="stack">
      <p class="subtitle">
        Ein Inserat nennt fast nie sein Flurstück. Gesucht wird deshalb über das, was
        dasteht — Ortsteil, Fläche, Straße —, und die Karte zeigt dabei durchgehend, was
        noch möglich ist. Reicht es nicht für ein einzelnes Flurstück, sagt die Antwort,
        worauf sich die Lage eingrenzen lässt.
      </p>
      <ParcelSearch v-if="searchQuery" :query="searchQuery" :key="searchRun"
                    @confirm="takeCandidate" @manual="stepBack('quelle')" />
      <div class="row">
        <button type="button" class="btn btn--quiet" @click="stepBack('werte')">Zurück</button>
      </div>
    </section>

    <!-- 4 · Flurstück -->
    <section v-else-if="stage === 'flurstueck'" class="stack">
      <p class="subtitle">
        So liegt das Flurstück im Kataster. Stimmt der Zuschnitt, geht es weiter;
        sonst zurück und die Angaben korrigieren. Den Ausschnitt bewegt die
        gedrückte Maustaste, das Mausrad zoomt, ein Doppelklick setzt ihn zurück.
      </p>

      <!-- The service found something implausible for this listing. Not an
           error — the parcel is real — but the user has to see it before the
           next click turns it into a plot they plan a house on. -->
      <div v-if="doubt" class="notice notice--error doubt-note">
        <b>Das ist vermutlich nicht das richtige Flurstück.</b>
        {{ doubt }}
      </div>

      <!-- The house is placed before the plot exists, so this is the first and
           only moment the user can be told it did not fit. -->
      <p v-if="!houseSeated" class="notice notice--error" role="status">
        <b>Für den Baukörper ist zwischen den Abstandsflächen kein Platz.</b>
        {{ num(draftBuilding.width, 1) }} × {{ num(draftBuilding.depth, 1) }} m finden auf diesem
        Zuschnitt in keiner Lage und in keinem Winkel Platz. Übernehmen lässt sich das Flurstück
        trotzdem; auf der Grundstücksseite liegt der Umriss dann mittig und ragt sichtbar über das
        Bebauungsfenster hinaus, und dort lassen sich Maße, Wandhöhe und Abstandstiefen ändern.
      </p>

      <div class="check-grid">
        <div class="panel">
          <!-- No house here: this step is about the parcel's outline, and a
               body nobody has planned yet only distracts from it. -->
          <SitePlan :plot="draft" :width="640" :height="440" backdrop="map" north-up
                    :show-building="false" navigable />
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
      <div class="row">
        <button type="button" :class="doubt ? 'btn btn--secondary' : 'btn'" @click="goToStage('angaben')">
          {{ doubt ? "Trotzdem übernehmen" : "Passt" }}
        </button>
        <button type="button" class="btn btn--quiet" @click="stepBack(returnStage)">Zurück</button>
      </div>
    </section>

    <!-- 5 · Angaben -->
    <section v-else class="stack">
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
            <button type="button" class="btn" @click="create">Anlegen und öffnen</button>
            <button type="button" class="btn btn--quiet" @click="stepBack('flurstueck')">Zurück</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import CadastralDistrictPicker from "../components/CadastralDistrictPicker.vue";
import ParcelSearch from "../components/ParcelSearch.vue";
import { state, addPlot, placement, autoSeatHouse } from "../lib/store.js";
import { WIZARD_STAGES, wizardStage } from "../router/stages.js";
import { readListing, readPage, resolveParcel, landValue } from "../lib/api.js";
import { queryFromFields } from "../lib/search.js";
import { plotFromCadastre } from "../lib/plots.js";
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
  components: { SitePlan, CadastralDistrictPicker, ParcelSearch },
  props: {
    /** The stage's URL segment; the route only matches the four known ones. */
    stage: { type: String, required: true }
  },
  data() {
    return {
      returnStage: "quelle",
      // What the listing said about price and address, held until a candidate
      // is chosen and the draft is built.
      listingExtras: null,
      lost: false,
      // How many history entries this wizard pushed; see `stepBack`.
      ownEntries: 0,
      source: "url",
      url: "",
      gemarkung: "",
      // The directory entry the text stands for, once one does. Null while
      // the text is free-hand — which stays a valid way to look one up.
      gemarkungEntry: null,
      flurstuecksnummer: "",
      pastedText: "",
      listingText: "",
      busy: false,
      error: "",
      readFields: [],
      /* The listing's own prose. It is what the search reads the cadastral
       * district, the street and the relation between the named places out of
       * — none of which is an attribute anywhere. It never reaches the stored
       * plot; see lib/plots.js for what a plot actually carries. */
      description: "",
      searchQuery: null,
      /* The listing's pictures. The search reads them only when the text names
       * no Flurstück — a seller who attaches a Geoportal print has already
       * answered the question, and one who has not costs three seconds an
       * image to learn nothing. */
      images: [],
      // Bumped to remount the search rather than reuse a finished one.
      searchRun: 0,
      draft: null,
      doubt: null,
      // Whether the footprint found room inside the setbacks; see `seatHouse`.
      houseSeated: true,
      // The labels for the stages in `WIZARD_STAGES`, in that order.
      steps: [
        { id: "quelle", name: "Quelle" },
        { id: "werte", name: "Gelesene Werte" },
        { id: "suche", name: "Flurstück suchen" },
        { id: "flurstueck", name: "Flurstück" },
        { id: "angaben", name: "Angaben" }
      ],
      sources: [
        { id: "url", name: "Link einwerfen",
          text: "Adresse einer Anzeige. Der Server holt die Seite und liest Adresse, Flurstück, Kaufpreis und Fläche heraus." },
        { id: "parcel", name: "Flurstück direkt",
          text: "Gemarkung und Flurstücksnummer, so wie sie im Geoportal stehen." },
        { id: "text", name: "Text durchsuchen",
          text: "Nur der Beschreibungstext. Daraus wird das Flurstück gesucht — ohne Modell, allein über Muster und das Gemarkungsverzeichnis." },
        { id: "paste", name: "Seite einfügen",
          text: "Für Portale, die keinen Serverabruf zulassen. Die kopierte Anzeigenseite einfügen." }
      ]
    };
  },
  computed: {
    stageIndex() { return WIZARD_STAGES.indexOf(this.stage); },
    /* What each stage needs in order to have anything to show. Only the first
     * one stands on its own: the read fields, the query and the draft live in
     * this component and are gone after a reload. */
    reachable() {
      if (this.stageIndex <= 0) return true;
      if (this.stage === "werte") return this.readFields.length > 0;
      if (this.stage === "suche") return Boolean(this.searchQuery);
      return Boolean(this.draft);
    },
    ready() {
      if (this.source === "url") return /^https?:\/\/\S{6,}/.test(this.url.trim());
      if (this.source === "parcel") return this.gemarkung.trim() && this.flurstuecksnummer.trim();
      if (this.source === "text") return this.listingText.trim().length > 20;
      return this.pastedText.trim().length > 20;
    },
    readLabel() {
      return { parcel: "Nachschlagen", text: "Flurstück suchen" }[this.source] ?? "Lesen";
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

    async read() {
      this.busy = true;
      this.error = "";
      try {
        if (this.source === "text") {
          // Straight into the search: no page to fetch and no model to ask.
          // The text is the evidence, and reading it is what the search does.
          this.searchQuery = {
            text: this.listingText.trim(),
          };
          this.listingExtras = {};
          this.searchRun++;
          this.returnStage = "quelle";
          this.goToStage("suche");
          return;
        }
        if (this.source === "parcel") {
          // Nothing to search for: the district and the number are the answer.
          this.returnStage = "quelle";
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
        this.description = response?.beschreibung || (this.source === "paste" ? this.pastedText : "");
        this.images = response?.bilder || [];
        this.returnStage = "werte";
        this.goToStage("werte");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    /** Hand what was read to the search.
     *
     *  Deliberately not a lookup any more. A coordinate resolves to whatever
     *  parcel it lands on — measured 6 235 m from the plot actually being sold,
     *  because the platform geocodes its own location field — and a single
     *  parcel number without its district is a guess. The search asks the
     *  cadastre a series of narrow questions instead, and shows what each one
     *  settled.
     */
    lookUpParcel() {
      const read = name => this.readFields.find(f => f.key === name)?.value;
      this.searchQuery = queryFromFields(this.readFields, {
        ...(this.description ? { text: this.description } : {}),
        ...(this.images.length ? { bilder: this.images } : {}),
        ...(this.gemarkungQuery ? { gemarkung: this.gemarkungQuery } : {})
      });
      this.listingExtras = {
        askingPrice: numberFrom(read("kaufpreis_eur")),
        note: read("adresse") ? `Aus der Anzeige: ${read("adresse")}` : ""
      };
      this.searchRun++;
      this.returnStage = "suche";
      this.goToStage("suche");
    },

    /** One candidate from the search becomes the draft plot.
     *
     *  Resolved again through /api/parcels/resolve rather than assembled from
     *  the search answer: that endpoint is what the rest of the app already
     *  speaks, and it re-checks the parcel on the way through.
     */
    async takeCandidate(candidate) {
      if (!candidate) return;
      this.busy = true;
      this.error = "";
      try {
        await this.queryCadastre(
          {
            gemarkung: candidate.properties.gemarkungsnummer || candidate.properties.gemarkung,
            flurstuecksnummer: candidate.properties.flurstuecksnummer,
            ...(this.searchQuery?.flaeche_m2 ? { expected_area_m2: Math.round(this.searchQuery.flaeche_m2) } : {})
          },
          this.listingExtras || {}
        );
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async queryCadastre(query, extra = {}) {
      const answer = await resolveParcel(query);
      const plot = plotFromCadastre(answer, extra);
      // Not an error: the parcel is real and the user may still want it. It is
      // a judgement they have to make, so it is put in front of them.
      this.doubt = answer.plausibility?.plausible === false
        ? answer.plausibility.warning
        : null;
      // The land value is a separate register; a plot without one is still usable.
      try {
        const value = await landValue(plot.anchor.lat, plot.anchor.lon);
        plot.bodenrichtwert = value?.euro_per_sqm ?? null;
        plot.brwZone = value?.zone ?? null;
        plot.brwReferenceDate = value?.reference_date ?? null;
      } catch { /* leave it empty and say so on the next step */ }
      /* A catalogue entry when the user has one, and otherwise the plot's own
       * dimensions — anything rather than a "Baukörper" box with nothing chosen
       * in it while the plan already draws a house. */
      const first = state.data.houseTypes[0];
      if (first) {
        plot.houseTypeId = first.id;
        if (first.ratio) plot.ratio = first.ratio;
      }
      this.houseSeated = autoSeatHouse(plot);
      this.draft = plot;
      this.goToStage("flurstueck");
    },

    create() {
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
.breadcrumb{ display: flex; align-items: center; gap: var(--w2b-space-2); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.breadcrumb a{ color: var(--w2b-primary); text-decoration: none; }
.breadcrumb a:hover{ text-decoration: underline; }
.page-head{ display: flex; align-items: flex-end; gap: var(--w2b-space-4); flex-wrap: wrap; }
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
.panel__footnote{ padding: var(--w2b-space-3) var(--w2b-space-4); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
</style>
