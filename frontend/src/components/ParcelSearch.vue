<template>
  <div class="suche stack">
    <!-- The verdict, before anything else. Three outcomes and none of them is
         "probably": a search that always produces an answer eventually
         produces a wrong one. -->
    <div class="suche__urteil" :class="`suche__urteil--${status || 'laeuft'}`" role="status">
      <div>
        <p class="eyebrow">{{ running ? "Suche läuft" : "Ergebnis" }}</p>
        <h2>{{ running ? phaseText : statusLabel }}</h2>
        <p class="suche__satz">{{ running ? "" : sentence }}</p>
        <p v-if="hint && !running" class="suche__hinweis">{{ hint }}</p>
      </div>
      <div class="spacer"></div>
      <p v-if="requests" class="suche__kosten">
        {{ requests }} {{ requests === 1 ? "Abfrage" : "Abfragen" }} ans Kataster
      </p>
    </div>

    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <!-- A contradiction is never resolved quietly. The most trustworthy
         reading is followed, said out loud, and can be replaced. -->
    <section v-for="conflict in conflicts" :key="conflict.art" class="konflikt">
      <div class="konflikt__kopf">
        <b>{{ conflict.frage }}</b>
        <span v-if="conflict.aufgeloest_durch" class="konflikt__geloest">
          {{ conflict.aufgeloest_durch }}
        </span>
        <span v-else class="konflikt__offen">
          Die Angaben widersprechen sich. Gesucht wird nach der zuverlässigsten;
          hier lässt sich das ändern.
        </span>
      </div>
      <div class="konflikt__optionen">
        <button v-for="option in optionsOf(conflict)" :key="option.id" type="button"
                class="konflikt__option" :aria-pressed="String(conflict.gewaehlt === option.id)"
                @click="choose(conflict.art, option.id)">
          <span class="konflikt__wert">{{ option.wert }}</span>
          <span class="konflikt__quelle">{{ sourceLabel(option.quelle) }}</span>
          <span v-if="option.beleg" class="konflikt__beleg">{{ option.beleg }}</span>
          <!-- A Beleg read off a picture is a line of OCR text, which is the
               least checkable evidence in the whole search. So the sheet comes
               with it: the choice is made against the document, not against a
               transcription of it. -->
          <img v-if="option.bild_url" class="konflikt__bild" :src="option.bild_url"
               alt="Das Bild, aus dem diese Angabe gelesen wurde" loading="lazy">
        </button>
      </div>
      <p v-if="optionsOf(conflict).some(o => o.bild_url)" class="konflikt__fussnote">
        Auf einem Katasterauszug stehen die Nummern der Nachbarflurstücke mit auf der
        Karte. Gelesen wird nur die beschriftete Angabe im Kopf des Auszugs; steht dort
        mehr als eine, entscheidet das Bild.
      </p>
    </section>

    <div class="suche__buehne">
      <div class="panel suche__karte">
        <!-- Zooming away from the answer and not finding the way back was the
             one thing the map could not do. Both buttons are always in reach. -->
        <div class="panel__head suche__kartenkopf">
          <!-- The photograph is the default: an advert shows pictures of the
               plot, and those are recognisable against an orthophoto in a way
               they never are against a street map. -->
          <div class="grundwahl" role="group" aria-label="Kartenhintergrund">
            <button type="button" :class="['grundwahl__knopf', { 'grundwahl__knopf--an': ground === 'site' }]"
                    :aria-pressed="String(ground === 'site')" @click="ground = 'site'">
              Luftbild
            </button>
            <button type="button" :class="['grundwahl__knopf', { 'grundwahl__knopf--an': ground === 'map' }]"
                    :aria-pressed="String(ground === 'map')" @click="ground = 'map'">
              Karte
            </button>
          </div>
          <div class="spacer"></div>
          <button type="button" class="btn btn--quiet btn--small"
                  :disabled="!resultGeometry" @click="focusResult">
            Zum Ergebnis
          </button>
          <button type="button" class="btn btn--quiet btn--small"
                  :disabled="!everything.length" @click="focusEverything">
            Alles zeigen
          </button>
        </div>
        <EvidenceMap ref="karte" :candidates="candidates" :district-outline="districtOutline"
                     :areas="areas" :huelle="huelle" :refuted-pin="refutedPin" :pin="pin"
                     :status="status" :flight="flight" :height="mapHeight"
                     :ground="ground" :highlighted="highlighted" @select="pick" />
        <p v-if="ground === 'site'" class="panel__footnote">
          Luftbild und Straßen vom GeoSN. Die amtlichen Flurstücksgrenzen zeichnet der
          Dienst erst ab Zoomstufe {{ parcelOutlineZoom }}; darüber liefert er ein leeres Bild.
        </p>
      </div>

      <!-- The course of the search, in the order it happened. One list, not
           two: the clues used to be sorted by confidence and the steps kept
           separately, so afterwards nobody could tell what came first. Every
           row that stands for something on the map jumps to it, and a clue can
           still be switched off — a contradiction nobody can check is one
           nobody can resolve. -->
      <div class="panel suche__protokoll">
        <div class="panel__head">
          <h3>Verlauf</h3>
          <div class="spacer"></div>
          <span v-if="queued" class="chip">{{ queued }} wartet</span>
          <button v-if="queued" type="button" class="btn btn--quiet btn--small" @click="skip">
            Rest zeigen
          </button>
        </div>
        <ol class="verlauf">
          <li v-for="step in steps" :key="step.n"
              class="verlauf__schritt" :class="[
                `verlauf__schritt--${step.kind}`,
                {
                  'verlauf--verworfen': step.indiz && indizOf(step).verworfen,
                  'verlauf--gezeigt': shownStep === step.n
                }
              ]">
            <span class="verlauf__nr" aria-hidden="true">{{ step.n }}</span>

            <button v-if="step.kind === 'indiz'" type="button" class="verlauf__zeile"
                    @click="focusStep(step)">
              <span class="verlauf__staerke"
                    :style="{ opacity: 0.25 + 0.75 * indizOf(step).sicherheit }"></span>
              <span class="verlauf__text">
                <b>{{ indizOf(step).text }}</b>
                <span class="verlauf__meta">
                  {{ sourceLabel(indizOf(step).quelle) }} ·
                  Sicherheit {{ percent(indizOf(step).sicherheit) }}
                </span>
                <span v-if="indizOf(step).beleg" class="verlauf__beleg">„{{ indizOf(step).beleg }}“</span>
                <span v-if="indizOf(step).verworfen_grund" class="verlauf__grund">
                  {{ indizOf(step).verworfen_grund }}
                </span>
              </span>
            </button>

            <button v-else type="button" class="verlauf__zeile verlauf__zeile--schritt"
                    :disabled="!hasFocus(step)" @click="focusStep(step)">
              <span class="verlauf__text">
                <span class="verlauf__marke">{{ stepLabel(step) }}</span>
                {{ step.text }}
              </span>
            </button>

            <button v-if="step.kind === 'indiz'" type="button" class="verlauf__schalter"
                    :aria-pressed="String(!indizOf(step).verworfen)"
                    :title="indizOf(step).verworfen ? 'Wieder berücksichtigen' : 'Ohne dieses Indiz suchen'"
                    @click="toggle(indizOf(step))">
              {{ indizOf(step).verworfen ? "+" : "×" }}
            </button>
          </li>
        </ol>
      </div>
    </div>

    <!-- The candidates, equally weighted while more than one survives. -->
    <div v-if="candidates.length" class="panel">
      <div class="panel__head">
        <h3>{{ candidates.length === 1 ? "Das Flurstück" : `${candidates.length} mögliche Flurstücke` }}</h3>
        <div class="spacer"></div>
        <span class="chip">ALKIS</span>
      </div>
      <table class="kandidaten">
        <thead>
          <tr><th>Flurstück</th><th>Gemarkung</th><th class="num">Fläche</th><th>Lage</th><th>Nutzung</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="candidate in candidates" :key="candidate.id"
              :class="{ 'kandidaten--gewaehlt': chosen === candidate.id }">
            <td class="mono">{{ candidate.properties.flurstuecksnummer }}</td>
            <td>{{ candidate.properties.gemarkung }}</td>
            <td class="num mono">{{ area(candidate.properties.flaeche_amtlich_m2) }}</td>
            <td>{{ lage(candidate.properties.lagebezeichnung) }}</td>
            <td>{{ candidate.properties.nutzung || "—" }}</td>
            <td class="num">
              <button type="button" class="btn btn--quiet btn--small" @click="pick(candidate.id)">
                {{ chosen === candidate.id ? "Gewählt" : "Wählen" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="candidates.length > 1" class="panel__footnote">
        Die Reihenfolge ordnet nur; entschieden wird sie nicht. Ausgeschieden ist hier
        niemand: Was übrig bleibt, hat jede amtliche Prüfung bestanden.
      </p>
    </div>

    <div class="row">
      <button type="button" class="btn" :disabled="!chosenCandidate" @click="$emit('confirm', chosenCandidate)">
        {{ status === "bestaetigt" ? "Übernehmen" : "Dieses Flurstück übernehmen" }}
      </button>
      <button type="button" class="btn btn--quiet" :disabled="streaming" @click="start">
        Suche wiederholen
      </button>
      <button type="button" class="btn btn--quiet" @click="$emit('manual')">
        Von Hand eintragen
      </button>
    </div>
  </div>
</template>

<script>
/**
 * The search, from the listing to the parcel — and to what is settled when no
 * single parcel can be named.
 *
 * The interface has one job beyond showing the answer: making the run
 * checkable. Every Indiz carries the sentence it came from, every contradiction
 * is named rather than resolved quietly, and either can be switched off, which
 * runs the search again — it is cheap enough for that.
 */
import EvidenceMap from "./EvidenceMap.vue";
import { DWELL_MS, FLIGHT_MS, StepQueue, prefersReducedMotion } from "../lib/evidence.js";
import { runSearch, STATUS_LABEL, verdictSentence } from "../lib/search.js";
import { PARCEL_OUTLINE_MIN_ZOOM } from "../lib/basemap.js";
import { area } from "../lib/format.js";

/** What each phase of the run is called in the course list. The backend names
 *  them; this is the German the reader sees next to the step. */
const PHASE_LABELS = {
  ernten: "Gelesen",
  raum: "Raum",
  treppe: "Toleranz",
  gegenprobe: "Gegenprobe",
  bilder: "Bilder",
  nummer: "Nummer",
  strasse: "Straße"
};

const SOURCE_LABELS = {
  nutzer: "von Hand",
  bild: "aus einem Bild der Anzeige gelesen",
  attribut: "Attributliste der Anzeige",
  fliesstext: "Anzeigentext",
  modell: "Modell",
  standortfeld: "Standortfeld",
  pin: "Kartenpunkt der Anzeige"
};

export default {
  name: "ParcelSearch",
  components: { EvidenceMap },
  props: {
    /** What is known about the listing; the shape `POST /api/parcels/search` takes. */
    query: { type: Object, required: true },
    mapHeight: { type: Number, default: 460 },
    /** Off in tests: they assert on the finished state, not on the pacing. */
    paced: { type: Boolean, default: true }
  },
  emits: ["confirm", "manual"],
  data() {
    return {
      // Whether the stream is still open. What the heading follows is `running`
      // below, which also waits for the queue: an answer that is still being
      // played out is not a finished run.
      streaming: false,
      error: "",
      status: null,
      indicia: [],
      conflicts: [],
      candidates: [],
      huelle: null,
      districtOutline: null,
      // The districts the search is prepared to look in, with their outlines.
      areas: [],
      hint: "",
      requests: 0,
      phaseText: "Angaben werden gelesen …",
      // The run in the order it happened. Every event that reaches `apply`
      // becomes one entry, so the sequence is a fact rather than a
      // reconstruction — the clues themselves are still re-sorted by
      // confidence for the conflict options, and that used to be the only
      // list there was.
      steps: [],
      queued: 0,
      queueStep: DWELL_MS,
      chosen: null,
      // Which entry of the Verlauf is being shown, and what it points at. The
      // map marks it: a jump that only moves the camera arrives somewhere
      // without saying which of the things on it was the reason.
      shownStep: null,
      highlighted: null,
      // The ground under the drawing. Remembered per visit only: which
      // backdrop helps depends on the plot in front of you.
      ground: "site",
      discarded: [],
      decisions: {}
    };
  },
  computed: {
    /** Still going as long as anything is unplayed. A heading that says
     *  „Ergebnis“ over a half-drawn map is worse than one that waits. */
    running() { return this.streaming || this.queued > 0; },
    statusLabel() { return STATUS_LABEL[this.status] ?? "Suche"; },
    parcelOutlineZoom() { return PARCEL_OUTLINE_MIN_ZOOM; },
    sentence() {
      return this.status
        ? verdictSentence(this.status, this.candidates.length, this.huelle, this.hint)
        : "";
    },
    chosenCandidate() { return this.candidates.find(c => c.id === this.chosen) ?? null; },
    /** Where „Zum Ergebnis“ goes: the parcel if there is one, else whatever
     *  the answer could still name. */
    resultGeometry() {
      if (this.chosenCandidate?.geometry) return this.chosenCandidate.geometry;
      if (this.candidates.length === 1) return this.candidates[0].geometry;
      return this.huelle?.geometry ?? null;
    },
    /** Everything the run put on the map, for the way back out. */
    everything() {
      return [
        ...this.candidates.map(candidate => candidate.geometry),
        this.huelle?.geometry,
        ...this.areas.map(area => area.geometry),
        this.districtOutline
      ].filter(Boolean);
    },
    /** How long the camera may take, matched to how fast the clues are playing.
     *
     *  A flight started before the last one landed spends the whole run
     *  interrupting itself, which is the twitch the queue exists to prevent —
     *  so the duration is tied to the step rather than fixed, and the floor
     *  moved with it. */
    flight() { return Math.max(520, Math.min(FLIGHT_MS, this.queueStep * 1.6)); },
    /** The pin, once something stronger has placed the plot elsewhere.
     *
     *  It stays on the map struck through rather than vanishing: whoever opens
     *  the listing sees this point, so an interface pointing somewhere else
     *  owes them the reason. */
    /** The point the advert itself names, as soon as it is read. */
    pin() {
      const indiz = this.indicia.find(entry => entry.art === "pin");
      if (!indiz) return null;
      const [lat, lon] = String(indiz.wert).split(",").map(Number);
      return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
    },
    refutedPin() {
      return this.candidates.length ? this.pin : null;
    }
  },
  mounted() { this.start(); },
  beforeUnmount() {
    this._queue?.stop();
    this._abort?.abort();
  },
  watch: {
    // A single survivor is the choice; it would be perverse to make someone
    // click the only row.
    candidates(list) { if (list.length === 1) this.chosen = list[0].id; }
  },
  methods: {
    area,
    percent(value) { return `${Math.round((value ?? 0) * 100)} %`; },
    sourceLabel(key) { return SOURCE_LABELS[key] ?? key; },
    lage(value) { return !value || /ohne lage/i.test(value) ? "—" : value; },
    optionsOf(conflict) {
      return conflict.optionen.map(id => this.indicia.find(i => i.id === id)).filter(Boolean);
    },

    start() {
      this._queue?.stop();
      this._abort?.abort();
      this._abort = new AbortController();
      Object.assign(this, {
        streaming: true, error: "", status: null, indicia: [], conflicts: [],
        candidates: [], huelle: null, districtOutline: null, areas: [],
        hint: "", requests: 0, steps: [], chosen: null,
        shownStep: null, highlighted: null,
        phaseText: "Angaben werden gelesen …"
      });

      // The queue is what keeps the map readable. Clues arrive unevenly and
      // sometimes all at once — behind a proxy that buffers, the whole run
      // lands in one chunk — and three camera moves in one frame is a twitch,
      // not an animation.
      this._queue = new StepQueue({ reduced: !this.paced || prefersReducedMotion() });
      this._queue.onStep = event => this.apply(event);
      this._queue.onIdle = () => { this.queued = 0; };

      runSearch(
        // Built fresh rather than written back into the prop: what the user
        // switched off belongs to this component, and a prop the child edits
        // is a prop whose owner cannot tell what it holds.
        { ...this.query, verworfen: this.discarded, entscheidungen: this.decisions },
        event => {
          this._queue.push(event);
          this.queued = this._queue.waiting;
        },
        { signal: this._abort.signal }
      )
        .catch(error => {
          if (error?.name === "AbortError") return;
          this.error = error.message;
        })
        .finally(() => { this.streaming = false; });
    },

    /** One line of the stream, once the queue lets it through. */
    apply(event) {
      this.queued = this._queue?.waiting ?? 0;
      this.queueStep = this._queue?.step ?? DWELL_MS;
      if (event.art === "phase") {
        this.phaseText = event.text || this.phaseText;
        if (event.text) this.record({ kind: "phase", phase: event.phase, text: event.text });
      } else if (event.art === "indiz") {
        const rest = this.indicia.filter(indiz => indiz.id !== event.indiz.id);
        this.indicia = [...rest, event.indiz].sort((a, b) => b.sicherheit - a.sicherheit);
        // Recorded by id, not by value: the same clue arrives again when a
        // conflict is settled, and the entry has to follow it rather than
        // freeze the first wording.
        this.record({ kind: "indiz", indiz: event.indiz.id });
      } else if (event.art === "konflikt") {
        const rest = this.conflicts.filter(conflict => conflict.art !== event.konflikt.art);
        this.conflicts = [...rest, event.konflikt];
      } else if (event.art === "gebiete") {
        this.areas = event.gebiete || [];
      } else if (event.art === "kandidaten") {
        this.candidates = event.kandidaten || [];
        this.record({
          kind: "kandidaten",
          text: this.candidateLine(event.anzahl ?? this.candidates.length),
          geometries: this.candidates.map(candidate => candidate.geometry).filter(Boolean)
        });
      } else if (event.art === "ergebnis") {
        this.status = event.status;
        this.candidates = event.kandidaten || [];
        this.huelle = event.huelle || null;
        this.districtOutline = event.gemarkung_umriss || null;
        if (event.gebiete) this.areas = event.gebiete;
        this.hint = event.text || "";
        this.requests = event.anfragen || 0;
        this.record({ kind: "ergebnis", text: this.huelle?.text || this.statusLabel });
      }
    },

    /** One entry in the course of the run. */
    record(step) {
      this.steps = [...this.steps, { ...step, n: this.steps.length + 1 }];
    },

    indizOf(step) {
      return this.indicia.find(indiz => indiz.id === step.indiz) ?? {};
    },

    candidateLine(count) {
      if (count === 1) return "1 Flurstück bleibt stehen";
      return `${count} Flurstücke bleiben stehen`;
    },

    stepLabel(step) {
      if (step.kind === "kandidaten") return "Kandidaten";
      if (step.kind === "ergebnis") return "Ergebnis";
      return PHASE_LABELS[step.phase] ?? "Schritt";
    },

    skip() {
      this._queue?.flush();
      this.queued = 0;
    },

    /** Switch an Indiz off — and search again without it. It is cheap enough. */
    toggle(indiz) {
      this.discarded = indiz.verworfen
        ? this.discarded.filter(id => id !== indiz.id)
        : [...this.discarded, indiz.id];
      this.rerun();
    },

    choose(art, id) {
      this.decisions = { ...this.decisions, [art]: id };
      this.rerun();
    },

    rerun() { this.start(); },

    /**
     * What one entry stands for on the map.
     *
     * Resolved when it is clicked rather than when it was recorded: a clue
     * arrives before the outline it names is fetched — the districts turn up
     * in the „raum“ step, several clues later — so anything captured at the
     * time would have been null for exactly the rows worth clicking.
     */
    focusOf(step) {
      if (step.kind === "ergebnis") return this.resultGeometry;
      if (step.kind === "kandidaten") {
        return step.geometries?.length ? step.geometries : null;
      }
      if (step.kind !== "indiz") return null;

      const indiz = this.indizOf(step);
      if (indiz.art === "flurstueck") {
        const named = this.candidates.find(
          candidate => candidate.properties.flurstuecksnummer === indiz.wert
        );
        if (named?.geometry) return named.geometry;
      }
      if (indiz.art === "gemarkung") {
        const area = this.areas.find(entry => entry.name === indiz.wert);
        if (area?.geometry) return area.geometry;
        return this.districtOutline;
      }
      if (indiz.art === "pin") {
        const [lat, lon] = String(indiz.wert).split(",").map(Number);
        if (Number.isFinite(lat) && Number.isFinite(lon)) {
          return { type: "Point", coordinates: [lon, lat] };
        }
        return null;
      }
      // Area, street, municipality, place: constraints over the whole set
      // rather than one thing on the map, so they frame what survived them.
      const candidates = this.candidates.map(candidate => candidate.geometry).filter(Boolean);
      if (candidates.length) return candidates;
      return this.huelle?.geometry || this.districtOutline;
    },

    hasFocus(step) {
      const geometry = this.focusOf(step);
      return Array.isArray(geometry) ? geometry.length > 0 : Boolean(geometry);
    },

    /** Clicking an entry jumps to it *and* marks it. Nobody waits for the
     *  animation, and nobody has to guess what the map just moved to. */
    focusStep(step) {
      this.skip();
      const geometry = this.focusOf(step);
      if (!geometry) return;
      this.shownStep = step.n;
      this.highlighted = geometry;
      this.$refs.karte?.focusOn?.(geometry);
    },

    focusResult() {
      this.skip();
      if (!this.resultGeometry) return;
      this.shownStep = null;
      this.highlighted = this.resultGeometry;
      this.$refs.karte?.focusOn?.(this.resultGeometry);
    },

    focusEverything() {
      this.skip();
      if (!this.everything.length) return;
      // Showing everything is the opposite of pointing at one thing.
      this.shownStep = null;
      this.highlighted = null;
      this.$refs.karte?.focusOn?.(this.everything);
    },

    pick(id) {
      this.chosen = id;
      const candidate = this.candidates.find(c => c.id === id);
      if (candidate) this.$refs.karte?.focusOn?.(candidate.geometry);
    }
  }
};
</script>

<style scoped>
.suche__urteil{
  display: flex; align-items: flex-start; gap: var(--w2b-space-4); flex-wrap: wrap;
  padding: var(--w2b-space-4) var(--w2b-space-5);
  border: 1.5px solid var(--w2b-line); border-left-width: 5px;
  border-radius: var(--w2b-radius-m); background: var(--w2b-surface);
}
.suche__urteil h2{ margin: 2px 0 0; font-size: var(--w2b-text-xl); }
.suche__urteil--bestaetigt{ border-left-color: var(--w2b-primary); }
.suche__urteil--mehrdeutig{ border-left-color: var(--w2b-secondary); }
.suche__urteil--erfolglos{ border-left-color: var(--w2b-error); }
.suche__urteil--laeuft{ border-left-color: var(--w2b-line); }
.suche__satz{ margin: var(--w2b-space-2) 0 0; color: var(--w2b-graphite); font-size: var(--w2b-text-s); max-width: 74ch; }
.suche__hinweis{ margin: var(--w2b-space-2) 0 0; color: var(--w2b-muted); font-size: var(--w2b-text-s); max-width: 74ch; }
.suche__kosten{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); margin: 0; }

.konflikt{
  padding: var(--w2b-space-4); border: 1.5px dashed var(--w2b-secondary);
  border-radius: var(--w2b-radius-m); background: var(--w2b-secondary-veil);
}
.konflikt__kopf{ display: flex; flex-direction: column; gap: 3px; margin-bottom: var(--w2b-space-3); }
.konflikt__offen, .konflikt__geloest{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.konflikt__geloest{ color: var(--w2b-primary); }
.konflikt__optionen{ display: flex; gap: var(--w2b-space-2); flex-wrap: wrap; }
.konflikt__option{
  display: flex; flex-direction: column; gap: 2px; text-align: left; cursor: pointer;
  padding: var(--w2b-space-2) var(--w2b-space-4); min-width: 180px; max-width: 320px;
  border: 1.5px solid var(--w2b-line); border-radius: var(--w2b-radius-s);
  background: var(--w2b-surface);
}
.konflikt__option[aria-pressed="true"]{ border-color: var(--w2b-primary); background: var(--w2b-primary-veil); }
.konflikt__wert{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-m); }
.konflikt__quelle{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.konflikt__beleg{
  font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted);
  line-height: 1.45; overflow-wrap: anywhere;
}

.suche__buehne{ display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: var(--w2b-space-4); align-items: start; }
@media (max-width: 900px){ .suche__buehne{ grid-template-columns: 1fr; } }
.suche__karte{ padding: var(--w2b-space-3); }
.suche__protokoll{ max-height: 560px; overflow-y: auto; }

.verlauf{ list-style: none; margin: 0; padding: 0; counter-reset: none; }
.verlauf__schritt{
  display: flex; align-items: flex-start; gap: var(--w2b-space-2);
  border-bottom: 1px solid var(--w2b-line-faint);
}
/* The number is the point of this list: the order is what was missing. */
.verlauf__nr{
  flex: none; width: 26px; padding-top: 11px; text-align: right;
  font-family: var(--w2b-font-mono); font-size: 10px; font-variant-numeric: tabular-nums;
  color: var(--w2b-muted);
}
.verlauf__zeile{
  flex: 1; display: flex; gap: var(--w2b-space-3); align-items: flex-start; text-align: left;
  background: none; border: 0; cursor: pointer; padding: 10px var(--w2b-space-3) 10px 6px;
  min-width: 0;
}
.verlauf__zeile:hover:not(:disabled){ background: var(--w2b-primary-veil); }
.verlauf__zeile:disabled{ cursor: default; }
.verlauf__staerke{
  flex: none; width: 5px; align-self: stretch; min-height: 26px; border-radius: 3px;
  background: var(--w2b-map-selection);
}
.verlauf__text{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.verlauf__text b{ font-size: var(--w2b-text-s); font-weight: 600; }
.verlauf__meta{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.verlauf__beleg{
  font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted);
  line-height: 1.5; overflow-wrap: anywhere;
}
.verlauf__grund{ font-size: var(--w2b-text-xs); color: var(--w2b-error); }

/* A step of the search reads quieter than a clue: it is what the search did,
   not what it was told. */
.verlauf__zeile--schritt .verlauf__text{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); line-height: 1.6; }
.verlauf__marke{
  display: inline-block; margin-right: 6px; padding: 1px 6px; border-radius: 999px;
  background: var(--w2b-surface-sunken); border: 1px solid var(--w2b-line-faint);
  font-size: 9.5px; letter-spacing: .05em; text-transform: uppercase; color: var(--w2b-muted);
}
.verlauf__schritt--ergebnis .verlauf__text{ color: var(--w2b-text); font-weight: 600; }
.verlauf__schritt--ergebnis .verlauf__marke{
  border-color: var(--w2b-primary); color: var(--w2b-primary);
}

/* The row whose subject is marked on the map. The two have to refer to each
   other, or a jump is a camera move with no explanation. */
.verlauf--gezeigt{ background: var(--w2b-primary-veil); }
.verlauf--gezeigt .verlauf__nr{ color: var(--w2b-primary); font-weight: 700; }

.verlauf--verworfen .verlauf__text b{ text-decoration: line-through; color: var(--w2b-muted); }
.verlauf--verworfen .verlauf__staerke{ background: var(--w2b-line); }
.verlauf__schalter{
  flex: none; align-self: center; margin-right: var(--w2b-space-3);
  width: 26px; height: 26px; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--w2b-line); background: var(--w2b-surface);
  color: var(--w2b-muted); font-size: 14px; line-height: 1;
}
.verlauf__schalter:hover{ border-color: var(--w2b-error); color: var(--w2b-error); }

/* Three controls in one row do not fit a 390 px panel: without the wrap the
   ground toggle lost its second half to `overflow: hidden`. */
.konflikt__bild{
  display: block; width: 100%; max-width: 260px; margin-top: var(--w2b-space-2);
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s);
  background: var(--w2b-surface);
}
.konflikt__fussnote{
  margin: var(--w2b-space-2) 0 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}

.suche__kartenkopf{ padding-bottom: var(--w2b-space-3); flex-wrap: wrap; gap: var(--w2b-space-2); }
.grundwahl{
  flex: none; display: inline-flex; border: 1px solid var(--w2b-line);
  border-radius: 999px; overflow: hidden;
}
.grundwahl__knopf{ flex: none; white-space: nowrap; }
.grundwahl__knopf{
  border: 0; background: none; cursor: pointer; padding: 4px 12px;
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.grundwahl__knopf--an{ background: var(--w2b-primary); color: var(--w2b-on-primary); }

.kandidaten{ width: 100%; border-collapse: collapse; font-size: var(--w2b-text-s); }
.kandidaten th, .kandidaten td{
  padding: 8px var(--w2b-space-4); text-align: left;
  border-bottom: 1px solid var(--w2b-line-faint);
}
.kandidaten th{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); font-weight: 600; }
.kandidaten .num{ text-align: right; }
.kandidaten .mono{ font-family: var(--w2b-font-mono); font-variant-numeric: tabular-nums; }
.kandidaten--gewaehlt{ background: var(--w2b-primary-veil); }
.panel__footnote{ padding: var(--w2b-space-3) var(--w2b-space-4); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }

@media (max-width: 700px){
  .kandidaten th:nth-child(4), .kandidaten td:nth-child(4),
  .kandidaten th:nth-child(5), .kandidaten td:nth-child(5){ display: none; }
}
</style>
