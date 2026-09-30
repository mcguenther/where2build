<template>
  <div class="shell">
    <!-- Fresh, on the way in, the header steps back: the sections all lead to
         empty pages and their counters all read zero, so the navigation is
         furniture around a page whose whole job is the one field. What stays is
         what still does something -- the brand, the palette, and the way into
         an account. -->
    <header class="site-header no-print" :class="{ 'site-header--quiet': bareHeader }">
      <div class="container site-header__inner">
        <RouterLink class="brand" :to="{ name: 'home' }" aria-label="Zur Startseite">
          <svg viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
            <rect x="5.5" y="5.5" width="37" height="37" rx="3.5" fill="none"
                  stroke="var(--w2b-primary)" stroke-width="3" />
            <rect x="14.5" y="14.5" width="19" height="19" rx="2"
                  fill="var(--w2b-secondary)" transform="rotate(15 24 24)" />
          </svg>
          <span class="brand__word">where<b>2</b>build</span>
        </RouterLink>

        <nav v-if="!bareHeader" class="main-nav" aria-label="Bereiche">
          <RouterLink v-for="s in sections" :key="s.section" :to="s.to"
                      :aria-current="isCurrent(s.section) ? 'page' : null">
            {{ s.name }}<span v-if="s.count !== null" class="main-nav__count">{{ s.count }}</span>
          </RouterLink>
        </nav>

        <div class="spacer"></div>

        <div class="theme-switch" role="group" aria-label="Darstellung">
          <button v-for="t in themes" :key="t.id" type="button"
                  :aria-pressed="String(state.theme === t.id)"
                  @click="applyTheme(t.id)">{{ t.name }}</button>
        </div>

        <!-- The way into an account, in every state. Where no provider is
             configured there is nothing to press, so nothing is drawn here --
             but the start page then says so in words instead of the app being
             silent about it, which is what made this look broken. -->
        <div v-if="state.account.angemeldet" class="account">
          <!-- Only for whoever administers this instance. Beside the account
               rather than among the sections: it is about the deployment, not
               about a part of somebody's work. -->
          <RouterLink v-if="state.account.verwalter" class="account__admin"
                      :to="{ name: 'admin' }"
                      :aria-current="$route.meta.section === 'admin' ? 'page' : null">Verwaltung</RouterLink>
          <!-- The name is the way to the account page: what is stored, and how
               to get rid of it. A section of its own would put it beside the
               work, which is not what it is about. -->
          <RouterLink class="account__link" :to="{ name: 'account' }"
                      :title="`Konto von ${state.account.name || 'dieser Anmeldung'}`">
            <span class="account__initials" aria-hidden="true">{{ initials }}</span>
            <span class="account__name">{{ state.account.name || "Angemeldet" }}</span>
          </RouterLink>
          <button type="button" class="btn btn--quiet btn--small" @click="leave">Abmelden</button>
        </div>
        <a v-else-if="state.account.eingerichtet" class="btn btn--secondary btn--small"
           :href="signInHref" @click.prevent="signIn">Anmelden</a>
      </div>
    </header>

    <!-- What the operator has to say, if anything. Above the work and below
         the header: a maintenance window is not a section of the application,
         and a banner nobody sees is not a banner. -->
    <div v-if="notice.sichtbar && notice.text" class="ansage no-print"
         :class="{ 'ansage--warnung': notice.art === 'warnung' }" role="status">
      <div class="container ansage__inner">
        <span class="ansage__mark" aria-hidden="true">{{ notice.art === "warnung" ? "!" : "i" }}</span>
        <p>{{ notice.text }}</p>
      </div>
    </div>

    <div v-if="state.sync.adoption" class="adoption no-print">
      <div class="container adoption__inner">
        <p>
          <b>In diesem Browser {{ state.sync.adoption.plots === 1 ? "liegt ein Grundstück" :
            `liegen ${state.sync.adoption.plots} Grundstücke` }}.</b>
          Ins Konto übernehmen? Der Stand liegt danach auf jedem Rechner, an dem diese
          Anmeldung gilt. Hier bleibt er ohnehin.
        </p>
        <div class="spacer"></div>
        <button type="button" class="btn btn--small" :disabled="state.sync.busy" @click="adoptLocal">
          {{ state.sync.busy ? "Wird übernommen …" : "Übernehmen" }}
        </button>
        <button type="button" class="btn btn--quiet btn--small" @click="declineAdoption">Hier lassen</button>
      </div>
    </div>

    <p v-if="state.sync.error" class="container sync-error no-print" role="alert">{{ state.sync.error }}</p>

    <main class="container">
      <RouterView />
    </main>

    <footer class="site-footer no-print">
      <div class="container site-footer__inner">
        <span>Amtliche Daten: © GeoSN, dl-de/by-2-0 · Bodenrichtwerte vom Gutachterausschuss</span>
        <span>Keine bauordnungsrechtliche Prüfung · keine Rechtsberatung</span>
      </div>
    </footer>

    <p class="print-footer print-only">
      where2build · Amtliche Daten © GeoSN, dl-de/by-2-0 ·
      Keine bauordnungsrechtliche Prüfung, keine Rechtsberatung.
    </p>
  </div>
</template>

<script>
import {
  state, applyTheme, loadAccount, loadFromAccount, adoptLocal, declineAdoption, isFresh,
  settleStoredStreetFronts
} from "./lib/store.js";
import { announcement, signInUrl, signOut } from "./lib/api.js";
import { beginSignIn } from "./lib/signIn.js";
import { wantedThumbnailGrounds } from "./lib/thumbnail.js";
import { warmBlocks } from "./lib/tileGround.js";

export default {
  name: "App",
  data() {
    return {
      state,
      themes: [
        { id: "light", name: "Hell" },
        { id: "dark", name: "Dunkel" },
        { id: "system", name: "System" }
      ],
      /* The operator's announcement. Empty and invisible is the normal state,
         which is why it starts that way rather than as null: nothing on the
         page moves while the answer is on its way. */
      notice: { text: "", art: "hinweis", sichtbar: false }
    };
  },
  async created() {
    // Not awaited before the account: the banner is the least urgent thing on
    // the page, and nothing else waits for it.
    announcement().then(answer => { this.notice = answer; });
    await loadAccount();
    // Only after the answer: which document is in force depends on whether
    // there is an account behind this browser at all.
    await loadFromAccount();
    // Plots stored before the street was read off the cadastre. Not awaited:
    // the page stands without it, and each plot redraws when its answer lands.
    settleStoredStreetFronts();
    // The thumbnails' ground, put into the backend's cache before a list or a
    // comparison draws it. A watch rather than a call in `addPlot`: the street
    // front settles after the plot is stored and turns the drawing, and
    // ticking a plot for comparison changes the scale every compared drawing
    // shares.
    this.$watch(() => wantedThumbnailGrounds(state.data.plots, state.data.selection),
      refs => warmBlocks(refs), { immediate: true });
  },
  computed: {
    /** Two letters off the display name, for the round mark beside it. */
    initials() {
      const name = (state.account.name || "").trim();
      if (!name) return "?";
      const parts = name.split(/\s+/).filter(Boolean);
      const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : name.slice(0, 2);
      return letters.toUpperCase();
    },
    /** Signing in comes back to the page it started on. */
    signInHref() { return signInUrl(this.$route.fullPath); },
    /** The reduced header: nothing entered yet, and standing on the page that
     *  greets somebody. Anywhere else the sections are the way back. */
    bareHeader() { return isFresh() && this.$route.name === "home"; },
    sections() {
      return [
        { section: "home", to: { name: "home" }, name: "Start", count: null },
        { section: "plots", to: { name: "plots" }, name: "Grundstücke", count: state.data.plots.length },
        { section: "houseTypes", to: { name: "houseTypes" }, name: "Haustypen", count: state.data.houseTypes.length },
        { section: "destinations", to: { name: "destinations" }, name: "Ziele", count: state.data.destinations.length },
        { section: "data", to: { name: "data" }, name: "Daten", count: null }
      ];
    }
  },
  methods: {
    /** Signing in runs in a window of its own, so this page stays standing --
     *  with whatever is half-entered on it. A refused window falls back to a
     *  full navigation; see lib/signIn.js. */
    signIn() { return beginSignIn(this.$route.fullPath); },
    applyTheme,
    /** Sign out and reload the answer rather than assuming it: the cookie is
     *  the backend's, and only it can say what is left of the session. */
    adoptLocal,
    declineAdoption,

    async leave() {
      await signOut().catch(() => {});
      await loadAccount();
      // The account's copy goes with the account: what stays is this
      // browser's, which is what an unsigned session has always worked on.
      await loadFromAccount();
    },

    /** Detail, wizard and comparison all live under "Grundstücke" in the
     *  navigation, so the current section comes from the route, not from the
     *  link being the exact one that was followed. */
    isCurrent(section) { return this.$route.meta.section === section; }
  }
};
</script>

<style scoped>
/* `overflow-x: clip` and not `hidden`: the start page's reception is a
   `100vw` breakout out of the 1360 px container, and on a window with a
   classic scrollbar `100vw` is wider than the page by exactly that scrollbar.
   Clipping swallows the overshoot without making this a scroll container, so
   nothing inside loses `position: sticky`. */
.shell{ min-height: 100vh; display: flex; flex-direction: column; overflow-x: clip; }
main{ flex: 1; padding-top: var(--w2b-space-5); }

.site-header{ background: var(--w2b-surface); border-bottom: 1px solid var(--w2b-line); }
/* Reduced: the same surface as the reception below it and no rule between the
   two, so header and hero read as one field rather than as a bar sitting on
   top of a page. It keeps its height, because the brand and the palette are
   still in it and a collapsing header would shift the whole page. */
.site-header--quiet{ border-bottom-color: transparent; }
.site-header__inner{
  display: flex; align-items: center; gap: var(--w2b-space-4) var(--w2b-space-5);
  flex-wrap: wrap; padding-top: var(--w2b-space-3); padding-bottom: var(--w2b-space-3);
}

.brand{
  display: flex; align-items: center; gap: 10px;
  background: none; border: 0; padding: 0; cursor: pointer; text-decoration: none;
}
.brand__word{
  font-family: var(--w2b-font-display); font-weight: 700; font-size: 21px;
  letter-spacing: -.035em; color: var(--w2b-ink);
}
.brand__word b{ color: var(--w2b-secondary-text); }

.main-nav{ display: flex; gap: var(--w2b-space-1); flex-wrap: wrap; min-width: 0; }
.main-nav a{
  display: flex; align-items: center; gap: 7px;
  background: none; border: 0; cursor: pointer; text-decoration: none;
  padding: 7px 13px; border-radius: var(--w2b-radius-s);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 14.5px;
  color: var(--w2b-graphite);
}
.main-nav a:hover{ background: var(--w2b-primary-veil); color: var(--w2b-ink); }
.main-nav a[aria-current="page"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.main-nav__count{
  font-family: var(--w2b-font-mono); font-size: 10.5px; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-line-faint); color: var(--w2b-muted);
}
.main-nav a[aria-current="page"] .main-nav__count{
  background: rgba(255,255,255,.18); color: var(--w2b-primary-on);
}

.theme-switch{ display: flex; border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); overflow: hidden; }
.theme-switch button{
  background: var(--w2b-surface); border: 0; cursor: pointer; padding: 6px 11px;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  color: var(--w2b-muted);
}
.theme-switch button + button{ border-left: 1px solid var(--w2b-line); }
.theme-switch button[aria-pressed="true"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }

.adoption{ background: var(--w2b-secondary-light); border-bottom: 1px solid var(--w2b-line); }
.adoption__inner{
  display: flex; align-items: center; gap: var(--w2b-space-3); flex-wrap: wrap;
  padding-top: var(--w2b-space-3); padding-bottom: var(--w2b-space-3);
  font-size: var(--w2b-text-s); color: var(--w2b-secondary-text);
}
.sync-error{ padding-top: var(--w2b-space-3); font-size: var(--w2b-text-s); color: var(--w2b-error); }

.account{ display: flex; align-items: center; gap: var(--w2b-space-2); }
/* A link, not a button: it goes to a page like the name beside it does. */
.ansage{ background: var(--w2b-secondary-veil); border-bottom: 1px solid var(--w2b-line); }
.ansage--warnung{ background: var(--w2b-error-surface); }
.ansage__inner{ display: flex; gap: var(--w2b-space-3); align-items: baseline; padding: var(--w2b-space-2) 0; }
.ansage__inner p{ margin: 0; }
.ansage__mark{
  display: grid; place-items: center; width: 20px; height: 20px; flex: 0 0 auto;
  border-radius: var(--w2b-radius-full); font-family: var(--w2b-font-display); font-size: var(--w2b-text-xs);
  background: var(--w2b-secondary); color: var(--w2b-white);
}
.ansage--warnung .ansage__mark{ background: var(--w2b-error); }

.account__admin{
  font-size: var(--w2b-text-xs);
  color: var(--w2b-primary);
  text-decoration: none;
  border: 1px solid var(--w2b-line);
  border-radius: var(--w2b-radius-full);
  padding: 2px var(--w2b-space-2);
  white-space: nowrap;
}
.account__admin:hover{ border-color: var(--w2b-primary); }
.account__admin[aria-current="page"]{ background: var(--w2b-primary-veil); border-color: var(--w2b-primary); }
.account__initials{
  display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-primary); color: var(--w2b-primary-on);
  font-family: var(--w2b-font-display); font-weight: 700; font-size: 12px;
}
.account__link{
  display: flex; align-items: center; gap: var(--w2b-space-2);
  text-decoration: none; border-radius: var(--w2b-radius-s);
}
.account__link:hover .account__name{ color: var(--w2b-primary); }
.account__name{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
a.btn{ text-decoration: none; display: inline-flex; align-items: center; }

.site-footer{ border-top: 1px solid var(--w2b-line); margin-top: var(--w2b-space-8); }
.site-footer__inner{
  display: flex; justify-content: space-between; gap: var(--w2b-space-4); flex-wrap: wrap;
  padding-top: var(--w2b-space-4); padding-bottom: var(--w2b-space-4);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}

@media (max-width: 560px){
  /* The name is the first thing to go: the mark beside it says the same. */
  .account__name{ display: none; }
  .brand__word{ font-size: 18px; }
  .main-nav a{ padding: 6px 10px; font-size: 13.5px; }
}
</style>
