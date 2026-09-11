<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Übersicht</p>
        <h1>Meine Grundstücke</h1>
        <p class="page-head__sub">
          Kandidaten in der Prüfung. Ein Klick auf die Karte öffnet den Lageplan; „Vergleichen“
          schaltet die Auswahl frei, um mehrere nebeneinander zu legen.
        </p>
      </div>
      <div class="spacer"></div>
      <button v-if="hasPlots" type="button" class="btn btn--secondary compare-toggle no-print"
              :aria-pressed="String(comparing)" @click="toggleComparing">Vergleichen</button>
      <button type="button" class="btn" @click="startWizard">Grundstück hinzufügen</button>
    </div>

    <p v-if="!backendUp" class="notice notice--error" role="alert">
      Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
      Seiten auslesen; gespeicherte Grundstücke bleiben aber sichtbar.
    </p>

    <div v-if="comparing && hasPlots" class="selection-bar panel no-print">
      <span class="selection-bar__count mono" role="status" aria-live="polite">{{ selectionLabel }}</span>
      <button type="button" class="btn btn--quiet btn--small" @click="selectAll">Alle auswählen</button>
      <button type="button" class="btn btn--quiet btn--small" @click="selectNone">Auswahl aufheben</button>
      <div class="spacer"></div>
      <button type="button" class="btn btn--quiet btn--small" @click="toggleComparing">Fertig</button>
      <button type="button" class="btn" :disabled="selected.length < 2" @click="compare">
        {{ selected.length < 2 ? "Vergleich öffnen" : `${selected.length} vergleichen` }}
      </button>
    </div>

    <div class="card-grid">
      <PlotCard v-for="plot in state.data.plots" :key="plot.id"
                :plot="plot" :selected="isSelected(plot.id)" :selectable="comparing"
                @open="open(plot.id)"
                @remove="remove(plot)"
                @select="on => toggleSelection(plot.id, on)" />

      <div class="empty-card">
        <h3>{{ hasPlots ? "Noch ein Kandidat?" : "Noch nichts in der Prüfung" }}</h3>
        <p>Link einer Anzeige, eingefügte Seite oder Gemarkung mit Flurstücksnummer:
          drei Wege hinein. Umriss und Fläche kommen aus dem Liegenschaftskataster.</p>
        <button type="button" class="btn btn--secondary" @click="startWizard">Grundstück hinzufügen</button>
      </div>
    </div>
  </div>
</template>

<script>
import PlotCard from "../components/PlotCard.vue";
import { state, toggleSelection, removePlot, save } from "../lib/store.js";
import { backendHealth } from "../lib/api.js";
import { wizardStage } from "../router/stages.js";

export default {
  name: "PlotsView",
  components: { PlotCard },
  data() {
    return {
      state,
      backendUp: true,
      /* View state, not part of the document: opening a plot is the common
       * errand, so the checkboxes stay away until asked for. Not conditional on
       * there being a selection either — `addPlot` puts every new plot into it,
       * so anyone who has ever added one would land in comparison mode, which
       * is the state this button exists to get out of. */
      comparing: false
    };
  },
  computed: {
    selected() { return state.data.selection; },
    hasPlots() { return state.data.plots.length > 0; },
    selectionLabel() {
      const n = this.selected.length;
      if (n === 0) return "Nichts ausgewählt: mindestens zwei Grundstücke anhaken";
      if (n === 1) return "1 Grundstück ausgewählt: noch mindestens eines";
      return `${n} Grundstücke ausgewählt`;
    }
  },
  async created() {
    this.backendUp = Boolean(await backendHealth());
  },
  methods: {
    toggleSelection,
    isSelected(id) { return state.data.selection.includes(id); },
    open(id) { this.$router.push({ name: "plot", params: { id } }); },
    startWizard() { this.$router.push(wizardStage(0)); },
    compare() { this.$router.push({ name: "compare" }); },
    // Leaving the mode hides the checkboxes and nothing else. The selection is
    // stored data that /vergleich reads cold; discarding it here would throw
    // away work the user did not ask to undo — "Auswahl aufheben" is that ask.
    toggleComparing() { this.comparing = !this.comparing; },
    // Both must persist like the per-card checkbox does — /vergleich is a link
    // someone can open cold, and a selection that vanishes on reload is worse
    // than none, because the page then honestly reports "nothing selected".
    selectAll() {
      state.data.selection = state.data.plots.map(p => p.id);
      save();
    },
    selectNone() {
      state.data.selection = [];
      save();
    },
    remove(plot) {
      const confirmed = window.confirm(`„${plot.name}“ aus der Liste entfernen? Der Stand dieses Grundstücks geht verloren.`);
      if (confirmed) removePlot(plot.id);
    }
  }
};
</script>

<style scoped>
.page-head__sub{ max-width: 62ch; }
.compare-toggle[aria-pressed="true"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.compare-toggle[aria-pressed="true"]:hover:not(:disabled){ background: var(--w2b-primary-light); }
.selection-bar{ display: flex; align-items: center; gap: var(--w2b-space-3); flex-wrap: wrap; padding: var(--w2b-space-3) var(--w2b-space-4); }
.selection-bar__count{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.empty-card{
  border: 1px dashed var(--w2b-line); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-space-3); padding: var(--w2b-space-6) var(--w2b-space-5); text-align: center; min-height: 260px;
}
.empty-card h3{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); }
.empty-card p{ color: var(--w2b-muted); font-size: var(--w2b-text-s); max-width: 32ch; }
</style>
