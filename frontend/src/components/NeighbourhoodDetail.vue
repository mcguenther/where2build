<template>
  <!-- The analysis at full width, below the plan: every boundary as a strip,
       every section, and the houses the § 34 band is measured from. It prints
       with the page, and the tab beside the plan jumps here. -->
  <section id="nachbarschaft" class="stack nb-detail" aria-labelledby="nachbarschaft-titel">
    <div class="page-head">
      <div>
        <p class="eyebrow">Nachbarschaft</p>
        <h2 id="nachbarschaft-titel">Nachbarschaft im Detail</h2>
        <p class="page-head__sub">
          Jede Grenze gerade gezogen und im selben Maßstab, oben die Nachbarseite, unten unser
          Grundstück. Daneben die Schnitte, jeweils dort, wo ein Nachbarhaus der Grenze am nächsten
          steht, und die Häuser, aus denen das Band nach § 34 gemessen ist. Wandhöhen sind unbekannt
          und bleiben es in der Zeichnung.
        </p>
      </div>
    </div>

    <div class="nb-detail__grid">
      <section class="panel" aria-labelledby="nb-grenzen">
        <div class="panel__head"><h3 id="nb-grenzen">Grenze für Grenze</h3></div>
        <div v-for="b in analysis.boundaries" :key="b.kind" class="grenzzeile" :data-boundary="b.kind">
          <div class="grenzzeile__kopf">
            <h4>{{ heading(b) }}</h4>
            <span class="faint mono">{{ metres(b.length, 1) }}</span>
            <span class="chip" :class="`chip--${chipOf(b.status)}`">{{ statusOf(b) }}</span>
          </div>
          <BoundaryStrip :analysis="analysis" :boundary="b.kind" :title="heading(b)" :scale="10.2" />
          <span class="faint">{{ STRIP_ORIGINS[b.kind] }} · oben Nachbarseite, unten unser Grundstück</span>
          <p v-for="(s, i) in textOf(b)" :key="i">{{ s }}</p>
        </div>
      </section>

      <div class="nb-detail__column">
        <section v-if="analysis.sections.length" class="panel" aria-labelledby="nb-schnitte">
          <div class="panel__head"><h3 id="nb-schnitte">Im Schnitt</h3></div>
          <div v-for="(s, i) in analysis.sections" :key="s.buildingId" class="schnitt-block">
            <div class="grenzzeile__kopf">
              <h4>{{ sectionHeading(s, i, analysis) }}</h4>
              <span v-if="s.reading" class="faint">Lesart: {{ s.reading === READING_BOUNDARY ? "an die Grenze" : "Abstand nötig" }}</span>
            </div>
            <NeighbourSection :analysis="analysis" :section="s" :index="i" :scale="14" />
          </div>
        </section>

        <section v-if="analysis.band" class="panel" aria-labelledby="nb-band">
          <div class="panel__head"><h3 id="nb-band">Umgebung nach § 34 BauGB</h3></div>
          <div class="schnitt-block">
            <BandChart v-if="analysis.band.houses.length" :band="analysis.band" />
            <span v-if="analysis.band.houses.length" class="faint">
              Meter hinter der Straße · Balken: Nachbarhäuser auf unserer Straßenseite, darunter unser
              Bestand und unser Grundstück mit dem Bebauungsfenster
            </span>
            <p v-for="(s, i) in bandSentences" :key="i">{{ s }}</p>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script>
import BoundaryStrip from "./BoundaryStrip.vue";
import NeighbourSection from "./NeighbourSection.vue";
import BandChart from "./BandChart.vue";
import { metres } from "../lib/format.js";
import {
  bandFinding, boundaryHeading, boundaryStatusLabel, clearBoundarySentence, sectionHeading
} from "../lib/findings.js";
import { READING_BOUNDARY, CLASS_CLEAR } from "../lib/neighbourhood.js";
import { STRIP_ORIGINS } from "../lib/neighbourhoodDrawing.js";

const CHIPS = { boundary: "warn", overlap: "warn", accessory: "unknown", [CLASS_CLEAR]: "good" };

export default {
  name: "NeighbourhoodDetail",
  components: { BoundaryStrip, NeighbourSection, BandChart },
  props: {
    analysis: { type: Object, required: true },
    /** `neighbourhoodFindings(analysis)`: the strips carry their sentences. */
    findings: { type: Array, default: () => [] }
  },
  data() { return { READING_BOUNDARY, STRIP_ORIGINS }; },
  computed: {
    bandSentences() { return bandFinding(this.analysis.band)?.sentences ?? []; }
  },
  methods: {
    metres,
    sectionHeading,
    heading(b) { return boundaryHeading(b, this.analysis); },
    statusOf(b) { return boundaryStatusLabel(b); },
    chipOf(status) { return CHIPS[status] ?? "unknown"; },
    /** The sentences of every finding at this boundary, in list order. */
    textOf(b) {
      const ids = new Set(b.facing.map(f => f.buildingId));
      const found = this.findings.filter(f => f.buildingId && ids.has(f.buildingId)).flatMap(f => f.sentences);
      return found.length ? found : [clearBoundarySentence(b)];
    }
  }
};
</script>

<style scoped>
.nb-detail{ scroll-margin-top: var(--w2b-space-4); }
.nb-detail__grid{ display: grid; gap: var(--w2b-space-4); grid-template-columns: minmax(0, 1fr); align-items: start; }
@media (min-width: 1100px){ .nb-detail__grid{ grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
.nb-detail__column{ display: flex; flex-direction: column; gap: var(--w2b-space-4); min-width: 0; }
.grenzzeile, .schnitt-block{
  display: grid; gap: 8px; padding: 14px 16px; border-top: 1px solid var(--w2b-line-faint); min-width: 0;
}
.panel__head + .grenzzeile, .panel__head + .schnitt-block{ border-top: 0; }
.grenzzeile__kopf{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.grenzzeile__kopf h4{ margin: 0; font-family: var(--w2b-font-display); font-size: var(--w2b-text-m); font-weight: 600; }
.grenzzeile__kopf .chip, .grenzzeile__kopf .faint:last-child{ margin-left: auto; }
.grenzzeile p, .schnitt-block p{ margin: 0; font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.mono{ font-family: var(--w2b-font-mono); }

@media print{
  .nb-detail{ break-before: page; }
  .nb-detail__grid{ display: block !important; }
  .grenzzeile, .schnitt-block{ break-inside: avoid; padding: 4pt 0 !important; }
  /* Paper has no scrolling: a strip wider than the sheet is scaled to it. */
  .nb-detail :deep(.scroll-x){ overflow: visible !important; }
  .nb-detail :deep(.scroll-x svg){ max-width: 100% !important; height: auto !important; }
}
</style>
