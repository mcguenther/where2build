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
          Die Angaben widersprechen sich. Gesucht wird nach der zuverlässigsten —
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
        </button>
      </div>
    </section>

    <div class="suche__buehne">
      <div class="panel suche__karte">
        <EvidenceMap ref="karte" :candidates="candidates" :district-outline="districtOutline"
                     :areas="areas" :huelle="huelle" :refuted-pin="refutedPin"
                     :status="status" :flight="flight" :height="mapHeight" @select="pick" />
      </div>

      <!-- The protocol. Every entry can be looked up and switched off: a
           contradiction nobody can check is one nobody can resolve. -->
      <div class="panel suche__protokoll">
        <div class="panel__head">
          <h3>Indizien</h3>
          <div class="spacer"></div>
          <span v-if="queued" class="chip">{{ queued }} wartet</span>
          <button v-if="queued" type="button" class="btn btn--quiet btn--small" @click="skip">
            Alles zeigen
          </button>
        </div>
        <ul class="indizien">
          <li v-for="indiz in shownIndicia" :key="indiz.id"
              :class="{ 'indizien--verworfen': indiz.verworfen }">
            <button type="button" class="indizien__zeile" @click="focusIndiz(indiz)">
              <span class="indizien__staerke" :style="{ opacity: 0.25 + 0.75 * indiz.sicherheit }"></span>
              <span class="indizien__text">
                <b>{{ indiz.text }}</b>
                <span class="indizien__meta">
                  {{ sourceLabel(indiz.quelle) }} · Sicherheit {{ percent(indiz.sicherheit) }}
                </span>
                <span v-if="indiz.beleg" class="indizien__beleg">„{{ indiz.beleg }}“</span>
                <span v-if="indiz.verworfen_grund" class="indizien__grund">{{ indiz.verworfen_grund }}</span>
              </span>
            </button>
            <button type="button" class="indizien__schalter"
                    :aria-pressed="String(!indiz.verworfen)"
                    :title="indiz.verworfen ? 'Wieder berücksichtigen' : 'Ohne dieses Indiz suchen'"
                    @click="toggle(indiz)">
              {{ indiz.verworfen ? "+" : "×" }}
            </button>
          </li>
        </ul>
        <ol v-if="protocol.length" class="protokoll">
          <li v-for="(step, i) in protocol" :key="i">{{ step }}</li>
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
        Die Reihenfolge ordnet nur — entschieden wird sie nicht. Ausgeschieden ist hier
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
import { area } from "../lib/format.js";

const SOURCE_LABELS = {
  nutzer: "von Hand",
  bild: "aus einem Bild gelesen",
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
      protocol: [],
      queued: 0,
      queueStep: DWELL_MS,
      chosen: null,
      discarded: [],
      decisions: {}
    };
  },
  computed: {
    /** Still going as long as anything is unplayed. A heading that says
     *  „Ergebnis“ over a half-drawn map is worse than one that waits. */
    running() { return this.streaming || this.queued > 0; },
    statusLabel() { return STATUS_LABEL[this.status] ?? "Suche"; },
    sentence() { return this.status ? verdictSentence(this.status, this.candidates.length, this.huelle) : ""; },
    shownIndicia() { return this.indicia; },
    chosenCandidate() { return this.candidates.find(c => c.id === this.chosen) ?? null; },
    /** How long the camera may take, matched to how fast the clues are playing.
     *
     *  A 900 ms flight started every 240 ms spends the whole run interrupting
     *  itself, which is the twitch the queue exists to prevent. */
    flight() { return Math.max(260, Math.min(FLIGHT_MS, this.queueStep * 1.6)); },
    /** The pin, once something stronger has placed the plot elsewhere.
     *
     *  It stays on the map struck through rather than vanishing: whoever opens
     *  the listing sees this point, so an interface pointing somewhere else
     *  owes them the reason. */
    refutedPin() {
      if (!this.candidates.length) return null;
      const pin = this.indicia.find(indiz => indiz.art === "pin");
      if (!pin) return null;
      const [lat, lon] = pin.wert.split(",").map(Number);
      return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
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
        hint: "", requests: 0, protocol: [], chosen: null,
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
        if (event.text) this.protocol = [...this.protocol, event.text];
      } else if (event.art === "indiz") {
        const rest = this.indicia.filter(indiz => indiz.id !== event.indiz.id);
        this.indicia = [...rest, event.indiz].sort((a, b) => b.sicherheit - a.sicherheit);
      } else if (event.art === "konflikt") {
        const rest = this.conflicts.filter(conflict => conflict.art !== event.konflikt.art);
        this.conflicts = [...rest, event.konflikt];
      } else if (event.art === "gebiete") {
        this.areas = event.gebiete || [];
      } else if (event.art === "kandidaten") {
        this.candidates = event.kandidaten || [];
      } else if (event.art === "ergebnis") {
        this.status = event.status;
        this.candidates = event.kandidaten || [];
        this.huelle = event.huelle || null;
        this.districtOutline = event.gemarkung_umriss || null;
        if (event.gebiete) this.areas = event.gebiete;
        this.hint = event.text || "";
        this.requests = event.anfragen || 0;
      }
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

    /** Clicking a clue jumps to it. Nobody waits for the animation. */
    focusIndiz(indiz) {
      this.skip();
      const candidate = this.candidates.find(c => c.properties.flurstuecksnummer === indiz.wert);
      const geometry = candidate?.geometry || this.districtOutline || this.huelle?.geometry;
      this.$refs.karte?.focusOn?.(geometry);
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

.indizien{ list-style: none; margin: 0; padding: 0; }
.indizien li{ display: flex; align-items: flex-start; border-bottom: 1px solid var(--w2b-line-faint); }
.indizien__zeile{
  flex: 1; display: flex; gap: var(--w2b-space-3); align-items: flex-start; text-align: left;
  background: none; border: 0; cursor: pointer; padding: 10px var(--w2b-space-3) 10px var(--w2b-space-4);
}
.indizien__zeile:hover{ background: var(--w2b-primary-veil); }
.indizien__staerke{
  flex: none; width: 5px; align-self: stretch; min-height: 26px; border-radius: 3px;
  background: var(--w2b-map-selection);
}
.indizien__text{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.indizien__text b{ font-size: var(--w2b-text-s); font-weight: 600; }
.indizien__meta{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.indizien__beleg{ font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted); line-height: 1.5; overflow-wrap: anywhere; }
.indizien__grund{ font-size: var(--w2b-text-xs); color: var(--w2b-error); }
.indizien--verworfen .indizien__text b{ text-decoration: line-through; color: var(--w2b-muted); }
.indizien--verworfen .indizien__staerke{ background: var(--w2b-line); }
.indizien__schalter{
  flex: none; align-self: center; margin-right: var(--w2b-space-3);
  width: 26px; height: 26px; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--w2b-line); background: var(--w2b-surface);
  color: var(--w2b-muted); font-size: 14px; line-height: 1;
}
.indizien__schalter:hover{ border-color: var(--w2b-error); color: var(--w2b-error); }

.protokoll{
  margin: var(--w2b-space-3) 0 0; padding: var(--w2b-space-3) var(--w2b-space-4) var(--w2b-space-4) 30px;
  border-top: 1px solid var(--w2b-line-faint);
  color: var(--w2b-muted); font-size: var(--w2b-text-xs); line-height: 1.7;
}

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
