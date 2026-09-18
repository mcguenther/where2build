<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>
    <p v-if="done" class="notice" role="status">{{ done }}</p>

    <!-- The announcement first: it is the only thing on this page that changes
         what every visitor sees, and it is the thing somebody opens this page
         for when something is wrong. -->
    <section class="panel">
      <div class="panel__head">
        <h3>Betriebsansage</h3>
        <div class="spacer"></div>
        <span class="chip" :class="{ 'chip--alarm': notice.sichtbar }">
          {{ notice.sichtbar ? "wird angezeigt" : "aus" }}
        </span>
      </div>
      <div class="panel__body stack">
        <p class="hint">
          Steht über jeder Seite, für alle — angemeldet oder nicht. Für das, was kein
          Fehlerprotokoll sagen kann: eine Wartung, ein bekannter Ausfall, ein Hinweis
          zum Datenstand.
        </p>
        <label class="field">
          <span>Text</span>
          <textarea v-model="notice.text" rows="2" maxlength="1000"
                    placeholder="Am Freitag ab 18 Uhr ist die Anwendung kurz nicht erreichbar."></textarea>
        </label>
        <div class="row row--wrap">
          <label class="field field--inline">
            <span>Art</span>
            <select v-model="notice.art">
              <option value="hinweis">Hinweis</option>
              <option value="warnung">Warnung</option>
            </select>
          </label>
          <label class="field field--inline">
            <span>Sichtbar bis</span>
            <input type="datetime-local" v-model="until" />
          </label>
          <label class="field field--check">
            <input type="checkbox" v-model="notice.sichtbar" />
            <span>anzeigen</span>
          </label>
          <div class="spacer"></div>
          <button type="button" class="btn btn--secondary btn--small" :disabled="saving"
                  @click="saveNotice">
            {{ saving ? "Wird gespeichert …" : "Ansage speichern" }}
          </button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Dienste</h3>
        <div class="spacer"></div>
        <span v-if="services.length" class="chip">{{ configuredCount }} von {{ services.length }} eingerichtet</span>
      </div>
      <div class="panel__body">
        <p v-if="services.length === 0" class="hint">
          {{ health ? "Dieser Server nennt keine Dienste." : "Wird geladen …" }}
        </p>
        <!-- Cards, not rows: the interesting part of a service is the sentence
             under its name, and a sentence in a table cell is a table cell
             nobody reads. -->
        <ul v-else class="cards">
          <li v-for="service in services" :key="service.name" class="card"
              :class="{ 'card--off': !service.konfiguriert }">
            <div class="card__head">
              <span class="card__dot" :class="service.konfiguriert ? 'card__dot--on' : 'card__dot--off'"
                    aria-hidden="true"></span>
              <b>{{ label(service.name) }}</b>
              <span class="spacer"></span>
              <span class="card__state">{{ service.konfiguriert ? "eingerichtet" : "nicht eingerichtet" }}</span>
            </div>
            <p class="card__hint">{{ service.hinweis }}</p>
            <p v-if="service.endpunkt" class="card__endpoint">{{ service.endpunkt }}</p>
          </li>
        </ul>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Läufe</h3>
        <div class="spacer"></div>
        <span class="chip" :class="{ 'chip--alarm': jobs && !jobs.scheduler_laeuft }">
          {{ jobs && jobs.scheduler_laeuft ? "Scheduler läuft" : "kein Scheduler" }}
        </span>
      </div>
      <div class="panel__body stack">
        <p v-if="!jobs" class="hint">Wird geladen …</p>
        <template v-else>
          <p v-if="jobs.hinweis" class="notice">{{ jobs.hinweis }}</p>
          <ul class="cards">
            <li v-for="job in jobs.jobs" :key="job.name" class="card">
              <div class="card__head">
                <b>{{ job.name }}</b>
                <span class="spacer"></span>
                <span v-if="job.laeuft" class="chip">läuft gerade</span>
                <span v-else-if="job.angefordert" class="chip chip--alarm">angefordert</span>
                <span v-else-if="job.exit_code === 0" class="card__state">zuletzt erfolgreich</span>
                <span v-else-if="job.exit_code !== null" class="card__state card__state--bad">
                  zuletzt Exit {{ job.exit_code }}
                </span>
                <span v-else class="card__state">noch nie gelaufen</span>
              </div>
              <p class="card__hint">{{ job.warum }}</p>
              <p class="card__endpoint">
                {{ job.zeitplan }} (UTC) ·
                {{ job.zuletzt ? `zuletzt ${moment(job.zuletzt)}` : "kein Lauf verzeichnet" }}
                <template v-if="job.dauer_s"> · {{ num(job.dauer_s, 1) }} s</template>
              </p>
              <div class="row">
                <button type="button" class="btn btn--quiet btn--small"
                        :disabled="working === job.name || job.laeuft || !!job.angefordert"
                        @click="startJob(job)">Jetzt starten</button>
              </div>
            </li>
          </ul>
        </template>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Zwischenspeicher</h3>
        <div class="spacer"></div>
        <span v-if="held" class="chip">{{ bytes(held.cache_bytes) }} von {{ bytes(held.cache_grenze_bytes) }}</span>
      </div>
      <div class="panel__body stack">
        <p v-if="!held" class="hint">Wird geladen …</p>
        <template v-else>
          <p v-if="held.caches.length === 0" class="hint">
            Auf diesem Server liegt noch nichts im Zwischenspeicher.
          </p>
          <!-- A bar each, because the question is „wovon ist das viel" and a
               number in a column cannot answer it. -->
          <ul v-else class="bars">
            <li v-for="entry in held.caches" :key="entry.name">
              <div class="bars__line">
                <b>{{ entry.name }}</b>
                <span class="spacer"></span>
                <span class="bars__value">{{ bytes(entry.bytes) }} · {{ num(entry.dateien, 0) }} Dateien</span>
                <button type="button" class="btn btn--quiet btn--small"
                        :disabled="working === entry.name" @click="clearCache(entry)">Leeren</button>
              </div>
              <div class="bars__track">
                <div class="bars__fill" :style="{ width: share(entry) }"></div>
              </div>
            </li>
          </ul>
          <p class="hint">
            Leeren kostet nichts außer Zeit: was gebraucht wird, wird beim nächsten Aufruf
            wieder geholt — und geht dann als Anfrage an den jeweiligen Dienst.
          </p>
        </template>
      </div>
    </section>

    <section v-if="held" class="panel">
      <div class="panel__head"><h3>Grenzen</h3></div>
      <div class="panel__body stack">
        <dl class="figures">
          <div>
            <dt>Dienstaufrufe je Zugang</dt>
            <dd>{{ held.kontingent_aktiv ? num(held.kontingent_dienste, 0) : "aus" }}</dd>
            <p class="hint">je {{ windowText(held.kontingent_fenster_s) }}</p>
          </div>
          <div>
            <dt>Kartenkacheln je Zugang</dt>
            <dd>{{ held.kontingent_aktiv ? num(held.kontingent_kacheln, 0) : "aus" }}</dd>
            <p class="hint">je {{ windowText(held.kontingent_fenster_s) }}</p>
          </div>
          <div>
            <dt>Automatische Sperre</dt>
            <dd>{{ num(held.sperre_ab, 0) }}</dd>
            <p class="hint">
              Anfragen in {{ windowText(held.sperre_fenster_s) }} → {{ held.sperre_dauer_min }} Minuten
            </p>
          </div>
          <div>
            <dt>Aufbewahrung</dt>
            <dd>{{ held.aufbewahrung_tage }}</dd>
            <p class="hint">Tage für Zähler und Fehler</p>
          </div>
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
 * The operational page: what runs, what it costs on disk, what is scheduled,
 * and the one sentence the operator can put in front of everybody.
 *
 * Cards rather than a table throughout, and that is not decoration: a service
 * is a name, a state and a sentence explaining it, and a table turns the
 * sentence into the widest column in the room. The caches get bars because
 * their question is „how much of the budget", which a number cannot answer on
 * its own.
 */
import { adminAnnouncement, adminClearCache, adminJobs, adminServices, adminStartJob, backendHealth, putAnnouncement } from "../../lib/api.js";
import { bytes, moment, num } from "../../lib/format.js";

/** The health endpoint speaks in ids; a page speaks German. An unknown id is
 *  shown as it is — a new service must not disappear from this list. */
const LABELS = {
  alkis: "Kataster (ALKIS)",
  gemarkungen: "Gemarkungsverzeichnis",
  hauskoordinaten: "Amtliche Hauskoordinaten",
  boris: "Bodenrichtwerte (BORIS)",
  luis: "Umweltdaten (LUIS)",
  luftqualitaet: "Luftqualität (UBA)",
  motis: "Routing (MOTIS)",
  poi: "Umgebungsverzeichnis",
  tiles: "Kartenkacheln (WMS)",
  basemap: "Hintergrundkarte",
  texterkennung: "Texterkennung (OCR)",
  anmeldung: "Anmeldung",
  kontingent: "Abrufkontingent",
  speicher: "Serverspeicher",
  llm: "Modell"
};

export default {
  name: "AdminOperations",
  data() {
    return {
      held: null,
      health: null,
      jobs: null,
      notice: { text: "", art: "hinweis", sichtbar: false, bis: null },
      until: "",
      failure: "",
      done: "",
      working: "",
      saving: false
    };
  },
  computed: {
    /* `/api/health` answers `null` when it cannot be reached at all and, in a
       test or against an older build, an object without `dienste`. Both are
       "nothing to draw" and neither may take the rest of the page down. */
    services() {
      return Array.isArray(this.health?.dienste) ? this.health.dienste : [];
    },
    configuredCount() {
      return this.services.filter(service => service.konfiguriert).length;
    }
  },
  created() { this.load(); },
  methods: {
    bytes,
    moment,
    num,
    label(name) { return LABELS[name] || name; },
    windowText(seconds) {
      const minutes = Math.round(seconds / 60);
      if (minutes < 60) return `${minutes} Minuten`;
      const hours = minutes / 60;
      return hours === 1 ? "Stunde" : `${num(hours, 0)} Stunden`;
    },
    /** How much of the whole cache budget one cache holds. */
    share(entry) {
      const limit = this.held?.cache_grenze_bytes || 0;
      if (!limit) return "0%";
      return `${Math.min(100, Math.max(1, (entry.bytes / limit) * 100)).toFixed(1)}%`;
    },

    async load() {
      this.failure = "";
      const [services, health, jobs, notice] = await Promise.allSettled([
        adminServices(),
        backendHealth(),
        adminJobs(),
        adminAnnouncement()
      ]);
      if (services.status === "fulfilled") this.held = services.value;
      else this.failure = services.reason.message;
      if (health.status === "fulfilled") this.health = health.value;
      if (jobs.status === "fulfilled") this.jobs = jobs.value;
      if (notice.status === "fulfilled") {
        this.notice = { ...notice.value };
        this.until = notice.value.bis ? String(notice.value.bis).slice(0, 16) : "";
      }
    },

    async saveNotice() {
      this.saving = true;
      this.failure = "";
      this.done = "";
      try {
        const saved = await putAnnouncement({
          text: this.notice.text,
          art: this.notice.art,
          sichtbar: this.notice.sichtbar,
          // An empty field means „bis jemand sie abschaltet", which is null
          // and not „sofort vorbei".
          bis: this.until ? new Date(this.until).toISOString() : null
        });
        this.notice = { ...saved };
        this.done = saved.sichtbar ? "Die Ansage steht jetzt über jeder Seite." : "Die Ansage ist aus.";
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.saving = false;
      }
    },

    async startJob(job) {
      const sure = window.confirm(
        `„${job.name}“ jetzt anfordern? Der Scheduler holt ihn beim nächsten Durchlauf ab.`
      );
      if (!sure) return;
      this.working = job.name;
      this.failure = "";
      this.done = "";
      try {
        await adminStartJob(job.name);
        this.done = `„${job.name}“ ist angefordert.`;
        this.jobs = await adminJobs();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.working = "";
      }
    },

    async clearCache(entry) {
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
        this.held = await adminServices();
      } catch (error) {
        this.failure = error.message;
      } finally {
        this.working = "";
      }
    }
  }
};
</script>

<style scoped>
.cards{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3);
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.card{ border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); padding: var(--w2b-space-3); }
.card--off{ background: var(--w2b-surface-sunken); }
.card__head{ display: flex; align-items: center; gap: var(--w2b-space-2); }
.card__dot{ width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
.card__dot--on{ background: var(--w2b-good); }
.card__dot--off{ background: var(--w2b-line); }
.card__state{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.card__state--bad{ color: var(--w2b-error); }
.card__hint{ margin: var(--w2b-space-2) 0 0; font-size: var(--w2b-text-s); }
.card__endpoint{
  margin: var(--w2b-space-1) 0 var(--w2b-space-2); font-family: var(--w2b-font-mono);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted); overflow-wrap: anywhere;
}
.bars{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3); }
.bars__line{ display: flex; align-items: center; gap: var(--w2b-space-2); }
.bars__value{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); font-variant-numeric: tabular-nums; }
.bars__track{ height: 6px; border-radius: var(--w2b-radius-full); background: var(--w2b-surface-sunken); margin-top: 4px; }
.bars__fill{ height: 100%; border-radius: var(--w2b-radius-full); background: var(--w2b-primary-light); }
.figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--w2b-space-4); margin: 0; }
.figures dt{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.figures dd{ margin: 0; font-size: var(--w2b-text-l, 1.25rem); font-family: var(--w2b-font-display); }
.figures .hint{ margin: 0; }
.field{ display: flex; flex-direction: column; gap: var(--w2b-space-1); font-size: var(--w2b-text-s); }
.field--inline{ max-width: 16rem; }
.field--check{ flex-direction: row; align-items: center; gap: var(--w2b-space-2); }
.row--wrap{ flex-wrap: wrap; align-items: end; }
.chip--alarm{ background: var(--w2b-error-surface); color: var(--w2b-error); }
</style>
