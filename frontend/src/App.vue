<template>
  <div class="shell">
    <header class="site-header no-print">
      <div class="container site-header__inner">
        <button type="button" class="brand" @click="goTo('plots')" aria-label="Zur Übersicht">
          <svg viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
            <rect x="5.5" y="5.5" width="37" height="37" rx="3.5" fill="none"
                  stroke="var(--w2b-primary)" stroke-width="3" />
            <rect x="14.5" y="14.5" width="19" height="19" rx="2"
                  fill="var(--w2b-secondary)" transform="rotate(15 24 24)" />
          </svg>
          <span class="brand__word">where<b>2</b>build</span>
        </button>

        <nav class="main-nav" aria-label="Bereiche">
          <button v-for="s in sections" :key="s.id" type="button"
                  :aria-current="isCurrent(s.id) ? 'page' : null"
                  @click="goTo(s.id)">
            {{ s.name }}<span v-if="s.count !== null" class="main-nav__count">{{ s.count }}</span>
          </button>
        </nav>

        <div class="spacer"></div>

        <div class="theme-switch" role="group" aria-label="Darstellung">
          <button v-for="t in themes" :key="t.id" type="button"
                  :aria-pressed="String(state.theme === t.id)"
                  @click="applyTheme(t.id)">{{ t.name }}</button>
        </div>
      </div>
    </header>

    <main class="container">
      <PlotsView        v-if="state.view === 'plots'" />
      <WizardView       v-else-if="state.view === 'wizard'" />
      <PlotView         v-else-if="state.view === 'plot'" />
      <CompareView      v-else-if="state.view === 'compare'" />
      <HouseTypesView   v-else-if="state.view === 'houseTypes'" />
      <DestinationsView v-else-if="state.view === 'destinations'" />
      <DataView         v-else-if="state.view === 'data'" />
    </main>

    <footer class="site-footer no-print">
      <div class="container site-footer__inner">
        <span>Amtliche Daten: © GeoSN, dl-de/by-2-0 · Bodenrichtwerte vom Gutachterausschuss</span>
        <span>Keine bauordnungsrechtliche Prüfung · keine Rechtsberatung</span>
      </div>
    </footer>

    <p class="print-footer print-only">
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
.shell{ min-height: 100vh; display: flex; flex-direction: column; }
main{ flex: 1; padding-top: var(--w2b-space-5); }

.site-header{ background: var(--w2b-surface); border-bottom: 1px solid var(--w2b-line); }
.site-header__inner{
  display: flex; align-items: center; gap: var(--w2b-space-4) var(--w2b-space-5);
  flex-wrap: wrap; padding-top: var(--w2b-space-3); padding-bottom: var(--w2b-space-3);
}

.brand{
  display: flex; align-items: center; gap: 10px;
  background: none; border: 0; padding: 0; cursor: pointer;
}
.brand__word{
  font-family: var(--w2b-font-display); font-weight: 700; font-size: 21px;
  letter-spacing: -.035em; color: var(--w2b-ink);
}
.brand__word b{ color: var(--w2b-secondary-text); }

.main-nav{ display: flex; gap: var(--w2b-space-1); flex-wrap: wrap; min-width: 0; }
.main-nav button{
  display: flex; align-items: center; gap: 7px;
  background: none; border: 0; cursor: pointer;
  padding: 7px 13px; border-radius: var(--w2b-radius-s);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 14.5px;
  color: var(--w2b-graphite);
}
.main-nav button:hover{ background: var(--w2b-primary-veil); color: var(--w2b-ink); }
.main-nav button[aria-current="page"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.main-nav__count{
  font-family: var(--w2b-font-mono); font-size: 10.5px; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-line-faint); color: var(--w2b-muted);
}
.main-nav button[aria-current="page"] .main-nav__count{
  background: rgba(255,255,255,.18); color: var(--w2b-primary-on);
}

.theme-switch{ display: flex; border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); overflow: hidden; }
.theme-switch button{
  background: var(--w2b-surface); border: 0; cursor: pointer; padding: 6px 11px;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  color: var(--w2b-muted);
}
.theme-switch button + button{ border-left: 1px solid var(--w2b-line); }
.theme-switch button[aria-pressed="true"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }

.site-footer{ border-top: 1px solid var(--w2b-line); margin-top: var(--w2b-space-8); }
.site-footer__inner{
  display: flex; justify-content: space-between; gap: var(--w2b-space-4); flex-wrap: wrap;
  padding-top: var(--w2b-space-4); padding-bottom: var(--w2b-space-4);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}

@media (max-width: 560px){
  .brand__word{ font-size: 18px; }
  .main-nav button{ padding: 6px 10px; font-size: 13.5px; }
}
</style>
