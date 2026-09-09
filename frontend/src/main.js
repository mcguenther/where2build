// Fontsource: only the weights actually used, imported individually
// so the fonts are bundled locally (no CDN requests at runtime).
import "@fontsource/archivo/400.css";
import "@fontsource/archivo/600.css";
import "@fontsource/archivo/700.css";
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/print.css";

/* MapLibre resolves its worker as a file next to its own module. After
 * bundling that is the app chunk, where no such file exists: the request 404s,
 * vector tiles are never parsed, and the map stays blank without raising a
 * single error. Vite emits the worker as its own asset here, and MapLibre is
 * told where it landed. */
import { setWorkerUrl } from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

import { createApp } from "vue";
import { createWebHistory } from "vue-router";
import App from "./App.vue";
import { createAppRouter } from "./router/index.js";
import { load, flushSave } from "./lib/store.js";

setWorkerUrl(mapWorkerUrl);

/* Before the first route is resolved: a link straight to a plot has to find
 * that plot in the document, and the document lives in this browser. */
load();

/* Writes to the account are collected and land a moment after the hand comes
 * to rest. Leaving the page is the one moment that cannot wait, and
 * `pagehide` is the event that actually fires on a phone, where the tab is
 * frozen rather than closed. */
window.addEventListener("pagehide", () => { flushSave(); });
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushSave();
});

createApp(App)
  .use(createAppRouter(createWebHistory(import.meta.env.BASE_URL)))
  .mount("#app");
