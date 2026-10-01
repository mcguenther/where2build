<template>
  <div class="nachbarschaft">
    <section class="panel">
      <div class="panel__head">
        <h3>Nachbarschaft</h3><span class="spacer"></span>
        <span v-if="counter" class="faint">{{ counter }}</span>
      </div>

      <p v-if="!hasAnchor" class="notice nb-note">
        Ohne Koordinate lassen sich keine Nachbargebäude finden.
      </p>
      <p v-else-if="busy" class="notice nb-note nb-note--wait" role="status">Nachbargebäude werden geholt …</p>
      <p v-else-if="error" class="notice notice--error nb-note" role="alert">{{ error }}</p>
      <p v-else-if="analysis && !analysis.buildings.length" class="notice nb-note">
        In der Umgebung ist dort kein Gebäude erfasst.
      </p>

      <template v-else-if="analysis">
        <BoundaryKey :analysis="analysis" :open="open && open.kind === 'strip' ? open.boundary : null"
                     class="no-print" @pick="pickBoundary" />
        <!-- A boundary picked in the key that no numbered finding looks at
             opens here, under the key. -->
        <div v-if="open && open.kind === 'strip' && !open.findingId" class="aufklapp aufklapp--oben no-print">
          <div class="aufklapp__kopf">
            <b>{{ headingOf(open.boundary) }}</b><span>{{ STRIP_ORIGINS[open.boundary] }}</span>
            <button type="button" @click="$emit('open', null)">Schließen</button>
          </div>
          <BoundaryStrip :analysis="analysis" :boundary="open.boundary" :title="headingOf(open.boundary)" />
          <p class="aufklapp__text">{{ clearSentence(open.boundary) }}</p>
        </div>

        <div class="befunde">
          <div v-for="f in numbered" :key="f.id" class="befund" :class="{ 'is-active': isActive(f) }"
               :data-finding="f.id" :data-building="f.buildingId"
               @pointerenter="$emit('hover', f.buildingId)" @pointerleave="$emit('hover', null)">
            <button type="button" class="nummer" :aria-pressed="String(isActive(f))"
                    :aria-label="`Im Plan zeigen: ${f.title}`" @click="$emit('pin', f.buildingId)">{{ f.marker }}</button>
            <span class="befund__zeile">
              <button type="button" class="befund__titel" @click="$emit('pin', f.buildingId)">{{ f.title }}</button>
              <span class="chip" :class="`chip--${chipOf(f.status)}`">{{ f.statusLabel }}</span>
              <span class="befund__wert">{{ valueOf(f) }}</span>
            </span>
            <div class="befund__text">
              <p v-for="(s, i) in leadSentences(f)" :key="i">{{ s }}</p>
            </div>
            <div v-if="f.readingSentences" class="lesart">
              <span class="lesart__kopf">Lesart</span>
              <div class="button-group no-print" role="group" :aria-label="`Lesart für ${f.title}`">
                <button type="button" :aria-pressed="String(f.reading !== READING_BOUNDARY)"
                        @click="$emit('reading', { buildingId: f.buildingId, reading: READING_SETBACK })">Abstand nötig</button>
                <button type="button" :aria-pressed="String(f.reading === READING_BOUNDARY)"
                        @click="$emit('reading', { buildingId: f.buildingId, reading: READING_BOUNDARY })">An die Grenze darf gebaut werden</button>
              </div>
              <p class="print-only">Lesart: {{ f.reading === READING_BOUNDARY ? "An die Grenze darf gebaut werden" : "Abstand nötig" }}</p>
              <p>{{ READING_DEFAULT_REASON }}</p>
            </div>
            <div v-if="f.readingSentences" class="befund__text">
              <p>{{ f.sentences[f.sentences.length - 1] }}</p>
            </div>
            <div v-if="targets(f).boundary || targets(f).section !== null" class="befund__knoepfe no-print">
              <button v-if="targets(f).boundary" type="button" class="knopf"
                      :aria-expanded="String(isOpen(f, 'strip'))" @click="toggle(f, 'strip')">Grenze ansehen</button>
              <button v-if="targets(f).section !== null" type="button" class="knopf"
                      :aria-expanded="String(isOpen(f, 'section'))" @click="toggle(f, 'section')">Im Schnitt</button>
            </div>
            <div v-if="isOpen(f, 'strip')" class="aufklapp no-print">
              <div class="aufklapp__kopf">
                <b>{{ headingOf(targets(f).boundary) }}</b><span>{{ STRIP_ORIGINS[targets(f).boundary] }}</span>
                <button type="button" @click="$emit('open', null)">Schließen</button>
              </div>
              <BoundaryStrip :analysis="analysis" :boundary="targets(f).boundary"
                             :title="headingOf(targets(f).boundary)" :focus-at="focusOf(f)" />
            </div>
            <div v-if="isOpen(f, 'section')" class="aufklapp no-print">
              <div class="aufklapp__kopf">
                <b>Schnitt {{ targets(f).section + 1 }}</b><span>Blick von der Straße</span>
                <button type="button" @click="$emit('open', null)">Schließen</button>
              </div>
              <NeighbourSection :analysis="analysis" :section="analysis.sections[targets(f).section]"
                                :index="targets(f).section" />
              <p class="aufklapp__text">Unter dem Boden, von oben: unsere Abstandsfläche · die 3 m der Nachbarn · 6-m-Zone</p>
            </div>
          </div>

          <p class="trenner eyebrow">Ohne Marke</p>
          <div v-for="f in unnumbered" :key="f.id" class="befund" :data-finding="f.id">
            <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">
              <template v-if="f.status === 'band'">
                <rect x="2" y="7" width="20" height="10" class="glyph-band" />
                <line x1="5" y1="5" x2="5" y2="19" class="glyph-band-line" />
                <line x1="19" y1="5" x2="19" y2="19" class="glyph-band-line" />
              </template>
              <template v-else-if="f.status === 'clear'">
                <rect x="3" y="6" width="18" height="12" rx="2" class="glyph-plot" />
                <path d="M7 12.5l3 3 6-6" class="glyph-check" />
              </template>
              <template v-else>
                <circle cx="12" cy="12" r="8.5" class="glyph-open" />
                <text x="12" y="16" text-anchor="middle" class="glyph-open-text">?</text>
              </template>
            </svg>
            <span class="befund__zeile">
              <span class="befund__titel befund__titel--still">{{ f.title }}</span>
              <span class="chip" :class="`chip--${chipOf(f.status)}`">{{ f.statusLabel }}</span>
              <span class="befund__wert">{{ valueOf(f) }}</span>
            </span>
            <div class="befund__text"><p v-for="(s, i) in f.sentences" :key="i">{{ s }}</p></div>
            <div v-if="f.id === 'band' && analysis.band && analysis.band.houses.length" class="befund__knoepfe no-print">
              <button type="button" class="knopf" @click="$emit('frame', 'street')">Auf der Straße zeigen</button>
            </div>
          </div>
        </div>
        <div class="zum-detail no-print">
          <span class="faint">Alle Grenzen, die Schnitte, die Umgebung</span>
          <a href="#nachbarschaft" @click.prevent="toDetail">Alle Grenzen und Schnitte ↓</a>
        </div>
        <p class="panel__footnote">Umrisse aus {{ source }}, ohne Wandhöhen.</p>
      </template>
    </section>

    <section v-if="hasAnchor" class="panel">
      <div class="panel__head"><h3>Planungsrecht</h3></div>
      <p v-if="planningBusy" class="notice nb-note nb-note--wait" role="status">RAPIS Sachsen wird gefragt …</p>
      <p v-else-if="planningError" class="notice notice--error nb-note" role="alert">{{ planningError }}</p>
      <div class="befunde">
        <div v-for="f in planningLines" :key="f.id" class="befund" :data-finding="f.id">
          <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <template v-if="f.status === 'open'">
              <circle cx="12" cy="12" r="8.5" class="glyph-open" />
              <text x="12" y="16" text-anchor="middle" class="glyph-open-text">?</text>
            </template>
            <template v-else>
              <rect x="5" y="3" width="14" height="18" rx="1.5" class="glyph-law" />
              <line x1="8" y1="8" x2="16" y2="8" class="glyph-law" />
              <line x1="8" y1="12" x2="16" y2="12" class="glyph-law" />
              <line x1="8" y1="16" x2="13" y2="16" class="glyph-law" />
            </template>
          </svg>
          <span class="befund__zeile">
            <span class="befund__titel befund__titel--still">{{ f.title }}</span>
            <span class="chip" :class="`chip--${chipOf(f.status)}`">{{ f.statusLabel }}</span>
          </span>
          <div class="befund__text"><p v-for="(s, i) in f.sentences" :key="i">{{ s }}</p></div>
        </div>
      </div>
      <p v-if="planning" class="panel__footnote quelle-zeile">
        <a v-if="planning.quelle_url" :href="planning.quelle_url" target="_blank" rel="noopener noreferrer">{{ planning.quelle }}</a>
        <span v-else>{{ planning.quelle }}</span>
        <template v-if="planning.datenstand"> · Datenstand {{ day(planning.datenstand) }}</template>
        <span v-if="planning.hinweis" class="quelle-zeile__hinweis">{{ planning.hinweis }}</span>
      </p>
    </section>
  </div>
</template>

<script>
import BoundaryKey from "./BoundaryKey.vue";
import BoundaryStrip from "./BoundaryStrip.vue";
import NeighbourSection from "./NeighbourSection.vue";
import { metres, num } from "../lib/format.js";
import {
  planningFindings, easementFinding, boundaryHeading, clearBoundarySentence, READING_DEFAULT_REASON
} from "../lib/findings.js";
import { READING_BOUNDARY, READING_SETBACK } from "../lib/neighbourhood.js";
import { findingTargets, STRIP_ORIGINS } from "../lib/neighbourhoodDrawing.js";

/* The chip a status gets. A Grenzbebauung and an Überdeckung want attention,
   not alarm: the red of a violation is for the house leaving the envelope. */
/** Matches `.plan-grid` in PlotView: one column at 1140 px and below. */
const SIDE_BY_SIDE = "(min-width: 1141px)";

const CHIPS = {
  boundary: "warn", overlap: "warn", accessory: "unknown", own: "unknown", clear: "good",
  band: "band", heights: "open", plan: "law", procedure: "warn", likely34: "law", fnp: "law", open: "open"
};

export default {
  name: "NeighbourhoodPane",
  components: { BoundaryKey, BoundaryStrip, NeighbourSection },
  props: {
    analysis: { type: Object, default: null },
    findings: { type: Array, default: () => [] },
    busy: { type: Boolean, default: false },
    error: { type: String, default: null },
    /** Where the outlines came from, as a dative: „dem Liegenschaftskataster". */
    source: { type: String, default: "dem Liegenschaftskataster" },
    hasAnchor: { type: Boolean, default: true },
    planning: { type: Object, default: null },
    planningBusy: { type: Boolean, default: false },
    planningError: { type: String, default: null },
    municipality: { type: String, default: "" },
    activeBuilding: { type: String, default: null },
    /** `{ kind: "strip" | "section", findingId, boundary, section }` or null. */
    open: { type: Object, default: null }
  },
  emits: ["hover", "pin", "open", "reading", "frame"],
  data() { return { READING_BOUNDARY, READING_SETBACK, READING_DEFAULT_REASON, STRIP_ORIGINS }; },
  computed: {
    numbered() { return this.findings.filter(f => f.marker); },
    unnumbered() { return this.findings.filter(f => !f.marker); },
    counter() {
      if (!this.analysis || !this.analysis.buildings.length) return null;
      return `${this.numbered.length} eingeordnet · ${this.analysis.clear.count} ohne Befund`;
    },
    /* The Baulast line holds whatever RAPIS answered, because it says where to
       ask, not what is there; the plan lines only once RAPIS has answered. */
    planningLines() {
      const lines = this.planning ? planningFindings(this.planning, this.municipality) : [];
      return this.planningBusy ? [] : [...lines, easementFinding(this.municipality)];
    }
  },
  methods: {
    metres,
    day(value) {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? "");
      return m ? `${m[3]}.${m[2]}.${m[1]}` : "—";
    },
    chipOf(status) { return CHIPS[status] ?? "unknown"; },
    targets(f) { return findingTargets(f, this.analysis); },
    building(id) { return this.analysis?.buildings.find(b => b.id === id) ?? null; },
    headingOf(kind) { return boundaryHeading(this.analysis?.boundaries.find(b => b.kind === kind), this.analysis); },
    clearSentence(kind) {
      const boundary = this.analysis?.boundaries.find(b => b.kind === kind);
      return boundary && !boundary.facing.length ? clearBoundarySentence(boundary) : null;
    },
    isActive(f) { return Boolean(this.activeBuilding) && this.activeBuilding === f.buildingId; },
    isOpen(f, kind) { return this.open?.kind === kind && this.open?.findingId === f.id; },
    /** The Grenzbebauung carries its reading sentence below the switch. */
    leadSentences(f) { return f.readingSentences ? f.sentences.slice(0, -1) : f.sentences; },
    valueOf(f) {
      if (f.id === "band") {
        const band = this.analysis?.band;
        return band?.front ? `${num(band.front.min, 1)}–${metres(band.front.max, 1)}` : "—";
      }
      if (f.id === "clear") return this.analysis?.clear.nearest !== null ? `ab ${metres(this.analysis.clear.nearest, 1)}` : "—";
      if (f.status === "own") {
        const own = this.analysis.buildings.filter(b => b.class === "own").map(b => b.toBoundary).filter(Number.isFinite);
        return own.length ? metres(Math.min(...own)) : "—";
      }
      const b = this.building(f.buildingId);
      return b && Number.isFinite(b.gap) ? metres(b.gap) : "—";
    },
    focusOf(f) {
      const face = this.building(f.buildingId)?.facing?.face;
      return face ? (face.from + face.to) / 2 : null;
    },
    toggle(f, kind) {
      if (this.isOpen(f, kind)) { this.$emit("open", null); return; }
      const t = this.targets(f);
      this.$emit("open", { kind, findingId: f.id, boundary: t.boundary, section: kind === "section" ? t.section : null });
    },
    /** From the key: the first numbered finding at that boundary opens with
     *  its strip, so the text and the drawing stand together. */
    pickBoundary(kind) {
      if (this.open?.kind === "strip" && this.open.boundary === kind) { this.$emit("open", null); return; }
      const f = this.numbered.find(x => this.targets(x).boundary === kind);
      this.$emit("open", { kind: "strip", findingId: f?.id ?? null, boundary: kind, section: null });
    },
    /** A building picked on the plan brings its entry to the top of the
     *  window, beside the plan, which is sticky. Only where the two stand side
     *  by side: stacked, the scroll would carry the plan out of sight. */
    reveal(buildingId) {
      if (!window.matchMedia?.(SIDE_BY_SIDE).matches) return;
      const entry = this.$el.querySelector?.(`.befunde [data-building="${CSS.escape(buildingId)}"]`);
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      entry?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
    },
    toDetail() {
      const target = document.getElementById("nachbarschaft");
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      target?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }
  }
};
</script>

<style scoped>
.nachbarschaft{ display: flex; flex-direction: column; gap: var(--w2b-space-4); min-width: 0; }
.nb-note{ margin: var(--w2b-space-3); }
.nb-note--wait{ animation: w2b-pulse 1.5s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce){ .nb-note--wait{ animation: none; } }

.befunde{ display: flex; flex-direction: column; }
.befund{
  display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 4px 10px;
  padding: 12px 14px; border-top: 1px solid var(--w2b-line-faint); position: relative;
  /* Brought up by a pick on the plan: level with the sticky plan's top. */
  scroll-margin-top: var(--w2b-space-3);
}
.befunde > .befund:first-child{ border-top: 0; }
.befund.is-active{ background: var(--w2b-primary-veil); }
.befund__zeile{ display: flex; align-items: baseline; gap: 6px 8px; flex-wrap: wrap; min-width: 0; }
.befund__titel{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-m); color: var(--w2b-ink);
  background: none; border: 0; padding: 0; cursor: pointer; text-align: left;
}
.befund__titel:hover{ color: var(--w2b-primary); }
.befund__titel--still{ cursor: default; }
.befund__titel--still:hover{ color: var(--w2b-ink); }
.befund__wert{
  margin-left: auto; font-family: var(--w2b-font-mono); font-size: var(--w2b-text-xs);
  color: var(--w2b-muted); white-space: nowrap;
}
.befund__text{ grid-column: 2; font-size: var(--w2b-text-s); color: var(--w2b-graphite); line-height: 1.5; min-width: 0; }
.befund__text p{ margin: 0; }
.befund__text p + p{ margin-top: 6px; }
.befund__knoepfe{ grid-column: 2; display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.knopf{
  border: 1px solid var(--w2b-line); background: var(--w2b-surface); border-radius: var(--w2b-radius-full);
  padding: 3px 10px; font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  color: var(--w2b-primary); cursor: pointer;
}
.knopf:hover{ border-color: var(--w2b-primary); }
.knopf:focus-visible, .nummer:focus-visible, .befund__titel:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: 2px; }
.knopf[aria-expanded="true"]{ background: var(--w2b-primary); border-color: var(--w2b-primary); color: var(--w2b-primary-on); }
.nummer{
  width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; padding: 0;
  border: 1.5px solid var(--w2b-ink); background: var(--w2b-surface); color: var(--w2b-ink);
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 12px; margin-top: 1px; cursor: pointer;
}
.befund.is-active .nummer{ background: var(--w2b-primary); border-color: var(--w2b-primary); color: var(--w2b-primary-on); }
.glyph{ width: 24px; height: 24px; display: block; margin-top: 1px; }
.glyph-band{ fill: var(--w2b-map-band-strong); }
.glyph-band-line{ stroke: var(--w2b-map-band-line); stroke-width: 1.2; stroke-dasharray: 3 2; }
.glyph-plot{ fill: var(--w2b-map-surface); stroke: var(--w2b-map-boundary); stroke-width: 1.4; }
.glyph-check{ fill: none; stroke: var(--w2b-good); stroke-width: 1.8; }
.glyph-open{ fill: none; stroke: var(--w2b-muted); stroke-width: 1.4; stroke-dasharray: 3 2.5; }
.glyph-open-text{ font-family: var(--w2b-font-display); font-weight: 600; font-size: 11px; fill: var(--w2b-muted); }
.glyph-law{ fill: none; stroke: var(--w2b-primary); stroke-width: 1.4; }

.chip--band{ background: var(--w2b-map-band-strong); color: var(--w2b-ink); }
.chip--open{ background: transparent; color: var(--w2b-muted); border: 1px dashed var(--w2b-line); }
.chip--law{ background: var(--w2b-primary-veil); color: var(--w2b-primary); }

.lesart{
  grid-column: 2; display: grid; gap: 6px; margin-top: 6px; padding: 8px 10px; min-width: 0;
  border-radius: var(--w2b-radius-s); background: var(--w2b-surface-sunken); border: 1px solid var(--w2b-line-faint);
}
.lesart__kopf{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 10.5px; letter-spacing: .1em;
  text-transform: uppercase; color: var(--w2b-muted);
}
.lesart .button-group{ align-self: start; flex-wrap: wrap; }
.lesart .button-group button{ white-space: normal; text-align: left; line-height: 1.3; }
.lesart p{ margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-graphite); }

.aufklapp{
  grid-column: 1 / -1; margin-top: 8px; min-width: 0;
  border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s); background: var(--w2b-surface); overflow: hidden;
}
.aufklapp--oben{ margin: 0 14px 10px; }
.aufklapp__kopf{
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; padding: 7px 10px;
  border-bottom: 1px solid var(--w2b-line-faint); font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.aufklapp__kopf b{ font-family: var(--w2b-font-display); color: var(--w2b-ink); font-size: var(--w2b-text-s); }
.aufklapp__kopf button{
  margin-left: auto; border: 0; background: none; color: var(--w2b-primary); cursor: pointer;
  font-weight: 600; font-size: var(--w2b-text-xs); font-family: var(--w2b-font-body);
}
.aufklapp__text{ margin: 0; padding: 6px 10px; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }

.trenner{ margin: 0; padding: 8px 14px 4px; border-top: 1px solid var(--w2b-line); }
.zum-detail{
  display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 10px 14px; border-top: 1px solid var(--w2b-line); font-size: var(--w2b-text-s);
}
.zum-detail a{ font-family: var(--w2b-font-display); font-weight: 600; text-decoration: none; color: var(--w2b-primary); }
.zum-detail a:hover{ text-decoration: underline; }
.quelle-zeile{ display: grid; gap: 4px; font-family: var(--w2b-font-mono); font-size: 10.5px; }
.quelle-zeile a{ color: var(--w2b-primary); }
.quelle-zeile__hinweis{ font-family: var(--w2b-font-body); font-size: var(--w2b-text-xs); }

@media print{
  .befund{ padding: 3pt 0 !important; }
  .befund.is-active{ background: none !important; }
  .lesart{ background: none !important; padding: 0 !important; border: 0 !important; }
}
</style>
