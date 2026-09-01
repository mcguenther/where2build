<template>
  <div v-if="destinations.length" class="route-grid" :style="gridStyle">
    <article v-for="destination in cards" :key="destination.id" class="route-card panel"
             :class="{ 'route-card--wide': layout.wide }">
      <div class="route-card__head">
        <h3>{{ destination.name }}</h3>
        <span class="route-card__address">{{ destination.match || destination.address || "ohne Adresse" }}</span>
      </div>

      <!-- The drawing and its caption on one side, everything that is read on
           the other. A single destination gets the whole row, and a picture
           that wide with a five-row table under it leaves the table floating in
           the middle of nothing. -->
      <div class="route-card__figure">
        <svg v-if="destination.sketch" :viewBox="destination.sketch.viewBox" class="route-card__sketch"
             role="img" :aria-label="`Gefahrener Weg nach ${destination.name}`">
          <rect x="0" y="0" :width="destination.sketch.frame.width" :height="destination.sketch.frame.height"
                fill="var(--w2b-map-ground)" />
          <!-- The ground: the same proxied WMS tiles the site plan uses, as plain
               <image> rather than a MapLibre instance. One card is a map; twenty
               cards are twenty WebGL contexts, which is past what a browser keeps
               alive. A tile that never arrives leaves the paper colour above. -->
          <image v-for="tile in destination.sketch.tiles" :key="tile.key" :href="tile.href"
                 :x="tile.left" :y="tile.top" :width="tile.size" :height="tile.size"
                 class="route-card__ground" preserveAspectRatio="none" />
          <polyline v-for="line in destination.sketch.lines" :key="line.mode" :points="line.points"
                    fill="none" :stroke="MODE_COLOURS[line.mode]"
                    :stroke-width="line.mode === destination.sketch.fastest ? destination.sketch.stroke : destination.sketch.stroke * 0.6"
                    :opacity="line.mode === destination.sketch.fastest ? 1 : 0.45"
                    stroke-linejoin="round" stroke-linecap="round" />
          <rect :x="destination.sketch.start.x - destination.sketch.marker" :y="destination.sketch.start.y - destination.sketch.marker"
                :width="destination.sketch.marker * 2" :height="destination.sketch.marker * 2" rx="2"
                fill="var(--w2b-map-halo)" stroke="var(--w2b-map-violation)" :stroke-width="destination.sketch.stroke * 0.65" />
          <circle :cx="destination.sketch.end.x" :cy="destination.sketch.end.y" :r="destination.sketch.marker * 1.2"
                  :fill="MODE_COLOURS[destination.sketch.fastest]" stroke="var(--w2b-map-halo)" :stroke-width="destination.sketch.stroke * 0.47" />
        </svg>
        <!-- Below the drawing, not on it. Laid over the sketch — even on a
             semi-transparent strip — the caption ran through the start marker
             whenever the frame was wide. Nothing overlaps if nothing overlaps. -->
        <p v-if="destination.sketch" class="route-card__scale">
          {{ destination.sketch.scaleLabel }}<span v-if="destination.sketch.tiles.length" class="route-card__credit"> · Karte GeoSN</span>
        </p>
      </div>

      <div class="route-card__detail">
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
      </div>
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
  coordinatesOf, fastestMode, frameGroundWidth, sketchFrame, tileCover, tileUrl
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

/**
 * How many cards share a row, and what shape their drawings then get.
 *
 * Three across is as narrow as a drawing may go; four destinations go two by
 * two rather than three and a lonely fourth. A card that has a row to itself
 * gets a frame it can fill: the same 2:1 picture that suits a 292 px column is
 * a strip of nothing across the full width.
 *
 * `units` is the drawing's width in SVG user units. It is not a layout size —
 * the grid column decides that — but a resolution: `tileCover` reads the zoom
 * off the frame, so a 300-unit drawing stretched over 1300 px of screen fetches
 * its ground four zoom steps too shallow and shows it blurred.
 *
 * The aspect bounds are the room the route's own proportions have to move in.
 * Wide cards are held to landscape on purpose: a route due north in a full-width
 * frame is drawn small and centred, with map either side of it, which is a
 * picture — a column 1300 px tall is not.
 */
function rowLayout(count) {
  // Alone in the row the card splits in two, so `units` is what is left for the
  // drawing beside the table, not the whole width of the shell.
  if (count <= 1) return { columns: 1, units: 880, minAspect: 1.5, maxAspect: 2.8, wide: true };
  if (count === 2 || count === 4) return { columns: 2, units: 620, minAspect: 1.1, maxAspect: 2.6, wide: false };
  return { columns: 3, units: 420, minAspect: 0.8, maxAspect: 2.2, wide: false };
}

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
    destinations() { return state.data.destinations; },
    /** How the row is divided, and therefore what shape a drawing gets. */
    layout() { return rowLayout(this.destinations.length); },
    gridStyle() {
      return {
        "--route-columns": this.layout.columns,
        // Below the wide breakpoint three across is too narrow to read.
        "--route-columns-mid": Math.min(this.layout.columns, 2)
      };
    },
    /**
     * The destinations with their drawing attached. A computed rather than a
     * method called eight times from the template: every call walked every
     * coordinate of every mode through the prop's proxy to work out the same
     * frame again.
     */
    cards() {
      return this.destinations.map(destination => ({ ...destination, sketch: this.sketchFor(destination) }));
    }
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
    sketchFor(destination) {
      const route = this.plot.routes[destination.id];
      if (!route) return null;
      const lines = MODES
        .map(m => ({ mode: m.mode, coordinates: coordinatesOf(route.modes[m.mode]?.geometry) }))
        .filter(l => l.coordinates);
      if (!lines.length) return null;

      const bounds = routeBounds(lines.map(l => l.coordinates));
      if (!bounds) return null;
      const { units, minAspect, maxAspect } = this.layout;
      const frame = sketchFrame(bounds, units, minAspect, maxAspect);
      const fit = fitBounds(bounds, frame.width, frame.height, frame.padding);
      if (!fit) return null;

      const fastest = fastestMode(route) || lines[0].mode;
      const leading = lines.find(l => l.mode === fastest) || lines[0];
      const cover = this.backdrop ? tileCover(fit, frame.width, frame.height) : null;
      return {
        fastest,
        frame,
        viewBox: `0 0 ${frame.width} ${frame.height}`,
        // Line and marker sizes are user units, so they have to follow the
        // frame — held at 3.4 they would be hairlines on a full-width card.
        stroke: Math.round((frame.width / 88) * 100) / 100,
        marker: Math.round((frame.width / 67) * 100) / 100,
        tiles: cover ? cover.tiles.map(t => ({ ...t, href: tileUrl(t) })) : [],
        // The fastest mode is drawn last so it lies on top of the others.
        lines: lines
          .map(l => ({ mode: l.mode, points: toPolyline(l.coordinates, fit) }))
          .sort((a, b) => (a.mode === fastest) - (b.mode === fastest)),
        start: toScreen(leading.coordinates[0], fit),
        end: toScreen(leading.coordinates[leading.coordinates.length - 1], fit),
        scaleLabel: this.scaleLabel(bounds, fit, frame.width)
      };
    },
    /** An honest scale bar beats a decorative one: the card is a few hundred
     *  metres wide for a school and tens of kilometres for a commute. The frame
     *  is measured, not the route's own box — a route due north spans no
     *  longitude at all and would be labelled ten metres wide. */
    scaleLabel(bounds, fit, width) {
      const m = frameGroundWidth(bounds, fit, width);
      if (!(m > 0)) return "";
      return m >= 1000
        ? `Bildbreite rund ${Math.round(m / 1000)} km`
        : `Bildbreite rund ${Math.max(10, Math.round(m / 10) * 10)} m`;
    }
  }
};
</script>

<style scoped>
/* The column count is set by the component, not by the available width: with
   two destinations the two cards share the row half and half, with one the card
   takes the row. `auto-fill` gave a lone destination a 292 px card against
   1000 px of nothing. Three across is the ceiling — below that a drawing is too
   narrow to tell a detour from a straight line. */
.route-grid{
  display: grid;
  grid-template-columns: repeat(var(--route-columns, 3), minmax(0, 1fr));
  gap: var(--w2b-space-4);
}
@media (max-width: 1040px){
  .route-grid{ grid-template-columns: repeat(var(--route-columns-mid, 2), minmax(0, 1fr)); }
}
@media (max-width: 680px){
  .route-grid{ grid-template-columns: minmax(0, 1fr); }
}
.route-card{ display: flex; flex-direction: column; }
.route-card__figure, .route-card__detail{ display: flex; flex-direction: column; min-width: 0; }
/* A card with the row to itself: drawing left, everything read on the right.
   The second column is capped, not shared — a table of five times does not get
   better at 600 px, it only leaves the drawing less. */
.route-card--wide{
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 400px); grid-template-rows: auto 1fr;
}
.route-card--wide .route-card__head{ grid-column: 1 / -1; }
.route-card--wide .route-card__figure{ border-right: 1px solid var(--w2b-line); }
.route-card--wide .route-card__sketch{ border-bottom: none; }
.route-card--wide .route-card__detail{ padding-top: var(--w2b-space-2); }
@media (max-width: 900px){
  .route-card--wide{ display: flex; flex-direction: column; }
  .route-card--wide .route-card__figure{ border-right: none; }
  .route-card--wide .route-card__sketch{ border-bottom: 1px solid var(--w2b-line); }
  .route-card--wide .route-card__detail{ padding-top: 0; }
}
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
/* The frame's proportions come from the route itself, so the height follows
   the width. The cap is for the extreme: a route that is nearly a straight line
   north in a narrow column would otherwise push the times off the screen. Past
   it the drawing keeps its shape and sits centred, which costs a little ground
   at the sides and never distorts a distance. */
.route-card__sketch{
  display: block; width: 100%; height: auto; max-height: min(58vh, 620px);
  border-bottom: 1px solid var(--w2b-line);
}
.route-card__scale{
  margin: 0; padding: 3px var(--w2b-space-4) 0; text-align: right;
  font-family: var(--w2b-font-mono); font-size: 9.5px; color: var(--w2b-muted);
}
/* The drawing does not go on paper — it costs ink and says little at that size.
   The whole figure goes with it, not only the picture: a caption reading
   "Bildbreite rund 22 km" under nothing is a measurement of nothing, and
   crediting a basemap the sheet does not carry is a claim about something the
   reader cannot see. The rule lives here rather than in `print.css` because a
   scoped selector carries a `[data-v-…]` attribute and would win over a bare
   class there anyway. */
@media print {
  .route-card__figure{ display: none; }
  .route-card--wide{ display: block; }
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
