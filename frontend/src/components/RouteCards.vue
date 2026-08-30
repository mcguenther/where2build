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
      <p v-if="sketch(destination)" class="route-card__scale">{{ sketch(destination).scaleLabel }}</p>

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
import { MODES, routeBounds, fitBounds, toPolyline, toScreen, coordinatesOf, fastestMode, groundWidth } from "../lib/routes.js";

/** One colour per mode, shared by the dots in the table and the drawn line,
 *  so the sketch says which mode actually wins for that destination. */
const MODE_COLOURS = {
  car: "var(--w2b-graphite)",
  bike: "var(--w2b-secondary)",
  transit: "var(--w2b-primary)"
};

export default {
  name: "RouteCards",
  props: { plot: { type: Object, required: true } },
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
        if (!entry.erreichbar) notes.push("keine Verbindung");
        else if (entry.hinweis) notes.push(entry.hinweis);
        return { ...m, ...entry, note: notes.join(" · "), title: entry.hinweis || "" };
      }).filter(Boolean);
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
      return {
        fastest,
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
.route-card__modes td{ padding: 7px var(--w2b-space-4); white-space: nowrap; }
.route-card__note{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); text-align: right; white-space: normal; }
.route-card__why{
  padding: var(--w2b-space-2) var(--w2b-space-4) 0; margin: 0;
  color: var(--w2b-muted); font-size: var(--w2b-text-xs); line-height: 1.45;
}
.route-card__why b{ color: var(--w2b-ink); font-weight: 600; }
.route-card__empty{ padding: var(--w2b-space-4); color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.route-card__links{ padding: var(--w2b-space-2) var(--w2b-space-4) 0; margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.route-card__links a{ color: var(--w2b-primary); }
.route-card__links-note{ display: block; }
.route-card__computed{ padding: 0 var(--w2b-space-4) var(--w2b-space-3); color: var(--w2b-muted); font-size: var(--w2b-text-xs); font-family: var(--w2b-font-mono); }
.mode{ display: inline-flex; align-items: center; gap: var(--w2b-space-2); font-size: var(--w2b-text-s); }
.mode__dot{ width: 11px; height: 11px; border-radius: 3px; flex: none; }
.mode__dot--car{ background: var(--w2b-graphite); }
.mode__dot--bike{ background: var(--w2b-secondary); }
.mode__dot--transit{ background: var(--w2b-primary); }
</style>
