<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <section class="panel panel--danger">
      <div class="panel__head"><h3>Datenbank leeren</h3></div>
      <div class="panel__body stack">
        <p>
          Hier wird gelöscht, was andere Leute gespeichert haben. Das lässt sich nicht
          rückgängig machen und es gibt keine Sicherung, die diese Anwendung selbst
          anlegt.
        </p>

        <fieldset class="scopes">
          <legend>Was geleert wird</legend>
          <label v-for="scope in SCOPES" :key="scope.id">
            <input type="checkbox" :value="scope.id" v-model="chosen" :disabled="stage !== 'ruhe'" />
            <span>
              <b>{{ scope.label }}</b>
              <span class="hint">{{ scope.hint }}</span>
            </span>
          </label>
        </fieldset>

        <p class="hint">
          Das Prüfprotokoll bleibt in jedem Fall stehen. Verwalter aus der Konfiguration
          (ADMIN_ACCOUNTS) kommen auch danach wieder in diesen Bereich; ein Verwaltungsrecht,
          das nur in der Datenbank stand, ist weg.
        </p>

        <!-- The first confirmation. It fetches a key from the server, so the
             second step cannot be reached by a page that skipped this one. -->
        <div v-if="stage === 'ruhe'" class="row">
          <button type="button" class="btn btn--danger" :disabled="chosen.length === 0 || busy"
                  @click="begin">
            {{ busy ? "Einen Moment …" : "Löschen vorbereiten" }}
          </button>
          <span v-if="chosen.length === 0" class="hint">Zuerst auswählen, was geleert werden soll.</span>
        </div>

        <!-- The second. The sentence has to be typed, and the server checks it
             as well: a confirmation that only the browser knows about is one
             the browser can skip. -->
        <div v-else class="stack confirm">
          <p>
            <b>Zweite Bestätigung.</b> Es wird geleert:
            {{ chosen.map(id => nameOf(id)).join(", ") }}.
            Zum Fortfahren bitte <code>{{ phrase }}</code> eintippen.
            Die Bestätigung gilt bis {{ moment(validUntil) }}.
          </p>
          <label class="confirm__field">
            <span>Wortlaut</span>
            <input type="text" v-model="typed" autocomplete="off" spellcheck="false" />
          </label>
          <div class="row">
            <button type="button" class="btn btn--danger" :disabled="typed.trim() !== phrase || busy"
                    @click="wipe">
              {{ busy ? "Wird gelöscht …" : "Jetzt endgültig löschen" }}
            </button>
            <button type="button" class="btn btn--quiet" :disabled="busy" @click="cancel">Abbrechen</button>
          </div>
        </div>

        <div v-if="result" class="notice" role="status">
          <b>Geleert.</b>
          <ul class="result">
            <li v-for="(count, table) in result" :key="table">{{ table }}: {{ count }} Zeilen</li>
          </ul>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The red button, with both of its confirmations.
 *
 * The first one asks the server for a single-use key; the second one needs
 * that key and the sentence typed back. Both are checked on the server, which
 * is the whole point — two dialogs that only this component knows about would
 * be two dialogs a script does not have to answer.
 *
 * What is emptied is chosen rather than fixed: "the database" means the
 * accounts to one person and the statistics to another, and a button that
 * takes both when only one was meant is exactly the accident this page has to
 * make impossible.
 */
import { adminPrepareWipe, adminWipe } from "../../lib/api.js";
import { moment } from "../../lib/format.js";

const SCOPES = [
  {
    id: "konten",
    label: "Konten und ihre Daten",
    hint: "Alle Konten, Grundstücke, Einstellungen und Freigabe-Links."
  },
  {
    id: "statistik",
    label: "Statistik und Fehler",
    hint: "Die Zähler je Stunde, die je Konto und das Fehlerprotokoll."
  },
  {
    id: "sperren",
    label: "Sperren",
    hint: "Alle Sperren werden aufgehoben, auch die automatisch gesetzten."
  }
];

export default {
  name: "AdminDanger",
  data() {
    return {
      SCOPES,
      chosen: [],
      stage: "ruhe",
      key: "",
      phrase: "",
      validUntil: null,
      typed: "",
      busy: false,
      failure: "",
      result: null
    };
  },
  methods: {
    moment,
    nameOf(id) { return (SCOPES.find(scope => scope.id === id) || {}).label || id; },
    async begin() {
      this.busy = true;
      this.failure = "";
      this.result = null;
      try {
        const prepared = await adminPrepareWipe();
        this.key = prepared.schluessel;
        this.phrase = prepared.satz;
        this.validUntil = prepared.gueltig_bis;
        this.typed = "";
        this.stage = "bestaetigen";
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    },
    cancel() {
      this.stage = "ruhe";
      this.key = "";
      this.typed = "";
    },
    async wipe() {
      this.busy = true;
      this.failure = "";
      try {
        const answer = await adminWipe(this.key, this.typed.trim(), this.chosen);
        this.result = answer.geleert;
        this.chosen = [];
        this.cancel();
      } catch (error) {
        this.failure = error.message;
        // A used key is used up, so there is no second try with the same one.
        this.cancel();
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.panel--danger{ border-color: var(--w2b-error); }
.panel--danger .panel__head h3{ color: var(--w2b-error); }
.scopes{ border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); padding: var(--w2b-space-3); display: grid; gap: var(--w2b-space-2); }
.scopes legend{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); padding: 0 var(--w2b-space-1); }
.scopes label{ display: flex; gap: var(--w2b-space-2); align-items: start; }
.scopes .hint{ display: block; margin: 0; }
.confirm{ border-left: 3px solid var(--w2b-error); padding-left: var(--w2b-space-3); }
.confirm__field{ display: flex; flex-direction: column; gap: var(--w2b-space-1); max-width: 22rem; }
.btn--danger{ background: var(--w2b-error); color: var(--w2b-white); border-color: var(--w2b-error); }
.btn--danger[disabled]{ opacity: .5; }
.result{ margin: var(--w2b-space-1) 0 0; padding-left: var(--w2b-space-4); }
</style>
