<template>
  <div class="stack">
    <section class="panel">
      <div class="panel__head"><h3>Zeitraum</h3></div>
      <div class="panel__body">
        <PeriodPicker @change="load" />
      </div>
    </section>

    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Fehler</h3>
        <div class="spacer"></div>
        <a v-if="period" class="btn btn--secondary btn--small" :href="downloadHref" download>
          Als NDJSON sichern
        </a>
      </div>
      <div class="panel__body stack">
        <div class="row row--wrap">
          <label class="field">
            <span>Suchen</span>
            <input type="search" v-model="search" placeholder="Dienst, Route oder Wortlaut"
                   @keyup.enter="find" @search="find" />
          </label>
          <div class="spacer"></div>
          <button type="button" class="btn btn--quiet btn--small" @click="find">Suchen</button>
        </div>

        <p v-if="busy" class="hint">Wird geladen …</p>
        <template v-else-if="held">
          <p v-if="held.quelle === 'speicher'" class="notice">
            Auf diesem Server ist kein Speicher für Konten eingerichtet, deshalb steht hier
            nur, was dieser Prozess seit seinem Start gesehen hat. Beim Neustart ist es weg.
          </p>
          <p v-if="held.eintraege.length === 0 && search" class="hint">
            Zu dieser Suche gibt es in diesem Zeitraum keinen Eintrag.
          </p>
          <p v-else-if="held.eintraege.length === 0" class="hint">
            In diesem Zeitraum ist nichts schiefgegangen — jedenfalls nichts, was der Server
            als seinen Fehler verbucht. Antworten wie „nicht gefunden“ oder „Kontingent
            erreicht“ stehen bewusst nicht hier, sondern in der Statistik.
          </p>
          <div v-else class="table-scroll">
            <table class="data-table data-table--stack">
              <thead>
                <tr><th>Zeit</th><th class="num">Status</th><th>Wo</th><th>Meldung</th><th>Konto</th></tr>
              </thead>
              <tbody>
                <tr v-for="(entry, index) in held.eintraege" :key="index">
                  <td data-label="Zeit">{{ moment(entry.zeit) }}</td>
                  <td class="num" data-label="Status">{{ entry.status ?? "—" }}</td>
                  <td data-label="Wo"><code class="where">{{ entry.dienst || entry.route || entry.bereich }}</code></td>
                  <td data-label="Meldung">{{ entry.meldung }}</td>
                  <td data-label="Konto"><code class="kennung">{{ entry.kennung || "—" }}</code></td>
                </tr>
              </tbody>
            </table>
          </div>
          <AdminPager :total="held.gesamt" :offset="offset" :limit="limit" @move="turn" />
        </template>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The failures, and the file of them.
 *
 * What counts as one is decided on the server and deliberately narrow: from
 * HTTP 500 up, minus the 503 that means "this deployment has no database",
 * which is a state and not a fault. A log that also held every 404 is one
 * nobody reads, and the point of this page is that somebody does.
 *
 * The download is an ordinary link rather than a fetch: the browser then saves
 * it under the name the server sends, and the file is the same bytes the page
 * is showing.
 */
import AdminPager from "./AdminPager.vue";
import PeriodPicker from "./PeriodPicker.vue";
import { adminErrorDownloadUrl, adminErrors } from "../../lib/api.js";
import { moment } from "../../lib/format.js";

export default {
  name: "AdminErrors",
  components: { AdminPager, PeriodPicker },
  data() {
    return { held: null, period: null, offset: 0, limit: 25, search: "", busy: false, failure: "" };
  },
  computed: {
    downloadHref() {
      return this.period ? adminErrorDownloadUrl(this.period.from, this.period.to) : "#";
    }
  },
  methods: {
    moment,
    find() {
      this.offset = 0;
      return this.load();
    },

    turn(offset) {
      this.offset = offset;
      return this.load();
    },

    async load(period) {
      this.period = period || this.period;
      if (!this.period) return;
      this.busy = true;
      this.failure = "";
      try {
        this.held = await adminErrors(this.period.from, this.period.to, {
          limit: this.limit,
          offset: this.offset,
          suche: this.search
        });
      } catch (error) {
        this.held = null;
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.field{ display: flex; flex-direction: column; gap: var(--w2b-space-1); font-size: var(--w2b-text-s); }
.row--wrap{ flex-wrap: wrap; align-items: end; }
.kennung, .where{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
/* The route is read as a path, so it breaks only where it has to -- „/api/
   setting s" was break-all doing what it was told. The account key has no
   natural break at all and keeps it. */
.where{ overflow-wrap: anywhere; }
.kennung{ word-break: break-all; }
</style>
