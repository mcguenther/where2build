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

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/print.css";

import { createApp } from "vue";
import App from "./App.vue";

createApp(App).mount("#app");
