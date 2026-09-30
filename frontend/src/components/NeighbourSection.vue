<template>
  <!-- A cut across the plot, square to the boundary a neighbour stands at.
       Walls are schematic: neither ALKIS nor OSM knows a wall height, so the
       drawing fades them out upwards and says „Höhe unbekannt" rather than
       inventing one. Under the ground line, from the top: our setback, the
       neighbour's 3 m and the 6-m-Zone. -->
  <div class="scroll-x">
    <svg :viewBox="`0 0 ${width} ${HEIGHT}`" :style="{ '--w': `${width}px` }" role="img"
         :aria-label="`Schnitt ${index + 1} durch ${title}, Höhe unbekannt`">
      <defs>
        <pattern :id="`${id}-hint`" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="7" class="sc-hint" />
        </pattern>
        <pattern :id="`${id}-zone`" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" class="sc-zone-veil" />
          <line x1="0" y1="0" x2="0" y2="6" class="sc-zone-line" />
          <line x1="0" y1="0" x2="6" y2="0" class="sc-zone-line" />
        </pattern>
        <linearGradient v-for="kind in ['main', 'own']" :id="`${id}-${kind}`" :key="kind"
                        :class="`sc-wall--${kind}`" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stop-color="currentColor" stop-opacity="1" />
          <stop offset=".72" stop-color="currentColor" stop-opacity=".85" />
          <stop offset="1" stop-color="currentColor" stop-opacity="0" />
        </linearGradient>
      </defs>
      <rect class="sc-sky" :width="width" :height="HEIGHT" />
      <rect class="sc-soil" x="0" :y="GROUND" :width="width" :height="HEIGHT - GROUND" />
      <rect v-if="plotSpan" class="sc-plot" :x="left(plotSpan[0], plotSpan[1])" :y="GROUND"
            :width="span(plotSpan[0], plotSpan[1])" :height="HEIGHT - GROUND" />

      <!-- Lane 1: our setback strips, or the strip a reading makes maybe buildable. -->
      <rect v-for="(iv, i) in ourSetback" :key="`s${i}`" :class="iv.maybe ? 'sc-maybe' : 'sc-strip'"
            :x="left(iv.from, iv.to)" :y="LANE[0]" :width="span(iv.from, iv.to)" :height="LANE_H" />
      <text v-for="(iv, i) in ourSetback" :key="`st${i}`" class="sc-text" :x="mid(iv.from, iv.to)"
            :y="LANE[0] + 11" text-anchor="middle">{{ iv.maybe ? "evtl. bebaubar" : metres(iv.to - iv.from, 1) }}</text>

      <!-- Lane 2: the neighbour's own 3 m, hatched where it reaches onto us. -->
      <template v-if="theirs">
        <rect class="sc-their" :x="left(theirs.from, theirs.to)" :y="LANE[1]" :width="span(theirs.from, theirs.to)" :height="LANE_H" />
        <rect v-for="(iv, i) in section.reach" :key="`r${i}`" :x="left(iv[0], iv[1])" :y="LANE[1]"
              :width="span(iv[0], iv[1])" :height="LANE_H" :fill="`url(#${id}-hint)`" />
        <text class="sc-text sc-text--muted" :x="theirsLabel.x" :y="LANE[1] + 11"
              :text-anchor="theirsLabel.anchor">3 m von {{ neighbourName }}</text>
      </template>
      <text v-else-if="building" class="sc-text sc-text--built" :x="X(0) + (flip ? -6 : 6)" :y="LANE[1] + 11"
            :text-anchor="flip ? 'end' : 'start'">{{ neighbourName }}: an der Grenze</text>

      <!-- Lane 3: the 6-m-Zone, where it applies under the reading. -->
      <template v-for="(iv, i) in zone" :key="`z${i}`">
        <rect :x="left(iv[0], iv[1])" :y="LANE[2]" :width="span(iv[0], iv[1])" :height="LANE_H" :fill="`url(#${id}-zone)`" />
        <rect class="sc-zone-edge" :x="left(iv[0], iv[1])" :y="LANE[2]" :width="span(iv[0], iv[1])" :height="LANE_H" />
        <text class="sc-text sc-text--zone sc-halo" :x="beside(iv[0], iv[1], zoneText(iv)).x" :y="LANE[2] + 11"
              :text-anchor="beside(iv[0], iv[1], zoneText(iv)).anchor">{{ zoneText(iv) }}</text>
      </template>

      <!-- The walls, schematic. -->
      <template v-for="(w, i) in walls" :key="`w${i}`">
        <rect :x="w.x" :y="GROUND - WALL_H" :width="w.width" :height="WALL_H" :fill="`url(#${id}-${w.kind})`" />
        <text class="sc-name" :x="w.x + w.width / 2" :y="GROUND - WALL_H - 6" text-anchor="middle">{{ w.name }}</text>
        <text v-if="w.width > 60" class="sc-unknown" :x="w.x + w.width / 2" :y="GROUND - 26" text-anchor="middle">Höhe unbekannt</text>
      </template>

      <!-- The envelope, with its width. -->
      <template v-for="(iv, i) in section.envelope" :key="`e${i}`">
        <line v-for="x in [iv[0], iv[1]]" :key="x" class="sc-env" :x1="X(x)" :y1="GROUND + 2" :x2="X(x)" :y2="GROUND - WALL_H - 22" />
        <line class="sc-env-dim" :x1="X(iv[0])" :y1="GROUND - WALL_H - 16" :x2="X(iv[1])" :y2="GROUND - WALL_H - 16" />
        <text class="sc-text sc-text--env sc-halo" :x="mid(iv[0], iv[1])" :y="GROUND - WALL_H - 22"
              text-anchor="middle">Fenster {{ metres(iv[1] - iv[0], 1) }}</text>
      </template>

      <line class="sc-ground" x1="0" :y1="GROUND" :x2="width" :y2="GROUND" />
      <line v-for="x in boundaries" :key="`b${x}`" class="sc-boundary" :x1="X(x)" :y1="GROUND - 18" :x2="X(x)" :y2="HEIGHT" />
      <template v-if="gap !== null && gap >= 0.05">
        <line class="sc-dim" :x1="X(0)" :y1="GROUND - 10" :x2="X(-gap)" :y2="GROUND - 10" />
        <text class="sc-text sc-halo" :x="mid(-gap, 0)" :y="GROUND - 14" text-anchor="middle">{{ metres(gap) }}</text>
      </template>
      <text v-if="lanes" class="sc-lane" :x="PAD" :y="LANE[0] + 10">unsere Abstandsfläche</text>
      <text v-if="lanes" class="sc-lane" :x="PAD" :y="LANE[1] + 10">die der Nachbarn</text>
      <text v-if="lanes" class="sc-lane" :x="PAD" :y="LANE[2] + 10">6-m-Zone</text>
      <text class="sc-lane" :x="PAD + gutter" y="14">{{ flip ? "← unser Grundstück" : `← ${neighbourName}` }}</text>
      <text class="sc-lane" :x="width - PAD" y="14" text-anchor="end">{{ flip ? `${neighbourName} →` : "unser Grundstück →" }}</text>
    </svg>
  </div>
</template>

<script>
import { metres } from "../lib/format.js";
import { CLASS_OWN, READING_BOUNDARY, MINIMUM_SETBACK_M } from "../lib/neighbourhood.js";
import { drawnKind, shortName } from "../lib/neighbourhoodDrawing.js";

let instances = 0;
const HEIGHT = 250;
const GROUND = 132;
const WALL_H = 80;
const LANE = [GROUND + 8, GROUND + 30, GROUND + 52];
const LANE_H = 14;
const PAD = 16;
const GUTTER = 150;
/* Roughly one character of the 10 px mono labels. */
const CHAR_PX = 6.1;

export default {
  name: "NeighbourSection",
  props: {
    analysis: { type: Object, required: true },
    /** One entry of `analysis.sections`. */
    section: { type: Object, required: true },
    index: { type: Number, default: 0 },
    /** Pixels per metre. At 13 and more the lanes are named in the drawing. */
    scale: { type: Number, default: 11 }
  },
  data() { return { id: `section-${++instances}`, HEIGHT, GROUND, WALL_H, LANE, LANE_H, PAD }; },
  computed: {
    building() { return this.analysis.buildings.find(b => b.id === this.section.buildingId) ?? null; },
    neighbourName() { return shortName(this.building); },
    title() { return this.building?.address || this.neighbourName; },
    /* Looking from the street, a neighbour on the right side stands on the
       right of the drawing. */
    flip() { return this.section.boundary === "right"; },
    lanes() { return this.scale >= 13; },
    plotSpan() {
      const far = this.section.oppositeBoundary;
      return Number.isFinite(far) ? [0, far] : null;
    },
    tMin() {
      const near = this.section.neighbour.map(iv => iv[0]).filter(Number.isFinite);
      const back = near.length ? Math.min(...near) : -8;
      return Math.max(this.section.from, Math.min(-8, back - 2));
    },
    tMax() { return (this.plotSpan ? this.plotSpan[1] : this.section.to) + 3; },
    /* The lane names get a gutter of their own at the left; drawn over the
       strips they collided with the setback figures. */
    gutter() { return this.lanes ? GUTTER : 0; },
    width() { return Math.round((this.tMax - this.tMin) * this.scale + 2 * PAD + this.gutter); },
    boundaries() { return this.plotSpan ? this.plotSpan : [0]; },
    gap() {
      const wall = this.section.neighbourWall;
      return Number.isFinite(wall) ? Math.max(0, -wall) : null;
    },
    /* Our setback in the cut: the plot minus the envelope. Under „an die
       Grenze" the stretch along this neighbour is maybe buildable instead. */
    ourSetback() {
      if (!this.plotSpan) return [];
      const [a, b] = this.plotSpan;
      const env = [...this.section.envelope].sort((x, y) => x[0] - y[0]);
      const pieces = [];
      let at = a;
      for (const [from, to] of env) {
        if (from > at + 0.01) pieces.push({ from: at, to: Math.min(from, b) });
        at = Math.max(at, to);
      }
      if (b > at + 0.01) pieces.push({ from: at, to: b });
      const maybe = this.section.reading === READING_BOUNDARY ? this.section.maybeBuildable : [];
      return pieces.map(p => ({
        ...p, maybe: maybe.some(([from, to]) => from < p.to - 0.01 && to > p.from + 0.01)
      }));
    },
    /** The neighbour's own 3 m, where it needs one: not under „an die Grenze". */
    theirs() {
      const wall = this.section.neighbourWall;
      if (!Number.isFinite(wall)) return null;
      if (this.section.reading === READING_BOUNDARY) return null;
      return { from: wall, to: wall + MINIMUM_SETBACK_M };
    },
    theirsLabel() {
      const t = this.theirs;
      if (!t) return { x: 0, anchor: "start" };
      return this.beside(t.from, t.to, `3 m von ${this.neighbourName}`);
    },
    zone() { return this.building?.zoneApplies ? this.section.zone : []; },
    walls() {
      const out = [];
      const add = (b, intervals) => {
        const kind = b && b.class === CLASS_OWN ? "own" : "main";
        for (const [a, c] of intervals) {
          const lo = Math.max(a, this.tMin), hi = Math.min(c, this.tMax);
          if (hi - lo < 0.2) continue;
          if (b && drawnKind(b) === "aux" && b.class !== CLASS_OWN) continue;
          const name = b?.class === CLASS_OWN ? "Bestand" : (b?.address ?? shortName(b));
          out.push({ x: this.left(lo, hi), width: this.span(lo, hi), kind, name });
        }
      };
      add(this.building, this.section.neighbour);
      for (const other of this.section.buildings) {
        add(this.analysis.buildings.find(b => b.id === other.buildingId), other.intervals);
      }
      return out;
    }
  },
  methods: {
    metres,
    X(t) {
      const x0 = PAD + this.gutter;
      return this.flip ? x0 + (this.tMax - t) * this.scale : x0 + (t - this.tMin) * this.scale;
    },
    left(a, b) { return Math.min(this.X(a), this.X(b)); },
    span(a, b) { return Math.abs(this.X(b) - this.X(a)); },
    mid(a, b) { return (this.X(a) + this.X(b)) / 2; },
    zoneText(iv) { return `${metres(iv[1] - iv[0])} ins Fenster`; },
    /** A label next to an interval: after it where it fits in the drawing,
     *  before it where it would run off the edge and lose its number. */
    beside(a, b, text) {
      const room = text.length * CHAR_PX + 5;
      const right = this.left(a, b) + this.span(a, b);
      if (right + room <= this.width - 2) return { x: right + 5, anchor: "start" };
      return { x: this.left(a, b) - 5, anchor: "end" };
    }
  }
};
</script>

<style scoped>
/* Drawn at its own scale where there is room, scaled down to the column
   where there is not — a label cut off at the edge hid its number. Only on a
   phone does it keep its scale and scroll sideways in its own box. */
.scroll-x{ overflow-x: auto; overscroll-behavior-x: contain; max-width: 100%; }
.scroll-x svg{ display: block; width: var(--w); max-width: 100%; height: auto; }
@media (max-width: 520px){ .scroll-x svg{ max-width: none; } }
.sc-sky{ fill: var(--w2b-surface); }
.sc-soil{ fill: var(--w2b-map-soil); }
.sc-plot{ fill: var(--w2b-map-surface); }
.sc-strip{ fill: var(--w2b-map-setback); }
.sc-maybe{ fill: var(--w2b-map-surface); stroke: var(--w2b-map-boundary-built); stroke-width: 1.2; stroke-dasharray: 1.5 3; }
.sc-their{ fill: none; stroke: var(--w2b-map-reach); stroke-width: .8; stroke-dasharray: 3 2; }
.sc-hint{ stroke: var(--w2b-map-reach); stroke-width: 1.1; }
.sc-zone-veil{ fill: var(--w2b-map-zone-veil); }
.sc-zone-line{ stroke: var(--w2b-map-zone); stroke-width: 1.1; }
.sc-zone-edge{ fill: none; stroke: var(--w2b-map-zone); stroke-width: 1.2; stroke-dasharray: 3 2; }
.sc-wall--main{ color: var(--w2b-map-neighbour-main); }
.sc-wall--own{ color: var(--w2b-map-existing); }
.sc-ground{ stroke: var(--w2b-ink); stroke-width: 1.4; }
.sc-boundary{ stroke: var(--w2b-map-boundary); stroke-width: 1.4; stroke-dasharray: 4 3; }
.sc-env{ stroke: var(--w2b-map-envelope); stroke-width: 1.2; stroke-dasharray: 5 3; }
.sc-env-dim, .sc-dim{ stroke: var(--w2b-graphite); stroke-width: .9; }
.sc-text{ font-family: var(--w2b-font-mono); font-size: 10px; fill: var(--w2b-graphite); }
.sc-text--muted{ fill: var(--w2b-muted); }
.sc-text--zone{ fill: var(--w2b-map-zone); }
.sc-text--built{ fill: var(--w2b-warning-text); }
.sc-text--env{ fill: var(--w2b-map-envelope); }
.sc-halo{ paint-order: stroke fill; stroke: var(--w2b-surface); stroke-width: 3px; stroke-linejoin: round; }
.sc-name{ font-family: var(--w2b-font-display); font-weight: 600; font-size: 12px; fill: var(--w2b-ink); }
.sc-unknown{ font-family: var(--w2b-font-mono); font-size: 10px; fill: var(--w2b-ink); opacity: .75; }
.sc-lane{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 9.5px; letter-spacing: .1em;
  text-transform: uppercase; fill: var(--w2b-muted);
}
</style>
