<template>
  <!-- Nothing to manage, nothing on the page. A section that is always there
       and usually empty is furniture; this one appears exactly when there is a
       link somebody could want back. -->
  <section v-if="links.length" class="panel no-print">
    <div class="panel__head">
      <h3>Vergebene Links</h3>
      <div class="spacer"></div>
      <span class="chip">{{ links.length }}</span>
    </div>
    <div class="panel__body stack">
      <p class="hint">
        Wer einen dieser Links hat, sieht dieses Grundstück, ohne sich anzumelden.
        Zurückziehen wirkt sofort — auch für Links, die schon verschickt sind.
      </p>

      <ul class="links">
        <li v-for="link in links" :key="link.id" class="links__row">
          <div class="links__what">
            <p class="links__when">
              Geteilt am {{ date(link.angelegt) }} · läuft am {{ date(link.laeuft_ab) }} ab
            </p>
            <p class="links__scope">{{ carried(link) }}</p>
          </div>
          <button type="button" class="btn btn--quiet btn--small"
                  :disabled="busy === link.id" @click="withdraw(link)">
            {{ busy === link.id ? "Wird zurückgezogen …" : "Zurückziehen" }}
          </button>
        </li>
      </ul>

      <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    </div>
  </section>
</template>

<script>
/**
 * The links that already exist for one plot, and the way back out of them.
 *
 * A shared link is public for ninety days, so being unable to see one is the
 * part that matters: without this the only way to undo a slip was to wait it
 * out. It sits on the plot's own page rather than in the account, because that
 * is where somebody who has just shared something looks.
 *
 * What each link carries is read off the stored row by the backend, not
 * remembered from the switches — so this list cannot claim a link holds a
 * price it does not hold.
 */
import { sharesOnServer, deleteShare } from "../lib/api.js";
import { state } from "../lib/store.js";
import { date } from "../lib/format.js";

/** The German names of the switches, in the order the share panel offers them. */
const NAMES = { preis: "Kaufpreis", haus: "Haus", wege: "Ziele und Wegezeiten", notiz: "Notiz" };

export default {
  name: "SharedLinks",
  props: { plot: { type: Object, required: true } },
  data() {
    return { links: [], busy: "", failure: "" };
  },
  created() { this.load(); },
  watch: {
    // Signing in or out changes whether there is anything to ask about, and
    // the plot changes when the page does.
    "plot.id": function () { this.load(); },
    "state.account.angemeldet": function () { this.load(); }
  },
  computed: {
    state() { return state; }
  },
  methods: {
    date,

    /** This plot's open links, newest first. Silent when there is no account:
     *  a signed-out browser has none, and an error about that is noise. */
    async load() {
      if (!state.account.angemeldet) {
        this.links = [];
        return;
      }
      try {
        const answer = await sharesOnServer();
        this.links = (answer.eintraege ?? []).filter(e => e.grundstueck === this.plot.id);
      } catch {
        this.links = [];
      }
    },

    carried(link) {
      const on = Object.keys(NAMES).filter(key => link.umfang?.[key]);
      if (!on.length) return "Enthält Lage, Fläche und Bodenrichtwert.";
      return `Enthält außerdem: ${on.map(key => NAMES[key]).join(", ")}.`;
    },

    async withdraw(link) {
      this.busy = link.id;
      this.failure = "";
      try {
        await deleteShare(link.id);
        this.links = this.links.filter(other => other.id !== link.id);
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = "";
      }
    }
  }
};
</script>

<style scoped>
.links{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-2); }
.links__row{
  display: flex; gap: var(--w2b-space-3); align-items: center; flex-wrap: wrap;
  padding: var(--w2b-space-3); border: 1px solid var(--w2b-line-faint);
  border-radius: var(--w2b-radius-s); background: var(--w2b-surface-sunken);
}
.links__what{ flex: 1; min-width: 220px; }
.links__when{ margin: 0; font-size: var(--w2b-text-s); }
.links__scope{ margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
</style>
