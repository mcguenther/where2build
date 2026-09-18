<template>
  <div class="stack">
    <p v-if="failure" class="notice notice--error" role="alert">{{ failure }}</p>

    <section class="panel">
      <div class="panel__head">
        <h3>Bestand</h3>
        <div class="spacer"></div>
        <span v-if="held" class="chip">{{ bytes(held.datenbank_bytes) }} Datenbank</span>
      </div>
      <div class="panel__body">
        <p v-if="busy" class="hint">Wird geladen …</p>
        <dl v-else-if="held" class="figures">
          <div><dt>Konten</dt><dd>{{ held.konten }}</dd></div>
          <div><dt>Grundstücke</dt><dd>{{ held.grundstuecke }}</dd></div>
          <div><dt>Offene Freigaben</dt><dd>{{ held.freigaben }}</dd></div>
          <div><dt>Gesperrte Konten</dt><dd :class="{ 'figures__alarm': held.sperren > 0 }">{{ held.sperren }}</dd></div>
          <div><dt>Verwalter</dt><dd>{{ held.verwalter + held.aus_konfiguration }}</dd></div>
          <div><dt>Zwischenspeicher</dt><dd>{{ bytes(held.cache_bytes) }}</dd></div>
        </dl>
        <p v-if="held && held.aus_konfiguration > 0" class="hint">
          Davon {{ held.aus_konfiguration }} aus der Konfiguration (ADMIN_ACCOUNTS). Diese
          stehen nicht in der Datenbank und bleiben deshalb auch nach einem Leeren bestehen.
        </p>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head"><h3>Dienste</h3></div>
      <div class="panel__body">
        <p v-if="!health" class="hint">Der Zustand der Dienste wird geladen …</p>
        <ul v-else class="lights">
          <li v-for="service in health.dienste" :key="service.name">
            <span class="lights__dot" :class="service.konfiguriert ? 'lights__dot--on' : 'lights__dot--off'"
                  :aria-hidden="true"></span>
            <div>
              <b>{{ service.name }}</b>
              <span class="lights__state">{{ service.konfiguriert ? "eingerichtet" : "nicht eingerichtet" }}</span>
              <p class="hint">{{ service.hinweis }}</p>
            </div>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * The first page of the area: how much there is, and what is switched on.
 *
 * The traffic lights come from `/api/health`, which the backend already
 * answers for everybody — a second endpoint saying the same thing would be a
 * second thing to keep in step. „eingerichtet" is what it can say and all it
 * can say: whether a service answers today is what the error list is for.
 */
import { adminOverview, backendHealth } from "../../lib/api.js";
import { bytes } from "../../lib/format.js";

export default {
  name: "AdminOverview",
  data() {
    return { held: null, health: null, busy: false, failure: "" };
  },
  created() { this.load(); },
  methods: {
    bytes,
    async load() {
      this.busy = true;
      this.failure = "";
      try {
        [this.held, this.health] = await Promise.all([adminOverview(), backendHealth()]);
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
.figures{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--w2b-space-4); margin: 0; }
.figures dt{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.figures dd{ margin: 0; font-size: var(--w2b-text-xl, 1.6rem); font-family: var(--w2b-font-display); }
.figures__alarm{ color: var(--w2b-error); }
.lights{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--w2b-space-3); }
.lights li{ display: flex; gap: var(--w2b-space-3); align-items: start; }
.lights__dot{ width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex: 0 0 auto; }
.lights__dot--on{ background: var(--w2b-good); }
.lights__dot--off{ background: var(--w2b-line); }
.lights__state{ margin-left: var(--w2b-space-2); font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.lights .hint{ margin: 2px 0 0; }
</style>
