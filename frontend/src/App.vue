<template>
  <div class="huelle">
    <header class="kopfleiste nicht-drucken">
      <div class="bahn kopfleiste__inhalt">
        <button type="button" class="marke" @click="goTo('plots')" aria-label="Zur Übersicht">
          <svg viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
            <rect x="5.5" y="5.5" width="37" height="37" rx="3.5" fill="none"
                  stroke="var(--w2b-primaer)" stroke-width="3" />
            <rect x="14.5" y="14.5" width="19" height="19" rx="2"
                  fill="var(--w2b-sekundaer)" transform="rotate(15 24 24)" />
          </svg>
          <span class="marke__wort">where<b>2</b>build</span>
        </button>

        <nav class="orte" aria-label="Bereiche">
          <button v-for="s in sections" :key="s.id" type="button"
                  :aria-current="isCurrent(s.id) ? 'page' : null"
                  @click="goTo(s.id)">
            {{ s.name }}<span v-if="s.count !== null" class="orte__zahl">{{ s.count }}</span>
          </button>
        </nav>

        <div class="dehnen"></div>

        <div class="darstellung" role="group" aria-label="Darstellung">
          <button v-for="t in themes" :key="t.id" type="button"
                  :aria-pressed="String(state.theme === t.id)"
                  @click="applyTheme(t.id)">{{ t.name }}</button>
        </div>
      </div>
    </header>

    <main class="bahn">
      <PlotsView        v-if="state.view === 'plots'" />
      <WizardView       v-else-if="state.view === 'wizard'" />
      <PlotView         v-else-if="state.view === 'plot'" />
      <CompareView      v-else-if="state.view === 'compare'" />
      <HouseTypesView   v-else-if="state.view === 'houseTypes'" />
      <DestinationsView v-else-if="state.view === 'destinations'" />
      <DataView         v-else-if="state.view === 'data'" />
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
      themes: [
        { id: "light", name: "Hell" },
        { id: "dark", name: "Dunkel" },
        { id: "system", name: "System" }
      ]
    };
  },
  computed: {
    sections() {
      return [
        { id: "plots", name: "Grundstücke", count: state.data.plots.length },
        { id: "houseTypes", name: "Haustypen", count: state.data.houseTypes.length },
        { id: "destinations", name: "Ziele", count: state.data.destinations.length },
        { id: "data", name: "Daten", count: null }
      ];
    }
  },
  created() { load(); },
  methods: {
    applyTheme,
    goTo(id) {
      state.view = id;
      window.scrollTo({ top: 0, behavior: "instant" });
    },
    /** Detail, wizard and compare all live under "Grundstücke" in the navigation. */
    isCurrent(id) {
      const home = ["plot", "compare", "wizard"].includes(state.view) ? "plots" : state.view;
      return home === id;
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
