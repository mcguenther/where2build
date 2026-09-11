<template>
  <div v-if="plot" class="stack location-page">
    <nav class="breadcrumb no-print" aria-label="Pfad">
      <RouterLink :to="{ name: 'plots' }">Grundstücke</RouterLink>
      <span aria-hidden="true">›</span>
      <RouterLink :to="{ name: 'plot', params: { id: plot.id } }">{{ plot.name }}</RouterLink>
      <span aria-hidden="true">›</span>
      <span>Standort</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Standort</p>
        <h1>Was am Grundstück gilt</h1>
        <p class="page-head__sub">
          Lärm, Hochwasser, Radon, Trinkwasserschutz, Schutzgebiete, Hangneigung, Baugrund
          und Luftqualität, gefragt mit dem Umriss des Flurstücks, nicht mit einem Punkt.
          Ein Grundstück schneidet Isophonen und Zonengrenzen; sein Mittelpunkt antwortet
          nur für einen Quadratmeter davon.
        </p>
      </div>
      <div class="spacer"></div>
      <div class="row no-print">
        <RouterLink class="btn btn--quiet" :to="{ name: 'plot', params: { id: plot.id } }">
          Zum Lageplan
        </RouterLink>
        <button type="button" class="btn btn--secondary" @click="print">Drucken</button>
      </div>
    </div>

    <p v-if="!plot.anchor" class="notice notice--error">
      Für dieses Grundstück ist keine Koordinate hinterlegt. Ohne sie gibt es keine Fläche,
      mit der sich die Fachdienste fragen ließen.
    </p>

    <div v-else class="location-grid print-sheet">
      <aside class="location-grid__facts">
        <section class="panel">
          <div class="panel__head"><h3>Flurstück</h3><div class="spacer"></div><span class="chip">ALKIS</span></div>
          <dl class="value-list">
            <dt>Gemarkung</dt><dd>{{ plot.gemarkung || "—" }}</dd>
            <dt>Flurstücke</dt><dd>{{ plot.flurstuecke.join(" · ") || "—" }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
            <dt>Lagebezeichnung</dt><dd>{{ plot.lagebezeichnung || "—" }}</dd>
            <dt>Gemeinde</dt><dd>{{ plot.municipality || "—" }}</dd>
            <dt>Koordinate</dt>
            <dd class="mono">{{ num(plot.anchor.lat, 5) }} · {{ num(plot.anchor.lon, 5) }}</dd>
          </dl>
        </section>

        <section class="panel">
          <div class="panel__head"><h3>Bodenrichtwert</h3><div class="spacer"></div><span class="chip">BORIS</span></div>
          <p v-if="!Number.isFinite(plot.bodenrichtwert)" class="location-page__empty">
            Für dieses Grundstück liegt kein Bodenrichtwert vor. Ohne ihn bleibt die
            Preiseinordnung leer; sie wird nicht geschätzt.
          </p>
          <template v-else>
            <p class="location-page__value">
              {{ num(plot.bodenrichtwert, 0) }} <small>€/m²</small>
            </p>
            <dl class="value-list">
              <dt>Stichtag</dt><dd>{{ date(plot.brwReferenceDate) }}</dd>
              <dt>Richtwertzone</dt><dd>{{ plot.brwZone || "—" }}</dd>
              <dt v-if="plot.brwReferencePlotArea">Richtwertgrundstück</dt>
              <dd v-if="plot.brwReferencePlotArea">{{ area(plot.brwReferencePlotArea) }}</dd>
              <dt>Dieses Flurstück</dt><dd>{{ area(plot.officialArea) }}</dd>
            </dl>
            <p v-if="conversionNeeded" class="location-page__note">
              Der Richtwert gilt für ein gedachtes Grundstück von
              {{ area(plot.brwReferencePlotArea) }}. Für {{ area(plot.officialArea) }} ist er
              nach der Umrechnungstabelle des Gutachterausschusses anzupassen. Das Produkt
              aus Wert und Fläche ist also nicht der Bodenwert dieses Grundstücks.
              <a v-if="plot.brwConversionUrl" :href="plot.brwConversionUrl"
                 target="_blank" rel="noopener noreferrer">Umrechnungstabelle</a>
            </p>
          </template>
        </section>

        <CheckList :plot="plot" auto @loaded="r => (checks = r)" />
      </aside>

      <section class="panel location-grid__map">
        <div class="plan-bar no-print">
          <span class="plan-bar__label">Grund</span>
          <div class="button-group" role="group" aria-label="Kartenhintergrund">
            <button v-for="b in backdrops" :key="b.id" type="button"
                    :aria-pressed="String(backdrop === b.id)"
                    @click="backdrop = b.id">{{ b.name }}</button>
          </div>
          <div class="spacer"></div>
          <span class="plan-bar__label">Ebene</span>
          <button type="button" class="toggle" :aria-pressed="String(Boolean(overlay))"
                  @click="toggleNoise">Lärm</button>
        </div>

        <SitePlan :plot="plot" :building="null" :show-building="false" navigable
                  :backdrop="backdrop" :overlay="overlay" north-up
                  :show-dimensions="false" :show-setbacks="false"
                  :width="900" :height="620" />

        <div v-if="overlay" class="key">
          <p class="key__head">Schallpegel L<sub>DEN</sub> über 24 Stunden, dB(A)</p>
          <ul class="key__bands">
            <li v-for="band in noiseBands" :key="band.label">
              <span class="key__swatch" :style="{ background: band.colour }"></span>{{ band.label }}
            </li>
          </ul>
          <p class="key__note">
            Die Karte zeichnet erst ab 50 dB(A). Das Band 45–49 dB(A) steckt in den Daten
            und hat in der amtlichen Darstellung keine Farbe; die Prüfung oben liest die
            Daten, nicht das Bild.
          </p>
        </div>

        <div class="plan-foot">
          <span>{{ overlay ? "Isophonen: LfULG · " : "" }}Kataster und Luftbild: © GeoSN, dl-de/by-2-0</span>
          <span v-if="checks">Abgerufen {{ date(checks.abgerufen_am) }}</span>
        </div>
      </section>
    </div>
  </div>

  <div v-else class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Grundstück</p>
        <h1>Dieses Grundstück liegt nicht in diesem Browser</h1>
        <p class="page-head__sub">
          Grundstücke werden nur hier gespeichert, nicht auf einem Server. Unter
          <span class="mono">{{ id }}</span> ist hier keines hinterlegt.
        </p>
      </div>
    </div>
    <div class="missing">
      <div class="row">
        <RouterLink class="btn" :to="{ name: 'plots' }">Zur Übersicht</RouterLink>
      </div>
    </div>
  </div>
</template>

<script>
/**
 * The location page: the map large, the record beside it.
 *
 * grundradar gives its map about a third of the width and puts the check list
 * next to it; here the map had been an accessory. That is the layout this page
 * takes over — with two differences that are the point of it. The checks are
 * asked with the parcel outline rather than a point, so a plot that straddles
 * two noise bands is reported as straddling them. And there is no score:
 * eleven checks, three of which nobody can answer, do not average into a number
 * that says anything about a plot.
 *
 * The plan draws no house here. This page is about the ground, and a footprint
 * nobody has placed yet would be the loudest thing on it.
 */
import SitePlan from "../components/SitePlan.vue";
import CheckList from "../components/CheckList.vue";
import { plotById } from "../lib/store.js";
import { NOISE_BANDS } from "../lib/basemap.js";
import { area, num, date } from "../lib/format.js";

export default {
  name: "LocationView",
  components: { SitePlan, CheckList },
  props: {
    /** The plot's id, straight out of the URL. */
    id: { type: String, required: true }
  },
  data() {
    return {
      checks: null,
      backdrop: "map",
      /** The overlay id, or null. One switch, because two noise layers on top
       *  of each other are two answers to the same question. */
      overlay: null,
      backdrops: [
        { id: "map", name: "Karte" },
        { id: "aerial", name: "Luftbild" },
        { id: "cadastre", name: "Kataster" }
      ]
    };
  },
  computed: {
    plot() { return plotById(this.id); },
    noiseBands() { return NOISE_BANDS.laerm; },
    /** Only worth a sentence when the two areas actually differ. */
    conversionNeeded() {
      const reference = this.plot?.brwReferencePlotArea;
      const own = this.plot?.officialArea;
      return Number.isFinite(reference) && Number.isFinite(own) && Math.abs(reference - own) > 1;
    }
  },
  methods: {
    area, num, date,
    toggleNoise() { this.overlay = this.overlay ? null : "laerm"; },
    print() { window.print(); }
  }
};
</script>

<style scoped>
.location-grid{
  display: grid; gap: var(--w2b-space-4);
  grid-template-columns: minmax(320px, 32fr) minmax(0, 68fr);
  align-items: start;
}
@media (max-width: 1000px){
  .location-grid{ grid-template-columns: 1fr; }
  /* On a phone the map comes first: it is what says where this is, and eleven
     checks below it are a long way to scroll before seeing anything. */
  .location-grid__map{ order: -1; }
}

.location-grid__facts{ display: grid; gap: var(--w2b-space-4); align-content: start; }
/* No padding: the bar and the source line sit flush against the panel's edges
   and are separated by rules, like the plan frame on the plot page. */
.location-grid__map{ overflow: hidden; }
.location-grid__map :deep(.site-plan){ display: block; }
/* The column of checks is several times taller than the map. Sticky keeps the
   plot in view while its record is read — which is the whole point of giving
   the map the larger half. */
@media (min-width: 1001px){
  .location-grid__map{ position: sticky; top: var(--w2b-space-3); }
}

.location-page__empty{
  margin: 0; padding: 0 var(--w2b-space-4) var(--w2b-space-4);
  color: var(--w2b-muted); font-size: var(--w2b-text-s);
}
.location-page__value{
  margin: 0; padding: var(--w2b-space-3) var(--w2b-space-4) var(--w2b-space-2);
  font-family: var(--w2b-font-display);
  font-weight: 700; font-size: 30px; letter-spacing: -.02em; line-height: 1;
}
.location-page__value small{ font-size: 15px; font-weight: 600; color: var(--w2b-muted); }
.location-page__note{
  margin: 0; padding: var(--w2b-space-3) var(--w2b-space-4);
  border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-xs); color: var(--w2b-graphite); line-height: 1.5;
}

.key{
  padding: var(--w2b-space-3);
  border-top: 1px solid var(--w2b-line);
}
.key__head{ margin: 0 0 6px; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.key__bands{
  display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 0; padding: 0; list-style: none;
  font-family: var(--w2b-font-mono); font-size: 11px; font-variant-numeric: tabular-nums;
}
.key__bands li{ display: flex; align-items: center; gap: 6px; }
.key__swatch{
  width: 14px; height: 10px; border-radius: 2px; border: 1px solid var(--w2b-line);
}
.key__note{
  margin: 8px 0 0; font-size: var(--w2b-text-xs); color: var(--w2b-muted);
  max-width: 68ch; line-height: 1.5;
}
</style>
