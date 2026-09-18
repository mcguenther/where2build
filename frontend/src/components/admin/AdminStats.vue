<template>
  <div class="stack">
    <section class="panel">
      <div class="panel__head"><h3>Zeitraum</h3></div>
      <div class="panel__body">
        <PeriodPicker @change="load" />
      </div>
    </section>

    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Anfragen</h3>
        <div class="spacer"></div>
        <span v-if="held" class="chip">{{ num(held.summe.anfragen, 0) }} gesamt</span>
      </div>
      <div class="panel__body stack">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <template v-else-if="held">
          <UsageChart :points="series" :raster="held.raster" title="Anfragen im Zeitraum" />
          <dl class="figures">
            <div><dt>Anfragen</dt><dd>{{ num(held.summe.anfragen, 0) }}</dd></div>
            <div><dt>Fehler</dt><dd :class="{ 'figures__alarm': held.summe.fehler > 0 }">{{ num(held.summe.fehler, 0) }}</dd></div>
            <div><dt>Abgewiesen (Kontingent)</dt><dd>{{ num(held.summe.limitiert, 0) }}</dd></div>
            <div><dt>Mittlere Dauer</dt><dd>{{ meanDuration }}</dd></div>
            <div><dt>Tokens hin</dt><dd>{{ num(held.summe.tokens_ein, 0) }}</dd></div>
            <div><dt>Tokens zurück</dt><dd>{{ num(held.summe.tokens_aus, 0) }}</dd></div>
          </dl>
        </template>
      </div>
    </section>

    <section v-if="held" class="panel">
      <div class="panel__head"><h3>Nach Dienst</h3></div>
      <div class="panel__body">
        <p v-if="held.nach_dienst.length === 0" class="hint">
          Für diesen Zeitraum liegt nichts vor.
        </p>
        <div v-else class="table-scroll">
          <table class="data-table data-table--stack">
            <thead>
              <tr>
                <th>Bereich</th><th>Dienst</th>
                <th class="num">Aufrufe</th><th class="num">Fehler</th>
                <th class="num">Ø Dauer</th><th class="num">Tokens</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in held.nach_dienst" :key="`${row.bereich}-${row.dienst}`">
                <td data-label="Bereich">{{ areaName(row.bereich) }}</td>
                <td data-label="Dienst">{{ row.dienst }}</td>
                <td class="num" data-label="Aufrufe">{{ num(row.anfragen, 0) }}</td>
                <td class="num" data-label="Fehler">{{ num(row.fehler, 0) }}</td>
                <td class="num" data-label="Ø Dauer">{{ mean(row) }}</td>
                <td class="num" data-label="Tokens">{{ row.tokens_ein + row.tokens_aus > 0 ? num(row.tokens_ein + row.tokens_aus, 0) : "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">
          „Anfrage“ ist ein Aufruf dieser Anwendung, „Dienst“ ein Aufruf, der nach außen
          ging — an ALKIS, BORIS, MOTIS oder das Modell —, „Modell“ die Tokens dazu.
          Eine Suche zählt einmal als Anfrage und so oft als Dienst, wie sie gefragt hat.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * What this deployment did, over a period the reader chooses.
 *
 * Two representations of one set of numbers, on purpose: the chart is for the
 * shape — when it happened, whether it is rising, where the failures sit — and
 * the table is for the value. Neither is decoration for the other, and the
 * table is also what a reader who cannot see the chart is left with.
 *
 * The mean duration is computed here rather than stored: the server sums the
 * durations, because a mean of means is not a mean, and the division belongs
 * where the period is known.
 */
import PeriodPicker from "./PeriodPicker.vue";
import UsageChart from "./UsageChart.vue";
import { adminStatistics } from "../../lib/api.js";
import { num } from "../../lib/format.js";
import { fillSeries } from "../../lib/period.js";

const AREAS = { anfrage: "Anfrage", dienst: "Dienst", modell: "Modell" };

export default {
  name: "AdminStats",
  components: { PeriodPicker, UsageChart },
  data() {
    return { held: null, period: null, busy: false, failure: "" };
  },
  computed: {
    meanDuration() { return this.held ? this.mean(this.held.summe) : "—"; },
    /* The chart gets every bucket of the period, the table only the ones with
       something in them: a row of zeroes is noise in a list and a gap in a
       chart is a lie. */
    series() {
      return this.held && this.period
        ? fillSeries(this.held.zeitreihe, this.period.from, this.period.to, this.held.raster)
        : [];
    }
  },
  methods: {
    num,
    areaName(key) { return AREAS[key] || key; },
    /** „—“ and never 0 ms: a mean over no calls is not zero, it is absent. */
    mean(row) {
      if (!row.anfragen) return "—";
      return `${num(Math.round(row.dauer_ms / row.anfragen), 0)} ms`;
    },
    async load(period) {
      this.period = period;
      this.busy = true;
      this.failure = "";
      try {
        this.held = await adminStatistics(period.from, period.to, period.grid);
      } catch (error) {
        this.held = null;
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: var(--w2b-space-4); margin: 0; }
.figures dt{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.figures dd{ margin: 0; font-size: var(--w2b-text-l, 1.25rem); font-family: var(--w2b-font-display); }
.figures__alarm{ color: var(--w2b-error); }
</style>
