<template>
  <div class="indizienkarte">
    <div ref="mapContainer" class="indizienkarte__canvas" :style="{ height: `${height}px` }"
         :data-map-ready="String(ready)"></div>

    <p v-if="unavailable" class="notice notice--error indizienkarte__notice">
      Die Karte lässt sich gerade nicht laden: {{ unavailable }}
    </p>

    <ul v-else class="indizienkarte__legend">
      <li v-if="candidates.length && !confirmed">
        <span class="indizienkarte__swatch indizienkarte__swatch--kandidat"></span>
        {{ candidates.length }} {{ candidates.length === 1 ? "mögliches Flurstück" : "mögliche Flurstücke" }}
      </li>
      <li v-if="confirmed">
        <span class="indizienkarte__swatch indizienkarte__swatch--bestaetigt"></span>
        Bestätigt — geprüft gegen das Kataster
      </li>
      <li v-if="areas.length">
        <span class="indizienkarte__swatch indizienkarte__swatch--gemarkung"></span>
        {{ areas.length === 1 ? "Gemarkung" : `${areas.length} Gemarkungen kommen in Frage` }}
      </li>
      <li v-if="refutedPin">
        <span class="indizienkarte__swatch indizienkarte__swatch--pin"></span>
        Kartenpunkt der Anzeige — widerlegt
      </li>
    </ul>
  </div>
</template>

<script>
/**
 * The evidence map: what is known about where the plot is, and how sure.
 *
 * The site plan answers "does it fit"; this answers "which parcel is it". It
 * takes the same backdrop as `SitePlan` — a MapLibre instance under the drawing
 * — and the same recipe: a halo stroke under every line, and the parcel fill
 * held back so the cadastre reads as a fabric rather than a wire frame.
 *
 * Its own rule, which the site plan has no use for, is the camera. It follows
 * the *candidate set*, never the newest clue, because a search interface must
 * never stand tighter than its own doubt — and it eases rather than jumps, so
 * a run reads as a narrowing-down instead of a slideshow. All of that maths is
 * in `lib/evidence.js`, where it can be tested without a canvas.
 */
import { Map as MapLibreMap, Marker, NavigationControl } from "maplibre-gl";
import { vectorStyle } from "../lib/basemap.js";
import { darkTheme } from "../lib/store.js";
import {
  FLIGHT_MS, boundsOf, contextOpacity, frameFor, isEmptyBounds, prefersReducedMotion
} from "../lib/evidence.js";

const token = (element, name) =>
  getComputedStyle(element).getPropertyValue(name).trim() || "#000";

const collection = features => ({ type: "FeatureCollection", features });

const polygonFeature = (geometry, properties = {}) =>
  geometry ? [{ type: "Feature", properties, geometry }] : [];

/** Mean of a geometry's coordinates. Good enough to put a dot on. */
function centre(geometry) {
  const points = [];
  const walk = node => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") return void points.push(node);
    node.forEach(walk);
  };
  walk(geometry?.coordinates);
  if (!points.length) return null;
  const lon = points.reduce((sum, p) => sum + p[0], 0) / points.length;
  const lat = points.reduce((sum, p) => sum + p[1], 0) / points.length;
  return [lon, lat];
}

export default {
  name: "EvidenceMap",
  props: {
    /** The live candidate set: `{id, geometry, properties, punkte}`. */
    candidates: { type: Array, default: () => [] },
    /** The cadastral district outline under them, as GeoJSON. */
    districtOutline: { type: Object, default: null },
    /** The districts the search is prepared to look in: `{name, anzahl, geometry}`.
     *  Drawn before any candidate exists, because "where could this be" is a
     *  real answer and the map should give it from the first seconds. */
    areas: { type: Array, default: () => [] },
    /** How long a camera move may take. Set by the queue's current pace. */
    flight: { type: Number, default: FLIGHT_MS },
    /** The common envelope — shown, but never like a hit. */
    huelle: { type: Object, default: null },
    /** The platform's pin, which is drawn struck through once refuted. */
    refutedPin: { type: Object, default: null },
    status: { type: String, default: null },
    height: { type: Number, default: 460 }
  },
  emits: ["select"],
  data() {
    return { unavailable: null, ready: false };
  },
  computed: {
    confirmed() { return this.status === "bestaetigt" && this.candidates.length === 1; },
    /** Which palette the ground is drawn in. Deliberately not a function of
     *  `unavailable`: a flag that feeds the rebuild rebuilds forever. */
    darkGround() { return darkTheme(); },
    candidateGeometries() { return this.candidates.map(c => c.geometry).filter(Boolean); },
    areaGeometries() { return this.areas.map(a => a.geometry).filter(Boolean); },
    /** The wash: whichever districts are still in play. Falls back to the one
     *  the answer settled on, for a run that had no space step. */
    districtGeometries() {
      return this.areaGeometries.length
        ? this.areaGeometries
        : [this.districtOutline].filter(Boolean);
    }
  },
  mounted() {
    this._frame = null;
    this._lastCount = null;
    this.build();
  },
  beforeUnmount() { this.destroy(); },
  watch: {
    darkGround() { this.rebuild(); },
    candidates() { this.draw(); this.moveCamera(); },
    districtOutline() { this.draw(); },
    areas() { this.draw(); this.moveCamera(); },
    huelle() { this.draw(); },
    status() { this.draw(); }
  },
  methods: {
    async build() {
      if (this._map) return;
      try {
        const style = await vectorStyle();
        if (!this.$refs.mapContainer || this._map) return;
        this._map = new MapLibreMap({
          container: this.$refs.mapContainer,
          style,
          center: [13.35, 51.05],   // Saxony, until the first clue says otherwise
          zoom: 6.4,
          attributionControl: { compact: true },
          // A theme switch is a rebuild -- MapLibre cannot swap a style under
          // its own layers -- and it must not throw away where the user is.
          ...(this._camera || {})
        });
        this._map.addControl(new NavigationControl({ showCompass: false }), "top-right");
        // One missing icon or tile is not a broken map — the rule the site plan
        // learned. Only a style that never arrives counts as a failure.
        this._map.on("error", e => console.warn("Indizienkarte:", e?.error?.message || e));
        this._map.on("load", () => {
          this._map.resize();
          this.addLayers();
          this.draw();
          if (this._camera) this._camera = null;
          else this.moveCamera({ instant: true });
        });
        this._map.on("idle", () => { this.ready = true; });
        this._resizes = new ResizeObserver(() => this._map?.resize());
        this._resizes.observe(this.$refs.mapContainer);
      } catch (error) {
        // Set once and left alone: a failure flag that feeds whatever decides
        // to build restarts itself forever, and the loop is pure microtasks —
        // no watchdog and no test timeout can end it.
        console.warn("Indizienkarte nicht verfügbar:", error);
        this.unavailable = error.message;
      }
    },
    rebuild() {
      const camera = this._map
        ? { center: this._map.getCenter(), zoom: this._map.getZoom() }
        : null;
      this.destroy();
      this.unavailable = null;
      this._camera = camera;
      this.$nextTick(() => this.build());
    },
    destroy() {
      this._resizes?.disconnect();
      this._resizes = null;
      this.ready = false;
      (this._markers || []).forEach(marker => marker.remove());
      this._markers = [];
      if (this._map) { this._map.remove(); this._map = null; }
    },

    addLayers() {
      const element = this.$el;
      const boundary = token(element, "--w2b-map-boundary");
      const selection = token(element, "--w2b-map-selection");
      const halo = token(element, "--w2b-map-halo");
      const envelope = token(element, "--w2b-map-envelope");

      for (const id of ["gemarkung", "huelle", "kandidaten", "punkte", "bestaetigt"]) {
        this._map.addSource(id, { type: "geojson", data: collection([]) });
      }

      // The district wash sits furthest down and fades as the camera goes in:
      // a layer whose extent dwarfs the frame has stopped informing and only
      // tints. Its opacity is set in `draw`, not here.
      this._map.addLayer({
        id: "gemarkung-fill", type: "fill", source: "gemarkung",
        paint: { "fill-color": envelope, "fill-opacity": 0.1 }
      });
      this._map.addLayer({
        id: "gemarkung-line", type: "line", source: "gemarkung",
        paint: { "line-color": envelope, "line-width": 1.2, "line-dasharray": [3, 3], "line-opacity": 0.5 }
      });

      // The common envelope: an answer about a street or a district, and never
      // drawn like a hit — no halo, no contour.
      this._map.addLayer({
        id: "huelle-fill", type: "fill", source: "huelle",
        paint: { "fill-color": selection, "fill-opacity": 0.14 }
      });

      // Every surviving candidate, equally strong. A ranking is an ordering,
      // not a finding, so nothing here says "this one".
      this._map.addLayer({
        id: "kandidaten-fill", type: "fill", source: "kandidaten",
        paint: { "fill-color": selection, "fill-opacity": 0.42 }
      });
      this._map.addLayer({
        id: "kandidaten-line", type: "line", source: "kandidaten",
        paint: { "line-color": selection, "line-width": 1.4 }
      });

      /* Twenty-two candidates spread over two districts are each a couple of
       * pixels wide, and a place you cannot find is not located. So every
       * candidate also gets a dot, which fades in exactly where the polygons
       * stop being visible and out again once the camera is close enough to
       * show the real outlines. */
      this._map.addLayer({
        id: "kandidaten-punkt", type: "circle", source: "punkte",
        paint: {
          "circle-color": selection,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3.5, 15, 6, 17, 8],
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 15.5, 0.85, 17, 0],
          "circle-stroke-width": 1.2,
          "circle-stroke-color": halo,
          "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 15.5, 0.9, 17, 0]
        }
      });

      // The one state that breaks the scale. Same line as the site plan draws
      // for a parcel: 6 px halo under 2,2 px contour, so anyone who has seen
      // one recognises the other without a legend.
      // A contour with nothing inside it reads as a hole, not as a plot. The
      // site plan holds its parcel fill to 42 % over the backdrop; so does this.
      this._map.addLayer({
        id: "bestaetigt-fill", type: "fill", source: "bestaetigt",
        paint: { "fill-color": selection, "fill-opacity": 0.42 }
      });
      this._map.addLayer({
        id: "bestaetigt-halo", type: "line", source: "bestaetigt",
        layout: { "line-join": "round" },
        paint: { "line-color": halo, "line-width": 6 }
      });
      this._map.addLayer({
        id: "bestaetigt-line", type: "line", source: "bestaetigt",
        layout: { "line-join": "round" },
        paint: { "line-color": boundary, "line-width": 2.2 }
      });

      this._map.on("click", "kandidaten-fill", event => {
        const id = event.features?.[0]?.properties?.id;
        if (id) this.$emit("select", id);
      });
      this._map.on("mouseenter", "kandidaten-fill", () => {
        this._map.getCanvas().style.cursor = "pointer";
      });
      this._map.on("mouseleave", "kandidaten-fill", () => {
        this._map.getCanvas().style.cursor = "";
      });
    },

    set(id, features) {
      this._map?.getSource(id)?.setData(collection(features));
    },

    draw() {
      if (!this._map || !this._map.getSource("kandidaten")) return;

      const confirmed = this.confirmed ? this.candidates[0] : null;
      const others = confirmed ? [] : this.candidates;

      this.set(
        "kandidaten",
        others.flatMap(candidate =>
          polygonFeature(candidate.geometry, {
            id: candidate.id,
            // A number the map can size by, so a stronger candidate reads as
            // stronger without a second colour.
            punkte: candidate.punkte ?? 0
          })
        )
      );
      this.set("bestaetigt", polygonFeature(confirmed?.geometry));
      // No dot over a confirmed parcel: that one has a contour of its own, and
      // a marker on top of it says "one of several" about the opposite.
      this.set(
        "punkte",
        others
          .map(candidate => ({ candidate, point: centre(candidate.geometry) }))
          .filter(entry => entry.point)
          .map(({ candidate, point }) => ({
            type: "Feature",
            properties: { id: candidate.id },
            geometry: { type: "Point", coordinates: point }
          }))
      );
      this.set(
        "gemarkung",
        this.districtGeometries.flatMap((geometry, index) =>
          polygonFeature(geometry, { name: this.areas[index]?.name ?? "" })
        )
      );
      // The envelope is only worth drawing while it says more than the
      // candidates do — a single parcel is its own envelope.
      this.set(
        "huelle",
        this.huelle && this.huelle.art !== "flurstueck"
          ? polygonFeature(this.huelle.geometry)
          : []
      );

      this.fadeContext();
      this.drawPin();
    },

    /** Fade the wide context layers as the camera closes in on the candidates. */
    fadeContext() {
      if (!this._map?.getLayer("gemarkung-fill") || isEmptyBounds(this._frame)) return;
      const opacity = contextOpacity(boundsOf(this.districtGeometries), this._frame, { full: 0.16 });
      this._map.setPaintProperty("gemarkung-fill", "fill-opacity", opacity);
      this._map.setPaintProperty("gemarkung-line", "line-opacity", Math.min(0.55, opacity * 3.4));
    },

    /** The refuted pin stays visible and struck through.
     *
     *  Anyone who opens the listing sees this point, so an interface that
     *  quietly points somewhere else owes them the reason. */
    drawPin() {
      (this._markers || []).forEach(marker => marker.remove());
      this._markers = [];
      if (!this.refutedPin || !this._map) return;
      const element = document.createElement("span");
      element.className = "indizienkarte__pin";
      // Text nodes, not markup: this comes from a listing page.
      element.textContent = "Anzeigenpunkt";
      element.title = "Der Kartenpunkt der Anzeige — meist der geokodierte Ortsname, nicht das Grundstück";
      this._markers = [
        new Marker({ element, anchor: "left" })
          .setLngLat([this.refutedPin.lon, this.refutedPin.lat])
          .addTo(this._map)
      ];
    },

    /**
     * Move to the frame the current doubt calls for.
     *
     * Eased, not jumped: a run is meant to read as a narrowing-down. The frame
     * itself comes from `frameFor`, which only lets the camera close in once a
     * candidate has actually dropped out.
     */
    moveCamera({ instant = false } = {}) {
      if (!this._map) return;
      const count = this.candidates.length;
      const tightened = this._lastCount !== null && count > 0 && count < this._lastCount;
      // Until a candidate exists, the districts in play *are* the doubt, and
      // framing them is how the map says where this could be at all.
      const next = frameFor({
        candidates: this.candidateGeometries.length
          ? this.candidateGeometries
          : this.districtGeometries,
        previous: this._frame,
        tightened: tightened || (count > 0 && this._lastCount === null)
      });
      this._lastCount = count === 0 ? this._lastCount : count;
      if (isEmptyBounds(next)) return;
      if (next === this._frame) return void this.fadeContext();
      this._frame = next;
      this.ready = false;
      this._map.fitBounds(
        [[next.west, next.south], [next.east, next.north]],
        {
          padding: 36,
          maxZoom: 18,
          duration: instant || prefersReducedMotion() ? 0 : this.flight,
          essential: true
        }
      );
      this.fadeContext();
    },

    /** Exposed so the protocol can jump to a clue without waiting for the queue. */
    focusOn(geometry) {
      if (!this._map || !geometry) return;
      const bounds = boundsOf(geometry);
      if (isEmptyBounds(bounds)) return;
      this._frame = frameFor({ candidates: this.candidateGeometries, evidence: geometry, previous: null, tightened: true });
      this._map.fitBounds(
        [[this._frame.west, this._frame.south], [this._frame.east, this._frame.north]],
        { padding: 36, maxZoom: 18, duration: prefersReducedMotion() ? 0 : this.flight, essential: true }
      );
    }
  }
};
</script>

<style scoped>
.indizienkarte__canvas{
  width: 100%; border-radius: var(--w2b-radius-m); overflow: hidden;
  background: var(--w2b-map-ground); border: 1px solid var(--w2b-line);
}
.indizienkarte__notice{ margin-top: var(--w2b-space-3); }
.indizienkarte__legend{
  display: flex; flex-wrap: wrap; gap: var(--w2b-space-4);
  margin: var(--w2b-space-3) 0 0; padding: 0; list-style: none;
  color: var(--w2b-muted); font-size: var(--w2b-text-xs);
}
.indizienkarte__legend li{ display: flex; align-items: center; gap: 6px; }
.indizienkarte__swatch{ width: 14px; height: 10px; border-radius: 2px; display: inline-block; }
.indizienkarte__swatch--kandidat{ background: var(--w2b-map-selection); opacity: .42; border: 1px solid var(--w2b-map-selection); }
.indizienkarte__swatch--bestaetigt{ background: var(--w2b-map-halo); border: 2px solid var(--w2b-map-boundary); }
.indizienkarte__swatch--gemarkung{ background: transparent; border: 1px dashed var(--w2b-map-envelope); }
.indizienkarte__swatch--pin{ background: var(--w2b-map-violation); opacity: .5; }
</style>

<style>
/* Unscoped: the marker element is created in script and attached by MapLibre
   outside this component's tree, so a scoped selector never reaches it. */
.indizienkarte__pin{
  font-family: var(--w2b-font-mono); font-size: 10px; white-space: nowrap;
  padding: 2px 7px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-surface); color: var(--w2b-muted);
  border: 1px solid var(--w2b-map-violation);
  text-decoration: line-through;
  text-decoration-color: var(--w2b-map-violation);
  text-decoration-thickness: 1.5px;
  transform: translateX(10px);
}
</style>
