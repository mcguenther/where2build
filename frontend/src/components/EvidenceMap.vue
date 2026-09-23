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
        Bestätigt: geprüft gegen das Kataster
      </li>
      <li v-if="areas.length">
        <span class="indizienkarte__swatch indizienkarte__swatch--gemarkung"></span>
        {{ areas.length === 1 ? "Gemarkung" : `${areas.length} Gemarkungen kommen in Frage` }}
      </li>
      <li v-if="bands.length">
        <span class="indizienkarte__swatch indizienkarte__swatch--band"></span>
        {{ bands.length === 1 ? "Entfernungsband" : `${bands.length} Entfernungsbänder` }}
        aus dem Inserat — gestrichelt, weil es nur ordnet
      </li>
      <li v-if="refutedPin">
        <span class="indizienkarte__swatch indizienkarte__swatch--pin"></span>
        Kartenpunkt der Anzeige, widerlegt
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
import { aerialCadastreStyle, canRenderMap, vectorStyle } from "../lib/basemap.js";
import { MapStack } from "../lib/mapFade.js";
import { darkTheme } from "../lib/store.js";
import { bandFeatures } from "../lib/bands.js";
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
    /** Every Indiz the run has produced. Only the distance bands are drawn from
     *  it: a stated distance is the one clue that says *why* the search is
     *  looking where it is looking, and the only one with a shape of its own
     *  that is not a parcel or a district. */
    indicia: { type: Array, default: () => [] },
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
    /** The same point before anything has refuted it. Framed while nothing
     *  better is known, so the map leaves the whole state at the first clue. */
    pin: { type: Object, default: null },
    /** The geometry the protocol is currently pointing at, marked on the map so
     *  a jump says *which* thing it jumped to. One or several. */
    highlighted: { type: [Object, Array], default: null },
    status: { type: String, default: null },
    height: { type: Number, default: 460 },
    /** What lies under the drawing. `site` is the orthophoto with the roads
     *  and the cadastral outlines over it — a listing's own photographs are
     *  recognisable against that, which a street map cannot offer. `map` is
     *  the vector basemap. */
    ground: { type: String, default: "site" }
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
    /** The distance bands, as features. Empty until a reference resolved. */
    bands() { return bandFeatures(this.indicia); },
    /** The wash: whichever districts are still in play. Falls back to the one
     *  the answer settled on, for a run that had no space step. */
    districtGeometries() {
      return this.areaGeometries.length
        ? this.areaGeometries
        : [this.districtOutline].filter(Boolean);
    },
    /** The advert's own point, as something to frame before anything is found. */
    pinGeometry() {
      const pin = this.pin || this.refutedPin;
      return pin ? [{ type: "Point", coordinates: [pin.lon, pin.lat] }] : [];
    }
  },
  created() { this._maps = new MapStack(); },
  mounted() {
    this._frame = null;
    this._lastCount = null;
    this.build();
  },
  beforeUnmount() { this.destroy(); },
  watch: {
    darkGround() { this.rebuild(); },
    // MapLibre cannot swap a style under its own layers, so a different ground
    // is a rebuild -- which keeps the camera, because `rebuild` saves it.
    ground() { this.rebuild(); },
    candidates() { this.draw(); this.moveCamera(); },
    districtOutline() { this.draw(); },
    areas() { this.draw(); this.moveCamera(); },
    pin() { this.moveCamera(); },
    highlighted() { this.drawHighlight(); },
    huelle() { this.draw(); },
    indicia() { this.draw(); },
    status() { this.draw(); }
  },
  methods: {
    async build() {
      if (this._map) return;
      if (!canRenderMap()) {
        this.unavailable = "Diese Ansicht braucht WebGL, und der Browser bietet es nicht an.";
        return;
      }
      try {
        const style = this.ground === "site" ? aerialCadastreStyle() : await vectorStyle();
        if (!this.$refs.mapContainer || this._map) return;
        // Built over the map it replaces and faded in once it has drawn, so
        // switching to the photograph does not flash bare paper
        // (`lib/mapFade.js`). `ready` waits for the fade as well as the tiles.
        const map = this._maps.start(this.$refs.mapContainer, container => new MapLibreMap({
          container,
          style,
          center: [13.35, 51.05],   // Saxony, until the first clue says otherwise
          zoom: 6.4,
          attributionControl: { compact: true },
          // A theme switch is a rebuild -- MapLibre cannot swap a style under
          // its own layers -- and it must not throw away where the user is.
          ...(this._camera || {})
        }), () => { this.ready = true; });
        this._map = map;
        this._map.addControl(new NavigationControl({ showCompass: false }), "top-right");
        // One missing icon or tile is not a broken map — the rule the site plan
        // learned. Only a style that never arrives counts as a failure.
        this._map.on("error", e => console.warn("Indizienkarte:", e?.error?.message || e));
        this._map.on("load", () => {
          // Superseded before it finished loading; its successor draws itself.
          if (this._map !== map) return;
          this._map.resize();
          this.addLayers();
          this.draw();
          if (this._camera) this._camera = null;
          else this.moveCamera({ instant: true });
        });
        if (!this._resizes) {
          this._resizes = new ResizeObserver(() => this._map?.resize());
          this._resizes.observe(this.$refs.mapContainer);
        }
      } catch (error) {
        // Set once and left alone: a failure flag that feeds whatever decides
        // to build restarts itself forever, and the loop is pure microtasks —
        // no watchdog and no test timeout can end it.
        console.warn("Indizienkarte nicht verfügbar:", error);
        this.destroy();
        this.unavailable = error.message;
      }
    },
    rebuild() {
      const camera = this._map
        ? { center: this._map.getCenter(), zoom: this._map.getZoom() }
        : null;
      // The old map and its pin stay on screen until the new one has faded
      // in over them, and go with it.
      this._maps.retire();
      this._map = null;
      this._markers = [];
      this.ready = false;
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
      this._map = null;
      this._maps.clear();
    },

    addLayers() {
      const element = this.$el;
      const boundary = token(element, "--w2b-map-boundary");
      const selection = token(element, "--w2b-map-selection");
      const halo = token(element, "--w2b-map-halo");
      const envelope = token(element, "--w2b-map-envelope");

      for (const id of ["baender", "gemarkung", "huelle", "kandidaten", "punkte", "bestaetigt", "gezeigt"]) {
        this._map.addSource(id, { type: "geojson", data: collection([]) });
      }

      /* An orthophoto is not a background, it is a picture — mostly green,
       * grey and dark, with detail everywhere. A wash tuned for pale paper
       * disappears into it and a hairline is gone over foliage. So over the
       * photo every fill is stronger and every line gets the halo the site
       * plan has always drawn under its own: dark underneath, colour on top,
       * legible against whatever happens to be beneath it. */
      const photo = this.ground === "site";
      const wash = photo ? 0.24 : 0.1;
      const hullWash = photo ? 0.26 : 0.14;
      const lineWidth = photo ? 2.2 : 1.4;
      const haloWidth = photo ? 5 : 0;

      /* The distance bands sit under everything, because they are the widest
       * thing on the map and the least binding. Both borders dashed, on
       * purpose: a solid line is what this map draws around a finding, and a
       * band is not one — it orders candidates, it may object, and it can
       * never confirm. The fill is barely there; what is worth seeing is where
       * the ring lies, not how much of the county it covers. */
      this._map.addLayer({
        id: "baender-fill", type: "fill", source: "baender",
        paint: { "fill-color": envelope, "fill-opacity": photo ? 0.12 : 0.07 }
      });
      if (haloWidth) {
        this._map.addLayer({
          id: "baender-halo", type: "line", source: "baender",
          layout: { "line-join": "round" },
          paint: { "line-color": halo, "line-width": 4, "line-opacity": 0.5 }
        });
      }
      this._map.addLayer({
        id: "baender-line", type: "line", source: "baender",
        layout: { "line-join": "round" },
        paint: {
          "line-color": envelope,
          "line-width": photo ? 2 : 1.4,
          "line-dasharray": [6, 4],
          "line-opacity": photo ? 0.9 : 0.6
        }
      });

      // The district wash sits furthest down and fades as the camera goes in:
      // a layer whose extent dwarfs the frame has stopped informing and only
      // tints. Its opacity is set in `draw`, not here.
      this._map.addLayer({
        id: "gemarkung-fill", type: "fill", source: "gemarkung",
        paint: { "fill-color": envelope, "fill-opacity": wash }
      });
      if (haloWidth) {
        this._map.addLayer({
          id: "gemarkung-halo", type: "line", source: "gemarkung",
          layout: { "line-join": "round" },
          paint: { "line-color": halo, "line-width": haloWidth, "line-opacity": 0.55 }
        });
      }
      this._map.addLayer({
        id: "gemarkung-line", type: "line", source: "gemarkung",
        paint: {
          "line-color": envelope,
          "line-width": photo ? 2 : 1.2,
          "line-dasharray": [3, 3],
          "line-opacity": photo ? 0.95 : 0.5
        }
      });

      // The common envelope: an answer about a street or a district, and never
      // drawn like a hit — no halo, no contour.
      this._map.addLayer({
        id: "huelle-fill", type: "fill", source: "huelle",
        paint: { "fill-color": selection, "fill-opacity": hullWash }
      });

      // Every surviving candidate, equally strong. A ranking is an ordering,
      // not a finding, so nothing here says "this one".
      this._map.addLayer({
        id: "kandidaten-fill", type: "fill", source: "kandidaten",
        paint: { "fill-color": selection, "fill-opacity": photo ? 0.5 : 0.42 }
      });
      if (haloWidth) {
        this._map.addLayer({
          id: "kandidaten-halo", type: "line", source: "kandidaten",
          layout: { "line-join": "round" },
          paint: { "line-color": halo, "line-width": haloWidth }
        });
      }
      this._map.addLayer({
        id: "kandidaten-line", type: "line", source: "kandidaten",
        paint: { "line-color": selection, "line-width": lineWidth }
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
          "circle-stroke-width": photo ? 2.4 : 1.2,
          "circle-stroke-color": halo,
          "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 15.5, 0.9, 17, 0]
        }
      });

      // The one state that breaks the scale. Same line as the site plan draws
      // for a parcel: 6 px halo under 2,2 px contour, so anyone who has seen
      // one recognises the other without a legend.
      // A contour with nothing inside it reads as a hole, not as a plot. The
      // site plan holds its parcel fill to 42 % over the backdrop; so does this.
      /* What the Verlauf is pointing at. Without it a jump to a clue was a
         camera move and nothing else — the map arrived somewhere and never said
         which of the things on it was the reason. Drawn over everything and
         only while an entry is selected. */
      this._map.addLayer({
        id: "gezeigt-halo", type: "line", source: "gezeigt",
        layout: { "line-join": "round" },
        paint: { "line-color": halo, "line-width": 8, "line-opacity": 0.75 }
      });
      this._map.addLayer({
        id: "gezeigt-line", type: "line", source: "gezeigt",
        layout: { "line-join": "round" },
        paint: {
          "line-color": token(element, "--w2b-accent") || selection,
          "line-width": 3,
          "line-dasharray": [2, 1.6]
        }
      });

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

    /** Mark whatever the protocol is pointing at, so a jump names its reason. */
    drawHighlight() {
      if (!this._map || !this._map.getSource("gezeigt")) return;
      const shapes = Array.isArray(this.highlighted)
        ? this.highlighted
        : [this.highlighted].filter(Boolean);
      this.set("gezeigt", shapes.flatMap(shape => polygonFeature(shape)));
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
      this.drawHighlight();
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
      this._map.getSource("baender")?.setData(collection(this.bands));
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
      element.title = "Der Kartenpunkt der Anzeige: meist der geokodierte Ortsname, nicht das Grundstück";
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
      // Whatever is the best statement about where this is, in that order.
      // The pin is last and it is not a candidate — it is 6 km out on a real
      // advert — but it is a *place*, and a map that sits on the whole state
      // while the list already names a village reads as broken.
      const known = this.candidateGeometries.length
        ? this.candidateGeometries
        : this.districtGeometries.length
          ? this.districtGeometries
          : this.pinGeometry;
      const next = frameFor({
        candidates: known,
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
  position: relative; width: 100%; border-radius: var(--w2b-radius-m); overflow: hidden;
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
.indizienkarte__swatch--band{
  background: color-mix(in srgb, var(--w2b-map-envelope) 14%, transparent);
  border: 1px dashed var(--w2b-map-envelope);
}
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
