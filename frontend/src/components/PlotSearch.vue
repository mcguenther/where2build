<template>
  <div class="search" :class="{ 'search--bare': bare }">
    <label v-if="!bare" :for="fieldId">Adresse, Flurstück oder Koordinate</label>

    <div class="search__field">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <!-- What the wrapper made of the text so far: a pill, a half of a
           parcel. It sits where the text would, and the text goes on after it. -->
      <slot name="lead"></slot>
      <input v-show="!hideInput" :id="fieldId" ref="input" type="text" autocomplete="off" spellcheck="false"
             role="combobox" aria-autocomplete="list"
             :aria-controls="listId" :aria-expanded="open ? 'true' : 'false'"
             :aria-activedescendant="activeIndex >= 0 && open ? optionId(activeIndex) : null"
             :placeholder="placeholder"
             :value="text"
             @input="type($event.target.value)"
             @paste="$emit('paste', $event)"
             @focus="open = true"
             @keydown.down.prevent="move(1)"
             @keydown.up.prevent="move(-1)"
             @keydown.enter.prevent="enter"
             @keydown.esc="open = false"
             @keydown.backspace="backspace">
      <span v-if="badge && !bare" class="search__badge" :data-certain="String(reading.certain)">{{ badge }}</span>
      <!-- What sits beside the field is the wrapper's business: the wizard
           puts nothing there, the start page its button. -->
      <slot name="action"></slot>
    </div>

    <!-- Over the page, never in it: a list in the flow pushed everything below
         it down as the hits arrived, and the page jumped with every keystroke.
         It sits in the browser's top layer where that exists, so no ancestor's
         `overflow: hidden` can cut it off -- `.panel` has one, and so has the
         start page's reception. -->
    <ul v-show="showList" ref="list" :id="listId" class="search__hits"
        :class="{ 'search__hits--floating': floating }" :style="listStyle"
        :popover="floating ? 'manual' : null"
        role="listbox" aria-label="Vorschläge">
      <li v-for="(hit, i) in hits" :key="hit.key" :id="optionId(i)"
          class="hit" :class="{ 'is-active': i === activeIndex }"
          role="option" :aria-selected="i === activeIndex ? 'true' : 'false'"
          @mousedown.prevent="choose(hit)">
        <span class="hit__name">{{ hit.name }}</span>
        <span class="hit__kind">{{ hit.kind }}</span>
        <span class="hit__note">{{ hit.note }}</span>
      </li>
    </ul>

    <template v-if="!bare">
      <p v-if="error" class="search__hint search__hint--warn">{{ error }}</p>
      <p v-else-if="missing" class="search__hint">{{ missing }}</p>
      <p v-else-if="busy" class="search__hint">Wird gesucht …</p>
      <p v-else class="search__hint">{{ hint }}</p>
    </template>
  </div>
</template>

<script>
/**
 * The way in: one field that takes an address, a parcel or a coordinate.
 *
 * The field reads what was typed before it looks anything up
 * (`lib/queryInput.js`), so a leading digit never queries the address index
 * and a coordinate never queries anything at all. Where two readings stay
 * plausible — "Lessingweg 44" and "Mölkau 204" are the same shape — it asks
 * both local indexes and groups what comes back, rather than guessing.
 *
 * The address hits come from `/api/geocode`, which answers from the official
 * Hauskoordinaten of the GeoSN first and falls back to the routing geocoder.
 * That is the point of doing it this way round: 990 000 Saxon addresses on our
 * own disk, no third-party service in the path of every keystroke.
 */
import { geocode, cadastralDistricts } from "../lib/api.js";
import { classifyQuery, queryKindLabel } from "../lib/queryInput.js";
import { searchDistricts } from "../lib/districts.js";
import { num } from "../lib/format.js";
import { canFloat, placementUnder, toggleFloating } from "../lib/floating.js";

/** Keystroke quiet before anything is looked up. */
const DEBOUNCE_MS = 120;
const MAX_DISTRICTS = 6;

/** Unique ids for the ARIA wiring, one set per instance. */
let instances = 0;

export default {
  name: "PlotSearch",
  /** `select` carries a ready `/api/parcels/resolve` payload and the label the
   *  user picked, so the caller neither re-reads the text nor re-derives it. */
  props: {
    /** The text, so a wrapper can read what is being typed and say something
     *  about it. Two-way like any field: `update:modelValue` on every stroke. */
    modelValue: { type: String, default: "" },
    /** Without its own label, badge and hint — for a wrapper that carries
     *  those itself. The suggestions and the keyboard stay. */
    bare: { type: Boolean, default: false },
    placeholder: { type: String, default: "Lessingweg 44 · Mölkau 204 · 51.33652, 12.44176" },
    /** The wrapper shows the text as something else — a pill — and the
     *  input steps aside. It stays mounted, so focus and the keyboard stay. */
    hideInput: { type: Boolean, default: false },
    /** Only the district directory is worth asking: the parcel number is
     *  already there, and what is typed after it can only be its Gemarkung. */
    onlyDistricts: { type: Boolean, default: false },
    /** Nothing is worth asking: the wrapper knows what the text is. */
    quiet: { type: Boolean, default: false }
  },
  emits: ["select", "update:modelValue", "paste", "submit", "district", "backspace"],
  data() {
    instances += 1;
    return {
      uid: instances,
      text: this.modelValue,
      addresses: [],
      districts: [],
      directory: [],
      busy: false,
      error: "",
      open: false,
      activeIndex: -1,
      /* Enter came before the answer it needs. Held until that answer lands,
       * and dropped by the next keystroke: it was meant for other text. */
      takeWhenReady: false,
      /* Where the floating list goes, measured off the field it belongs to.
       * Without the Popover API the list falls back to an absolutely placed
       * one, which is all a test environment needs. */
      floating: canFloat(),
      listStyle: null
    };
  },
  watch: {
    // The wrapper may reset or prefill the field; typing here reports back.
    modelValue(value) { if (value !== this.text) this.text = value; },
    showList(shown) {
      if (shown) {
        window.addEventListener("scroll", this.place, true);
        window.addEventListener("resize", this.place);
        this.$nextTick(this.place);
      } else {
        this.unlisten();
        toggleFloating(this.$refs.list, false);
      }
    },
    // A new row changes nothing on the page, but the list may need a new cap.
    hits() { if (this.showList) this.$nextTick(this.place); }
  },
  computed: {
    fieldId() { return `plot-search-${this.uid}`; },
    listId() { return `plot-search-${this.uid}-hits`; },
    reading() { return classifyQuery(this.text); },
    badge() { return queryKindLabel(this.reading); },
    /** Which indexes the text is worth asking, after the wrapper had its say. */
    wanted() {
      if (this.quiet) return [];
      if (this.onlyDistricts) return this.text.trim() ? ["district"] : [];
      return this.reading.search ?? [];
    },
    showList() { return this.open && this.hits.length > 0; },

    /** The rows, in the order the reading makes plausible. */
    hits() {
      const rows = [];
      const reading = this.reading;
      if (this.quiet) return rows;
      if (this.onlyDistricts) return this.districts.map(entry => this.districtRow(entry));

      if (reading.kind === "coordinate" && reading.coordinate) {
        const c = reading.coordinate;
        rows.push(c.system === "utm33"
          ? {
              key: "coord-utm", kind: "Koordinate",
              name: `${num(c.easting, 0)} · ${num(c.northing, 0)}`,
              note: "ETRS89 / UTM 33N, wie im Geoportal",
              query: { easting: c.easting, northing: c.northing }
            }
          : {
              key: "coord-wgs", kind: "Koordinate",
              name: `${num(c.lat, 5)} · ${num(c.lon, 5)}`,
              note: c.swapped ? "Reihenfolge getauscht gelesen" : "WGS 84",
              query: { lat: c.lat, lon: c.lon }
            });
      }

      // A parcel is only a question once a district stands beside the number.
      if (reading.parcelNumber && (reading.district || reading.districtKey)) {
        const number = reading.parcelNumber.denominator
          ? `${reading.parcelNumber.numerator}/${reading.parcelNumber.denominator}`
          : reading.parcelNumber.numerator;
        const district = reading.districtKey || reading.district;
        rows.push({
          key: `parcel-${district}-${number}`,
          kind: "Flurstück",
          name: `${district} ${number}`,
          note: "im Liegenschaftskataster nachschlagen",
          query: { gemarkung: district, flurstuecksnummer: number }
        });
      }

      this.addresses.forEach((hit, i) => rows.push({
        key: `address-${i}-${hit.lat}-${hit.lon}`,
        kind: hit.art === "adresse" ? "Adresse" : "Ort",
        name: hit.name,
        note: hit.beschreibung || "",
        // The address as the register spells it, so the step that follows can
        // check it against the cadastre's own `lagebeztxt` instead of trusting
        // the coordinate to land in the right parcel.
        address: hit.name,
        query: { lat: hit.lat, lon: hit.lon }
      }));

      // A district alone resolves nothing; it names the half that is missing.
      this.districts.forEach(entry => rows.push(this.districtRow(entry)));

      return rows;
    },

    /** What the field is still waiting for, when the reading knows. */
    missing() {
      if (this.reading.missing === "district") {
        return "Zu einer Flurstücksnummer gehört die Gemarkung. Dieselbe Nummer gibt es "
          + "in jeder. Etwa „Mölkau 204“.";
      }
      if (this.reading.missing === "parcelNumber") {
        return "Vier oder sechs Ziffern lesen sich als Gemarkungsschlüssel und als "
          + "Flurstücksnummer. Beides zusammen entscheidet: „3044 85/1“.";
      }
      return "";
    },
    hint() {
      if (!this.text.trim()) {
        return "Die Adressen kommen aus den amtlichen Hauskoordinaten des GeoSN, nicht von "
          + "einem fremden Dienst.";
      }
      // Only where both readings actually produced a row: "Lilienweg 25 Leipzig"
      // is ambiguous by shape too, but nothing offered it as a parcel, and
      // saying so there explains a choice nobody was given.
      const kinds = new Set(this.hits.map(hit => hit.kind));
      if (kinds.has("Flurstück") && (kinds.has("Adresse") || kinds.has("Ort"))) {
        return "„Lessingweg 44“ und „Mölkau 204“ haben dieselbe Form; deshalb stehen hier "
          + "beide Lesarten, statt dass eine geraten wird.";
      }
      return this.hits.length ? "" : "Nichts gefunden. Postleitzahl oder Ort ergänzen hilft oft.";
    }
  },
  beforeUnmount() {
    clearTimeout(this._timer);
    this.unlisten();
  },
  methods: {
    optionId(index) { return `plot-search-${this.uid}-hit-${index}`; },

    districtRow(entry) {
      return {
        key: `district-${entry.schluessel}`,
        kind: "Gemarkung",
        name: entry.name,
        note: `${entry.schluessel} · ${entry.gemeinde}`,
        district: entry
      };
    },

    /** Put the floating list under the box the field sits in. */
    place() {
      const list = this.$refs.list;
      if (!this.floating || !list || !this.showList) return;
      const anchor = this.$el.closest("[data-list-anchor]") || this.$el;
      this.listStyle = placementUnder(anchor.getBoundingClientRect());
      toggleFloating(list, true);
    },

    unlisten() {
      window.removeEventListener("scroll", this.place, true);
      window.removeEventListener("resize", this.place);
    },

    /** Backspace in an empty field takes back what the wrapper built before
     *  it, the way a mail client takes back the last recipient. */
    backspace(event) {
      if (!this.text) {
        event.preventDefault();
        this.$emit("backspace");
      }
    },

    type(value) {
      this.text = value;
      this.$emit("update:modelValue", value);
      this.open = true;
      this.activeIndex = -1;
      this.takeWhenReady = false;
      clearTimeout(this._timer);
      this._timer = setTimeout(() => { this._timer = null; this.look(); }, DEBOUNCE_MS);
    },

    async look() {
      const wanted = this.wanted;
      this.error = "";
      // A coordinate is answered by the reading itself; nothing to ask.
      if (!wanted.includes("address") && !wanted.includes("district")) {
        this.addresses = [];
        this.districts = [];
        this.takeIfWaiting();
        return;
      }

      // The text this answer belongs to, so a slow reply for an older query
      // cannot overwrite a newer one.
      const asked = this.text;
      this.busy = true;
      try {
        if (wanted.includes("district")) {
          if (!this.directory.length) {
            this.directory = (await cadastralDistricts())?.gemarkungen ?? [];
          }
          if (asked !== this.text) return;
          this.districts = searchDistricts(this.directory, asked, MAX_DISTRICTS).hits;
        } else {
          this.districts = [];
        }

        if (wanted.includes("address")) {
          const answer = await geocode(asked);
          if (asked !== this.text) return;
          this.addresses = answer?.treffer ?? [];
        } else {
          this.addresses = [];
        }
      } catch (error) {
        if (asked !== this.text) return;
        // Nothing found is a normal answer from the geocoder, not a failure to
        // report; anything else is the backend's own German sentence.
        this.addresses = [];
        if (error.status !== 404) this.error = error.message;
      } finally {
        if (asked === this.text) {
          this.busy = false;
          this.takeIfWaiting();
        }
      }
    },

    takeIfWaiting() {
      if (!this.takeWhenReady) return;
      this.takeWhenReady = false;
      this.take();
    },

    move(step) {
      if (!this.open) this.open = true;
      if (!this.hits.length) return;
      const next = this.activeIndex + step;
      this.activeIndex = next < 0 ? this.hits.length - 1 : next % this.hits.length;
    },

    /** Enter on a highlighted row takes that row. Otherwise it is the
     *  wrapper's to decide — a link or a bare number is not one of the rows,
     *  and only the wrapper knows what else it holds. */
    enter(event) {
      if (event.isComposing) return;
      const hit = this.open ? this.hits[this.activeIndex] : null;
      if (hit) this.choose(hit);
      else this.$emit("submit");
    },

    /** The row the field stands for, if there is one.
     *
     *  Asked before the lookup has answered, it waits for it: pressing Enter
     *  straight after typing is the normal speed, not an impatient one.
     *  Rows of one reading are in the order the index ranks them, so the top
     *  one is taken — the geocoder answers five rows even for a full address
     *  with its postcode. Rows of two readings, a parcel beside an address,
     *  are the ambiguity the field exists to show rather than resolve: then
     *  the first is only highlighted, and a second Enter is a choice
     *  somebody saw. */
    take() {
      if (this._timer || this.busy) {
        this.takeWhenReady = true;
        return;
      }
      const highlighted = this.hits[this.activeIndex];
      if (highlighted) return this.choose(highlighted);
      if (!this.hits.length) return;
      const readings = new Set(this.hits.map(hit => (hit.kind === "Ort" ? "Adresse" : hit.kind)));
      if (readings.size === 1) return this.choose(this.hits[0]);
      this.open = true;
      this.activeIndex = 0;
    },

    choose(hit) {
      // A district is half an answer. The wrapper turns it into a block and
      // the parcel number is typed after it; it resolves nothing on its own.
      if (hit.district) {
        this.activeIndex = -1;
        this.districts = [];
        this.$emit("district", hit.district);
        this.$refs.input?.focus();
        return;
      }
      this.open = false;
      this.$emit("select", {
        query: hit.query, label: `${hit.kind}: ${hit.name}`, address: hit.address ?? null,
        kind: hit.kind
      });
    },

    focus() { this.$refs.input?.focus(); }
  }
};
</script>

<style scoped>
.search{ display: flex; flex-direction: column; gap: 6px; position: relative; }
/* Without its own label the field sits inside whatever wraps it, and that
   wrapper brings the border and the padding. */
.search--bare .search__field{ border: 0; background: none; padding: 0; }
.search--bare .search__field:focus-within{ border: 0; }
.search label{
  font-family: var(--w2b-font-display); font-weight: 600;
  font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}

.search__field{
  display: flex; align-items: center; gap: 8px;
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s);
  background: var(--w2b-surface); padding: 0 10px;
}
.search__field:focus-within{ border-color: var(--w2b-primary); }
.search__field svg{ color: var(--w2b-muted); flex: none; }
.search__field input{
  flex: 1; min-width: 0; border: 0; background: none; outline: none;
  padding: 9px 0; font: inherit; font-size: 15px; color: var(--w2b-ink);
}
.search__badge{
  flex: none; font-family: var(--w2b-font-mono); font-size: 10.5px;
  padding: 2px 6px; border-radius: var(--w2b-radius-xs);
  background: var(--w2b-surface-sunken); color: var(--w2b-muted); white-space: nowrap;
}
.search__badge[data-certain="true"]{ background: var(--w2b-primary-veil); color: var(--w2b-primary-dark); }

/* Over the page, not in it. The list used to sit in the flow -- `.panel`
   clips an absolutely placed one -- and pushed everything below it down with
   every hit that arrived. In the top layer nothing clips it; without the
   Popover API it is placed absolutely under the field, and the box it sits in
   lets it out (see QueryBox). */
.search__hits{
  position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 40;
  margin: 0; padding: 4px; list-style: none; max-height: 19rem; overflow-y: auto;
  background: var(--w2b-surface); border: 1px solid var(--w2b-line);
  border-radius: var(--w2b-radius-s); box-shadow: var(--w2b-shadow-high);
  color: var(--w2b-ink);
}
.search__hits--floating{ position: fixed; inset: auto; right: auto; }
/* The user agent centres a popover in the viewport; `place()` sets where. */
.search__hits--floating:popover-open{ margin: 0; }
.hit{
  display: grid; grid-template-columns: 1fr auto; gap: 1px var(--w2b-space-3);
  padding: 6px 9px; border-radius: var(--w2b-radius-xs); cursor: pointer;
  align-items: baseline;
}
.hit + .hit{ border-top: 1px solid var(--w2b-line-faint); }
.hit.is-active, .hit:hover{ background: var(--w2b-primary-veil); }
/* The address first, where the eye and the caret already are. It used to be in
   the right-hand column with the category on the left, so the row read
   "Adresse … Lessingweg 44" — the useful half last and furthest from the
   typing. The category is what is now on the right: it says which index
   answered, which matters only once the name has been read. */
.hit__name{
  font-size: var(--w2b-text-s); font-weight: 600; line-height: 1.35;
  overflow-wrap: anywhere;
}
.hit__kind{
  font-family: var(--w2b-font-mono); font-size: 10px; color: var(--w2b-muted);
  text-align: right; white-space: nowrap;
}
/* Under both, because a postcode and a district are the second line of an
   address, not a column of their own. */
.hit__note{
  grid-column: 1 / -1; font-size: var(--w2b-text-xs); color: var(--w2b-muted);
  line-height: 1.35;
}
.hit__note:empty{ display: none; }

.search__hint{ margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted); max-width: 62ch; }
.search__hint--warn{ color: var(--w2b-warning-text); }
</style>
