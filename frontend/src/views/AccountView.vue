<template>
  <div class="stack">
    <nav class="breadcrumb" aria-label="Pfad">
      <RouterLink :to="{ name: 'home' }">Start</RouterLink>
      <span>Konto</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Anmeldung und gespeicherte Daten</p>
        <h1>Konto</h1>
        <p class="page-head__sub">
          Was hier über dieses Konto liegt, und wie es wieder wegkommt.
        </p>
      </div>
    </div>

    <!-- Signed out, or a deployment with no accounts at all: both are complete
         states of this app, not failures, so both say what holds instead of
         showing an empty page. -->
    <section v-if="!state.account.angemeldet" class="panel">
      <div class="panel__body stack">
        <template v-if="state.account.eingerichtet">
          <p>Für dieses Konto ist hier nichts zu sehen, solange niemand angemeldet ist.</p>
          <p><a class="btn btn--secondary" :href="signInHref" @click.prevent="signIn">Anmelden oder Konto anlegen</a></p>
        </template>
        <template v-else>
          <p>
            In diesem Betrieb ist keine Anmeldung eingerichtet, es gibt also keine Konten.
            Alles bleibt im Speicher dieses Browsers; unter
            <RouterLink :to="{ name: 'data' }">„Daten“</RouterLink> steht der Austausch als JSON.
          </p>
        </template>
      </div>
    </section>

    <template v-else>
      <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

      <section class="panel">
        <div class="panel__head">
          <h3>Gespeichert ist</h3>
          <div class="spacer"></div>
          <span v-if="held" class="chip">{{ size }}</span>
        </div>
        <div class="panel__body stack">
          <p v-if="busy" class="hint">Wird geladen …</p>

          <!-- The row is created on the first write, so being signed in with
               nothing stored is a real state and says so rather than showing
               an account full of zeroes. -->
          <p v-else-if="nothingStored">
            Es ist noch nichts gespeichert. Ein Konto entsteht hier erst, wenn das erste
            Grundstück gesichert wird. Bis dahin liegt alles nur in diesem Browser.
          </p>

          <template v-else-if="held">
            <p class="hint">
              Das ist vollständig: mehr als diese Zeilen hält diese Anwendung nicht über
              eine Person. Name und Anbieter-Kennung kommen von der Anmeldung, nicht von uns.
            </p>
            <dl class="value-list">
              <dt>Name</dt><dd>{{ held.anzeigename || "vom Anbieter nicht mitgegeben" }}</dd>
              <dt>Anbieter</dt><dd class="wrap">{{ held.anbieter }}</dd>
              <dt>Kennung beim Anbieter</dt><dd class="wrap">{{ held.anbieter_kennung }}</dd>
              <dt>Kennung dieses Kontos</dt><dd class="wrap">{{ held.kennung }}</dd>
              <dt>Angelegt</dt><dd>{{ date(held.angelegt) }}</dd>
              <dt>Grundstücke</dt><dd>{{ held.grundstuecke }}</dd>
              <dt>Umfang</dt><dd>{{ size }}</dd>
            </dl>
            <!-- Two identifiers, and only one of them is the one an operator
                 asks for. Saying which is cheaper than the support mail that
                 follows from pasting the other. -->
            <p class="hint">
              „Kennung dieses Kontos“ ist die, unter der diese Anwendung das Konto führt —
              sie steht auch in <code>ADMIN_ACCOUNTS</code>, wenn der Betreiber dieses Konto
              zum Verwalter macht. Die Kennung beim Anbieter kommt von der Anmeldung und
              wird hier nirgends sonst verwendet.
            </p>
            <div class="row">
              <button type="button" class="btn btn--secondary" :disabled="exporting" @click="downloadRecord">
                {{ exporting ? "Wird zusammengestellt …" : "Auskunft als JSON sichern" }}
              </button>
            </div>
            <p v-if="exportMessage" class="notice" :class="{ 'notice--error': exportFailed }">{{ exportMessage }}</p>
          </template>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Konto löschen</h3></div>
        <div class="panel__body stack">
          <p>
            Das Konto und alles darin werden gelöscht: die Grundstücke, die Haustypen, die
            Ziele und die Zeile mit Name und Kennung. Das lässt sich nicht rückgängig machen.
          </p>
          <!-- Deleting an account is not the same wish as throwing away the
               work, and conflating the two would surprise somebody badly. The
               browser keeps its stand, exactly as it does on signing out. -->
          <p class="hint">
            Der Stand in diesem Browser bleibt dabei erhalten, genau wie beim Abmelden.
            Zum Wegwerfen gibt es unter
            <RouterLink :to="{ name: 'data' }">„Daten“</RouterLink> „Alles löschen“.
          </p>
          <div class="row">
            <button type="button" class="btn btn--quiet" :disabled="deleting" @click="remove">
              {{ deleting ? "Wird gelöscht …" : "Konto endgültig löschen" }}
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script>
/**
 * The account, and the way out of it.
 *
 * Two things this page owes somebody: what is held about them, in full rather
 * than as a summary they have to trust, and a way to erase it. The second is
 * the reason the page exists at all — the `users` row carries the display name
 * the provider granted, and until now nothing could remove it.
 */
import { state, loadAccount, loadFromAccount } from "../lib/store.js";
import { accountOnServer, deleteAccountOnServer, plotsOnServer, settingsOnServer, signInUrl } from "../lib/api.js";
import { beginSignIn } from "../lib/signIn.js";
import { date } from "../lib/format.js";

export default {
  name: "AccountView",
  data() {
    return {
      state,
      held: null,
      busy: false,
      /** Signed in, but nothing has ever been written under this sign-in. */
      nothingStored: false,
      failure: "",
      exporting: false,
      exportMessage: "",
      exportFailed: false,
      deleting: false
    };
  },
  computed: {
    signInHref() { return signInUrl(this.$route.fullPath); },
    size() {
      const bytes = this.held?.groesse_bytes ?? 0;
      if (bytes < 1024) return `${bytes} Byte`;
      const kib = bytes / 1024;
      return kib < 1024 ? `${kib.toFixed(1)} KiB` : `${(kib / 1024).toFixed(1)} MiB`;
    }
  },
  created() { this.load(); },
  watch: {
    /* Who is signed in is asked once, by the App, and the answer arrives after
       this page has already been created — so a *direct* load of /konto found
       `angemeldet` still false, `load()` returned at its first line, and the
       panel stayed empty with no error to show for it. Clicking here from the
       header always worked, which is why this survived until the page got a
       screenshot of its own. Watching also covers signing in in the second
       window, which lands back here with the account filled in. */
    "state.account.angemeldet"(signedIn) {
      if (signedIn && !this.held) this.load();
    }
  },
  methods: {
    /** Signing in runs in a window of its own, so this page stays standing --
     *  with whatever is half-entered on it. A refused window falls back to a
     *  full navigation; see lib/signIn.js. */
    signIn() { return beginSignIn(this.$route.fullPath); },
    date,
    async load() {
      if (!state.account.angemeldet) return;
      this.busy = true;
      this.failure = "";
      try {
        this.held = await accountOnServer();
        this.nothingStored = false;
      } catch (error) {
        // 404 is "nothing written yet" and 503 is "no store in this
        // deployment" — both are states, and neither is an error to shout at
        // somebody. Anything else is.
        if (error.status === 404) { this.nothingStored = true; }
        else if (error.status === 503) { this.nothingStored = true; }
        else { this.failure = error.message; }
      } finally {
        this.busy = false;
      }
    },

    /** The whole record, as the server holds it — not the browser's copy.
     *  A statement about what is stored has to be read from where it is. */
    async downloadRecord() {
      this.exporting = true;
      this.exportMessage = "";
      this.exportFailed = false;
      try {
        const [plots, settings] = await Promise.all([plotsOnServer(), settingsOnServer()]);
        const record = { konto: this.held, grundstuecke: plots.eintraege, einstellungen: settings };
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(record, null, 2)], { type: "application/json" })
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = "where2build-konto.json";
        link.click();
        URL.revokeObjectURL(url);
        this.exportMessage = "Datei gesichert.";
      } catch (error) {
        this.exportMessage = error.message;
        this.exportFailed = true;
      } finally {
        this.exporting = false;
      }
    },

    async remove() {
      const sure = window.confirm(
        "Konto und alle gespeicherten Daten endgültig löschen? Das lässt sich nicht rückgängig machen."
      );
      if (!sure) return;
      this.deleting = true;
      this.failure = "";
      try {
        await deleteAccountOnServer();
        // The backend ended the session in the same answer, so who is signed
        // in has to be asked again rather than assumed — and the document in
        // force switches back to this browser's own.
        await loadAccount();
        await loadFromAccount();
        this.held = null;
        this.$router.push({ name: "home" });
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.deleting = false;
      }
    }
  }
};
</script>

<style scoped>
/* An issuer URL and a provider's subject have no spaces to break at, and the
   value column is narrow. */
.value-list dd.wrap{ word-break: break-all; text-align: right; }
</style>
