<template>
  <div class="search">
    <label :for="fieldId">Adresse, Flurstück oder Koordinate</label>

    <div class="search__field">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <input :id="fieldId" ref="input" type="text" autocomplete="off" spellcheck="false"
             role="combobox" aria-autocomplete="list"
             :aria-controls="listId" :aria-expanded="open ? 'true' : 'false'"
             :aria-activedescendant="activeIndex >= 0 && open ? optionId(activeIndex) : null"
             placeholder="Lessingweg 44 · Mölkau 204 · 51.33652, 12.44176"
             :value="text"
             @input="type($event.target.value)"
             @focus="open = true"
             @keydown.down.prevent="move(1)"
             @keydown.up.prevent="move(-1)"
             @keydown.enter.prevent="take"
             @keydown.esc="open = false">
      <span v-if="badge" class="search__badge" :data-certain="String(reading.certain)">{{ badge }}</span>
    </div>

    <ul v-show="open && hits.length" :id="listId" class="search__hits"
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

    <p v-if="error" class="search__hint search__hint--warn">{{ error }}</p>
    <p v-else-if="missing" class="search__hint">{{ missing }}</p>
    <p v-else-if="busy" class="search__hint">Wird gesucht …</p>
    <p v-else class="search__hint">{{ hint }}</p>
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

/** Keystroke quiet before anything is looked up. */
const DEBOUNCE_MS = 120;
const MAX_DISTRICTS = 6;

/** Unique ids for the ARIA wiring, one set per instance. */
let instances = 0;

export default {
  name: "PlotSearch",
  /** `select` carries a ready `/api/parcels/resolve` payload and the label the
   *  user picked, so the caller neither re-reads the text nor re-derives it. */
  emits: ["select"],
  data() {
    instances += 1;
    return {
      uid: instances,
      text: "",
      addresses: [],
      districts: [],
      directory: [],
      busy: false,
      error: "",
      open: false,
      activeIndex: -1
    };
  },
  computed: {
    fieldId() { return `plot-search-${this.uid}`; },
    listId() { return `plot-search-${this.uid}-hits`; },
    reading() { return classifyQuery(this.text); },
    badge() { return queryKindLabel(this.reading); },

    /** The rows, in the order the reading makes plausible. */
    hits() {
      const rows = [];
      const reading = this.reading;

      if (reading.kind === "coordinate" && reading.coordinate) {
        const c = reading.coordinate;
        rows.push(c.system === "utm33"
          ? {
              key: "coord-utm", kind: "Koordinate",
              name: `${num(c.easting, 0)} · ${num(c.northing, 0)}`,
              note: "ETRS89 / UTM 33N — wie im Geoportal",
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
      this.districts.forEach(entry => rows.push({
        key: `district-${entry.schluessel}`,
        kind: "Gemarkung",
        name: entry.name,
        note: `${entry.schluessel} · ${entry.gemeinde} — Flurstücksnummer ergänzen`,
        district: entry
      }));

      return rows;
    },

    /** What the field is still waiting for, when the reading knows. */
    missing() {
      if (this.reading.missing === "district") {
        return "Zu einer Flurstücksnummer gehört die Gemarkung — dieselbe Nummer gibt es "
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
        return "„Lessingweg 44“ und „Mölkau 204“ haben dieselbe Form — deshalb stehen hier "
          + "beide Lesarten, statt dass eine geraten wird.";
      }
      return this.hits.length ? "" : "Nichts gefunden. Postleitzahl oder Ort ergänzen hilft oft.";
    }
  },
  beforeUnmount() { clearTimeout(this._timer); },
  methods: {
    optionId(index) { return `plot-search-${this.uid}-hit-${index}`; },

    type(value) {
      this.text = value;
      this.open = true;
      this.activeIndex = -1;
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.look(), DEBOUNCE_MS);
    },

    async look() {
      const reading = this.reading;
      const wanted = reading.search ?? [];
      this.error = "";
      // A coordinate is answered by the reading itself; nothing to ask.
      if (!wanted.includes("address") && !wanted.includes("district")) {
        this.addresses = [];
        this.districts = [];
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
        if (asked === this.text) this.busy = false;
      }
    },

    move(step) {
      if (!this.open) this.open = true;
      if (!this.hits.length) return;
      const next = this.activeIndex + step;
      this.activeIndex = next < 0 ? this.hits.length - 1 : next % this.hits.length;
    },

    take() {
      const hit = this.hits[this.activeIndex] ?? (this.hits.length === 1 ? this.hits[0] : null);
      if (hit) this.choose(hit);
    },

    choose(hit) {
      // A district is half an answer: it goes into the field so the parcel
      // number can be typed after it, rather than resolving to nothing.
      if (hit.district) {
        this.text = `${hit.district.schluessel} `;
        this.activeIndex = -1;
        this.$refs.input?.focus();
        return;
      }
      this.open = false;
      this.$emit("select", {
        query: hit.query, label: `${hit.kind}: ${hit.name}`, address: hit.address ?? null
      });
    }
  }
};
</script>

<style scoped>
.search{ display: flex; flex-direction: column; gap: 6px; }
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

/* In the flow, not floating over it. A dropdown positioned absolutely is at
   the mercy of every ancestor: `.panel` sets `overflow: hidden` to clip its
   own rounded corners, which cut the list off after the first row. Pushing the
   hint below it costs nothing here and cannot be clipped by anything. */
.search__hits{
  margin: 4px 0 0; padding: 4px; list-style: none; max-height: 19rem; overflow-y: auto;
  background: var(--w2b-surface); border: 1px solid var(--w2b-line);
  border-radius: var(--w2b-radius-s);
}
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
