<template>
  <!-- How far behind the street the houses on our side of it stand, one bar
       each, and under them our Bestand and our plot with its envelope. The
       band is orientation for § 34, never a limit. -->
  <div class="scroll-x">
    <svg :viewBox="`0 0 ${width} ${height}`" :width="width" :height="height" role="img"
         aria-label="Wie weit die Nachbarhäuser hinter der Straße stehen">
      <template v-if="band.front && band.rear">
        <rect class="bc-band" :x="X(band.front.min)" :y="TOP - 6"
              :width="(band.rear.max - band.front.min) * scale" :height="rows.length * ROW + 6" />
        <rect class="bc-band-front" :x="X(band.front.min)" :y="TOP - 6"
              :width="Math.max(1, (band.front.max - band.front.min) * scale)" :height="rows.length * ROW + 6" />
      </template>
      <g v-for="(r, i) in rows" :key="`r${i}`">
        <text class="bc-name" :x="LEFT - 8" :y="TOP + i * ROW + ROW / 2 + 3.5" text-anchor="end">{{ r.label }}</text>
        <template v-if="r.kind === 'plot'">
          <rect class="bc-plot" :x="X(r.from)" :y="TOP + i * ROW + 3" :width="(r.to - r.from) * scale" :height="ROW - 6" />
          <rect v-if="r.envelope" class="bc-env" :x="X(r.envelope.front)" :y="TOP + i * ROW + 4.5"
                :width="(r.envelope.rear - r.envelope.front) * scale" :height="ROW - 9" />
        </template>
        <rect v-else :class="r.kind === 'own' ? 'bc-own' : 'bc-house'" :x="X(r.from)" :y="TOP + i * ROW + 3"
              :width="Math.max(1, (r.to - r.from) * scale)" :height="ROW - 6" rx="2" />
      </g>
      <line class="bc-axis" :x1="X(0)" :y1="base" :x2="X(maxDepth)" :y2="base" />
      <template v-for="v in ticks" :key="`t${v}`">
        <line class="bc-axis" :x1="X(v)" :y1="base" :x2="X(v)" :y2="base + (v % 10 === 0 ? 6 : 3)" />
        <text v-if="v % 10 === 0" class="bc-tick" :x="X(v)" :y="base + 17" text-anchor="middle">{{ v }}</text>
      </template>
      <text class="bc-tick" :x="LEFT - 8" :y="base + 17" text-anchor="end">m</text>
    </svg>
  </div>
</template>

<script>
import { houseNumber } from "../lib/neighbourhoodDrawing.js";

const ROW = 16;
const LEFT = 84;
const TOP = 12;

export default {
  name: "BandChart",
  props: {
    /** `analysis.band`. */
    band: { type: Object, required: true },
    scale: { type: Number, default: 11 }
  },
  data() { return { ROW, LEFT, TOP }; },
  computed: {
    rows() {
      const label = (address, fallback) => houseNumber(address) ?? fallback;
      return [
        ...this.band.houses.map(h => ({ kind: "house", label: label(h.address, "Haus"), from: h.front, to: h.rear })),
        ...this.band.own.filter(o => o.useKind === "residential")
          .map(o => ({ kind: "own", label: `${label(o.address, "")} Bestand`.trim(), from: o.front, to: o.rear })),
        { kind: "plot", label: "unser", from: this.band.plot.front, to: this.band.plot.rear, envelope: this.band.envelope }
      ];
    },
    maxDepth() { return Math.max(this.band.plot.rear, this.band.rear?.max ?? 0); },
    width() { return Math.round(LEFT + this.maxDepth * this.scale + 30); },
    base() { return TOP + this.rows.length * ROW + 4; },
    height() { return this.base + 24; },
    ticks() {
      const out = [];
      for (let v = 0; v <= this.maxDepth + 0.01; v += 5) out.push(v);
      return out;
    }
  },
  methods: {
    X(v) { return LEFT + v * this.scale; }
  }
};
</script>

<style scoped>
.scroll-x{ overflow-x: auto; overscroll-behavior-x: contain; max-width: 100%; }
.scroll-x svg{ display: block; max-width: none; height: auto; }
.bc-band{ fill: var(--w2b-map-band); }
.bc-band-front{ fill: var(--w2b-map-band-strong); }
.bc-name{ font-family: var(--w2b-font-mono); font-size: 10px; fill: var(--w2b-graphite); }
.bc-house{ fill: var(--w2b-map-neighbour-main); stroke: var(--w2b-map-neighbour-main-edge); stroke-width: 1; }
.bc-own{ fill: var(--w2b-map-existing); }
.bc-plot{ fill: var(--w2b-map-setback); stroke: var(--w2b-map-boundary); stroke-width: 1; }
.bc-env{ fill: var(--w2b-map-surface); stroke: var(--w2b-map-envelope); stroke-width: 1; stroke-dasharray: 4 3; }
.bc-axis{ stroke: var(--w2b-muted); stroke-width: 1; }
.bc-tick{ font-family: var(--w2b-font-mono); font-size: 9.5px; fill: var(--w2b-muted); }
</style>
