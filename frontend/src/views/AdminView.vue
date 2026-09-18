<template>
  <div class="stack">
    <nav class="breadcrumb" aria-label="Pfad">
      <RouterLink :to="{ name: 'home' }">Start</RouterLink>
      <span>Verwaltung</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Betrieb dieser Instanz</p>
        <h1>Verwaltung</h1>
        <p class="page-head__sub">
          Was hier läuft, wer es benutzt, und was sich daran ändern lässt.
        </p>
      </div>
    </div>

    <!-- Not signed in, not an administrator, or no sign-in in this deployment
         at all: three different things, and each says which it is rather than
         showing one empty page. -->
    <section v-if="!allowed" class="panel">
      <div class="panel__body stack">
        <p v-if="checking" class="hint">Wird geprüft …</p>
        <template v-else-if="!state.account.eingerichtet">
          <p>
            In diesem Betrieb ist keine Anmeldung eingerichtet, es gibt also auch keine
            Verwalter. Ohne Anmeldung und ohne Datenbank hält diese Anwendung nichts,
            was zu verwalten wäre.
          </p>
        </template>
        <template v-else-if="!state.account.angemeldet">
          <p>Dieser Bereich ist nur angemeldet zu sehen.</p>
          <p><a class="btn btn--secondary" :href="signInHref" @click.prevent="signIn">Anmelden</a></p>
        </template>
        <template v-else>
          <p>
            Dieses Konto ist kein Verwalter dieser Instanz. Das Recht vergibt ein anderer
            Verwalter — oder der Betreiber trägt die Kennung in <code>ADMIN_ACCOUNTS</code> ein.
          </p>
          <p class="hint">Die Kennung dieses Kontos: <code>{{ state.account.kennung }}</code></p>
        </template>
      </div>
    </section>

    <template v-else>
      <!-- Each area has an address of its own, so a reload stays where it was
           and a link into „Konten" leads there. -->
      <nav class="areas" aria-label="Bereiche der Verwaltung">
        <RouterLink v-for="area in AREAS" :key="area.id"
                    :to="{ name: 'admin', params: { bereich: area.id } }"
                    :aria-current="area.id === current ? 'page' : null">{{ area.label }}</RouterLink>
      </nav>

      <component :is="component" :key="current" />
    </template>
  </div>
</template>

<script>
/**
 * The administration area: one shell, one area at a time.
 *
 * Reachable only with the flag from `/api/auth/me`, and that is a courtesy
 * rather than a lock — every route behind it asks the server again, where the
 * answer cannot be edited in a console. What this page must not do is redirect
 * somebody away: a person whose account lost the flag, or who arrives before
 * the answer does, gets a sentence saying which of the three states they are
 * in, not a bounce to the start page that reads like a broken link.
 */
import { state, loadAccount } from "../lib/store.js";
import { signInUrl } from "../lib/api.js";
import { beginSignIn } from "../lib/signIn.js";
import AdminOverview from "../components/admin/AdminOverview.vue";
import AdminStats from "../components/admin/AdminStats.vue";
import AdminAccounts from "../components/admin/AdminAccounts.vue";
import AdminServices from "../components/admin/AdminServices.vue";
import AdminShares from "../components/admin/AdminShares.vue";
import AdminErrors from "../components/admin/AdminErrors.vue";
import AdminAudit from "../components/admin/AdminAudit.vue";
import AdminDanger from "../components/admin/AdminDanger.vue";

/** The areas, in the order somebody works through them: what is there, what it
 *  did, who did it, what it runs on — and the dangerous end, last. */
export const AREAS = [
  { id: "uebersicht", label: "Übersicht", component: AdminOverview },
  { id: "statistik", label: "Statistik", component: AdminStats },
  { id: "konten", label: "Konten", component: AdminAccounts },
  { id: "dienste", label: "Dienste", component: AdminServices },
  { id: "freigaben", label: "Freigaben", component: AdminShares },
  { id: "fehler", label: "Fehler", component: AdminErrors },
  { id: "protokoll", label: "Protokoll", component: AdminAudit },
  { id: "gefahrenzone", label: "Gefahrenzone", component: AdminDanger }
];

export default {
  name: "AdminView",
  props: { bereich: { type: String, default: "" } },
  data() {
    return { state, AREAS, checking: !state.account.eingerichtet };
  },
  computed: {
    allowed() { return state.account.verwalter === true; },
    current() {
      return AREAS.some(area => area.id === this.bereich) ? this.bereich : AREAS[0].id;
    },
    component() {
      return (AREAS.find(area => area.id === this.current) || AREAS[0]).component;
    },
    signInHref() { return signInUrl(this.$route.fullPath); }
  },
  async created() {
    // The header asks this too, but a reload that lands straight on this page
    // may get here first — and the difference between „nicht angemeldet" and
    // „kein Verwalter" is the whole content of the panel above.
    if (!state.account.eingerichtet) {
      await loadAccount();
      this.checking = false;
    }
  },
  methods: {
    signIn() { return beginSignIn(this.$route.fullPath); }
  }
};
</script>

<style scoped>
.areas{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-1); border-bottom: 1px solid var(--w2b-line); }
.areas a{
  padding: var(--w2b-space-2) var(--w2b-space-3);
  border-bottom: 2px solid transparent;
  color: var(--w2b-graphite);
  text-decoration: none;
  font-size: var(--w2b-text-s);
}
.areas a:hover{ color: var(--w2b-primary); }
.areas a[aria-current="page"]{ border-bottom-color: var(--w2b-primary); color: var(--w2b-primary); font-weight: 600; }
</style>
