<template>
  <div class="stapel">
    <nav class="krume nicht-drucken" aria-label="Pfad">
      <button type="button" @click="zurueck">Grundstücke</button>
      <span aria-hidden="true">›</span><span>Vergleich</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Nebeneinander</p>
        <h1>Vergleich</h1>
        <p class="seitenkopf__unter">{{ untertitel }}</p>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still nicht-drucken" @click="zurueck">Auswahl ändern</button>
      <button type="button" class="knopf knopf--zweit nicht-drucken" @click="drucken">Drucken</button>
    </div>

    <section class="tafel">
      <div class="tafel__kopf"><h3>Kennzahlen</h3></div>
      <div class="tabelle-rollt">
        <table class="liste">
          <thead>
            <tr>
              <th>Grundstück</th><th class="zahl">Fläche</th><th class="zahl">Preis</th>
              <th class="zahl">Je m²</th><th class="zahl">Δ Bodenrichtwert</th><th>Form</th>
              <th v-if="ziel1" class="zahl">{{ ziel1.name }} ÖPNV</th>
              <th v-if="ziel2" class="zahl">{{ ziel2.name }} Rad</th>
              <th class="nicht-drucken"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in gewaehlte" :key="p.id">
              <td>
                <b>{{ p.name }}</b><br>
                <span class="zart daten">{{ p.gemarkung }} · Flst. {{ p.flurstuecke.join(" · ") }}</span>
              </td>
              <td class="zahl">{{ area(p.flaecheAmtlich) }}</td>
              <td class="zahl">{{ euro(p.kaufpreis) }}</td>
              <td class="zahl">{{ euroPerSqm(kennzahl(p).jeQuadratmeter) }}</td>
              <td class="zahl"><span class="chip" :class="`chip--${kennzahl(p).abweichungKlasse}`">{{ percent(kennzahl(p).abweichung) }}</span></td>
              <td>
                <span class="chip chip--gut">{{ kennzahl(p).formklasse }}</span>
                <span class="zart daten"> {{ num(kennzahl(p).rechteckigkeit, 2) }}</span>
              </td>
              <td v-if="ziel1" class="zahl">{{ zeit(p, ziel1.id, "transit") }}</td>
              <td v-if="ziel2" class="zahl">{{ zeit(p, ziel2.id, "bike") }}</td>
              <td class="nicht-drucken">
                <button type="button" class="knopf knopf--still knopf--klein" @click="oeffnen(p.id)">Öffnen</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="tafel">
      <div class="tafel__kopf">
        <h3>Gleicher Maßstab, gleiche Ausrichtung</h3>
        <div class="dehnen"></div><span v-if="massstabZahl" class="chip">rund 1 : {{ massstabZahl }}</span>
      </div>
      <div class="tafel__leib">
        <div class="risse">
          <figure v-for="p in gewaehlte" :key="p.id" class="riss">
            <button type="button" class="riss__knopf" :aria-label="`${p.name} öffnen`" @click="oeffnen(p.id)">
              <SitePlan :plot="p" :koerper="koerper(p)" :breite="220" :hoehe="280" :massstab="gemeinsamerMassstab" kompakt />
            </button>
            <figcaption>
              <span>{{ p.gemarkung }}</span>
              <span class="daten">R {{ num(kennzahl(p).rechteckigkeit, 2) }}</span>
            </figcaption>
          </figure>
        </div>
        <p class="fussnote">
          R = Rechteckigkeit: Polygonfläche geteilt durch die Fläche des kleinsten gedrehten
          Umschließungsrechtecks. Über 0,95 rechteckig, 0,85–0,95 fast, darunter komplex.
        </p>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import { state, placement } from "../lib/store.js";
import { plotMetrics } from "../lib/metrics.js";
import { fitScale } from "../lib/geometry.js";
import { area, euro, euroPerSqm, percent, num, duration } from "../lib/format.js";

export default {
  name: "CompareView",
  components: { SitePlan },
  computed: {
    gewaehlte() { return state.daten.grundstuecke.filter(p => state.daten.auswahl.includes(p.id)); },
    /** The smallest of the individual fits, so the largest plot still fits and
     *  every drawing shares one scale — which is what the panel claims. */
    gemeinsamerMassstab() {
      if (!this.gewaehlte.length) return null;
      return Math.min(...this.gewaehlte.map(p => fitScale(p.polygon, 220, 280, 6)));
    },
    massstabZahl() {
      // A CSS pixel is about 0.2646 mm; the drawing renders near its viewBox width.
      return this.gemeinsamerMassstab ? Math.round(1000 / (this.gemeinsamerMassstab * 0.26458) / 50) * 50 : null;
    },
    ziel1() { return state.daten.ziele[0] || null; },
    ziel2() { return state.daten.ziele[1] || null; },
    untertitel() {
      return this.gewaehlte.length
        ? `${this.gewaehlte.length} von ${state.daten.grundstuecke.length} Kandidaten. Über „Auswahl ändern“ kommen andere herein oder heraus.`
        : "Nichts ausgewählt — auf der Übersicht Kandidaten ankreuzen.";
    }
  },
  methods: {
    area, euro, euroPerSqm, percent, num,
    kennzahl(p) { return plotMetrics(p); },
    koerper(p) { return placement(p); },
    /** One mode's travel time to one destination, or a dash when the routing
     *  service found nothing. Modes are addressed by name — the mockup's
     *  positional array is gone. */
    zeit(plot, zielId, modus) {
      const m = plot.wege[zielId]?.modi?.[modus];
      return m && m.erreichbar ? duration(m.duration_s) : "—";
    },
    zurueck() { state.ansicht = "grundstuecke"; window.scrollTo({ top: 0 }); },
    oeffnen(id) { state.offenesGrundstueck = id; state.ansicht = "grundstueck"; window.scrollTo({ top: 0 }); },
    drucken() { window.print(); }
  }
};
</script>

<style scoped>
.krume{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.krume button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font: inherit; }
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 66ch; }
.zart{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.risse{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: var(--w2b-raum-4); }
.riss{ margin: 0; display: flex; flex-direction: column; gap: var(--w2b-raum-2); }
.riss__knopf{ padding: 0; border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s); overflow: hidden; background: none; cursor: pointer; }
.riss figcaption{ display: flex; justify-content: space-between; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-graphit); }
.fussnote{ margin-top: var(--w2b-raum-4); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
</style>
