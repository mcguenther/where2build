<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Für alle Grundstücke</p>
        <h1>Ziele</h1>
        <p class="page-head__sub">
          Arbeit, Schule, Kita, Bahnhof — die Orte, zu denen von jedem Grundstück aus gerechnet
          wird. Eine Änderung hier wirkt sich auf alle Kandidaten aus.
        </p>
      </div>
      <div class="spacer"></div>
      <button type="button" class="btn" @click="add">Ziel hinzufügen</button>
    </div>

    <section class="panel">
      <div class="panel__head">
        <h3>Hinterlegte Ziele</h3><div class="spacer"></div>
        <span class="chip">MOTIS · DELFI-GTFS</span>
      </div>
      <div v-if="destinations.length" class="destination-list">
        <div v-for="destination in destinations" :key="destination.id" class="destination-row">
          <div class="destination-row__fields">
            <div class="field">
              <label :for="`n-${destination.id}`">Name</label>
              <input :id="`n-${destination.id}`" type="text" v-model="destination.name" @input="save">
            </div>
            <div class="field">
              <label :for="`a-${destination.id}`">Adresse</label>
              <input :id="`a-${destination.id}`" type="text" v-model="destination.address"
                     @input="addressChanged(destination)" placeholder="Straße Hausnummer, Ort">
            </div>
            <button type="button" class="btn btn--secondary btn--small"
                    :disabled="!destination.address || busy === destination.id" @click="lookUp(destination)">
              {{ busy === destination.id ? "Sucht…" : "Nachschlagen" }}
            </button>
            <button type="button" class="btn btn--quiet btn--small" @click="remove(destination)">Entfernen</button>
          </div>

          <p v-if="errors[destination.id]" class="notice notice--error">{{ errors[destination.id] }}</p>

          <div v-else-if="matches[destination.id]" class="match-list">
            <p class="match-list__question">Welcher Ort ist gemeint?</p>
            <button v-for="(m, i) in matches[destination.id]" :key="i" type="button"
                    class="match-list__option" @click="accept(destination, m)">
              <span class="match-list__name">{{ m.name }}</span>
              <span class="match-list__where">{{ m.beschreibung }}</span>
              <span class="match-list__coords">{{ m.lat.toFixed(5) }}, {{ m.lon.toFixed(5) }}</span>
            </button>
            <button type="button" class="btn btn--quiet btn--small" @click="discard(destination)">Abbrechen</button>
          </div>

          <p v-else-if="destination.lat" class="destination-row__status">
            Verortet auf <strong>{{ destination.match || "gewählte Koordinate" }}</strong>
            <span class="faint">{{ destination.lat.toFixed(5) }}, {{ destination.lon.toFixed(5) }}</span>
          </p>
          <p v-else class="destination-row__status destination-row__status--open">
            Noch nicht verortet — ohne Koordinate lässt sich kein Weg berechnen.
          </p>
        </div>
      </div>
      <div v-else class="empty">
        <p>Noch keine Ziele. Ohne Ziele bleiben die Wege bei jedem Grundstück leer.</p>
        <button type="button" class="btn btn--secondary" @click="add">Erstes Ziel anlegen</button>
      </div>
    </section>

    <div class="callout">
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
import { geocode } from "../lib/api.js";

export default {
  name: "DestinationsView",
  data() {
    return {
      busy: null,       // id of the destination currently being looked up
      matches: {},      // id -> candidates awaiting a decision
      errors: {}
    };
  },
  computed: {
    destinations() { return state.data.destinations; },
    referencePoint() { return state.data.plots.find(p => p.anchor)?.anchor || null; }
  },
  methods: {
    save,
    add() { addDestination(); },

    /** Editing the address invalidates the coordinate that was found for the
     *  old one — keeping it would route to the previous place in silence. */
    addressChanged(destination) {
      delete this.errors[destination.id];
      delete this.matches[destination.id];
      if (destination.lat !== undefined) unlocateDestination(destination.id);
      else save();
    },

    async lookUp(destination) {
      this.busy = destination.id;
      delete this.errors[destination.id];
      delete this.matches[destination.id];
      try {
        // The first plot's coordinate is the reference: destinations are
        // everyday places near the plots, and the geocoder is far more likely
        // to pick the right "Am Kirschberg" when it knows the region.
        const response = await geocode(destination.address, this.referencePoint);
        const candidates = (response.treffer || []).filter(t => Number.isFinite(t.lat) && Number.isFinite(t.lon));
        if (!candidates.length) {
          this.errors[destination.id] = "Zu dieser Adresse wurde nichts gefunden. Bitte genauer schreiben, etwa mit Ort.";
        } else if (candidates.length === 1) {
          this.accept(destination, candidates[0]);
        } else {
          // Several matches: the user decides. This geocoder is imprecise
          // enough that picking the first silently would be a wrong answer.
          this.matches[destination.id] = candidates.slice(0, 5);
        }
      } catch (error) {
        this.errors[destination.id] = error.message;
      } finally {
        this.busy = null;
      }
    },

    accept(destination, choice) {
      locateDestination(destination.id, { lat: choice.lat, lon: choice.lon, match: choice.name });
      delete this.matches[destination.id];
    },

    discard(destination) { delete this.matches[destination.id]; },

    remove(destination) {
      const confirmed = window.confirm(`„${destination.name}“ entfernen? Die berechneten Wege dorthin gehen bei allen Grundstücken verloren.`);
      if (confirmed) removeDestination(destination.id);
    }
  }
};
</script>

<style scoped>
.page-head{ display: flex; align-items: flex-end; gap: var(--w2b-space-4); flex-wrap: wrap; }
.page-head__sub{ margin-top: var(--w2b-space-2); color: var(--w2b-graphite); font-size: var(--w2b-text-s); max-width: 66ch; }
.destination-list{ display: flex; flex-direction: column; }
.destination-row{ padding: var(--w2b-space-3) var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line-faint); }
.destination-row:last-child{ border-bottom: 0; }
.destination-row__fields{ display: grid; grid-template-columns: 1fr 1.6fr auto auto; gap: var(--w2b-space-3); align-items: end; }
@media (max-width: 680px){ .destination-row__fields{ grid-template-columns: 1fr; } }
.destination-row__status{ margin-top: var(--w2b-space-2); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.destination-row__status--open{ color: var(--w2b-secondary-deep, var(--w2b-muted)); }
.destination-row__status .faint{ font-family: var(--w2b-font-mono); margin-left: var(--w2b-space-2); }
.match-list{ margin-top: var(--w2b-space-3); display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
.match-list__question{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); margin-bottom: 2px; }
.match-list__option{
  display: flex; gap: var(--w2b-space-3); align-items: baseline; width: 100%; text-align: left;
  padding: var(--w2b-space-2) var(--w2b-space-3); border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s, 4px);
  background: var(--w2b-surface); cursor: pointer; font: inherit; font-size: var(--w2b-text-s); color: inherit;
}
.match-list__option:hover{ border-color: var(--w2b-primary); }
.match-list__where{ color: var(--w2b-muted); font-size: var(--w2b-text-xs); }
.match-list__coords{ margin-left: auto; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.empty{ padding: var(--w2b-space-5); color: var(--w2b-muted); font-size: var(--w2b-text-s); display: flex; flex-direction: column; align-items: flex-start; gap: var(--w2b-space-3); }
</style>
