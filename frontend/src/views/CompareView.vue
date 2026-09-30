<template>
  <div class="stack">
    <nav class="breadcrumb no-print" aria-label="Pfad">
      <RouterLink :to="{ name: 'plots' }">Grundstücke</RouterLink>
      <span aria-hidden="true">›</span><span>Vergleich</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Nebeneinander</p>
        <h1>Vergleich</h1>
        <p class="page-head__sub">{{ subtitle }}</p>
      </div>
      <div class="spacer"></div>
      <button type="button" class="btn btn--quiet no-print" @click="$router.push({ name: 'plots' })">Auswahl ändern</button>
      <button type="button" class="btn btn--secondary no-print" @click="print">Drucken</button>
    </div>

    <section class="panel">
      <div class="panel__head"><h3>Kennzahlen</h3></div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Grundstück</th><th class="num">Fläche</th><th class="num">Preis</th>
              <th class="num">Je m²</th><th class="num">Δ Bodenrichtwert</th><th>Form</th>
              <th v-if="firstDestination" class="num">{{ destinationName(firstDestination) }} ÖPNV</th>
              <th v-if="secondDestination" class="num">{{ destinationName(secondDestination) }} Rad</th>
              <th class="no-print"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in selectedPlots" :key="p.id">
              <td>
                <b>{{ p.name }}</b><br>
                <span class="faint mono">{{ p.gemarkung }} · Flst. {{ p.flurstuecke.join(" · ") }}</span>
              </td>
              <td class="num">{{ area(p.officialArea) }}</td>
              <td class="num">{{ euro(p.askingPrice) }}</td>
              <td class="num">{{ euroPerSqm(metrics(p).pricePerSqm) }}</td>
              <td class="num"><span class="chip" :class="`chip--${metrics(p).deviationClass}`">{{ percent(metrics(p).deviation) }}</span></td>
              <td>
                <span class="chip chip--good">{{ metrics(p).shapeClass }}</span>
                <span class="faint mono"> {{ num(metrics(p).rectangularity, 2) }}</span>
              </td>
              <td v-if="firstDestination" class="num">{{ travelTime(p, firstDestination.id, "transit") }}</td>
              <td v-if="secondDestination" class="num">{{ travelTime(p, secondDestination.id, "bike") }}</td>
              <td class="no-print">
                <button type="button" class="btn btn--quiet btn--small" @click="open(p.id)">Öffnen</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Gleicher Maßstab, gleiche Ausrichtung</h3>
        <div class="spacer"></div><span v-if="scaleDenominator" class="chip">rund 1 : {{ scaleDenominator }}</span>
      </div>
      <div class="panel__body">
        <div class="plan-figures">
          <figure v-for="p in selectedPlots" :key="p.id" class="plan-figure">
            <button type="button" class="plan-figure__button" :aria-label="`${p.name} öffnen`" @click="open(p.id)">
              <PlotThumbnail :plot="p" :width="frame.width" :height="frame.height" :scale="sharedScale" />
            </button>
            <figcaption>
              <span>{{ p.gemarkung }}</span>
              <span class="mono">R {{ num(metrics(p).rectangularity, 2) }}</span>
            </figcaption>
          </figure>
        </div>
        <p class="footnote">
          R = Rechteckigkeit: Polygonfläche geteilt durch die Fläche des kleinsten gedrehten
          Umschließungsrechtecks. Über 0,95 rechteckig, 0,85–0,95 fast, darunter komplex.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
import PlotThumbnail from "../components/PlotThumbnail.vue";
import { state, destinationName } from "../lib/store.js";
import { plotMetrics } from "../lib/metrics.js";
import { COMPARE_FRAME, sharedThumbnailScale } from "../lib/thumbnail.js";
import { area, euro, euroPerSqm, percent, num, duration } from "../lib/format.js";

export default {
  name: "CompareView",
  components: { PlotThumbnail },
  data() {
    return { frame: COMPARE_FRAME };
  },
  computed: {
    selectedPlots() { return state.data.plots.filter(p => state.data.selection.includes(p.id)); },
    /** The smallest of the individual fits, so the largest plot still fits and
     *  every drawing shares one scale — which is what the panel claims. */
    sharedScale() {
      return sharedThumbnailScale(this.selectedPlots, COMPARE_FRAME.width, COMPARE_FRAME.height);
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
        : "Nichts ausgewählt. Auf der Übersicht Kandidaten ankreuzen.";
    }
  },
  methods: {
    destinationName,
    area, euro, euroPerSqm, percent, num,
    metrics(plot) { return plotMetrics(plot); },
    /** One mode's travel time to one destination, or a dash when the routing
     *  service found nothing. Modes are addressed by name — the mockup's
     *  positional array is gone. */
    travelTime(plot, destinationId, mode) {
      const m = plot.routes[destinationId]?.modes?.[mode];
      return m && m.erreichbar ? duration(m.duration_s) : "—";
    },
    open(id) { this.$router.push({ name: "plot", params: { id } }); },
    print() { window.print(); }
  }
};
</script>

<style scoped>
.faint{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
.plan-figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: var(--w2b-space-4); }
.plan-figure{ margin: 0; display: flex; flex-direction: column; gap: var(--w2b-space-2); }
.plan-figure__button{ padding: 0; border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); overflow: hidden; background: none; cursor: pointer; }
.plan-figure figcaption{ display: flex; justify-content: space-between; gap: var(--w2b-space-2); font-size: var(--w2b-text-xs); color: var(--w2b-graphite); }
.footnote{ margin-top: var(--w2b-space-4); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
</style>
