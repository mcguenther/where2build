<template>
  <article class="plot-card panel" :class="{ 'plot-card--selected': selected }">
    <label class="plot-card__select no-print">
      <input type="checkbox" :checked="selected" :aria-label="`${plot.name} für den Vergleich auswählen`"
             @change="$emit('select', $event.target.checked)">
      Vergleich
    </label>

    <button type="button" class="plot-card__plan" :aria-label="`Lageplan ${plot.name} öffnen`" @click="$emit('open')">
      <SitePlan :plot="plot" :building="building" :width="300" :height="196" compact />
    </button>

    <div class="plot-card__body">
      <h3><button type="button" class="plot-card__title" @click="$emit('open')">{{ plot.name }}</button></h3>
      <!-- `ort` never existed; plotFromCadastre sets `municipality`. Reading the
           missing field left every card starting with a stray separator. -->
      <p class="plot-card__place">
        <template v-if="plot.municipality">{{ plot.municipality }} · </template>Flst. {{ plot.flurstuecke.join(" · ") }}
      </p>

      <dl class="plot-card__values">
        <dt>Fläche</dt><dd>{{ area(plot.officialArea) }}</dd>
        <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
        <dt>Je m²</dt><dd>{{ euroPerSqm(metrics.pricePerSqm) }}</dd>
        <dt v-if="firstDestination">{{ firstDestination.name }} · ÖPNV</dt>
        <dd v-if="firstDestination">{{ duration(firstDestinationTime) }}</dd>
      </dl>

      <div class="plot-card__chips">
        <span class="chip" :class="`chip--${metrics.deviationClass}`">
          <template v-if="metrics.deviation !== null">{{ percent(metrics.deviation) }} ggü. BRW</template>
          <template v-else>kein Kaufpreis</template>
        </span>
        <span class="chip chip--good">{{ metrics.shapeClass }}</span>
      </div>
    </div>

    <div class="plot-card__foot">
      <button type="button" class="btn btn--small" @click="$emit('open')">Lageplan öffnen</button>
      <div class="spacer"></div>
      <button type="button" class="btn btn--quiet btn--small" @click="$emit('remove')">Entfernen</button>
    </div>
  </article>
</template>

<script>
import SitePlan from "./SitePlan.vue";
import { plotMetrics } from "../lib/metrics.js";
import { placement, state } from "../lib/store.js";
import { area, euro, euroPerSqm, percent, duration } from "../lib/format.js";

export default {
  name: "PlotCard",
  components: { SitePlan },
  props: { plot: { type: Object, required: true }, selected: { type: Boolean, default: false } },
  emits: ["open", "remove", "select"],
  computed: {
    building() { return placement(this.plot); },
    metrics() { return plotMetrics(this.plot); },
    firstDestination() { return state.data.destinations[0] || null; },
    firstDestinationTime() {
      const m = this.firstDestination && this.plot.routes[this.firstDestination.id]?.modes?.transit;
      return m && m.erreichbar ? m.duration_s : null;
    }
  },
  methods: { area, euro, euroPerSqm, percent, duration }
};
</script>

<style scoped>
.plot-card{ display: flex; flex-direction: column; position: relative; }
.plot-card--selected{ border-color: var(--w2b-primary); box-shadow: 0 0 0 1px var(--w2b-primary); }

.plot-card__select{
  position: absolute; top: 10px; left: 10px; z-index: 2;
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px 4px 7px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-surface); border: 1px solid var(--w2b-line); cursor: pointer;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 10.5px;
  letter-spacing: .06em; color: var(--w2b-graphite);
}
.plot-card__plan{
  display: block; width: 100%; padding: 0; border: 0; cursor: pointer;
  background: none; border-bottom: 1px solid var(--w2b-line);
}
.plot-card__body{ padding: var(--w2b-space-3) var(--w2b-space-4); display: flex; flex-direction: column; gap: var(--w2b-space-2); flex: 1; }
.plot-card__title{
  background: none; border: 0; padding: 0; cursor: pointer; font: inherit; color: inherit; text-align: left;
}
.plot-card__title:hover{ color: var(--w2b-primary); }
.plot-card__place{ font-family: var(--w2b-font-mono); font-size: 10.5px; color: var(--w2b-muted); margin-top: -4px; }
.plot-card__values{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px var(--w2b-space-3); font-size: var(--w2b-text-s); }
.plot-card__values dt{ color: var(--w2b-graphite); }
.plot-card__values dd{ margin: 0; text-align: right; font-family: var(--w2b-font-mono); font-variant-numeric: tabular-nums; }
.plot-card__chips{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; padding-top: var(--w2b-space-1); }
.plot-card__foot{ display: flex; gap: var(--w2b-space-2); padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }
</style>
