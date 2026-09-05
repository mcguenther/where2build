<template>
  <section class="panel checks">
    <div class="panel__head">
      <h3>Prüfungen</h3>
      <div class="spacer"></div>
      <button type="button" class="btn btn--secondary btn--small no-print"
              :disabled="!ring || busy" @click="load">
        {{ busy ? "Wird geprüft…" : result || error ? "Neu prüfen" : "Prüfen" }}
      </button>
    </div>

    <p v-if="!ring" class="checks__empty">
      Ohne Flurstücksumriss gibt es nichts zu fragen — die Prüfungen werden mit der
      Grundstücksfläche gestellt, nicht mit einem Punkt.
    </p>
    <p v-else-if="error" class="notice notice--error" role="alert">{{ error }}</p>
    <p v-else-if="busy && !result" class="checks__empty">
      Sieben Fachdienste des Freistaats und die Messwerte des Umweltbundesamtes werden
      abgefragt. Das dauert einen Moment.
    </p>
    <p v-else-if="!result" class="checks__empty">
      Lärm, Hochwasser, Radon, Trinkwasserschutz, Schutzgebiete, Hangneigung, Baugrund
      und Luftqualität — gefragt wird mit dem Umriss des Flurstücks.
    </p>

    <template v-else>
      <div class="checks__tally">
        <span v-if="tally.counts.good" class="chip chip--good">{{ tally.counts.good }} ohne Befund</span>
        <span v-if="tally.counts.note" class="chip chip--warn">{{ tally.counts.note }} zu beachten</span>
        <span v-if="tally.counts.open" class="chip">{{ tally.counts.open }} offen</span>
      </div>
      <p class="checks__no-score">
        Kein Gesamtwert: eine Zahl aus {{ checks.length }} Prüfungen, von denen
        {{ tally.counts.open }} keine Daten haben, beschriebe die Datenlage und sähe aus
        wie eine Aussage über das Grundstück.
      </p>

      <ol class="checks__list">
        <li v-for="check in checks" :key="check.id" class="check" :data-status="check.finding.status">
          <span class="check__dot" aria-hidden="true"></span>
          <div class="check__head">
            <span class="check__name">{{ check.name }}</span>
            <span class="check__value">{{ check.finding.value }}</span>
          </div>
          <p class="check__text">{{ check.finding.text }}</p>

          <!-- The interpretation is the noise finding's second half: what the
               band costs in everyday terms, and against which recommendation.
               It names its source, because it is the one part that reaches
               beyond what the survey itself states. -->
          <div v-if="check.finding.interpretation" class="reading">
            <p class="reading__head">
              <span class="reading__level">{{ check.finding.interpretation.label }}</span>
              {{ check.finding.interpretation.everyday }}
            </p>
            <ul class="reading__notes">
              <li v-for="(note, i) in check.finding.interpretation.notes" :key="i">{{ note }}</li>
            </ul>
            <p class="reading__source">{{ check.finding.interpretation.source }}</p>
          </div>

          <details v-if="check.detail" class="check__detail">
            <summary>{{ check.detailLabel }}</summary>
            <p>{{ check.detail }}</p>
          </details>

          <p v-if="check.quelle" class="check__source">{{ check.quelle }}</p>
        </li>
      </ol>

      <p class="checks__foot">{{ result.hinweis }}</p>
    </template>
  </section>
</template>

<script>
/**
 * The check list — counters, then one row per check.
 *
 * Every sentence here comes from `siteChecks.js` and the templates behind it.
 * This component chooses no words of its own beyond the headings: what a plot
 * reads like must be reviewable in one file, not spread across a template.
 *
 * There is deliberately no overall score. grundradar computes one from
 * fourteen categories and says "Datenabdeckung 58 %" in the same tooltip — a
 * value that is 42 % missing data is a statement about the data, wearing the
 * clothes of a statement about the plot.
 */
import { siteChecks } from "../lib/api.js";
import { siteFindings, siteTally } from "../lib/siteChecks.js";
import { toWgs84 } from "../lib/projection.js";

export default {
  name: "CheckList",
  props: {
    plot: { type: Object, required: true },
    /** Ask as soon as the component appears, rather than on a button press. */
    auto: { type: Boolean, default: false }
  },
  emits: ["loaded"],
  data() {
    return { result: null, busy: false, error: null };
  },
  computed: {
    /** The parcel outline in WGS84. Without an anchor the local metres name no
     *  place on earth, and there is nothing to ask about. */
    ring() {
      if (!this.plot?.anchor || !this.plot.polygon?.length) return null;
      const ring = toWgs84(this.plot.polygon, this.plot.anchor);
      // GeoJSON rings close; the services expect the same.
      return [...ring, ring[0]];
    },
    checks() { return siteFindings(this.result); },
    tally() { return siteTally(this.checks); }
  },
  created() { if (this.auto && this.ring) this.load(); },
  watch: {
    "plot.id"() {
      this.result = null;
      this.error = null;
      if (this.auto && this.ring) this.load();
    }
  },
  methods: {
    async load() {
      if (!this.ring) return;
      this.busy = true;
      this.error = null;
      try {
        this.result = await siteChecks(this.ring);
        this.$emit("loaded", this.result);
      } catch (error) {
        // The backend's own German sentence, never a replacement for it.
        this.error = error.message;
        this.result = null;
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.checks__empty{ color: var(--w2b-muted); font-size: var(--w2b-text-s); margin: 0; }
.checks__tally{ display: flex; flex-wrap: wrap; gap: 6px; }
.checks__no-score{
  margin: 6px 0 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted); max-width: 52ch;
}

.checks__list{ list-style: none; margin: var(--w2b-space-3) 0 0; padding: 0; }

.check{
  position: relative; padding: var(--w2b-space-3) 0 var(--w2b-space-3) var(--w2b-space-4);
  border-top: 1px solid var(--w2b-line-faint);
}
.check:first-child{ border-top: 0; }
.check__dot{
  position: absolute; left: 0; top: calc(var(--w2b-space-3) + 6px);
  width: 9px; height: 9px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-line);
}
.check[data-status="good"] .check__dot{ background: var(--w2b-good); }
.check[data-status="note"] .check__dot{ background: var(--w2b-warning); }

.check__head{ display: flex; align-items: baseline; gap: var(--w2b-space-2); }
.check__name{ font-family: var(--w2b-font-display); font-weight: 600; font-size: 14.5px; }
.check__value{
  margin-left: auto; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs);
  font-variant-numeric: tabular-nums; text-align: right; color: var(--w2b-muted);
}
.check[data-status="good"] .check__value{ color: var(--w2b-good); }
.check[data-status="note"] .check__value{ color: var(--w2b-warning-text); }

.check__text{ margin: 4px 0 0; font-size: var(--w2b-text-s); line-height: 1.5; }
.check__source{
  margin: 6px 0 0; font-family: var(--w2b-font-mono); font-size: 10.5px;
  color: var(--w2b-muted); letter-spacing: .01em;
}

.reading{
  margin-top: 8px; padding: 8px 10px; border-left: 2px solid var(--w2b-warning);
  background: var(--w2b-primary-veil); border-radius: 0 var(--w2b-radius-s) var(--w2b-radius-s) 0;
}
.reading__head{ margin: 0; font-size: var(--w2b-text-s); line-height: 1.5; }
.reading__level{
  font-family: var(--w2b-font-display); font-weight: 700; text-transform: uppercase;
  font-size: 10.5px; letter-spacing: .08em; color: var(--w2b-warning-text); margin-right: 7px;
}
.reading__notes{ margin: 6px 0 0; padding-left: 1.1em; font-size: var(--w2b-text-xs); color: var(--w2b-graphite); }
.reading__notes li + li{ margin-top: 3px; }
.reading__source{ margin: 6px 0 0; font-size: 10.5px; color: var(--w2b-muted); }

.check__detail{ margin-top: 7px; font-size: var(--w2b-text-xs); }
.check__detail summary{ cursor: pointer; color: var(--w2b-muted); }
.check__detail p{ margin: 5px 0 0; color: var(--w2b-graphite); line-height: 1.5; }

.checks__foot{
  margin: var(--w2b-space-3) 0 0; padding-top: var(--w2b-space-3);
  border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted); max-width: 58ch;
}
</style>
