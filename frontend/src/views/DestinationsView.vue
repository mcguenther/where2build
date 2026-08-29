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
          <div class="zielzeile__felder">
            <div class="feld">
              <label :for="`n-${ziel.id}`">Name</label>
              <input :id="`n-${ziel.id}`" type="text" v-model="ziel.name" @input="save">
            </div>
            <div class="feld">
              <label :for="`a-${ziel.id}`">Adresse</label>
              <input :id="`a-${ziel.id}`" type="text" v-model="ziel.adresse"
                     @input="adresseGeaendert(ziel)" placeholder="Straße Hausnummer, Ort">
            </div>
            <button type="button" class="knopf knopf--zweit knopf--klein"
                    :disabled="!ziel.adresse || laeuft === ziel.id" @click="nachschlagen(ziel)">
              {{ laeuft === ziel.id ? "Sucht…" : "Nachschlagen" }}
            </button>
            <button type="button" class="knopf knopf--still knopf--klein" @click="entfernen(ziel)">Entfernen</button>
          </div>

          <p v-if="fehler[ziel.id]" class="band band--fehler">{{ fehler[ziel.id] }}</p>

          <div v-else-if="treffer[ziel.id]" class="trefferliste">
            <p class="trefferliste__frage">Welcher Ort ist gemeint?</p>
            <button v-for="(t, i) in treffer[ziel.id]" :key="i" type="button"
                    class="trefferliste__wahl" @click="uebernehmen(ziel, t)">
              <span class="trefferliste__name">{{ t.name }}</span>
              <span class="trefferliste__wo">{{ t.beschreibung }}</span>
              <span class="trefferliste__koord">{{ t.lat.toFixed(5) }}, {{ t.lon.toFixed(5) }}</span>
            </button>
            <button type="button" class="knopf knopf--still knopf--klein" @click="verwerfen(ziel)">Abbrechen</button>
          </div>

          <p v-else-if="ziel.lat" class="zielzeile__stand">
            Verortet auf <strong>{{ ziel.treffer || "gewählte Koordinate" }}</strong>
            <span class="zart">{{ ziel.lat.toFixed(5) }}, {{ ziel.lon.toFixed(5) }}</span>
          </p>
          <p v-else class="zielzeile__stand zielzeile__stand--offen">
            Noch nicht verortet — ohne Koordinate lässt sich kein Weg berechnen.
          </p>
        </div>
      </div>
      <div v-else class="leer">
        <p>Noch keine Ziele. Ohne Ziele bleiben die Wege bei jedem Grundstück leer.</p>
        <button type="button" class="knopf knopf--zweit" @click="hinzufuegen">Erstes Ziel anlegen</button>
      </div>
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
import {
  state, addDestination, removeDestination, save, locateDestination, unlocateDestination
} from "../lib/store.js";
import { geokodieren } from "../lib/api.js";

export default {
  name: "DestinationsView",
  data() {
    return {
      laeuft: null,        // id of the destination currently being looked up
      treffer: {},         // id -> candidates awaiting a decision
      fehler: {}
    };
  },
  computed: {
    ziele() { return state.daten.ziele; },
    bezugspunkt() { return state.daten.grundstuecke.find(p => p.anker)?.anker || null; }
  },
  methods: {
    save,
    hinzufuegen() { addDestination(); },

    /** Editing the address invalidates the coordinate that was found for the
     *  old one — keeping it would route to the previous place in silence. */
    adresseGeaendert(ziel) {
      delete this.fehler[ziel.id];
      delete this.treffer[ziel.id];
      if (ziel.lat !== undefined) unlocateDestination(ziel.id);
      else save();
    },

    async nachschlagen(ziel) {
      this.laeuft = ziel.id;
      delete this.fehler[ziel.id];
      delete this.treffer[ziel.id];
      try {
        // The first plot's coordinate is the reference: destinations are
        // everyday places near the plots, and the geocoder is far more likely
        // to pick the right "Am Kirschberg" when it knows the region.
        const antwort = await geokodieren(ziel.adresse, this.bezugspunkt);
        const kandidaten = (antwort.treffer || []).filter(t => Number.isFinite(t.lat) && Number.isFinite(t.lon));
        if (!kandidaten.length) {
          this.fehler[ziel.id] = "Zu dieser Adresse wurde nichts gefunden. Bitte genauer schreiben, etwa mit Ort.";
        } else if (kandidaten.length === 1) {
          this.uebernehmen(ziel, kandidaten[0]);
        } else {
          // Several matches: the user decides. This geocoder is imprecise
          // enough that picking the first silently would be a wrong answer.
          this.treffer[ziel.id] = kandidaten.slice(0, 5);
        }
      } catch (fehler) {
        this.fehler[ziel.id] = fehler.message;
      } finally {
        this.laeuft = null;
      }
    },

    uebernehmen(ziel, wahl) {
      locateDestination(ziel.id, { lat: wahl.lat, lon: wahl.lon, treffer: wahl.name });
      delete this.treffer[ziel.id];
    },

    verwerfen(ziel) { delete this.treffer[ziel.id]; },

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
.zielzeile{ padding: var(--w2b-raum-3) var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie-zart); }
.zielzeile:last-child{ border-bottom: 0; }
.zielzeile__felder{ display: grid; grid-template-columns: 1fr 1.6fr auto auto; gap: var(--w2b-raum-3); align-items: end; }
@media (max-width: 680px){ .zielzeile__felder{ grid-template-columns: 1fr; } }
.zielzeile__stand{ margin-top: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.zielzeile__stand--offen{ color: var(--w2b-sekundaer-tief, var(--w2b-gedaempft)); }
.zielzeile__stand .zart{ font-family: var(--w2b-daten); margin-left: var(--w2b-raum-2); }
.trefferliste{ margin-top: var(--w2b-raum-3); display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
.trefferliste__frage{ font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); margin-bottom: 2px; }
.trefferliste__wahl{
  display: flex; gap: var(--w2b-raum-3); align-items: baseline; width: 100%; text-align: left;
  padding: var(--w2b-raum-2) var(--w2b-raum-3); border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s, 4px);
  background: var(--w2b-flaeche); cursor: pointer; font: inherit; font-size: var(--w2b-schrift-s); color: inherit;
}
.trefferliste__wahl:hover{ border-color: var(--w2b-primaer); }
.trefferliste__wo{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.trefferliste__koord{ margin-left: auto; font-family: var(--w2b-daten); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.leer{ padding: var(--w2b-raum-5); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); display: flex; flex-direction: column; align-items: flex-start; gap: var(--w2b-raum-3); }
</style>
