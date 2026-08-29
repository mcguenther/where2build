<template>
  <svg
    ref="flaeche"
    class="lageplan"
    :class="{ 'lageplan--zieht': ziehen }"
    :viewBox="`0 0 ${breite} ${hoehe}`"
    role="img"
    :aria-label="beschriftung"
    @pointerdown="griffFassen"
    @pointermove="griffZiehen"
    @pointerup="griffLoslassen"
    @pointercancel="griffLoslassen"
    @keydown="tastatur"
  >
    <defs>
      <pattern :id="`nachbar-${uid}`" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--w2b-karte-nachbar)" stroke-width="1.6" opacity=".8" />
      </pattern>
      <marker :id="`kote-${uid}`" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto">
        <line x1="5" y1="1.5" x2="5" y2="8.5" stroke="var(--w2b-karte-grenze)" stroke-width="1.2" />
      </marker>
    </defs>

    <rect x="0" y="0" :width="breite" :height="hoehe" :fill="grundfarbe" />

    <g :transform="`rotate(${drehung}, ${breite / 2}, ${hoehe / 2})`">
      <!-- Basemap stand-in. Real tiles arrive through the backend proxy later. -->
      <g v-if="grund === 'luftbild'" opacity=".55">
        <ellipse v-for="(b, i) in gruenflaechen" :key="`g${i}`"
                 :cx="b[0]" :cy="b[1]" :rx="b[2]" :ry="b[3]" fill="var(--w2b-salbei)" :opacity="i % 2 ? .3 : .2" />
      </g>
      <g v-else-if="grund === 'kataster'" stroke="var(--w2b-karte-nachbar)" stroke-width="1" opacity=".16">
        <line v-for="l in raster" :key="l.k" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
      </g>

      <!-- Street: brass edge along the carriageway, as in the legend -->
      <polygon :points="pfad(umfeld.street)" fill="var(--w2b-karte-strasse-flaeche)" />
      <line :x1="strassenkante.x1" :y1="strassenkante.y1" :x2="strassenkante.x2" :y2="strassenkante.y2"
            stroke="var(--w2b-karte-strasse)" :stroke-width="kompakt ? 2 : 3" />

      <!-- Neighbouring parcels and their buildings -->
      <polygon v-for="(n, i) in umfeld.parcels" :key="`n${i}`" :points="pfad(n)"
               fill="none" stroke="var(--w2b-karte-nachbar)" stroke-width="1.1" stroke-dasharray="5 4" />
      <template v-if="nachbarn">
        <polygon v-for="(b, i) in umfeld.buildings" :key="`b${i}`" :points="pfad(ecken(b))"
                 :fill="`url(#nachbar-${uid})`" stroke="var(--w2b-karte-nachbar)" stroke-width="1.1" />
      </template>

      <!-- The plot -->
      <polygon :points="pfad(plot.polygon)" fill="var(--w2b-karte-flaeche)" />

      <!-- The setback strip is what gets colour: marked is what may NOT be built on. -->
      <template v-if="saum && fenster.length">
        <path :d="saumRing" fill-rule="evenodd" fill="var(--w2b-karte-saum)" />
        <polygon :points="pfad(fenster)" fill="none" stroke="var(--w2b-karte-fenster)"
                 stroke-width="1.5" stroke-dasharray="6 4" />
      </template>

      <line v-if="plot.teilung" :x1="p(plot.teilung[0]).x" :y1="p(plot.teilung[0]).y"
            :x2="p(plot.teilung[1]).x" :y2="p(plot.teilung[1]).y"
            stroke="var(--w2b-karte-grenze)" stroke-width="1" stroke-dasharray="6 4" opacity=".4" />

      <!-- Halo first, then the line: without it boundaries vanish in an orthophoto. -->
      <polygon :points="pfad(plot.polygon)" fill="none" stroke="var(--w2b-karte-halo)"
               :stroke-width="kompakt ? 3.5 : 6" stroke-linejoin="round" />
      <polygon :points="pfad(plot.polygon)" fill="none" stroke="var(--w2b-karte-grenze)"
               :stroke-width="kompakt ? 1.5 : 2.2" stroke-linejoin="round" />
      <template v-if="!kompakt">
        <rect v-for="(v, i) in plot.polygon" :key="`v${i}`"
              :x="p(v).x - 2.5" :y="p(v).y - 2.5" width="5" height="5"
              fill="var(--w2b-karte-halo)" stroke="var(--w2b-karte-grenze)" stroke-width="1.4" />
      </template>

      <!-- The house: brass, because the user designed it -->
      <g :class="{ 'plan-griff': interaktiv }" :tabindex="interaktiv ? 0 : null"
         :role="interaktiv ? 'button' : null"
         :aria-label="interaktiv ? 'Baukörper — ziehen oder mit den Pfeiltasten verschieben' : null"
         data-haus>
        <polygon :points="pfad(hausEcken)" fill="var(--w2b-karte-entwurf)" fill-opacity=".85"
                 :stroke="verstoss ? 'var(--w2b-karte-verstoss)' : 'var(--w2b-karte-entwurf-rand)'"
                 :stroke-width="verstoss ? 2.4 : (kompakt ? 1.2 : 1.7)" />
        <circle v-for="(e, i) in ausreisser" :key="`a${i}`" :cx="p(e).x" :cy="p(e).y" r="4.5"
                fill="none" stroke="var(--w2b-karte-verstoss)" stroke-width="1.7" />
      </g>

      <!-- Dimension chains -->
      <g v-if="zeigeMasse">
        <g v-for="(k, i) in ketten" :key="`k${i}`">
          <line :x1="k.h1.x1" :y1="k.h1.y1" :x2="k.h1.x2" :y2="k.h1.y2"
                stroke="var(--w2b-karte-grenze)" stroke-width=".7" opacity=".45" />
          <line :x1="k.h2.x1" :y1="k.h2.y1" :x2="k.h2.x2" :y2="k.h2.y2"
                stroke="var(--w2b-karte-grenze)" stroke-width=".7" opacity=".45" />
          <line :x1="k.linie.x1" :y1="k.linie.y1" :x2="k.linie.x2" :y2="k.linie.y2"
                stroke="var(--w2b-karte-grenze)" stroke-width="1"
                :marker-start="`url(#kote-${uid})`" :marker-end="`url(#kote-${uid})`" />
          <text :x="k.text.x" :y="k.text.y" :transform="`rotate(${-drehung}, ${k.text.x}, ${k.text.y})`"
                class="lageplan__mass">{{ k.label }}</text>
        </g>
        <template v-if="engstelle">
          <line :x1="engstelle.x1" :y1="engstelle.y1" :x2="engstelle.x2" :y2="engstelle.y2"
                :stroke="engstelle.eng ? 'var(--w2b-karte-verstoss)' : 'var(--w2b-karte-fenster)'"
                stroke-width="1.4" stroke-dasharray="3 3" />
          <text :x="engstelle.tx" :y="engstelle.ty"
                :transform="`rotate(${-drehung}, ${engstelle.tx}, ${engstelle.ty})`"
                class="lageplan__mass"
                :style="{ fill: engstelle.eng ? 'var(--w2b-karte-verstoss)' : 'var(--w2b-karte-fenster)' }">
            {{ engstelle.label }}
          </text>
        </template>
      </g>
    </g>

    <!-- North arrow and scale bar stay upright and stay in print: with the map
         turned to the street they are the only orientation left. -->
    <g v-if="!kompakt">
      <g :transform="`translate(${breite - 58}, 74) rotate(${nordWinkel})`">
        <circle cx="0" cy="0" r="26" fill="var(--w2b-karte-halo)" opacity=".65" />
        <path d="M0,-22 L7,12 L0,5 L-7,12 Z" fill="var(--w2b-karte-grenze)" />
      </g>
      <text :x="breite - 58" y="112" text-anchor="middle" class="lageplan__nord">N</text>

      <g :transform="`translate(38, ${hoehe - 44})`">
        <rect x="0" y="-5" :width="zehnMeter" height="5" fill="var(--w2b-karte-grenze)" />
        <rect :x="zehnMeter" y="-5" :width="zehnMeter" height="5" fill="none"
              stroke="var(--w2b-karte-grenze)" stroke-width="1.2" />
        <line x1="0" y1="0" :x2="zehnMeter * 2" y2="0" stroke="var(--w2b-karte-grenze)" stroke-width="1.2" />
        <text x="0" y="15" class="lageplan__leiste" text-anchor="middle">0</text>
        <text :x="zehnMeter" y="15" class="lageplan__leiste" text-anchor="middle">10</text>
        <text :x="zehnMeter * 2" y="15" class="lageplan__leiste" text-anchor="end">20 m</text>
      </g>
    </g>
  </svg>
</template>

<script>
import {
  buildableArea, polygonEdges, rectangleCorners, pointInPolygon,
  closestBoundaryPoint, boundingBox, fitScale
} from "../lib/geometry.js";
import { neighbourhood } from "../lib/neighbourhood.js";
import { num } from "../lib/format.js";

let laufendeNummer = 0;

export default {
  name: "SitePlan",
  props: {
    plot: { type: Object, required: true },
    koerper: { type: Object, required: true },   // {width, depth, cx, cy, rotation}
    breite: { type: Number, default: 820 },
    hoehe: { type: Number, default: 620 },
    interaktiv: { type: Boolean, default: false },
    kompakt: { type: Boolean, default: false },
    grund: { type: String, default: "karte" },
    genordet: { type: Boolean, default: false },
    nachbarn: { type: Boolean, default: true },
    masse: { type: Boolean, default: true },
    saum: { type: Boolean, default: true },
    /** Fixed pixels per metre. Without it each plan fits its own frame. */
    massstab: { type: Number, default: null }
  },
  emits: ["verschieben"],
  data() {
    return { uid: ++laufendeNummer, ziehen: null };
  },
  computed: {
    beschriftung() {
      return `Lageplan ${this.plot.name}: Flurstück, farbig markierte Abstandsfläche und Baukörper`;
    },
    /** Dimension chains are noise at thumbnail size. */
    zeigeMasse() { return this.masse && !this.kompakt; },
    drehung() { return this.genordet ? this.plot.nordVersatz : 0; },
    nordWinkel() { return -this.plot.nordVersatz + this.drehung; },
    grundfarbe() { return this.grund === "luftbild" ? "var(--w2b-karte-gruen)" : "var(--w2b-karte-grund)"; },
    umfeld() { return neighbourhood(this.plot.polygon, this.plot.flaecheAmtlich || 1, 0); },

    /* Frame the plot with a margin, then stretch the box to the frame's aspect
       so the drawing fills the panel instead of floating in it. */
    sicht() {
      const box = boundingBox(this.plot.polygon);
      const rand = this.kompakt ? 6 : 40;
      const luft = 0.16;
      let bw = box.width * (1 + luft * 2);
      let bh = box.height * (1 + luft * 2);
      const seiten = (this.breite - rand * 2) / (this.hoehe - rand * 2);
      if (bw / bh < seiten) bw = bh * seiten; else bh = bw / seiten;
      const scale = (this.breite - rand * 2) / bw;
      return { scale, mx: (box.minX + box.maxX) / 2, my: (box.minY + box.maxY) / 2 };
    },
    zehnMeter() { return 10 * this.sicht.scale; },
    fenster() { return buildableArea(this.plot.polygon, this.plot.tiefen); },
    saumRing() {
      const aussen = this.plot.polygon.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      const innen = this.fenster.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      return `M${aussen}Z M${innen}Z`;
    },
    hausEcken() { return rectangleCorners(this.koerper); },
    ausreisser() {
      if (!this.fenster.length) return this.hausEcken;
      return this.hausEcken.filter(e => !pointInPolygon(e, this.fenster));
    },
    verstoss() { return this.ausreisser.length > 0; },
    strassenkante() {
      const [a, b] = [this.umfeld.street[0], this.umfeld.street[1]];
      return { x1: this.p(a).x, y1: this.p(a).y, x2: this.p(b).x, y2: this.p(b).y };
    },
    raster() {
      const linien = [];
      for (let m = -160; m <= 220; m += 10) {
        linien.push({ k: `x${m}`, x1: this.px(m), y1: -400, x2: this.px(m), y2: this.hoehe + 400 });
        linien.push({ k: `y${m}`, x1: -400, y1: this.py(m), x2: this.breite + 400, y2: this.py(m) });
      }
      return linien;
    },
    gruenflaechen() {
      const w = this.breite, h = this.hoehe;
      return [[w * .18, h * .22, w * .11, h * .1], [w * .74, h * .3, w * .09, h * .08],
              [w * .3, h * .78, w * .13, h * .07], [w * .82, h * .7, w * .08, h * .11],
              [w * .12, h * .58, w * .07, h * .07]];
    },
    ketten() {
      const kanten = polygonEdges(this.plot.polygon);
      const h = this.hausEcken;
      const liste = [
        { a: this.plot.polygon[1], b: this.plot.polygon[0], off: 4.5, wert: kanten[0].length },
        { a: this.plot.polygon[0], b: this.plot.polygon[this.plot.polygon.length - 1], off: 4.5,
          wert: kanten[kanten.length - 1].length },
        { a: h[0], b: h[1], off: -3.1, wert: this.koerper.width },
        { a: h[1], b: h[2], off: -3.1, wert: this.koerper.depth }
      ];
      return liste.map(k => this.kette(k.a, k.b, k.off, `${num(k.wert)} m`));
    },
    engstelle() {
      if (!this.plot.polygon.length) return null;
      let best = { distance: Infinity };
      for (const ecke of this.hausEcken) {
        const nah = closestBoundaryPoint(ecke, this.plot.polygon);
        if (nah.distance < best.distance) best = { ...nah, von: ecke };
      }
      if (!best.point) return null;
      const a = this.p(best.von), b = this.p(best.point);
      const mindest = Math.min(...this.plot.tiefen);
      return {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        tx: (a.x + b.x) / 2, ty: (a.y + b.y) / 2 - 7,
        eng: best.distance < mindest - 0.01,
        label: `${num(best.distance)} m`
      };
    }
  },
  methods: {
    px(x) { return this.breite / 2 + (x - this.sicht.mx) * this.sicht.scale; },
    py(y) { return this.hoehe / 2 - (y - this.sicht.my) * this.sicht.scale; },
    p(v) {
      const point = Array.isArray(v) ? { x: v[0], y: v[1] } : v;
      return { x: this.px(point.x), y: this.py(point.y) };
    },
    pfad(ring) { return ring.map(v => { const q = this.p(v); return `${q.x.toFixed(1)},${q.y.toFixed(1)}`; }).join(" "); },
    ecken(rect) { return rectangleCorners(rect); },
    /** One dimension chain: two witness lines, the measure line, and a label. */
    kette(a, b, versatz, label) {
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      const n = { x: -dy / len, y: dx / len };
      const a2 = { x: a.x + n.x * versatz, y: a.y + n.y * versatz };
      const b2 = { x: b.x + n.x * versatz, y: b.y + n.y * versatz };
      const mitte = { x: (a2.x + b2.x) / 2 + n.x * 1.6, y: (a2.y + b2.y) / 2 + n.y * 1.6 };
      const A = this.p(a), B = this.p(b), A2 = this.p(a2), B2 = this.p(b2), M = this.p(mitte);
      return {
        h1: { x1: A.x, y1: A.y, x2: A2.x, y2: A2.y },
        h2: { x1: B.x, y1: B.y, x2: B2.x, y2: B2.y },
        linie: { x1: A2.x, y1: A2.y, x2: B2.x, y2: B2.y },
        text: { x: M.x, y: M.y + 3.5 },
        label
      };
    },
    /** Screen pixels back to metres, undoing the map rotation. */
    inMeter(event) {
      const rect = this.$refs.flaeche.getBoundingClientRect();
      const k = this.breite / rect.width;
      const px = (event.clientX - rect.left) * k;
      const py = (event.clientY - rect.top) * k;
      const r = (this.drehung * Math.PI) / 180;
      const dx = px - this.breite / 2, dy = py - this.hoehe / 2;
      const ux = dx * Math.cos(-r) - dy * Math.sin(-r);
      const uy = dx * Math.sin(-r) + dy * Math.cos(-r);
      return { x: this.sicht.mx + ux / this.sicht.scale, y: this.sicht.my - uy / this.sicht.scale };
    },
    griffFassen(event) {
      if (!this.interaktiv || !event.target.closest("[data-haus]")) return;
      const point = this.inMeter(event);
      this.ziehen = { dx: this.koerper.cx - point.x, dy: this.koerper.cy - point.y };
      this.$refs.flaeche.setPointerCapture(event.pointerId);
      event.preventDefault();
    },
    griffZiehen(event) {
      if (!this.ziehen) return;
      const point = this.inMeter(event);
      this.$emit("verschieben", { cx: point.x + this.ziehen.dx, cy: point.y + this.ziehen.dy });
    },
    griffLoslassen() { this.ziehen = null; },
    tastatur(event) {
      if (!this.interaktiv || !event.target.closest("[data-haus]")) return;
      const schritt = event.shiftKey ? 1 : 0.25;
      const richtung = {
        ArrowLeft: [-schritt, 0], ArrowRight: [schritt, 0],
        ArrowUp: [0, schritt], ArrowDown: [0, -schritt]
      }[event.key];
      if (!richtung) return;
      event.preventDefault();
      this.$emit("verschieben", { cx: this.koerper.cx + richtung[0], cy: this.koerper.cy + richtung[1] });
    }
  }
};
</script>

<style scoped>
.lageplan{ display: block; width: 100%; height: auto; touch-action: none; }
.lageplan--zieht{ cursor: grabbing; }
.plan-griff{ cursor: grab; }
.lageplan__mass{
  font-family: var(--w2b-daten); font-size: 10.5px; font-weight: 500;
  fill: var(--w2b-karte-grenze); text-anchor: middle;
  paint-order: stroke fill; stroke: var(--w2b-karte-halo); stroke-width: 3.4px; stroke-linejoin: round;
}
.lageplan__nord{
  font-family: var(--w2b-anzeige); font-size: 14px; font-weight: 600;
  fill: var(--w2b-karte-grenze); text-anchor: middle;
  paint-order: stroke fill; stroke: var(--w2b-karte-halo); stroke-width: 3px;
}
.lageplan__leiste{
  font-family: var(--w2b-daten); font-size: 9.5px; fill: var(--w2b-karte-grenze);
  paint-order: stroke fill; stroke: var(--w2b-karte-halo); stroke-width: 3px;
}
</style>
