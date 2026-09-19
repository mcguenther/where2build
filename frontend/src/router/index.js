/**
 * The route table. Every view has an address, so a reload keeps the user where
 * they were, a plot can be linked to, and the back button steps back through
 * the wizard instead of leaving it.
 *
 * The paths are German because the user reads them in the address bar and
 * pastes them to someone else — they are interface, like every other string on
 * screen. The names the code navigates by are English, and nothing outside this
 * file writes a path by hand.
 */
import { createRouter } from "vue-router";
import HomeView from "../views/HomeView.vue";
import PlotsView from "../views/PlotsView.vue";
import PlotView from "../views/PlotView.vue";
import WizardView from "../views/WizardView.vue";
import CompareView from "../views/CompareView.vue";
import HouseTypesView from "../views/HouseTypesView.vue";
import DestinationsView from "../views/DestinationsView.vue";
import LocationView from "../views/LocationView.vue";
import DataView from "../views/DataView.vue";
import AccountView from "../views/AccountView.vue";
import AdminView from "../views/AdminView.vue";
import SharedPlotView from "../views/SharedPlotView.vue";
import SignInDoneView from "../views/SignInDoneView.vue";
import NotFoundView from "../views/NotFoundView.vue";
import { WIZARD_STAGES, wizardStage } from "./stages.js";

/* `meta.section` is what the header highlights: the detail page, the wizard and
 * the comparison all belong under "Grundstücke". The start page is its own
 * section — it is where a search begins, not where the list lives. */
export const routes = [
  { path: "/", name: "home", component: HomeView, meta: { section: "home" } },
  { path: "/grundstuecke", name: "plots", component: PlotsView, meta: { section: "plots" } },
  { path: "/aufnahme", redirect: () => wizardStage(0) },
  {
    // An unknown stage is a typo, not a stage: it falls through to the 404 route.
    path: `/aufnahme/:stage(${WIZARD_STAGES.join("|")})`,
    name: "wizard",
    component: WizardView,
    props: true,
    meta: { section: "plots" }
  },
  { path: "/grundstueck/:id", name: "plot", component: PlotView, props: true, meta: { section: "plots" } },
  {
    path: "/grundstueck/:id/standort",
    name: "location",
    component: LocationView,
    props: true,
    meta: { section: "plots" }
  },
  // The surroundings map lives on the plot page itself now; the address it used
  // to have is kept because it was linkable, and leads there.
  {
    path: "/grundstueck/:id/umgebung",
    redirect: to => ({ name: "plot", params: { id: to.params.id } })
  },
  { path: "/vergleich", name: "compare", component: CompareView, meta: { section: "plots" } },
  { path: "/haustypen", name: "houseTypes", component: HouseTypesView, meta: { section: "houseTypes" } },
  { path: "/ziele", name: "destinations", component: DestinationsView, meta: { section: "destinations" } },
  { path: "/daten", name: "data", component: DataView, meta: { section: "data" } },
  /* Reached from the name in the header rather than from the sections: it is
     about the person, not about a part of the work. */
  { path: "/konto", name: "account", component: AccountView, meta: { section: "account" } },
  /* The administration area. One route with the area in the path, so a reload
     stays where it was and „Konten" can be linked to. No guard: what may be
     seen is decided by the backend on every request, and a guard here would
     only be able to redirect somebody away from the page that tells them why
     they are not allowed in. */
  {
    path: "/verwaltung/:bereich?",
    name: "admin",
    component: AdminView,
    props: true,
    meta: { section: "admin" }
  },
  /* A shared plot, open to anybody with the link.
     The trailing segment is a readable slug and is never read: the token is
     the whole address, so `/geteilt/AbC…` and
     `/geteilt/AbC…/wiesenstrasse-grossbothen` are the same page. Cut this way
     from the start so a slug can be added later without breaking the links
     already sent. */
  {
    path: "/geteilt/:token/:slug*",
    name: "shared",
    component: SharedPlotView,
    props: true,
    meta: { section: null }
  },
  /* Where the sign-in exchange ends. Normally seen by nobody: it runs in a
     window of its own, which closes here -- see lib/signIn.js. The path is
     the `ziel` the backend is given, so it has to be a route. */
  {
    path: "/anmeldung-fertig",
    name: "signInDone",
    component: SignInDoneView,
    meta: { section: null }
  },
  { path: "/:pathMatch(.*)*", name: "notFound", component: NotFoundView }
];

/**
 * The history is passed in: the browser gets `createWebHistory`, the tests get
 * `createMemoryHistory`.
 */
export const createAppRouter = history =>
  createRouter({
    history,
    routes,
    // Going back returns to where the page was left; every other navigation
    // starts at the top, which is what the views used to do by hand.
    scrollBehavior: (to, from, savedPosition) => savedPosition || { top: 0 }
  });
