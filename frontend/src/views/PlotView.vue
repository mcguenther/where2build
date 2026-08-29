<template>
  <div v-if="plot" class="stapel grundstueck-seite">
    <nav class="krume nicht-drucken" aria-label="Pfad">
      <button type="button" @click="zurueck">Grundstücke</button>
      <span aria-hidden="true">›</span>
      <span>{{ plot.name }}</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Gemarkung {{ plot.gemarkung }} · {{ plot.flurstuecke.length }} Flurstück{{ plot.flurstuecke.length > 1 ? 'e' : '' }}</p>
        <h1>{{ plot.name }}</h1>
        <p class="seitenkopf__unter">
          {{ plot.ort }} · Flurstück {{ plot.flurstuecke.join(" und ") }} ·
          {{ area(plot.flaecheAmtlich) }} · {{ euro(plot.kaufpreis) }}
        </p>
        <p v-if="plot.notiz" class="seitenkopf__notiz">{{ plot.notiz }}</p>
      </div>
      <div class="dehnen"></div>
      <div class="reihe nicht-drucken">
        <button type="button" class="knopf knopf--still" :disabled="!vorheriges" @click="blaettern(-1)">‹ Voriges</button>
        <button type="button" class="knopf knopf--still" :disabled="!naechstes" @click="blaettern(1)">Nächstes ›</button>
        <button type="button" class="knopf knopf--zweit" @click="drucken">Drucken</button>
      </div>
    </div>

    <div class="plangitter druckblatt">
      <div class="planrahmen tafel druckblatt__plan">
        <div class="planleiste nicht-drucken">
          <span class="planleiste__schild">Grund</span>
          <div class="schaltgruppe" role="group" aria-label="Kartenhintergrund">
            <button v-for="g in gruende" :key="g.id" type="button"
                    :aria-pressed="String(state.plan.grund === g.id)"
                    @click="state.plan.grund = g.id">{{ g.name }}</button>
          </div>
          <span class="planleiste__schild">Ausrichtung</span>
          <div class="schaltgruppe" role="group" aria-label="Kartenausrichtung">
            <button type="button" :aria-pressed="String(state.plan.genordet)"
                    @click="state.plan.genordet = true">Genordet</button>
            <button type="button" :aria-pressed="String(!state.plan.genordet)"
                    @click="state.plan.genordet = false">Straßenparallel</button>
          </div>
          <div class="dehnen"></div>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.nachbarn)"
                  @click="state.plan.nachbarn = !state.plan.nachbarn">Nachbarn</button>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.masse)"
                  @click="state.plan.masse = !state.plan.masse">Maße</button>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.saum)"
                  @click="state.plan.saum = !state.plan.saum">Abstandsflächen</button>
        </div>

        <p class="band" :class="verstoss ? 'band--fehler' : 'band--gut'" role="status">
          <span v-if="verstoss">
            <b>{{ ausreisser }} Gebäudeecke{{ ausreisser > 1 ? 'n liegen' : ' liegt' }} außerhalb des Bebauungsfensters.</b>
            Geringster Grenzabstand {{ metres(engsterAbstand) }}.
          </span>
          <span v-else>
            <b>Baukörper liegt im Bebauungsfenster.</b>
            Geringster Grenzabstand {{ metres(engsterAbstand) }}.
          </span>
        </p>

        <SitePlan :plot="plot" :koerper="koerper" interaktiv
                  :grund="state.plan.grund" :genordet="state.plan.genordet"
                  :nachbarn="state.plan.nachbarn" :masse="state.plan.masse" :saum="state.plan.saum"
                  @verschieben="verschieben" />

        <div class="planfuss">
          <span>ETRS89 / UTM33N — EPSG:25833</span>
          <span>© GeoSN, dl-de/by-2-0</span>
        </div>
      </div>

      <aside class="protokoll">
        <section class="tafel">
          <div class="tafel__kopf"><h3>Grundstück</h3><div class="dehnen"></div><span class="chip">ALKIS</span></div>
          <dl class="werteliste">
            <dt>Gemarkung</dt><dd>{{ plot.gemarkung }}</dd>
            <dt>Flurstücke</dt><dd>{{ plot.flurstuecke.join(" · ") }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(plot.flaecheAmtlich) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(kennzahlen.flaecheGerechnet, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ plot.polygon.length }}</dd>
            <dt>Straßenfront</dt><dd>{{ metres(kennzahlen.strassenfront) }}</dd>
          </dl>
          <p class="tafel__fussnote">
            Für den Preisvergleich zählt die amtliche Fläche. Die aus dem Polygon
            gerechnete weicht regelmäßig um ein paar Quadratmeter ab.
          </p>
        </section>

        <section class="tafel">
          <div class="tafel__kopf"><h3>Form</h3></div>
          <dl class="werteliste">
            <dt>Rechteckigkeit</dt><dd>{{ num(kennzahlen.rechteckigkeit, 3) }}</dd>
            <dt>Einstufung</dt><dd><span class="chip chip--gut">{{ kennzahlen.formklasse }}</span></dd>
            <dt>Seitenverhältnis</dt><dd>1 : {{ num(seitenverhaeltnis) }}</dd>
            <dt>Umschl. Rechteck</dt><dd>{{ num(kennzahlen.mrr.width, 1) }} × {{ num(kennzahlen.mrr.height, 1) }} m</dd>
          </dl>
        </section>

        <section class="tafel">
          <div class="tafel__kopf"><h3>Preis</h3><div class="dehnen"></div><span class="chip">BORIS</span></div>
          <dl class="werteliste">
            <dt>Kaufpreis</dt><dd>{{ euro(plot.kaufpreis) }}</dd>
            <dt>Angebot je m²</dt><dd>{{ euroPerSqm(kennzahlen.jeQuadratmeter) }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }} <span class="zart">Zone {{ plot.brwZone }}</span></dd>
            <dt>Stichtag</dt><dd>{{ date(plot.brwStichtag) }}</dd>
          </dl>
          <div class="preisband">
            <div class="preisband__skala">
              <div class="preisband__achse"></div>
              <div class="preisband__spanne" :style="{ left: pos(plot.bodenrichtwert * .85) + '%', width: (pos(plot.bodenrichtwert * 1.15) - pos(plot.bodenrichtwert * .85)) + '%' }"></div>
              <div class="preisband__brw" :style="{ left: pos(plot.bodenrichtwert) + '%' }"></div>
              <div class="preisband__marke" :style="{ left: pos(kennzahlen.jeQuadratmeter) + '%' }"
                   :title="`Angebot ${euroPerSqm(kennzahlen.jeQuadratmeter)}/m²`"></div>
            </div>
            <div class="preisband__achsentext">
              <span>{{ Math.round(spanne.lo) }} €</span>
              <span>{{ Math.round(plot.bodenrichtwert) }} €</span>
              <span>{{ Math.round(spanne.hi) }} €</span>
            </div>
            <p class="preisband__aussage">
              Das Angebot liegt <b>{{ percent(kennzahlen.abweichung) }}
              {{ kennzahlen.abweichung > 0 ? "über" : "unter" }} dem Bodenrichtwert</b> der Zone.
            </p>
          </div>
        </section>
      </aside>
    </div>

    <div class="werkzeuge">
      <section class="tafel">
        <div class="tafel__kopf"><h3>Abstandsflächen</h3><div class="dehnen"></div><span class="chip chip--warn">§ 6 SächsBO</span></div>
        <table class="liste abstands-tabelle">
          <thead><tr><th>Grenze</th><th class="zahl">Länge</th><th class="zahl">Tiefe</th></tr></thead>
          <tbody>
            <tr v-for="(grenze, i) in grenzen" :key="i">
              <td>{{ grenze.name }}</td>
              <td class="zahl">{{ metres(grenze.laenge) }}</td>
              <td class="zahl">
                <input type="number" min="0" max="20" step="0.1" class="tiefe"
                       :value="plot.tiefen[i]" :aria-label="`Abstandstiefe ${grenze.name}`"
                       @input="tiefeSetzen(i, $event.target.value)">
              </td>
            </tr>
          </tbody>
        </table>
        <div class="regler nicht-drucken">
          <label for="wandhoehe">Wandhöhe</label>
          <output class="daten">{{ metres(plot.wandhoehe) }}</output>
          <input id="wandhoehe" type="range" min="2.5" max="12" step="0.1"
                 :value="plot.wandhoehe" @input="wandhoeheSetzen($event.target.value)">
          <p class="regler__hinweis">
            0,4 · H = <b>{{ metres(plot.wandhoehe * 0.4) }}</b>
            <template v-if="plot.wandhoehe * 0.4 < 3"> — unter dem Mindestmaß von 3 m, deshalb greift der Mindestwert.</template>
            <template v-else> — maßgeblich, weil größer als das Mindestmaß von 3 m.</template>
          </p>
        </div>
      </section>

      <section class="tafel">
        <div class="tafel__kopf"><h3>Baukörper</h3></div>
        <div class="feld feld--gerahmt nicht-drucken">
          <label for="haustyp">Haustyp</label>
          <select id="haustyp" :value="plot.haustypId" @change="haustypSetzen($event.target.value)">
            <option v-for="h in state.daten.haustypen" :key="h.id" :value="h.id">
              {{ h.hersteller }} {{ h.name }} — {{ num(h.bebauteFlaeche) }} m² bebaut
            </option>
            <option :value="EIGENMASS">Eigene Maße …</option>
          </select>
        </div>

        <div v-if="istEigenmass" class="eigenmass nicht-drucken">
          <div class="feld">
            <label for="em-laenge">Länge</label>
            <input id="em-laenge" type="number" min="4" max="30" step="0.1"
                   :value="eigenmass.laenge" @input="eigenmassSetzen('laenge', $event.target.value)">
          </div>
          <div class="feld">
            <label for="em-breite">Breite</label>
            <input id="em-breite" type="number" min="4" max="30" step="0.1"
                   :value="eigenmass.breite" @input="eigenmassSetzen('breite', $event.target.value)">
          </div>
          <p class="eigenmass__hinweis">
            Ergibt {{ area(eigenmass.laenge * eigenmass.breite, 1) }} bebaute Fläche.
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button type="button" class="knopf knopf--zweit knopf--klein" @click="alsHaustypSichern">
            Als Haustyp in den Katalog
          </button>
        </div>

        <dl class="werteliste">
          <dt>Bebaute Fläche</dt><dd>{{ area(bebauteFlaeche, 2) }}</dd>
          <dt v-if="haustyp">Wohnfläche ges.</dt><dd v-if="haustyp">{{ area(haustyp.wohnflaeche, 2) }}</dd>
          <dt>Außenmaß</dt>
          <dd>{{ num(koerper.width, 1) }} × {{ num(koerper.depth, 1) }} m
            <span v-if="koerper.estimated" class="zart" title="aus der bebauten Fläche geschätzt">≈</span></dd>
          <dt>Drehung</dt><dd>{{ degrees(plot.haus.rotation) }}</dd>
          <dt>GRZ</dt><dd>{{ num(bebauteFlaeche / plot.flaecheAmtlich, 2) }}</dd>
        </dl>

        <div class="ausrichten nicht-drucken">
          <button type="button" class="knopf knopf--zweit" @click="anStrasseAusrichten">
            An der Straße ausrichten
          </button>
          <p class="regler__hinweis">
            Dreht den Baukörper parallel zur Straßenfront ({{ degrees(strassenwinkel) }})
            und schiebt ihn zurück ins Fenster, falls er dabei herausrutscht.
          </p>
        </div>

        <div v-if="koerper.estimated" class="regler nicht-drucken">
          <label for="verhaeltnis">Seitenverhältnis</label>
          <output class="daten">{{ num(plot.verhaeltnis) }}</output>
          <input id="verhaeltnis" type="range" min="1" max="2.2" step="0.01"
                 :value="plot.verhaeltnis" @input="verhaeltnisSetzen($event.target.value)">
          <p class="regler__hinweis">Aus der bebauten Fläche geschätzt — das Datenblatt liefert keine Außenmaße.</p>
        </div>

        <div class="regler nicht-drucken">
          <label for="drehung">Drehung</label>
          <output class="daten">{{ degrees(plot.haus.rotation) }}</output>
          <input id="drehung" type="range" min="-90" max="90" step="1"
                 :value="plot.haus.rotation" @input="drehungSetzen($event.target.value)">
          <p class="regler__hinweis">Haus mit der Maus ziehen, mit den Pfeiltasten fein verschieben.</p>
        </div>
      </section>

      <div class="notiz notiz--mahnung">
        <h4>Keine bauordnungsrechtliche Prüfung</h4>
        <p>Die Abstandstiefe bemisst sich nach § 6 SächsBO grundsätzlich nach der Wandhöhe;
          3 m sind der Mindestwert, nicht die Regel. Grenzgaragen sind privilegiert, ein
          Bebauungsplan kann abweichende Baugrenzen festsetzen.</p>
        <p>Nach § 15 Abs. 2 ImmoWertV kann ein einzelnes Grundstück innerhalb der
          Richtwertzone eine abweichende Nutzungsart haben — dann gilt der Zonenwert nicht.</p>
      </div>
    </div>

    <section class="stapel">
      <div class="seitenkopf">
        <div>
          <p class="marke-klein">Erreichbarkeiten</p>
          <h2>Wege von hier</h2>
          <p class="seitenkopf__unter">
            Für jedes hinterlegte Ziel Auto, Rad, ÖPNV und die beste Kombination.
            Ziele gelten für alle Grundstücke.
          </p>
        </div>
        <div class="dehnen"></div>
        <button type="button" class="knopf knopf--still nicht-drucken" @click="state.ansicht = 'ziele'">
          Ziele bearbeiten
        </button>
      </div>
      <RouteCards :plot="plot" />
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import RouteCards from "../components/RouteCards.vue";
import { state, plotById, placement, houseTypeById, houseFootprint, save, addHouseType, newId, EIGENMASS }
  from "../lib/store.js";
import { plotMetrics } from "../lib/metrics.js";
import {
  polygonEdges, edgeCompass, buildableArea, cornersOutside, smallestSetback,
  alignToEdge, alignmentToEdge
} from "../lib/geometry.js";
import { area, euro, euroPerSqm, metres, num, percent, degrees, date } from "../lib/format.js";

export default {
  name: "PlotView",
  components: { SitePlan, RouteCards },
  data() {
    return {
      state, EIGENMASS,
      gruende: [{ id: "karte", name: "Karte" }, { id: "luftbild", name: "Luftbild" }, { id: "kataster", name: "Kataster" }]
    };
  },
  computed: {
    plot() { return plotById(state.offenesGrundstueck) || state.daten.grundstuecke[0] || null; },
    koerper() { return placement(this.plot); },
    haustyp() { return houseTypeById(this.plot.haustypId); },
    istEigenmass() { return this.plot.haustypId === EIGENMASS; },
    eigenmass() { return this.plot.eigenmass || { laenge: 11.4, breite: 8.5 }; },
    bebauteFlaeche() {
      const k = houseFootprint(this.plot);
      return k.width * k.depth;
    },
    kennzahlen() { return plotMetrics(this.plot); },
    fenster() { return buildableArea(this.plot.polygon, this.plot.tiefen); },
    ausreisser() { return cornersOutside(this.koerper, this.fenster); },
    verstoss() { return this.ausreisser > 0; },
    engsterAbstand() { return smallestSetback(this.koerper, this.plot.polygon); },
    strassenwinkel() { return alignmentToEdge(this.plot.polygon, 0); },
    seitenverhaeltnis() {
      const m = this.kennzahlen.mrr;
      return Math.max(m.width, m.height) / Math.min(m.width, m.height);
    },
    spanne() { return { lo: this.plot.bodenrichtwert * 0.7, hi: this.plot.bodenrichtwert * 1.45 }; },
    grenzen() {
      return polygonEdges(this.plot.polygon).map((kante, i) => ({
        name: `${edgeCompass(this.plot.polygon, i, this.plot.nordVersatz)} — ${i === 0 ? "zur Straße" : "Nachbar"}`,
        laenge: kante.length
      }));
    },
    reihenfolge() { return state.daten.grundstuecke.findIndex(p => p.id === this.plot.id); },
    vorheriges() { return this.reihenfolge > 0; },
    naechstes() { return this.reihenfolge < state.daten.grundstuecke.length - 1; }
  },
  methods: {
    area, euro, euroPerSqm, metres, num, percent, degrees, date,
    zurueck() { state.ansicht = "grundstuecke"; window.scrollTo({ top: 0 }); },
    blaettern(schritt) {
      const ziel = state.daten.grundstuecke[this.reihenfolge + schritt];
      if (ziel) { state.offenesGrundstueck = ziel.id; window.scrollTo({ top: 0 }); }
    },
    drucken() { window.print(); },
    pos(wert) {
      const { lo, hi } = this.spanne;
      return Math.max(0, Math.min(100, ((wert - lo) / (hi - lo)) * 100));
    },
    verschieben({ cx, cy }) { this.plot.haus.cx = cx; this.plot.haus.cy = cy; save(); },
    tiefeSetzen(i, wert) {
      const v = parseFloat(wert);
      this.plot.tiefen[i] = Number.isFinite(v) && v >= 0 ? v : 0;
      save();
    },
    wandhoeheSetzen(wert) {
      this.plot.wandhoehe = parseFloat(wert);
      // § 6 SächsBO: the depth follows wall height, with 3 m as the floor.
      const tiefe = Math.round(Math.max(3, this.plot.wandhoehe * 0.4) * 10) / 10;
      this.plot.tiefen = this.plot.tiefen.map(() => tiefe);
      save();
    },
    verhaeltnisSetzen(wert) { this.plot.verhaeltnis = parseFloat(wert); save(); },
    drehungSetzen(wert) { this.plot.haus.rotation = parseFloat(wert); save(); },
    haustypSetzen(id) {
      this.plot.haustypId = id;
      if (id === EIGENMASS) {
        if (!this.plot.eigenmass) {
          const k = this.koerper;
          this.plot.eigenmass = { laenge: Math.round(k.width * 10) / 10, breite: Math.round(k.depth * 10) / 10 };
        }
      } else {
        const typ = houseTypeById(id);
        if (typ?.verhaeltnis) this.plot.verhaeltnis = typ.verhaeltnis;
      }
      save();
    },
    eigenmassSetzen(feld, wert) {
      const v = parseFloat(wert);
      if (!Number.isFinite(v)) return;
      this.plot.eigenmass = { ...this.eigenmass, [feld]: Math.min(30, Math.max(4, v)) };
      save();
    },
    alsHaustypSichern() {
      const { laenge, breite } = this.eigenmass;
      const typ = addHouseType({
        id: newId("ht"), hersteller: "Eigene Maße", name: `${num(laenge, 1)} × ${num(breite, 1)} m`,
        bebauteFlaeche: Math.round(laenge * breite * 100) / 100, wohnflaeche: null,
        wohnflaecheEg: null, wohnflaecheOg: null, laenge, breite,
        dachform: "offen", preisAb: null, verhaeltnis: laenge / breite,
        quelle: null, gelesenAm: new Date().toISOString().slice(0, 10), eigen: true
      });
      this.plot.haustypId = typ.id;
      save();
    },
    anStrasseAusrichten() {
      const neu = alignToEdge(this.plot.polygon, this.fenster, this.koerper, 0);
      this.plot.haus = { cx: neu.cx, cy: neu.cy, rotation: Math.round(neu.rotation * 10) / 10 };
      save();
    }
  }
};
</script>

<style scoped>
.krume{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.krume button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font: inherit; }
.krume button:hover{ text-decoration: underline; }

.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 64ch; }
.seitenkopf__notiz{ margin-top: var(--w2b-raum-1); color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); font-style: italic; }

.plangitter{ display: grid; grid-template-columns: minmax(0, 1fr) 336px; gap: var(--w2b-raum-4); align-items: start; }
@media (max-width: 1140px){ .plangitter{ grid-template-columns: 1fr; } }
.planrahmen{ position: sticky; top: var(--w2b-raum-3); }
@media (max-width: 1140px){ .planrahmen{ position: static; } }

.planleiste{
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: var(--w2b-raum-2) var(--w2b-raum-3); border-bottom: 1px solid var(--w2b-linie);
}
.planleiste__schild{
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: 10.5px;
  letter-spacing: .1em; text-transform: uppercase; color: var(--w2b-gedaempft); margin-left: 4px;
}
.schaltgruppe{ display: flex; border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s); overflow: hidden; }
.schaltgruppe button, .schalter{
  background: var(--w2b-flaeche); border: 0; cursor: pointer; padding: 5px 11px;
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-xs);
  color: var(--w2b-gedaempft);
}
.schaltgruppe button + button{ border-left: 1px solid var(--w2b-linie); }
.schalter{ border: 1px solid var(--w2b-linie); border-radius: var(--w2b-radius-s); }
.schaltgruppe button[aria-pressed="true"], .schalter[aria-pressed="true"]{
  background: var(--w2b-primaer); color: var(--w2b-primaer-auf);
}
.band{ border-radius: 0; }
.planfuss{
  display: flex; justify-content: space-between; gap: var(--w2b-raum-3); flex-wrap: wrap;
  padding: var(--w2b-raum-2) var(--w2b-raum-3); border-top: 1px solid var(--w2b-linie);
  font-family: var(--w2b-daten); font-size: 10.5px; color: var(--w2b-gedaempft);
}

.protokoll{ display: flex; flex-direction: column; gap: var(--w2b-raum-4); }
.werteliste{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.werteliste dt, .werteliste dd{
  padding: 8px var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie-zart); margin: 0;
  display: flex; align-items: center;
}
.werteliste dt{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.werteliste dd{ justify-content: flex-end; gap: 6px; font-family: var(--w2b-daten); font-size: var(--w2b-schrift-s); font-variant-numeric: tabular-nums; }
.werteliste dt:last-of-type, .werteliste dd:last-of-type{ border-bottom: 0; }
.zart{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-xs); }
.tafel__fussnote{ padding: var(--w2b-raum-3) var(--w2b-raum-4); border-top: 1px solid var(--w2b-linie-zart); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }

.preisband{ padding: var(--w2b-raum-4); }
.preisband__skala{ position: relative; height: 34px; margin-bottom: var(--w2b-raum-2); }
.preisband__achse{ position: absolute; left: 0; right: 0; top: 17px; height: 1px; background: var(--w2b-linie); }
.preisband__spanne{ position: absolute; top: 15px; height: 5px; border-radius: var(--w2b-radius-voll); background: var(--w2b-primaer-schleier); }
.preisband__brw{ position: absolute; top: 7px; width: 2px; height: 21px; background: var(--w2b-primaer); border-radius: 1px; }
.preisband__marke{ position: absolute; top: 11px; width: 12px; height: 12px; margin-left: -6px; border-radius: 3px; background: var(--w2b-sekundaer); border: 1.5px solid var(--w2b-sekundaer-text); transform: rotate(45deg); }
.preisband__achsentext{ display: flex; justify-content: space-between; font-family: var(--w2b-daten); font-size: 10.5px; color: var(--w2b-gedaempft); }
.preisband__aussage{ margin-top: var(--w2b-raum-3); font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.preisband__aussage b{ color: var(--w2b-tinte); }

.werkzeuge{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--w2b-raum-4); align-items: start; }
.tiefe{ width: 72px; padding: 4px 7px; text-align: right; }
.regler{ display: grid; grid-template-columns: 1fr auto; gap: 5px var(--w2b-raum-3); align-items: center; padding: var(--w2b-raum-3) var(--w2b-raum-4); border-top: 1px solid var(--w2b-linie-zart); }
.regler label{ font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-xs); letter-spacing: .09em; text-transform: uppercase; color: var(--w2b-gedaempft); }
.regler input[type="range"]{ grid-column: 1 / -1; }
.regler__hinweis{ grid-column: 1 / -1; font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.feld--gerahmt{ padding: var(--w2b-raum-3) var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie); }
.eigenmass{ display: grid; grid-template-columns: 1fr 1fr; gap: var(--w2b-raum-3); padding: var(--w2b-raum-3) var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie); background: var(--w2b-sekundaer-schleier); }
.eigenmass__hinweis{ grid-column: 1 / -1; font-size: var(--w2b-schrift-xs); color: var(--w2b-sekundaer-text); }
.ausrichten{ display: flex; flex-direction: column; gap: var(--w2b-raum-2); padding: var(--w2b-raum-3) var(--w2b-raum-4); border-top: 1px solid var(--w2b-linie-zart); }
</style>
