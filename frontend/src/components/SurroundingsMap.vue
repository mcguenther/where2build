<template>
  <div class="surroundings">
    <div v-if="!unavailable" class="surroundings__tools no-print">
      <span class="surroundings__tools-label">Ausschnitt</span>
      <button type="button" class="btn btn--quiet btn--small" :aria-pressed="String(framing === 'plot')"
              @click="setFraming('plot')">Grundstück</button>
      <button type="button" class="btn btn--quiet btn--small" :aria-pressed="String(framing === 'nearby')"
              @click="setFraming('nearby')">Umgebung</button>
      <button v-if="routedDestinations.length" type="button" class="btn btn--quiet btn--small"
              :aria-pressed="String(framing === 'destinations')"
              @click="setFraming('destinations')">Mit Zielen</button>
    </div>

    <div ref="mapContainer" class="surroundings__canvas" :style="{ height: `${height}px` }"
         :data-map-ready="String(ready)"></div>

    <p v-if="unavailable" class="notice notice--error surroundings__notice">
      Die Karte lässt sich gerade nicht laden: {{ unavailable }}
    </p>

    <ul v-else class="surroundings__legend">
      <li><span class="surroundings__swatch surroundings__swatch--plot"></span>Grundstück</li>
      <li><span class="surroundings__swatch surroundings__swatch--house"></span>Baukörper</li>
      <li v-if="located.length"><span class="surroundings__swatch surroundings__swatch--poi"></span>
        {{ located.length }} {{ located.length === 1 ? "Ort" : "Orte" }} in der Umgebung</li>
      <li v-if="routedDestinations.length"><span class="surroundings__swatch surroundings__swatch--goal"></span>
        {{ routedDestinations.length }} {{ routedDestinations.length === 1 ? "eigenes Ziel" : "eigene Ziele" }}</li>
    </ul>
  </div>
</template>

<script>
/**
 * The plot in its surroundings: the house where it would stand, enough map
 * around it to recognise the place, and every point of interest that was
 * found, at the scale that holds them all.
 *
 * The site plan answers "does it fit"; this answers "where is this". They are
 * deliberately different drawings — the plan is fixed-framing and printable,
 * this one pans and zooms.
 */
import { Map as MapLibreMap, Marker, NavigationControl } from "maplibre-gl";
import { vectorStyle } from "../lib/basemap.js";
import { MapStack } from "../lib/mapFade.js";
import { darkTheme } from "../lib/store.js";
import { toWgs84 } from "../lib/projection.js";
import { rectangleCorners } from "../lib/geometry.js";
import { openStreetMapPlace, openStreetMapRoute } from "../lib/mapLinks.js";
import { duration, metres } from "../lib/format.js";

const CATEGORY_LABELS = {
  schule: "Schule", kindergarten: "Kita", park: "Park", spielplatz: "Spielplatz",
  supermarkt: "Supermarkt", arzt: "Arzt", tram: "Straßenbahn", bus: "Bus",
  sbahn: "S-Bahn", bahnhof: "Bahnhof"
};

/* Read off the stylesheet rather than hard-coded, so the drawing keeps using
 * the same palette as the site plan and follows the theme with it. */
/** "Linie 141" / "Linien 141, 172", and nothing at all when the answer carries
 *  no lines -- `null` is "nicht abgefragt", and a hover label is no place to
 *  explain that. The panel below the map says it in words. */
const lineLabel = (lines) =>
  lines && lines.length ? `${lines.length === 1 ? "Linie" : "Linien"} ${lines.join(", ")}` : "";

const token = (element, name) =>
  getComputedStyle(element).getPropertyValue(name).trim() || "#000";

export default {
  name: "SurroundingsMap",
  props: {
    plot: { type: Object, required: true },
    building: { type: Object, default: null },
    /** The `treffer` array of a /api/nearby answer. */
    hits: { type: Array, default: () => [] },
    /** The destinations this user entered: `{id, name, lat, lon, line, note}`,
     *  where `line` is the computed route as `[lon, lat]` pairs, if there is one. */
    destinations: { type: Array, default: () => [] },
    height: { type: Number, default: 520 }
  },
  data() {
    // Two questions, two scales: a destination in Dresden zooms the plot down
    // to nothing, which is the opposite of placing it. The nearby framing is
    // the default because that is what this view is for.
    return { unavailable: null, framing: "nearby", ready: false };
  },
  computed: {
    /** Only what carries a coordinate can be put on a map. */
    located() {
      return this.hits.filter(h => Number.isFinite(h.lat) && Number.isFinite(h.lon));
    },
    plotOutline() {
      return this.plot.anchor ? toWgs84(this.plot.polygon, this.plot.anchor) : [];
    },
    houseOutline() {
      if (!this.plot.anchor || !this.building) return [];
      return toWgs84(rectangleCorners(this.building), this.plot.anchor);
    },
    routedDestinations() {
      return this.destinations.filter(d => Number.isFinite(d.lat) && Number.isFinite(d.lon));
    },
    /** Which palette the ground is drawn in. Deliberately not a function of
     *  `unavailable` — a flag that feeds the rebuild rebuilds forever. */
    darkGround() { return darkTheme(); },
    routeLines() {
      return this.routedDestinations.map(d => d.line).filter(line => Array.isArray(line) && line.length > 1);
    }
  },
  created() { this._maps = new MapStack(); },
  mounted() { this.build(); },
  beforeUnmount() { this.destroy(); },
  watch: {
    // A different plot is a different place: rebuild rather than pan.
    "plot.id"() { this.rebuild(); },
    // MapLibre cannot swap a style under its own custom layers, so a changed
    // palette is a rebuild. The camera is carried across it: a theme switch
    // must not throw away where the user had panned to.
    darkGround() { this.rebuild({ keepCamera: true }); },
    located() { this.drawMarkers(); },
    routedDestinations() { this.drawMarkers(); this.drawRoutes(); },
    houseOutline() { this.setData("house", this.houseOutline); }
  },
  methods: {
    label(key) { return CATEGORY_LABELS[key] ?? key; },
    async build() {
      if (!this.plot.anchor || this._map) return;
      try {
        const style = await vectorStyle();
        if (!this.$refs.mapContainer || this._map) return;
        // Built over the map it replaces and faded in once it has drawn, so a
        // theme switch does not flash bare paper (`lib/mapFade.js`). Anything
        // photographing it waits for the fade as well as for the tiles.
        const map = this._maps.start(this.$refs.mapContainer, container => new MapLibreMap({
          container,
          style,
          center: [this.plot.anchor.lon, this.plot.anchor.lat],
          zoom: 15,
          attributionControl: { compact: true },
          ...(this._camera || {})
        }), () => { this.ready = true; });
        this._map = map;
        this._map.addControl(new NavigationControl({ showCompass: false }), "top-right");
        // One missing icon or tile is not a broken map -- the same rule the
        // site plan learned. Only a style that never arrives counts as failure.
        this._map.on("error", e => console.warn("Umgebungskarte:", e?.error?.message || e));
        this._map.on("load", () => {
          // Superseded before it finished loading; its successor draws itself.
          if (this._map !== map) return;
          // The canvas is sized at construction; inside a grid that is before
          // the column has its width, and the map then paints a patch in the
          // corner of a box it thinks is smaller than it is.
          this._map.resize();
          this.drawOutlines();
          this.drawRoutes();
          this.drawMarkers();
          // Only frame afresh when there is nothing to return to; a rebuild
          // that kept the camera has already been put back where it was.
          if (this._camera) this._camera = null;
          else this.frame();
        });
        if (!this._resizes) {
          this._resizes = new ResizeObserver(() => this._map?.resize());
          this._resizes.observe(this.$refs.mapContainer);
        }
      } catch (error) {
        // Set once and left alone: the flag must not feed back into whatever
        // decides to build, or the failure restarts itself forever.
        console.warn("Umgebungskarte nicht verfügbar:", error);
        this.destroy();
        this.unavailable = error.message;
      }
    },
    rebuild({ keepCamera = false } = {}) {
      if (keepCamera && this._map) {
        this._camera = {
          center: this._map.getCenter(), zoom: this._map.getZoom(),
          bearing: this._map.getBearing(), pitch: this._map.getPitch()
        };
      }
      // The old map and its markers stay on screen until the new one has
      // faded in over them, and go with it.
      this._maps.retire();
      this._map = null;
      this._markers = [];
      this.ready = false;
      this.unavailable = null;
      this.$nextTick(() => this.build());
    },
    destroy() {
      this._resizes?.disconnect();
      this._resizes = null;
      this.ready = false;
      (this._markers || []).forEach(m => m.remove());
      this._markers = [];
      this._map = null;
      this._maps.clear();
    },
    polygon(ring) {
      return {
        type: "FeatureCollection",
        features: ring.length
          ? [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] } }]
          : []
      };
    },
    setData(id, ring) {
      const source = this._map?.getSource(id);
      if (source) source.setData(this.polygon(ring));
    },
    drawRoutes() {
      if (!this._map) return;
      const data = {
        type: "FeatureCollection",
        features: this.routeLines.map(line => ({
          type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line }
        }))
      };
      const source = this._map.getSource("routes");
      if (source) return source.setData(data);

      this._map.addSource("routes", { type: "geojson", data });
      this._map.addLayer({
        id: "routes-halo", type: "line", source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": token(this.$el, "--w2b-map-halo"), "line-width": 5, "line-opacity": 0.8 }
      });
      this._map.addLayer({
        id: "routes-line", type: "line", source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": token(this.$el, "--w2b-map-street"), "line-width": 2.5 }
      });
    },
    drawOutlines() {
      const el = this.$el;
      const boundary = token(el, "--w2b-map-boundary");
      const house = token(el, "--w2b-map-design");
      const houseEdge = token(el, "--w2b-map-design-edge");

      this._map.addSource("plot", { type: "geojson", data: this.polygon(this.plotOutline) });
      this._map.addLayer({
        id: "plot-fill", type: "fill", source: "plot",
        paint: { "fill-color": boundary, "fill-opacity": 0.12 }
      });
      this._map.addLayer({
        id: "plot-line", type: "line", source: "plot",
        paint: { "line-color": boundary, "line-width": 2 }
      });

      this._map.addSource("house", { type: "geojson", data: this.polygon(this.houseOutline) });
      this._map.addLayer({
        id: "house-fill", type: "fill", source: "house",
        paint: { "fill-color": house, "fill-opacity": 0.85 }
      });
      this._map.addLayer({
        id: "house-line", type: "line", source: "house",
        paint: { "line-color": houseEdge, "line-width": 1.5 }
      });
    },
    /** Markers are HTML, not a symbol layer: a symbol layer needs glyphs from
     *  the style, and a label that cannot render is a place that vanishes. */
    drawMarkers() {
      if (!this._map) return;
      (this._markers || []).forEach(m => m.remove());
      // The parcel itself. At the scale that holds the surroundings it is a
      // couple of pixels wide, and a place you cannot find is not located.
      const home = [{
        lon: this.plot.anchor.lon, lat: this.plot.anchor.lat, kind: "home",
        title: "Hier", name: this.plot.name, lines: "", note: "",
        href: openStreetMapPlace(this.plot.anchor),
        hover: `${this.plot.name} auf OpenStreetMap`
      }];
      const places = this.located.map(hit => ({
        lon: hit.lon, lat: hit.lat, kind: "poi",
        title: this.label(hit.kategorie),
        name: hit.name,
        // The lines belong on hover, not on the always-visible label: six
        // stops in one village already fight for the same few pixels, and
        // the category is what has to stay readable there.
        lines: lineLabel(hit.linien),
        note: hit.erreichbar
          ? `${duration(hit.duration_s)} · ${metres(hit.distance_m, 0)}`
          : "kein Fußweg gefunden",
        href: openStreetMapRoute(this.plot.anchor, hit, "walk"),
        hover: `Fußweg vom Grundstück zu ${hit.name} auf OpenStreetMap`
      }));
      const goals = this.routedDestinations.map(goal => ({
        lon: goal.lon, lat: goal.lat, kind: "goal",
        title: "Ziel",
        name: goal.name,
        lines: "",
        note: goal.note || "",
        href: openStreetMapRoute(this.plot.anchor, goal, "car"),
        hover: `Weg vom Grundstück zu ${goal.name} auf OpenStreetMap`
      }));

      this._markers = [...home, ...places, ...goals].map(place => {
        const element = document.createElement("a");
        element.className = `surroundings__poi surroundings__poi--${place.kind}`;
        element.href = place.href;
        element.target = "_blank";
        element.rel = "noopener noreferrer";
        element.title = place.hover;
        // Written as text nodes, not markup: these names come from OpenStreetMap
        // and from what the user typed, and neither is ours to trust as HTML.
        const dot = document.createElement("span");
        dot.className = "surroundings__poi-dot";
        const text = document.createElement("span");
        text.className = "surroundings__poi-text";
        const strong = document.createElement("b");
        strong.textContent = place.title;
        text.append(strong);
        [place.name, place.lines, place.note].filter(Boolean).forEach(line => {
          const span = document.createElement("span");
          span.textContent = line;
          text.append(span);
        });
        element.append(dot, text);
        return new Marker({ element, anchor: "left" })
          .setLngLat([place.lon, place.lat])
          .addTo(this._map);
      });
    },
    setFraming(framing) {
      this.framing = framing;
      this.ready = false;
      this.frame();
    },
    /** Show the plot and everything that was found around it, at one scale. */
    frame() {
      const points = {
        plot: this.plotOutline,
        nearby: [...this.plotOutline, ...this.located.map(h => [h.lon, h.lat])],
        destinations: [
          ...this.plotOutline,
          ...this.routedDestinations.map(d => [d.lon, d.lat]),
          ...this.routeLines.flat()
        ]
      }[this.framing];
      if (!points.length) return;
      const bounds = points.reduce(
        (b, [lon, lat]) => ({
          west: Math.min(b.west, lon), east: Math.max(b.east, lon),
          south: Math.min(b.south, lat), north: Math.max(b.north, lat)
        }),
        { west: Infinity, east: -Infinity, south: Infinity, north: -Infinity }
      );
      this._map.fitBounds(
        [[bounds.west, bounds.south], [bounds.east, bounds.north]],
        // Room for the marker labels, which sit to the right of their point.
        {
          padding: { top: 40, bottom: 40, left: 40, right: 150 },
          maxZoom: this.framing === "plot" ? 18.5 : 17,
          duration: 0
        }
      );
    }
  }
};
</script>

<style scoped>
.surroundings__canvas{
  position: relative; width: 100%; border-radius: var(--w2b-radius-m); overflow: hidden;
  background: var(--w2b-map-ground); border: 1px solid var(--w2b-line);
}
.surroundings__notice{ margin-top: var(--w2b-space-3); }
.surroundings__legend{
  display: flex; flex-wrap: wrap; gap: var(--w2b-space-4);
  margin: var(--w2b-space-3) 0 0; padding: 0; list-style: none;
  color: var(--w2b-muted); font-size: var(--w2b-text-xs);
}
.surroundings__legend li{ display: flex; align-items: center; gap: 6px; }
.surroundings__swatch{ width: 14px; height: 10px; border-radius: 2px; display: inline-block; }
.surroundings__swatch--plot{ background: var(--w2b-map-boundary); opacity: .35; border: 1px solid var(--w2b-map-boundary); }
.surroundings__swatch--house{ background: var(--w2b-map-design); border: 1px solid var(--w2b-map-design-edge); }
.surroundings__swatch--poi{ background: var(--w2b-map-envelope); border-radius: 50%; width: 10px; height: 10px; }
.surroundings__swatch--goal{ background: var(--w2b-map-street); width: 10px; height: 10px; }
.surroundings__tools{
  display: flex; align-items: center; gap: var(--w2b-space-2);
  margin-bottom: var(--w2b-space-3);
}
.surroundings__tools-label{
  color: var(--w2b-muted); font-size: var(--w2b-text-xs);
  letter-spacing: .06em; text-transform: uppercase;
}
</style>

<style>
/* Not scoped: the marker element is created in script and lives in MapLibre's
   own container, where a [data-v-…] attribute would never reach it. */
.surroundings__poi{
  display: flex; align-items: center; gap: 5px;
  text-decoration: none; color: var(--w2b-text); cursor: pointer;
}
.surroundings__poi-dot{
  width: 11px; height: 11px; flex: none; border-radius: 50%;
  background: var(--w2b-map-envelope); border: 2px solid var(--w2b-map-halo);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, .35);
}
/* A destination the user entered is square, so the two kinds stay apart for
   anyone who cannot rely on the colour difference. */
.surroundings__poi--goal .surroundings__poi-dot{ border-radius: 2px; background: var(--w2b-map-street); }
.surroundings__poi--home .surroundings__poi-dot{
  width: 15px; height: 15px; background: var(--w2b-map-design);
  border-color: var(--w2b-map-design-edge);
}
.surroundings__poi--home .surroundings__poi-text{ border-color: var(--w2b-map-design-edge); }
.surroundings__poi-text{
  display: flex; flex-direction: column; line-height: 1.15;
  padding: 2px 5px; border-radius: var(--w2b-radius-xs);
  background: var(--w2b-surface); border: 1px solid var(--w2b-line);
  font-size: 10px; white-space: nowrap;
}
.surroundings__poi-text b{ font-size: 10.5px; }
.surroundings__poi-text span{ color: var(--w2b-muted); font-size: 9.5px; }
.surroundings__poi-text span:last-child{ font-family: var(--w2b-font-mono); font-size: 9px; }

/* Only the category is always on the map. Six stops in one village put their
   full names on top of each other and on top of the plot, which is the one
   thing this view exists to show; the name and the walk come on hover, and the
   table below the map carries all of it in full either way. */
.surroundings__poi-text span{ display: none; }
.surroundings__poi:hover .surroundings__poi-text span,
.surroundings__poi:focus-visible .surroundings__poi-text span{ display: block; }
.surroundings__poi:hover .surroundings__poi-text{ border-color: var(--w2b-primary); }

/* Whatever is being read sits on top of what is not, and the plot sits above
   everything: a marker hidden behind a label is a place that is not located. */
.surroundings__poi{ z-index: 1; }
.surroundings__poi:hover{ z-index: 3; }
.surroundings__poi--home{ z-index: 2; }
.surroundings__poi--home .surroundings__poi-text span{ display: block; }
</style>
