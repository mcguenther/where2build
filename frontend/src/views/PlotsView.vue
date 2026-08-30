<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Übersicht</p>
        <h1>Meine Grundstücke</h1>
        <p class="page-head__sub">
          Kandidaten in der Prüfung. Ein Klick auf die Karte öffnet den Lageplan; über die
          Auswahl links oben kommen mehrere nebeneinander in den Vergleich.
        </p>
      </div>
      <div class="spacer"></div>
      <button type="button" class="btn" @click="startWizard">Grundstück hinzufügen</button>
    </div>

    <p v-if="!backendUp" class="notice notice--error" role="alert">
      Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
      Seiten auslesen — gespeicherte Grundstücke bleiben aber sichtbar.
    </p>

    <div v-if="hasPlots" class="selection-bar panel no-print">
      <span class="selection-bar__count mono">{{ selectionLabel }}</span>
      <button type="button" class="btn btn--quiet btn--small" @click="selectAll">Alle auswählen</button>
      <button type="button" class="btn btn--quiet btn--small" @click="selectNone">Auswahl aufheben</button>
      <div class="spacer"></div>
      <button type="button" class="btn" :disabled="selected.length < 2" @click="compare">
        {{ selected.length < 2 ? "Vergleichen" : `${selected.length} vergleichen` }}
      </button>
    </div>

    <div class="card-grid">
      <PlotCard v-for="plot in state.data.plots" :key="plot.id"
                :plot="plot" :selected="isSelected(plot.id)"
                @open="open(plot.id)"
                @remove="remove(plot)"
                @select="on => toggleSelection(plot.id, on)" />

      <div class="empty-card">
        <h3>{{ hasPlots ? "Noch ein Kandidat?" : "Noch nichts in der Prüfung" }}</h3>
        <p>Link einer Anzeige, eingefügte Seite oder Gemarkung mit Flurstücksnummer —
          drei Wege hinein. Umriss und Fläche kommen aus dem Liegenschaftskataster.</p>
        <button type="button" class="btn btn--secondary" @click="startWizard">Grundstück hinzufügen</button>
      </div>
    </div>
  </div>
</template>

<script>
import PlotCard from "../components/PlotCard.vue";
import { state, toggleSelection, removePlot } from "../lib/store.js";
import { backendHealth } from "../lib/api.js";

export default {
  name: "PlotsView",
  components: { PlotCard },
  data() { return { state, backendUp: true }; },
  computed: {
    selected() { return state.data.selection; },
    hasPlots() { return state.data.plots.length > 0; },
    selectionLabel() {
      const n = this.selected.length;
      if (n === 0) return "Nichts ausgewählt";
      return n === 1 ? "1 Grundstück ausgewählt" : `${n} Grundstücke ausgewählt`;
    }
  },
  async created() {
    this.backendUp = Boolean(await backendHealth());
  },
  methods: {
    toggleSelection,
    isSelected(id) { return state.data.selection.includes(id); },
    open(id) { state.openPlotId = id; state.view = "plot"; window.scrollTo({ top: 0 }); },
    startWizard() { state.view = "wizard"; window.scrollTo({ top: 0 }); },
    compare() { state.view = "compare"; window.scrollTo({ top: 0 }); },
    selectAll() { state.data.selection = state.data.plots.map(p => p.id); },
    selectNone() { state.data.selection = []; },
    remove(plot) {
      const confirmed = window.confirm(`„${plot.name}“ aus der Liste entfernen? Der Stand dieses Grundstücks geht verloren.`);
      if (confirmed) removePlot(plot.id);
    }
  }
};
</script>

<style scoped>
.page-head{ display: flex; align-items: flex-end; gap: var(--w2b-space-4); flex-wrap: wrap; }
.page-head__sub{ margin-top: var(--w2b-space-2); color: var(--w2b-graphite); max-width: 62ch; font-size: var(--w2b-text-s); }
.selection-bar{ display: flex; align-items: center; gap: var(--w2b-space-3); flex-wrap: wrap; padding: var(--w2b-space-3) var(--w2b-space-4); }
.selection-bar__count{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.card-grid{ display: grid; grid-template-columns: repeat(auto-fill, minmax(292px, 1fr)); gap: var(--w2b-space-4); }
.empty-card{
  border: 1px dashed var(--w2b-line); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-space-3); padding: var(--w2b-space-6) var(--w2b-space-5); text-align: center; min-height: 260px;
}
.empty-card h3{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); }
.empty-card p{ color: var(--w2b-muted); font-size: var(--w2b-text-s); max-width: 32ch; }
</style>
