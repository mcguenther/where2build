<template>
  <div class="stack">
    <section class="panel">
      <div class="panel__head"><h3>Zeitraum</h3></div>
      <div class="panel__body stack">
        <PeriodPicker @change="load" />
        <label class="field field--check">
          <input type="checkbox" v-model="compare" @change="reload" />
          <span>Mit dem gleich langen Zeitraum davor vergleichen</span>
        </label>
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
          <UsageChart :points="series" :raster="held.raster" :vergleich="comparison"
                      title="Anfragen im Zeitraum" />
          <dl class="figures">
            <div><dt>Anfragen</dt><dd>{{ num(held.summe.anfragen, 0) }}</dd></div>
            <div><dt>Fehler</dt><dd :class="{ 'figures__alarm': held.summe.fehler > 0 }">{{ num(held.summe.fehler, 0) }}</dd></div>
            <div><dt>Abgewiesen (Kontingent)</dt><dd>{{ num(held.summe.limitiert, 0) }}</dd></div>
            <div><dt>Mittlere Dauer</dt><dd>{{ meanDuration }}</dd></div>
            <div><dt>Tokens hin</dt><dd>{{ num(held.summe.tokens_ein, 0) }}</dd></div>
            <div><dt>Tokens zurück</dt><dd>{{ num(held.summe.tokens_aus, 0) }}</dd></div>
            <div>
              <dt>Kosten Modell</dt>
              <dd>{{ money(held.summe.kosten_eur) }}</dd>
            </div>
          </dl>
          <!-- What the comparison is for: a number beside a number, not a
               second chart. -->
          <p v-if="held.vergleich_summe" class="hint">
            Zeitraum davor: {{ num(held.vergleich_summe.anfragen, 0) }} Anfragen
            ({{ difference }}), {{ num(held.vergleich_summe.fehler, 0) }} Fehler.
          </p>
          <p v-if="held.preise && !held.preise.vorhanden" class="hint">
            Keine Preisliste: {{ held.preise.hinweis }} Tokens werden trotzdem gezählt —
            was fehlt, ist nur die Umrechnung in Geld.
          </p>
          <p v-else-if="held.preise" class="hint">
            Kosten umgerechnet mit {{ num(held.preise.usd_je_eur, 4) }} USD je Euro
            (EZB, {{ held.preise.kurs_stand }}); Preisliste vom
            {{ date(held.preise.stand) }} mit {{ num(held.preise.modelle, 0) }} Modellen.
            Ein Modell ohne hinterlegten Preis zeigt „—“ und nicht 0,00 €.
          </p>
        </template>
      </div>
    </section>

    <!-- The one panel here that is about the product rather than the machine.
         Nothing fails when a search comes back empty, so no error log would
         ever show this. -->
    <section v-if="searches.gesamt > 0" class="panel">
      <div class="panel__head">
        <h3>Suchergebnisse</h3>
        <div class="spacer"></div>
        <span class="chip">{{ num(searches.gesamt, 0) }} Suchen</span>
      </div>
      <div class="panel__body stack">
        <ul class="quality">
          <li v-for="entry in searches.zeilen" :key="entry.id">
            <div class="quality__line">
              <b>{{ entry.label }}</b>
              <span class="spacer"></span>
              <span class="quality__value">
                {{ num(entry.anzahl, 0) }} · {{ num(entry.anteil, 0) }} %
              </span>
            </div>
            <div class="quality__track">
              <div class="quality__fill" :class="`quality__fill--${entry.id}`"
                   :style="{ width: `${Math.max(1, entry.anteil)}%` }"></div>
            </div>
          </li>
        </ul>
        <p class="hint">
          „Bestätigt“ heißt, eine amtliche Angabe hat genau ein Flurstück übrig gelassen.
          „Mehrdeutig“ heißt, dorthin kam nur eine gewählte Toleranz. „Erfolglos“ heißt,
          das Inserat gab zu wenig her — daran ist nichts kaputt, und genau deshalb steht
          es hier und nicht im Fehlerprotokoll.
        </p>
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
                <th class="num">Ø Dauer</th><th class="num">Tokens</th><th class="num">Kosten</th>
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
                <td class="num" data-label="Kosten">{{ money(row.kosten_eur) }}</td>
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
import { date, num } from "../../lib/format.js";
import { fillSeries } from "../../lib/period.js";

const AREAS = { anfrage: "Anfrage", dienst: "Dienst", modell: "Modell", suche: "Suche" };

/** The three ways a parcel search can end, in the order they are worth
 *  reading: what was settled, what was guessed at, what was not found. */
const OUTCOMES = [
  { id: "bestaetigt", label: "Bestätigt" },
  { id: "mehrdeutig", label: "Mehrdeutig" },
  { id: "erfolglos", label: "Erfolglos" },
  { id: "abgebrochen", label: "Abgebrochen" }
];

export default {
  name: "AdminStats",
  components: { PeriodPicker, UsageChart },
  data() {
    return { held: null, period: null, compare: false, busy: false, failure: "" };
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
    },
    /* The earlier period, padded the same way and laid over the current one.
       The points keep their own times; the chart only uses their heights. */
    comparison() {
      if (!this.held?.vergleich || !this.period) return [];
      const span = this.period.to - this.period.from;
      return fillSeries(
        this.held.vergleich,
        new Date(this.period.from.getTime() - span),
        new Date(this.period.to.getTime() - span),
        this.held.raster
      );
    },
    /** How the parcel searches in this period ended. */
    searches() {
      const rows = (this.held?.nach_dienst || []).filter(row => row.bereich === "suche");
      const total = rows.reduce((sum, row) => sum + row.anfragen, 0);
      const byOutcome = Object.fromEntries(rows.map(row => [row.dienst, row.anfragen]));
      return {
        gesamt: total,
        zeilen: OUTCOMES.filter(outcome => byOutcome[outcome.id]).map(outcome => ({
          ...outcome,
          anzahl: byOutcome[outcome.id],
          anteil: total ? (byOutcome[outcome.id] / total) * 100 : 0
        }))
      };
    },
    /** „+18 %“ against the period before, or nothing when it was empty. */
    difference() {
      const before = this.held?.vergleich_summe?.anfragen || 0;
      const now = this.held?.summe?.anfragen || 0;
      if (!before) return "davor war nichts gezählt";
      const change = ((now - before) / before) * 100;
      return `${change > 0 ? "+" : change < 0 ? "−" : "±"}${num(Math.abs(change), 0)} %`;
    }
  },
  methods: {
    num,
    date,
    areaName(key) { return AREAS[key] || key; },
    /** „—“ for a model the price list does not know. Never 0,00 €: that would
     *  be a figure computed from a missing input. */
    money(value) {
      return value === null || value === undefined
        ? "—"
        : `${num(value, value < 1 ? 4 : 2)} €`;
    },
    reload() { return this.load(); },
    /** „—“ and never 0 ms: a mean over no calls is not zero, it is absent. */
    mean(row) {
      if (!row.anfragen) return "—";
      return `${num(Math.round(row.dauer_ms / row.anfragen), 0)} ms`;
    },
    async load(period) {
      this.period = period || this.period;
      if (!this.period) return;
      this.busy = true;
      this.failure = "";
      try {
        this.held = await adminStatistics(
          this.period.from,
          this.period.to,
          this.period.grid,
          this.compare
        );
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
/* Row, not column: `.field` stacks a label over its control, which for a
   checkbox puts the box above its own words. */
.field--check{ display: flex; flex-direction: row; align-items: center; gap: var(--w2b-space-2); font-size: var(--w2b-text-s); }
.quality{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3); }
.quality__line{ display: flex; align-items: baseline; gap: var(--w2b-space-2); }
.quality__value{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); font-variant-numeric: tabular-nums; }
.quality__track{ height: 6px; border-radius: var(--w2b-radius-full); background: var(--w2b-surface-sunken); margin-top: 4px; }
.quality__fill{ height: 100%; border-radius: var(--w2b-radius-full); background: var(--w2b-primary-light); }
.quality__fill--mehrdeutig{ background: var(--w2b-secondary); }
.quality__fill--erfolglos, .quality__fill--abgebrochen{ background: var(--w2b-error); }
.figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: var(--w2b-space-4); margin: 0; }
.figures dt{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.figures dd{ margin: 0; font-size: var(--w2b-text-l, 1.25rem); font-family: var(--w2b-font-display); }
.figures__alarm{ color: var(--w2b-error); }
</style>
