<template>
  <div v-if="ziele.length" class="wege-kartei">
    <article v-for="(ziel, i) in ziele" :key="ziel.id" class="weg-karte tafel">
      <div class="weg-karte__kopf">
        <h3>{{ ziel.name }}</h3>
        <span class="weg-karte__adresse">{{ ziel.adresse }}</span>
      </div>

      <svg viewBox="0 0 300 150" class="weg-karte__skizze" role="img" :aria-label="`Kartenskizze der Route nach ${ziel.name}`">
        <rect x="0" y="0" width="300" height="150" fill="var(--w2b-karte-grund)" />
        <g stroke="var(--w2b-karte-nachbar)" stroke-width="3.2" opacity=".4" fill="none" stroke-linecap="round">
          <line v-for="(l, k) in netz(ziel, i).strassen" :key="`s${k}`" :x1="l[0]" :y1="l[1]" :x2="l[2]" :y2="l[3]" />
        </g>
        <g fill="var(--w2b-karte-nachbar)" opacity=".16">
          <rect v-for="(b, k) in netz(ziel, i).bloecke" :key="`b${k}`" :x="b[0]" :y="b[1]" :width="b[2]" :height="b[3]" rx="2" />
        </g>
        <polyline :points="netz(ziel, i).route" fill="none" :stroke="farbe(ziel)"
                  stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round" />
        <rect :x="netz(ziel, i).start[0] - 4.5" :y="netz(ziel, i).start[1] - 4.5" width="9" height="9" rx="2"
              fill="var(--w2b-karte-halo)" stroke="var(--w2b-karte-verstoss)" stroke-width="2.2" />
        <circle :cx="netz(ziel, i).ende[0]" :cy="netz(ziel, i).ende[1]" r="5.5"
                :fill="farbe(ziel)" stroke="var(--w2b-karte-halo)" stroke-width="1.6" />
        <text x="293" y="143" text-anchor="end" class="weg-karte__quelle">MOTIS · DELFI-GTFS</text>
      </svg>

      <table v-if="plot.wege[ziel.id]" class="liste weg-karte__modi">
        <tbody>
          <tr v-for="m in modi(ziel)" :key="m.name">
            <td><span class="modus"><i :class="`modus__punkt modus__punkt--${m.art}`"></i>{{ m.name }}</span></td>
            <td class="zahl">{{ minutes(m.dauer) }}</td>
            <td class="zahl weg-karte__notiz">{{ m.notiz }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="weg-karte__leer">Noch nicht berechnet.</p>
    </article>
  </div>
  <p v-else class="weg-karte__leer">Noch keine Ziele hinterlegt.</p>
</template>

<script>
import { state } from "../lib/store.js";
import { minutes } from "../lib/format.js";

/** One colour per mode, shared by the dots in the table and the route sketch,
 *  so the sketch says which mode actually wins for that destination. */
const MODUSFARBE = {
  auto: "var(--w2b-graphit)",
  rad: "var(--w2b-sekundaer)",
  oepnv: "var(--w2b-primaer)",
  komb: "var(--w2b-primaer-hell)"
};

export default {
  name: "RouteCards",
  props: { plot: { type: Object, required: true } },
  computed: {
    ziele() { return state.daten.ziele; }
  },
  methods: {
    minutes,
    /** The fastest mode decides the colour — that is information, not decoration. */
    schnellster(ziel) {
      const modi = this.modi(ziel);
      if (!modi.length) return "oepnv";
      return modi.reduce((a, b) => (b.dauer < a.dauer ? b : a)).art;
    },
    farbe(ziel) { return MODUSFARBE[this.schnellster(ziel)]; },
    /**
     * A schematic street grid with the route running along it. Derived from the
     * plot and destination ids so each sketch differs but never flickers.
     * MOTIS supplies the real geometry once the backend is wired up.
     */
    netz(ziel, index) {
      let seed = [...(this.plot.id + ziel.id)].reduce((a, c) => a + c.charCodeAt(0), index * 17);
      const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
      const ys = [0.2 + rnd() * 0.06, 0.44 + rnd() * 0.06, 0.68 + rnd() * 0.06];
      const xs = [0.1 + rnd() * 0.04, 0.3 + rnd() * 0.06, 0.55 + rnd() * 0.06, 0.84 + rnd() * 0.04];
      const strassen = [
        ...ys.map(y => [0, y * 150, 300, (y + (rnd() - 0.5) * 0.03) * 150]),
        ...xs.map(x => [x * 300, 0, (x + (rnd() - 0.5) * 0.02) * 300, 150]),
        [xs[0] * 300, ys[2] * 150, xs[3] * 300, ys[0] * 150]
      ];
      const bloecke = Array.from({ length: 7 }, () => [rnd() * 250, rnd() * 116, 26 + rnd() * 30, 18 + rnd() * 14]);
      const punkte = [[xs[0], 0.92], [xs[0], ys[2]], [xs[1], ys[2]], [xs[1], ys[1]],
                      [xs[2], ys[1]], [xs[2], ys[0]], [xs[3], ys[0]]];
      return {
        strassen, bloecke,
        route: punkte.map(([a, b]) => `${(a * 300).toFixed(1)},${(b * 150).toFixed(1)}`).join(" "),
        start: [xs[0] * 300, 0.92 * 150],
        ende: [xs[3] * 300, ys[0] * 150]
      };
    },
    modi(ziel) {
      const w = this.plot.wege[ziel.id];
      if (!w) return [];
      return [
        { art: "auto", name: "Auto", dauer: w[0], notiz: w[6] },
        { art: "rad", name: "Rad", dauer: w[1], notiz: "" },
        { art: "oepnv", name: "ÖPNV", dauer: w[2], notiz: w[5] },
        { art: "komb", name: "Kombiniert", dauer: w[3], notiz: w[4] }
      ];
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
.weg-karte__notiz{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.weg-karte__leer{ padding: var(--w2b-raum-4); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }
.modus{ display: inline-flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-s); }
.modus__punkt{ width: 11px; height: 11px; border-radius: 3px; flex: none; }
.modus__punkt--auto{ background: var(--w2b-graphit); }
.modus__punkt--rad{ background: var(--w2b-sekundaer); }
.modus__punkt--oepnv{ background: var(--w2b-primaer); }
.weg-karte__notiz{ text-align: right; }
.modus__punkt--komb{ background: linear-gradient(90deg, var(--w2b-sekundaer) 50%, var(--w2b-primaer) 50%); }
</style>
