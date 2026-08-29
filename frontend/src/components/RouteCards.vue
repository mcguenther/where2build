<template>
  <div v-if="ziele.length" class="wege-kartei">
    <article v-for="ziel in ziele" :key="ziel.id" class="weg-karte tafel">
      <div class="weg-karte__kopf">
        <h3>{{ ziel.name }}</h3>
        <span class="weg-karte__adresse">{{ ziel.treffer || ziel.adresse || "ohne Adresse" }}</span>
      </div>

      <svg v-if="bild(ziel)" viewBox="0 0 300 150" class="weg-karte__skizze"
           role="img" :aria-label="`Gefahrener Weg nach ${ziel.name}`">
        <rect x="0" y="0" width="300" height="150" fill="var(--w2b-karte-grund)" />
        <polyline v-for="linie in bild(ziel).linien" :key="linie.art" :points="linie.punkte"
                  fill="none" :stroke="MODUSFARBE[linie.art]"
                  :stroke-width="linie.art === bild(ziel).schnellster ? 3.4 : 2"
                  :opacity="linie.art === bild(ziel).schnellster ? 1 : 0.45"
                  stroke-linejoin="round" stroke-linecap="round" />
        <rect :x="bild(ziel).start.x - 4.5" :y="bild(ziel).start.y - 4.5" width="9" height="9" rx="2"
              fill="var(--w2b-karte-halo)" stroke="var(--w2b-karte-verstoss)" stroke-width="2.2" />
        <circle :cx="bild(ziel).ende.x" :cy="bild(ziel).ende.y" r="5.5"
                :fill="MODUSFARBE[bild(ziel).schnellster]" stroke="var(--w2b-karte-halo)" stroke-width="1.6" />
        <text x="293" y="143" text-anchor="end" class="weg-karte__quelle">{{ bild(ziel).massstab }}</text>
      </svg>

      <table v-if="modi(ziel).length" class="liste weg-karte__modi">
        <tbody>
          <tr v-for="m in modi(ziel)" :key="m.art">
            <td><span class="modus"><i :class="`modus__punkt modus__punkt--${m.art}`"></i>{{ m.name }}</span></td>
            <td class="zahl">{{ m.erreichbar ? duration(m.duration_s) : "—" }}</td>
            <td class="zahl weg-karte__notiz" :title="m.titel">{{ m.notiz }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="!ziel.lat" class="weg-karte__leer">
        Adresse noch nicht verortet — unter „Ziele“ nachschlagen lassen.
      </p>
      <p v-else-if="!plot.wege[ziel.id]" class="weg-karte__leer">Noch nicht berechnet.</p>
      <p v-else-if="!modi(ziel).some(m => m.erreichbar)" class="weg-karte__leer">
        Keine Verbindung gefunden — mit keinem Verkehrsmittel.
      </p>
      <p v-if="plot.wege[ziel.id] && plot.wege[ziel.id].berechnet_am" class="weg-karte__stand">
        Berechnet {{ datum(plot.wege[ziel.id].berechnet_am) }}<span v-if="plot.wege[ziel.id].quelle"> · {{ plot.wege[ziel.id].quelle }}</span>
      </p>
    </article>
  </div>
  <p v-else class="weg-karte__leer">Noch keine Ziele hinterlegt.</p>
</template>

<script>
import { state } from "../lib/store.js";
import { duration } from "../lib/format.js";
import { MODI, routeBounds, fitBounds, toPolyline, toScreen, coordinatesOf, fastestMode, groundWidth } from "../lib/routes.js";

/** One colour per mode, shared by the dots in the table and the drawn line,
 *  so the sketch says which mode actually wins for that destination. */
const MODUSFARBE = {
  car: "var(--w2b-graphit)",
  bike: "var(--w2b-sekundaer)",
  transit: "var(--w2b-primaer)"
};

export default {
  name: "RouteCards",
  props: { plot: { type: Object, required: true } },
  data() { return { MODUSFARBE }; },
  computed: {
    ziele() { return state.daten.ziele; }
  },
  methods: {
    duration,
    datum(iso) {
      const d = new Date(iso);
      return Number.isNaN(d.getTime())
        ? "unbekannt"
        : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
    },
    modi(ziel) {
      const weg = this.plot.wege[ziel.id];
      if (!weg) return [];
      return MODI.map(m => {
        const daten = weg.modi[m.art];
        if (!daten) return null;
        const notizen = [];
        if (Number.isInteger(daten.umstiege)) {
          notizen.push(daten.umstiege === 0 ? "ohne Umstieg" : `${daten.umstiege}× umsteigen`);
        }
        // The service's own sentence is written for a wide context; in a
        // 292 px card it wraps to four lines and pushes the times off screen.
        // The short form carries the same fact; the full one stays in the title.
        if (!daten.erreichbar) notizen.push("keine Verbindung");
        else if (daten.hinweis) notizen.push(daten.hinweis);
        return { ...m, ...daten, notiz: notizen.join(" · "), titel: daten.hinweis || "" };
      }).filter(Boolean);
    },
    /**
     * The drawn lines are the geometry MOTIS returned, nothing else. All modes
     * of one destination share a frame so their detours are comparable; a
     * destination without geometry gets no picture at all.
     */
    bild(ziel) {
      const weg = this.plot.wege[ziel.id];
      if (!weg) return null;
      const linien = MODI
        .map(m => ({ art: m.art, koordinaten: coordinatesOf(weg.modi[m.art]?.geometry) }))
        .filter(l => l.koordinaten);
      if (!linien.length) return null;

      const bounds = routeBounds(linien.map(l => l.koordinaten));
      const fit = fitBounds(bounds, 300, 150);
      if (!fit) return null;

      const schnellster = fastestMode(weg) || linien[0].art;
      const leitlinie = linien.find(l => l.art === schnellster) || linien[0];
      return {
        schnellster,
        // The fastest mode is drawn last so it lies on top of the others.
        linien: linien
          .map(l => ({ art: l.art, punkte: toPolyline(l.koordinaten, fit) }))
          .sort((a, b) => (a.art === schnellster) - (b.art === schnellster)),
        start: toScreen(leitlinie.koordinaten[0], fit),
        ende: toScreen(leitlinie.koordinaten[leitlinie.koordinaten.length - 1], fit),
        massstab: this.massstab(bounds)
      };
    },
    /** An honest scale bar beats a decorative one: the card is a few hundred
     *  metres wide for a school and tens of kilometres for a commute. */
    massstab(bounds) {
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
