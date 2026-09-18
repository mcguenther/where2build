<template>
  <div class="stack">
    <section class="panel">
      <div class="panel__head"><h3>Zeitraum des Verbrauchs</h3></div>
      <div class="panel__body">
        <PeriodPicker @change="load" />
      </div>
    </section>

    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    <p v-if="done" class="notice" role="status">{{ done }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Konten</h3>
        <div class="spacer"></div>
        <span v-if="rows.length" class="chip">{{ rows.length }} Zeilen</span>
      </div>
      <div class="panel__body">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <p v-else-if="rows.length === 0" class="hint">
          Es ist nichts gespeichert und es wurde in diesem Zeitraum nichts abgerufen.
        </p>
        <div v-else class="table-scroll">
          <table class="data-table data-table--stack">
            <thead>
              <tr>
                <th>Konto</th>
                <th class="num">Grundstücke</th>
                <th class="num">Umfang</th>
                <th class="num">Anfragen</th>
                <th class="num">Fehler</th>
                <th class="num">Tokens</th>
                <th>Zuletzt</th>
                <th>Zustand</th>
                <th>Verwaltung</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.kennung" :class="{ 'row--blocked': row.gesperrt_bis }">
                <td>
                  <b>{{ row.anzeigename || "ohne Namen" }}</b>
                  <br /><code class="kennung">{{ row.kennung }}</code>
                  <br /><span class="hint">{{ row.angelegt ? `angelegt ${date(row.angelegt)}` : "nichts gespeichert" }}</span>
                </td>
                <td class="num" data-label="Grundstücke">{{ row.grundstuecke }}</td>
                <td class="num" data-label="Umfang">{{ bytes(row.bytes) }}</td>
                <td class="num" data-label="Anfragen">{{ num(row.anfragen, 0) }}</td>
                <td class="num" data-label="Fehler">{{ num(row.fehler, 0) }}</td>
                <td class="num" data-label="Tokens">{{ row.tokens_ein + row.tokens_aus > 0 ? num(row.tokens_ein + row.tokens_aus, 0) : "—" }}</td>
                <td data-label="Zuletzt">{{ row.zuletzt_aktiv ? moment(row.zuletzt_aktiv) : "—" }}</td>
                <td>
                  <span v-if="row.gesperrt_bis" class="chip chip--alarm">
                    gesperrt bis {{ moment(row.gesperrt_bis) }}
                  </span>
                  <span v-else-if="row.ist_admin" class="chip">Verwalter</span>
                  <span v-else class="hint">—</span>
                  <p v-if="row.gesperrt_grund" class="hint">{{ row.gesperrt_grund }}</p>
                </td>
                <td class="actions">
                  <button v-if="row.gesperrt_bis" type="button" class="btn btn--quiet btn--small"
                          :disabled="working === row.kennung" @click="unblock(row)">Sperre aufheben</button>
                  <button v-else type="button" class="btn btn--quiet btn--small"
                          :disabled="working === row.kennung" @click="block(row)">Sperren</button>
                  <button type="button" class="btn btn--quiet btn--small"
                          :disabled="working === row.kennung" @click="toggleRole(row)">
                    {{ row.ist_admin ? "Recht entziehen" : "Zum Verwalter" }}
                  </button>
                  <button type="button" class="btn btn--quiet btn--small"
                          :disabled="working === row.kennung" @click="remove(row)">Löschen</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">
          Eine Zeile ohne „angelegt“ hat hier nichts gespeichert und ist nur durch ihre
          Aufrufe bekannt — sperren lässt sie sich trotzdem, zum Verwalter machen nicht.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * Who uses this deployment, and the three things an operator can do about it.
 *
 * Blocking is first among them because it is the one that has to be quick: the
 * row shows what an account spent in the period, and the button beside it stops
 * it — in the process serving the click immediately, and everywhere else within
 * one flush.
 *
 * Deleting an account is deliberately not a red button anywhere else in this
 * area: it is one person's data, it is asked for one row at a time, and it asks
 * back before it happens.
 */
import PeriodPicker from "./PeriodPicker.vue";
import {
  adminAccounts,
  adminBlock,
  adminDeleteAccount,
  adminSetRole,
  adminUnblock
} from "../../lib/api.js";
import { bytes, date, moment, num } from "../../lib/format.js";

export default {
  name: "AdminAccounts",
  components: { PeriodPicker },
  data() {
    return { rows: [], period: null, busy: false, failure: "", done: "", working: "" };
  },
  methods: {
    bytes,
    date,
    moment,
    num,
    async load(period) {
      this.period = period || this.period;
      if (!this.period) return;
      this.busy = true;
      this.failure = "";
      try {
        const answer = await adminAccounts(this.period.from, this.period.to);
        this.rows = answer.konten;
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    },

    async act(row, run, message) {
      this.working = row.kennung;
      this.failure = "";
      this.done = "";
      try {
        await run();
        this.done = message;
        await this.load();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.working = "";
      }
    },

    block(row) {
      const answer = window.prompt(
        "Für wie viele Minuten soll dieses Konto gesperrt werden?\n" +
          "Die Sperre endet danach von selbst.",
        "60"
      );
      if (answer === null) return;
      const minutes = Number.parseInt(answer, 10);
      if (!Number.isFinite(minutes) || minutes < 1) {
        this.failure = "Bitte eine Anzahl Minuten größer als null angeben.";
        return;
      }
      const reason = window.prompt("Grund (erscheint im Prüfprotokoll):", "Auffällig viele Anfragen") || "";
      return this.act(
        row,
        () => adminBlock(row.kennung, minutes, reason),
        `Konto für ${minutes} Minuten gesperrt.`
      );
    },

    unblock(row) {
      return this.act(row, () => adminUnblock(row.kennung), "Sperre aufgehoben.");
    },

    toggleRole(row) {
      const wanted = !row.ist_admin;
      const sure = window.confirm(
        wanted
          ? "Dieses Konto darf danach die Verwaltung öffnen: Statistiken, Konten, Sperren und das Leeren der Datenbank."
          : "Dieses Konto verliert den Zugang zur Verwaltung."
      );
      if (!sure) return;
      return this.act(
        row,
        () => adminSetRole(row.kennung, wanted),
        wanted ? "Verwaltungsrecht gegeben." : "Verwaltungsrecht entzogen."
      );
    },

    remove(row) {
      const sure = window.confirm(
        `Konto ${row.anzeigename || row.kennung} mit allen Grundstücken, Einstellungen und ` +
          "Freigaben endgültig löschen? Das lässt sich nicht rückgängig machen."
      );
      if (!sure) return;
      return this.act(row, () => adminDeleteAccount(row.kennung), "Konto gelöscht.");
    }
  }
};
</script>

<style scoped>
.kennung{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.actions{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-1); }
.row--blocked{ background: var(--w2b-error-surface); }
.chip--alarm{ background: var(--w2b-error-surface); color: var(--w2b-error); }
.data-table .hint{ margin: 0; }
</style>
