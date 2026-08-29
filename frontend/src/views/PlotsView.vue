<template>
  <div class="stapel">
    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Übersicht</p>
        <h1>Meine Grundstücke</h1>
        <p class="seitenkopf__unter">
          Kandidaten in der Prüfung. Ein Klick auf die Karte öffnet den Lageplan; über die
          Auswahl links oben kommen mehrere nebeneinander in den Vergleich.
        </p>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf" @click="aufnehmen">Grundstück hinzufügen</button>
    </div>

    <p v-if="!backendDa" class="band band--fehler" role="alert">
      Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
      Seiten auslesen — gespeicherte Grundstücke bleiben aber sichtbar.
    </p>

    <div v-if="hatGrundstuecke" class="auswahlleiste tafel nicht-drucken">
      <span class="auswahlleiste__zahl daten">{{ auswahlText }}</span>
      <button type="button" class="knopf knopf--still knopf--klein" @click="alle">Alle auswählen</button>
      <button type="button" class="knopf knopf--still knopf--klein" @click="keine">Auswahl aufheben</button>
      <div class="dehnen"></div>
      <button type="button" class="knopf" :disabled="gewaehlt.length < 2" @click="vergleichen">
        {{ gewaehlt.length < 2 ? "Vergleichen" : `${gewaehlt.length} vergleichen` }}
      </button>
    </div>

    <div class="kartei">
      <PlotCard v-for="plot in state.daten.grundstuecke" :key="plot.id"
                :plot="plot" :gewaehlt="istGewaehlt(plot.id)"
                @oeffnen="oeffnen(plot.id)"
                @entfernen="entfernen(plot)"
                @auswaehlen="an => toggleSelection(plot.id, an)" />

      <div class="leerkarte">
        <h3>{{ hatGrundstuecke ? "Noch ein Kandidat?" : "Noch nichts in der Prüfung" }}</h3>
        <p>Link einer Anzeige, eingefügte Seite oder Gemarkung mit Flurstücksnummer —
          drei Wege hinein. Umriss und Fläche kommen aus dem Liegenschaftskataster.</p>
        <button type="button" class="knopf knopf--zweit" @click="aufnehmen">Grundstück hinzufügen</button>
      </div>
    </div>
  </div>
</template>

<script>
import PlotCard from "../components/PlotCard.vue";
import { state, toggleSelection, removePlot } from "../lib/store.js";
import { backendZustand } from "../lib/api.js";

export default {
  name: "PlotsView",
  components: { PlotCard },
  data() { return { state, backendDa: true }; },
  computed: {
    gewaehlt() { return state.daten.auswahl; },
    hatGrundstuecke() { return state.daten.grundstuecke.length > 0; },
    auswahlText() {
      const n = this.gewaehlt.length;
      if (n === 0) return "Nichts ausgewählt";
      return n === 1 ? "1 Grundstück ausgewählt" : `${n} Grundstücke ausgewählt`;
    }
  },
  async created() {
    this.backendDa = Boolean(await backendZustand());
  },
  methods: {
    toggleSelection,
    istGewaehlt(id) { return state.daten.auswahl.includes(id); },
    oeffnen(id) { state.offenesGrundstueck = id; state.ansicht = "grundstueck"; window.scrollTo({ top: 0 }); },
    aufnehmen() { state.ansicht = "aufnahme"; window.scrollTo({ top: 0 }); },
    vergleichen() { state.ansicht = "vergleich"; window.scrollTo({ top: 0 }); },
    alle() { state.daten.auswahl = state.daten.grundstuecke.map(p => p.id); },
    keine() { state.daten.auswahl = []; },
    entfernen(plot) {
      const sicher = window.confirm(`„${plot.name}“ aus der Liste entfernen? Der Stand dieses Grundstücks geht verloren.`);
      if (sicher) removePlot(plot.id);
    }
  }
};
</script>

<style scoped>
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); max-width: 62ch; font-size: var(--w2b-schrift-s); }
.auswahlleiste{ display: flex; align-items: center; gap: var(--w2b-raum-3); flex-wrap: wrap; padding: var(--w2b-raum-3) var(--w2b-raum-4); }
.auswahlleiste__zahl{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.kartei{ display: grid; grid-template-columns: repeat(auto-fill, minmax(292px, 1fr)); gap: var(--w2b-raum-4); }
.leerkarte{
  border: 1px dashed var(--w2b-linie); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-raum-3); padding: var(--w2b-raum-6) var(--w2b-raum-5); text-align: center; min-height: 260px;
}
.leerkarte h3{ color: var(--w2b-graphit); font-size: var(--w2b-schrift-l); }
.leerkarte p{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); max-width: 32ch; }
</style>
