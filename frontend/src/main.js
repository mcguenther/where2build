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
import App from "./App.vue";

setWorkerUrl(mapWorkerUrl);

createApp(App).mount("#app");
