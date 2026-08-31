<template>
  <div class="field gemarkung">
    <label :for="fieldId">Gemarkung</label>

    <input :id="fieldId" ref="input" type="text" autocomplete="off" spellcheck="false"
           role="combobox" aria-autocomplete="list"
           :aria-controls="listId"
           :aria-expanded="open ? 'true' : 'false'"
           :aria-activedescendant="activeIndex >= 0 && open ? optionId(activeIndex) : null"
           :value="query"
           placeholder="Moritzburg oder 3044"
           @input="type($event.target.value)"
           @focus="open = true"
           @blur="open = false"
           @keydown.down.prevent="move(1)"
           @keydown.up.prevent="move(-1)"
           @keydown.enter="take"
           @keydown.esc="escape"
           @keydown.tab="open = false">

    <ul v-show="open && hits.length" :id="listId" class="gemarkung__liste"
        role="listbox" aria-label="Gefundene Gemarkungen">
      <li v-for="(hit, i) in hits" :key="hit.schluessel" :id="optionId(i)"
          class="gemarkung__treffer" :class="{ 'is-active': i === activeIndex }"
          role="option" :aria-selected="i === activeIndex ? 'true' : 'false'"
          @mousedown.prevent="choose(hit)">
        <span class="gemarkung__name">{{ hit.name }}</span>
        <span class="gemarkung__schluessel">{{ hit.schluessel }}</span>
        <span class="gemarkung__gemeinde">{{ hit.gemeinde }}</span>
      </li>
    </ul>

    <!-- Everything below is a remark on what was typed. None of it blocks the
         lookup: the directory is an aid, and a name it does not carry may
         still be the one in the Geoportal. -->
    <p v-if="error" class="gemarkung__hinweis gemarkung__hinweis--warnung">
      {{ error }} Der Name oder der Schlüssel lässt sich weiterhin von Hand eintragen.
    </p>
    <p v-else-if="loading" class="gemarkung__hinweis">Verzeichnis wird geladen …</p>
    <template v-else>
      <p v-if="selected" class="gemarkung__hinweis">
        Verzeichnis: {{ selected.name }} · <span class="gemarkung__schluessel">{{ selected.schluessel }}</span>
        · {{ selected.gemeinde }}
      </p>
      <p v-else-if="ambiguous" class="gemarkung__hinweis">
        Diesen Namen tragen mehrere Gemarkungen. Die Auswahl aus der Liste legt fest, welche gemeint ist.
      </p>
      <p v-else-if="unknown" class="gemarkung__hinweis gemarkung__hinweis--warnung">
        Kein Eintrag im Verzeichnis trägt diesen Namen oder Schlüssel. Nachschlagen lässt sich das trotzdem.
      </p>
      <p v-if="open && omitted" class="gemarkung__hinweis">
        {{ omitted }} weitere Treffer sind nicht aufgeführt — weiter tippen grenzt ein.
      </p>
    </template>
  </div>
</template>

<script>
import { cadastralDistricts } from "../lib/api.js";

/** Rendered rows. The directory holds about 5 300 entries; a list that long
 *  is neither readable nor cheap to draw, and a search that wide is not a
 *  search. What is left over is counted, not hidden silently. */
const VISIBLE_LIMIT = 50;

/** Every Saxon key is six digits and starts with 14 — see CLAUDE.md. */
const LAND_PREFIX = "14";
const DISTRICT_NUMBER_LENGTH = 4;

/** Unique ids for the ARIA wiring, one set per instance. */
let instances = 0;

/** Lower case, without diacritics, so "Molkau" finds "Mölkau". */
function fold(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

/**
 * The forms of one key a user may have in front of them. The Geoportal prints
 * the six-digit key on its Gemarkung layer and the four-digit district number
 * on its Flurstueck layer, and a number that has been through a spreadsheet
 * has lost its leading zero.
 */
function keyForms(key) {
  const forms = [key];
  if (key.length === LAND_PREFIX.length + DISTRICT_NUMBER_LENGTH && key.startsWith(LAND_PREFIX)) {
    const short = key.slice(LAND_PREFIX.length);
    forms.push(short, short.replace(/^0+/, ""));
  }
  return forms;
}

export default {
  name: "CadastralDistrictPicker",
  props: {
    /** The text in the field — a directory name, or whatever was typed. */
    modelValue: { type: String, default: "" }
  },
  /** `select` carries the directory entry behind the text, or null when the
   *  text matches none. Its key is unambiguous where a name is not. */
  emits: ["update:modelValue", "select"],
  data() {
    instances += 1;
    return {
      uid: instances,
      query: this.modelValue,
      directory: [],
      loading: false,
      error: "",
      open: false,
      activeIndex: -1
    };
  },
  computed: {
    fieldId() { return `gemarkung-${this.uid}`; },
    listId() { return `gemarkung-${this.uid}-liste`; },
    needle() { return fold(this.query).trim(); },

    /** Everything the query matches, best first: a name that starts with it
     *  before one that merely contains it. Ties keep the directory's own
     *  order, which the service sorts by name. */
    matches() {
      if (!this.needle) return [];
      const scored = [];
      this.directory.forEach(entry => {
        const rank = this.rank(entry);
        if (rank !== null) scored.push({ entry, rank });
      });
      scored.sort((a, b) => a.rank - b.rank);
      return scored.map(s => s.entry);
    },
    hits() { return this.matches.slice(0, VISIBLE_LIMIT); },
    omitted() { return Math.max(0, this.matches.length - this.hits.length); },

    /** The entries the text names outright, rather than merely resembles. */
    exact() {
      if (!this.needle) return [];
      return this.directory.filter(
        entry => fold(entry.name) === this.needle || keyForms(entry.schluessel).includes(this.query.trim())
      );
    },
    selected() { return this.exact.length === 1 ? this.exact[0] : null; },
    ambiguous() { return this.exact.length > 1; },
    unknown() {
      return Boolean(this.query.trim()) && this.directory.length > 0 && this.matches.length === 0;
    }
  },
  watch: {
    modelValue(value) { if (value !== this.query) this.query = value; },
    /** Whatever the text now stands for, including nothing. */
    selected: { handler(entry) { this.$emit("select", entry); }, immediate: false }
  },
  mounted() { this.load(); },
  methods: {
    async load() {
      this.loading = true;
      this.error = "";
      try {
        const answer = await cadastralDistricts();
        this.directory = answer?.gemarkungen ?? [];
      } catch (error) {
        // The German explanation from the backend, never an empty list: an
        // empty list would read as "Saxony has no such district".
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },

    /** How well an entry answers the query, or null if it does not. */
    rank(entry) {
      const name = fold(entry.name);
      if (name.startsWith(this.needle)) return 0;
      const typed = this.query.trim();
      if (/^\d+$/.test(typed) && keyForms(entry.schluessel).some(form => form.startsWith(typed))) return 1;
      if (name.includes(this.needle)) return 2;
      return null;
    },

    optionId(index) { return `gemarkung-${this.uid}-treffer-${index}`; },

    type(value) {
      this.query = value;
      this.open = true;
      this.activeIndex = -1;
      this.$emit("update:modelValue", value);
    },

    move(step) {
      if (!this.open) this.open = true;
      if (!this.hits.length) return;
      const next = this.activeIndex + step;
      this.activeIndex = next < 0 ? this.hits.length - 1 : next % this.hits.length;
      this.$nextTick(() => {
        this.$el.querySelector(".gemarkung__treffer.is-active")?.scrollIntoView?.({ block: "nearest" });
      });
    },

    /** Enter takes the highlighted row. With nothing highlighted it does
     *  nothing at all — the typed text is an answer in its own right. */
    take(event) {
      if (!this.open || this.activeIndex < 0 || !this.hits.length) return;
      event.preventDefault();
      this.choose(this.hits[this.activeIndex]);
    },

    escape(event) {
      if (!this.open) return;
      event.preventDefault();
      this.open = false;
      this.activeIndex = -1;
    },

    choose(entry) {
      this.query = entry.name;
      this.open = false;
      this.activeIndex = -1;
      this.$emit("update:modelValue", entry.name);
      // The name may not be unique; say which entry was meant regardless of
      // what the watcher on `selected` makes of the text.
      this.$emit("select", entry);
      this.$refs.input?.focus();
    }
  }
};
</script>

<style scoped>
.gemarkung{ position: relative; }

.gemarkung__liste{
  position: absolute; z-index: 30; top: 100%; left: 0; right: 0;
  margin: var(--w2b-space-1) 0 0; padding: var(--w2b-space-1); list-style: none;
  max-height: 264px; overflow-y: auto; overscroll-behavior: contain;
  background: var(--w2b-surface); border: 1px solid var(--w2b-line);
  border-radius: var(--w2b-radius-s); box-shadow: var(--w2b-shadow-high);
}
.gemarkung__treffer{
  display: grid; grid-template-columns: minmax(0, 1fr) auto;
  gap: 0 var(--w2b-space-2); align-items: baseline; cursor: pointer;
  padding: 6px var(--w2b-space-3); border-radius: var(--w2b-radius-xs);
}
.gemarkung__treffer:hover, .gemarkung__treffer.is-active{ background: var(--w2b-primary-veil); }
.gemarkung__name{ font-size: var(--w2b-text-s); color: var(--w2b-ink); overflow-wrap: anywhere; }
.gemarkung__schluessel{
  font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs); color: var(--w2b-graphite);
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.gemarkung__gemeinde{
  grid-column: 1 / -1; font-size: var(--w2b-text-xs); color: var(--w2b-muted); overflow-wrap: anywhere;
}
.gemarkung__hinweis{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); line-height: 1.45; overflow-wrap: anywhere; }
.gemarkung__hinweis--warnung{ color: var(--w2b-warning-text); }
</style>
