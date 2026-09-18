<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    <p v-if="done" class="notice" role="status">{{ done }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Zwischenspeicher</h3>
        <div class="spacer"></div>
        <span v-if="held" class="chip">{{ bytes(held.cache_bytes) }} von {{ bytes(held.cache_grenze_bytes) }}</span>
      </div>
      <div class="panel__body stack">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <template v-else-if="held">
          <p v-if="held.caches.length === 0" class="hint">
            Auf diesem Server liegt noch nichts im Zwischenspeicher.
          </p>
          <div v-else class="table-scroll">
            <table class="data-table data-table--stack">
              <thead>
                <tr><th>Name</th><th class="num">Dateien</th><th class="num">Umfang</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="entry in held.caches" :key="entry.name">
                  <td data-label="Name">{{ entry.name }}</td>
                  <td class="num" data-label="Dateien">{{ num(entry.dateien, 0) }}</td>
                  <td class="num" data-label="Umfang">{{ bytes(entry.bytes) }}</td>
                  <td>
                    <button type="button" class="btn btn--quiet btn--small"
                            :disabled="working === entry.name" @click="clear(entry)">Leeren</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="hint">
            Leeren kostet nichts außer Zeit: was gebraucht wird, wird beim nächsten Aufruf
            wieder geholt — und geht dann als Anfrage an den jeweiligen Dienst.
          </p>
        </template>
      </div>
    </section>

    <section v-if="held" class="panel">
      <div class="panel__head"><h3>Kontingente und Sperren</h3></div>
      <div class="panel__body stack">
        <dl class="value-list">
          <dt>Dienstaufrufe je Zugang</dt>
          <dd>{{ held.kontingent_aktiv ? `${num(held.kontingent_dienste, 0)} je ${windowText(held.kontingent_fenster_s)}` : "aus" }}</dd>
          <dt>Kartenkacheln je Zugang</dt>
          <dd>{{ held.kontingent_aktiv ? `${num(held.kontingent_kacheln, 0)} je ${windowText(held.kontingent_fenster_s)}` : "aus" }}</dd>
          <dt>Automatische Sperre</dt>
          <dd>ab {{ num(held.sperre_ab, 0) }} Anfragen in {{ windowText(held.sperre_fenster_s) }}, für {{ held.sperre_dauer_min }} Minuten</dd>
          <dt>Aufbewahrung der Zähler</dt>
          <dd>{{ held.aufbewahrung_tage }} Tage</dd>
        </dl>
        <p class="hint">
          Diese Werte stehen in der Konfiguration des Servers (ADMIN_… und RATELIMIT_…)
          und lassen sich hier nicht ändern — was hier änderbar wäre, würde beim nächsten
          Start wieder überschrieben.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The operational half: what is on disk, and what the ceilings are.
 *
 * Read-only apart from clearing a cache, and deliberately so. The ceilings come
 * from the environment, so a field here that wrote them would be a setting that
 * disappears on the next restart — the page says where they are set instead.
 */
import { adminClearCache, adminServices } from "../../lib/api.js";
import { bytes, num } from "../../lib/format.js";

export default {
  name: "AdminServices",
  data() {
    return { held: null, busy: false, failure: "", done: "", working: "" };
  },
  created() { this.load(); },
  methods: {
    bytes,
    num,
    /** Named for what it says, not „window“: that one is the global. */
    windowText(seconds) {
      const minutes = Math.round(seconds / 60);
      if (minutes < 60) return `${minutes} Minuten`;
      const hours = minutes / 60;
      return hours === 1 ? "Stunde" : `${num(hours, 0)} Stunden`;
    },
    async load() {
      this.busy = true;
      this.failure = "";
      try {
        this.held = await adminServices();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.busy = false;
      }
    },
    async clear(entry) {
      const sure = window.confirm(
        `Zwischenspeicher „${entry.name}“ mit ${entry.dateien} Dateien leeren?`
      );
      if (!sure) return;
      this.working = entry.name;
      this.failure = "";
      this.done = "";
      try {
        await adminClearCache(entry.name);
        this.done = `„${entry.name}“ geleert.`;
        await this.load();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.working = "";
      }
    }
  }
};
</script>
