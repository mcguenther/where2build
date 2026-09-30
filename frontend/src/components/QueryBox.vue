<template>
  <div class="query-box" :class="{ 'query-box--prose': blockKind === 'prose' }">
    <div class="query-box__field" data-list-anchor>
      <PlotSearch ref="search" v-model="text" bare
                  :placeholder="fieldPlaceholder"
                  :hide-input="hideInput"
                  :only-districts="Boolean(numberBlock && !district)"
                  :quiet="quietSearch"
                  @select="picked"
                  @submit="go"
                  @paste="takePaste"
                  @district="takeDistrict"
                  @backspace="takeBack"
                  @unmatched="takeUnmatched">
        <template #lead>
          <!-- The halves of a parcel, whichever came first. The Gemarkung
               stands first either way: that is how the cadastre names it. -->
          <span v-if="district || numberBlock" class="pill pill--square"
                :class="{ 'pill--done': Boolean(district && numberBlock) }">
            <span v-if="district" class="pill__part"><small>Gemarkung</small>{{ district.name }}</span>
            <span v-if="district && numberBlock" class="pill__divider" aria-hidden="true"></span>
            <span v-if="numberBlock" class="pill__part"><small>Flst.</small><span class="mono">{{ numberBlock }}</span></span>
            <button type="button" class="pill__remove" aria-label="Flurstück entfernen" @click="clearParcel">✕</button>
          </span>

          <span v-if="blockKind === 'url'" class="pill" :class="{ 'pill--busy': busy }">
            <span class="pill__portal" aria-hidden="true">{{ link.letter }}</span>
            <span class="pill__label">{{ link.host }}</span>
            <span class="pill__aside">{{ busy ? "wird gelesen …" : link.number }}</span>
            <button type="button" class="pill__remove" aria-label="Link entfernen" @click="removeBlock">✕</button>
          </span>

          <span v-else-if="blockKind === 'page'" class="pill pill--square" :class="{ 'pill--busy': busy }">
            <span class="pill__icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 1.5h5.5L12 4v10.5H4Z" /><path d="M9.5 1.5V4H12M6 8h4M6 10.5h4" /></svg>
            </span>
            <span class="pill__label">{{ pageHost || "Anzeigenseite" }}</span>
            <span v-if="busy" class="pill__aside">wird gelesen …</span>
            <button type="button" class="pill__remove" aria-label="Eingefügte Seite entfernen" @click="removeBlock">✕</button>
          </span>

          <span v-else-if="blockKind === 'coordinate'" class="pill">
            <span class="pill__icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M8 14s5-4.3 5-8A5 5 0 0 0 3 6c0 3.7 5 8 5 8Z" /><circle cx="8" cy="6" r="1.7" /></svg>
            </span>
            <span class="pill__label mono">{{ coordinateLabel }}</span>
            <button type="button" class="pill__remove" aria-label="Koordinate entfernen" @click="removeBlock">✕</button>
          </span>

          <!-- A description stays text: folded to a few lines, opened on
               request, and with what the browser already recognises marked. -->
          <div v-else-if="blockKind === 'prose'" class="prose">
            <p class="prose__text" :class="{ 'is-open': proseOpen }">
              <span v-if="excerpt.cut">… </span><template v-for="(part, i) in excerpt.segments" :key="i"><mark v-if="part.kind" :class="`mark mark--${part.kind}`">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template>
            </p>
            <div class="prose__foot">
              <span class="prose__kinds">
                <span v-for="kind in marks.kinds" :key="kind" :class="`mark mark--${kind}`">{{ MARK_LABELS[kind] }}</span>
                <span class="prose__count">{{ num(words, 0) }} Wörter</span>
              </span>
              <span class="prose__actions">
                <button type="button" class="link-button" @click="proseOpen = !proseOpen">
                  {{ proseOpen ? "Weniger zeigen" : "Ganzen Text zeigen" }}
                </button>
                <button type="button" class="link-button" @click="editAsText">Bearbeiten</button>
              </span>
            </div>
          </div>
        </template>

        <template #action>
          <div class="query-box__actions">
          <!-- How the input is read, in the same place for every kind of
               input. It is a button: the menu behind it overrules the reading. -->
          <div v-if="marker" class="reading">
            <button ref="marker" type="button" class="marker"
                    :class="{ 'marker--warn': marker.warn, 'marker--soft': marker.soft, 'marker--fixed': Boolean(fixedKind) }"
                    aria-haspopup="menu" :aria-expanded="menuOpen ? 'true' : 'false'"
                    :aria-controls="menuId"
                    :aria-label="`Gelesen als ${marker.label}${marker.warn ? ', ' + marker.warn : ''}. Andere Lesart wählen`"
                    @click="toggleMenu" @keydown.esc="closeMenu">
              {{ marker.label }}<span v-if="marker.warn" class="marker__warn"> · {{ marker.warn }}</span>
            </button>
            <div v-show="menuOpen" ref="menu" :id="menuId" class="menu"
                 :class="{ 'menu--floating': floating }" :style="menuStyle"
                 :popover="floating ? 'manual' : null"
                 role="menu" aria-label="Lesart" @keydown.esc="closeMenu">
              <button v-for="option in readings" :key="option.id" type="button"
                      class="menu__item" role="menuitemradio"
                      :aria-checked="option.current ? 'true' : 'false'"
                      :disabled="!option.available"
                      @click="fix(option.id)">
                <span>{{ option.name }}</span>
                <small v-if="option.note">{{ option.note }}</small>
              </button>
              <template v-if="canEditAsText">
                <hr class="menu__rule">
                <button type="button" class="menu__item" role="menuitem" @click="editAsText">Als Text bearbeiten</button>
              </template>
            </div>
          </div>
          <button type="button" class="btn btn--large" :disabled="busy || !ready" @click="go">
            {{ busy ? "Wird gelesen …" : "Grundstück finden" }}
          </button>
          </div>
        </template>
      </PlotSearch>
    </div>

    <!-- Where the coordinate lands, before anything is looked up: the point,
         its neighbourhood and the parcel under it. It appears after a paste or
         an Enter, both of which someone did on purpose. UTM has no preview —
         the projection lives in the backend, and the pill says what was read. -->
    <CoordinatePreview v-if="previewPoint" class="query-box__preview"
                       :lat="previewPoint.lat" :lon="previewPoint.lon"
                       @move="movedPoint = $event" />
  </div>
</template>

<script>
/**
 * The way in, in one field.
 *
 * Everything goes in here: an address, a parcel, a coordinate, the link of a
 * listing, a pasted listing page, or its description text. What was typed is
 * read before anything is looked up (`lib/queryInput.js`), and the reading is
 * shown in the field itself, at its right edge, for every kind of input —
 * a marker that opens the other readings, because two readings are sometimes
 * equally plausible and one of them is right.
 *
 * What is short stays text; what is long becomes a pill. Text becomes a block
 * only on an unmistakable signal — a paste, a chosen suggestion, Enter, or a
 * space after a number at the very start — and never in the middle of typing:
 * 2 165 of the 5 339 Saxon Gemarkung names contain a space, and „Altstadt" is
 * the start of three of them.
 *
 * The component decides nothing beyond that. It emits either
 *   - `resolve` — a ready `/api/parcels/resolve` payload, when the cadastre
 *     can simply be asked, or
 *   - `read`    — text or markup that has to be read first,
 * and leaves fetching and navigating to whoever placed it.
 */
import PlotSearch from "./PlotSearch.vue";
import CoordinatePreview from "./CoordinatePreview.vue";
import { classifyQuery } from "../lib/queryInput.js";
import { cadastralDistricts } from "../lib/api.js";
import { markText, wordCount, MARK_LABELS } from "../lib/textMarks.js";
import { canFloat, placementUnder, toggleFloating } from "../lib/floating.js";
import { num } from "../lib/format.js";
// The cap lives with the call that sends it; see `PAGE_LIMIT` in api.js.
import { PAGE_LIMIT } from "../lib/api.js";

/** The readings the marker's menu offers, in the order it lists them. */
export const READINGS = [
  { id: "address", name: "Adresse" },
  { id: "parcel", name: "Flurstück" },
  { id: "coordinate", name: "Koordinate" },
  { id: "url", name: "Link zur Anzeige" },
  { id: "page", name: "Eingefügte Anzeige" },
  { id: "prose", name: "Beschreibungstext" }
];

/** What the marker says for each reading — shorter than the menu's names. */
const MARKER_LABELS = {
  address: "Adresse", parcel: "Flurstück", coordinate: "Koordinate",
  url: "Link", page: "Anzeigenseite", prose: "Beschreibung"
};

/** Readings that are read by the server rather than looked up. */
const READ_KINDS = ["url", "page", "prose"];
/** Readings that are shown as a block once they are one. */
const BLOCK_KINDS = ["url", "page", "coordinate", "prose"];

/** A parcel number: numerator, optionally over a denominator. */
const PARCEL_NUMBER = /^(\d{1,5})(?:\s*\/\s*([0-9a-z]{1,3}))?$/i;
/** A number at the very start, then a space, then whatever is typed next. */
const LEADING_NUMBER = /^(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)\s+(.*)$/i;
/** The district and the number in one go, either order. */
const HEAD_NUMBER = /^(.*?\p{L}.*?)[\s,;]+(?:Flurst(?:ück|\.)?\s*)?(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)$/iu;
const NUMBER_HEAD = /^(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)[\s,;]+(.*\p{L}.*)$/u;

/** Listing numbers long enough to be one, at the end of a portal's path. */
const LISTING_NUMBER = /(\d{6,})(?:-\d+)*\/?$/;

/** A description folded open at its first mark when that is further in. */
const EXCERPT_FROM = 90;

let instances = 0;

export default {
  name: "QueryBox",
  components: { PlotSearch, CoordinatePreview },
  props: {
    /** The caller is fetching. The field stays readable, the button waits. */
    busy: { type: Boolean, default: false },
    placeholder: { type: String, default: "Adresse, Flurstück, Koordinate oder Link" }
  },
  emits: ["resolve", "read"],
  data() {
    instances += 1;
    return {
      MARK_LABELS,
      uid: instances,
      text: "",
      /* The markup beside the plain text. It is what makes a pasted page worth
       * more than its text: price, area, coordinate and the images all sit in
       * there, and none of them survive a `<textarea>`. */
      pastedHtml: "",
      /* A reading someone insisted on. It holds until the field is emptied or
       * the reading is picked again. */
      fixedKind: null,
      /* The text that became a block, and so is shown as a pill. Any other
       * text is plain text again: a block is a way of showing, not a change. */
      blockText: null,
      // Set by a paste, taken by the text that follows it.
      pasting: false,
      /* The halves of a parcel that are blocks already. */
      district: null,
      numberBlock: "",
      // Enter came while a Gemarkung was only typed: take the row it matches,
      // and then ask the cadastre without a second press.
      goAfterDistrict: false,
      proseOpen: false,
      // Where the preview's point was moved to; null while it is where typed.
      movedPoint: null,
      directory: null,
      menuOpen: false,
      menuStyle: null,
      floating: canFloat()
    };
  },
  computed: {
    menuId() { return `query-box-${this.uid}-menu`; },
    reading() { return classifyQuery(this.text); },

    /** What the input is, before anybody overruled it.
     *
     *  A link wins over the markup that came with it. Copying a link out of a
     *  browser, a mail or a chat puts `<a href="…">` on the clipboard as well,
     *  and read as a pasted page that is a page with nothing in it: the server
     *  answered 503 for an advert it fetches without trouble. */
    readKind() {
      if (this.district || this.numberBlock) return "parcel";
      if (this.pastedHtml && this.reading.kind !== "url") return "page";
      switch (this.reading.kind) {
        case "url": case "prose": case "coordinate": case "parcel": return this.reading.kind;
        // Letters only is a street on its way to being typed; a Gemarkung
        // among the suggestions becomes a block when it is picked. Only a
        // name *and* a number („Lessingweg 44", „Mölkau 204") are two readings.
        case "ambiguous": return this.reading.search.includes("parcel") ? "ambiguous" : "address";
        default: return null;
      }
    },
    kind() { return this.fixedKind || this.readKind; },

    /** The kind shown as a block, if the text has become one. */
    blockKind() {
      if (this.blockText === null || this.blockText !== this.text || !this.text.trim()) return null;
      return BLOCK_KINDS.includes(this.kind) ? this.kind : null;
    },
    hideInput() { return this.blockKind !== null; },
    /** Nothing in the directories can answer what is not a place name. */
    quietSearch() {
      return this.blockKind !== null || Boolean(this.district) || READ_KINDS.includes(this.fixedKind);
    },
    fieldPlaceholder() {
      if (this.numberBlock && this.district) return "";
      if (this.numberBlock && !this.district) return "Gemarkung …";
      if (this.district && !this.numberBlock) return "Flurstücksnummer, etwa 204/3";
      return this.placeholder;
    },

    /** The parcel number the text holds, when a Gemarkung is a block already. */
    typedNumber() {
      const match = PARCEL_NUMBER.exec(this.text.trim());
      return match ? (match[2] ? `${match[1]}/${match[2]}` : match[1]) : "";
    },
    /** A free text read as a parcel on request: „Mölkau 204/3", „204/3 Mölkau". */
    parcelFromText() {
      const text = this.text.trim();
      let match = HEAD_NUMBER.exec(text);
      if (match) return { district: match[1].trim(), number: match[2].replace(/\s+/g, "") };
      match = NUMBER_HEAD.exec(text);
      if (match) return { district: match[2].trim(), number: match[1].replace(/\s+/g, "") };
      return null;
    },

    /** What the marker says, or nothing while there is nothing to read. */
    marker() {
      if (this.district && !this.numberBlock && !this.typedNumber) {
        return { label: "Flurstück", warn: "Nummer fehlt" };
      }
      if (this.numberBlock && !this.district) return { label: "Flurstück", warn: "Gemarkung fehlt" };
      if (!this.text.trim() && !this.district) return null;
      const kind = this.kind;
      if (kind === "ambiguous") return { label: "2 Lesarten", soft: true };
      if (!kind) return null;
      if (!this.fixedKind && kind === "parcel" && this.reading.missing === "district") {
        return { label: "Flurstück", warn: "Gemarkung fehlt" };
      }
      if (!this.fixedKind && kind === "parcel" && this.reading.missing === "parcelNumber") {
        return { label: "2 Lesarten", soft: true };
      }
      if (kind === "coordinate" && this.reading.coordinate?.swapped) {
        return { label: "Koordinate", warn: "getauscht" };
      }
      if (kind === "coordinate" && this.reading.coordinate?.system === "utm33") {
        return { label: "Koordinate · UTM" };
      }
      return { label: MARKER_LABELS[kind] };
    },

    /** The menu: every reading, with why the impossible ones are not offered. */
    readings() {
      const text = this.text.trim();
      const current = this.kind === "ambiguous" ? null : this.kind;
      const why = {
        address: /^\p{L}/u.test(text) ? "" : "beginnt nicht mit einem Namen",
        parcel: /\d/.test(text) || this.district || this.numberBlock ? "" : "keine Nummer darin",
        coordinate: this.reading.coordinate ? "" : "keine zwei Zahlen",
        url: this.reading.kind === "url" ? "" : "kein Link",
        page: this.pastedHtml ? "" : "kein HTML dabei",
        prose: text.length > 8 ? "" : "zu kurz"
      };
      return READINGS.map(option => ({
        ...option,
        current: option.id === current,
        available: !why[option.id],
        note: why[option.id] || (!this.fixedKind && option.id === this.readKind ? "erkannt" : "")
      }));
    },
    canEditAsText() {
      return this.blockKind !== null || Boolean(this.district) || Boolean(this.numberBlock);
    },

    /** Readings that are read rather than looked up. */
    isReadable() { return READ_KINDS.includes(this.kind); },
    ready() {
      if (this.isReadable) return Boolean(this.pastedHtml || this.text.trim().length > 8);
      if (this.district) return Boolean(this.numberBlock || this.typedNumber);
      // A Gemarkung being typed after the number: the top row, or failing
      // that the name as typed, completes it.
      if (this.numberBlock) return Boolean(this.text.trim());
      if (this.fixedKind === "parcel") return Boolean(this.parcelFromText);
      return this.text.trim().length > 1;
    },

    link() {
      try {
        const url = new URL(this.text.trim());
        const host = url.hostname.replace(/^www\./, "");
        const number = url.pathname.match(LISTING_NUMBER)?.[1] ?? "";
        return { host, number, letter: host.charAt(0).toUpperCase() };
      } catch {
        return { host: this.text.trim(), number: "", letter: "" };
      }
    },
    /** The portal a pasted page came from, read off the links it carries. */
    pageHost() {
      const counts = new Map();
      for (const match of this.pastedHtml.matchAll(/https?:\/\/(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})/gi)) {
        const host = match[1].toLowerCase();
        counts.set(host, (counts.get(host) ?? 0) + 1);
      }
      let best = "";
      let most = 0;
      counts.forEach((count, host) => { if (count > most) { best = host; most = count; } });
      // Image servers and CDNs carry most links on a portal page; the portal's
      // own name is the part they share with it.
      const parts = best.split(".");
      return parts.length > 2 ? parts.slice(-2).join(".") : best;
    },
    /** The point the preview shows, and the one the cadastre is asked for. */
    previewPoint() {
      const c = this.reading.coordinate;
      if (this.blockKind !== "coordinate" || !c || c.system !== "wgs84") return null;
      return this.movedPoint || { lat: c.lat, lon: c.lon };
    },
    coordinateLabel() {
      const c = this.reading.coordinate;
      if (!c) return this.text.trim();
      if (c.system === "utm33") return `${num(c.easting, 0)} · ${num(c.northing, 0)}`;
      const point = this.movedPoint || c;
      return `${num(point.lat, 5)}° N · ${num(point.lon, 5)}° O`;
    },

    marks() { return markText(this.blockKind === "prose" ? this.text : "", this.directory); },
    words() { return wordCount(this.text); },
    /** The folded description starts at its first mark when that is further
     *  in: the start of an advert is usually its greeting. */
    excerpt() {
      const { segments, first } = this.marks;
      if (this.proseOpen || first < EXCERPT_FROM) return { segments, cut: false };
      const from = Math.max(0, this.text.lastIndexOf(" ", first - 40) + 1);
      const cut = [];
      let at = 0;
      for (const part of segments) {
        const end = at + part.text.length;
        if (end > from) cut.push(at >= from ? part : { ...part, text: part.text.slice(from - at) });
        at = end;
      }
      return { segments: cut, cut: true };
    }
  },
  watch: {
    /* The field is what everything else follows.
     *
     * An empty field with nothing built before it is a fresh start: the
     * insisted reading and the markup of the page pasted before go with it.
     * Leaving either behind shipped the page pasted before with the next
     * read, and a wrong answer that looks exactly as official as the right
     * one is the one thing this app may not produce. */
    text(value) {
      this.movedPoint = null;
      if (this.pasting) {
        this.pasting = false;
        this.blockText = value;
      }
      if (!value.trim() && !this.district && !this.numberBlock) {
        this.fixedKind = null;
        this.pastedHtml = "";
        this.blockText = null;
        this.proseOpen = false;
        return;
      }
      this.takeLeadingNumber(value);
    },
    blockKind(kind) {
      if (kind === "prose" && !this.directory) this.loadDirectory();
    },
    menuOpen(open) {
      if (open) {
        document.addEventListener("mousedown", this.closeOutside, true);
        window.addEventListener("scroll", this.placeMenu, true);
        window.addEventListener("resize", this.placeMenu);
        this.$nextTick(this.placeMenu);
      } else {
        this.unlistenMenu();
        toggleFloating(this.$refs.menu, false);
      }
    }
  },
  beforeUnmount() { this.unlistenMenu(); },
  methods: {
    num,

    takePaste(event) {
      const html = event.clipboardData?.getData("text/html");
      if (html && html.length > this.pastedHtml.length) this.pastedHtml = html.slice(0, PAGE_LIMIT);
      // Whatever arrives next is pasted, not typed, and becomes a block if its
      // kind is one. Nobody types a link or a page into this field character
      // by character, and a pill must not appear while someone does.
      this.pasting = true;
    },

    /** A number at the very start, then a space, is a parcel number.
     *
     *  The one place where a space is a safe signal: a German address never
     *  begins with a digit, and nothing after „204/3 " is part of the number.
     *  A number without a denominator waits for the letter that follows —
     *  „3044 85/1" is a district key and a number, not a number and a name. */
    takeLeadingNumber(value) {
      if (this.district || this.numberBlock || this.blockText !== null || this.fixedKind) return;
      const match = LEADING_NUMBER.exec(value);
      if (!match) return;
      const number = match[1].replace(/\s+/g, "");
      const rest = match[2];
      if (!number.includes("/") && !/^\p{L}/u.test(rest)) return;
      this.numberBlock = number;
      // A tick later: set in the same flush as the text it replaces, the
      // field would see its value go from "" to "" and keep showing the number.
      this.$nextTick(() => { this.text = rest; });
    },

    takeDistrict(entry) {
      this.district = entry;
      this.text = "";
      this.$nextTick(() => this.$refs.search?.focus());
      if (this.goAfterDistrict) {
        this.goAfterDistrict = false;
        this.go();
      }
    },

    /** No row for what was typed after the number. The name goes to the
     *  cadastre as typed: the directory is an aid, not a gate, and a service
     *  that is down must not lock the field. */
    takeUnmatched() {
      if (!this.goAfterDistrict) return;
      this.goAfterDistrict = false;
      const typed = this.text.trim();
      if (!this.numberBlock || !typed) return;
      this.$emit("resolve", {
        query: { gemarkung: typed, flurstuecksnummer: this.numberBlock },
        label: `Flurstück: ${typed} ${this.numberBlock}`,
        address: null
      });
    },

    /** Backspace in an empty field takes back the last block. */
    takeBack() {
      if (this.blockKind) return this.removeBlock();
      if (this.numberBlock && this.district) this.numberBlock = "";
      else if (this.district) this.district = null;
      else if (this.numberBlock) this.numberBlock = "";
    },

    clearParcel() {
      this.district = null;
      this.numberBlock = "";
      this.$nextTick(() => this.$refs.search?.focus());
    },

    removeBlock() {
      this.blockText = null;
      this.pastedHtml = "";
      this.fixedKind = null;
      this.proseOpen = false;
      this.text = "";
      this.$nextTick(() => this.$refs.search?.focus());
    },

    /** Every block goes back into the text it was made of. */
    editAsText() {
      this.closeMenu();
      if (this.district || this.numberBlock) {
        this.text = [this.district?.name, this.numberBlock, this.text.trim()].filter(Boolean).join(" ");
        this.district = null;
        this.numberBlock = "";
        // The text is back as typed; it must not be cut up again straight away.
        this.fixedKind = "parcel";
      }
      this.blockText = null;
      this.$nextTick(() => this.$refs.search?.focus());
    },

    async loadDirectory() {
      try {
        this.directory = (await cadastralDistricts())?.gemarkungen ?? [];
      } catch {
        // The marks are a courtesy; without the directory there are no place
        // marks, and the text is still the text.
        this.directory = [];
      }
    },

    toggleMenu() { this.menuOpen = !this.menuOpen; },
    closeMenu() { this.menuOpen = false; },
    closeOutside(event) {
      const inside = this.$refs.menu?.contains(event.target) || this.$refs.marker?.contains(event.target);
      if (!inside) this.closeMenu();
    },
    placeMenu() {
      if (!this.floating || !this.menuOpen || !this.$refs.marker) return;
      this.menuStyle = placementUnder(this.$refs.marker.getBoundingClientRect(), { align: "right", width: 260 });
      toggleFloating(this.$refs.menu, true);
    },
    unlistenMenu() {
      document.removeEventListener("mousedown", this.closeOutside, true);
      window.removeEventListener("scroll", this.placeMenu, true);
      window.removeEventListener("resize", this.placeMenu);
    },

    fix(id) {
      this.fixedKind = id === this.readKind ? null : id;
      // A reading that is shown as a block becomes one; the others go back to
      // being the text they are.
      this.blockText = BLOCK_KINDS.includes(id) ? this.text : null;
      this.closeMenu();
    },

    /** A suggestion was picked. A coordinate becomes a block first — the map
     *  under it shows where it lands before anything is looked up; everything
     *  else is a finished question for the cadastre. */
    picked(payload) {
      if (payload.kind === "Koordinate") {
        this.blockText = this.text;
        return;
      }
      this.$emit("resolve", payload);
    },

    go() {
      if (this.busy || !this.ready) return;
      if (this.isReadable) {
        this.blockText = this.text;
        return this.$emit("read", {
          kind: this.kind,
          text: this.text.trim(),
          html: this.pastedHtml
        });
      }
      if (this.numberBlock && !this.district) {
        this.goAfterDistrict = true;
        return this.$refs.search?.take();
      }
      if (this.district) {
        const number = this.numberBlock || this.typedNumber;
        this.numberBlock = number;
        this.text = "";
        return this.$emit("resolve", {
          query: { gemarkung: this.district.schluessel, flurstuecksnummer: number },
          label: `Flurstück: ${this.district.name} ${number}`,
          address: null
        });
      }
      if (this.kind === "coordinate" && this.reading.coordinate) {
        if (this.blockKind !== "coordinate") {
          this.blockText = this.text;
          return;
        }
        const c = this.reading.coordinate;
        const point = this.previewPoint;
        return this.$emit("resolve", {
          query: c.system === "utm33" ? { easting: c.easting, northing: c.northing } : { lat: point.lat, lon: point.lon },
          label: `Koordinate: ${this.coordinateLabel}`,
          address: null
        });
      }
      if (this.fixedKind === "parcel" && this.parcelFromText) {
        const { district, number } = this.parcelFromText;
        return this.$emit("resolve", {
          query: { gemarkung: district, flurstuecksnummer: number },
          label: `Flurstück: ${district} ${number}`,
          address: null
        });
      }
      // Address, plain parcel: the answer is one of the rows the field is
      // already offering, so the button does what Enter does.
      this.$refs.search?.take();
    }
  }
};
</script>

<style scoped>
/* Whether the button fits beside the field is decided by the width of this
   box, not of the window: in a column it is already too narrow at 1024px and
   the placeholder disappears underneath it.
   `overflow: visible` lets the list and the menu out where the Popover API is
   missing; `.panel`, which this box usually also is, clips its corners. */
.query-box{ container-type: inline-size; overflow: visible; }

.query-box__field{
  display: flex; align-items: center;
  background: var(--w2b-surface); border: 1.5px solid var(--w2b-line);
  border-radius: var(--w2b-radius-m); padding: 6px 6px 6px 16px;
  transition: border-color .14s ease, box-shadow .14s ease;
}
.query-box__field:focus-within{ border-color: var(--w2b-primary); box-shadow: 0 0 0 3px var(--w2b-primary-veil); }
.query-box__field :deep(.search){ flex: 1; min-width: 0; }
.query-box__field :deep(.search__field){ min-height: 48px; }
.query-box__field :deep(.search__field input){ font-size: 18px; padding: 12px 0; }
.query-box--prose .query-box__field :deep(.search__field){ align-items: flex-start; }
.query-box--prose .query-box__field :deep(.search__field > svg){ margin-top: 12px; }

.query-box__preview{ margin-top: var(--w2b-space-3); }

/* ---------- pills ---------- */
.pill{
  display: inline-flex; align-items: center; gap: 7px; min-width: 0; max-width: 100%;
  flex: 0 1 auto; overflow: hidden; white-space: nowrap;
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-full);
  background: var(--w2b-surface-sunken); padding: 4px 4px 4px 6px;
  font-size: var(--w2b-text-m); color: var(--w2b-ink);
}
.pill--square{ border-radius: var(--w2b-radius-s); }
.pill--done{ background: var(--w2b-good-surface); border-color: color-mix(in srgb, var(--w2b-primary) 30%, var(--w2b-line)); }
.pill__icon, .pill__portal{
  flex: none; display: grid; place-items: center; width: 24px; height: 24px;
  border-radius: var(--w2b-radius-full); background: var(--w2b-primary-veil); color: var(--w2b-primary);
}
.pill__icon svg{ width: 14px; height: 14px; }
.pill__portal{
  width: 18px; height: 18px; border-radius: var(--w2b-radius-xs); margin-left: 3px;
  background: var(--w2b-primary); color: var(--w2b-primary-on);
  font-family: var(--w2b-font-display); font-weight: 700; font-size: 10px;
}
.pill--busy .pill__icon, .pill--busy .pill__portal{ animation: pill-pulse 1.2s ease-in-out infinite; }
@keyframes pill-pulse{ 50%{ opacity: .35; } }
@media (prefers-reduced-motion: reduce){
  .pill--busy .pill__icon, .pill--busy .pill__portal{ animation: none; }
}
.pill__label{ min-width: 3em; overflow: hidden; text-overflow: ellipsis; }
.pill__aside{ color: var(--w2b-muted); font-size: var(--w2b-text-s); overflow: hidden; text-overflow: ellipsis; }
.pill__aside:empty{ display: none; }
.pill__part{ display: inline-flex; align-items: center; gap: 6px; padding-left: 4px; }
.pill__part small{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 10px;
  letter-spacing: .08em; text-transform: uppercase; color: var(--w2b-muted);
}
.pill__divider{ width: 1px; align-self: stretch; background: var(--w2b-line); }
.pill__remove{
  flex: none; display: grid; place-items: center; width: 22px; height: 22px;
  border: 0; border-radius: var(--w2b-radius-full); background: none;
  color: var(--w2b-muted); font-size: 12px; cursor: pointer;
}
.pill__remove:hover{ background: var(--w2b-line-faint); color: var(--w2b-ink); }

/* ---------- a description, folded ---------- */
.prose{ flex: 1; min-width: 0; padding: 8px 0 4px; }
.prose__text{
  margin: 0; font-size: var(--w2b-text-m); line-height: 1.55; color: var(--w2b-ink);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  overflow-wrap: anywhere;
}
.prose__text.is-open{ display: block; -webkit-line-clamp: unset; max-height: 18rem; overflow-y: auto; }
.prose__foot{
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px 12px;
  margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.prose__kinds, .prose__actions{ display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.mark{ color: inherit; border-radius: 3px; padding: 0 2px; background: var(--w2b-secondary-veil); box-shadow: inset 0 -1.5px 0 var(--w2b-secondary); }
.mark--place{ background: var(--w2b-primary-veil); box-shadow: inset 0 -1.5px 0 var(--w2b-primary); }
.prose__kinds .mark{ padding: 0 5px; color: var(--w2b-graphite); }
.link-button{
  border: 0; background: none; padding: 0; cursor: pointer;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  color: var(--w2b-primary); text-decoration: underline; text-underline-offset: 3px;
}

/* ---------- the reading marker ---------- */
/* Pushed to the right edge even when a pill stands where the input was. */
.query-box__actions{ margin-left: auto; flex: none; display: flex; align-items: center; }
.reading{ position: relative; flex: none; display: flex; align-items: center; margin-right: 8px; }
.marker{
  display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; cursor: pointer;
  border: 1px solid var(--w2b-primary); border-radius: var(--w2b-radius-full);
  background: var(--w2b-primary-veil); color: var(--w2b-primary);
  padding: 3px 7px 3px 10px;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 11px;
  letter-spacing: .06em; text-transform: uppercase;
}
.marker::after{
  content: ""; width: 0; height: 0; margin-top: 3px;
  border: 4px solid transparent; border-top-color: currentColor;
}
.marker--fixed{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.marker--warn{ border-color: var(--w2b-warning); background: var(--w2b-warning-surface); color: var(--w2b-warning-text); }
.marker--soft{ border-color: var(--w2b-line); background: var(--w2b-surface); color: var(--w2b-muted); }
.marker__warn{ text-transform: none; letter-spacing: 0; font-weight: 500; }

.menu{
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 41; width: 260px;
  display: flex; flex-direction: column; padding: 6px; margin: 0; overflow-y: auto;
  background: var(--w2b-surface); color: var(--w2b-ink);
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-m);
  box-shadow: var(--w2b-shadow-high);
}
.menu--floating{ position: fixed; inset: auto; right: auto; }
.menu--floating:popover-open{ margin: 0; }
.menu__item{
  display: flex; justify-content: space-between; align-items: baseline; gap: 10px;
  border: 0; background: none; text-align: left; cursor: pointer;
  padding: 7px 10px; border-radius: var(--w2b-radius-s);
  font: inherit; font-size: var(--w2b-text-s); color: inherit;
}
.menu__item:hover:not(:disabled), .menu__item:focus-visible{ background: var(--w2b-primary-veil); }
.menu__item[aria-checked="true"]{ background: var(--w2b-primary-veil); color: var(--w2b-primary); font-weight: 600; }
.menu__item:disabled{ color: var(--w2b-muted); cursor: default; opacity: .75; }
.menu__item small{ font-size: 11px; color: var(--w2b-muted); font-weight: 400; }
.menu__rule{ border: 0; border-top: 1px solid var(--w2b-line-faint); margin: 4px 0; }

/* Narrow, the button goes below the field. It sits *inside* the search's own
   row, though — so that row is what has to wrap; wrapping the box around it
   only squeezed the input to nothing. The marker stays on the input's line. */
@container (max-width: 540px){
  .query-box__field{ padding: 10px 12px; }
  .query-box__field :deep(.search__field){ flex-wrap: wrap; row-gap: 8px; }
  .query-box__field :deep(.search__field input){ flex: 1 1 40%; font-size: 16px; padding: 6px 0; }
  .query-box__actions{ display: contents; }
  .query-box__field .btn--large{ flex: 1 1 100%; }
  .reading{ margin-right: 0; }
  .prose{ flex-basis: 100%; }
}
</style>
