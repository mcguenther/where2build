<template>
  <div v-if="destinations.length" class="wege-kartei">
    <article v-for="destination in destinations" :key="destination.id" class="weg-karte tafel">
      <div class="weg-karte__kopf">
        <h3>{{ destination.name }}</h3>
        <span class="weg-karte__adresse">{{ destination.match || destination.address || "ohne Adresse" }}</span>
      </div>

      <svg v-if="sketch(destination)" viewBox="0 0 300 150" class="weg-karte__skizze"
           role="img" :aria-label="`Gefahrener Weg nach ${destination.name}`">
        <rect x="0" y="0" width="300" height="150" fill="var(--w2b-karte-grund)" />
        <polyline v-for="line in sketch(destination).lines" :key="line.mode" :points="line.points"
                  fill="none" :stroke="MODE_COLOURS[line.mode]"
                  :stroke-width="line.mode === sketch(destination).fastest ? 3.4 : 2"
                  :opacity="line.mode === sketch(destination).fastest ? 1 : 0.45"
                  stroke-linejoin="round" stroke-linecap="round" />
        <rect :x="sketch(destination).start.x - 4.5" :y="sketch(destination).start.y - 4.5" width="9" height="9" rx="2"
              fill="var(--w2b-karte-halo)" stroke="var(--w2b-karte-verstoss)" stroke-width="2.2" />
        <circle :cx="sketch(destination).end.x" :cy="sketch(destination).end.y" r="5.5"
                :fill="MODE_COLOURS[sketch(destination).fastest]" stroke="var(--w2b-karte-halo)" stroke-width="1.6" />
        <text x="293" y="143" text-anchor="end" class="weg-karte__quelle">{{ sketch(destination).scaleLabel }}</text>
      </svg>

      <table v-if="modes(destination).length" class="liste weg-karte__modi">
        <tbody>
          <tr v-for="m in modes(destination)" :key="m.mode">
            <td><span class="modus"><i :class="`modus__punkt modus__punkt--${m.mode}`"></i>{{ m.name }}</span></td>
            <td class="zahl">{{ m.erreichbar ? duration(m.duration_s) : "—" }}</td>
            <td class="zahl weg-karte__notiz" :title="m.title">{{ m.note }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="!destination.lat" class="weg-karte__leer">
        Adresse noch nicht verortet — unter „Ziele“ nachschlagen lassen.
      </p>
      <p v-else-if="!plot.routes[destination.id]" class="weg-karte__leer">Noch nicht berechnet.</p>
      <p v-else-if="!modes(destination).some(m => m.erreichbar)" class="weg-karte__leer">
        Keine Verbindung gefunden — mit keinem Verkehrsmittel.
      </p>
      <p v-if="plot.routes[destination.id] && plot.routes[destination.id].calculatedAt" class="weg-karte__stand">
        Berechnet {{ formatDate(plot.routes[destination.id].calculatedAt) }}<span v-if="plot.routes[destination.id].source"> · {{ plot.routes[destination.id].source }}</span>
      </p>
    </article>
  </div>
  <p v-else class="weg-karte__leer">Noch keine Ziele hinterlegt.</p>
</template>

<script>
import { state } from "../lib/store.js";
import { duration } from "../lib/format.js";
import { MODES, routeBounds, fitBounds, toPolyline, toScreen, coordinatesOf, fastestMode, groundWidth } from "../lib/routes.js";

/** One colour per mode, shared by the dots in the table and the drawn line,
 *  so the sketch says which mode actually wins for that destination. */
const MODE_COLOURS = {
  car: "var(--w2b-graphit)",
  bike: "var(--w2b-sekundaer)",
  transit: "var(--w2b-primaer)"
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
.wege-kartei{ display: grid; grid-template-columns: repeat(auto-fill, minmax(292px, 1fr)); gap: var(--w2b-raum-4); }
.weg-karte{ display: flex; flex-direction: column; }
.weg-karte__kopf{ display: flex; align-items: baseline; gap: var(--w2b-raum-2); padding: var(--w2b-raum-3) var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie); }
.weg-karte__kopf h3{ font-size: var(--w2b-schrift-l); }
.weg-karte__adresse{ font-family: var(--w2b-daten); font-size: 10px; color: var(--w2b-gedaempft); margin-left: auto; text-align: right; }
.weg-karte__skizze{ display: block; width: 100%; height: auto; border-bottom: 1px solid var(--w2b-linie); }
.weg-karte__quelle{ font-family: var(--w2b-daten); font-size: 8.5px; fill: var(--w2b-gedaempft); }
.weg-karte__modi td{ padding: 7px var(--w2b-raum-4); white-space: nowrap; }
.weg-karte__notiz{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); text-align: right; white-space: normal; }
.weg-karte__leer{ padding: var(--w2b-raum-4); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }
.weg-karte__stand{ padding: 0 var(--w2b-raum-4) var(--w2b-raum-3); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); font-family: var(--w2b-daten); }
.modus{ display: inline-flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-s); }
.modus__punkt{ width: 11px; height: 11px; border-radius: 3px; flex: none; }
.modus__punkt--car{ background: var(--w2b-graphit); }
.modus__punkt--bike{ background: var(--w2b-sekundaer); }
.modus__punkt--transit{ background: var(--w2b-primaer); }
</style>
