<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Für alle Grundstücke</p>
        <h1>Ziele</h1>
        <p class="page-head__sub">
          Arbeit, Schule, Kita, Bahnhof: die Orte, zu denen von jedem Grundstück aus gerechnet
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

          <!-- Located and not open for editing: a filed record, not a form. -->
          <div v-if="isSaved(destination)" class="destination-record">
            <div class="destination-record__head">
              <h4 class="destination-record__name">{{ displayName(destination) }}</h4>
              <span class="chip chip--good">Gespeichert</span>
              <div class="spacer"></div>
              <button type="button" class="btn btn--secondary btn--small no-print"
                      :aria-label="`„${displayName(destination)}“ bearbeiten`"
                      @click="beginEdit(destination)">
                <span aria-hidden="true">✎</span> Bearbeiten
              </button>
              <button type="button" class="btn btn--quiet btn--small no-print"
                      @click="remove(destination)">Entfernen</button>
            </div>
            <dl class="value-list">
              <dt>Adresse</dt><dd>{{ destination.address || "—" }}</dd>
              <dt>Verortet auf</dt>
              <dd>
                {{ destination.match || "gewählte Koordinate" }}
                <span class="faint">{{ destination.lat.toFixed(5) }}, {{ destination.lon.toFixed(5) }}</span>
              </dd>
            </dl>
          </div>

          <template v-else>
            <div class="destination-row__fields">
              <div class="field">
                <label :for="`n-${destination.id}`">Name</label>
                <input :id="`n-${destination.id}`" type="text" placeholder="Neues Ziel"
                       :value="draft(destination).name"
                       @input="setName(destination, $event.target.value)"
                       @keydown.enter.exact.prevent="lookUpByEnter(destination)">
              </div>
              <div class="field">
                <label :for="`a-${destination.id}`">Adresse</label>
                <input :id="`a-${destination.id}`" type="text" placeholder="Straße Hausnummer, Ort"
                       :value="draft(destination).address"
                       @input="setAddress(destination, $event.target.value)"
                       @keydown.enter.exact.prevent="lookUpByEnter(destination)">
              </div>
              <button type="button" class="btn btn--secondary btn--small"
                      :disabled="!draft(destination).address || busy === destination.id"
                      @click="lookUp(destination)">
                {{ busy === destination.id ? "Sucht…" : "Nachschlagen" }}
              </button>
              <button type="button" class="btn btn--quiet btn--small"
                      @click="remove(destination)">Entfernen</button>
            </div>

            <!-- What the change costs, before it takes effect rather than after. -->
            <p v-if="addressEdited(destination)" class="notice notice--warn" role="status">
              <!-- One span: `.notice` is a flex row, and a bare <strong> beside
                   the text becomes a column of its own on a narrow screen. -->
              <span>
                Mit „Fertig“ wird die Verortung auf
                <strong>{{ destination.match || "die gewählte Koordinate" }}</strong>
                verworfen, und mit ihr alle bereits berechneten Wege zu diesem Ziel bei allen
                Grundstücken. „Abbrechen“ lässt beides stehen.
              </span>
            </p>

            <div v-if="edits[destination.id]" class="destination-row__actions no-print">
              <button type="button" class="btn btn--small" @click="commit(destination)">Fertig</button>
              <button type="button" class="btn btn--quiet btn--small"
                      @click="cancel(destination)">Abbrechen</button>
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

            <p v-else-if="!isLocated(destination)" class="destination-row__status destination-row__status--open">
              Noch nicht verortet. Ohne Koordinate lässt sich kein Weg berechnen.
            </p>
          </template>

          <!-- How to reach the first stop. A preference about the next
               calculation, not a record of what this place is, so it stays
               adjustable without opening the record for editing — and changing
               it destroys nothing that was already computed. -->
          <div class="feeder no-print">
            <label :for="`z-${destination.id}`">Zubringer zum ÖPNV</label>
            <select :id="`z-${destination.id}`" :value="zubringerOf(destination)"
                    @change="setZubringer(destination, $event.target.value)">
              <option v-for="z in ZUBRINGER" :key="z.wert" :value="z.wert">{{ z.name }}</option>
            </select>
            <p class="feeder__hint">
              <template v-if="zubringerOf(destination) === 'automatic'">
                Rad und Fußweg werden beide gerechnet; das Rad gewinnt ab zehn Minuten Fußweg
                zur ersten Haltestelle oder wenn es die Reise deutlich verkürzt. Das Auto
                kommt erst ab zehn Minuten Radweg dazu, und nur, wenn es schneller ist.
              </template>
              <template v-else>
                Fest eingestellt. „Wege berechnen“ auf der Grundstücksseite übernimmt es.
              </template>
            </p>
          </div>
        </div>
      </div>
      <div v-else class="empty">
        <p>Noch keine Ziele. Ohne Ziele bleiben die Wege bei jedem Grundstück leer.</p>
        <button type="button" class="btn btn--secondary" @click="add">Erstes Ziel anlegen</button>
      </div>
    </section>

    <div v-if="publicRouter" class="callout">
      <h4>Die Wege berechnet Transitous</h4>
      <p>Öffentliche MOTIS-Instanz der Community. Für Produktionslast ungeeignet; die Betreiber
        weisen selbst auf begrenzte Ressourcen hin. Der mitgelieferte Docker-Stapel bringt eine
        eigene Instanz mit.</p>
    </div>
  </div>
</template>

<script>
import {
  state, addDestination, removeDestination, save, locateDestination, unlocateDestination,
  destinationName
} from "../lib/store.js";
import { geocode, backendHealth } from "../lib/api.js";
import { ZUBRINGER, zubringerOf } from "../lib/routes.js";

export default {
  name: "DestinationsView",
  data() {
    return {
      ZUBRINGER,
      busy: null,       // id of the destination currently being looked up
      matches: {},      // id -> candidates awaiting a decision
      errors: {},
      /* id -> the fields as they are being typed. A located destination is a
       * stored record: its name and address are only written back when the
       * user says so, which is what makes leaving the editor free of cost. */
      edits: {},
      // The router the backend reports. Unknown until /api/health answers, and
      // unknown means no claim about it either way.
      routerEndpoint: null
    };
  },
  computed: {
    publicRouter() { return Boolean(this.routerEndpoint?.includes("transitous.org")); },
    destinations() { return state.data.destinations; },
    referencePoint() { return state.data.plots.find(p => p.anchor)?.anchor || null; }
  },
  async mounted() {
    const health = await backendHealth();
    const motis = health?.dienste?.find(service => service.name === "motis");
    this.routerEndpoint = motis?.endpunkt || null;
  },
  methods: {
    zubringerOf,

    /** Absent means "automatisch", so a return to the default clears the field
     *  rather than writing the default into every destination. */
    setZubringer(destination, value) {
      if (value === "automatic") delete destination.zubringer;
      else destination.zubringer = value;
      save();
    },

    displayName: destinationName,
    add() { addDestination(); },

    isLocated(destination) {
      return Number.isFinite(destination.lat) && Number.isFinite(destination.lon);
    },

    /** A record to read rather than a form to fill: located, and not open for editing. */
    isSaved(destination) {
      return this.isLocated(destination) && !this.edits[destination.id];
    },

    /** The fields under the cursor: the edit buffer where there is one, the
     *  destination itself while it is still a draft nothing depends on. */
    draft(destination) { return this.edits[destination.id] || destination; },

    addressEdited(destination) {
      const edit = this.edits[destination.id];
      return Boolean(edit) && edit.address.trim() !== (destination.address || "").trim();
    },

    setName(destination, value) {
      const edit = this.edits[destination.id];
      if (edit) { edit.name = value; return; }
      destination.name = value;
      save();
    },

    setAddress(destination, value) {
      delete this.errors[destination.id];
      delete this.matches[destination.id];
      const edit = this.edits[destination.id];
      if (edit) { edit.address = value; return; }
      destination.address = value;
      save();
    },

    beginEdit(destination) {
      this.edits[destination.id] = { name: destination.name, address: destination.address };
      // The cursor belongs where the editing starts, not at the top of the page.
      this.$nextTick(() => this.$el.querySelector(`#n-${destination.id}`)?.focus());
    },

    /** Write the buffer back. A changed address invalidates the coordinate that
     *  was found for the old one — keeping it would route to the previous place
     *  in silence — so it goes, together with every route computed to it. */
    commit(destination) {
      const edit = this.edits[destination.id];
      if (!edit) return;
      const addressChanged = this.addressEdited(destination);
      destination.name = edit.name.trim();
      destination.address = edit.address;
      delete this.edits[destination.id];
      delete this.errors[destination.id];
      delete this.matches[destination.id];
      if (addressChanged) unlocateDestination(destination.id);
      else save();
    },

    cancel(destination) {
      delete this.edits[destination.id];
      delete this.errors[destination.id];
      delete this.matches[destination.id];
    },

    lookUpByEnter(destination) {
      if (!this.draft(destination).address || this.busy === destination.id) return;
      this.lookUp(destination);
    },

    async lookUp(destination) {
      this.busy = destination.id;
      delete this.errors[destination.id];
      delete this.matches[destination.id];
      try {
        // The first plot's coordinate is the reference: destinations are
        // everyday places near the plots, and the geocoder is far more likely
        // to pick the right "Am Kirschberg" when it knows the region.
        const response = await geocode(this.draft(destination).address, this.referencePoint);
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

    /** Accepting a candidate is the moment the destination is stored: the typed
     *  fields go in with it, and the editor closes on the finished record. */
    accept(destination, choice) {
      const edit = this.edits[destination.id];
      if (edit) {
        destination.name = edit.name.trim();
        destination.address = edit.address;
        delete this.edits[destination.id];
      }
      locateDestination(destination.id, { lat: choice.lat, lon: choice.lon, match: choice.name });
      delete this.matches[destination.id];
    },

    discard(destination) { delete this.matches[destination.id]; },

    remove(destination) {
      const confirmed = window.confirm(`„${destinationName(destination)}“ entfernen? Die berechneten Wege dorthin gehen bei allen Grundstücken verloren.`);
      if (confirmed) removeDestination(destination.id);
    }
  }
};
</script>

<style scoped>
.destination-list{ display: flex; flex-direction: column; }
.destination-row{ padding: var(--w2b-space-3) var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line-faint); }
.destination-row:last-child{ border-bottom: 0; }
.feeder{
  display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px var(--w2b-space-3);
  align-items: center; padding: var(--w2b-space-3) var(--w2b-space-4);
  border-top: 1px solid var(--w2b-line-faint);
}
.feeder label{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  letter-spacing: .09em; text-transform: uppercase; color: var(--w2b-muted);
}
.feeder select{ max-width: 26ch; }
.feeder__hint{ grid-column: 1 / -1; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
@media (max-width: 560px){
  .feeder{ grid-template-columns: 1fr; }
  .feeder select{ max-width: none; }
}
.destination-row__fields{ display: grid; grid-template-columns: 1fr 1.6fr auto auto; gap: var(--w2b-space-3); align-items: end; }
@media (max-width: 680px){ .destination-row__fields{ grid-template-columns: 1fr; } }
.destination-row__actions{ display: flex; gap: var(--w2b-space-2); margin-top: var(--w2b-space-3); flex-wrap: wrap; }
.destination-row__status{ margin-top: var(--w2b-space-2); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.destination-row__status--open{ color: var(--w2b-secondary-deep, var(--w2b-muted)); }
.destination-row__status .faint{ font-family: var(--w2b-font-mono); margin-left: var(--w2b-space-2); }
.notice{ margin-top: var(--w2b-space-3); }
/* Not an error: the coordinate is still there, and the user can still step back. */
.notice--warn{ background: var(--w2b-warning-surface); color: var(--w2b-warning-text); }

/* A stored destination reads as a record — a heading, a state, three values. */
.destination-record{ border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); background: var(--w2b-surface-sunken); }
.destination-record__head{
  display: flex; align-items: center; gap: var(--w2b-space-2); flex-wrap: wrap;
  padding: var(--w2b-space-2) var(--w2b-space-3); border-bottom: 1px solid var(--w2b-line-faint);
}
.destination-record__name{ margin: 0; font-size: var(--w2b-text-m); }
.value-list{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.value-list dt, .value-list dd{
  padding: 6px var(--w2b-space-3); border-bottom: 1px solid var(--w2b-line-faint); margin: 0;
  display: flex; align-items: center;
}
.value-list dt{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.value-list dd{ justify-content: flex-end; gap: 6px; font-size: var(--w2b-text-s); text-align: right; }
.value-list dt:last-of-type, .value-list dd:last-of-type{ border-bottom: 0; }
.faint{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }

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
