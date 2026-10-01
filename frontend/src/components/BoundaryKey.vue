<template>
  <!-- The plot's boundaries as a small diagram: the street on the left, the
       way one looks into the plot from it, each boundary coloured only on the
       stretch where something stands. A boundary is a button that opens its
       strip. -->
  <div class="schluessel">
    <svg :viewBox="`0 0 ${VIEW_W} ${viewHeight}`" role="group"
         aria-label="Unsere Grenzen; eine Grenze wählen öffnet ihre Ansicht">
      <rect class="kg-plot" :x="L" :y="T" :width="W" :height="H" />
      <rect class="kg-strip" :x="L" :y="T" :width="W" :height="H" />
      <rect class="kg-plot" :x="L + inset" :y="T + inset" :width="Math.max(0, W - 2 * inset)"
            :height="Math.max(0, H - 2 * inset)" />
      <g v-for="seg in segments" :key="seg.kind" class="kg-seg" :class="{ 'is-open': open === seg.kind }"
         :data-boundary="seg.kind" tabindex="0" role="button"
         :aria-label="`${seg.name}: Grenze ansehen`" :aria-pressed="String(open === seg.kind)"
         @click="$emit('pick', seg.kind)"
         @keydown.enter.prevent="$emit('pick', seg.kind)" @keydown.space.prevent="$emit('pick', seg.kind)">
        <path class="kg-focus" :d="seg.d" />
        <path class="kg-base" :d="seg.d" />
        <path v-for="(m, i) in seg.marks" :key="`m${i}`" class="kg-mark" :class="`kg-mark--${m.status}`" :d="m.d" />
        <rect v-for="(b, i) in seg.buildings" :key="`b${i}`" :class="`kg-building kg-building--${b.kind}`"
              :x="b.x" :y="b.y" :width="b.width" :height="b.height" />
        <path class="kg-hit" :d="seg.d" />
        <text v-for="(line, i) in seg.label.lines" :key="`t${i}`" class="kg-text"
              :class="{ 'kg-strong': line.strong }" :x="seg.label.x" :y="seg.label.y + i * 13"
              :text-anchor="seg.label.anchor">{{ line.text }}</text>
      </g>
    </svg>
  </div>
</template>

<script>
import { metres } from "../lib/format.js";
import { CLASS_BOUNDARY, CLASS_OVERLAP, CLASS_ACCESSORY, CLASS_CLEAR, MINIMUM_SETBACK_M } from "../lib/neighbourhood.js";
import { shortName, BOUNDARY_NAMES } from "../lib/neighbourhoodDrawing.js";

const VIEW_W = 358;
const L = 64;
const T = 30;
const W = 200;

/** What a boundary's worst neighbour says, in the few words the diagram has. */
function sideLabel(entry, building) {
  if (!entry) return "frei";
  const name = shortName(building);
  if (entry.class === CLASS_BOUNDARY) return `${name} · an der Grenze · ${metres(entry.faceTo - entry.faceFrom, 1)}`;
  if (entry.class === CLASS_OVERLAP) return `${name} · ${metres(entry.gap)} · 6-m-Zone`;
  if (entry.class === CLASS_ACCESSORY) return `${name} · zählt nicht`;
  return "frei";
}
const SHORT_STATUS = {
  [CLASS_BOUNDARY]: "an der Grenze", [CLASS_OVERLAP]: "Überdeckung",
  [CLASS_ACCESSORY]: "zählt nicht", [CLASS_CLEAR]: "frei"
};

export default {
  name: "BoundaryKey",
  props: {
    analysis: { type: Object, required: true },
    /** The boundary whose strip is open, if any. */
    open: { type: String, default: null }
  },
  emits: ["pick"],
  data() { return { VIEW_W, L, T, W }; },
  computed: {
    byKind() { return new Map(this.analysis.boundaries.map(b => [b.kind, b])); },
    sideLength() {
      const sides = ["left", "right"].map(k => this.byKind.get(k)?.length).filter(Number.isFinite);
      return sides.length ? Math.max(...sides) : (this.byKind.get("street")?.length ?? 1);
    },
    /* Metres to pixels along the sides; the street is drawn at the same scale,
       within limits, so a deep narrow plot still reads as one. */
    scale() { return W / this.sideLength; },
    H() {
      const street = this.byKind.get("street")?.length ?? this.sideLength / 2;
      return Math.min(70, Math.max(34, street * this.scale));
    },
    inset() { return Math.min(MINIMUM_SETBACK_M * this.scale, this.H / 3); },
    B() { return T + this.H; },
    R() { return L + W; },
    viewHeight() { return Math.round(this.B + 38); },
    segments() {
      const out = [];
      const building = id => this.analysis.buildings.find(b => b.id === id);
      const worst = g => g.facing.find(f => f.class === g.status) ?? null;
      for (const kind of ["left", "right", "street", "rear"]) {
        const g = this.byKind.get(kind);
        if (!g) continue;
        const frac = s => Math.max(0, Math.min(1, s / (g.length || 1)));
        const marks = [];
        const buildings = [];
        const entries = g.facing.filter(f => f.faceTo - f.faceFrom > 0.05);
        let d;
        let label;
        if (kind === "left" || kind === "right") {
          const top = kind === "left";
          const y = top ? T : this.B;
          const out1 = top ? -1 : 1;
          d = `M${L},${y}H${this.R}`;
          for (const f of entries) {
            const x1 = L + frac(f.faceFrom) * W, x2 = L + frac(f.faceTo) * W;
            marks.push({ status: f.class, d: `M${x1.toFixed(1)},${y + out1 * 3}H${x2.toFixed(1)}` });
            const bx = L + frac(f.from) * W, bw = Math.max(4, (frac(f.to) - frac(f.from)) * W);
            buildings.push({ kind: f.class === CLASS_ACCESSORY ? "aux" : "main", x: bx, width: bw,
              y: top ? y - 6 - 8 : y + 6, height: 8 });
          }
          if (!entries.length) marks.push({ status: CLASS_CLEAR, d: `M${L},${y + out1 * 3}H${this.R}` });
          label = { x: L, y: top ? T - 18 : this.B + 26, anchor: "start",
            lines: [{ text: sideLabel(worst(g), building(worst(g)?.buildingId)) }] };
        } else {
          const street = kind === "street";
          const x = street ? L : this.R;
          const outward = street ? -1 : 1;
          d = `M${x},${T}V${this.B}`;
          // The street is measured from its left corner (the top), the rear
          // from its right one (the bottom).
          const yOf = s => (street ? T + frac(s) * this.H : this.B - frac(s) * this.H);
          for (const f of entries) {
            const y1 = yOf(f.faceFrom), y2 = yOf(f.faceTo);
            marks.push({ status: f.class, d: `M${x + outward * 3},${y1.toFixed(1)}V${y2.toFixed(1)}` });
            const a = yOf(f.from), b = yOf(f.to);
            buildings.push({ kind: f.class === CLASS_ACCESSORY ? "aux" : "main",
              x: street ? x - 6 - 8 : x + 6, width: 8, y: Math.min(a, b), height: Math.max(4, Math.abs(b - a)) });
          }
          if (!entries.length) marks.push({ status: CLASS_CLEAR, d: `M${x + outward * 3},${T}V${this.B}` });
          label = {
            x: street ? L - 10 : this.R + 18, y: T + this.H / 2 - 3, anchor: street ? "end" : "start",
            lines: [{ text: street ? "Straße" : "hinten", strong: true }, { text: SHORT_STATUS[g.status] ?? "frei" }]
          };
        }
        out.push({ kind, name: BOUNDARY_NAMES[kind], d, marks, buildings, label });
      }
      return out;
    }
  }
};
</script>

<style scoped>
.schluessel{ padding: 6px 10px 10px; }
.schluessel svg{ display: block; width: 100%; height: auto; max-width: 380px; margin-inline: auto; overflow: visible; }
.kg-seg{ cursor: pointer; }
.kg-seg:focus{ outline: none; }
.kg-hit{ stroke: transparent; stroke-width: 18; fill: none; }
.kg-base{ stroke: var(--w2b-map-boundary); stroke-width: 2; fill: none; }
.kg-mark{ stroke-width: 6; fill: none; stroke-linecap: butt; }
.kg-mark--clear{ stroke: var(--w2b-good); stroke-width: 3; }
.kg-mark--boundary{ stroke: var(--w2b-map-boundary-built); }
.kg-mark--overlap{ stroke: var(--w2b-map-zone); stroke-dasharray: 5 3; }
.kg-mark--accessory{ stroke: var(--w2b-muted); }
.kg-building--main{ fill: var(--w2b-map-neighbour-main); stroke: var(--w2b-map-neighbour-main-edge); stroke-width: 1; }
.kg-building--aux{ fill: var(--w2b-map-neighbour-aux); stroke: var(--w2b-map-neighbour-aux-edge); stroke-width: .8; }
.kg-focus{ fill: none; stroke: var(--w2b-map-selection); stroke-width: 10; opacity: 0; stroke-linecap: round; }
.kg-seg:hover .kg-focus{ opacity: .25; }
.kg-seg:focus-visible .kg-focus, .kg-seg.is-open .kg-focus{ opacity: .5; }
.kg-text{ font-family: var(--w2b-font-mono); font-size: 10px; fill: var(--w2b-graphite); }
.kg-strong{ font-weight: 600; fill: var(--w2b-ink); }
.kg-plot{ fill: var(--w2b-map-surface); }
.kg-strip{ fill: var(--w2b-map-setback); }
</style>
