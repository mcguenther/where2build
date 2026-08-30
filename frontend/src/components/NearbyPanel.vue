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
              <!-- A place you cannot look up is a name, not a finding. -->
              <a v-if="Number.isFinite(hit.lat) && Number.isFinite(hit.lon)"
                 class="nearby__name" :href="placeLink(hit)"
                 target="_blank" rel="noopener noreferrer"
                 :title="`${hit.name} auf OpenStreetMap ansehen`">{{ hit.name }}</a>
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
           category this server has no data for, and one that was searched. -->
      <p v-if="missing.length" class="nearby__hint">
        Kein Datenbestand für {{ missing.map(c => label(c.kategorie)).join(", ") }}.
        Das heißt nicht, dass es dort nichts gibt.
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
import { openStreetMapPlace, openStreetMapRoute } from "../lib/mapLinks.js";

/** German labels for the server's category keys. */
const LABELS = {
  schule: "Schule", kindergarten: "Kita", park: "Park", spielplatz: "Spielplatz",
  supermarkt: "Supermarkt", arzt: "Arzt", tram: "Straßenbahn", sbahn: "S-Bahn",
  bus: "Bus", bahnhof: "Bahnhof"
};

export default {
  name: "NearbyPanel",
  props: { plot: { type: Object, required: true } },
  data() { return { result: null, busy: false, error: null }; },
  computed: {
    found() { return this.result?.treffer ?? []; },
    missing() { return (this.result?.kategorien ?? []).filter(c => c.verfuegbar === false); },
    empty() {
      return (this.result?.kategorien ?? []).filter(c => c.verfuegbar === true && c.anzahl === 0);
    }
  },
  watch: { "plot.id"() { this.result = null; this.error = null; } },
  methods: {
    duration,
    metres,
    placeLink(hit) { return openStreetMapPlace(hit); },
    /** The walk itself, for anyone who wants to see the route rather than the point. */
    walkLink(hit) { return openStreetMapRoute(this.plot.anchor, hit, "walk"); },
    label(key) { return LABELS[key] ?? key; },
    async load() {
      this.busy = true;
      this.error = null;
      try {
        this.result = await nearby({ lat: this.plot.anchor.lat, lon: this.plot.anchor.lon });
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
a.nearby__name{ text-decoration: underline; text-underline-offset: 2px; }
a.nearby__name:hover{ color: var(--w2b-primary); }
.nearby__walk{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); white-space: nowrap; }
.nearby__hint{ padding: 0 var(--w2b-space-4) var(--w2b-space-2); color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
</style>
