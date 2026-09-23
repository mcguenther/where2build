<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <!-- „Ist alles in Ordnung?" — die eine Frage, mit der jemand diesen Bereich
         öffnet. Eine Zeile je Sache, jede mit dem Weg dorthin, wo sich etwas
         daran tun lässt. Die Einzelheiten stehen dort und nicht hier: doppelt
         geführte Listen driften. -->
    <section class="panel">
      <div class="panel__head">
        <h3>Zustand</h3>
        <div class="spacer"></div>
        <span class="chip" :class="{ 'chip--alarm': attention > 0 }">
          {{ attention === 0 ? "nichts Auffälliges" : `${attention} zu sehen` }}
        </span>
      </div>
      <div class="panel__body">
        <ul class="state">
          <li v-for="row in state" :key="row.id">
            <span class="state__dot" :class="`state__dot--${row.art}`" aria-hidden="true"></span>
            <div class="state__text">
              <b>{{ row.titel }}</b>
              <p class="hint">{{ row.text }}</p>
            </div>
            <div class="spacer"></div>
            <RouterLink class="state__link" :to="{ name: 'admin', params: { bereich: row.bereich } }">
              {{ row.ziel }}
            </RouterLink>
          </li>
        </ul>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Letzte 24 Stunden</h3>
        <div class="spacer"></div>
        <RouterLink class="state__link" :to="{ name: 'admin', params: { bereich: 'statistik' } }">
          Statistik
        </RouterLink>
      </div>
      <div class="panel__body stack">
        <p v-if="!day || !day.summe" class="hint">Wird geladen …</p>
        <template v-else>
          <UsageChart :points="series" raster="stunde" flach title="Anfragen je Stunde" />
          <dl class="figures">
            <div><dt>Anfragen</dt><dd>{{ num(day.summe.anfragen, 0) }}</dd></div>
            <div>
              <dt>Fehler</dt>
              <dd :class="{ 'figures__alarm': day.summe.fehler > 0 }">{{ num(day.summe.fehler, 0) }}</dd>
            </div>
            <div><dt>Ø Dauer</dt><dd>{{ meanDuration }}</dd></div>
            <div><dt>Tokens</dt><dd>{{ tokens }}</dd></div>
            <div><dt>Kosten Modell</dt><dd>{{ money(day.summe.kosten_eur) }}</dd></div>
            <div><dt>Suchen</dt><dd>{{ num(searches.gesamt, 0) }}</dd></div>
          </dl>
          <p v-if="searches.gesamt > 0" class="hint">{{ searches.text }}</p>
        </template>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <h3>Bestand</h3>
        <div class="spacer"></div>
        <span v-if="held" class="chip">{{ bytes(held.datenbank_bytes) }} Datenbank</span>
      </div>
      <div class="panel__body stack">
        <p v-if="!held || held.konten === undefined" class="hint">Wird geladen …</p>
        <template v-else>
          <dl class="figures">
            <div><dt>Konten</dt><dd>{{ num(held.konten, 0) }}</dd></div>
            <div><dt>Grundstücke</dt><dd>{{ num(held.grundstuecke, 0) }}</dd></div>
            <div><dt>Offene Freigaben</dt><dd>{{ num(held.freigaben, 0) }}</dd></div>
            <div>
              <dt>Gesperrte Konten</dt>
              <dd :class="{ 'figures__alarm': held.sperren > 0 }">{{ num(held.sperren, 0) }}</dd>
            </div>
            <div><dt>Verwalter</dt><dd>{{ held.verwalter + held.aus_konfiguration }}</dd></div>
            <div><dt>Zwischenspeicher</dt><dd>{{ bytes(held.cache_bytes) }}</dd></div>
          </dl>
          <p v-if="held.aus_konfiguration > 0" class="hint">
            Davon {{ held.aus_konfiguration }} aus der Konfiguration (ADMIN_ACCOUNTS). Diese
            stehen nicht in der Datenbank und bleiben deshalb auch nach einem Leeren bestehen.
          </p>
        </template>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The first page: is anything wrong, what happened today, and how much is here.
 *
 * It used to carry the full list of services as well, which the operations
 * page now draws properly — the same list in two places is two places to keep
 * in step, and the one that was here was the worse of the two. What is left is
 * what a first page is for: one line per thing that could need attention, each
 * with the way to where it can be acted on, and the numbers nobody has to
 * navigate for.
 *
 * Every panel loads on its own and fails on its own: without a database the
 * counts and the statistics are gone, and the service lights and the scheduler
 * are still there to say so.
 */
import UsageChart from "./UsageChart.vue";
import {
  adminAnnouncement,
  adminJobs,
  adminOverview,
  adminStatistics,
  backendHealth
} from "../../lib/api.js";
import { bytes, num } from "../../lib/format.js";
import { fillSeries, rangeFor } from "../../lib/period.js";

/** The German names of the services, as the operations page has them. */
const LABELS = {
  alkis: "Kataster",
  gemarkungen: "Gemarkungen",
  hauskoordinaten: "Hauskoordinaten",
  boris: "Bodenrichtwerte",
  luis: "Umweltdaten",
  luftqualitaet: "Luftqualität",
  motis: "Routing",
  poi: "Umgebungsverzeichnis",
  tiles: "Kartenkacheln",
  basemap: "Hintergrundkarte",
  texterkennung: "Texterkennung",
  anmeldung: "Anmeldung",
  kontingent: "Abrufkontingent",
  speicher: "Serverspeicher",
  llm: "Modell"
};

const OUTCOMES = { bestaetigt: "bestätigt", mehrdeutig: "mehrdeutig", erfolglos: "erfolglos", abgebrochen: "abgebrochen" };

export default {
  name: "AdminOverview",
  components: { UsageChart },
  data() {
    return {
      held: null,
      health: null,
      jobs: null,
      day: null,
      notice: null,
      period: rangeFor("day"),
      failure: ""
    };
  },
  computed: {
    services() {
      return Array.isArray(this.health?.dienste) ? this.health.dienste : [];
    },
    series() {
      return Array.isArray(this.day?.zeitreihe)
        ? fillSeries(this.day.zeitreihe, this.period.from, this.period.to, "stunde")
        : [];
    },
    tokens() {
      const total = (this.day?.summe?.tokens_ein || 0) + (this.day?.summe?.tokens_aus || 0);
      return total > 0 ? num(total, 0) : "—";
    },
    meanDuration() {
      const summe = this.day?.summe;
      // Ein Mittel über nichts ist nicht null, sondern nicht vorhanden.
      if (!summe?.anfragen) return "—";
      return `${num(Math.round(summe.dauer_ms / summe.anfragen), 0)} ms`;
    },
    searches() {
      const rows = (this.day?.nach_dienst || []).filter(row => row.bereich === "suche");
      const total = rows.reduce((sum, row) => sum + row.anfragen, 0);
      return {
        gesamt: total,
        text: rows
          .map(row => `${num(row.anfragen, 0)} ${OUTCOMES[row.dienst] || row.dienst}`)
          .join(", ")
      };
    },

    /** Eine Zeile je Sache, die Aufmerksamkeit brauchen kann. */
    state() {
      return [
        this.servicesRow(),
        this.jobsRow(),
        this.blocksRow(),
        this.errorsRow(),
        this.noticeRow()
      ];
    },
    /** Wie viele dieser Zeilen gerade etwas melden. */
    attention() {
      return this.state.filter(row => row.art === "warnung").length;
    }
  },
  created() { this.load(); },
  methods: {
    bytes,
    num,
    money(value) {
      return value === null || value === undefined ? "—" : `${num(value, value < 1 ? 4 : 2)} €`;
    },

    servicesRow() {
      const missing = this.services.filter(service => !service.konfiguriert);
      return {
        id: "dienste",
        titel: "Dienste",
        // „nicht eingerichtet" ist kein Fehler: Modell, OCR und das
        // Umgebungsverzeichnis sind Zusatz, und ein Betrieb ohne sie ist ein
        // vollständiger Betrieb. Deshalb hier nie eine Warnung, sondern die
        // Zahl und die Namen.
        art: this.services.length ? "ruhig" : "unbekannt",
        text: this.services.length
          ? `${this.services.length - missing.length} von ${this.services.length} eingerichtet` +
            (missing.length ? `; ohne: ${missing.map(s => LABELS[s.name] || s.name).join(", ")}` : "")
          : "Der Zustand der Dienste ließ sich nicht abfragen.",
        bereich: "betrieb",
        ziel: "Betrieb"
      };
    },

    jobsRow() {
      const failed = (this.jobs?.jobs || []).filter(job => job.exit_code !== null && job.exit_code !== 0);
      const pending = (this.jobs?.jobs || []).filter(job => job.angefordert);
      return {
        id: "laeufe",
        titel: "Wiederkehrende Läufe",
        // Ein fehlender Scheduler ist für sich kein Fehler -- das Profil ist
        // Zusatz. Er wird einer, sobald etwas auf ihn wartet.
        art: failed.length || (pending.length && !this.jobs?.scheduler_laeuft)
          ? "warnung"
          : this.jobs
            ? "ruhig"
            : "unbekannt",
        text: !this.jobs
          ? "Die Liste der Läufe ließ sich nicht abfragen."
          : [
              failed.length ? `Zuletzt fehlgeschlagen: ${failed.map(job => job.name).join(", ")}.` : "",
              this.jobs.scheduler_laeuft ? "Scheduler läuft." : "Kein Scheduler.",
              pending.length
                ? `${pending.length} ${pending.length === 1 ? "Lauf ist" : "Läufe sind"} angefordert` +
                  (this.jobs.scheduler_laeuft ? "." : " und bleiben liegen, bis einer startet.")
                : ""
            ]
              .filter(Boolean)
              .join(" "),
        bereich: "betrieb",
        ziel: "Betrieb"
      };
    },

    blocksRow() {
      const blocked = this.held?.sperren ?? null;
      return {
        id: "sperren",
        titel: "Sperren",
        art: blocked === null ? "unbekannt" : blocked > 0 ? "warnung" : "ruhig",
        text:
          blocked === null
            ? "Ohne Serverspeicher gibt es keine Sperrliste."
            : blocked === 0
              ? "Kein Konto ist gesperrt."
              : `${blocked} ${blocked === 1 ? "Konto ist" : "Konten sind"} gesperrt.`,
        bereich: "konten",
        ziel: "Konten"
      };
    },

    errorsRow() {
      const count = this.day?.summe?.fehler ?? null;
      return {
        id: "fehler",
        titel: "Fehler",
        art: count === null ? "unbekannt" : count > 0 ? "warnung" : "ruhig",
        text:
          count === null
            ? "Ohne Serverspeicher liegen keine Zähler vor."
            : count === 0
              ? "In den letzten 24 Stunden nichts."
              : `${num(count, 0)} in den letzten 24 Stunden.`,
        bereich: "fehler",
        ziel: "Fehler"
      };
    },

    noticeRow() {
      const shown = this.notice?.sichtbar && this.notice.text;
      return {
        id: "ansage",
        titel: "Betriebsansage",
        // Eine sichtbare Ansage ist nichts Schlimmes, aber sie steht über
        // jeder Seite — wer hier hereinkommt, soll wissen, dass sie läuft.
        art: shown ? "warnung" : this.notice ? "ruhig" : "unbekannt",
        text: shown
          ? `Wird angezeigt: „${this.notice.text}“`
          : this.notice
            ? "Keine Ansage geschaltet."
            : "Der Stand der Ansage ließ sich nicht abfragen.",
        bereich: "betrieb",
        ziel: "Betrieb"
      };
    },

    async load() {
      this.failure = "";
      const [counts, health, jobs, day, notice] = await Promise.allSettled([
        adminOverview(),
        backendHealth(),
        adminJobs(),
        adminStatistics(this.period.from, this.period.to, "stunde"),
        adminAnnouncement()
      ]);
      if (counts.status === "fulfilled") this.held = counts.value;
      else this.failure = counts.reason.message;
      if (health.status === "fulfilled") this.health = health.value;
      if (jobs.status === "fulfilled") this.jobs = jobs.value;
      if (day.status === "fulfilled") this.day = day.value;
      if (notice.status === "fulfilled") this.notice = notice.value;
    }
  }
};
</script>

<style scoped>
.figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: var(--w2b-space-4); margin: 0; }
.figures dt{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.figures dd{ margin: 0; font-size: var(--w2b-text-l, 1.25rem); font-family: var(--w2b-font-display); }
.figures__alarm{ color: var(--w2b-error); }

.state{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3); }
.state li{ display: flex; align-items: baseline; gap: var(--w2b-space-3); }
.state__dot{ width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
.state__dot--ruhig{ background: var(--w2b-good); }
.state__dot--warnung{ background: var(--w2b-warning); }
.state__dot--unbekannt{ background: var(--w2b-line); }
.state__text .hint{ margin: 0; }
.state__link{ font-size: var(--w2b-text-xs); white-space: nowrap; }
.chip--alarm{ background: var(--w2b-warning-surface); color: var(--w2b-warning-text); }
</style>
