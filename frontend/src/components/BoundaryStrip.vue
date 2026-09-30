<template>
  <!-- One boundary straightened out and true to scale: above the line the
       neighbour's side, below it our plot with the setback strip, the reach,
       the 6-m-Zone and the envelope. Wider than a column, so it scrolls
       sideways in its own box. -->
  <div ref="box" class="scroll-x">
    <svg v-if="frameOf" :viewBox="`0 0 ${width} ${height}`" :style="{ '--w': `${width}px` }" role="img"
         :aria-label="`${title}, gerade gezogen, ${metres(frameOf.length, 1)}`">
      <defs>
        <pattern :id="`${id}-hint`" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="7" class="st-hint" />
        </pattern>
        <pattern :id="`${id}-zone`" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" class="st-zone-veil" />
          <line x1="0" y1="0" x2="0" y2="6" class="st-zone-line" />
          <line x1="0" y1="0" x2="6" y2="0" class="st-zone-line" />
        </pattern>
        <clipPath :id="`${id}-clip`">
          <rect x="0" :y="top" :width="width" :height="bandHeight" />
        </clipPath>
      </defs>
      <g :clip-path="`url(#${id}-clip)`">
        <rect class="st-ground" x="0" :y="top" :width="width" :height="bandHeight" />
        <polygon v-for="b in others" :key="b.id" :points="b.points" :class="`st-building st-building--${b.kind}`" />
        <polygon class="st-parcel" :points="tr(analysis.parcel)" />
        <path class="st-setback" fill-rule="evenodd" :d="`${trPath(analysis.parcel)} ${trPath(analysis.envelope.ring)}`" />
        <polygon v-for="m in analysis.maybeBuildable" :key="`mb${m.buildingId}`" class="st-maybe" :points="tr(m.ring)" />
        <template v-for="b in reach" :key="`r${b.id}`">
          <path :d="b.d" fill-rule="evenodd" :fill="`url(#${id}-hint)`" />
          <path :d="b.d" fill-rule="evenodd" class="st-hatch-edge" />
        </template>
        <template v-for="z in analysis.zones" :key="`z${z.buildingId}`">
          <path :d="z.rings.map(trPath).join(' ')" fill-rule="evenodd" :fill="`url(#${id}-zone)`" />
          <path :d="z.rings.map(trPath).join(' ')" fill-rule="evenodd" class="st-zone-edge" />
        </template>
        <polygon class="st-envelope" :points="tr(analysis.envelope.ring)" />
        <polygon class="st-halo" :points="tr(analysis.parcel)" />
        <polygon class="st-boundary" :points="tr(analysis.parcel)" />
        <polygon v-for="b in own" :key="b.id" :points="b.points" :class="`st-building st-building--${b.kind}`" />
        <template v-for="g in built" :key="`g${g.id}`">
          <line class="st-built" :x1="g.x1" :y1="lineY + 3.4" :x2="g.x2" :y2="lineY + 3.4" />
          <line v-for="x in [g.x1, g.x2]" :key="x" class="st-built-tick" :x1="x" :y1="lineY - 3" :x2="x" :y2="lineY + 9" />
        </template>
      </g>
      <text v-for="(l, i) in labels" :key="`l${i}`" class="st-label" :class="l.tone && `st-label--${l.tone}`"
            :x="l.x" :y="l.y" :text-anchor="l.anchor ?? 'middle'">{{ l.text }}</text>
      <line class="st-axis" :x1="X(0)" :y1="height - 24" :x2="X(frameOf.length)" :y2="height - 24" />
      <template v-for="t in ticks" :key="`t${t.at}`">
        <line class="st-axis" :x1="X(t.at)" :y1="height - 24" :x2="X(t.at)" :y2="height - (t.major ? 18 : 21)" />
        <text v-if="t.major" class="st-tick" :x="X(t.at)" :y="height - 7" text-anchor="middle">{{ t.at }}</text>
      </template>
      <text class="st-tick" :x="X(frameOf.length) + 4" :y="height - 7">{{ metres(frameOf.length, 1) }}</text>
    </svg>
  </div>
</template>

<script>
import { metres } from "../lib/format.js";
import { CLASS_BOUNDARY, CLASS_OWN, READING_BOUNDARY } from "../lib/neighbourhood.js";
import { stripFrame, drawnKind, shortName } from "../lib/neighbourhoodDrawing.js";

let instances = 0;

/* Metres shown on either side of the line. Up: the neighbour's wall and a
   bit of its house. Down: our 3 m and the 6-m-Zone behind it. */
const UP_M = 5.2;
const DOWN_M = 7.2;
const LEFT_PX = 18;
const TOP_PX = 22;
/* Roughly one character of the 10,5 px mono labels. */
const CHAR_PX = 6.4;

export default {
  name: "BoundaryStrip",
  props: {
    analysis: { type: Object, required: true },
    /** „street", „left", „right" or „rear". */
    boundary: { type: String, required: true },
    /** Pixels per metre. */
    scale: { type: Number, default: 8.6 },
    title: { type: String, default: "Grenze" },
    /** Metres along the boundary to scroll into the middle on opening. */
    focusAt: { type: Number, default: null }
  },
  data() { return { id: `strip-${++instances}`, top: TOP_PX }; },
  computed: {
    group() { return this.analysis.boundaries.find(b => b.kind === this.boundary) ?? null; },
    frameOf() { return this.group ? stripFrame(this.group, this.analysis.parcel) : null; },
    lineY() { return TOP_PX + UP_M * this.scale; },
    bandHeight() { return (UP_M + DOWN_M) * this.scale; },
    height() { return Math.round(this.lineY + DOWN_M * this.scale + 30); },
    width() { return Math.round(LEFT_PX + ((this.frameOf?.length ?? 0) + 3.2) * this.scale + 30); },
    /* Only what can land in the band is drawn: a building is in it when one of
       its corners lies within reach of this boundary's stretch. */
    near() {
      const f = this.frameOf;
      if (!f) return [];
      return this.analysis.buildings.filter(b => b.ring.some(p => {
        const u = f.u(p), w = f.w(p);
        return u > -12 && u < f.length + 12 && w > -DOWN_M - 12 && w < UP_M + 12;
      }));
    },
    others() {
      return this.near.filter(b => b.class !== CLASS_OWN).map(b => ({ id: b.id, kind: drawnKind(b), points: this.tr(b.ring) }));
    },
    own() {
      return this.near.filter(b => b.class === CLASS_OWN).map(b => ({ id: b.id, kind: drawnKind(b), points: this.tr(b.ring) }));
    },
    reach() {
      return this.analysis.buildings.filter(b => b.reach && b.reading !== READING_BOUNDARY)
        .map(b => ({ id: b.id, d: b.reach.rings.map(this.trPath).join(" ") }));
    },
    facing() {
      return this.analysis.buildings.filter(b => b.facing?.boundary === this.boundary);
    },
    built() {
      return this.facing.filter(b => b.class === CLASS_BOUNDARY)
        .map(b => ({ id: b.id, x1: this.X(b.facing.face.from), x2: this.X(b.facing.face.to) }));
    },
    labels() {
      const f = this.frameOf;
      if (!f) return [];
      const out = [];
      for (const b of this.facing) {
        const mid = (Math.max(b.facing.span.from, -3) + Math.min(b.facing.span.to, f.length + 3)) / 2;
        const name = `${shortName(b)} · ${metres(b.gap)}`;
        out.push({ x: this.within(this.X(mid) - 50, name.length * CHAR_PX, false), y: TOP_PX - 7, anchor: "start", text: name });
        if (b.zoneApplies && b.zone) {
          const text = `6-m-Zone · bis ${metres(b.zone.depthFromBoundary)}`;
          out.push({ x: this.within(this.X((b.facing.face.from + b.facing.face.to) / 2), text.length * CHAR_PX, true),
            y: this.lineY + 4.6 * this.scale + 4, text, tone: "zone" });
        }
        const strip = b.reading === READING_BOUNDARY ? this.analysis.maybeBuildable.find(m => m.buildingId === b.id) : null;
        if (strip) {
          const text = "möglicherweise bebaubar";
          out.push({ x: this.within(this.X((b.facing.face.from + b.facing.face.to) / 2), text.length * CHAR_PX, true),
            y: this.lineY + 1.5 * this.scale + 4, text, tone: "built" });
        }
      }
      return out;
    },
    ticks() {
      const out = [];
      const length = this.frameOf?.length ?? 0;
      // The last round mark stays clear of the length written at the end.
      for (let t = 0; t <= length - 2.5; t += 5) out.push({ at: t, major: t % 10 === 0 });
      return out;
    }
  },
  mounted() {
    // A long boundary opens at the stretch that matters, not at its corner.
    const box = this.$refs.box;
    if (box && Number.isFinite(this.focusAt) && box.clientWidth) {
      box.scrollLeft = Math.max(0, this.X(this.focusAt) - box.clientWidth / 2);
    }
  },
  methods: {
    metres,
    X(u) { return LEFT_PX + u * this.scale; },
    /** Keep a label of `length` px inside the drawing, centred or left-set. */
    within(x, length, centred) {
      const lo = centred ? length / 2 + 2 : 2, hi = this.width - (centred ? length / 2 : length) - 2;
      return Math.max(lo, Math.min(hi, x));
    },
    Y(w) { return this.lineY - w * this.scale; },
    tr(ring) {
      const f = this.frameOf;
      if (!f || !ring?.length) return "";
      return ring.map(p => `${this.X(f.u(p)).toFixed(1)},${this.Y(f.w(p)).toFixed(1)}`).join(" ");
    },
    trPath(ring) {
      const points = this.tr(ring);
      return points ? `M${points.replace(/ /g, "L")}Z` : "";
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
.st-ground{ fill: var(--w2b-map-ground); }
.st-parcel{ fill: var(--w2b-map-surface); }
.st-setback{ fill: var(--w2b-map-setback); }
.st-envelope{ fill: none; stroke: var(--w2b-map-envelope); stroke-width: 1.5; stroke-dasharray: 6 4; }
.st-halo{ fill: none; stroke: var(--w2b-map-halo); stroke-width: 6; stroke-linejoin: round; }
.st-boundary{ fill: none; stroke: var(--w2b-map-boundary); stroke-width: 2.2; stroke-linejoin: round; }
.st-building{ stroke-linejoin: round; }
.st-building--main{ fill: var(--w2b-map-neighbour-main); stroke: var(--w2b-map-neighbour-main-edge); stroke-width: 1; }
.st-building--aux{ fill: var(--w2b-map-neighbour-aux); stroke: var(--w2b-map-neighbour-aux-edge); stroke-width: .8; }
.st-building--own{ fill: var(--w2b-map-existing); stroke: var(--w2b-map-boundary); stroke-width: 1; }
.st-building--own-aux{ fill: var(--w2b-map-existing); fill-opacity: .55; stroke: var(--w2b-map-boundary); stroke-width: .8; }
.st-hint{ stroke: var(--w2b-map-reach); stroke-width: 1.1; }
.st-hatch-edge{ fill: none; stroke: var(--w2b-map-reach); stroke-width: .8; }
.st-zone-veil{ fill: var(--w2b-map-zone-veil); }
.st-zone-line{ stroke: var(--w2b-map-zone); stroke-width: 1.1; }
.st-zone-edge{ fill: none; stroke: var(--w2b-map-zone); stroke-width: 1.2; stroke-dasharray: 3 2; }
.st-maybe{ fill: var(--w2b-map-surface); stroke: var(--w2b-map-boundary-built); stroke-width: 1.4; stroke-dasharray: 1.5 3; stroke-linecap: round; }
.st-built{ stroke: var(--w2b-map-boundary-built); stroke-width: 4.5; }
.st-built-tick{ stroke: var(--w2b-map-boundary-built); stroke-width: 2; }
.st-label{
  font-family: var(--w2b-font-mono); font-size: 10.5px; font-weight: 500; fill: var(--w2b-map-boundary);
  paint-order: stroke fill; stroke: var(--w2b-map-halo); stroke-width: 3.4px; stroke-linejoin: round;
}
.st-label--zone{ fill: var(--w2b-map-zone); }
.st-label--built{ fill: var(--w2b-warning-text); }
.st-axis{ stroke: var(--w2b-muted); stroke-width: 1; }
.st-tick{ font-family: var(--w2b-font-mono); font-size: 9.5px; fill: var(--w2b-muted); }
</style>
