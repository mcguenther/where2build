<template>
  <div class="stapel">
    <nav class="krume nicht-drucken" aria-label="Pfad">
      <button type="button" @click="back">Grundstücke</button>
      <span aria-hidden="true">›</span><span>Vergleich</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Nebeneinander</p>
        <h1>Vergleich</h1>
        <p class="seitenkopf__unter">{{ subtitle }}</p>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still nicht-drucken" @click="back">Auswahl ändern</button>
      <button type="button" class="knopf knopf--zweit nicht-drucken" @click="print">Drucken</button>
    </div>

    <section class="tafel">
      <div class="tafel__kopf"><h3>Kennzahlen</h3></div>
      <div class="tabelle-rollt">
        <table class="liste">
          <thead>
            <tr>
              <th>Grundstück</th><th class="zahl">Fläche</th><th class="zahl">Preis</th>
              <th class="zahl">Je m²</th><th class="zahl">Δ Bodenrichtwert</th><th>Form</th>
              <th v-if="firstDestination" class="zahl">{{ firstDestination.name }} ÖPNV</th>
              <th v-if="secondDestination" class="zahl">{{ secondDestination.name }} Rad</th>
              <th class="nicht-drucken"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in selectedPlots" :key="p.id">
              <td>
                <b>{{ p.name }}</b><br>
                <span class="zart daten">{{ p.gemarkung }} · Flst. {{ p.flurstuecke.join(" · ") }}</span>
              </td>
              <td class="zahl">{{ area(p.officialArea) }}</td>
              <td class="zahl">{{ euro(p.askingPrice) }}</td>
              <td class="zahl">{{ euroPerSqm(metrics(p).pricePerSqm) }}</td>
              <td class="zahl"><span class="chip" :class="`chip--${metrics(p).deviationClass}`">{{ percent(metrics(p).deviation) }}</span></td>
              <td>
                <span class="chip chip--gut">{{ metrics(p).shapeClass }}</span>
                <span class="zart daten"> {{ num(metrics(p).rectangularity, 2) }}</span>
              </td>
              <td v-if="firstDestination" class="zahl">{{ travelTime(p, firstDestination.id, "transit") }}</td>
              <td v-if="secondDestination" class="zahl">{{ travelTime(p, secondDestination.id, "bike") }}</td>
              <td class="nicht-drucken">
                <button type="button" class="knopf knopf--still knopf--klein" @click="open(p.id)">Öffnen</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="tafel">
      <div class="tafel__kopf">
        <h3>Gleicher Maßstab, gleiche Ausrichtung</h3>
        <div class="dehnen"></div><span v-if="scaleDenominator" class="chip">rund 1 : {{ scaleDenominator }}</span>
      </div>
      <div class="tafel__leib">
        <div class="risse">
          <figure v-for="p in selectedPlots" :key="p.id" class="riss">
            <button type="button" class="riss__knopf" :aria-label="`${p.name} öffnen`" @click="open(p.id)">
              <SitePlan :plot="p" :building="building(p)" :width="220" :height="280" :scale="sharedScale" compact />
            </button>
            <figcaption>
              <span>{{ p.gemarkung }}</span>
              <span class="daten">R {{ num(metrics(p).rectangularity, 2) }}</span>
            </figcaption>
          </figure>
        </div>
        <p class="fussnote">
          R = Rechteckigkeit: Polygonfläche geteilt durch die Fläche des kleinsten gedrehten
          Umschließungsrechtecks. Über 0,95 rechteckig, 0,85–0,95 fast, darunter komplex.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import { state, placement } from "../lib/store.js";
import { plotMetrics } from "../lib/metrics.js";
import { fitScale } from "../lib/geometry.js";
import { area, euro, euroPerSqm, percent, num, duration } from "../lib/format.js";

export default {
  name: "CompareView",
  components: { SitePlan },
  computed: {
    selectedPlots() { return state.data.plots.filter(p => state.data.selection.includes(p.id)); },
    /** The smallest of the individual fits, so the largest plot still fits and
     *  every drawing shares one scale — which is what the panel claims. */
    sharedScale() {
      if (!this.selectedPlots.length) return null;
      return Math.min(...this.selectedPlots.map(p => fitScale(p.polygon, 220, 280, 6)));
    },
    scaleDenominator() {
      // A CSS pixel is about 0.2646 mm; the drawing renders near its viewBox width.
      return this.sharedScale ? Math.round(1000 / (this.sharedScale * 0.26458) / 50) * 50 : null;
    },
    firstDestination() { return state.data.destinations[0] || null; },
    secondDestination() { return state.data.destinations[1] || null; },
    subtitle() {
      return this.selectedPlots.length
        ? `${this.selectedPlots.length} von ${state.data.plots.length} Kandidaten. Über „Auswahl ändern“ kommen andere herein oder heraus.`
        : "Nichts ausgewählt — auf der Übersicht Kandidaten ankreuzen.";
    }
  },
  methods: {
    area, euro, euroPerSqm, percent, num,
    metrics(plot) { return plotMetrics(plot); },
    building(plot) { return placement(plot); },
    /** One mode's travel time to one destination, or a dash when the routing
     *  service found nothing. Modes are addressed by name — the mockup's
     *  positional array is gone. */
    travelTime(plot, destinationId, mode) {
      const m = plot.routes[destinationId]?.modes?.[mode];
      return m && m.erreichbar ? duration(m.duration_s) : "—";
    },
    back() { state.view = "plots"; window.scrollTo({ top: 0 }); },
    open(id) { state.openPlotId = id; state.view = "plot"; window.scrollTo({ top: 0 }); },
    print() { window.print(); }
  }
};
</script>

<style scoped>
.krume{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.krume button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font: inherit; }
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 66ch; }
.zart{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.risse{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: var(--w2b-raum-4); }
.riss{ margin: 0; display: flex; flex-direction: column; gap: var(--w2b-raum-2); }
.riss__knopf{ padding: 0; border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s); overflow: hidden; background: none; cursor: pointer; }
.riss figcaption{ display: flex; justify-content: space-between; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-graphit); }
.fussnote{ margin-top: var(--w2b-raum-4); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
</style>
