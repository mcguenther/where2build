<template>
  <article class="karte tafel" :class="{ 'karte--gewaehlt': gewaehlt }">
    <label class="karte__wahl">
      <input type="checkbox" :checked="gewaehlt" :aria-label="`${plot.name} für den Vergleich auswählen`"
             @change="$emit('auswaehlen', $event.target.checked)">
      Vergleich
    </label>

    <button type="button" class="karte__riss" :aria-label="`Lageplan ${plot.name} öffnen`" @click="$emit('oeffnen')">
      <SitePlan :plot="plot" :koerper="koerper" :breite="300" :hoehe="196" kompakt />
    </button>

    <div class="karte__rumpf">
      <h3><button type="button" class="karte__titel" @click="$emit('oeffnen')">{{ plot.name }}</button></h3>
      <p class="karte__ort">{{ plot.ort }} · Flst. {{ plot.flurstuecke.join(" · ") }}</p>

      <dl class="karte__werte">
        <dt>Fläche</dt><dd>{{ area(plot.flaecheAmtlich) }}</dd>
        <dt>Kaufpreis</dt><dd>{{ euro(plot.kaufpreis) }}</dd>
        <dt>Je m²</dt><dd>{{ euroPerSqm(kennzahlen.jeQuadratmeter) }}</dd>
        <dt v-if="erstesZiel">{{ erstesZiel.name }} · ÖPNV</dt>
        <dd v-if="erstesZiel">{{ minutes(erstesZielZeit) }}</dd>
      </dl>

      <div class="karte__marken">
        <span class="chip" :class="`chip--${kennzahlen.abweichungKlasse}`">
          {{ percent(kennzahlen.abweichung) }} ggü. BRW
        </span>
        <span class="chip chip--gut">{{ kennzahlen.formklasse }}</span>
      </div>
    </div>

    <div class="karte__fuss">
      <button type="button" class="knopf knopf--klein" @click="$emit('oeffnen')">Lageplan öffnen</button>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still knopf--klein" @click="$emit('entfernen')">Entfernen</button>
    </div>
  </article>
</template>

<script>
import SitePlan from "./SitePlan.vue";
import { plotMetrics } from "../lib/metrics.js";
import { placement, state } from "../lib/store.js";
import { area, euro, euroPerSqm, percent, minutes } from "../lib/format.js";

export default {
  name: "PlotCard",
  components: { SitePlan },
  props: { plot: { type: Object, required: true }, gewaehlt: { type: Boolean, default: false } },
  emits: ["oeffnen", "entfernen", "auswaehlen"],
  computed: {
    koerper() { return placement(this.plot); },
    kennzahlen() { return plotMetrics(this.plot); },
    erstesZiel() { return state.daten.ziele[0] || null; },
    erstesZielZeit() {
      const w = this.erstesZiel && this.plot.wege[this.erstesZiel.id];
      return w ? w[2] : null;
    }
  },
  methods: { area, euro, euroPerSqm, percent, minutes }
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
