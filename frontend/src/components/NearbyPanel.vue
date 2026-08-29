<template>
  <section class="tafel umgebung">
    <div class="tafel__kopf">
      <h3>In der Umgebung</h3>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--zweit knopf--klein nicht-drucken"
              :disabled="!plot.anchor || busy" @click="load">
        {{ busy ? "Sucht…" : result ? "Neu suchen" : "Nachsehen" }}
      </button>
    </div>

    <p v-if="!plot.anchor" class="umgebung__leer">
      Ohne Koordinate gibt es keinen Punkt, von dem aus gesucht werden könnte.
    </p>
    <p v-else-if="error" class="band band--fehler">{{ error }}</p>
    <p v-else-if="!result" class="umgebung__leer">
      Schule, Kita, Park, Spielplatz, Supermarkt, Arzt und die nächsten Haltestellen —
      gerechnet als Fußweg, nicht als Luftlinie.
    </p>

    <template v-else>
      <table v-if="found.length" class="liste umgebung__liste">
        <tbody>
          <tr v-for="(hit, i) in found" :key="i">
            <td class="umgebung__was">
              <b>{{ label(hit.kategorie) }}</b>
              <span class="umgebung__name">{{ hit.name }}</span>
            </td>
            <td class="zahl">{{ hit.erreichbar ? duration(hit.duration_s) : "—" }}</td>
            <td class="zahl umgebung__weg">
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
      <p v-if="missing.length" class="umgebung__hinweis">
        Kein Datenbestand für {{ missing.map(c => label(c.kategorie)).join(", ") }}.
        Das heißt nicht, dass es dort nichts gibt.
      </p>
      <p v-if="empty.length" class="umgebung__hinweis">
        Nichts gefunden für {{ empty.map(c => label(c.kategorie)).join(", ") }}.
      </p>
      <p class="tafel__fussnote">{{ result.quelle }}</p>
    </template>
  </section>
</template>

<script>
import { nearby } from "../lib/api.js";
import { duration, metres } from "../lib/format.js";

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
.umgebung__leer{ padding: var(--w2b-raum-4); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }
.umgebung__liste td{ padding: 7px var(--w2b-raum-4); vertical-align: baseline; }
.umgebung__was{ display: flex; flex-direction: column; gap: 1px; }
.umgebung__name{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.umgebung__weg{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); white-space: nowrap; }
.umgebung__hinweis{ padding: 0 var(--w2b-raum-4) var(--w2b-raum-2); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
</style>
