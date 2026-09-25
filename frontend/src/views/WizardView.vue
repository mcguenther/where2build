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
      Der begonnene Entwurf ist nicht mehr vorhanden; beim Neuladen der Seite bleibt er
      nicht erhalten. Bitte noch einmal mit der Quelle beginnen.
    </p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <!-- 1 · Quelle. Also what a stage without its data falls back to, so the
         redirect in `checkStage` never renders a step that has nothing.
         One field for all five ways in: the reading decides which of them is
         happening, and the chips let it be overruled. -->
    <section v-if="stage === 'quelle' || !reachable" class="stack">
      <p class="subtitle">
        Adresse, Flurstück, Koordinate, der Link einer Anzeige oder die eingefügte
        Anzeigenseite: alles in dasselbe Feld.
      </p>

      <!-- A document the bookmarklet handed over. Not the field's business:
           nothing was typed, there is nothing to correct, and a textarea
           holding two megabytes of markup would show nobody anything. -->
      <p v-if="handoverWaiting" class="hint">
        Warten auf die Seite aus dem Tab, in dem das Lesezeichen geklickt wurde …
      </p>

      <QueryBox v-else class="panel wizard__query" :busy="busy"
                @resolve="searchPicked" @read="readPayload" />

      <p class="hint">
        Was getippt wurde, wird zuerst gelesen und dann nachgeschlagen: eine deutsche
        Adresse beginnt nie mit einer Ziffer, eine Koordinate sind zwei Zahlen, und ein
        Nenner (<span class="mono">85/1</span>) kommt in keiner Adresse vor. Bleiben zwei
        Lesarten möglich, werden beide Verzeichnisse gefragt statt eine geraten. Was
        darunter steht, lässt sich anklicken, wenn es die falsche ist.
        <br>
        <b>Eine Anzeigenseite</b> im Browser mit <span class="mono">Strg+A</span>,
        <span class="mono">Strg+C</span> kopieren und hier einfügen: die Zwischenablage
        führt neben dem Text auch das HTML mit, und daraus kommen Preis, Fläche und die
        Bilder ohne Modell. Der <i>Kopf</i> der Seite kommt dabei nicht mit —
        <span class="mono">Strg+A</span> wählt nur den Rumpf aus, also fehlen die
        Meta-Angaben und mit ihnen die Koordinate. ImmoScout24 lässt außerdem keinen
        Serverabruf zu; dort ist das Einfügen der Weg.
      </p>

      <!-- Its own modifier, and that is not decoration: the search step has a
           `details.gelesen` too, so a script waiting for one would match this
           one on the step before and then wait for a list that never comes. -->
      <details class="gelesen gelesen--lesezeichen no-print">
        <summary>
          <span class="gelesen__titel">Ein Klick statt Kopieren</span>
          <span class="gelesen__zahl">Lesezeichen, einmal einrichten</span>
        </summary>
        <p class="subtitle">
          Diesen Knopf in die Lesezeichenleiste ziehen — ist sie nicht zu sehen, holt
          <span class="mono">Strg+Umschalt+B</span> sie hervor. Auf der Anzeigenseite dann
          darauf klicken: der Browser schickt die Seite, die er ohnehin vor sich hat,
          hierher. Vollständig, also mit allem, was das Kopieren verliert.
        </p>
        <p class="row">
          <a class="btn" :href="bookmarkletLink" @click.prevent>Grundstück prüfen</a>
        </p>
        <p class="hint">
          Der Knopf tut hier nichts, er <i>ist</i> das Lesezeichen. Er öffnet
          <span class="mono">{{ appOrigin }}</span> in einem neuen Tab und übergibt die
          Seite dorthin; an das Portal geht dabei keine Anfrage.
        </p>
      </details>
    </section>

    <!-- 2 · Gelesene Werte -->
    <!-- 2 · Flurstück suchen. The listing named a place, not a parcel; this
         step turns the one into the other and shows what it stood on. What the
         reader got off the page rides along folded up: it is what the search
         is running on, so it belongs here, and it is a list nobody has to read
         before carrying on, so it starts closed. -->
    <section v-else-if="stage === 'suche'" class="stack">
      <p class="subtitle">
        Ein Inserat nennt fast nie sein Flurstück. Gesucht wird deshalb über das, was
        dasteht (Ortsteil, Fläche, Straße), und die Karte zeigt dabei durchgehend, was
        noch möglich ist. Reicht es nicht für ein einzelnes Flurstück, sagt die Antwort,
        worauf sich die Lage eingrenzen lässt.
      </p>

      <details v-if="readSummary" class="gelesen">
        <summary>
          <span class="gelesen__titel">Gelesene Werte</span>
          <span class="gelesen__zahl">{{ readSummary }}</span>
        </summary>
        <p class="subtitle">
          Jedes Feld führt die Quelle mit, aus der es stammt. Was die Seite nicht hergibt,
          bleibt leer und wird nicht erfunden. Eine Änderung hier startet die Suche neu.
        </p>
        <div class="suggestions">
          <div v-for="f in readFields" :key="f.key" class="suggestion" :class="{ 'suggestion--empty': !f.value }">
            <span class="suggestion__head">
              <span class="field-label">{{ f.label }}</span>
              <span class="suggestion__tag">{{ f.value ? "automatisch gelesen" : "nicht belegt" }}</span>
            </span>
            <span class="suggestion__eingabe">
              <input type="text" v-model="f.value" :aria-label="f.label"
                     :placeholder="f.value ? '' : 'steht nicht auf der Seite'"
                     @keydown.enter.exact.prevent="lookUpParcel">
              <span v-if="f.unit" class="suggestion__einheit" aria-hidden="true">{{ f.unit }}</span>
            </span>
            <span class="suggestion__source">{{ f.source }}</span>
          </div>
        </div>
        <div class="row">
          <button type="button" class="btn btn--quiet" @click="lookUpParcel">
            Suche mit diesen Werten neu starten
          </button>
        </div>
      </details>

      <ParcelSearch v-if="searchQuery" :query="searchQuery" :key="searchRun"
                    @confirm="takeCandidate" @manual="stepBack('quelle')" />
      <div class="row">
        <button type="button" class="btn btn--quiet" @click="stepBack('quelle')">Zurück</button>
      </div>
    </section>

    <!-- 3 · Grundstück: die Flurstücke und die Angaben dazu -->
    <section v-else-if="stage === 'flurstueck'" class="stack">
      <p class="subtitle">
        So liegen die Flurstücke im Kataster. Ein Klick wählt ein anderes; zum
        Zusammensetzen mehrerer umschalten. Den Ausschnitt bewegt die gedrückte
        Maustaste, das Mausrad zoomt, ein Doppelklick setzt ihn zurück.
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
        Gewählt ist {{ corrected }}: die Lagebezeichnung im Kataster nennt genau diese
        Adresse. Ein Klick auf ein anderes Flurstück ändert das.
      </p>

      <p v-if="addError" class="notice notice--error" role="alert">{{ addError }}</p>

      <div class="check-grid">
        <div class="panel">
          <!-- Two ways to click, because they are two different intentions:
               correcting the parcel is the common one, assembling a plot out of
               several is the rarer one and would otherwise happen by accident. -->
          <div class="plan-bar">
            <span class="plan-bar__label">Klick</span>
            <div class="button-group" role="group" aria-label="Was ein Klick tut">
              <button type="button" :aria-pressed="String(!composing)"
                      @click="composing = false">Wechseln</button>
              <button type="button" :aria-pressed="String(composing)"
                      @click="composing = true">Zusammensetzen</button>
            </div>
            <div class="spacer"></div>
            <span class="plan-bar__label">{{ selection.length }} gewählt</span>
          </div>
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
                    overlay="liegenschaftskarte" north-up :hold-frame="holdFrame"
                    :show-building="false" :show-dimensions="false" navigable
                    :parcels="choices" :chosen-parcels="selection"
                    :problem-parcels="detached"
                    @choose="chooseParcel" />
          <p v-if="selectionNote" class="notice" :class="{ 'notice--error': detached.length }"
             role="status">{{ selectionNote }}</p>
          <p class="panel__footnote">
            <template v-if="choices.length > 1">
              {{ choices.length }} Flurstücke im Umkreis; die Katasterlinien beschriften
              jedes mit seiner Nummer.
              {{ composing ? "Ein Klick nimmt eines dazu oder heraus." : "Ein Klick wählt ein anderes." }}
            </template>
            Kataster: © GeoSN, dl-de/by-2-0 · Luftbild: © GeoBasis-DE / Länder
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
              <input id="q-name" type="text" v-model="draft.name" @keydown.enter.exact.prevent="createByEnter">
            </div>
            <div class="field">
              <label for="q-price">Kaufpreis in Euro</label>
              <input id="q-price" type="number" min="0" step="1000" v-model.number="draft.askingPrice"
                     placeholder="ohne Angabe kein €/m²-Vergleich"
                     @keydown.enter.exact.prevent="createByEnter">
            </div>
          </div>
          <div class="field">
            <label for="q-note">Notiz</label>
            <input id="q-note" type="text" v-model="draft.note" placeholder="Optional: was auffiel"
                   @keydown.enter.exact.prevent="createByEnter">
          </div>
          <p v-if="!draft.bodenrichtwert" class="notice">
            Für dieses Grundstück ließ sich kein Bodenrichtwert abrufen. Die Preiseinordnung
            bleibt dann leer; nachtragen lässt sie sich später.
          </p>
          <div class="row">
            <!-- A split plot may be assembled on the way to a whole one, but it
                 cannot be created: the drawing holds one outline, and half a
                 plot would be a plot nobody chose. -->
            <button type="button" :class="doubt ? 'btn btn--secondary' : 'btn'"
                    :disabled="busy || detached.length > 0"
                    :title="detached.length ? 'Die rot markierten Flurstücke hängen nicht mit dem übrigen Grundstück zusammen.' : null"
                    @click="create">
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
import ParcelSearch from "../components/ParcelSearch.vue";
import QueryBox from "../components/QueryBox.vue";
import { state, addPlot, autoSeatHouse } from "../lib/store.js";
import { settleStreetFront } from "../lib/streetFront.js";
import { WIZARD_STAGES, wizardStage } from "../router/stages.js";
import { takeHandoff } from "../lib/handoff.js";
import {
  readListing, readPage, resolveParcel, landValue, nearbyParcels, PAGE_LIMIT
} from "../lib/api.js";
import { queryFromFields } from "../lib/search.js";
import { plotFromCadastre, parcelForAddress, outerRing } from "../lib/plots.js";
import { polygonArea, polygonCentroid, pointInPolygon } from "../lib/geometry.js";
import { toLocal } from "../lib/projection.js";
import { area, euroPerSqm, num, parseGermanNumber as numberFrom } from "../lib/format.js";
import {
  HANDOVER_QUERY, HANDOVER_READY, HANDOVER_PAGE, bookmarkletHref
} from "../lib/bookmarklet.js";

/** The backend answers with {feld: {wert, quelle_url, bestaetigt}}. */
function fieldsFromResponse(response) {
  const fields = response?.felder ?? {};
  const labels = {
    adresse: "Adresse", lat: "Breitengrad", lon: "Längengrad",
    flurstuecke: "Flurstücke", kaufpreis_eur: "Kaufpreis",
    grundstuecksflaeche_m2: "Grundstücksfläche"
  };
  /* Shown beside the box, never inside it: „600" is what the search sends to
   * the cadastre, and a unit inside the field would travel with it. A number
   * with no unit next to a price with no unit is a field nobody can read. */
  const units = { grundstuecksflaeche_m2: "m²", kaufpreis_eur: "€", lat: "°", lon: "°" };
  return Object.entries(fields).map(([key, entry]) => ({
    key,
    label: labels[key] ?? key,
    unit: units[key] ?? "",
    value: Array.isArray(entry?.wert)
      ? entry.wert.map(v => (typeof v === "object" ? [v.zaehler, v.nenner].filter(Boolean).join("/") : v)).join(", ")
      : entry?.wert ?? "",
    source: entry?.quelle_url || response?.hinweis || "aus der gelesenen Seite"
  }));
}


export default {
  name: "WizardView",
  components: { SitePlan, ParcelSearch, QueryBox },
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
      /* The document a bookmarklet handed over: `{ url, html }`.
       *
       * Not the field's state and not a paste. `handoff` (one f, lib/handoff.js)
       * is a different thing entirely -- what the start page leaves behind for
       * this view; this is a whole page arriving from another tab. */
      handover: null,
      /* The nonce this tab was opened with, while the other tab has not
       * answered yet. Two things are checked before a document is taken: the
       * message comes from the window that opened this one, and it carries
       * this nonce. The sender's origin cannot be checked -- it is whichever
       * portal the user was looking at -- so the nonce stands in for it. */
      handoverNonce: "",
      handoverWaiting: false,
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
      /* What a model read out of the listing, already through the Beleg gate on
       * the server. Empty for every listing the deterministic readers settled,
       * which is most of them. */
      modelIndicia: [],
      // Bumped to remount the search rather than reuse a finished one.
      searchRun: 0,
      draft: null,
      doubt: null,
      /** The parcels around the resolved point, for the user to choose from. */
      choices: [],
      /** The keys of the parcels the plot is made of. A plot is a set of
       *  parcels, so this is what the map's clicks add to and take from. */
      selection: [],
      /** Why the last click did not do what it looked like it would. */
      selectionNote: null,
      /** What a click does: replace the plot's parcel, or add to it. Replacing
       *  is the default because correcting the parcel is the common case. */
      composing: false,
      /** Chosen parcels the drawn outline does not reach — the plot is in two
       *  pieces. Allowed on the way through, marked in red, and not a plot. */
      detached: [],
      /** Whether the camera stays where it is when the draft changes. True for
       *  a click on the map — the user has to see *which* outline moved — and
       *  false when the correction moves the plot by itself: the map would
       *  otherwise keep showing the parcel the coordinate landed in, which is
       *  the parcel the correction just rejected. */
      holdFrame: false,
      /** The address the search picked, so the cadastre's own Lagebezeichnung
       *  can be checked against it rather than the coordinate being trusted. */
      searchedAddress: null,
      /** The parcel number a Lagebezeichnung match put in place of the one the
       *  coordinate landed in. Null unless it actually differed. */
      corrected: null,
      /** What went wrong while the plot was being reassembled. */
      addError: "",
      // The labels for the stages in `WIZARD_STAGES`, in that order. The
      // parcel and the fields are one step: the fields are three inputs, and
      // the "Passt" between them decided nothing.
      steps: [
        { id: "quelle", name: "Quelle" },
        { id: "suche", name: "Flurstück suchen" },
        { id: "flurstueck", name: "Flurstück und Angaben" }
      ],
    };
  },
  computed: {
    stageIndex() { return WIZARD_STAGES.indexOf(this.stage); },
    /* What each stage needs in order to have anything to show. Only the first
     * one stands on its own: the read fields, the query and the draft live in
     * this component and are gone after a reload. */
    reachable() {
      if (this.stageIndex <= 0) return true;
      if (this.stage === "suche") return Boolean(this.searchQuery);
      return Boolean(this.draft);
    },
    /** How much the reader got, for the folded summary line.
     *
     *  Empty when it got nothing — „0 von 6 Feldern belegt“ is a box that says
     *  it has nothing to show, which is worse than not being there. Typed prose
     *  reaches this state routinely: the extraction endpoint needs a model for
     *  a plain description, while the search's own pattern reader does not. */
    readSummary() {
      const filled = this.readFields.filter(f => f.value).length;
      return filled ? `${filled} von ${this.readFields.length} Feldern belegt` : "";
    },
    computedArea() { return this.draft ? polygonArea(this.draft.polygon) : 0; },
    /** The app's own address, which is what the bookmarklet has to be told:
     *  it runs on the portal's page and knows nothing else about us. */
    appOrigin() { return window.location.origin; },
    bookmarkletLink() { return bookmarkletHref(this.appOrigin); },
  },
  created() {
    this.checkStage();
    this.takeHandoff();
    this.startHandover();
  },
  beforeUnmount() {
    this.stopHandover();
  },
  watch: {
    stage() { this.checkStage(); },
    /* Every outline the Flurstück step settles on gets its street read off the
     * cadastre, so the plan there is already turned to the right side. */
    "draft.polygon"() { this.settleStreet(this.draft); }
  },
  methods: {
    area, euroPerSqm, num,

    /** An input the start page left behind. It is the same input the first
     *  step takes, so it runs through the same two methods — the field is
     *  somewhere else, the work is here. */
    takeHandoff() {
      const input = takeHandoff();
      if (!input) return;
      if (input.resolve) return this.searchPicked(input.resolve);
      if (input.read) return this.readPayload(input.read);
    },

    /** Announce this tab to the bookmarklet that opened it.
     *
     *  The bookmarklet cannot send the document straight away: this app has to
     *  be mounted and listening first, and nothing else tells it when that is.
     *  So the tab it opened says so, and the nonce in its own address is what
     *  it says it with. */
    startHandover() {
      const nonce = this.$route.query[HANDOVER_QUERY];
      if (this.handoverNonce || this.handover) return;
      if (typeof nonce !== "string" || !nonce) return;
      // Opened by hand, or the opener is gone: there is nobody to answer, and
      // the field below is then the right answer without saying anything.
      if (!window.opener) return;
      this.handoverNonce = nonce;
      this.handoverWaiting = true;
      window.addEventListener("message", this.takeHandover);
      // `"*"`, because the portal's origin is not knowable from here — and
      // there is nothing to keep: the nonce is in this tab's own address bar.
      window.opener.postMessage({ w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce }, "*");
    },

    /** The document, once the other tab sends it. Then straight into reading:
     *  the click on the bookmarklet was the instruction. */
    takeHandover(event) {
      const data = event.data;
      if (!this.handoverNonce || event.source !== window.opener) return;
      if (!data || data.w2b !== HANDOVER_PAGE || data[HANDOVER_QUERY] !== this.handoverNonce) return;
      if (typeof data.html !== "string" || !data.html) return;
      this.stopHandover();
      this.handover = {
        url: typeof data.url === "string" ? data.url : "",
        html: data.html.slice(0, PAGE_LIMIT)
      };
      this.readPayload({ kind: "paste", text: "", html: this.handover.html });
    },

    stopHandover() {
      this.handoverNonce = "";
      this.handoverWaiting = false;
      window.removeEventListener("message", this.takeHandover);
    },

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
        this.returnStage = "quelle";
        this.searchedAddress = address ?? null;
        await this.queryCadastre(query, { note: `Gesucht: ${label}` });
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },



    /** A listing to read: a link the server fetches, or text and markup that
     *  came out of the clipboard. Everything lands on the same step — typed
     *  prose used to jump straight into the search, so the same page arrived
     *  at two different places depending on which box it went into, and the
     *  values it *did* carry (area, price) were never shown. */
    async readPayload({ kind, text, html }) {
      this.busy = true;
      this.error = "";
      try {
        this.returnStage = "quelle";
        const response = kind === "url" ? await readListing(text) : await readPage(html || text);
        this.readFields = fieldsFromResponse(response);
        this.description = response?.beschreibung || text;
        this.images = response?.bilder || [];
        // What a model read, already through the Beleg gate on the server: each
        // one carries the sentence it was read from, and the search weighs it
        // like any other clue — below the body text, and never as a filter.
        this.modelIndicia = response?.indizien || [];
        // Straight on. The read values were a step of their own and answered a
        // question nobody had asked yet — they are what the search runs on, so
        // they now travel with it, folded shut.
        this.lookUpParcel();
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
        ...(this.modelIndicia.length ? { indizien: this.modelIndicia } : {})
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
      // Nobody clicked: the address moved the plot, so the map follows it.
      this.holdFrame = false;
      this.corrected = `Flurstück ${corrected.flurstuecke.join(" · ")}`;
      this.selection = [named.properties.kennzeichen];
      this.draft = { ...corrected, bodenrichtwert: plot.bodenrichtwert, brwZone: plot.brwZone,
                     brwReferenceDate: plot.brwReferenceDate,
                     brwReferencePlotArea: plot.brwReferencePlotArea,
                     brwConversionUrl: plot.brwConversionUrl,
                     houseTypeId: plot.houseTypeId, ratio: plot.ratio };
    },

    /** A click on the map, in whichever of the two meanings is switched on.
     *
     * Replacing is the default: the common case is that the coordinate landed
     * on the wrong parcel and one click puts that right. Composing is the other
     * one — a plot is a set of parcels, and then a click adds or removes. */
    async chooseParcel(kennzeichen) {
      if (this.busy || !this.choices.length) return;
      const taken = this.selection.includes(kennzeichen);
      if (!this.composing) {
        if (taken && this.selection.length === 1) return;
        this.holdFrame = true;
        await this.applySelection([kennzeichen]);
        return;
      }
      if (taken && this.selection.length === 1) {
        this.selectionNote = "Ein Grundstück besteht aus mindestens einem Flurstück. "
          + "Erst ein anderes dazunehmen, dann lässt sich dieses abwählen.";
        return;
      }
      this.holdFrame = true;
      await this.applySelection(taken
        ? this.selection.filter(key => key !== kennzeichen)
        : [...this.selection, kennzeichen]);
    },

    /** Which chosen parcels the drawn outline does not contain.
     *
     * Parcels that do not touch are a real set in the register and a shape one
     * outline cannot hold. Refusing the click was worse than allowing it: the
     * way back to a whole plot often leads through a split one — take the
     * middle parcel out, then the far one. So they are marked instead, and the
     * step will not create a plot while any of them stands. */
    /** A feature's centre as `[lon, lat]`, or null when it carries no ring. */
    centreOf(feature) {
      const ring = outerRing(feature?.geometry);
      if (ring.length < 4) return null;
      const n = ring.length;
      return [ring.reduce((s, c) => s + c[0], 0) / n, ring.reduce((s, c) => s + c[1], 0) / n];
    },

    detachedParcels(plot, features) {
      if (!plot?.anchor || !plot.polygon?.length) return [];
      return features
        .filter(feature => {
          const ring = outerRing(feature.geometry);
          if (ring.length < 4) return false;
          return !pointInPolygon(polygonCentroid(toLocal(ring, plot.anchor)), plot.polygon);
        })
        .map(feature => feature.properties?.kennzeichen)
        .filter(Boolean);
    },

    /** Resolve a set of parcel keys into the draft, keeping what the cadastre
     *  cannot know: the name and price the user typed, and the note. */
    async applySelection(keys) {
      this.busy = true;
      this.selectionNote = null;
      try {
        const answer = await resolveParcel({ kennzeichen: keys });
        const kept = {
          name: this.draft.name, askingPrice: this.draft.askingPrice, note: this.draft.note,
          /* Which piece is the plot when the set falls apart: the one around the
             parcel this selection started from, not whichever the register
             listed first. */
          near: this.centreOf(answer.features?.[0])
        };
        const plot = await this.withLandValue(plotFromCadastre(answer, kept));
        this.draft = { ...plot, houseTypeId: this.draft.houseTypeId, ratio: this.draft.ratio };
        this.selection = keys;
        this.detached = this.detachedParcels(plot, answer.features ?? []);
        this.selectionNote = this.detached.length
          ? "Die rot markierten Flurstücke hängen nicht mit dem übrigen Grundstück "
            + "zusammen. Gezeichnet ist nur der zusammenhängende Teil: entweder die "
            + "markierten wieder abwählen oder das Flurstück dazwischen dazunehmen."
          : null;
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
      this.detached = [];
      this.selection = (answer.features ?? [])
        .map(feature => feature.properties?.kennzeichen)
        .filter(Boolean);
      this.goToStage("flurstueck");
      // After the step is on screen: the choice is an aid, not a precondition.
      await this.loadChoices(plot, extra);
    },

    /** The street front for this draft. A failure keeps the longest-edge guess
     *  and `create` asks once more; an answer for a draft that has since been
     *  replaced lands on that old object and changes nothing on screen. */
    async settleStreet(draft) {
      if (!draft) return;
      try { await settleStreetFront(draft); } catch { /* the guess stands */ }
    },

    /** Enter does what the button does, and only when the button is the plain
     *  one: „Trotzdem anlegen" overrides a doubt, and overriding it should
     *  take a click on the words that say so, not a key pressed in a field. */
    createByEnter(event) {
      if (event.isComposing || this.busy || this.detached.length || this.doubt) return;
      this.create();
    },

    async create() {
      // Before the house is seated: it is turned to the street edge.
      if (this.draft.streetFront === undefined) await this.settleStreet(this.draft);
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

/* The field is a panel of its own inside the step. */
.wizard__query{ padding: var(--w2b-space-4); }

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
/* The unit sits beside the box, not in it: what is typed here goes to the
   cadastre, and „600 m²" is not a number. */
.suggestion__eingabe{ display: flex; align-items: baseline; gap: var(--w2b-space-2); }
.suggestion__eingabe input{ flex: 1 1 auto; min-width: 0; }
.suggestion__einheit{ flex: 0 0 auto; color: var(--w2b-muted); font-size: var(--w2b-text-s); }

/* What was read off the page. Folded shut, because it is what the search is
   already running on rather than something to approve first. */
.gelesen{
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-m);
  background: var(--w2b-surface-sunken);
  padding: 0 var(--w2b-space-4);
}
.gelesen > summary{
  display: flex; align-items: baseline; gap: var(--w2b-space-3); flex-wrap: wrap;
  padding: var(--w2b-space-3) 0; cursor: pointer; list-style: revert;
}
.gelesen > summary::marker{ color: var(--w2b-muted); }
.gelesen__titel{ font-weight: 600; }
.gelesen__zahl{ color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.gelesen[open]{ padding-bottom: var(--w2b-space-4); }
.gelesen .subtitle{ margin-top: 0; }
.gelesen .suggestions{ margin-top: var(--w2b-space-3); }
.gelesen .row{ margin-top: var(--w2b-space-3); }

.check-grid{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: var(--w2b-space-4); align-items: start; }
@media (max-width: 900px){ .check-grid{ grid-template-columns: 1fr; } }
.value-list{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.value-list dt, .value-list dd{ padding: 8px var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line-faint); margin: 0; display: flex; align-items: center; }
.value-list dt{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.value-list dd{ justify-content: flex-end; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-s); font-variant-numeric: tabular-nums; text-align: right; }
/* No rule above it here: the value list it follows is the panel's whole body. */
.panel__footnote{ border-top: 0; }
</style>
