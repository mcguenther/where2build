<template>
  <section class="panel nearby">
    <div class="panel__head">
      <h3>In der Umgebung</h3>
      <div class="spacer"></div>
      <button type="button" class="btn btn--secondary btn--small no-print"
              :disabled="!plot.anchor || busy" @click="load">
        {{ busy ? "Sucht…" : result ? "Neu suchen" : "Nachsehen" }}
      </button>
    </div>

    <p v-if="!plot.anchor" class="nearby__empty">
      Ohne Koordinate gibt es keinen Punkt, von dem aus gesucht werden könnte.
    </p>
    <p v-else-if="error" class="notice notice--error">{{ error }}</p>
    <p v-else-if="!result" class="nearby__empty">
      Schule, Kita, Park, Spielplatz, Supermarkt, Arzt und die nächsten Haltestellen —
      gerechnet als Fußweg, nicht als Luftlinie.
    </p>

    <template v-else>
      <table v-if="found.length" class="data-table nearby__list">
        <tbody>
          <tr v-for="(hit, i) in found" :key="i">
            <td class="nearby__what">
              <b>{{ label(hit.kategorie) }}</b>
              <span v-if="hit.art && hit.art !== label(hit.kategorie)" class="nearby__kind">{{ hit.art }}</span>
              <!-- A place you cannot look up is a name, not a finding. The link
                   is the way there, not a pin on it: the row states a walking
                   distance, and a marker alone leaves that claim unchecked. -->
              <a v-if="located(hit)" class="nearby__name" :href="link(hit)"
                 target="_blank" rel="noopener noreferrer"
                 :title="`Fußweg vom Grundstück zu ${hit.name} auf OpenStreetMap`">{{ hit.name }}</a>
              <span v-else class="nearby__name">{{ hit.name }}</span>
            </td>
            <td class="num">{{ hit.erreichbar ? duration(hit.duration_s) : "—" }}</td>
            <td class="num nearby__walk">
              <span v-if="hit.erreichbar" :title="`Luftlinie ${metres(hit.luftlinie_m, 0)}`">
                {{ metres(hit.distance_m, 0) }} Fußweg
              </span>
              <span v-else>kein Fußweg gefunden</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Two different silences, and confusing them would be a lie: a
           category this server has no data for, and one that was searched.
           The reason comes from the service, never from here — it knows
           whether the index is missing or the source refused the request, and
           a fixed sentence would state the wrong one. -->
      <p v-for="group in unavailable" :key="group.hinweis" class="nearby__hint">
        <b>{{ group.categories.map(label).join(", ") }}:</b> {{ group.hinweis }}
      </p>
      <p v-if="empty.length" class="nearby__hint">
        Nichts gefunden für {{ empty.map(c => label(c.kategorie)).join(", ") }}.
      </p>
      <p class="panel__footnote">{{ result.quelle }}</p>
    </template>
  </section>
</template>

<script>
import { nearby } from "../lib/api.js";
import { duration, metres } from "../lib/format.js";
import { openStreetMapRoute } from "../lib/mapLinks.js";

/** German labels for the server's category keys. */
const LABELS = {
  schule: "Schule", kindergarten: "Kita", park: "Park", spielplatz: "Spielplatz",
  supermarkt: "Supermarkt", arzt: "Arzt", tram: "Straßenbahn", sbahn: "S-Bahn",
  bus: "Bus", bahnhof: "Bahnhof"
};

export default {
  name: "NearbyPanel",
  props: {
    plot: { type: Object, required: true },
    /** Look straight away instead of waiting for the button. The surroundings
     *  view exists to show this; making it ask first would be a click for
     *  nothing. The plot page keeps the button. */
    auto: { type: Boolean, default: false }
  },
  emits: ["loaded"],
  data() { return { result: null, busy: false, error: null }; },
  computed: {
    found() { return this.result?.treffer ?? []; },
    /** Unavailable categories, grouped by the reason the service gave, so six
     *  categories failing the same way read as one line rather than six. */
    unavailable() {
      const byReason = new Map();
      (this.result?.kategorien ?? [])
        .filter(c => c.verfuegbar === false)
        .forEach(c => {
          const reason = c.hinweis || "Für diese Kategorie liegen hier keine Daten vor.";
          if (!byReason.has(reason)) byReason.set(reason, []);
          byReason.get(reason).push(c.kategorie);
        });
      return [...byReason].map(([hinweis, categories]) => ({ hinweis, categories }));
    },
    empty() {
      return (this.result?.kategorien ?? []).filter(c => c.verfuegbar === true && c.anzahl === 0);
    }
  },
  mounted() { if (this.auto && this.plot.anchor) this.load(); },
  watch: {
    "plot.id"() {
      this.result = null;
      this.error = null;
      this.$emit("loaded", null);
      if (this.auto && this.plot.anchor) this.load();
    }
  },
  methods: {
    duration,
    metres,
    located(hit) { return Number.isFinite(hit.lat) && Number.isFinite(hit.lon); },
    /** The walk the row measured, openable. No anchor, no rows: the panel
     *  refuses to search at all without one, so there is no second case. */
    link(hit) { return openStreetMapRoute(this.plot.anchor, hit, "walk"); },
    label(key) { return LABELS[key] ?? key; },
    async load() {
      this.busy = true;
      this.error = null;
      try {
        this.result = await nearby({ lat: this.plot.anchor.lat, lon: this.plot.anchor.lon });
        this.$emit("loaded", this.result);
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.nearby__empty{ padding: var(--w2b-space-4); color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.nearby__list td{ padding: 7px var(--w2b-space-4); vertical-align: baseline; }
.nearby__what{ display: flex; flex-direction: column; gap: 1px; }
.nearby__name{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
.nearby__kind{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
a.nearby__name{ text-decoration: underline; text-underline-offset: 2px; }
a.nearby__name:hover{ color: var(--w2b-primary); }
.nearby__walk{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); white-space: nowrap; }
.nearby__hint{ padding: 0 var(--w2b-space-4) var(--w2b-space-2); color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
</style>
