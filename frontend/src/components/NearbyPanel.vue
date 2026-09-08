<template>
  <section class="panel nearby">
    <div class="panel__head">
      <h3>In der Umgebung</h3>
      <div class="spacer"></div>
      <button type="button" class="btn btn--secondary btn--small no-print"
              :disabled="!plot.anchor || busy" @click="load">
        {{ busy ? "Sucht…" : result || error ? "Neu suchen" : "Nachsehen" }}
      </button>
    </div>

    <p v-if="!plot.anchor" class="nearby__empty">
      Ohne Koordinate gibt es keinen Punkt, von dem aus gesucht werden könnte.
    </p>
    <p v-else-if="error" class="notice notice--error">{{ error }}</p>
    <p v-else-if="!result" class="nearby__empty">
      Schule, Kita, Park, Spielplatz, Supermarkt, Arzt und die nächsten Haltestellen,
      gerechnet als Fußweg, nicht als Luftlinie.
    </p>

    <template v-else>
      <!-- Five columns where there were three: on a phone the last of them was
           cut off by the panel's own `overflow: hidden`, without a scrollbar to
           say so. Below the breakpoint the cells give up their side padding and
           the walk may wrap; the scroll container is what catches whatever is
           left over. -->
      <div v-if="found.length" class="table-scroll">
      <table class="data-table nearby__list">
        <thead>
          <tr>
            <th>Ziel</th>
            <th class="num">zu Fuß</th>
            <th class="num">Rad</th>
            <th class="num">Auto</th>
            <th class="num nearby__walk">Strecke</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(hit, i) in found" :key="hit.key">
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
              <!-- Which lines call here, not only which kind of vehicle: "Bus"
                   is a category, "141, 172" is what somebody actually rides.
                   Only the lines of the modes this row was found for -- the bus
                   lines at a tram stop are not what makes it a tram stop. -->
              <span v-if="hit.linien && hit.linien.length" class="nearby__lines"
                    :title="`Linien laut Fahrplan: ${hit.linien.join(', ')}`">
                <span v-for="line in hit.linien" :key="line" class="nearby__line">{{ line }}</span>
              </span>
              <span v-else-if="lineNote(hit)" class="nearby__kind">{{ lineNote(hit) }}</span>
            </td>
            <td class="num">{{ hit.erreichbar ? duration(hit.duration_s) : "—" }}</td>
            <!-- Rad und Auto kommen aus einer zweiten, langsameren Anfrage. Bis
                 sie da ist, steht hier ein Platzhalter statt eines Strichs, der
                 wie „gibt es nicht“ aussähe. -->
            <td class="num" :title="modeNote(hit, 'bike')">
              <span v-if="extraBusy" class="skeleton-cell" aria-label="wird berechnet"></span>
              <template v-else>{{ modeTime(hit, "bike") }}</template>
            </td>
            <td class="num" :title="modeNote(hit, 'car')">
              <span v-if="extraBusy" class="skeleton-cell" aria-label="wird berechnet"></span>
              <template v-else>{{ modeTime(hit, "car") }}</template>
            </td>
            <td class="num nearby__walk">
              <span v-if="hit.erreichbar" :title="`Luftlinie ${metres(hit.luftlinie_m, 0)}`">
                {{ metres(hit.distance_m, 0) }} Fußweg
              </span>
              <span v-else-if="Number.isFinite(hit.luftlinie_m)">
                {{ metres(hit.luftlinie_m, 0) }} Luftlinie
              </span>
              <span v-else>kein Fußweg gefunden</span>
            </td>
          </tr>
        </tbody>
      </table>
      </div>

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
      <p v-if="extraError" class="nearby__hint">
        <b>Rad und Auto:</b> {{ extraError }} Die Fußwege oben stehen, die Strecke
        daneben ist gemessen.
      </p>
      <p class="panel__footnote">{{ result.quelle }}</p>
    </template>
  </section>
</template>

<script>
import { nearby, reachability } from "../lib/api.js";
import { duration, metres } from "../lib/format.js";
import { openStreetMapRoute } from "../lib/mapLinks.js";

/** German labels for the server's category keys. */
const LABELS = {
  schule: "Schule", kindergarten: "Kita", park: "Park", spielplatz: "Spielplatz",
  supermarkt: "Supermarkt", arzt: "Arzt", tram: "Straßenbahn", sbahn: "S-Bahn",
  bus: "Bus", bahnhof: "Bahnhof"
};

/** What this browser session has already asked for, per plot and coordinate.
 *  An unasked-for search may happen once: opening the same plot again, or
 *  seeing it on both pages, must not put the timetable service through the
 *  whole round again. A failure is remembered as well — a search that failed
 *  by itself has to stay failed until somebody presses the button. */
const answered = new Map();

const sessionKey = plot => `${plot.id}:${plot.anchor?.lat ?? ""},${plot.anchor?.lon ?? ""}`;

export default {
  name: "NearbyPanel",
  props: {
    plot: { type: Object, required: true },
    /** Look straight away instead of waiting for the button — once per plot
     *  and session, see `answered`. The button stays either way, as the way to
     *  search again. */
    auto: { type: Boolean, default: false }
  },
  emits: ["loaded"],
  data() {
    return {
      result: null, busy: false, error: null,
      /** Travel times per hit and mode, from the second request. */
      extra: {}, extraBusy: false, extraError: null
    };
  },
  computed: {
    /** The hits, nearest on foot first.
     *
     * The service ranks within a category; across categories the order was the
     * category list's, so a supermarket four minutes away sat below a school
     * twenty minutes away. Walking time is the measure this panel is about —
     * air distance would reorder them wrongly, detours reach 2,88x. */
    found() {
      const hits = (this.result?.treffer ?? []).map((hit, i) => ({
        ...hit, key: `${hit.kategorie}-${i}`
      }));
      return hits.sort((a, b) => {
        if (a.erreichbar !== b.erreichbar) return a.erreichbar ? -1 : 1;
        return (a.duration_s ?? Infinity) - (b.duration_s ?? Infinity);
      });
    },
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
  mounted() { if (this.auto && this.plot.anchor) this.autoLoad(); },
  watch: {
    "plot.id"() {
      this.result = null;
      this.error = null;
      this.extra = {};
      this.extraError = null;
      this.$emit("loaded", null);
      if (this.auto && this.plot.anchor) this.autoLoad();
    }
  },
  methods: {
    duration,
    metres,
    located(hit) { return Number.isFinite(hit.lat) && Number.isFinite(hit.lon); },

    /** What the second request found for this row, or a dash. */
    modeTime(hit, mode) {
      const route = this.extra[hit.key]?.[mode];
      return route?.erreichbar ? duration(route.duration_s) : "—";
    },
    /** Why a dash is a dash: the row says nothing on its own. */
    modeNote(hit, mode) {
      const route = this.extra[hit.key]?.[mode];
      if (route?.erreichbar) return null;
      return route?.hinweis || this.extraError || "Noch nicht berechnet.";
    },

    /** Bike and car for the places just found.
     *
     * A second request, because the first one is a walking matrix and these are
     * routes. It is allowed to fail: the walking times and the measured
     * distances stand on their own, and the two columns then say so rather
     * than the panel losing its rows. */
    async loadModes() {
      const targets = this.found.filter(hit => this.located(hit));
      if (!targets.length || !this.plot.anchor) return;
      this.extraBusy = true;
      this.extraError = null;
      try {
        const answer = await reachability(
          { lat: this.plot.anchor.lat, lon: this.plot.anchor.lon },
          targets.map(hit => ({ id: hit.key, name: hit.name, lat: hit.lat, lon: hit.lon })),
          ["bike", "car"]
        );
        const rows = {};
        (answer?.ergebnisse ?? []).forEach(row => {
          (rows[row.destination_id] ||= {})[row.mode] = row;
        });
        this.extra = rows;
      } catch (error) {
        this.extraError = error.message;
      } finally {
        this.extraBusy = false;
      }
    },

    /** The walk the row measured, openable. No anchor, no rows: the panel
     *  refuses to search at all without one, so there is no second case. */
    link(hit) { return openStreetMapRoute(this.plot.anchor, hit, "walk"); },
    label(key) { return LABELS[key] ?? key; },
    /** Why a stop shows no line -- and it is never "es fährt keine". Two
     *  silences again: the server stops looking lines up after a fixed number
     *  of stops, which is not the same statement as "an dieser Haltestelle
     *  hält keine Linie". A place from OpenStreetMap has no lines to have and
     *  says nothing at all. */
    lineNote(hit) {
      if (hit.quelle !== "motis") return null;
      return hit.linien == null ? "Linien nicht abgefragt" : "keine Linie im Fahrplan";
    },
    /** The search nobody asked for: skipped once this session has an answer
     *  for this plot, so a re-render, a return visit or the second page
     *  showing the same plot costs no request at all. */
    autoLoad() {
      const seen = answered.get(sessionKey(this.plot));
      if (!seen) return this.load();
      this.result = seen.result;
      this.error = seen.error;
      this.$emit("loaded", this.result);
      // The walking answer is remembered for this session; the two routed
      // columns are not, and a returning visitor should still see them.
      return this.result ? this.loadModes() : Promise.resolve();
    },
    async load() {
      this.busy = true;
      this.error = null;
      const key = sessionKey(this.plot);
      try {
        // `linien` costs the timetable service one request per stop, and is the
        // difference between "hier hält ein Bus" and "hier hält die 141".
        this.result = await nearby(
          { lat: this.plot.anchor.lat, lon: this.plot.anchor.lon },
          { linien: true }
        );
        answered.set(key, { result: this.result, error: null });
        this.$emit("loaded", this.result);
        await this.loadModes();
      } catch (error) {
        this.error = error.message;
        answered.set(key, { result: null, error: this.error });
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
.nearby__lines{ display: flex; flex-wrap: wrap; gap: 3px; margin-top: 2px; }
.nearby__line{
  padding: 0 5px; border-radius: var(--w2b-radius-xs);
  background: var(--w2b-surface-sunken); border: 1px solid var(--w2b-line);
  color: var(--w2b-graphite); font-family: var(--w2b-font-mono);
  font-size: var(--w2b-text-xs); line-height: 1.55;
}
a.nearby__name{ text-decoration: underline; text-underline-offset: 2px; }
a.nearby__name:hover{ color: var(--w2b-primary); }
.nearby__walk{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); white-space: nowrap; }
@media (max-width: 620px){
  .nearby__list th, .nearby__list td{ padding-left: 8px; padding-right: 8px; }
  .nearby__list th:first-child, .nearby__list td:first-child{ padding-left: var(--w2b-space-4); }
  .nearby__list th:last-child, .nearby__list td:last-child{ padding-right: var(--w2b-space-4); }
  .nearby__walk{ white-space: normal; }
}
.nearby__hint{ padding: 0 var(--w2b-space-4) var(--w2b-space-2); color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
</style>
