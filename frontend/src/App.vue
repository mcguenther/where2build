<template>
  <div class="huelle">
    <header class="kopfleiste nicht-drucken">
      <div class="bahn kopfleiste__inhalt">
        <button type="button" class="marke" @click="gehe('grundstuecke')" aria-label="Zur Übersicht">
          <svg viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
            <rect x="5.5" y="5.5" width="37" height="37" rx="3.5" fill="none"
                  stroke="var(--w2b-primaer)" stroke-width="3" />
            <rect x="14.5" y="14.5" width="19" height="19" rx="2"
                  fill="var(--w2b-sekundaer)" transform="rotate(15 24 24)" />
          </svg>
          <span class="marke__wort">where<b>2</b>build</span>
        </button>

        <nav class="orte" aria-label="Bereiche">
          <button v-for="o in orte" :key="o.id" type="button"
                  :aria-current="istHier(o.id) ? 'page' : null"
                  @click="gehe(o.id)">
            {{ o.name }}<span v-if="o.zahl !== null" class="orte__zahl">{{ o.zahl }}</span>
          </button>
        </nav>

        <div class="dehnen"></div>

        <div class="darstellung" role="group" aria-label="Darstellung">
          <button v-for="d in darstellungen" :key="d.id" type="button"
                  :aria-pressed="String(state.darstellung === d.id)"
                  @click="applyTheme(d.id)">{{ d.name }}</button>
        </div>
      </div>
    </header>

    <main class="bahn">
      <PlotsView        v-if="state.ansicht === 'grundstuecke'" />
      <WizardView       v-else-if="state.ansicht === 'aufnahme'" />
      <PlotView         v-else-if="state.ansicht === 'grundstueck'" />
      <CompareView      v-else-if="state.ansicht === 'vergleich'" />
      <HouseTypesView   v-else-if="state.ansicht === 'haustypen'" />
      <DestinationsView v-else-if="state.ansicht === 'ziele'" />
      <DataView         v-else-if="state.ansicht === 'daten'" />
    </main>

    <footer class="fussleiste nicht-drucken">
      <div class="bahn fussleiste__inhalt">
        <span>Amtliche Daten: © GeoSN, dl-de/by-2-0 · Bodenrichtwerte vom Gutachterausschuss</span>
        <span>Keine bauordnungsrechtliche Prüfung · keine Rechtsberatung</span>
      </div>
    </footer>

    <p class="druckfuss nur-drucken">
      where2build · Amtliche Daten © GeoSN, dl-de/by-2-0 ·
      Keine bauordnungsrechtliche Prüfung, keine Rechtsberatung.
    </p>
  </div>
</template>

<script>
import { state, load, applyTheme } from "./lib/store.js";
import PlotsView from "./views/PlotsView.vue";
import PlotView from "./views/PlotView.vue";
import WizardView from "./views/WizardView.vue";
import CompareView from "./views/CompareView.vue";
import HouseTypesView from "./views/HouseTypesView.vue";
import DestinationsView from "./views/DestinationsView.vue";
import DataView from "./views/DataView.vue";

export default {
  name: "App",
  components: { PlotsView, PlotView, WizardView, CompareView, HouseTypesView, DestinationsView, DataView },
  data() {
    return {
      state,
      darstellungen: [
        { id: "light", name: "Hell" },
        { id: "dark", name: "Dunkel" },
        { id: "system", name: "System" }
      ]
    };
  },
  computed: {
    orte() {
      return [
        { id: "grundstuecke", name: "Grundstücke", zahl: state.daten.grundstuecke.length },
        { id: "haustypen", name: "Haustypen", zahl: state.daten.haustypen.length },
        { id: "ziele", name: "Ziele", zahl: state.daten.ziele.length },
        { id: "daten", name: "Daten", zahl: null }
      ];
    }
  },
  created() { load(); },
  methods: {
    applyTheme,
    gehe(ort) {
      state.ansicht = ort;
      window.scrollTo({ top: 0, behavior: "instant" });
    },
    /** Detail, wizard and compare all live under "Grundstücke" in the navigation. */
    istHier(id) {
      const heim = ["grundstueck", "vergleich", "aufnahme"].includes(state.ansicht)
        ? "grundstuecke"
        : state.ansicht;
      return heim === id;
    }
  }
};
</script>

<style scoped>
.huelle{ min-height: 100vh; display: flex; flex-direction: column; }
main{ flex: 1; padding-top: var(--w2b-raum-5); }

.kopfleiste{ background: var(--w2b-flaeche); border-bottom: 1px solid var(--w2b-linie); }
.kopfleiste__inhalt{
  display: flex; align-items: center; gap: var(--w2b-raum-4) var(--w2b-raum-5);
  flex-wrap: wrap; padding-top: var(--w2b-raum-3); padding-bottom: var(--w2b-raum-3);
}

.marke{
  display: flex; align-items: center; gap: 10px;
  background: none; border: 0; padding: 0; cursor: pointer;
}
.marke__wort{
  font-family: var(--w2b-anzeige); font-weight: 700; font-size: 21px;
  letter-spacing: -.035em; color: var(--w2b-tinte);
}
.marke__wort b{ color: var(--w2b-sekundaer-text); }

.orte{ display: flex; gap: var(--w2b-raum-1); flex-wrap: wrap; min-width: 0; }
.orte button{
  display: flex; align-items: center; gap: 7px;
  background: none; border: 0; cursor: pointer;
  padding: 7px 13px; border-radius: var(--w2b-radius-s);
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: 14.5px;
  color: var(--w2b-graphit);
}
.orte button:hover{ background: var(--w2b-primaer-schleier); color: var(--w2b-tinte); }
.orte button[aria-current="page"]{ background: var(--w2b-primaer); color: var(--w2b-primaer-auf); }
.orte__zahl{
  font-family: var(--w2b-daten); font-size: 10.5px; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: var(--w2b-radius-voll);
  background: var(--w2b-linie-zart); color: var(--w2b-gedaempft);
}
.orte button[aria-current="page"] .orte__zahl{
  background: rgba(255,255,255,.18); color: var(--w2b-primaer-auf);
}

.darstellung{ display: flex; border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s); overflow: hidden; }
.darstellung button{
  background: var(--w2b-flaeche); border: 0; cursor: pointer; padding: 6px 11px;
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-xs);
  color: var(--w2b-gedaempft);
}
.darstellung button + button{ border-left: 1px solid var(--w2b-linie); }
.darstellung button[aria-pressed="true"]{ background: var(--w2b-primaer); color: var(--w2b-primaer-auf); }

.fussleiste{ border-top: 1px solid var(--w2b-linie); margin-top: var(--w2b-raum-8); }
.fussleiste__inhalt{
  display: flex; justify-content: space-between; gap: var(--w2b-raum-4); flex-wrap: wrap;
  padding-top: var(--w2b-raum-4); padding-bottom: var(--w2b-raum-4);
  font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft);
}

@media (max-width: 560px){
  .marke__wort{ font-size: 18px; }
  .orte button{ padding: 6px 10px; font-size: 13.5px; }
}
</style>
