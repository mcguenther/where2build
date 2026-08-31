<template>
  <div v-if="destinations.length" class="route-grid">
    <article v-for="destination in destinations" :key="destination.id" class="route-card panel">
      <div class="route-card__head">
        <h3>{{ destination.name }}</h3>
        <span class="route-card__address">{{ destination.match || destination.address || "ohne Adresse" }}</span>
      </div>

      <svg v-if="sketch(destination)" viewBox="0 0 300 150" class="route-card__sketch"
           role="img" :aria-label="`Gefahrener Weg nach ${destination.name}`">
        <rect x="0" y="0" width="300" height="150" fill="var(--w2b-map-ground)" />
        <!-- The ground: the same proxied WMS tiles the site plan uses, as plain
             <image> rather than a MapLibre instance. One card is a map; twenty
             cards are twenty WebGL contexts, which is past what a browser keeps
             alive. A tile that never arrives leaves the paper colour above. -->
        <image v-for="tile in sketch(destination).tiles" :key="tile.key" :href="tile.href"
               :x="tile.left" :y="tile.top" :width="tile.size" :height="tile.size"
               class="route-card__ground" preserveAspectRatio="none" />
        <polyline v-for="line in sketch(destination).lines" :key="line.mode" :points="line.points"
                  fill="none" :stroke="MODE_COLOURS[line.mode]"
                  :stroke-width="line.mode === sketch(destination).fastest ? 3.4 : 2"
                  :opacity="line.mode === sketch(destination).fastest ? 1 : 0.45"
                  stroke-linejoin="round" stroke-linecap="round" />
        <rect :x="sketch(destination).start.x - 4.5" :y="sketch(destination).start.y - 4.5" width="9" height="9" rx="2"
              fill="var(--w2b-map-halo)" stroke="var(--w2b-map-violation)" stroke-width="2.2" />
        <circle :cx="sketch(destination).end.x" :cy="sketch(destination).end.y" r="5.5"
                :fill="MODE_COLOURS[sketch(destination).fastest]" stroke="var(--w2b-map-halo)" stroke-width="1.6" />
      </svg>
      <!-- Below the drawing, not on it. Laid over the sketch — even on a
           semi-transparent strip — the caption ran through the start marker
           whenever the frame was wide. Nothing overlaps if nothing overlaps. -->
      <p v-if="sketch(destination)" class="route-card__scale">
        {{ sketch(destination).scaleLabel }}<span v-if="sketch(destination).tiles.length" class="route-card__credit"> · Karte GeoSN</span>
      </p>

      <table v-if="modes(destination).length" class="data-table route-card__modes">
        <tbody>
          <tr v-for="m in modes(destination)" :key="m.mode">
            <td><span class="mode"><i :class="`mode__dot mode__dot--${m.mode}`"></i>{{ m.name }}</span></td>
            <td class="num">{{ m.erreichbar ? duration(m.duration_s) : "—" }}</td>
            <td class="num route-card__note" :title="m.title">{{ m.note }}</td>
          </tr>
        </tbody>
      </table>

      <!-- A tooltip is not a display: invisible on a touch screen, in print, and
           to anyone who does not hover. The reason gets its own line, below the
           table where there is room for a sentence. -->
      <p v-for="m in unreachable(destination)" :key="`why-${m.mode}`" class="route-card__why">
        <b>{{ m.name }}:</b> {{ m.hinweis || "Der Routendienst hat keine Verbindung gefunden." }}
      </p>

      <!-- Which way to the first stop was taken, and on what numbers. A mode
           substituted in silence is a figure nobody can check. -->
      <p v-if="feeder(destination)" class="route-card__choice">
        <b>Anschluss:</b> {{ feeder(destination).name }} — {{ feeder(destination).reason }}
      </p>
      <p v-if="detour(destination)" class="route-card__choice route-card__choice--detour">
        {{ detour(destination) }}
      </p>

      <p v-if="!destination.lat" class="route-card__empty">
        Adresse noch nicht verortet — unter „Ziele“ nachschlagen lassen.
      </p>
      <p v-else-if="!plot.routes[destination.id]" class="route-card__empty">Noch nicht berechnet.</p>
      <p v-else-if="!modes(destination).some(m => m.erreichbar)" class="route-card__empty">
        Keine Verbindung gefunden — mit keinem Verkehrsmittel.
      </p>
      <!-- A drawn route is a claim until someone can open it elsewhere. -->
      <p v-if="canLinkOut(destination)" class="route-card__links nicht-drucken no-print">
        Nachprüfen:
        <a :href="osmLink(destination)" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>
        ·
        <a :href="googleLink(destination)" target="_blank" rel="noopener noreferrer">Google Maps</a>
        <span v-if="fastestMode(plot.routes[destination.id]) === 'transit'" class="route-card__links-note">
          — OpenStreetMap kennt keinen ÖPNV, dort als Autoroute.
        </span>
      </p>

      <p v-if="plot.routes[destination.id] && plot.routes[destination.id].calculatedAt" class="route-card__computed">
        Berechnet {{ formatDate(plot.routes[destination.id].calculatedAt) }}<span v-if="plot.routes[destination.id].source"> · {{ plot.routes[destination.id].source }}</span>
      </p>
    </article>
  </div>
  <p v-else class="route-card__empty">Noch keine Ziele hinterlegt.</p>
</template>

<script>
import { state } from "../lib/store.js";
import { duration } from "../lib/format.js";
import { openStreetMapRoute, googleMapsRoute } from "../lib/mapLinks.js";
import {
  MODES, ZUBRINGER, zubringerOf, routeBounds, fitBounds, toPolyline, toScreen,
  coordinatesOf, fastestMode, groundWidth, tileCover, tileUrl
} from "../lib/routes.js";

/** One colour per mode, shared by the dots in the table and the drawn line,
 *  so the sketch says which mode actually wins for that destination.
 *  The three ÖPNV variants share one colour on purpose: they are one row, and
 *  only ever one of them is present. */
const MODE_COLOURS = {
  car: "var(--w2b-graphite)",
  bike: "var(--w2b-secondary)",
  transit: "var(--w2b-primary)",
  bike_transit: "var(--w2b-primary)",
  car_transit: "var(--w2b-primary)"
};

/** The modes that end in a public transport service, in ladder order. */
const TRANSIT_MODES = ["transit", "bike_transit", "car_transit"];

export default {
  name: "RouteCards",
  props: {
    plot: { type: Object, required: true },
    /** The raster ground under each sketch. Off leaves the flat paper colour —
     *  and one fewer request per tile, which matters when printing a page of
     *  twenty cards. */
    backdrop: { type: Boolean, default: true }
  },
  data() { return { MODE_COLOURS }; },
  computed: {
    destinations() { return state.data.destinations; }
  },
  methods: {
    duration,
    formatDate(iso) {
      const d = new Date(iso);
      return Number.isNaN(d.getTime())
        ? "unbekannt"
        : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
    },
    fastestMode,
    canLinkOut(destination) {
      return Boolean(this.plot.anchor) && Number.isFinite(destination.lat) && Number.isFinite(destination.lon);
    },
    /** Link out in whichever mode came out fastest — that is the one shown. */
    linkMode(destination) {
      return fastestMode(this.plot.routes[destination.id]) || "car";
    },
    osmLink(destination) {
      return openStreetMapRoute(this.plot.anchor, destination, this.linkMode(destination));
    },
    googleLink(destination) {
      return googleMapsRoute(this.plot.anchor, destination, this.linkMode(destination));
    },

    /** Modes the service could not route — each gets a readable reason. */
    unreachable(destination) {
      return this.modes(destination).filter(m => !m.erreichbar);
    },
    modes(destination) {
      const route = this.plot.routes[destination.id];
      if (!route) return [];
      return MODES.map(m => {
        const entry = route.modes[m.mode];
        if (!entry) return null;
        const notes = [];
        if (Number.isInteger(entry.umstiege)) {
          notes.push(entry.umstiege === 0 ? "ohne Umstieg" : `${entry.umstiege}× umsteigen`);
        }
        // The service's own sentence is written for a wide context; in a
        // 292 px card it wraps to four lines and pushes the times off screen.
        // The short form carries the same fact; the full one stays in the title.
        // On a mode that *was* routed the sentence is not a failure but the
        // reason a feeder was chosen, and that belongs in `feeder()` below,
        // under the table where there is room for it.
        if (!entry.erreichbar) notes.push("keine Verbindung");
        return { ...m, ...entry, note: notes.join(" · "), title: entry.hinweis || "" };
      }).filter(Boolean);
    },
    /** The ÖPNV row that was actually routed for this destination, if any. */
    transitEntry(destination) {
      const route = this.plot.routes[destination.id];
      if (!route) return null;
      const mode = TRANSIT_MODES.find(m => route.modes[m]);
      return mode ? { mode, ...route.modes[mode] } : null;
    },

    /**
     * How the first stop is reached, and why — the sentence the backend wrote
     * when it made the choice. Without it a substituted mode is a number nobody
     * can check, so a routed ÖPNV row that carries no reason gets none written
     * for it here either.
     */
    feeder(destination) {
      const entry = this.transitEntry(destination);
      if (!entry || !entry.erreichbar || !entry.hinweis) return null;
      const label = MODES.find(m => m.mode === entry.mode);
      return { name: label ? label.name : entry.mode, reason: entry.hinweis };
    },

    /** What is pinned on this destination, in the words a picker uses. */
    zubringerLabel(destination) {
      const found = ZUBRINGER.find(z => z.wert === zubringerOf(destination));
      return found ? found.name : null;
    },

    /**
     * When the combination is slower than simply cycling or driving the whole
     * way, say so. The rows are all on screen, but the comparison is the point
     * of the card and it should not depend on the reader doing the subtraction.
     */
    detour(destination) {
      const entry = this.transitEntry(destination);
      const route = this.plot.routes[destination.id];
      if (!entry || !entry.erreichbar || !route) return null;
      const beaten = ["bike", "car"]
        .map(mode => ({ mode, ...(route.modes[mode] || {}) }))
        .filter(m => m.erreichbar && Number.isFinite(m.duration_s) && m.duration_s < entry.duration_s);
      if (!beaten.length) return null;
      const best = beaten.reduce((a, b) => (b.duration_s < a.duration_s ? b : a));
      const name = MODES.find(m => m.mode === best.mode).name;
      return `Durchgehend mit dem ${name === "Rad" ? "Rad" : "Auto"} sind es ${duration(best.duration_s)} — schneller als diese Kombination.`;
    },

    /**
     * The drawn lines are the geometry MOTIS returned, nothing else. All modes
     * of one destination share a frame so their detours are comparable; a
     * destination without geometry gets no picture at all.
     */
    sketch(destination) {
      const route = this.plot.routes[destination.id];
      if (!route) return null;
      const lines = MODES
        .map(m => ({ mode: m.mode, coordinates: coordinatesOf(route.modes[m.mode]?.geometry) }))
        .filter(l => l.coordinates);
      if (!lines.length) return null;

      const bounds = routeBounds(lines.map(l => l.coordinates));
      const fit = fitBounds(bounds, 300, 150);
      if (!fit) return null;

      const fastest = fastestMode(route) || lines[0].mode;
      const leading = lines.find(l => l.mode === fastest) || lines[0];
      const cover = this.backdrop ? tileCover(fit, 300, 150) : null;
      return {
        fastest,
        tiles: cover ? cover.tiles.map(t => ({ ...t, href: tileUrl(t) })) : [],
        // The fastest mode is drawn last so it lies on top of the others.
        lines: lines
          .map(l => ({ mode: l.mode, points: toPolyline(l.coordinates, fit) }))
          .sort((a, b) => (a.mode === fastest) - (b.mode === fastest)),
        start: toScreen(leading.coordinates[0], fit),
        end: toScreen(leading.coordinates[leading.coordinates.length - 1], fit),
        scaleLabel: this.scaleLabel(bounds)
      };
    },
    /** An honest scale bar beats a decorative one: the card is a few hundred
     *  metres wide for a school and tens of kilometres for a commute. */
    scaleLabel(bounds) {
      const m = groundWidth(bounds);
      if (!(m > 0)) return "";
      return m >= 1000
        ? `Bildbreite rund ${Math.round(m / 1000)} km`
        : `Bildbreite rund ${Math.max(10, Math.round(m / 10) * 10)} m`;
    }
  }
};
</script>

<style scoped>
.route-grid{ display: grid; grid-template-columns: repeat(auto-fill, minmax(292px, 1fr)); gap: var(--w2b-space-4); }
.route-card{ display: flex; flex-direction: column; }
/* Two lines high whatever the name does. A destination whose name wraps used
   to make its card taller than its neighbours, so the rows across the grid
   stopped lining up — which is the whole point of a comparison. */
.route-card__head{
  display: flex; align-items: baseline; gap: var(--w2b-space-2);
  padding: var(--w2b-space-3) var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line);
  min-height: 3.4rem;
}
.route-card__head h3{ overflow-wrap: anywhere; }
.route-card__head h3{ font-size: var(--w2b-text-l); }
.route-card__address{ font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted); margin-left: auto; text-align: right; }
.route-card__sketch{ display: block; width: 100%; height: auto; border-bottom: 1px solid var(--w2b-line); }
.route-card__scale{
  margin: 0; padding: 3px var(--w2b-space-4) 0; text-align: right;
  font-family: var(--w2b-font-mono); font-size: 9.5px; color: var(--w2b-muted);
}
/* `print.css` hides the sketch on paper — the drawing costs ink and says little
   at that size. The map credit goes with it: crediting a basemap on a sheet
   that carries none is a claim about something the reader cannot see. The rule
   lives here rather than in `print.css` because a scoped selector carries a
   `[data-v-…]` attribute and would win over a bare class there anyway. */
@media print {
  .route-card__credit{ display: none; }
}
.route-card__modes td{ padding: 7px var(--w2b-space-4); white-space: nowrap; }
/* The label may break. "Auto + ÖPNV" is two and a half times "ÖPNV", and with
   all three columns unbreakable the table's minimum width overran the 292 px
   card — the reason column was cut off at the edge. */
.route-card__modes td:first-child{ white-space: normal; }
/* `td` in the selector on purpose: `.route-card__modes td` sets `nowrap`, and a
   bare class loses to it — so the reason column never actually wrapped and the
   table pushed its last column off the edge of the card. */
.route-card__modes td.route-card__note{
  color: var(--w2b-muted); font-size: var(--w2b-text-xs); text-align: right; white-space: normal;
}
.route-card__why{
  padding: var(--w2b-space-2) var(--w2b-space-4) 0; margin: 0;
  color: var(--w2b-muted); font-size: var(--w2b-text-xs); line-height: 1.45;
}
.route-card__why b{ color: var(--w2b-ink); font-weight: 600; }
/* The chosen feeder and its numbers. Same voice as the reasons above it, and
   for the same reason: it has to be readable without hovering, on paper too. */
.route-card__choice{
  padding: var(--w2b-space-2) var(--w2b-space-4) 0; margin: 0;
  color: var(--w2b-muted); font-size: var(--w2b-text-xs); line-height: 1.45;
}
.route-card__choice b{ color: var(--w2b-ink); font-weight: 600; }
.route-card__choice--detour{ color: var(--w2b-secondary-text); }
/* The ground is held well back: the route lines are the subject, and unlike the
   site plan they carry no halo — a second polyline per line would double what
   the card draws for a picture 300 units wide. A washed-out map keeps the
   graphite, brass and loden strokes legible over any of it. */
.route-card__ground{ opacity: .55; }
.route-card__empty{ padding: var(--w2b-space-4); color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.route-card__links{ padding: var(--w2b-space-2) var(--w2b-space-4) 0; margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.route-card__links a{ color: var(--w2b-primary); }
.route-card__links-note{ display: block; }
.route-card__computed{ padding: 0 var(--w2b-space-4) var(--w2b-space-3); color: var(--w2b-muted); font-size: var(--w2b-text-xs); font-family: var(--w2b-font-mono); }
.mode{ display: inline-flex; align-items: center; gap: var(--w2b-space-2); font-size: var(--w2b-text-s); }
.mode__dot{ width: 11px; height: 11px; border-radius: 3px; flex: none; }
.mode__dot--car{ background: var(--w2b-graphite); }
.mode__dot--bike{ background: var(--w2b-secondary); }
.mode__dot--transit,
.mode__dot--bike_transit,
.mode__dot--car_transit{ background: var(--w2b-primary); }
</style>
