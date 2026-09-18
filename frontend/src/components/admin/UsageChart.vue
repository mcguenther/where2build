<template>
  <figure class="chart">
    <figcaption class="chart__head">
      <span class="chart__title">{{ title }}</span>
      <span class="spacer"></span>
      <!-- The legend is always there for two series, and both are labelled in
           words as well as in colour: „Fehler" red and nothing else would be
           the one thing a colour-blind reader cannot read. -->
      <span class="chart__key"><i class="chart__swatch chart__swatch--ok"></i>Beantwortet</span>
      <span class="chart__key"><i class="chart__swatch chart__swatch--fail"></i>Fehler</span>
    </figcaption>

    <p v-if="!hasAnything" class="hint">
      Für diesen Zeitraum ist nichts gezählt. Gezählt wird erst, seit dieser Server
      Zähler führt — vorher liegt nichts vor, und eine Linie bei null wäre eine Behauptung.
    </p>

    <template v-else>
      <svg class="chart__plot" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img"
           :aria-label="`${title}: ${total} Anfragen, davon ${failures} mit Fehler`"
           @mouseleave="hovered = null">
        <!-- One recessive rule at the top of the scale; no grid behind the bars. -->
        <line class="chart__axis" :x1="0" :y1="PLOT_TOP" :x2="WIDTH" :y2="PLOT_TOP" />
        <line class="chart__axis" :x1="0" :y1="baseline" :x2="WIDTH" :y2="baseline" />
        <!-- Three labels, not one per bar: seventy-two of them is a smear, and
             none at all leaves a shape with no time in it. -->
        <text v-for="tick in ticks" :key="`t-${tick.x}`" class="chart__tick"
              :x="tick.x" :y="HEIGHT - 2" :text-anchor="tick.anchor">{{ tick.text }}</text>
        <g v-for="(bar, index) in bars" :key="index" @mouseenter="hovered = index">
          <title>{{ label(bar.point) }}: {{ bar.point.anfragen }} Anfragen, {{ bar.point.fehler }} Fehler</title>
          <!-- A hit area the whole height of the plot: a bar two pixels tall is
               not something anybody can point at. -->
          <rect class="chart__hit" :x="bar.x" :y="PLOT_TOP" :width="bar.width" :height="baseline - PLOT_TOP" />
          <path v-if="bar.okHeight > 0" class="chart__bar chart__bar--ok" :d="bar.okPath" />
          <path v-if="bar.failHeight > 0" class="chart__bar chart__bar--fail" :d="bar.failPath" />
        </g>
      </svg>

      <div class="chart__foot">
        <span class="chart__scale">Höchstwert {{ max }} je {{ raster === "stunde" ? "Stunde" : "Tag" }}</span>
        <span class="spacer"></span>
        <!-- The readout replaces a number on every bar: a label per point is
             unreadable at 72 of them, and none at all makes the chart a shape. -->
        <span class="chart__readout">{{ readout }}</span>
      </div>
    </template>
  </figure>
</template>

<script>
/**
 * Calls over time, as stacked bars: what was answered, and what failed.
 *
 * Inline SVG and no library. The shape is a bar per bucket and the numbers
 * come ready-grouped from the server, so a charting dependency would be a
 * megabyte to draw rectangles — and this one has to work in both themes,
 * which means its colours are the application's own tokens rather than a
 * palette of its own.
 *
 * Two series on one scale, never two scales: tokens and calls do not belong
 * in one picture, so tokens have a picture of their own.
 */
import { date } from "../../lib/format.js";

const WIDTH = 720;
const HEIGHT = 216;
const PLOT_TOP = 12;
// Room under the baseline for the three time labels.
const BASELINE = HEIGHT - 20;
// The gap between two bars, in the same units as the viewBox. Two pixels of
// surface is what keeps adjacent fills from reading as one block.
const GAP = 2;
const RADIUS = 4;

/** A rectangle rounded at the end away from the baseline. */
function topRounded(x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, width / 2, height));
  return (
    `M${x} ${y + height}` +
    `V${y + r}` +
    `a${r} ${r} 0 0 1 ${r} ${-r}` +
    `h${width - 2 * r}` +
    `a${r} ${r} 0 0 1 ${r} ${r}` +
    `V${y + height}` +
    "Z"
  );
}

export default {
  name: "UsageChart",
  props: {
    points: { type: Array, default: () => [] },
    raster: { type: String, default: "stunde" },
    title: { type: String, default: "Anfragen" }
  },
  data() {
    return { WIDTH, HEIGHT, PLOT_TOP, hovered: null };
  },
  computed: {
    baseline() { return BASELINE; },
    total() { return this.points.reduce((sum, point) => sum + point.anfragen, 0); },
    failures() { return this.points.reduce((sum, point) => sum + point.fehler, 0); },
    hasAnything() { return this.points.length > 0 && this.total > 0; },
    max() { return Math.max(1, ...this.points.map(point => point.anfragen)); },
    bars() {
      const step = WIDTH / Math.max(1, this.points.length);
      const width = Math.max(1, step - GAP);
      const scale = (BASELINE - PLOT_TOP) / this.max;
      return this.points.map((point, index) => {
        const failHeight = Math.round(point.fehler * scale);
        const okHeight = Math.round(Math.max(0, point.anfragen - point.fehler) * scale);
        const x = index * step + GAP / 2;
        // Failures sit on top, so the eye compares the whole bar against the
        // scale and the red part against itself.
        const okTop = BASELINE - okHeight;
        const failTop = okTop - failHeight - (okHeight > 0 && failHeight > 0 ? GAP : 0);
        return {
          point,
          x,
          width,
          okHeight,
          failHeight,
          okPath: topRounded(x, okTop, width, okHeight, failHeight > 0 ? 0 : RADIUS),
          failPath: topRounded(x, failTop, width, failHeight, RADIUS)
        };
      });
    },
    /** First, middle and last bucket of the period. */
    ticks() {
      if (this.points.length === 0) return [];
      const step = WIDTH / this.points.length;
      const middle = Math.floor(this.points.length / 2);
      const last = this.points.length - 1;
      const at = (index, anchor) => ({
        x: index * step + (anchor === "end" ? step : anchor === "middle" ? step / 2 : 0),
        anchor,
        text: this.label(this.points[index])
      });
      return this.points.length < 3
        ? [at(0, "start")]
        : [at(0, "start"), at(middle, "middle"), at(last, "end")];
    },
    readout() {
      const point = this.hovered === null ? null : this.points[this.hovered];
      if (!point) return `${this.total} Anfragen, davon ${this.failures} mit Fehler`;
      return `${this.label(point)}: ${point.anfragen} Anfragen, ${point.fehler} Fehler`;
    }
  },
  methods: {
    /** An hour is read as a time, a day as a date. */
    label(point) {
      if (!point?.zeit) return "—";
      const moment = new Date(point.zeit);
      if (this.raster === "tag") return moment.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
      return moment.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    },
    date
  }
};
</script>

<style scoped>
.chart{ margin: 0; }
.chart__head, .chart__foot{
  display: flex; align-items: center; gap: var(--w2b-space-3);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.chart__title{ font-weight: 600; color: var(--w2b-graphite); }
.chart__key{ display: inline-flex; align-items: center; gap: var(--w2b-space-1); }
.chart__swatch{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.chart__swatch--ok{ background: var(--w2b-primary-light); }
.chart__swatch--fail{ background: var(--w2b-error); }
.chart__plot{ width: 100%; height: auto; display: block; margin: var(--w2b-space-2) 0; }
.chart__axis{ stroke: var(--w2b-line); stroke-width: 1; }
.chart__bar--ok{ fill: var(--w2b-primary-light); }
.chart__bar--fail{ fill: var(--w2b-error); }
.chart__hit{ fill: transparent; }
.chart__tick{ fill: var(--w2b-muted); font-size: 11px; font-family: var(--w2b-font-mono); }
g:hover .chart__bar--ok{ fill: var(--w2b-primary); }
.chart__readout{ font-family: var(--w2b-font-mono); font-variant-numeric: tabular-nums; }
</style>
