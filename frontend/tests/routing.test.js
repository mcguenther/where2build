/**
 * The addresses themselves: what a reload lands on, what a shared link opens,
 * and what the back button does. The whole app is mounted for these — the
 * router is only the source of truth for navigation if the shell obeys it.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory } from "vue-router";
import App from "../src/App.vue";
import { createAppRouter } from "../src/router/index.js";
import { WIZARD_STAGES } from "../src/router/stages.js";
import { state } from "../src/lib/store.js";
import { realState } from "./helpers.js";
import PlotsView from "../src/views/PlotsView.vue";

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

/** The app as a reload leaves it: a fresh router, opened at one address.
 *  The plan is stubbed — a backdrop is a MapLibre instance, and these tests are
 *  about addresses, not about the drawing. */
async function openApp(path) {
  const router = createAppRouter(createMemoryHistory());
  router.push(path);
  await router.isReady();
  const app = mount(App, { global: { plugins: [router], stubs: { SitePlan: true } } });
  await flushPromises();
  return { app, router };
}

const currentView = app => app.findComponent({ name: "App" }).vm.$route.name;

describe("Adressen", () => {
  it("führt jede Ansicht unter ihrer eigenen Adresse", async () => {
    // A phrase that only that view shows — the navigation stands on every page.
    const addresses = [
      ["/", "plots", "Meine Grundstücke"],
      ["/vergleich", "compare", "Gleicher Maßstab, gleiche Ausrichtung"],
      ["/haustypen", "houseTypes", "Der Katalog gilt für alle Grundstücke"],
      ["/ziele", "destinations", "Hinterlegte Ziele"],
      ["/daten", "data", "Sicherung und Umzug"],
      ["/aufnahme/quelle", "wizard", "Welcher passt zu dem, was vorliegt?"],
      ["/grundstueck/plot-concave", "plot", "Abstandsflächen"]
    ];
    for (const [path, name, heading] of addresses) {
      const { app, router } = await openApp(path);
      expect(router.currentRoute.value.name, path).toBe(name);
      expect(app.text(), path).toContain(heading);
      // What a reload does: the address stays what it was.
      expect(router.currentRoute.value.fullPath).toBe(path);
    }
  });

  it("schickt /aufnahme auf den ersten Schritt", async () => {
    const { router } = await openApp("/aufnahme");
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/quelle");
  });

  it("hebt den Bereich hervor, zu dem die Seite gehört", async () => {
    for (const path of ["/", "/vergleich", "/aufnahme/quelle", "/grundstueck/plot-concave"]) {
      const { app } = await openApp(path);
      const current = app.findAll(".main-nav a").filter(a => a.attributes("aria-current") === "page");
      expect(current, path).toHaveLength(1);
      expect(current[0].text(), path).toContain("Grundstücke");
    }
    const { app } = await openApp("/daten");
    expect(app.find('.main-nav a[aria-current="page"]').text()).toContain("Daten");
  });

  it("erklärt eine unbekannte Adresse auf Deutsch", async () => {
    const { app } = await openApp("/gibtsnicht");
    expect(app.text()).toContain("Diese Seite gibt es nicht");
    expect(app.text()).toContain("/gibtsnicht");
  });
});

describe("Verweis auf ein Grundstück", () => {
  it("öffnet das verlinkte Grundstück, nicht das erste", async () => {
    const { app, router } = await openApp("/grundstueck/plot-convex");
    expect(router.currentRoute.value.params.id).toBe("plot-convex");
    // The name of the linked plot, not of the first one in the document.
    expect(app.find("h1").text()).toBe(state.data.plots.find(p => p.id === "plot-convex").name);
  });

  it("erklärt ein Grundstück, das es hier nicht gibt, statt leer zu bleiben", async () => {
    const { app } = await openApp("/grundstueck/plot-gibtsnicht");
    const text = app.text();
    expect(text).toContain("Dieses Grundstück liegt nicht in diesem Browser");
    expect(text).toContain("plot-gibtsnicht");
    expect(text).toContain("Zur Übersicht");
    // Not a half-drawn plot page: no plan, no figures from another plot.
    expect(app.find(".plot-page").exists()).toBe(false);
  });

  it("erklärt sich auch, wenn der Stand gelöscht wurde", async () => {
    state.data = { version: 2, plots: [], houseTypes: [], destinations: [], selection: [] };
    const { app } = await openApp("/grundstueck/plot-concave");
    expect(app.text()).toContain("Dieses Grundstück liegt nicht in diesem Browser");
  });

  it("kommt mit dem Zurück-Knopf aus dem Grundstück zurück in die Übersicht", async () => {
    const { app, router } = await openApp("/");
    await router.push({ name: "plot", params: { id: "plot-concave" } });
    await flushPromises();
    expect(currentView(app)).toBe("plot");

    router.back();
    await flushPromises();
    expect(currentView(app)).toBe("plots");
    expect(app.text()).toContain("Meine Grundstücke");
  });
});

describe("Aufnahme", () => {
  /** Puts the wizard on a later stage the way the user does: with data. */
  const wizardWithDraft = async () => {
    const { app, router } = await openApp("/aufnahme/quelle");
    const wizard = app.findComponent({ name: "WizardView" });
    wizard.vm.readFields = [{ key: "adresse", label: "Adresse", value: "Muldentalstraße 4", source: "Test" }];
    wizard.vm.draft = { ...state.data.plots[0] };
    return { app, router, wizard };
  };

  it("gibt jedem Schritt eine eigene Adresse", async () => {
    const { router, wizard } = await wizardWithDraft();
    for (const [index, slug] of WIZARD_STAGES.entries()) {
      await router.push(`/aufnahme/${slug}`);
      await flushPromises();
      expect(wizard.vm.stageIndex).toBe(index);
    }
  });

  it("geht mit dem Zurück-Knopf des Browsers einen Schritt zurück, nicht hinaus", async () => {
    const { app, router, wizard } = await wizardWithDraft();
    wizard.vm.goToStage(1);
    await flushPromises();
    wizard.vm.goToStage(2);
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/flurstueck");

    router.back();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/werte");
    expect(currentView(app)).toBe("wizard");

    router.back();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/quelle");
    expect(currentView(app)).toBe("wizard");
  });

  it("nimmt der Zurück-Schaltfläche denselben Weg wie dem Browser", async () => {
    const { router, wizard } = await wizardWithDraft();
    wizard.vm.goToStage(1);
    await flushPromises();
    wizard.vm.goToStage(2);
    await flushPromises();

    wizard.vm.stepBack(1);
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/werte");

    // It stepped out of the entry instead of pushing a new one: the stage it
    // came from is still ahead, where the browser's forward button expects it.
    router.forward();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/flurstueck");
  });

  it("sagt beim Neuladen eines späteren Schritts, dass der Entwurf fort ist", async () => {
    const { app, router } = await openApp("/aufnahme/flurstueck");
    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/quelle");
    expect(app.text()).toContain("Der begonnene Entwurf ist nicht mehr vorhanden");
    expect(app.text()).toContain("Welcher passt zu dem, was vorliegt?");
  });

  it("kennt keinen erfundenen Schritt", async () => {
    const { app } = await openApp("/aufnahme/quatsch");
    expect(app.text()).toContain("Diese Seite gibt es nicht");
  });
});

describe("Auswahl für den Vergleich", () => {
  it("überlebt „Alle auswählen“ einen Neuladen", async () => {
    // /vergleich is a link someone can open cold. A selection that is not
    // written down is gone by then, and the page then honestly reports
    // "nothing selected" — which hides the fact that the click did nothing.
    const { router } = await openApp("/");
    localStorage.clear();
    state.data = realState();

    const view = mount(PlotsView, { global: { plugins: [router] } });
    // The selection buttons live in the comparison mode now; opening a plot is
    // what the overview offers first.
    await view.find(".compare-toggle").trigger("click");
    await view.findAll("button").find(b => b.text() === "Alle auswählen").trigger("click");

    expect(state.data.selection).toHaveLength(state.data.plots.length);
    const stored = JSON.parse(localStorage.getItem(
      Object.keys(localStorage).find(k => (localStorage.getItem(k) || "").startsWith("{"))
    ));
    expect(stored.selection).toHaveLength(state.data.plots.length);
  });

  it("schreibt auch das Aufheben der Auswahl weg", async () => {
    const { router } = await openApp("/");
    localStorage.clear();
    state.data = realState();
    state.data.selection = state.data.plots.map(p => p.id);

    const view = mount(PlotsView, { global: { plugins: [router] } });
    await view.find(".compare-toggle").trigger("click");
    await view.findAll("button").find(b => b.text() === "Auswahl aufheben").trigger("click");

    const stored = JSON.parse(localStorage.getItem(
      Object.keys(localStorage).find(k => (localStorage.getItem(k) || "").startsWith("{"))
    ));
    expect(stored.selection).toEqual([]);
  });
});
