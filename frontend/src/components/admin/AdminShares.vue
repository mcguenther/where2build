<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    <p v-if="done" class="notice" role="status">{{ done }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Offene Links</h3>
        <div class="spacer"></div>
        <button type="button" class="btn btn--quiet btn--small" :disabled="busy" @click="sweep">
          Abgelaufene entfernen
        </button>
      </div>
      <div class="panel__body stack">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <p v-else-if="rows.length === 0" class="hint">Zurzeit ist nichts geteilt.</p>
        <div v-else class="table-scroll">
          <table class="data-table data-table--stack">
            <thead>
              <tr><th>Link</th><th>Von</th><th>Angelegt</th><th>Läuft ab</th><th class="num">Umfang</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.token">
                <td data-label="Link"><code class="kennung">{{ row.token }}</code></td>
                <td>
                  {{ row.anzeigename || "ohne Namen" }}
                  <br /><code class="kennung">{{ row.kennung }}</code>
                </td>
                <td data-label="Angelegt">{{ moment(row.angelegt) }}</td>
                <td data-label="Läuft ab">{{ moment(row.laeuft_ab) }}</td>
                <td class="num" data-label="Umfang">{{ bytes(row.bytes) }}</td>
                <td>
                  <button type="button" class="btn btn--quiet btn--small"
                          :disabled="working === row.token" @click="withdraw(row)">Zurückziehen</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">
          Was in einem Link steht, ist hier nicht zu sehen und soll es auch nicht sein:
          ein geteiltes Grundstück ist die Sache dessen, der es geteilt hat. Zurückziehen
          geht trotzdem — danach führt der Link nirgendwohin.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The shared links, as the operator can legitimately see them.
 *
 * Token, owner, dates and size. Not the document: an operator who has to
 * withdraw a link — because it was reported, or because it is expired and the
 * sweep has not run — does not have to read what is in it to do that.
 */
import { adminDeleteShare, adminShares, adminSweepShares } from "../../lib/api.js";
import { bytes, moment } from "../../lib/format.js";

export default {
  name: "AdminShares",
  data() {
    return { rows: [], busy: false, failure: "", done: "", working: "" };
  },
  created() { this.load(); },
  methods: {
    bytes,
    moment,
    async load() {
      this.busy = true;
      this.failure = "";
      try {
        this.rows = (await adminShares()).freigaben;
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    },
    async withdraw(row) {
      if (!window.confirm("Diesen Link zurückziehen? Wer ihn hat, sieht danach nichts mehr.")) return;
      this.working = row.token;
      this.failure = "";
      this.done = "";
      try {
        await adminDeleteShare(row.token);
        this.done = "Link zurückgezogen.";
        await this.load();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.working = "";
      }
    },
    async sweep() {
      this.failure = "";
      this.done = "";
      try {
        const answer = await adminSweepShares();
        this.done = answer.entfernt === 1
          ? "Ein abgelaufener Link wurde entfernt."
          : `${answer.entfernt} abgelaufene Links wurden entfernt.`;
        await this.load();
      } catch (error) {
        this.failure = error.message;
      }
    }
  }
};
</script>

<style scoped>
.kennung{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); word-break: break-all; }
</style>
