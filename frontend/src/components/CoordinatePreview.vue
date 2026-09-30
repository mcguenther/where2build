<template>
  <!-- One fixed height in every state: loading, found, nothing found, failed.
       The preview sits under the search field, and a box that grew when the
       cadastre answered would push the page down under the user's hand. -->
  <div ref="root" class="kartenvorschau" :class="{ 'kartenvorschau--verschieben': moving }"
       :style="{ height: `${PREVIEW_HEIGHT}px` }">
    <svg class="kartenvorschau__karte" :viewBox="`0 0 ${frame.width} ${frame.height}`"
         preserveAspectRatio="xMidYMid slice"
         :role="moving ? 'application' : 'img'" :tabindex="moving ? 0 : undefined"
         :aria-label="mapLabel"
         @pointerdown="onPointerDown" @pointermove="onPointerMove"
         @pointerup="onPointerUp" @pointercancel="onPointerUp" @keydown="onKeyDown">
      <rect x="0" y="0" :width="frame.width" :height="frame.height" fill="var(--w2b-map-ground)" />
      <!-- The ground is the proxied GeoSN web atlas as plain <image> tiles, the
           way the route cards draw theirs, not a MapLibre instance: this box
           appears the moment a coordinate is typed, before anything is looked
           up, and a WebGL context plus a style download for a 170 px glimpse
           of the neighbourhood is the heaviest possible way to show it. A tile
           that never arrives leaves the ground colour above. -->
      <!-- The veil goes on the group, not on each tile: semi-transparent tiles
           that overlap by the half unit below draw their seams twice. -->
      <g class="kartenvorschau__grund">
        <image v-for="tile in tiles" :key="tile.key" :href="tile.href"
               :x="tile.left" :y="tile.top" :width="tile.size + 0.5" :height="tile.size + 0.5"
               preserveAspectRatio="none" />
      </g>
      <g v-if="outlines.length" class="kartenvorschau__flurstueck">
        <path v-for="outline in outlines" :key="`halo-${outline.key}`" :d="outline.d"
              fill="none" stroke="var(--w2b-map-halo)" stroke-width="6" stroke-linejoin="round" />
        <path v-for="outline in outlines" :key="outline.key" :d="outline.d" fill-rule="evenodd"
              fill="var(--w2b-primary-veil)" stroke="var(--w2b-map-boundary)" stroke-width="2.2"
              stroke-linejoin="round" />
      </g>
      <circle class="kartenvorschau__punkt" :cx="marker.x" :cy="marker.y" r="7"
              fill="var(--w2b-primary)" stroke="#fff" stroke-width="2.5" />
    </svg>

    <p v-if="moving" class="kv-hinweis">Klicken oder den Punkt ziehen</p>
    <button type="button" class="kv-verschieben" :aria-pressed="moving ? 'true' : 'false'"
            @click="toggleMoving">Punkt verschieben</button>

    <div class="kv-leiste">
      <span class="wert kv-status" :class="{ 'kv-status--fehler': status === 'error' }" aria-live="polite">
        <template v-if="status === 'loading'">Flurstück wird nachgeschlagen …</template>
        <template v-else-if="status === 'found'">{{ foundPrefix }} <b>{{ parcelLabel }}</b></template>
        <template v-else-if="status === 'none'">An diesem Punkt wurde kein Flurstück gefunden.</template>
        <template v-else>{{ errorMessage }}</template>
      </span>
      <span v-if="status === 'found' && containing.length === 1" class="wert mono">{{ officialArea }}</span>
      <span v-if="tiles.length" class="kv-quelle">© GeoSN</span>
    </div>
  </div>
</template>

<script>
import { resolveParcel } from "../lib/api.js";
import { area, num } from "../lib/format.js";
import { pointInPolygon } from "../lib/geometry.js";
import { metresPerDegreeLon } from "../lib/projection.js";
import { fromScreen, tileCover, tileUrl, toScreen } from "../lib/routes.js";

export const PREVIEW_HEIGHT = 170;
/** A drag or a run of arrow presses is one question to the cadastre, not ten. */
export const LOOKUP_DELAY_MS = 350;
/* Zoom 18 is about 0,4 m per pixel at Saxon latitudes: an ordinary building
   plot is some 60 px across, with its neighbours and the street beside it —
   enough to see whether the point sits on the plot or on the road. An integer
   zoom keeps each tile at exactly 256 units, so the ground is never resampled. */
const ZOOM = 18;
const TILE_PIXELS = 256;
const FALLBACK_WIDTH = 480;
const KEY_STEP_M = 2;
const KEY_STEP_LARGE_M = 10;
const METRES_PER_DEGREE_LAT = metresPerDegreeLon(0);

const coordinateLabel = (lat, lon) => `${num(lat, 5)}° N · ${num(lon, 5)}° O`;
const numberOf = p => (p.nenner ? `${p.zaehler}/${p.nenner}` : String(p.zaehler ?? ""));
const ringsOf = geometry => {
  if (geometry?.type === "Polygon") return geometry.coordinates ?? [];
  if (geometry?.type === "MultiPolygon") return (geometry.coordinates ?? []).flat();
  return [];
};
const listed = items => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} und ${items.at(-1)}`);

export default {
  name: "CoordinatePreview",
  props: {
    lat: { type: Number, required: true },
    lon: { type: Number, required: true }
  },
  emits: ["move", "parcel"],
  data() {
    return {
      PREVIEW_HEIGHT,
      point: { lat: this.lat, lon: this.lon },
      // The frame stays put while the point moves: re-centring on every click
      // would slide the map out from under the pointer that is placing it.
      centre: { lat: this.lat, lon: this.lon },
      width: FALLBACK_WIDTH,
      moving: false,
      dragging: false,
      status: "loading",
      answer: null,
      errorMessage: "",
      reported: false
    };
  },
  computed: {
    frame() {
      // The border is inside the fixed height; user units are CSS pixels, so a
      // tile is drawn at its own size whatever the column is.
      return { width: this.width, height: PREVIEW_HEIGHT - 2 };
    },
    fit() {
      const scale = (TILE_PIXELS * 2 ** ZOOM) / (2 * Math.PI);
      const origin = toScreen([this.centre.lon, this.centre.lat], { scale, dx: 0, dy: 0 });
      return { scale, dx: this.frame.width / 2 - origin.x, dy: this.frame.height / 2 - origin.y };
    },
    tiles() {
      const cover = tileCover(this.fit, this.frame.width, this.frame.height);
      return cover ? cover.tiles.map(tile => ({ ...tile, href: tileUrl(tile) })) : [];
    },
    marker() {
      return toScreen([this.point.lon, this.point.lat], this.fit);
    },
    features() {
      return this.status === "found" && Array.isArray(this.answer?.features) ? this.answer.features : [];
    },
    /* The register is asked with a one-metre box and falls back to whatever
       the box touched, so a returned parcel is not proof the point is in it.
       Only a parcel that contains the point earns „liegt in“. */
    containing() {
      const here = { x: this.point.lon, y: this.point.lat };
      return this.features.filter(feature => {
        const [outer] = ringsOf(feature.geometry);
        return outer && pointInPolygon(here, outer.map(([x, y]) => ({ x, y })));
      });
    },
    named() {
      return this.containing.length === 1 ? this.containing : this.features;
    },
    foundPrefix() {
      return this.containing.length === 1 ? "Punkt liegt in" : "Punkt liegt an der Grenze von";
    },
    parcelLabel() {
      const parcels = this.named.map(feature => feature.properties ?? {});
      const districts = [...new Set(parcels.map(p => p.gemarkung).filter(Boolean))];
      if (districts.length === 1) return `${districts[0]} ${listed(parcels.map(numberOf))}`;
      return listed(parcels.map(p => [p.gemarkung, numberOf(p)].filter(Boolean).join(" ")));
    },
    officialArea() {
      return area(this.containing[0]?.properties?.flaeche_amtlich_m2);
    },
    outlines() {
      return this.features.map((feature, index) => ({
        key: feature.id ?? feature.properties?.kennzeichen ?? index,
        d: ringsOf(feature.geometry)
          .map(ring => `M${ring.map(c => {
            const p = toScreen(c, this.fit);
            return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
          }).join("L")}Z`)
          .join("")
      }));
    },
    mapLabel() {
      const where = coordinateLabel(this.point.lat, this.point.lon);
      return this.moving
        ? `Karte zum Verschieben des Punkts ${where}: klicken, ziehen oder Pfeiltasten`
        : `Kartenausschnitt um den Punkt ${where}`;
    }
  },
  watch: {
    lat() { this.followProps(); },
    lon() { this.followProps(); }
  },
  created() {
    // Bookkeeping, not state: nothing on screen reads these.
    this.ticket = 0;
    this.timer = null;
    this.observer = null;
  },
  mounted() {
    const root = this.$refs.root;
    if (root?.clientWidth) this.width = Math.round(root.clientWidth);
    if (typeof ResizeObserver !== "undefined") {
      this.observer = new ResizeObserver(([entry]) => {
        const measured = Math.round(entry.contentRect.width);
        if (measured > 0) this.width = measured;
      });
      this.observer.observe(root);
    }
    this.lookUp();
  },
  beforeUnmount() {
    this.observer?.disconnect();
    clearTimeout(this.timer);
    // Whatever is still in flight answers a component that is gone.
    this.ticket += 1;
  },
  methods: {
    followProps() {
      // The parent echoing our own `move` back is not a new place.
      if (this.lat === this.point.lat && this.lon === this.point.lon) return;
      this.point = { lat: this.lat, lon: this.lon };
      this.centre = { lat: this.lat, lon: this.lon };
      clearTimeout(this.timer);
      this.lookUp();
    },
    async lookUp() {
      const ticket = this.invalidate();
      try {
        const answer = await resolveParcel({ lat: this.point.lat, lon: this.point.lon });
        if (ticket !== this.ticket) return;
        this.answer = answer;
        this.status = Array.isArray(answer?.features) && answer.features.length ? "found" : "none";
        this.report(this.status === "found" ? answer : null);
      } catch (error) {
        if (ticket !== this.ticket) return;
        // A 404 from a point lookup is the cadastre's plain "nothing here";
        // its own sentence talks about parcel numbers nobody typed.
        if (error?.status === 404) {
          this.status = "none";
        } else {
          this.status = "error";
          this.errorMessage = error?.message ?? "";
        }
        this.report(null);
      }
    },
    /** Every answer still on its way is stale from here on. */
    invalidate() {
      this.ticket += 1;
      this.status = "loading";
      this.answer = null;
      this.errorMessage = "";
      if (this.reported) this.report(null);
      return this.ticket;
    },
    report(answer) {
      this.reported = Boolean(answer);
      this.$emit("parcel", answer);
    },
    commit() {
      this.$emit("move", { lat: this.point.lat, lon: this.point.lon });
      this.invalidate();
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.lookUp(), LOOKUP_DELAY_MS);
    },
    toggleMoving() {
      this.moving = !this.moving;
      this.dragging = false;
    },
    coordinateAt(event) {
      const rect = event.currentTarget?.getBoundingClientRect?.();
      if (!rect || !(rect.width > 0) || !(rect.height > 0)) return null;
      // `slice` scales by the larger ratio and centres the rest.
      const ratio = Math.max(rect.width / this.frame.width, rect.height / this.frame.height);
      const x = (event.clientX - rect.left - (rect.width - this.frame.width * ratio) / 2) / ratio;
      const y = (event.clientY - rect.top - (rect.height - this.frame.height * ratio) / 2) / ratio;
      const clamped = {
        x: Math.min(this.frame.width, Math.max(0, x)),
        y: Math.min(this.frame.height, Math.max(0, y))
      };
      const [lon, lat] = fromScreen(clamped, this.fit);
      return { lat, lon };
    },
    onPointerDown(event) {
      if (!this.moving || event.button > 0) return;
      const target = this.coordinateAt(event);
      if (!target) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      this.dragging = true;
      this.point = target;
      this.invalidate();
    },
    onPointerMove(event) {
      if (!this.dragging) return;
      const target = this.coordinateAt(event);
      if (target) this.point = target;
    },
    onPointerUp(event) {
      if (!this.dragging) return;
      this.dragging = false;
      const target = this.coordinateAt(event);
      if (target) this.point = target;
      this.commit();
    },
    onKeyDown(event) {
      if (!this.moving) return;
      if (event.key === "Escape") {
        this.moving = false;
        return;
      }
      const steps = { ArrowUp: [0, 1], ArrowDown: [0, -1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
      const step = steps[event.key];
      if (!step) return;
      event.preventDefault();
      const metres = event.shiftKey ? KEY_STEP_LARGE_M : KEY_STEP_M;
      this.point = {
        lat: this.point.lat + (step[1] * metres) / METRES_PER_DEGREE_LAT,
        lon: this.point.lon + (step[0] * metres) / metresPerDegreeLon(this.point.lat)
      };
      this.commit();
    }
  }
};
</script>

<style scoped>
.kartenvorschau{
  position: relative;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--w2b-line);
  border-radius: 10px;
  background: var(--w2b-map-ground);
}
.kartenvorschau__karte{ display: block; width: 100%; height: 100%; touch-action: pan-y; }
.kartenvorschau--verschieben .kartenvorschau__karte{ cursor: crosshair; touch-action: none; }
.kartenvorschau__karte:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: -3px; }
.kartenvorschau__grund{ opacity: .72; }
/* The web atlas only comes in daylight colours, and a near-white ground under
   a dark page is glare with the outline lost in it — the reason the site plan
   switches its vector style. A raster tile cannot switch, so it is turned. */
:root[data-theme="dark"] .kartenvorschau__grund{
  opacity: .8; filter: invert(1) hue-rotate(180deg) saturate(.55) brightness(.9);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]) .kartenvorschau__grund{
    opacity: .8; filter: invert(1) hue-rotate(180deg) saturate(.55) brightness(.9);
  }
}
.kartenvorschau__punkt{ filter: drop-shadow(0 1px 2px rgba(0,0,0,.35)); }

/* Status along the bottom, the button in the bottom-right corner as in the
   mock-up while the row has room for both; on a narrow column the button goes
   to the top-right corner instead of wrapping under the status, where the
   second row would sit on the parcel. */
.kartenvorschau{ container-type: inline-size; }
.kv-leiste{
  position: absolute; left: 8px; right: 156px; bottom: 8px;
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  pointer-events: none;
}
.kv-leiste > *{ pointer-events: auto; }
.wert{
  min-width: 0;
  font-size: 12.5px; line-height: 1.45;
  padding: 2px 7px; border-radius: 6px;
  border: 1px solid var(--w2b-line-faint);
  background: var(--w2b-surface); color: var(--w2b-graphite);
  box-shadow: var(--w2b-shadow);
}
.wert b{ font-weight: 600; color: var(--w2b-ink); }
.wert.mono{ font-family: var(--w2b-font-mono); white-space: nowrap; }
/* A long backend message may wrap, but only so far: it is laid over the map
   and must leave the point visible. */
.kv-status{
  overflow: hidden;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2;
}
.kv-status--fehler{ color: var(--w2b-map-violation); }
.kv-quelle{
  margin-left: auto;
  font-size: 10.5px; color: var(--w2b-muted);
  background: color-mix(in srgb, var(--w2b-surface) 80%, transparent);
  padding: 0 4px; border-radius: 4px;
  pointer-events: none;
}
.kv-verschieben{
  position: absolute; right: 8px; bottom: 8px;
  font: 600 13px var(--w2b-font-display);
  color: var(--w2b-primary);
  background: var(--w2b-surface);
  border: 1px solid var(--w2b-line-faint);
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  white-space: nowrap;
  text-decoration: underline; text-underline-offset: 3px;
  box-shadow: var(--w2b-shadow);
}
.kv-verschieben[aria-pressed="true"]{
  background: var(--w2b-primary); border-color: var(--w2b-primary);
  color: var(--w2b-primary-on); text-decoration: none;
}
.kv-verschieben:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: 2px; }
.kv-hinweis{
  position: absolute; left: 8px; top: 8px; margin: 0;
  font-size: var(--w2b-text-xs); color: var(--w2b-ink);
  background: var(--w2b-surface); border-radius: 6px; padding: 2px 7px;
  box-shadow: var(--w2b-shadow);
  pointer-events: none;
}
@container (max-width: 519px){
  .kv-leiste{ right: 8px; }
  .kv-verschieben{ top: 8px; bottom: auto; }
  .kv-hinweis{ max-width: calc(100% - 160px); }
}
</style>
