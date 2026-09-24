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

    <div class="checks__body">
    <p v-if="!ring" class="checks__empty">
      Ohne Flurstücksumriss gibt es nichts zu fragen: die Prüfungen werden mit der
      Grundstücksfläche gestellt, nicht mit einem Punkt.
    </p>
    <p v-else-if="error" class="notice notice--error" role="alert">{{ error }}</p>
    <div v-else-if="busy && !result" class="checks__waiting" role="status" aria-live="polite">
      <p class="checks__empty">
        Sieben Fachdienste des Freistaats und die Messwerte des Umweltbundesamtes werden
        abgefragt. Das dauert einen Moment.
      </p>
      <!-- The cards that are coming, in outline: a check's mark, its name, its
           value and two lines of sentence. Not decoration — it says how much is
           on the way and where it will appear. -->
      <ol class="skeleton checks__cards checks__skeleton" aria-hidden="true">
        <li v-for="row in 4" :key="row" class="skeleton__row">
          <span class="skeleton__bar skeleton__bar--dot"></span>
          <span class="skeleton__bar skeleton__bar--name"></span>
          <span class="skeleton__bar skeleton__bar--value"></span>
          <span class="skeleton__bar skeleton__bar--text"></span>
          <span class="skeleton__bar skeleton__bar--text skeleton__bar--short"></span>
        </li>
      </ol>
    </div>
    <p v-else-if="!result" class="checks__empty">
      Lärm, Hochwasser, Radon, Trinkwasserschutz, Schutzgebiete, Hangneigung, Baugrund
      und Luftqualität. Gefragt wird mit dem Umriss des Flurstücks.
    </p>

    <template v-else>
      <ul class="checks__tally" aria-label="Zusammenfassung">
        <li v-for="group in groups" :key="group.status" class="tally" :data-status="group.status">
          <span class="mark" aria-hidden="true">{{ group.mark }}</span>
          {{ group.checks.length }} {{ group.counted }}
        </li>
      </ul>
      <HintFold class="checks__hints" :count="1">
        <p>Kein Gesamtwert: eine Zahl aus {{ checks.length }} Prüfungen, von denen
          {{ tally.counts.open }} keine Daten haben, beschriebe die Datenlage und sähe aus
          wie eine Aussage über das Grundstück.</p>
      </HintFold>

      <!-- Every group is rendered and the folded ones only hidden: paper has
           nothing to click, so the print sheet opens them all. -->
      <section v-for="group in groups" :key="group.status" :id="groupId(group.status)"
               class="checks__group" :data-status="group.status"
               :class="{ 'checks__group--folded': folded(group.status) }">
        <h4 class="checks__group-head">
          <span class="mark" aria-hidden="true">{{ group.mark }}</span>
          {{ group.label }}
          <span class="checks__group-count">{{ group.checks.length }}</span>
        </h4>
        <ol class="checks__cards">
          <li v-for="check in group.checks" :key="check.id" class="check" :data-status="check.finding.status">
            <div class="check__head">
              <span class="check__name">{{ check.name }}</span>
              <span class="check__value">{{ check.finding.value }}</span>
            </div>
            <div class="check__body">
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
            </div>
            <p v-if="check.quelle" class="check__source">{{ check.quelle }}</p>
          </li>
        </ol>
      </section>

      <div v-if="groups.length > 1" class="checks__more no-print">
        <button type="button" class="btn btn--secondary btn--small" :aria-expanded="String(expanded)"
                :aria-controls="foldedIds" @click="expanded = !expanded">
          {{ expanded ? `Nur „${groups[0].label}“ zeigen` : `Alle ${checks.length} Prüfungen zeigen` }}
        </button>
        <span v-if="!expanded" class="checks__more-hint">dazu {{ remainder }}</span>
      </div>

      <p class="checks__foot">{{ result.hinweis }}</p>
    </template>
    </div>
  </section>
</template>

<script>
/**
 * The check list — counters, then one card per check, grouped by what it found.
 *
 * Every sentence here comes from `siteChecks.js` and the templates behind it.
 * This component chooses no words of its own beyond the headings: what a plot
 * reads like must be reviewable in one file, not spread across a template.
 *
 * Only the gravest group that has a member is open at first. Eleven cards are
 * a long way to scroll for the two that say something, and a plot with nothing
 * to note shows what was checked and found clean instead of an empty box. The
 * others are a click away and counted above, so nothing is hidden without
 * saying how much.
 *
 * There is deliberately no overall score. grundradar computes one from
 * fourteen categories and says "Datenabdeckung 58 %" in the same tooltip — a
 * value that is 42 % missing data is a statement about the data, wearing the
 * clothes of a statement about the plot.
 */
import { siteChecks } from "../lib/api.js";
import { siteFindings, siteTally, GOOD, NOTE, OPEN } from "../lib/siteChecks.js";
import { tallyText } from "../lib/findings.js";
import { toWgs84 } from "../lib/projection.js";
import HintFold from "./HintFold.vue";

/** Gravest first. The mark repeats the colour in a shape, for anyone who
 *  cannot tell amber from green, and for paper printed in black. */
const GROUPS = [
  { status: NOTE, label: "Zu beachten", counted: "zu beachten", mark: "!" },
  { status: GOOD, label: "Ohne Befund", counted: "ohne Befund", mark: "✓" },
  { status: OPEN, label: "Offen", counted: "offen", mark: "?" }
];

export default {
  name: "CheckList",
  components: { HintFold },
  props: {
    plot: { type: Object, required: true },
    /** Ask as soon as the component appears, rather than on a button press. */
    auto: { type: Boolean, default: false }
  },
  emits: ["loaded"],
  data() {
    return { result: null, busy: false, error: null, expanded: false };
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
    tally() { return siteTally(this.checks); },
    /** The groups that have a member, gravest first. */
    groups() {
      return GROUPS
        .map(group => ({ ...group, checks: this.checks.filter(c => c.finding.status === group.status) }))
        .filter(group => group.checks.length);
    },
    /** What the button would add, in the counters' own wording. */
    remainder() {
      const leading = this.groups[0]?.status;
      return tallyText({ ...this.tally.counts, [leading]: 0 });
    },
    foldedIds() {
      return this.groups.slice(1).map(group => this.groupId(group.status)).join(" ");
    }
  },
  created() { if (this.auto && this.ring) this.load(); },
  watch: {
    "plot.id"() {
      this.result = null;
      this.error = null;
      this.expanded = false;
      if (this.auto && this.ring) this.load();
    }
  },
  methods: {
    folded(status) { return !this.expanded && status !== this.groups[0]?.status; },
    groupId(status) { return `checks-${this.plot.id}-${status}`; },
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
.checks__body{ padding: var(--w2b-space-3) var(--w2b-space-4) var(--w2b-space-4); }

.checks__empty{ color: var(--w2b-muted); font-size: var(--w2b-text-s); margin: 0; }

/* Each status has one colour, one surface and one mark, used by the counters,
   the group headings and the cards alike — so the amber of a counter is the
   amber of the cards it counts. */
[data-status="note"]{ --status: var(--w2b-warning); --status-text: var(--w2b-warning-text); --status-surface: var(--w2b-warning-surface); }
[data-status="good"]{ --status: var(--w2b-good); --status-text: var(--w2b-good); --status-surface: var(--w2b-good-surface); }
[data-status="open"]{ --status: var(--w2b-line); --status-text: var(--w2b-muted); --status-surface: var(--w2b-surface-sunken); }

.mark{
  display: inline-grid; place-items: center; flex: none;
  width: 17px; height: 17px; border-radius: var(--w2b-radius-full);
  background: var(--status); color: var(--w2b-surface);
  font-family: var(--w2b-font-display); font-weight: 700; font-size: 11px; line-height: 1;
}
[data-status="open"] .mark{ color: var(--w2b-muted); }

.checks__tally{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.tally{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 11px 3px 4px; border-radius: var(--w2b-radius-full);
  background: var(--status-surface); color: var(--status-text);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-s);
}
/* Inside the padded panel body rather than at a panel's edge. */
.checks__hints{ border-top: 0; margin-top: var(--w2b-space-1); max-width: 52ch; }
.checks__hints :deep(.hint-fold__head){ padding-inline: 0; }
.checks__hints :deep(.hint-fold__body){ padding-right: 0; padding-left: 12px; }

.checks__group{ margin-top: var(--w2b-space-4); }
.checks__group--folded{ display: none; }
.checks__group-head{
  display: flex; align-items: center; gap: 7px; margin: 0 0 var(--w2b-space-2);
  font-family: var(--w2b-font-display); font-weight: 700; font-size: var(--w2b-text-xs);
  letter-spacing: .08em; text-transform: uppercase; color: var(--status-text);
}
.checks__group-count{ color: var(--w2b-muted); font-weight: 600; }

/* Cards rather than rows: a finding is a thing of its own with a verdict, and
   a row in a long list made the two that matter look like the nine that do
   not. Two across where there is room — one across the sentence is a line of
   type far longer than anybody reads comfortably. */
.checks__cards{
  display: grid; gap: var(--w2b-space-3);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr));
  margin: 0; padding: 0; list-style: none;
}

.check{
  display: flex; flex-direction: column; min-width: 0;
  border: 1px solid var(--w2b-line); border-left: 4px solid var(--status);
  border-radius: var(--w2b-radius-s); background: var(--w2b-surface);
}
.check__head{
  display: flex; align-items: baseline; gap: var(--w2b-space-2);
  padding: 7px var(--w2b-space-3); background: var(--status-surface);
}
.check__name{ font-family: var(--w2b-font-display); font-weight: 700; font-size: 15px; color: var(--w2b-ink); }
.check__value{
  margin-left: auto; text-align: right;
  font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); font-weight: 600;
  font-variant-numeric: tabular-nums; color: var(--status-text);
}
.check__body{ padding: var(--w2b-space-2) var(--w2b-space-3) 0; }
.check__text{ margin: 0; font-size: var(--w2b-text-s); line-height: 1.5; }
/* Pinned to the foot, so the sources of two cards in a row line up whatever
   their sentences are long. */
.check__source{
  margin: auto 0 0; padding: var(--w2b-space-2) var(--w2b-space-3);
  font-family: var(--w2b-font-mono); font-size: 10.5px;
  color: var(--w2b-muted); letter-spacing: .01em; overflow-wrap: anywhere;
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

.checks__more{
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--w2b-space-2) var(--w2b-space-3);
  margin-top: var(--w2b-space-4);
}
.checks__more-hint{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }

/* The placeholders take the cards' outline, so nothing jumps when they land. */
.checks__skeleton .skeleton__row{
  padding: var(--w2b-space-3); border: 1px solid var(--w2b-line-faint);
  border-left-width: 4px; border-radius: var(--w2b-radius-s);
}
.checks__skeleton .skeleton__row:first-child{ padding-top: var(--w2b-space-3); border-top: 1px solid var(--w2b-line-faint); }

.checks__foot{
  margin: var(--w2b-space-4) 0 0; padding-top: var(--w2b-space-3);
  border-top: 1px solid var(--w2b-line);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted); max-width: 58ch;
}
</style>
