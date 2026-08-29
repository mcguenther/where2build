<template>
  <article class="karte tafel" :class="{ 'karte--gewaehlt': selected }">
    <label class="karte__wahl">
      <input type="checkbox" :checked="selected" :aria-label="`${plot.name} für den Vergleich auswählen`"
             @change="$emit('select', $event.target.checked)">
      Vergleich
    </label>

    <button type="button" class="karte__riss" :aria-label="`Lageplan ${plot.name} öffnen`" @click="$emit('open')">
      <SitePlan :plot="plot" :building="building" :width="300" :height="196" compact />
    </button>

    <div class="karte__rumpf">
      <h3><button type="button" class="karte__titel" @click="$emit('open')">{{ plot.name }}</button></h3>
      <p class="karte__ort">{{ plot.ort }} · Flst. {{ plot.flurstuecke.join(" · ") }}</p>

      <dl class="karte__werte">
        <dt>Fläche</dt><dd>{{ area(plot.officialArea) }}</dd>
        <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
        <dt>Je m²</dt><dd>{{ euroPerSqm(metrics.pricePerSqm) }}</dd>
        <dt v-if="firstDestination">{{ firstDestination.name }} · ÖPNV</dt>
        <dd v-if="firstDestination">{{ duration(firstDestinationTime) }}</dd>
      </dl>

      <div class="karte__marken">
        <span class="chip" :class="`chip--${metrics.deviationClass}`">
          <template v-if="metrics.deviation !== null">{{ percent(metrics.deviation) }} ggü. BRW</template>
          <template v-else>kein Kaufpreis</template>
        </span>
        <span class="chip chip--gut">{{ metrics.shapeClass }}</span>
      </div>
    </div>

    <div class="karte__fuss">
      <button type="button" class="knopf knopf--klein" @click="$emit('open')">Lageplan öffnen</button>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still knopf--klein" @click="$emit('remove')">Entfernen</button>
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
.karte{ display: flex; flex-direction: column; position: relative; }
.karte--gewaehlt{ border-color: var(--w2b-primaer); box-shadow: 0 0 0 1px var(--w2b-primaer); }

.karte__wahl{
  position: absolute; top: 10px; left: 10px; z-index: 2;
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px 4px 7px; border-radius: var(--w2b-radius-voll);
  background: var(--w2b-flaeche); border: 1px solid var(--w2b-linie); cursor: pointer;
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: 10.5px;
  letter-spacing: .06em; color: var(--w2b-graphit);
}
.karte__riss{
  display: block; width: 100%; padding: 0; border: 0; cursor: pointer;
  background: none; border-bottom: 1px solid var(--w2b-linie);
}
.karte__rumpf{ padding: var(--w2b-raum-3) var(--w2b-raum-4); display: flex; flex-direction: column; gap: var(--w2b-raum-2); flex: 1; }
.karte__titel{
  background: none; border: 0; padding: 0; cursor: pointer; font: inherit; color: inherit; text-align: left;
}
.karte__titel:hover{ color: var(--w2b-primaer); }
.karte__ort{ font-family: var(--w2b-daten); font-size: 10.5px; color: var(--w2b-gedaempft); margin-top: -4px; }
.karte__werte{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px var(--w2b-raum-3); font-size: var(--w2b-schrift-s); }
.karte__werte dt{ color: var(--w2b-graphit); }
.karte__werte dd{ margin: 0; text-align: right; font-family: var(--w2b-daten); font-variant-numeric: tabular-nums; }
.karte__marken{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; padding-top: var(--w2b-raum-1); }
.karte__fuss{ display: flex; gap: var(--w2b-raum-2); padding: var(--w2b-raum-3) var(--w2b-raum-4); border-top: 1px solid var(--w2b-linie-zart); }
</style>
