<template>
  <div class="stapel">
    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Für alle Grundstücke</p>
        <h1>Ziele</h1>
        <p class="seitenkopf__unter">
          Arbeit, Schule, Kita, Bahnhof — die Orte, zu denen von jedem Grundstück aus gerechnet
          wird. Eine Änderung hier wirkt sich auf alle Kandidaten aus.
        </p>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf" @click="hinzufuegen">Ziel hinzufügen</button>
    </div>

    <section class="tafel">
      <div class="tafel__kopf">
        <h3>Hinterlegte Ziele</h3><div class="dehnen"></div>
        <span class="chip">MOTIS · DELFI-GTFS</span>
      </div>
      <div v-if="ziele.length" class="zielliste">
        <div v-for="ziel in ziele" :key="ziel.id" class="zielzeile">
          <div class="feld">
            <label :for="`n-${ziel.id}`">Name</label>
            <input :id="`n-${ziel.id}`" type="text" v-model="ziel.name" @input="save">
          </div>
          <div class="feld">
            <label :for="`a-${ziel.id}`">Adresse</label>
            <input :id="`a-${ziel.id}`" type="text" v-model="ziel.adresse" @input="save">
          </div>
          <button type="button" class="knopf knopf--still knopf--klein" @click="entfernen(ziel)">Entfernen</button>
        </div>
      </div>
      <p v-else class="leer">Noch keine Ziele. Ohne Ziele bleibt der Bereich „Wege“ leer.</p>
    </section>

    <div class="notiz">
      <h4>Im Prototyp läuft das gegen Transitous</h4>
      <p>Öffentliche MOTIS-Instanz der Community — ideal, um diesen Bereich zu bauen, ohne
        vorher einen Server aufzusetzen. Für Produktionslast ungeeignet; die Betreiber weisen
        selbst auf begrenzte Ressourcen hin. Die Umstellung auf eine eigene Instanz ändert
        nur die Basis-Adresse.</p>
    </div>
  </div>
</template>

<script>
import { state, addDestination, removeDestination, save } from "../lib/store.js";

export default {
  name: "DestinationsView",
  computed: { ziele() { return state.daten.ziele; } },
  methods: {
    save,
    hinzufuegen() { addDestination(); },
    entfernen(ziel) {
      const sicher = window.confirm(`„${ziel.name}“ entfernen? Die berechneten Wege dorthin gehen bei allen Grundstücken verloren.`);
      if (sicher) removeDestination(ziel.id);
    }
  }
};
</script>

<style scoped>
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 66ch; }
.zielliste{ display: flex; flex-direction: column; }
.zielzeile{
  display: grid; grid-template-columns: 1fr 1.6fr auto; gap: var(--w2b-raum-3); align-items: end;
  padding: var(--w2b-raum-3) var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie-zart);
}
.zielzeile:last-child{ border-bottom: 0; }
@media (max-width: 680px){ .zielzeile{ grid-template-columns: 1fr; } }
.leer{ padding: var(--w2b-raum-4); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }
</style>
