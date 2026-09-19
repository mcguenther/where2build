<template>
  <div class="period">
    <div class="period__presets" role="group" aria-label="Zeitraum">
      <button v-for="preset in PRESETS" :key="preset.id" type="button" class="btn btn--small"
              :class="chosen === preset.id ? 'btn--secondary' : 'btn--quiet'"
              :aria-pressed="String(chosen === preset.id)"
              @click="pick(preset.id)">{{ preset.label }}</button>
      <button type="button" class="btn btn--small"
              :class="chosen === 'frei' ? 'btn--secondary' : 'btn--quiet'"
              :aria-pressed="String(chosen === 'frei')"
              @click="openFree">Zeitraum wählen</button>
    </div>

    <div v-if="chosen === 'frei'" class="period__free">
      <label>Von <input type="date" v-model="from" :max="to" @change="apply" /></label>
      <label>Bis <input type="date" v-model="to" :min="from" :max="today" @change="apply" /></label>
      <p v-if="problem" class="notice notice--error" role="alert">{{ problem }}</p>
    </div>

    <p class="period__range hint">{{ description }}</p>
  </div>
</template>

<script>
/**
 * The period every page of the administration area is read through.
 *
 * Presets first, because "the last day" is what somebody wants nine times out
 * of ten and a date picker for it is three clicks. The free range is next to
 * them rather than instead of them.
 *
 * The component owns no data of its own: it emits a period, and whoever holds
 * the page fetches with it. That keeps the picker usable above a chart, above
 * a table and above the error list without any of them having to know how a
 * week is worked out.
 */
import { PRESETS, dateValue, rangeFor, rangeFromDates } from "../../lib/period.js";
import { date } from "../../lib/format.js";

export default {
  name: "PeriodPicker",
  props: {
    /** Which preset is chosen at first. */
    start: { type: String, default: "day" }
  },
  emits: ["change"],
  data() {
    const now = new Date();
    return {
      PRESETS,
      chosen: this.start,
      today: dateValue(now),
      from: dateValue(new Date(now.getTime() - 7 * 24 * 3600 * 1000)),
      to: dateValue(now),
      problem: "",
      current: rangeFor(this.start)
    };
  },
  computed: {
    description() {
      const { from, to, grid } = this.current;
      const unit = grid === "stunde" ? "je Stunde" : "je Tag";
      return `${date(from.toISOString())} bis ${date(to.toISOString())}, ${unit}`;
    }
  },
  created() { this.$emit("change", this.current); },
  methods: {
    pick(id) {
      this.chosen = id;
      this.problem = "";
      this.current = rangeFor(id);
      this.$emit("change", this.current);
    },
    openFree() {
      this.chosen = "frei";
      this.apply();
    },
    apply() {
      const range = rangeFromDates(this.from, this.to);
      if (!range) {
        // Said, not swallowed: a picker that quietly keeps the old period
        // while showing new dates is a page that lies about what it shows.
        this.problem = "Das Ende des Zeitraums muss nach seinem Anfang liegen.";
        return;
      }
      this.problem = "";
      this.current = range;
      this.$emit("change", range);
    }
  }
};
</script>

<style scoped>
.period{ display: flex; flex-direction: column; gap: var(--w2b-space-2); }
.period__presets{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-2); }
.period__free{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-3); align-items: end; }
.period__free label{ display: flex; flex-direction: column; gap: var(--w2b-space-1); font-size: var(--w2b-text-s); }
.period__range{ margin: 0; }
</style>
