<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Prüfprotokoll</h3>
        <div class="spacer"></div>
        <span v-if="total" class="chip">{{ num(total, 0) }} Einträge</span>
      </div>
      <div class="panel__body stack">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <p v-else-if="rows.length === 0" class="hint">Bisher hat niemand hier etwas geändert.</p>
        <div v-else class="table-scroll">
          <table class="data-table data-table--stack">
            <thead>
              <tr><th>Zeit</th><th>Wer</th><th>Was</th><th>Woran</th><th>Näheres</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in rows" :key="index">
                <td data-label="Zeit">{{ moment(row.zeit) }}</td>
                <td>
                  {{ row.name || "ohne Namen" }}
                  <br /><code class="kennung">{{ row.kennung }}</code>
                </td>
                <td data-label="Was">{{ actionName(row.aktion) }}</td>
                <td data-label="Woran"><code class="kennung">{{ row.ziel || "—" }}</code></td>
                <td class="details" data-label="Näheres">{{ row.details ? JSON.stringify(row.details) : "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <AdminPager :total="total" :offset="offset" :limit="limit" @move="turn" />
        <p class="hint">
          Dieses Protokoll bleibt auch dann stehen, wenn die Datenbank geleert wird —
          sonst wäre der Eintrag über das Leeren das Erste, was das Leeren löscht.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * Who changed what in this area.
 *
 * Worth having the moment there is more than one administrator, and worth
 * having before that for the one case nobody plans for: an action nobody
 * remembers taking. The entries are written by the backend, not by this page.
 */
import AdminPager from "./AdminPager.vue";
import { adminAudit } from "../../lib/api.js";
import { moment, num } from "../../lib/format.js";

const ACTIONS = {
  rolle: "Verwaltungsrecht gegeben",
  "rolle-entzogen": "Verwaltungsrecht entzogen",
  sperre: "Konto gesperrt",
  "sperre-aufgehoben": "Sperre aufgehoben",
  "konto-geloescht": "Konto gelöscht",
  "freigabe-zurueckgezogen": "Freigabe zurückgezogen",
  "freigaben-aufgeraeumt": "Abgelaufene Freigaben entfernt",
  "cache-geleert": "Zwischenspeicher geleert",
  "datenbank-geleert": "Datenbank geleert"
};

export default {
  name: "AdminAudit",
  components: { AdminPager },
  data() {
    return { rows: [], total: 0, offset: 0, limit: 25, busy: false, failure: "" };
  },
  created() { this.load(); },
  methods: {
    moment,
    num,
    turn(offset) {
      this.offset = offset;
      return this.load();
    },
    /** The stored value is code; what is read is German. An unknown action is
     *  shown as it is rather than hidden — a new one must not vanish here. */
    actionName(key) { return ACTIONS[key] || key; },
    async load() {
      this.busy = true;
      this.failure = "";
      try {
        const answer = await adminAudit({ limit: this.limit, offset: this.offset });
        this.rows = answer.eintraege;
        this.total = answer.gesamt;
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<style scoped>
.kennung{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-muted); word-break: break-all; }
.details{ font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); word-break: break-all; }
</style>
