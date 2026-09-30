<template>
  <section v-if="cardKind || summary" class="listing-preview" :class="{ 'listing-preview--bare': !cardKind }"
           aria-label="Gelesene Anzeige">
    <!-- A link: the advert as a messenger would unfurl it.
         Every picture here is loaded straight from the portal's image server.
         `no-referrer` keeps this app's address (and so which plot somebody is
         looking at) out of that request, and `lazy` keeps a long strip from
         costing requests nobody scrolls to. -->

    <div v-if="cardKind === 'url'" class="karte">
      <div class="bild" aria-hidden="true">
        <img v-if="shows(images[0])" :src="images[0]" alt=""
             referrerpolicy="no-referrer" loading="lazy" @error="fail(images[0])">
      </div>
      <div class="koerper">
        <p class="quelle">
          <span v-if="host" class="fav" aria-hidden="true">{{ hostLetter }}</span>
          <span>{{ sourceLine }}</span>
        </p>
        <p v-if="title" class="titel">{{ title }}</p>
        <ul v-if="chips.length" class="werte">
          <li v-for="chip in chips" :key="chip.key" class="wert" :class="{ 'wert--stark': chip.strong }">
            {{ chip.text }}
          </li>
        </ul>
      </div>
      <a v-if="link" class="lk" :href="link" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>
    </div>

    <!-- A pasted page: a miniature rebuilt out of what the reader returned —
         never a picture of the real page — with a numbered pin where each
         finding sits, and the same numbers in the list beside it. -->
    <div v-else-if="cardKind === 'page'" class="mini-wrap">
      <div class="mini" aria-hidden="true">
        <div class="mini__kopf">
          <span v-if="host" class="fav fav--klein">{{ hostLetter }}</span>
          <span>{{ host || "Eingefügte Seite" }}</span>
        </div>
        <div v-if="title" class="mini__zeile">
          <p class="mini__titel">{{ title }}</p>
          <span class="pin" :class="pinSide('titel')">{{ pinOf("titel") }}</span>
        </div>
        <div v-if="images.length" class="mini__zeile">
          <div class="mini__foto">
            <img v-if="shows(images[0])" :src="images[0]" alt=""
                 referrerpolicy="no-referrer" loading="lazy" @error="fail(images[0])">
          </div>
          <div v-if="strip.length" class="mini__reihe">
            <span v-for="src in strip" :key="src" class="mini__klein">
              <img v-if="shows(src)" :src="src" alt=""
                   referrerpolicy="no-referrer" loading="lazy" @error="fail(src)">
            </span>
          </div>
          <span class="pin" :class="pinSide('bilder')">{{ pinOf("bilder") }}</span>
        </div>
        <div v-if="price" class="mini__zeile">
          <p class="mini__preis">{{ price }}</p>
          <span class="pin" :class="pinSide('preis')">{{ pinOf("preis") }}</span>
        </div>
        <div v-if="place" class="mini__zeile">
          <p class="mini__fein">{{ place }}</p>
          <span class="pin" :class="pinSide('ort')">{{ pinOf("ort") }}</span>
        </div>
        <div v-if="plotArea" class="mini__zeile">
          <p class="mini__fein">{{ plotArea }}</p>
          <span class="pin" :class="pinSide('flaeche')">{{ pinOf("flaeche") }}</span>
        </div>
        <p v-if="excerpt" class="mini__text">{{ excerpt }}</p>
      </div>

      <div class="befund-spalte">
        <p class="quelle">Aus der eingefügten Seite gelesen</p>
        <ol class="befund">
          <li v-for="finding in findings" :key="finding.key">
            <span class="pin">{{ finding.number }}</span>
            <span><b>{{ finding.label }}</b> {{ finding.text }}</span>
          </li>
          <li v-if="!hasCoordinate" class="fehlt">
            <span class="fehlt__zeichen" aria-hidden="true">!</span>
            <span>
              <b>Koordinate fehlt</b> – der Kopf der Seite kam nicht mit.
              <button type="button" class="lk" @click="$emit('bookmarklet')">Lesezeichen nimmt ihn mit</button>
            </span>
          </li>
        </ol>
      </div>
    </div>

    <!-- The read values themselves, editable. Keeps the class the screenshot
         run and the bookmarklet script wait for. -->
    <details v-if="summary" class="gelesen">
      <summary>
        <span class="gelesen__titel">Gelesene Werte</span>
        <span class="gelesen__zahl">{{ summary }}</span>
      </summary>
      <slot></slot>
    </details>
  </section>
</template>

<script>
import { area, euro } from "../lib/format.js";

/** How many pictures the miniature's strip shows beside the big one. */
const STRIP_LENGTH = 5;
/** How much of the prose the miniature sets as its body text. */
const EXCERPT_LENGTH = 260;

const valueOf = (response, key) => response?.felder?.[key]?.wert;

/**
 * What a listing looked like once it was read: the advert's card for a link,
 * a rebuilt miniature for a pasted page, and in both cases the fold with the
 * editable values. Everything drawn comes out of the extract response; a
 * value the response does not carry is not drawn and not listed as found.
 */
export default {
  name: "ListingPreview",
  props: {
    /** The answer of `/api/listings/extract`. */
    response: { type: Object, required: true },
    /** How the listing came in: "url", "page" or "prose". Prose was the input
     *  itself, so there is nothing to preview — only the fold is drawn. */
    kind: { type: String, default: "page" },
    /** The address the listing was read from, if there was one. */
    url: { type: String, default: "" },
    /** The fold's count line; no fold without it. */
    summary: { type: String, default: "" }
  },
  emits: ["bookmarklet"],
  data() {
    return {
      /* Pictures that did not load. They come from the portal's servers,
       * which may refuse, move or drop them; their box then stays grey
       * rather than showing a broken-image icon. */
      failed: []
    };
  },
  computed: {
    cardKind() {
      if (this.kind === "url") return "url";
      if (this.kind === "page" && this.findings.length) return "page";
      return "";
    },
    images() {
      return Array.isArray(this.response?.bilder) ? this.response.bilder.filter(Boolean) : [];
    },
    strip() { return this.images.slice(1, 1 + STRIP_LENGTH); },
    title() {
      const title = this.response?.titel;
      return typeof title === "string" ? title.trim() : "";
    },
    price() {
      const value = valueOf(this.response, "kaufpreis_eur");
      return Number.isFinite(value) && value > 0 ? euro(value) : "";
    },
    plotArea() {
      const value = valueOf(this.response, "grundstuecksflaeche_m2");
      return Number.isFinite(value) && value > 0 ? area(value) : "";
    },
    place() {
      const value = valueOf(this.response, "adresse");
      return typeof value === "string" ? value.trim() : "";
    },
    /** „Adresse" only for a line that names a house; a postcode and a town
     *  are a place, and calling them an address promises more than is there. */
    placeLabel() {
      return /[a-zäöüß.]\s+\d+\s?[a-z]?\s*(,|$)/i.test(this.place) ? "Adresse" : "Ort";
    },
    hasCoordinate() {
      return Number.isFinite(valueOf(this.response, "lat")) && Number.isFinite(valueOf(this.response, "lon"));
    },
    imageCount() {
      const n = this.images.length;
      return n === 1 ? "1 Bild" : `${n} Bilder`;
    },
    excerpt() {
      const text = String(this.response?.beschreibung || "").replace(/\s+/g, " ").trim();
      // The description starts with the title when the page had one; the
      // miniature already set that as its heading.
      const body = this.title && text.startsWith(this.title) ? text.slice(this.title.length).trim() : text;
      return body.slice(0, EXCERPT_LENGTH);
    },
    /** What the reader found, in the order the miniature draws it. Numbered
     *  after filtering, so the pins run 1, 2, 3 without gaps. */
    findings() {
      const found = [
        this.title && { key: "titel", label: "Titel", text: this.title },
        this.images.length && {
          key: "bilder", label: this.imageCount,
          text: "– die Suche liest sie nach einem Katasterauszug, wenn der Text allein nicht reicht"
        },
        this.price && { key: "preis", label: "Preis", text: this.price },
        this.place && { key: "ort", label: this.placeLabel, text: this.place },
        this.plotArea && { key: "flaeche", label: "Fläche", text: this.plotArea }
      ].filter(Boolean);
      return found.map((finding, i) => ({ ...finding, number: i + 1 }));
    },
    host() {
      try {
        return this.url ? new URL(this.url).hostname.replace(/^www\./, "") : "";
      } catch {
        return "";
      }
    },
    hostLetter() { return this.host.charAt(0).toLowerCase(); },
    /** The advert's own number where the address carries one. Only for the
     *  portal whose URLs are known to end in it; anywhere else a number in
     *  the path could be anything. */
    listingNumber() {
      if (!/(^|\.)kleinanzeigen\.de$/.test(this.host)) return "";
      try {
        const match = new URL(this.url).pathname.match(/\/(\d{6,})(?:-\d+)*\/?$/);
        return match ? match[1] : "";
      } catch {
        return "";
      }
    },
    sourceLine() {
      if (!this.host) return "Gelesene Anzeige";
      return this.listingNumber ? `${this.host} · Nr. ${this.listingNumber}` : this.host;
    },
    link() {
      const candidate = this.url || this.response?.quelle_url || "";
      return /^https?:\/\//i.test(candidate) ? candidate : "";
    },
    chips() {
      return [
        this.price && { key: "preis", text: this.price, strong: true },
        this.plotArea && { key: "flaeche", text: this.plotArea, strong: true },
        this.place && { key: "ort", text: this.place },
        this.images.length && { key: "bilder", text: this.imageCount }
      ].filter(Boolean);
    }
  },
  watch: {
    response() { this.failed = []; }
  },
  methods: {
    shows(src) { return Boolean(src) && !this.failed.includes(src); },
    fail(src) { if (!this.failed.includes(src)) this.failed.push(src); },
    pinOf(key) { return this.findings.find(f => f.key === key)?.number ?? ""; },
    /** Alternating sides, as in the approved mock, so neighbouring pins never
     *  sit on top of each other. */
    pinSide(key) { return this.pinOf(key) % 2 ? "pin--links" : "pin--rechts"; }
  }
};
</script>

<style scoped>
/* The preview and the fold are one box: what was read, and underneath the same
   values to correct. The images come from the portal, so every box that holds
   one has a fixed size and a grey ground — nothing moves when a picture
   arrives, and nothing is broken when one never does. */
.listing-preview{
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-m);
  background: var(--w2b-surface);
  min-width: 0; overflow: hidden;
}

.quelle{
  margin: 0; display: flex; align-items: center; gap: 6px; min-width: 0;
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.quelle span:last-child{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fav{
  flex: none; display: grid; place-items: center; width: 16px; height: 16px;
  border-radius: 4px; background: var(--w2b-graphite); color: var(--w2b-surface);
  font: 700 9px/1 var(--w2b-font-display); text-transform: lowercase;
}
.fav--klein{ width: 10px; height: 10px; border-radius: 2px; font-size: 6.5px; }
.lk{
  font: 600 var(--w2b-text-s) var(--w2b-font-display); color: var(--w2b-primary);
  background: none; border: 0; padding: 0; cursor: pointer;
  text-decoration: underline; text-underline-offset: 3px; white-space: nowrap;
}
.lk:hover{ color: var(--w2b-primary-light); }

/* ---------- a link: the card ---------- */
.karte{ display: flex; gap: var(--w2b-space-3); padding: var(--w2b-space-3); min-width: 0; align-items: flex-start; }
.bild{
  flex: none; width: 112px; height: 84px; border-radius: var(--w2b-radius-s); overflow: hidden;
  background: var(--w2b-line-faint);
}
.bild img, .mini__foto img, .mini__klein img{ width: 100%; height: 100%; object-fit: cover; display: block; }
.koerper{ flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.titel{
  margin: 0; font: 600 var(--w2b-text-m)/1.3 var(--w2b-font-display); color: var(--w2b-ink);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  overflow-wrap: anywhere;
}
.werte{ list-style: none; margin: 2px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.wert{
  font-size: 12.5px; border-radius: 6px; padding: 2px 7px; max-width: 100%;
  background: var(--w2b-surface-sunken); border: 1px solid var(--w2b-line-faint); color: var(--w2b-graphite);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.wert--stark{ font-weight: 600; color: var(--w2b-ink); }
.karte > .lk{ flex: none; align-self: flex-start; }

/* ---------- a pasted page: the miniature ---------- */
.mini-wrap{
  display: flex; gap: 30px; align-items: flex-start; min-width: 0;
  /* Room for the pins, which stand half outside the miniature. */
  padding: var(--w2b-space-4) var(--w2b-space-4) var(--w2b-space-4) 26px;
}
.mini{
  position: relative; flex: none; width: 168px; box-sizing: border-box;
  background: var(--w2b-paper); color: var(--w2b-ink);
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); padding: 8px;
  box-shadow: 4px 4px 0 -1px var(--w2b-surface), 4px 4px 0 0 var(--w2b-line);
}
.mini p{ margin: 0; }
.mini__kopf{
  display: flex; align-items: center; gap: 4px; min-width: 0;
  font: 600 7px var(--w2b-font-display); color: var(--w2b-muted);
  border-bottom: 1px solid var(--w2b-line-faint); padding-bottom: 4px; margin-bottom: 5px;
}
.mini__kopf span:last-child{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mini__zeile{ position: relative; }
.mini__zeile + .mini__zeile{ margin-top: 5px; }
.mini__titel{
  font: 700 8.5px/1.25 var(--w2b-font-display);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  overflow-wrap: anywhere;
}
.mini__foto{ height: 72px; border-radius: 4px; overflow: hidden; background: var(--w2b-line); }
.mini__reihe{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px; margin-top: 2px; }
.mini__klein{ display: block; height: 16px; border-radius: 2px; overflow: hidden; background: var(--w2b-line); }
.mini__preis{ font: 700 10.5px var(--w2b-font-display); color: var(--w2b-secondary-text); }
.mini__fein{ font-size: 7.5px; line-height: 1.3; color: var(--w2b-graphite); overflow-wrap: anywhere; }
.mini__text{
  margin-top: 6px !important; font-size: 6px; line-height: 1.45; color: var(--w2b-muted);
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;
}

.pin{
  display: grid; place-items: center; flex: none;
  width: 18px; height: 18px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-primary); color: var(--w2b-primary-on);
  font: 700 10px/1 var(--w2b-font-display);
}
.mini .pin{ position: absolute; top: 0; box-shadow: 0 0 0 2px var(--w2b-surface); }
.mini .pin--links{ left: -25px; }
.mini .pin--rechts{ right: -25px; }

.befund-spalte{ flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--w2b-space-2); }
.befund{
  list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px;
  font-size: var(--w2b-text-s); color: var(--w2b-graphite); min-width: 0;
}
.befund li{ display: flex; gap: var(--w2b-space-2); align-items: baseline; min-width: 0; }
.befund li > span:last-child{ min-width: 0; overflow-wrap: anywhere; }
.befund li .pin{ transform: translateY(3px); }
.befund b{ font-weight: 600; color: var(--w2b-ink); }
.befund .fehlt{ color: var(--w2b-warning-text); }
.befund .fehlt b{ color: var(--w2b-warning-text); }
.fehlt__zeichen{
  flex: none; display: grid; place-items: center; width: 18px; height: 18px; box-sizing: border-box;
  border-radius: var(--w2b-radius-full); background: var(--w2b-warning-surface);
  border: 1px solid var(--w2b-warning); font: 700 10px/1 var(--w2b-font-display);
  transform: translateY(3px);
}
.befund .lk{ font-size: var(--w2b-text-s); white-space: normal; text-align: left; }

/* The telephone: the findings go under the miniature, which takes the width. */
@media (max-width: 460px){
  .karte{ flex-wrap: wrap; }
  .bild{ width: 100%; height: 140px; }
  .koerper{ flex-basis: 100%; }
  .mini-wrap{ flex-direction: column; gap: var(--w2b-space-4); padding-left: 30px; padding-right: 30px; }
  .mini{ width: 100%; }
  .mini__foto{ height: 132px; }
  .mini__klein{ height: 30px; }
}

/* ---------- the fold ---------- */
.gelesen{
  border-top: 1px solid var(--w2b-line);
  background: var(--w2b-surface-sunken);
  padding: 0 var(--w2b-space-4);
}
.listing-preview--bare .gelesen{ border-top: 0; }
.gelesen > summary{
  display: flex; align-items: baseline; gap: var(--w2b-space-3); flex-wrap: wrap;
  padding: var(--w2b-space-3) 0; cursor: pointer; list-style: revert;
}
.gelesen > summary::marker{ color: var(--w2b-muted); }
.gelesen__titel{ font-weight: 600; }
.gelesen__zahl{ color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.gelesen[open]{ padding-bottom: var(--w2b-space-4); }
</style>
