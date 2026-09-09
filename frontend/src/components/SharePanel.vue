<template>
  <section class="panel share no-print">
    <div class="panel__head">
      <h3>Per Link teilen</h3>
      <div class="spacer"></div>
      <button type="button" class="btn btn--quiet btn--small" @click="$emit('close')">Schließen</button>
    </div>

    <!-- Signed out, and where there are no accounts at all. Neither is an
         error: sharing needs somewhere to keep the copy, and saying which of
         the two it is beats a disabled button with no reason. -->
    <div v-if="!state.account.angemeldet" class="panel__body stack">
      <template v-if="state.account.eingerichtet">
        <p>
          <b>Zum Teilen braucht es ein Konto.</b> Der geteilte Stand liegt auf dem Server,
          damit der Link auch dann noch etwas zeigt, wenn dieser Browser längst zu ist.
        </p>
        <p class="hint">
          Anmelden dauert einen Moment, und das Grundstück bleibt dabei genau so stehen,
          wie es jetzt ist.
        </p>
        <p><a class="btn" :href="signInHref">Anmelden oder Konto anlegen</a></p>
      </template>
      <template v-else>
        <p>
          <b>Teilen ist in diesem Betrieb nicht eingerichtet.</b> Ein geteilter Link braucht
          einen Server, der den Stand hält, und dazu ein Konto. Beides gibt es hier nicht.
        </p>
        <p class="hint">
          Zum Weitergeben bleibt der Ausdruck über „Drucken“ und der Austausch als JSON
          unter <RouterLink :to="{ name: 'data' }">„Daten“</RouterLink>.
        </p>
      </template>
    </div>

    <div v-else-if="link" class="panel__body stack">
      <p><b>Der Link steht.</b> Er zeigt den Stand von jetzt und läuft nach 90 Tagen ab.</p>
      <div class="row">
        <input class="share__link" type="text" readonly :value="link"
               aria-label="Geteilter Link" @focus="$event.target.select()">
        <button type="button" class="btn" @click="copy">In die Zwischenablage</button>
      </div>
      <p class="hint">{{ carriedSentence }}</p>
      <p v-if="message" class="hint">{{ message }}</p>
    </div>

    <div v-else class="panel__body stack">
      <p class="hint">
        Wer den Link hat, sieht das Grundstück: Lage, Umriss, amtliche Fläche und den
        Bodenrichtwert. Das sind Angaben, die die Register ohnehin veröffentlichen.
        Alles Weitere geht nur mit, wenn es hier eingeschaltet ist.
      </p>
      <p class="hint">
        Wo der Link eingefügt wird — Chat, Mail, Messenger —, erscheint eine Vorschaukarte
        mit Luftbild, Umriss und Name des Grundstücks.
      </p>

      <ul class="share__options">
        <li v-for="option in OPTIONS" :key="option.id">
          <label>
            <input type="checkbox" v-model="include[option.id]">
            <span>
              <b>{{ option.name }}</b>
              <span class="share__why">{{ option.why }}</span>
            </span>
          </label>
        </li>
      </ul>

      <div class="row">
        <button type="button" class="btn" :disabled="busy" @click="create">
          {{ busy ? "Wird geteilt …" : "Link erzeugen" }}
        </button>
      </div>
      <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    </div>
  </section>
</template>

<script>
/**
 * Making a shared link, and deciding what goes into it.
 *
 * Every switch starts off. A link is public — the token is the whole of the
 * access — so the safe default is the least it can be, and anything beyond the
 * plot's own registered facts has to be asked for. The backend cuts what is
 * not switched on, so this panel decides but does not enforce.
 *
 * Two of the switches carry something a snapshot cannot look up afterwards: the
 * house type lives in the settings document and the destinations do too, so
 * both are resolved into the document here when their switch is on.
 */
import { state, placement, houseTypeById, destinationName } from "../lib/store.js";
import { createShare, signInUrl } from "../lib/api.js";

/** What may travel beyond the plot, and why somebody might not want it to.
 *  The ids match `FreigabeUmfang` in the backend. */
const OPTIONS = [
  { id: "preis", name: "Kaufpreis", why: "Damit auch der Vergleich mit dem Bodenrichtwert." },
  { id: "haus", name: "Geplantes Haus", why: "Der Baukörper im Plan und der Haustyp." },
  { id: "wege", name: "Ziele und Wegezeiten", why: "Arbeit, Schule und wohin sonst gerechnet wurde." },
  { id: "notiz", name: "Notiz", why: "Was ihr euch zu diesem Grundstück notiert habt." }
];

export default {
  name: "SharePanel",
  props: { plot: { type: Object, required: true } },
  emits: ["close", "created"],
  data() {
    return {
      state,
      OPTIONS,
      include: { preis: false, haus: false, wege: false, notiz: false },
      busy: false,
      link: "",
      message: "",
      failure: ""
    };
  },
  computed: {
    signInHref() { return signInUrl(this.$route.fullPath); },
    /** Named after the fact, so what went out is readable without guessing. */
    carriedSentence() {
      const on = OPTIONS.filter(o => this.include[o.id]).map(o => o.name.toLowerCase());
      if (!on.length) return "Mitgeteilt wurden nur Lage, Fläche und Bodenrichtwert.";
      const listed = on.length === 1 ? on[0] : `${on.slice(0, -1).join(", ")} und ${on.at(-1)}`;
      return `Zusätzlich mitgeteilt: ${listed}.`;
    }
  },
  methods: {
    async create() {
      this.busy = true;
      this.failure = "";
      try {
        const made = await createShare(this.snapshot(), { ...this.include });
        this.link = new URL(
          this.$router.resolve({ name: "shared", params: { token: made.id, slug: [] } }).href,
          window.location.origin
        ).toString();
        // So the list of links on the page below knows about this one without
        // a reload -- taking it back has to be possible in the same breath.
        this.$emit("created");
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    },

    /** The plot plus what a reader could not otherwise resolve.
     *
     *  Added only where the switch is on: sending it regardless and trusting
     *  the backend to cut it would work, but it would also put somebody's
     *  destinations on the wire for a link that does not carry them. */
    snapshot() {
      const document = { ...this.plot };
      if (this.include.haus) {
        document.placedBuilding = this.plot.house ? placement(this.plot) : null;
        document.houseTypeName = houseTypeById(this.plot.houseTypeId)?.name ?? null;
      }
      if (this.include.wege) {
        document.sharedDestinations = Object.keys(this.plot.routes ?? {})
          .map(id => state.data.destinations.find(d => d.id === id))
          .filter(Boolean)
          .map(d => ({ id: d.id, name: destinationName(d) }));
      }
      return document;
    },

    async copy() {
      try {
        await navigator.clipboard.writeText(this.link);
        this.message = "In die Zwischenablage gelegt.";
      } catch {
        this.message = "Der Browser lässt das Kopieren nicht zu. Den Link markieren und Strg+C.";
      }
    }
  }
};
</script>

<style scoped>
.share__link{ flex: 1; min-width: 220px; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-s); }
.share__options{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3); }
.share__options label{ display: flex; gap: var(--w2b-space-3); align-items: flex-start; cursor: pointer; }
.share__options input{ margin-top: 3px; flex: none; }
.share__why{ display: block; font-size: var(--w2b-text-s); color: var(--w2b-muted); }
</style>
