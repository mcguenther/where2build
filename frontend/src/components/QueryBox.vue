<template>
  <div class="query-box">
    <div class="query-box__field">
      <PlotSearch ref="search" v-model="text" bare
                  :placeholder="placeholder"
                  @select="$emit('resolve', $event)"
                  @submit="go"
                  @paste="takePaste">
        <template #action>
          <button type="button" class="btn btn--large" :disabled="busy || !ready" @click="go">
            {{ busy ? "Wird gelesen …" : "Grundstück finden" }}
          </button>
        </template>
      </PlotSearch>
    </div>

    <!-- How the input was read, and a way to overrule it. Two groups: what
         someone knows about the place, and what they have from the listing.
         The grouping is also where the row breaks, so the break is not an
         accident of width. -->
    <div class="kinds">
      <span class="kinds__label">{{ kindsLabel }}</span>
      <div v-for="(group, i) in KIND_GROUPS" :key="i" class="kinds__group">
        <button v-for="kind in group" :key="kind.id" type="button" class="kind"
                :data-state="stateOf(kind.id)"
                :aria-pressed="fixedKind === kind.id ? 'true' : 'false'"
                :aria-label="stateOf(kind.id) === 'set'
                  ? `${kind.name}: festgelegt, klicken zum Aufheben`
                  : `Als ${kind.name} lesen`"
                @click="fix(kind.id)">
          {{ kind.name }}<span v-if="stateOf(kind.id) === 'set'" class="kind__off" aria-hidden="true">✕</span>
        </button>
      </div>
    </div>

    <!-- The one reading that unfolds something: the two halves do not fit in
         one field. A bare number lands here by itself — without a district it
         is nothing. -->
    <div v-if="wantsPair" class="query-box__pair">
      <CadastralDistrictPicker v-model="district" @select="districtEntry = $event" @submit="go" />
      <div class="field">
        <label for="q-parcel-number">Flurstücksnummer</label>
        <input id="q-parcel-number" type="text" v-model="parcelNumber" placeholder="85/1"
               @keydown.enter.prevent="go">
      </div>
    </div>

    <p v-if="note" class="query-box__note" v-html="note"></p>
  </div>
</template>

<script>
/**
 * The way in, in one field.
 *
 * Everything goes in here: an address, a parcel, a coordinate, the link of a
 * listing, a pasted listing page, or its description text. What was typed is
 * read before anything is looked up (`lib/queryInput.js`), the reading is
 * shown as a chip, and a chip can be clicked to overrule it — which is the
 * whole reason the chips exist, because two readings are sometimes equally
 * plausible and one of them is right.
 *
 * The component decides nothing beyond that. It emits either
 *   - `resolve` — a ready `/api/parcels/resolve` payload, when the cadastre
 *     can simply be asked, or
 *   - `read`    — text or markup that has to be read first,
 * and leaves fetching and navigating to whoever placed it: the wizard
 * continues its stages, the start page pushes into them.
 */
import PlotSearch from "./PlotSearch.vue";
import CadastralDistrictPicker from "./CadastralDistrictPicker.vue";
import { classifyQuery } from "../lib/queryInput.js";
// The cap lives with the call that sends it; see `PAGE_LIMIT` in api.js.
import { PAGE_LIMIT } from "../lib/api.js";



/** The readings, in two groups — the break between them is the grouping. */
export const KIND_GROUPS = [
  [
    { id: "address", name: "Adresse" },
    { id: "parcel", name: "Flurstück" },
    { id: "district", name: "Gemarkung + Flurstück" },
    { id: "coordinate", name: "Koordinate" }
  ],
  [
    { id: "url", name: "Link zur Anzeige" },
    { id: "page", name: "Eingefügte Anzeige" },
    { id: "prose", name: "Beschreibungstext" }
  ]
];

/* A sentence appears only where it leads somewhere: something is missing, or
 * two readings are equally plausible. What the chips already say is not
 * written underneath them. */
const NOTES = {
  parcel: "<b>Ohne Gemarkung ist die Nummer nicht eindeutig.</b> Dieselbe gibt es in Sachsen vielfach.",
  ambiguous: "<b>Zwei Lesarten sind gleich plausibel.</b> Beide Verzeichnisse werden gefragt, statt eines zu raten. Oder hier festlegen."
};

/** Which chips light up for a reading of `classifyQuery`. */
function chipsFor(reading) {
  switch (reading.kind) {
    case "coordinate": return ["coordinate"];
    case "url": return ["url"];
    case "prose": return ["prose"];
    case "parcel":
      // A number without a district is the one case that names what it lacks.
      return reading.missing === "district" ? ["parcel"] : ["district"];
    case "ambiguous":
      return reading.search.includes("parcel") ? ["address", "district"] : ["address"];
    default: return [];
  }
}

export default {
  name: "QueryBox",
  components: { PlotSearch, CadastralDistrictPicker },
  props: {
    /** The caller is fetching. The field stays readable, the button waits. */
    busy: { type: Boolean, default: false },
    placeholder: { type: String, default: "Adresse, Flurstück, Koordinate oder Link" }
  },
  emits: ["resolve", "read"],
  data() {
    return {
      KIND_GROUPS,
      text: "",
      /* The markup beside the plain text. It is what makes a pasted page worth
       * more than its text: price, area, coordinate and the images all sit in
       * there, and none of them survive a `<textarea>`. */
      pastedHtml: "",
      /* A reading someone insisted on. It holds until the field is emptied or
       * the chip is clicked again — the next keystroke must not inherit it
       * silently, and must not throw it away either. */
      fixedKind: null,
      district: "",
      districtEntry: null,
      parcelNumber: ""
    };
  },
  computed: {
    reading() { return classifyQuery(this.text); },
    /** What lit up on its own, before anyone overruled it. */
    readChips() { return this.pastedHtml ? ["page"] : chipsFor(this.reading); },
    kind() { return this.fixedKind || this.readChips[0] || null; },
    kindsLabel() {
      if (this.fixedKind) return "Festgelegt als";
      return this.readChips.length ? "Gelesen als" : "Oder gezielt";
    },
    wantsPair() { return this.kind === "district" || this.kind === "parcel"; },
    /** The key beats the name: the directory answers on the key, and a name
     *  that is not in it is still worth sending as typed. */
    districtQuery() { return this.districtEntry?.schluessel || this.district.trim(); },
    /** Readings that are read rather than looked up. */
    isReadable() { return ["url", "page", "prose"].includes(this.kind); },
    ready() {
      if (this.isReadable) return Boolean(this.pastedHtml || this.text.trim().length > 8);
      if (this.wantsPair) return Boolean(this.districtQuery && this.parcelNumber.trim());
      return this.text.trim().length > 1;
    },
    note() {
      if (this.fixedKind) return "";
      if (this.reading.kind === "ambiguous" && this.readChips.length > 1) return NOTES.ambiguous;
      /* A note names what is missing, so supplying it has to take the note
       * with it. „Ohne Gemarkung ist die Nummer nicht eindeutig" standing over
       * a filled Gemarkung contradicts itself, and the reading underneath does
       * not change when the pair is completed -- the field it asks for is not
       * the search field. */
      if (this.readChips[0] === "parcel" && this.districtQuery) return "";
      return NOTES[this.readChips[0]] || "";
    }
  },
  watch: {
    /* The field is what everything else follows.
     *
     * An empty field is a fresh start — the insisted reading, the markup of
     * the page pasted before and the unfolded pair all go with it. Leaving the
     * parcel number behind was worse than untidy: type "85/1", clear, type
     * "204", and the cadastre was asked for 85/1 while the field said 204.
     * A wrong answer that looks exactly as official as the right one is the
     * one thing this app may not produce.
     *
     * And while the pair is open, the number in it follows what is typed: a
     * bare number belongs in the field that takes numbers, and retyping it
     * there is work the reading already did. Typing into the pair itself does
     * not touch the search field, so it stays editable. */
    text: {
      immediate: true,
      handler(value) {
        if (!value.trim()) {
          this.fixedKind = null;
          this.pastedHtml = "";
          this.parcelNumber = "";
          this.district = "";
          this.districtEntry = null;
          return;
        }
        if (!this.wantsPair) return;
        const bare = value.trim().match(/(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)$/i);
        if (bare) this.parcelNumber = bare[1].replace(/\s+/g, "");
      }
    },
    // Overruling the reading can open the pair on its own; the number the
    // field already carries belongs in it either way.
    wantsPair(open) {
      if (!open || this.parcelNumber) return;
      const bare = this.text.trim().match(/(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)$/i);
      if (bare) this.parcelNumber = bare[1].replace(/\s+/g, "");
    }
  },
  methods: {
    stateOf(id) {
      if (this.fixedKind === id) return "set";
      return !this.fixedKind && this.readChips.includes(id) ? "read" : "off";
    },
    fix(id) {
      this.fixedKind = this.fixedKind === id ? null : id;
    },
    takePaste(event) {
      const html = event.clipboardData?.getData("text/html");
      if (html && html.length > this.pastedHtml.length) this.pastedHtml = html.slice(0, PAGE_LIMIT);
    },
    go() {
      if (this.busy || !this.ready) return;
      if (this.isReadable) {
        return this.$emit("read", {
          kind: this.kind,
          text: this.text.trim(),
          html: this.pastedHtml
        });
      }
      if (this.wantsPair) {
        const number = this.parcelNumber.trim();
        return this.$emit("resolve", {
          query: { gemarkung: this.districtQuery, flurstuecksnummer: number },
          label: `Flurstück: ${this.district.trim()} ${number}`,
          address: null
        });
      }
      // Address, coordinate, plain parcel: the answer is one of the rows the
      // field is already offering, so the button does what Enter does.
      this.$refs.search?.take();
    }
  }
};
</script>

<style scoped>
/* Whether the button fits beside the field is decided by the width of this
   box, not of the window: in a column it is already too narrow at 1024px and
   the placeholder disappears underneath it. */
.query-box{ container-type: inline-size; }

.query-box__field{
  display: flex; align-items: center;
  background: var(--w2b-surface); border: 1.5px solid var(--w2b-line);
  border-radius: var(--w2b-radius-m); padding: 6px 6px 6px 16px;
  transition: border-color .14s ease, box-shadow .14s ease;
}
.query-box__field:focus-within{ border-color: var(--w2b-primary); box-shadow: 0 0 0 3px var(--w2b-primary-veil); }
.query-box__field :deep(.search){ flex: 1; min-width: 0; }
.query-box__field :deep(.search__field input){ font-size: 18px; padding: 12px 0; }
.query-box__field :deep(.search__hits){ margin-top: 10px; }

.query-box__pair{
  display: grid; grid-template-columns: minmax(200px, 1fr) 180px; gap: var(--w2b-space-3);
  margin-top: var(--w2b-space-4); padding-top: var(--w2b-space-4);
  border-top: 1px dashed var(--w2b-line);
}
/* The readings. Recognised is dashed — it was read, not decided; insisted on
   is solid, with a way back out. */
.kinds{
  display: flex; flex-direction: column; align-items: center;
  gap: var(--w2b-space-2); margin-top: var(--w2b-space-4);
}
.kinds__label{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 10.5px;
  letter-spacing: .1em; text-transform: uppercase; color: var(--w2b-muted);
}
.kinds__group{ display: flex; justify-content: center; gap: var(--w2b-space-2); flex-wrap: wrap; }
.kind{
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer; padding: 4px 11px;
  border-radius: var(--w2b-radius-full); border: 1px solid var(--w2b-line);
  background: var(--w2b-surface); color: var(--w2b-muted);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs); letter-spacing: .02em;
}
.kind:hover{ border-color: var(--w2b-muted); color: var(--w2b-graphite); }
.kind[data-state="read"]{
  border-style: dashed; border-color: var(--w2b-primary);
  color: var(--w2b-primary); background: var(--w2b-primary-veil);
}
.kind[data-state="set"]{
  border-style: solid; border-color: transparent;
  background: var(--w2b-primary); color: var(--w2b-primary-on);
}
.kind[data-state="set"]:hover{ background: var(--w2b-primary-light); }
.kind__off{
  display: grid; place-items: center; width: 15px; height: 15px; margin-right: -3px;
  border-radius: var(--w2b-radius-full); background: rgba(255,255,255,.22); font-size: 10px; line-height: 1;
}

.query-box__note{ margin-top: var(--w2b-space-3); font-size: var(--w2b-text-s); color: var(--w2b-muted); }
.query-box__note :deep(b){ color: var(--w2b-graphite); font-weight: 600; }

/* Narrow, the button goes below the field. It sits *inside* the search's own
   row, though — so that row is what has to wrap; wrapping the box around it
   only squeezed the input to nothing. */
@container (max-width: 540px){
  .query-box__field{ padding: 10px 12px; }
  .query-box__field :deep(.search__field){ flex-wrap: wrap; row-gap: 8px; }
  .query-box__field :deep(.search__field input){ flex: 1 1 60%; font-size: 16px; padding: 6px 0; }
  .query-box__field .btn--large{ flex: 1 1 100%; }
}

@media (max-width: 560px){
  .query-box__pair{ grid-template-columns: 1fr; }
  /* On a phone the chips wrap anyway — the label above them costs a line. */
  .kinds__label{ display: none; }
}
</style>
