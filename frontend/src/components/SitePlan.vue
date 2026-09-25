<template>
  <div class="site-plan-shell">
    <div v-if="hasBackdrop" ref="mapContainer" class="site-plan__map" aria-hidden="true"
         :data-map-ready="String(mapReady)"></div>
    <svg
    ref="svg"
    class="site-plan"
    :class="{
      'site-plan--dragging': dragging,
      'site-plan--measuring': measuring,
      'site-plan--navigable': navigable && !measuring,
      'site-plan--cooperative': cooperative,
      'site-plan--panning': panning
    }"
    :viewBox="`0 0 ${width} ${height}`"
    :aria-busy="groundSettled ? null : 'true'"
    role="img"
    :aria-label="ariaLabel"
    @pointerdown="pointerDown"
    @pointermove="pointerMove"
    @pointerup="pointerUp"
    @pointercancel="pointerUp"
    @wheel="onWheel"
    @dblclick="onDoubleClick"
    @keydown="onKeydown"
  >
    <defs>
      <marker :id="`dim-${uid}`" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto">
        <line x1="5" y1="1.5" x2="5" y2="8.5" stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
      </marker>
      <!-- A hatch, not a fill: the statutory setback strip is the only thing on
           this drawing that gets a solid colour, and this is a hint. -->
      <pattern :id="`hint-${uid}`" width="7" height="7" patternUnits="userSpaceOnUse"
               patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="7" stroke="var(--w2b-map-neighbour)" stroke-width="1.1" />
      </pattern>
    </defs>

    <!-- What stands while a tile ground is on its way: a placeholder with the
         same pulse as every other one in the app, so the wait reads as alive
         rather than as an empty frame. -->
    <rect v-if="!hasBackdrop" x="0" y="0" :width="width" :height="height"
          :fill="groundSettled ? backgroundFill : 'var(--w2b-line-faint)'"
          :class="{ 'site-plan__placeholder': !groundSettled }" />

    <!-- With a tile ground the whole drawing waits for it and then appears in
         one go: an outline first and its surroundings a moment later reads as
         something breaking. The paper is drawn again inside, because a group
         fading in is isolated from what lies under it, and the ground's
         multiply would have nothing to multiply into. -->
    <g class="site-plan__content" :class="{ 'is-waiting': !groundSettled }"
       :data-ground="groundSettled ? 'ready' : 'loading'">
    <rect v-if="!hasBackdrop && groundImage" x="0" y="0" :width="width" :height="height" :fill="backgroundFill" />

    <g :transform="`rotate(${rotation}, ${width / 2}, ${height / 2})`">
      <!-- One composed image. A failed one is dropped, the drawing appears on
           the flat ground, and no broken-image icon is left behind. -->
      <g v-if="groundImage" class="site-plan__tile-ground"
         :class="{ 'site-plan__tile-ground--dark': darkBackdrop }" aria-hidden="true">
        <image :key="groundImage.href" :href="groundImage.href"
               :x="groundImage.x" :y="groundImage.y"
               :width="groundImage.width" :height="groundImage.height"
               preserveAspectRatio="none"
               @load="groundLoaded = groundImage.href" @error="groundFailed = groundImage.href" />
      </g>

      <polygon :points="path(plot.polygon)" fill="var(--w2b-map-surface)"
               :fill-opacity="hasBackdrop ? 0.42 : 1" />

      <!-- The setback strip is what gets colour: marked is what may NOT be built on. -->
      <template v-if="showSetbacks && envelope.length">
        <path :d="setbackRing" fill-rule="evenodd" fill="var(--w2b-map-setback)" />
        <!-- Where the neighbouring building's own minimum setback would reach
             onto this plot. A hint, never a finding — see
             docs/research/abstandsflaechen-nachbargebaeude.md. -->
        <path v-if="neighbourRing" :d="neighbourRing" fill-rule="evenodd"
              :fill="`url(#hint-${uid})`" opacity=".75" />
        <polygon v-if="neighbourEnvelope.length" :points="path(neighbourEnvelope)" fill="none"
                 stroke="var(--w2b-map-neighbour)" stroke-width="1.1" stroke-dasharray="2 3" />
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
      <g v-if="houseVisible" :class="{ 'plan-handle': interactive }" :tabindex="interactive ? 0 : null"
         :role="interactive ? 'button' : null"
         :aria-label="interactive ? 'Baukörper: anklicken zum Bearbeiten, ziehen oder mit den Pfeiltasten verschieben' : null"
         :aria-pressed="interactive ? String(houseSelected) : null"
         data-house>
        <!-- Selected: the panel beside the plan is editing this footprint. A
             frame a few pixels outside it, so the violation stroke stays readable. -->
        <g v-if="houseSelected" class="site-plan__selection">
          <polygon :points="selectionFrame.map(q => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(' ')"
                   fill="none" stroke="var(--w2b-map-selection)" stroke-width="1.5" stroke-dasharray="5 4" />
          <circle v-for="(q, i) in selectionFrame" :key="`s${i}`" :cx="q.x" :cy="q.y" r="4"
                  fill="var(--w2b-map-halo)" stroke="var(--w2b-map-selection)" stroke-width="1.5" />
        </g>
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
          <!-- A segment too short to carry its own text keeps its label on a leader. -->
          <line v-if="c.leader" :x1="c.leader.x1" :y1="c.leader.y1" :x2="c.leader.x2" :y2="c.leader.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".7" opacity=".5" />
          <text :x="c.text.x" :y="c.text.y" :transform="`rotate(${-rotation}, ${c.text.x}, ${c.text.y})`"
                class="site-plan__dimension">{{ c.label }}</text>
        </g>

        <!-- Overall size on a ring of its own, outside every per-edge chain. -->
        <g v-for="(c, i) in overallChains" :key="`o${i}`" class="site-plan__overall">
          <line :x1="c.h1.x1" :y1="c.h1.y1" :x2="c.h1.x2" :y2="c.h1.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".7" opacity=".3" stroke-dasharray="3 4" />
          <line :x1="c.h2.x1" :y1="c.h2.y1" :x2="c.h2.x2" :y2="c.h2.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".7" opacity=".3" stroke-dasharray="3 4" />
          <line :x1="c.line.x1" :y1="c.line.y1" :x2="c.line.x2" :y2="c.line.y2"
                stroke="var(--w2b-map-boundary)" stroke-width=".9" opacity=".55" stroke-dasharray="7 4"
                :marker-start="`url(#dim-${uid})`" :marker-end="`url(#dim-${uid})`" />
          <text :x="c.text.x" :y="c.text.y" :transform="`rotate(${-rotation}, ${c.text.x}, ${c.text.y})`"
                class="site-plan__dimension site-plan__dimension--overall">{{ c.label }}</text>
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

      <!-- The parcels to choose between, above the drawing rather than under
           it: a chosen parcel is drawn with no fill, and the plot's own fill
           sat on top of it — so the click that should have taken it back out
           of the plot never reached it. Nothing changes visually; the chosen
           ones are transparent and the others do not overlap the plot. -->
      <g v-if="choosableParcels.length" class="site-plan__choices">
        <polygon v-for="parcel in choosableParcels" :key="parcel.key"
                 class="site-plan__choice"
                 :class="{ 'is-chosen': parcel.chosen, 'is-problem': parcel.problem }"
                 :points="path(parcel.ring)" :data-number="parcel.number"
                 tabindex="0" role="button"
                 :aria-label="`Flurstück ${parcel.number}, ${parcel.area}`"
                 :aria-pressed="String(parcel.chosen)"
                 @keydown.enter.prevent="$emit('choose', parcel.id)"
                 @keydown.space.prevent="$emit('choose', parcel.id)" />
      </g>
      <!-- The numbers last, so nothing draws over them. Counter-rotated: a
           parcel number read sideways is not a label. -->
      <g v-if="choosableParcels.length" class="site-plan__choice-labels">
        <text v-for="parcel in labelledParcels" :key="`n${parcel.key}`"
              :x="parcel.at.x" :y="parcel.at.y"
              :transform="`rotate(${-rotation}, ${parcel.at.x}, ${parcel.at.y})`"
              class="site-plan__choice-label" :class="{ 'is-chosen': parcel.chosen }"
              text-anchor="middle">{{ parcel.number }}</text>
      </g>
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
        <rect x="0" y="-5" :width="scaleBar.width" height="5" fill="var(--w2b-map-boundary)" />
        <rect :x="scaleBar.width" y="-5" :width="scaleBar.width" height="5" fill="none"
              stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
        <line x1="0" y1="0" :x2="scaleBar.width * 2" y2="0" stroke="var(--w2b-map-boundary)" stroke-width="1.2" />
        <text x="0" y="15" class="site-plan__scale-bar" text-anchor="middle">0</text>
        <text :x="scaleBar.width" y="15" class="site-plan__scale-bar" text-anchor="middle">{{ scaleBar.label }}</text>
        <text :x="scaleBar.width * 2" y="15" class="site-plan__scale-bar" text-anchor="end">{{ scaleBar.endLabel }}</text>
      </g>
    </g>
    </svg>
  </div>
</template>

<script>
import {
  buildableArea, polygonEdges, rectangleCorners, pointInPolygon,
  closestBoundaryPoint, streetDownRotation, turnedBox, asCounterClockwise,
  minimumRotatedRectangleCorners, constrainToEnvelope, hasNeighbourHint,
  polygonCentroid
} from "../lib/geometry.js";
import { cameraFor, toLocal, toWgs84 } from "../lib/projection.js";
import { groundBlock } from "../lib/tileGround.js";
import { outerRing } from "../lib/plots.js";
import { num, area } from "../lib/format.js";
import { BACKDROPS, canRenderMap, withOverlay } from "../lib/basemap.js";
import { darkTheme } from "../lib/store.js";
// MapLibre 6 ships named exports only — there is no default.
// Its worker URL is set once in main.js; see the note there.
import { Map as MapLibreMap } from "maplibre-gl";

let instanceCount = 0;

/* How far outside the outline each ring of dimensions sits, in pixels of the
 * drawing rather than in metres: 4,5 m is a hair's breadth on a 1583 m field
 * and half the picture on a 12 m plot, so a fixed metre offset can only look
 * right at one size. Metres come from dividing by the scale. */
const EDGE_CHAIN_PX = 18;
const HOUSE_CHAIN_PX = 15;
/* Two rings for the labels of segments too short to carry their own, so that
 * neighbouring slivers do not write over each other. */
const SHORT_LABEL_PX = [36, 54];
/* How far the overall chain clears whatever ring ended up outermost. */
const OVERALL_CLEARANCE_PX = 22;
/* What the outermost text still needs beyond its chain. */
const CHAIN_TEXT_PX = 14;
/* Roughly the width of one character at the 10,5 px label size. */
const LABEL_CHARACTER_PX = 6.2;
/* Above this many segments a chain per boundary stops being information: the
 * field a district address resolves to has 159 of them, and one label each
 * turns the plan into a black band with nothing legible in it. The overall
 * size still stands — that is the number being asked for — and every segment
 * length is listed in the setback table on the plot page. */
const MAX_LABELLED_EDGES = 16;
/* Round distances a scale bar may step in, and the width one half aims for. */
const SCALE_BAR_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000];
const SCALE_BAR_SEGMENT_PX = 56;

/** How far a pointer may travel between press and release and still count as
 *  a click rather than a pan. */
const CLICK_SLOP_PX = 4;

/** Metres of neighbouring ground the parcel picker keeps in frame. About one
 *  plot's width in a terraced street, which is what makes the neighbour either
 *  side visible and clickable. */
const CHOICE_BAND_M = 18;

/* Roughly what a parcel number occupies at the label's own size — 11px in the
   mono face — and the line it sits on. Enough to tell whether two of them would
   touch; not a text metric. */
const LABEL_CHAR_WIDTH = 6.6;
const LABEL_LINE_HEIGHT = 13;

/** A bounding box with a band of metres added on every side. */
const grow = (box, band) => ({
  minX: box.minX - band, maxX: box.maxX + band,
  minY: box.minY - band, maxY: box.maxY + band,
  width: box.width + 2 * band, height: box.height + 2 * band
});

/** How far the navigable view may depart from the fitted framing. */
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 8;

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));


export default {
  name: "SitePlan",
  props: {
    plot: { type: Object, required: true },
    /** {width, depth, cx, cy, rotation}. Absent where no house is planned yet. */
    building: { type: Object, default: null },
    width: { type: Number, default: 820 },
    height: { type: Number, default: 620 },
    interactive: { type: Boolean, default: false },
    /** Hold the dragged footprint inside the buildable envelope. Lifted where
     *  there is no envelope to hold it in — see `constrainToEnvelope`. */
    confineToEnvelope: { type: Boolean, default: true },
    compact: { type: Boolean, default: false },
    // "none" by default: a backdrop is a MapLibre instance, and the small
    // plans on cards and in the comparison must not each start one.
    backdrop: { type: String, default: "none" },
    /** A raster layer laid over the backdrop — today the noise survey. Needs a
     *  backdrop under it: the bands are translucent and mean nothing on paper. */
    overlay: { type: String, default: null },
    /** A proxied raster layer drawn as plain <image> tiles under the plot —
     *  the ground a thumbnail gets instead of a MapLibre backdrop. Several
     *  cards on one page would each start a WebGL context otherwise, and
     *  contexts past the browser's limit go blank without a word. */
    tileGround: { type: String, default: null },
    /** Relative breathing room around the outline, overriding the default.
     *  A thumbnail that shows its neighbours needs more than one that
     *  shows the plot alone. */
    padding: { type: Number, default: null },
    /** Keep the camera where it is when the plot changes. Picking another
     *  parcel is a change the user has to *see*: a drawing that re-centres on
     *  the new outline looks the same before and after, and the neighbours
     *  they were comparing are suddenly somewhere else. */
    holdFrame: { type: Boolean, default: false },
    /** Parcels the user may pick from, as `/api/parcels/nearby` returns them.
     *  Given, the drawing frames all of them, draws each with its number and
     *  emits `choose` with the parcel key that was clicked. */
    parcels: { type: Array, default: null },
    /** Which of `parcels` the plot is made of, by `kennzeichen`. A plot is a
     *  set of parcels, so this is a set — the drawing marks every one of them
     *  as taken and leaves the rest on offer. */
    chosenParcels: { type: Array, default: () => [] },
    /** Chosen parcels that are part of a problem — today: they hang off the
     *  rest of the plot. Marked rather than refused, so the user can click
     *  their way back to a shape that holds together. */
    problemParcels: { type: Array, default: () => [] },
    northUp: { type: Boolean, default: false },
    showDimensions: { type: Boolean, default: true },
    showSetbacks: { type: Boolean, default: true },
    /** The cadastral check draws the parcel alone: no house is planned there yet. */
    showBuilding: { type: Boolean, default: true },
    /** Let the pointer pan and the wheel zoom the framing, backdrop included. */
    navigable: { type: Boolean, default: false },
    /** The plan sits in the middle of a long page, and the page has to keep
     *  scrolling across it: the wheel zooms only with Ctrl or ⌘ held (a
     *  trackpad pinch arrives as exactly that), and a vertical swipe scrolls
     *  the page instead of panning. */
    cooperative: { type: Boolean, default: false },
    /** Per-segment depths a neighbouring building's own minimum would ask for.
     *  Absent, or equal to the statutory ones, and nothing extra is drawn. */
    neighbourDepths: { type: Array, default: null },
    /** Fixed pixels per metre. Without it each plan fits its own frame. */
    scale: { type: Number, default: null },
    /** Measuring mode: clicks add points, the run is measured segment by segment. */
    measuring: { type: Boolean, default: false },
    /** Draws the footprint as the thing being edited. */
    houseSelected: { type: Boolean, default: false }
  },
  /* `select` carries "house" for a click on the footprint and null for a click
     anywhere else on the plan. A click, not a press: a drag moves the house
     and must not also open or close anything. */
  emits: ["move", "measured", "choose", "select"],
  data() {
    return {
      uid: ++instanceCount, dragging: null, mapUnavailable: false, heldFrame: null,
      /* Whether every tile of the current view has arrived. Only anything that
       * photographs the plan reads it — a picture taken before this is a
       * picture of a half-drawn backdrop. Kept apart from `mapUnavailable`,
       * which is the failure flag and must never drive a rebuild. */
      mapReady: false,
      measurePoints: [], measurePointer: null,
      // Navigation, relative to the fitted framing: a factor on its scale and
      // an offset of its centre, in metres. Both feed `view`, so the backdrop
      // follows through the camera watcher instead of drifting behind a
      // CSS transform on the drawing.
      zoomFactor: 1,
      panMetres: { x: 0, y: 0 },
      panning: null,
      // The ground image by its href: the one that has arrived, and the one
      // that could not. Keyed by href so a changed frame starts hidden again.
      groundLoaded: null, groundFailed: null
    };
  },
  computed: {
    /** One gate for everything the house draws: a plan without a building, and
     *  a plan that deliberately hides it, are the same case downstream. */
    houseVisible() { return this.showBuilding && Boolean(this.building); },
    ariaLabel() {
      const what = this.houseVisible
        ? "Flurstück, farbig markierte Abstandsfläche und Baukörper"
        : "Flurstück und farbig markierte Abstandsfläche";
      return `Lageplan ${this.plot.name}: ${what}`;
    },
    /** Dimension chains are noise at thumbnail size. */
    dimensionsVisible() { return this.showDimensions && !this.compact; },
    /* Real outlines arrive already oriented: local +y is north. "Genordet"
       therefore means no rotation, and "straßenparallel" turns the drawing so
       the street front runs left to right along the bottom — the way one
       stands on the pavement looking at the plot. */
    rotation() {
      if (this.northUp) return 0;
      return streetDownRotation(this.plot.polygon, this.plot.streetEdge ?? 0);
    },
    northAngle() { return this.rotation; },
    /** Whether a backdrop is *wanted*: one that is not "none", and an anchor
     *  to align it to. Kept apart from whether one is actually on screen: the
     *  rebuild watcher hangs off this, and folding the failure flag in made the
     *  component fight itself — a failed build set the flag, the flag changed
     *  this, the watcher rebuilt, the rebuild cleared the flag, and the style
     *  was fetched again, forever. */
    wantsBackdrop() { return this.backdrop !== "none" && Boolean(this.plot.anchor); },
    hasBackdrop() { return this.wantsBackdrop && !this.mapUnavailable; },
    /** The raster ground under the drawing as one image, placed in the
     *  rotated group so it turns with it. See lib/tileGround.js. */
    groundImage() {
      if (!this.tileGround || this.hasBackdrop || !this.plot.anchor) return null;
      const block = groundBlock(this.plot.anchor, this.view, this.width, this.height, this.tileGround);
      return block && block.href !== this.groundFailed ? block : null;
    },
    /** Whether the drawing may show: no tile ground to wait for, or it has
     *  arrived. A failed one drops out of `groundImage`, which settles it too. */
    groundSettled() { return !this.groundImage || this.groundLoaded === this.groundImage.href; },
    backgroundFill() { return this.backdrop === "aerial" ? "var(--w2b-map-green)" : "var(--w2b-map-ground)"; },
    /** Which palette the vector backdrop should be drawn in. Deliberately not
     *  a function of whether the last build succeeded — see `rebuildMap`. */
    darkBackdrop() { return darkTheme(); },

    /** The parcels on offer, in this plot's own metre frame. Empty unless a
     *  caller handed some over, so every other use of this component is
     *  untouched. */
    choosableParcels() {
      if (!this.parcels?.length || !this.plot.anchor) return [];
      return this.parcels.flatMap(feature => {
        const ring = outerRing(feature.geometry);
        if (ring.length < 4) return [];
        const local = toLocal(ring, this.plot.anchor);
        const properties = feature.properties ?? {};
        const centre = polygonCentroid(local);
        return [{
          key: properties.kennzeichen ?? `${properties.zaehler}/${properties.nenner ?? ""}`,
          id: properties.kennzeichen,
          number: properties.nenner ? `${properties.zaehler}/${properties.nenner}` : `${properties.zaehler}`,
          area: area(properties.flaeche_amtlich_m2),
          size: Number(properties.flaeche_amtlich_m2) || 0,
          chosen: this.chosenParcels.includes(properties.kennzeichen),
          problem: this.problemParcels.includes(properties.kennzeichen),
          ring: local,
          at: this.p(centre)
        }];
      });
    },

    /** Whether the ground under the drawing already names the parcels. */
    groundNamesParcels() {
      return this.hasBackdrop
        && (this.backdrop === "cadastre" || this.overlay === "liegenschaftskarte");
    },

    /** Those whose number lands inside the drawing and clear of one already
     *  placed. A label over empty paper names a parcel the user cannot see, let
     *  alone click — and two of them in the same spot read as a third number:
     *  "292/2" over "293/5" came out as "29293/5". The chosen parcel keeps its
     *  number, then the larger ones, so what gets dropped is the sliver at the
     *  edge of the frame rather than the plot in the middle of it. */
    labelledParcels() {
      // The Liegenschaftskarte writes every parcel number itself, in the
      // register's own stacked notation. Repeating them upright next to it gave
      // "96/1" twice per parcel, which reads as a fault rather than a label.
      if (this.groundNamesParcels) return [];
      const inset = 14;
      const inside = this.choosableParcels.filter(parcel =>
        parcel.at.x > inset && parcel.at.x < this.width - inset
        && parcel.at.y > inset && parcel.at.y < this.height - inset);
      const order = [...inside].sort((a, b) =>
        Number(b.chosen) - Number(a.chosen) || b.size - a.size);

      const placed = [];
      for (const parcel of order) {
        const half = LABEL_CHAR_WIDTH * parcel.number.length / 2 + 2;
        const clash = placed.some(other =>
          Math.abs(other.at.x - parcel.at.x) < other.half + half
          && Math.abs(other.at.y - parcel.at.y) < LABEL_LINE_HEIGHT);
        if (!clash) placed.push({ ...parcel, half });
      }
      return placed;
    },

    /** The outline in counter-clockwise order, so "outward" is one fixed sign.
     *  A cadastral ring arrives either way round, and the old chains offset by
     *  a normal whose direction depended on that — which is why one of them
     *  sat inside the parcel. */
    ccwPolygon() { return asCounterClockwise(this.plot.polygon); },

    baseMargin() { return this.compact ? 6 : 40; },

    /* Trial fit, read only to decide which segments have room for their own
       label — and therefore how much frame the outer rings need. It never reads
       that reserve back, so the two do not chase each other: reserving in
       metres did, and shrank a 35 m plot to a third of its frame. */
    trialScale() { return this.fitBox(turnedBox(this.plot.polygon, this.rotation), this.baseMargin); },

    /** Whether a chain per boundary segment can still be read on this outline. */
    edgesLabelled() { return this.ccwPolygon.length <= MAX_LABELLED_EDGES; },

    /** Indices of the segments with no room to carry their own text. */
    crowdedEdges() {
      const found = [];
      if (!this.edgesLabelled) return found;
      polygonEdges(this.ccwPolygon).forEach((edge, i) => {
        const label = `${num(edge.length)} m`;
        if (edge.length * this.trialScale < label.length * LABEL_CHARACTER_PX) found.push(i);
      });
      return found;
    },

    /* The outermost ring in play. A parcel whose sides all carry their own
       labels pays nothing for the leader rings it does not use. */
    overallOffsetPx() {
      const rings = Math.min(this.crowdedEdges.length, SHORT_LABEL_PX.length);
      return (rings ? SHORT_LABEL_PX[rings - 1] : EDGE_CHAIN_PX) + OVERALL_CLEARANCE_PX;
    },

    /* The chains hang a fixed number of *pixels* outside the outline, so the
       room they need is a pixel margin — not metres. */
    margin() {
      return this.dimensionsVisible
        ? this.baseMargin + this.overallOffsetPx + CHAIN_TEXT_PX
        : this.baseMargin;
    },

    /** Metres per pixel of the drawing — the chain offsets' unit of exchange. */
    metresPerPixel() { return 1 / this.view.scale; },

    /* Frame the plot with a margin, then stretch the box to the frame's aspect
       so the drawing fills the panel instead of floating in it. */
    fit() {
      /* A frame held across a change of plot. It is kept in WGS84, because the
         local metres are measured from the plot's own anchor and the new plot
         has a different one — the same numbers would be a different place. */
      if (this.heldFrame && this.plot.anchor) {
        const [centre] = toLocal([this.heldFrame.centre], this.plot.anchor);
        return { scale: this.heldFrame.scale, mx: centre.x, my: centre.y };
      }
      /* With a choice on the table the frame grows by a fixed band of metres so
         the parcels either side are in it and big enough to hit. Framing *all*
         of them instead put 33 parcels across 200 m: the neighbours became
         specks, and their numbers floated in empty paper. A band, not a factor,
         because the width that matters is a neighbour's, not this plot's. */
      /* The box is the one the plot has on screen, turned to its street: the
         drawing rotates about the frame's centre, so that box's centre is the
         point the frame centres on and its size is what has to fit. */
      const turned = turnedBox(this.plot.polygon, this.rotation);
      const box = this.parcels?.length ? grow(turned, CHOICE_BAND_M) : turned;
      /* A caller that hands us a scale is drawing several plots side by side
         and needs them comparable, so its value wins over our own fit. It is
         the smallest of the individual fits, so nothing overflows its frame. */
      const scale = Number.isFinite(this.scale) && this.scale > 0 ? this.scale : this.fitBox(box, this.margin);
      return { scale, mx: turned.centre.x, my: turned.centre.y };
    },
    /** The fit as the user has moved it. Everything projects through this —
     *  `px`/`py` for the drawing and `setCamera` for the ground — so the two
     *  cannot come apart. Untouched, it is the fit itself. */
    view() {
      return {
        scale: this.fit.scale * this.zoomFactor,
        mx: this.fit.mx + this.panMetres.x,
        my: this.fit.my + this.panMetres.y
      };
    },
    /* A bar of a fixed ten metres writes its three labels on top of each other
       the moment the drawing covers a kilometre — and zooming does exactly
       that. The step follows the scale, so each half stays about as wide on
       screen whatever the plot measures and however far it is zoomed. */
    scaleBar() {
      const step = SCALE_BAR_STEPS.find(m => m * this.view.scale >= SCALE_BAR_SEGMENT_PX)
        ?? SCALE_BAR_STEPS[SCALE_BAR_STEPS.length - 1];
      return { width: step * this.view.scale, label: num(step, 0), endLabel: `${num(step * 2, 0)} m` };
    },
    envelope() { return buildableArea(this.plot.polygon, this.plot.setbacks); },
    /** The envelope as it would be if the neighbours' minimum setbacks counted
     *  against this plot. Empty unless it is actually deeper than our own. */
    neighbourEnvelope() {
      if (!this.neighbourDepths || !this.envelope.length) return [];
      if (!hasNeighbourHint(this.plot.setbacks, this.neighbourDepths)) return [];
      return buildableArea(this.plot.polygon, this.neighbourDepths);
    },
    neighbourRing() {
      if (!this.neighbourEnvelope.length) return null;
      const outer = this.envelope.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      const inner = this.neighbourEnvelope.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      return `M${outer}Z M${inner}Z`;
    },
    setbackRing() {
      const outer = this.plot.polygon.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      const inner = this.envelope.map(v => `${this.p(v).x},${this.p(v).y}`).join("L");
      return `M${outer}Z M${inner}Z`;
    },
    houseCorners() { return this.houseVisible ? rectangleCorners(this.building) : []; },
    /** The footprint's corners in screen units, pushed 7 px outward along the
     *  diagonals. */
    selectionFrame() {
      const corners = this.houseCorners.map(c => this.p(c));
      if (!corners.length) return [];
      const cx = corners.reduce((sum, q) => sum + q.x, 0) / corners.length;
      const cy = corners.reduce((sum, q) => sum + q.y, 0) / corners.length;
      return corners.map(q => {
        const len = Math.hypot(q.x - cx, q.y - cy) || 1;
        return { x: q.x + (q.x - cx) / len * 7, y: q.y + (q.y - cy) / len * 7 };
      });
    },
    outliers() {
      if (!this.envelope.length) return this.houseCorners;
      return this.houseCorners.filter(e => !pointInPolygon(e, this.envelope));
    },
    violation() { return this.outliers.length > 0; },
    /* One chain per boundary segment, not the two the old list picked out: on
       a five-point parcel that left three sides unlabelled and the two it did
       show — a 47,69 m front and a 2,04 m sliver — read as the whole story. */
    dimensionChains() {
      const ring = this.ccwPolygon;
      const perPixel = this.metresPerPixel;
      const chains = [];
      let crowded = 0;

      if (this.edgesLabelled) polygonEdges(ring).forEach((edge, i) => {
        const a = ring[i], b = ring[(i + 1) % ring.length];
        const label = `${num(edge.length)} m`;
        const chain = this.dimensionChain(a, b, -EDGE_CHAIN_PX * perPixel, label);
        // A segment with no room for its own text keeps the label, on a leader
        // further out. Dropping it is what hid the short sides in the first place.
        if (this.crowdedEdges.includes(i)) {
          const ring2 = SHORT_LABEL_PX[crowded++ % SHORT_LABEL_PX.length];
          const far = this.dimensionChain(a, b, -ring2 * perPixel, label);
          chain.text = far.text;
          chain.leader = {
            x1: (chain.line.x1 + chain.line.x2) / 2, y1: (chain.line.y1 + chain.line.y2) / 2,
            x2: far.text.x, y2: far.text.y - 3.5
          };
        }
        chains.push(chain);
      });

      const h = this.houseCorners;
      if (this.houseVisible) {
        const houseOffset = -HOUSE_CHAIN_PX * perPixel;
        chains.push(this.dimensionChain(h[0], h[1], houseOffset, `${num(this.building.width)} m`));
        chains.push(this.dimensionChain(h[1], h[2], houseOffset, `${num(this.building.depth)} m`));
      }
      return chains;
    },

    /* The overall size, on a ring outside all of those. Measured on the minimum
       rotated rectangle rather than the axis-aligned box: the same parcel that
       the box calls 1583 x 198 m is a 1594 x 30 m ribbon, and the elongation is
       exactly what somebody reading a plot wants to see. */
    overallChains() {
      const mrr = minimumRotatedRectangleCorners(this.plot.polygon);
      if (!mrr) return [];
      const c = asCounterClockwise(mrr.corners);
      const offset = -this.overallOffsetPx * this.metresPerPixel;
      const side = (p, q) => Math.hypot(q.x - p.x, q.y - p.y);
      return [[c[0], c[1]], [c[1], c[2]]].map(([p, q]) =>
        this.dimensionChain(p, q, offset, `gesamt ${num(side(p, q), 1)} m`));

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
      if (!this.houseVisible || !this.plot.polygon.length) return null;
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
  mounted() {
    this.buildMap();
    this.watchSize();
    // The first framing is never a change, so the watcher below would not see
    // it — and the first pick would then be the one that moves the map.
    this.rememberFrame();
  },
  beforeUnmount() {
    this._sizeWatcher?.disconnect();
    this._sizeWatcher = null;
    this.destroyMap();
  },
  watch: {
    // A different backdrop means a different style; MapLibre cannot swap sources
    // underneath itself, so the map is torn down and rebuilt.
    wantsBackdrop() { this.rebuildMap(); },
    backdrop() { this.rebuildMap(); },
    // MapLibre cannot add a source to a running style either, so switching the
    // overlay is the same rebuild as switching the ground.
    overlay() { this.rebuildMap(); },
    // Only the vector backdrop has a palette; the aerial photo and the
    // cadastral map are the authority's own raster and look the same either way.
    darkBackdrop() { if (this.backdrop === "map") this.rebuildMap(); },
    measuring(on) { if (!on) this.clearMeasurement(); },
    "plot.id"(_, previous) {
      this.clearMeasurement();
      /* Another parcel from the picker: the ground is the same ground, so
         neither the camera nor the map is touched. `_shownFrame` is what the
         last camera actually showed — this watcher runs before the one that
         records the next one. */
      if (this.holdFrame && previous && this._shownFrame) {
        this.heldFrame = this._shownFrame;
        // The held frame already carries the zoom and pan that produced it.
        this.zoomFactor = 1;
        this.panMetres = { x: 0, y: 0 };
        return;
      }
      this.resetView();
      this.rebuildMap();
    },
    navigable(on) { if (!on) this.resetView(); },
    rotation() { this.setCamera(); },
    view() {
      this.setCamera();
      this.rememberFrame();
    }
  },
  methods: {
    /** MapLibre needs WebGL and a network; neither is guaranteed. Any failure
     *  leaves the drawing alone rather than taking the page down with it. */
    rebuildMap() {
      this.destroyMap();
      this.mapUnavailable = false;
      this.mapReady = false;
      // The container only exists once `hasBackdrop` has re-rendered it.
      this.$nextTick(() => this.buildMap());
    },
    /** The camera is derived from the drawing's rendered width, and that width
     *  is not final at mount: the panel around it is still laying out, and a
     *  measurement of 0 falls back to the unscaled `width`. The backdrop then
     *  sits at the wrong scale under a drawing that is right — the parcel
     *  outline no longer matches the parcel under it, with nothing in the
     *  console. Every later size settles it here. */
    watchSize() {
      if (typeof ResizeObserver === "undefined" || !this.$refs.svg) return;
      this._sizeWatcher = new ResizeObserver(() => this.setCamera());
      this._sizeWatcher.observe(this.$refs.svg);
    },
    async buildMap() {
      if (!this.hasBackdrop || !this.plot.anchor || this._map) return;
      // A raster backdrop needs no network, so without this the map would be
      // constructed wherever there is no WebGL and only fail on the way out,
      // inside the library. The flag is a boolean here, not a message.
      if (!canRenderMap()) {
        this.mapUnavailable = true;
        return;
      }
      const run = ++this._mapRun;
      try {
        const style = withOverlay(
          await BACKDROPS[this.backdrop](), this.overlay, this.backdrop
        );
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
        // "idle" means every tile for this view has arrived and been drawn.
        this._map.on("idle", () => { this.mapReady = true; });
        // A single missing icon or tile is not a broken map. Tearing the
        // backdrop down for one of those is what made it look permanently
        // unavailable; only a style that never loads counts as a failure.
        this._map.on("error", e => console.warn("Karte:", e?.error?.message || e));
        this.setCamera();
      } catch (error) {
        // A missing basemap must not take the drawing down, but staying silent
        // about it would hide a broken build.
        this.mapFailed(error, run);
      }
    },
    destroyMap() {
      const map = this._map;
      this._map = null;
      // A map that never finished starting cannot always be taken apart again:
      // MapLibre's teardown reaches for internals it never got round to
      // creating. Unmounting a component must not fail over that.
      try { map?.remove(); } catch { /* there is nothing left to keep */ }
    },
    /** Where the drawing stands, in a frame that survives a change of anchor:
     *  the local metres are measured from the plot's own anchor, and the next
     *  plot has a different one. */
    rememberFrame() {
      if (!this.plot.anchor) return;
      this._shownFrame = {
        centre: toWgs84([{ x: this.view.mx, y: this.view.my }], this.plot.anchor)[0],
        scale: this.view.scale
      };
    },
    /** No backdrop, and the drawing carries on without one. */
    mapFailed(error, run) {
      // Silence would hide a broken build; a thrown error would take the
      // drawing down with the backdrop, and the drawing is the answer here.
      console.warn("Kartenhintergrund nicht verfügbar:", error);
      if (run !== undefined && run !== this._mapRun) return;
      this.destroyMap();
      this.mapUnavailable = true;
    },
    /** Put the camera exactly where the drawing is, so overlay and ground agree. */
    setCamera() {
      if (!this._map || !this.plot.anchor) return;
      const renderedWidth = this.$refs.svg?.getBoundingClientRect().width || this.width;
      try {
        this._map.jumpTo(cameraFor({
          anchor: this.plot.anchor,
          centreMetres: { x: this.view.mx, y: this.view.my },
          metresPerPixel: 1 / (this.view.scale * (renderedWidth / this.width)),
          rotation: this.rotation
        }));
        this._map.resize();
      } catch (error) {
        // Without WebGL the constructor succeeds and the first frame does not,
        // so this is where a backdrop that cannot run announces itself. Once it
        // has drawn once, a failed camera is not a reason to take it away: this
        // runs on every pan, and the next change sets the camera again.
        if (this.mapReady) { console.warn("Karte:", error?.message || error); return; }
        this.mapFailed(error);
      }
    },
    /** Pixels per metre that fit a box into this frame, given the margin the
     *  chains outside the outline need. */
    fitBox(box, margin) {
      /* The relative padding is breathing room around the outline. Once a ring
         of chains is reserved in the margin, that ring *is* the breathing room,
         and keeping both spends the frame twice. */
      const padding = this.padding ?? (this.dimensionsVisible ? 0.02 : 0.16);
      let bw = box.width * (1 + padding * 2);
      let bh = box.height * (1 + padding * 2);
      const aspect = (this.width - margin * 2) / (this.height - margin * 2);
      if (bw / bh < aspect) bw = bh * aspect; else bh = bw / aspect;
      return (this.width - margin * 2) / bw;
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
    /** Back to the framing the plan fits by itself. */
    resetView() {
      this.zoomFactor = 1;
      this.panMetres = { x: 0, y: 0 };
      this.panning = null;
      // A double click asks for this plot's own framing, held frame or not.
      this.heldFrame = null;
    },
    /* Measuring and moving the house are what the pointer is for wherever they
       are switched on; panning only gets what is left over. */
    pointerDown(event) {
      this._press = null;
      if (this.measuring) { this.measureClick(event); return; }
      /* A press on a parcel on offer. It cannot be a `click` handler: with
         `navigable` the pan below captures the pointer and calls
         preventDefault, and a prevented pointerdown produces no click at all.
         So the press is remembered and the release decides — under a few
         pixels it picked, beyond that it panned. */
      const choice = event.target.closest?.(".site-plan__choice");
      this._pressedChoice = choice
        ? {
            x: event.clientX,
            y: event.clientY,
            parcel: this.choosableParcels.find(p => p.number === choice.dataset.number)
          }
        : null;
      this._press = this.interactive
        ? { x: event.clientX, y: event.clientY, house: Boolean(this.houseVisible && event.target.closest?.("[data-house]")) }
        : null;
      if (this.interactive && this.houseVisible && event.target.closest("[data-house]")) {
        const point = this.toMetres(event);
        this.dragging = { dx: this.building.cx - point.x, dy: this.building.cy - point.y };
        this.$refs.svg.setPointerCapture(event.pointerId);
        event.preventDefault();
        return;
      }
      if (!this.navigable) return;
      // The metre the pointer grabbed. It is held under the cursor for as long
      // as the button is down, so the drawing follows the hand exactly.
      this.panning = this.toMetres(event);
      this.$refs.svg.setPointerCapture(event.pointerId);
      event.preventDefault();
    },
    pointerMove(event) {
      if (this.measuring) { if (this.measurePoints.length) this.measurePointer = this.toMetres(event); return; }
      if (this.panning) {
        const point = this.toMetres(event);
        this.panMetres = {
          x: this.panMetres.x + (this.panning.x - point.x),
          y: this.panMetres.y + (this.panning.y - point.y)
        };
        return;
      }
      if (!this.dragging) return;
      const point = this.toMetres(event);
      this.$emit("move", this.allowedMove({ cx: point.x + this.dragging.dx, cy: point.y + this.dragging.dy }));
    },
    /** Where the house may go. Both ways of moving it — the pointer and the
     *  arrow keys — pass through here, so the constraint cannot hold for one
     *  of them and not the other. Switched off, the wish is the answer. */
    allowedMove(wanted) {
      if (!this.confineToEnvelope || !this.houseVisible) return wanted;
      return constrainToEnvelope(this.envelope, this.building, wanted);
    },
    pointerUp(event) {
      const pressed = this._pressedChoice;
      const press = this._press;
      this._pressedChoice = null;
      this._press = null;
      this.dragging = null;
      this.panning = null;
      if (press && event.type !== "pointercancel" && Math.hypot(event.clientX - press.x, event.clientY - press.y) <= CLICK_SLOP_PX) {
        this.$emit("select", press.house ? "house" : null);
      }
      if (!pressed?.parcel) return;
      const moved = Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y);
      if (moved <= CLICK_SLOP_PX) this.$emit("choose", pressed.parcel.id);
    },
    /** Zoom towards the cursor: the metre under it stays where it is. */
    onWheel(event) {
      if (!this.navigable || this.measuring) return;
      if (this.cooperative && !event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const next = clamp(this.zoomFactor * Math.exp(-event.deltaY * 0.0015), MIN_ZOOM, MAX_ZOOM);
      if (next === this.zoomFactor) return;
      const under = this.toMetres(event);
      const centre = { x: this.view.mx, y: this.view.my };
      const ratio = this.zoomFactor / next;
      this.zoomFactor = next;
      this.panMetres = {
        x: under.x - (under.x - centre.x) * ratio - this.fit.mx,
        y: under.y - (under.y - centre.y) * ratio - this.fit.my
      };
    },
    /** A second click on an empty plan is the way back to the fitted framing. */
    onDoubleClick() {
      if (this.navigable && !this.measuring) this.resetView();
    },
    onKeydown(event) {
      if (!this.interactive || !this.houseVisible || !event.target.closest("[data-house]")) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.$emit("select", "house");
        return;
      }
      if (event.key === "Escape") { this.$emit("select", null); return; }
      const step = event.shiftKey ? 1 : 0.25;
      const direction = {
        ArrowLeft: [-step, 0], ArrowRight: [step, 0],
        ArrowUp: [0, step], ArrowDown: [0, -step]
      }[event.key];
      if (!direction) return;
      event.preventDefault();
      this.$emit("move", this.allowedMove({
        cx: this.building.cx + direction[0], cy: this.building.cy + direction[1]
      }));
    }
  }
};
</script>

<style scoped>
/* The tile ground is context, not subject: grey, and multiplied into the paper
   so the service's white falls away and only its line work is left. The plot's
   own opaque fill then sits above it as the one light, coloured shape. In the
   dark theme the render is inverted first, or it would be a pale sheet. */
.site-plan__tile-ground{ opacity: .42; filter: grayscale(1); mix-blend-mode: multiply; }
.site-plan__tile-ground--dark{ opacity: .45; filter: invert(1) grayscale(1); mix-blend-mode: screen; }
/* Outline, house and surroundings appear together, once the ground has
   arrived — not the outline first and a quilt filling in around it. print.css
   shows the drawing regardless. */
.site-plan__content{ transition: opacity .24s ease-out; }
.site-plan__content.is-waiting{ opacity: 0; }
.site-plan__placeholder{ animation: w2b-pulse 1.5s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce){
  .site-plan__content{ transition: none; }
  .site-plan__placeholder{ animation: none; opacity: .7; }
}
/* The parcels on offer. Deliberately quiet: the plot itself keeps the halo and
   the drawn contour, and a candidate is a thin outline with its number — a
   choice, not a finding. */
.site-plan__choice{
  fill: var(--w2b-map-surface); fill-opacity: .12;
  stroke: var(--w2b-map-boundary); stroke-width: 1; stroke-opacity: .45;
  cursor: pointer;
  /* A chosen parcel is drawn with no fill at all, and an untouchable parcel
     cannot be deselected — which is exactly what "taking one out again does
     not work" was. `all` hit-tests the area whether or not it is painted. */
  pointer-events: all;
}
.site-plan__choice:hover{ fill-opacity: .3; stroke-opacity: .9; }
.site-plan__choice:focus-visible{ outline: none; stroke: var(--w2b-primary); stroke-width: 2.5; }
.site-plan__choice.is-chosen{ fill-opacity: 0; stroke-opacity: 0; }
/* After `is-chosen`, because a marked parcel is a chosen one: it is in the
   plot and that is the problem. */
.site-plan__choice.is-problem{
  fill: var(--w2b-map-violation); fill-opacity: .22;
  stroke: var(--w2b-map-violation); stroke-width: 2; stroke-opacity: 1;
  stroke-dasharray: 7 4;
}

.site-plan__choice-label{
  font-family: var(--w2b-font-mono); font-size: 11px; font-weight: 500;
  fill: var(--w2b-map-boundary); opacity: .7;
  paint-order: stroke fill; stroke: var(--w2b-map-halo); stroke-width: 3.4px;
  pointer-events: none; user-select: none;
}
.site-plan__choice-label.is-chosen{ opacity: 1; font-weight: 700; }

.site-plan-shell{ position: relative; }
.site-plan__map{ position: absolute; inset: 0; }
.site-plan{ display: block; width: 100%; height: auto; touch-action: none; position: relative; }
.site-plan--dragging{ cursor: grabbing; }
.site-plan--navigable{ cursor: grab; }
.site-plan--cooperative{ touch-action: pan-y; }
.site-plan--panning{ cursor: grabbing; }
.site-plan--measuring{ cursor: crosshair; }
.site-plan__dimension--measuring{ fill: var(--w2b-map-violation); }
.site-plan__dimension--overall{ font-size: 9.5px; opacity: .8; }
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
