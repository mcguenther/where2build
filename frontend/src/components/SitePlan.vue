<template>
  <div class="site-plan-shell">
    <div v-if="hasBackdrop" ref="mapContainer" class="site-plan__map" aria-hidden="true"></div>
    <svg
    ref="svg"
    class="site-plan"
    :class="{ 'site-plan--dragging': dragging, 'site-plan--measuring': measuring }"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="ariaLabel"
    @pointerdown="pointerDown"
    @pointermove="pointerMove"
    @pointerup="pointerUp"
    @pointercancel="pointerUp"
    @keydown="onKeydown"
  >
    <defs>
      <marker :id="`dim-${uid}`" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto">
        <line x1="5" y1="1.5" x2="5" y2="8.5" stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
      </marker>
    </defs>

    <rect v-if="!hasBackdrop" x="0" y="0" :width="width" :height="height" :fill="backgroundFill" />

    <g :transform="`rotate(${rotation}, ${width / 2}, ${height / 2})`">
      <polygon :points="path(plot.polygon)" fill="var(--w2b-map-surface)"
               :fill-opacity="hasBackdrop ? 0.42 : 1" />

      <!-- The setback strip is what gets colour: marked is what may NOT be built on. -->
      <template v-if="showSetbacks && envelope.length">
        <path :d="setbackRing" fill-rule="evenodd" fill="var(--w2b-map-setback)" />
        <polygon :points="path(envelope)" fill="none" stroke="var(--w2b-map-envelope)"
                 stroke-width="1.5" stroke-dasharray="6 4" />
      </template>

      <line v-if="plot.divisionLine" :x1="p(plot.divisionLine[0]).x" :y1="p(plot.divisionLine[0]).y"
            :x2="p(plot.divisionLine[1]).x" :y2="p(plot.divisionLine[1]).y"
            stroke="var(--w2b-map-boundary)" stroke-width="1" stroke-dasharray="6 4" opacity=".4" />

      <!-- Halo first, then the line: without it boundaries vanish in an orthophoto. -->
      <polygon :points="path(plot.polygon)" fill="none" stroke="var(--w2b-map-halo)"
               :stroke-width="compact ? 3.5 : 6" stroke-linejoin="round" />
      <polygon :points="path(plot.polygon)" fill="none" stroke="var(--w2b-map-boundary)"
               :stroke-width="compact ? 1.5 : 2.2" stroke-linejoin="round" />
      <template v-if="!compact">
        <rect v-for="(v, i) in plot.polygon" :key="`v${i}`"
              :x="p(v).x - 2.5" :y="p(v).y - 2.5" width="5" height="5"
              fill="var(--w2b-map-halo)" stroke="var(--w2b-map-boundary)" stroke-width="1.4" />
      </template>

      <!-- The house: brass, because the user designed it -->
      <g :class="{ 'plan-handle': interactive }" :tabindex="interactive ? 0 : null"
         :role="interactive ? 'button' : null"
         :aria-label="interactive ? 'Baukörper — ziehen oder mit den Pfeiltasten verschieben' : null"
         data-house>
        <polygon :points="path(houseCorners)" fill="var(--w2b-map-design)" fill-opacity=".85"
                 :stroke="violation ? 'var(--w2b-map-violation)' : 'var(--w2b-map-design-edge)'"
                 :stroke-width="violation ? 2.4 : (compact ? 1.2 : 1.7)" />
        <circle v-for="(e, i) in outliers" :key="`a${i}`" :cx="p(e).x" :cy="p(e).y" r="4.5"
                fill="none" stroke="var(--w2b-map-violation)" stroke-width="1.7" />
      </g>

      <!-- Measuring tape: click sets a point, a second click closes the run. -->
      <g v-if="measuring && measurePoints.length" class="site-plan__measure">
        <polyline v-if="measurePoints.length > 1" :points="measureLine" fill="none"
                  stroke="var(--w2b-map-violation)" stroke-width="1.8" stroke-dasharray="6 4" />
        <line v-if="measurePoints.length === 1 && measurePointer"
              :x1="p(measurePoints[0]).x" :y1="p(measurePoints[0]).y"
              :x2="p(measurePointer).x" :y2="p(measurePointer).y"
              stroke="var(--w2b-map-violation)" stroke-width="1.4" stroke-dasharray="4 4" opacity=".7" />
        <circle v-for="(m, i) in measurePoints" :key="`m${i}`" :cx="p(m).x" :cy="p(m).y" r="4"
                fill="var(--w2b-map-halo)" stroke="var(--w2b-map-violation)" stroke-width="2" />
        <text v-for="(t, i) in measureLabels" :key="`mt${i}`" :x="t.x" :y="t.y"
              :transform="`rotate(${-rotation}, ${t.x}, ${t.y})`" class="site-plan__dimension site-plan__dimension--measuring">
          {{ t.text }}
        </text>
      </g>

      <!-- Dimension chains -->
      <g v-if="dimensionsVisible">
        <g v-for="(c, i) in dimensionChains" :key="`k${i}`">
          <line :x1="c.h1.x1" :y1="c.h1.y1" :x2="c.h1.x2" :y2="c.h1.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".7" opacity=".45" />
          <line :x1="c.h2.x1" :y1="c.h2.y1" :x2="c.h2.x2" :y2="c.h2.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".7" opacity=".45" />
          <line :x1="c.line.x1" :y1="c.line.y1" :x2="c.line.x2" :y2="c.line.y2"
                stroke="var(--w2b-map-boundary)" stroke-width="1"
                :marker-start="`url(#dim-${uid})`" :marker-end="`url(#dim-${uid})`" />
          <text :x="c.text.x" :y="c.text.y" :transform="`rotate(${-rotation}, ${c.text.x}, ${c.text.y})`"
                class="site-plan__dimension">{{ c.label }}</text>
        </g>
        <template v-if="narrowest">
          <line :x1="narrowest.x1" :y1="narrowest.y1" :x2="narrowest.x2" :y2="narrowest.y2"
                :stroke="narrowest.tight ? 'var(--w2b-map-violation)' : 'var(--w2b-map-envelope)'"
                stroke-width="1.4" stroke-dasharray="3 3" />
          <text :x="narrowest.tx" :y="narrowest.ty"
                :transform="`rotate(${-rotation}, ${narrowest.tx}, ${narrowest.ty})`"
                class="site-plan__dimension"
                :style="{ fill: narrowest.tight ? 'var(--w2b-map-violation)' : 'var(--w2b-map-envelope)' }">
            {{ narrowest.label }}
          </text>
        </template>
      </g>
    </g>

    <!-- North arrow and scale bar stay upright and stay in print: with the map
         turned to the street they are the only orientation left. -->
    <g v-if="!compact">
      <g :transform="`translate(${width - 58}, 74) rotate(${northAngle})`">
        <circle cx="0" cy="0" r="26" fill="var(--w2b-map-halo)" opacity=".65" />
        <path d="M0,-22 L7,12 L0,5 L-7,12 Z" fill="var(--w2b-map-boundary)" />
      </g>
      <text :x="width - 58" y="112" text-anchor="middle" class="site-plan__north">N</text>

      <g :transform="`translate(38, ${height - 44})`">
        <rect x="0" y="-5" :width="tenMetres" height="5" fill="var(--w2b-map-boundary)" />
        <rect :x="tenMetres" y="-5" :width="tenMetres" height="5" fill="none"
              stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
        <line x1="0" y1="0" :x2="tenMetres * 2" y2="0" stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
        <text x="0" y="15" class="site-plan__scale-bar" text-anchor="middle">0</text>
        <text :x="tenMetres" y="15" class="site-plan__scale-bar" text-anchor="middle">10</text>
        <text :x="tenMetres * 2" y="15" class="site-plan__scale-bar" text-anchor="end">20 m</text>
      </g>
    </g>
    </svg>
  </div>
</template>

<script>
import {
  buildableArea, polygonEdges, rectangleCorners, pointInPolygon,
  closestBoundaryPoint, boundingBox, alignmentToEdge
} from "../lib/geometry.js";
import { cameraFor } from "../lib/projection.js";
import { num } from "../lib/format.js";
// MapLibre 6 ships named exports only — there is no default.
// Its worker URL is set once in main.js; see the note there.
import { Map as MapLibreMap } from "maplibre-gl";

/* Every backdrop comes through our own backend. The vector style is rewritten
 * server-side so each URL inside it points back at /api/basemap/; the raster
 * layers are the authority's own WMS behind /api/tiles/. The browser therefore
 * needs no route to the internet, which is what makes this work behind a
 * firewall — and what stopped it working when the style was loaded directly. */
const MAP_STYLE_URL = "/api/basemap/style.json";

/**
 * The proxy answers with relative URLs, because only the browser knows which
 * origin it reached this API on. MapLibre needs them expanded before it can
 * use them: it rejects a relative `sprite` outright ("must be absolute"), and
 * handed a style object it has no base to resolve a source's TileJSON — and
 * then the relative tile URLs inside that TileJSON go nowhere, which is a
 * silent failure: the style never finishes loading and no tile is ever asked
 * for. So every URL is made absolute here, against this page.
 */
async function vectorStyle() {
  // A style that does not arrive means no backdrop, not a page that waits
  // forever: the drawing is what matters and it needs no network at all.
  const signal = AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined;
  const response = await fetch(MAP_STYLE_URL, { signal });
  if (!response.ok) throw new Error(`Kartenstil nicht ladbar (HTTP ${response.status})`);
  const style = await response.json();
  const origin = window.location.origin;
  const absolute = value => (typeof value === "string" && value.startsWith("/") ? `${origin}${value}` : value);

  if (style.glyphs) style.glyphs = absolute(style.glyphs);
  if (style.sprite) {
    style.sprite = Array.isArray(style.sprite)
      ? style.sprite.map(e => ({ ...e, url: absolute(e.url) }))
      : absolute(style.sprite);
  }
  // A source that points at a TileJSON is resolved here instead of by MapLibre:
  // the tile URLs inside that document are relative too, and MapLibre does not
  // resolve those against the source URL. Inlining them ends the guesswork.
  await Promise.all(Object.values(style.sources || {}).map(async source => {
    if (Array.isArray(source.tiles)) source.tiles = source.tiles.map(absolute);
    if (!source.url) return;
    const tilejson = await fetch(absolute(source.url), { signal }).then(r => (r.ok ? r.json() : null));
    if (!tilejson || !Array.isArray(tilejson.tiles)) return;
    delete source.url;
    Object.assign(source, tilejson, { type: source.type, tiles: tilejson.tiles.map(absolute) });
  }));
  return style;
}

/** A minimal raster style around one of the proxied WMS layers. */
const rasterStyle = (layer, attribution) => ({
  version: 8,
  sources: {
    [layer]: {
      type: "raster",
      tiles: [`${window.location.origin}/api/tiles/${layer}/{z}/{x}/{y}.png`],
      tileSize: 256,
      maxzoom: 20,
      attribution
    }
  },
  layers: [{ id: layer, type: "raster", source: layer }]
});

const GEOSN = "© GeoSN, dl-de/by-2-0";

/** What each backdrop offers. `none` keeps the drawing on plain paper. */
const BACKDROPS = {
  map: vectorStyle,
  aerial: async () => rasterStyle("dop", GEOSN),
  cadastre: async () => rasterStyle("alkis", GEOSN)
};

let instanceCount = 0;

export default {
  name: "SitePlan",
  props: {
    plot: { type: Object, required: true },
    building: { type: Object, required: true },   // {width, depth, cx, cy, rotation}
    width: { type: Number, default: 820 },
    height: { type: Number, default: 620 },
    interactive: { type: Boolean, default: false },
    compact: { type: Boolean, default: false },
    // "none" by default: a backdrop is a MapLibre instance, and the small
    // plans on cards and in the comparison must not each start one.
    backdrop: { type: String, default: "none" },
    northUp: { type: Boolean, default: false },
    showDimensions: { type: Boolean, default: true },
    showSetbacks: { type: Boolean, default: true },
    /** Fixed pixels per metre. Without it each plan fits its own frame. */
    scale: { type: Number, default: null },
    /** Measuring mode: clicks add points, the run is measured segment by segment. */
    measuring: { type: Boolean, default: false }
  },
  emits: ["move", "measured"],
  data() {
    return { uid: ++instanceCount, dragging: null, mapUnavailable: false, measurePoints: [], measurePointer: null };
  },
  computed: {
    ariaLabel() {
      return `Lageplan ${this.plot.name}: Flurstück, farbig markierte Abstandsfläche und Baukörper`;
    },
    /** Dimension chains are noise at thumbnail size. */
    dimensionsVisible() { return this.showDimensions && !this.compact; },
    /* Real outlines arrive already oriented: local +y is north. "Genordet"
       therefore means no rotation, and "straßenparallel" turns the drawing by
       the angle of the street front. */
    rotation() {
      if (this.northUp) return 0;
      // Normalised to (-90°, 90°]: the raw edge angle would turn the plan upside
      // down whenever the ring happens to run the other way round the boundary.
      return alignmentToEdge(this.plot.polygon, this.plot.streetEdge ?? 0);
    },
    northAngle() { return this.rotation; },
    /** A backdrop needs one that is not "none" and a georeference to put it
     *  under. Without the anchor there is nothing to align a map to. */
    hasBackdrop() { return this.backdrop !== "none" && Boolean(this.plot.anchor) && !this.mapUnavailable; },
    backgroundFill() { return this.backdrop === "aerial" ? "var(--w2b-map-green)" : "var(--w2b-map-ground)"; },

    /* Frame the plot with a margin, then stretch the box to the frame's aspect
       so the drawing fills the panel instead of floating in it. */
    view() {
      const box = boundingBox(this.plot.polygon);
      const margin = this.compact ? 6 : 40;
      const padding = 0.16;
      let bw = box.width * (1 + padding * 2);
      let bh = box.height * (1 + padding * 2);
      const aspect = (this.width - margin * 2) / (this.height - margin * 2);
      if (bw / bh < aspect) bw = bh * aspect; else bh = bw / aspect;
      const fitted = (this.width - margin * 2) / bw;
      /* A caller that hands us a scale is drawing several plots side by side
         and needs them comparable, so its value wins over our own fit. It is
         the smallest of the individual fits, so nothing overflows its frame. */
      const scale = Number.isFinite(this.scale) && this.scale > 0 ? this.scale : fitted;
      return { scale, mx: (box.minX + box.maxX) / 2, my: (box.minY + box.maxY) / 2 };
    },
    tenMetres() { return 10 * this.view.scale; },
    envelope() { return buildableArea(this.plot.polygon, this.plot.setbacks); },
    setbackRing() {
      const outer = this.plot.polygon.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      const inner = this.envelope.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      return `M${outer}Z M${inner}Z`;
    },
    houseCorners() { return rectangleCorners(this.building); },
    outliers() {
      if (!this.envelope.length) return this.houseCorners;
      return this.houseCorners.filter(e => !pointInPolygon(e, this.envelope));
    },
    violation() { return this.outliers.length > 0; },
    dimensionChains() {
      const edges = polygonEdges(this.plot.polygon);
      const h = this.houseCorners;
      const wanted = [
        { a: this.plot.polygon[1], b: this.plot.polygon[0], offset: 4.5, value: edges[0].length },
        { a: this.plot.polygon[0], b: this.plot.polygon[this.plot.polygon.length - 1], offset: 4.5,
          value: edges[edges.length - 1].length },
        { a: h[0], b: h[1], offset: -3.1, value: this.building.width },
        { a: h[1], b: h[2], offset: -3.1, value: this.building.depth }
      ];
      return wanted.map(c => this.dimensionChain(c.a, c.b, c.offset, `${num(c.value)} m`));
    },
    measureLine() {
      return this.measurePoints.map(m => { const q = this.p(m); return `${q.x.toFixed(1)},${q.y.toFixed(1)}`; }).join(" ");
    },
    /** One label per segment, plus the running total once there are three points. */
    measureLabels() {
      const labels = [];
      let total = 0;
      for (let i = 1; i < this.measurePoints.length; i++) {
        const a = this.measurePoints[i - 1], b = this.measurePoints[i];
        const length = Math.hypot(b.x - a.x, b.y - a.y);
        total += length;
        const A = this.p(a), B = this.p(b);
        labels.push({ x: (A.x + B.x) / 2, y: (A.y + B.y) / 2 - 7, text: `${num(length)} m` });
      }
      if (this.measurePoints.length > 2) {
        const last = this.p(this.measurePoints[this.measurePoints.length - 1]);
        labels.push({ x: last.x, y: last.y + 18, text: `gesamt ${num(total)} m` });
      }
      return labels;
    },
    narrowest() {
      if (!this.plot.polygon.length) return null;
      let best = { distance: Infinity };
      for (const corner of this.houseCorners) {
        const near = closestBoundaryPoint(corner, this.plot.polygon);
        if (near.distance < best.distance) best = { ...near, from: corner };
      }
      if (!best.point) return null;
      const a = this.p(best.from), b = this.p(best.point);
      const required = Math.min(...this.plot.setbacks);
      return {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        tx: (a.x + b.x) / 2, ty: (a.y + b.y) / 2 - 7,
        tight: best.distance < required - 0.01,
        label: `${num(best.distance)} m`
      };
    }
  },
  created() { this._mapRun = 0; },
  mounted() { this.buildMap(); },
  beforeUnmount() { this.destroyMap(); },
  watch: {
    // A different backdrop means a different style; MapLibre cannot swap sources
    // underneath itself, so the map is torn down and rebuilt.
    hasBackdrop() { this.rebuildMap(); },
    backdrop() { this.rebuildMap(); },
    measuring(on) { if (!on) this.clearMeasurement(); },
    "plot.id"() {
      this.clearMeasurement();
      this.rebuildMap();
    },
    rotation() { this.setCamera(); },
    view() { this.setCamera(); }
  },
  methods: {
    /** MapLibre needs WebGL and a network; neither is guaranteed. Any failure
     *  leaves the drawing alone rather than taking the page down with it. */
    rebuildMap() {
      this.destroyMap();
      this.mapUnavailable = false;
      // The container only exists once `hasBackdrop` has re-rendered it.
      this.$nextTick(() => this.buildMap());
    },
    async buildMap() {
      if (!this.hasBackdrop || !this.plot.anchor || this._map) return;
      const run = ++this._mapRun;
      try {
        const style = await BACKDROPS[this.backdrop]();
        // The backdrop may have changed again while the style was in flight.
        if (run !== this._mapRun || !this.$refs.mapContainer || this._map) return;
        this._map = new MapLibreMap({
          container: this.$refs.mapContainer,
          style,
          center: [this.plot.anchor.lon, this.plot.anchor.lat],
          zoom: 17,
          interactive: false,
          attributionControl: false,
          // Set at construction or the map prints blank — it cannot be added later.
          preserveDrawingBuffer: true
        });
        this._map.on("load", () => this.setCamera());
        // A single missing icon or tile is not a broken map. Tearing the
        // backdrop down for one of those is what made it look permanently
        // unavailable; only a style that never loads counts as a failure.
        this._map.on("error", e => console.warn("Karte:", e?.error?.message || e));
        this.setCamera();
      } catch (error) {
        // A missing basemap must not take the drawing down, but staying silent
        // about it would hide a broken build.
        console.warn("Kartenhintergrund nicht verfügbar:", error);
        if (run === this._mapRun) this.mapUnavailable = true;
      }
    },
    destroyMap() {
      if (this._map) { this._map.remove(); this._map = null; }
    },
    /** Put the camera exactly where the drawing is, so overlay and ground agree. */
    setCamera() {
      if (!this._map || !this.plot.anchor) return;
      const renderedWidth = this.$refs.svg?.getBoundingClientRect().width || this.width;
      this._map.jumpTo(cameraFor({
        anchor: this.plot.anchor,
        centreMetres: { x: this.view.mx, y: this.view.my },
        metresPerPixel: 1 / (this.view.scale * (renderedWidth / this.width)),
        rotation: this.rotation
      }));
      this._map.resize();
    },
    px(x) { return this.width / 2 + (x - this.view.mx) * this.view.scale; },
    py(y) { return this.height / 2 - (y - this.view.my) * this.view.scale; },
    p(v) {
      const point = Array.isArray(v) ? { x: v[0], y: v[1] } : v;
      return { x: this.px(point.x), y: this.py(point.y) };
    },
    path(ring) { return ring.map(v => { const q = this.p(v); return `${q.x.toFixed(1)},${q.y.toFixed(1)}`; }).join(" "); },
    /** One dimension chain: two witness lines, the measure line, and a label. */
    dimensionChain(a, b, offset, label) {
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      const n = { x: -dy / len, y: dx / len };
      const a2 = { x: a.x + n.x * offset, y: a.y + n.y * offset };
      const b2 = { x: b.x + n.x * offset, y: b.y + n.y * offset };
      const middle = { x: (a2.x + b2.x) / 2 + n.x * 1.6, y: (a2.y + b2.y) / 2 + n.y * 1.6 };
      const A = this.p(a), B = this.p(b), A2 = this.p(a2), B2 = this.p(b2), M = this.p(middle);
      return {
        h1: { x1: A.x, y1: A.y, x2: A2.x, y2: A2.y },
        h2: { x1: B.x, y1: B.y, x2: B2.x, y2: B2.y },
        line: { x1: A2.x, y1: A2.y, x2: B2.x, y2: B2.y },
        text: { x: M.x, y: M.y + 3.5 },
        label
      };
    },
    /** Screen pixels back to metres, undoing the map rotation. */
    toMetres(event) {
      const rect = this.$refs.svg.getBoundingClientRect();
      const k = this.width / rect.width;
      const px = (event.clientX - rect.left) * k;
      const py = (event.clientY - rect.top) * k;
      const r = (this.rotation * Math.PI) / 180;
      const dx = px - this.width / 2, dy = py - this.height / 2;
      const ux = dx * Math.cos(-r) - dy * Math.sin(-r);
      const uy = dx * Math.sin(-r) + dy * Math.cos(-r);
      return { x: this.view.mx + ux / this.view.scale, y: this.view.my - uy / this.view.scale };
    },
    /** In measuring mode a click adds a point; a double click ends the run. */
    measureClick(event) {
      const point = this.toMetres(event);
      this.measurePoints = [...this.measurePoints, point];
      this.$emit("measured", { points: this.measurePoints, length: this.measureLength() });
    },
    measureLength() {
      let total = 0;
      for (let i = 1; i < this.measurePoints.length; i++) {
        total += Math.hypot(this.measurePoints[i].x - this.measurePoints[i - 1].x,
                            this.measurePoints[i].y - this.measurePoints[i - 1].y);
      }
      return total;
    },
    clearMeasurement() {
      this.measurePoints = [];
      this.measurePointer = null;
      this.$emit("measured", { points: [], length: 0 });
    },
    pointerDown(event) {
      if (this.measuring) { this.measureClick(event); return; }
      if (!this.interactive || !event.target.closest("[data-house]")) return;
      const point = this.toMetres(event);
      this.dragging = { dx: this.building.cx - point.x, dy: this.building.cy - point.y };
      this.$refs.svg.setPointerCapture(event.pointerId);
      event.preventDefault();
    },
    pointerMove(event) {
      if (this.measuring) { if (this.measurePoints.length) this.measurePointer = this.toMetres(event); return; }
      if (!this.dragging) return;
      const point = this.toMetres(event);
      this.$emit("move", { cx: point.x + this.dragging.dx, cy: point.y + this.dragging.dy });
    },
    pointerUp() { this.dragging = null; },
    onKeydown(event) {
      if (!this.interactive || !event.target.closest("[data-house]")) return;
      const step = event.shiftKey ? 1 : 0.25;
      const direction = {
        ArrowLeft: [-step, 0], ArrowRight: [step, 0],
        ArrowUp: [0, step], ArrowDown: [0, -step]
      }[event.key];
      if (!direction) return;
      event.preventDefault();
      this.$emit("move", { cx: this.building.cx + direction[0], cy: this.building.cy + direction[1] });
    }
  }
};
</script>

<style scoped>
.site-plan-shell{ position: relative; }
.site-plan__map{ position: absolute; inset: 0; }
.site-plan{ display: block; width: 100%; height: auto; touch-action: none; position: relative; }
.site-plan--dragging{ cursor: grabbing; }
.site-plan--measuring{ cursor: crosshair; }
.site-plan__dimension--measuring{ fill: var(--w2b-map-violation); }
.plan-handle{ cursor: grab; }
.site-plan__dimension{
  font-family: var(--w2b-font-mono); font-size: 10.5px; font-weight: 500;
  fill: var(--w2b-map-boundary); text-anchor: middle;
  paint-order: stroke fill; stroke: var(--w2b-map-halo); stroke-width: 3.4px; stroke-linejoin: round;
}
.site-plan__north{
  font-family: var(--w2b-font-display); font-size: 14px; font-weight: 600;
  fill: var(--w2b-map-boundary); text-anchor: middle;
  paint-order: stroke fill; stroke: var(--w2b-map-halo); stroke-width: 3px;
}
.site-plan__scale-bar{
  font-family: var(--w2b-font-mono); font-size: 9.5px; fill: var(--w2b-map-boundary);
  paint-order: stroke fill; stroke: var(--w2b-map-halo); stroke-width: 3px;
}
</style>
