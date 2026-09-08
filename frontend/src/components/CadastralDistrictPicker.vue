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
        {{ omitted }} weitere Treffer sind nicht aufgeführt; weiter tippen grenzt ein.
      </p>
    </template>
  </div>
</template>

<script>
import { cadastralDistricts } from "../lib/api.js";
import { searchDistricts, exactDistricts } from "../lib/districts.js";

/** Rendered rows. The directory holds about 5 300 entries; a list that long
 *  is neither readable nor cheap to draw, and a search that wide is not a
 *  search. What is left over is counted, not hidden silently. */
const VISIBLE_LIMIT = 50;

/** Unique ids for the ARIA wiring, one set per instance. */
let instances = 0;

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
    /** Everything the query matches, best first: a name that starts with it
     *  before one that merely contains it. Ties keep the directory's own
     *  order, which the service sorts by name. */
    found() { return searchDistricts(this.directory, this.query, VISIBLE_LIMIT); },
    hits() { return this.found.hits; },
    omitted() { return Math.max(0, this.found.total - this.hits.length); },

    /** The entries the text names outright, rather than merely resembles. */
    exact() { return exactDistricts(this.directory, this.query); },
    selected() { return this.exact.length === 1 ? this.exact[0] : null; },
    ambiguous() { return this.exact.length > 1; },
    unknown() {
      return Boolean(this.query.trim()) && this.directory.length > 0 && this.found.total === 0;
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
