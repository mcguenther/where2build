<template>
  <div v-if="plot" class="stapel grundstueck-seite">
    <nav class="krume nicht-drucken" aria-label="Pfad">
      <button type="button" @click="back">Grundstücke</button>
      <span aria-hidden="true">›</span>
      <span>{{ plot.name }}</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Gemarkung {{ plot.gemarkung }} · {{ plot.flurstuecke.length }} Flurstück{{ plot.flurstuecke.length > 1 ? 'e' : '' }}</p>
        <h1>{{ plot.name }}</h1>
        <p class="seitenkopf__unter">
          {{ plot.municipality }} · Flurstück {{ plot.flurstuecke.join(" und ") }} ·
          {{ area(plot.officialArea) }} · {{ euro(plot.askingPrice) }}
        </p>
        <p v-if="plot.note" class="seitenkopf__notiz">{{ plot.note }}</p>
      </div>
      <div class="dehnen"></div>
      <div class="reihe nicht-drucken">
        <button type="button" class="knopf knopf--still" :disabled="!hasPrevious" @click="step(-1)">‹ Voriges</button>
        <button type="button" class="knopf knopf--still" :disabled="!hasNext" @click="step(1)">Nächstes ›</button>
        <button type="button" class="knopf knopf--zweit" @click="print">Drucken</button>
      </div>
    </div>

    <div class="plangitter druckblatt">
      <div class="planrahmen tafel druckblatt__plan">
        <div class="planleiste nicht-drucken">
          <span class="planleiste__schild">Grund</span>
          <div class="schaltgruppe" role="group" aria-label="Kartenhintergrund">
            <button v-for="b in backdrops" :key="b.id" type="button"
                    :disabled="b.id !== 'none' && !hasAnchor"
                    :title="b.id !== 'none' && !hasAnchor ? 'Ohne Koordinate lässt sich keine Karte darunterlegen.' : null"
                    :aria-pressed="String(state.plan.backdrop === b.id)"
                    @click="state.plan.backdrop = b.id">{{ b.name }}</button>
          </div>
          <span class="planleiste__schild">Ausrichtung</span>
          <div class="schaltgruppe" role="group" aria-label="Kartenausrichtung">
            <button type="button" :aria-pressed="String(state.plan.northUp)"
                    @click="state.plan.northUp = true">Genordet</button>
            <button type="button" :aria-pressed="String(!state.plan.northUp)"
                    @click="state.plan.northUp = false">Straßenparallel</button>
          </div>
          <div class="dehnen"></div>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.showDimensions)"
                  @click="state.plan.showDimensions = !state.plan.showDimensions">Maße</button>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.showSetbacks)"
                  @click="state.plan.showSetbacks = !state.plan.showSetbacks">Abstandsflächen</button>
          <button type="button" class="schalter" :aria-pressed="String(state.plan.measuring)"
                  @click="toggleMeasuring">Messen</button>
        </div>

        <p class="band" :class="violation ? 'band--fehler' : 'band--gut'" role="status">
          <span v-if="violation">
            <b>{{ outliers }} Gebäudeecke{{ outliers > 1 ? 'n liegen' : ' liegt' }} außerhalb des Bebauungsfensters.</b>
            Geringster Grenzabstand {{ metres(narrowestSetback) }}.
          </span>
          <span v-else>
            <b>Baukörper liegt im Bebauungsfenster.</b>
            Geringster Grenzabstand {{ metres(narrowestSetback) }}.
          </span>
        </p>

        <p v-if="state.plan.measuring" class="band messband">
          <span v-if="!measurement.points.length">Auf den Plan klicken, um zu messen. Jeder weitere Klick verlängert den Streckenzug.</span>
          <span v-else><b>{{ metres(measurement.length) }}</b> über {{ measurement.points.length - 1 }}
            {{ measurement.points.length === 2 ? "Abschnitt" : "Abschnitte" }}.</span>
          <button v-if="measurement.points.length" type="button" class="knopf knopf--still knopf--klein"
                  style="margin-left:auto" @click="clearMeasurement">Zurücksetzen</button>
        </p>

        <SitePlan ref="plan" :plot="plot" :building="building" interactive
                  :measuring="state.plan.measuring" @measured="m => (measurement = m)"
                  :backdrop="state.plan.backdrop" :north-up="state.plan.northUp"
                  :show-dimensions="state.plan.showDimensions" :show-setbacks="state.plan.showSetbacks"
                  @move="moveHouse" />

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
            <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(metrics.computedArea, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ plot.polygon.length }}</dd>
            <dt>Straßenfront</dt><dd>{{ metres(metrics.streetFrontage) }}</dd>
          </dl>
          <p class="tafel__fussnote">
            Für den Preisvergleich zählt die amtliche Fläche. Die aus dem Polygon
            gerechnete weicht regelmäßig um ein paar Quadratmeter ab.
          </p>
        </section>

        <section class="tafel">
          <div class="tafel__kopf"><h3>Form</h3></div>
          <dl class="werteliste">
            <dt>Rechteckigkeit</dt><dd>{{ num(metrics.rectangularity, 3) }}</dd>
            <dt>Einstufung</dt><dd><span class="chip chip--gut">{{ metrics.shapeClass }}</span></dd>
            <dt>Seitenverhältnis</dt><dd>1 : {{ num(aspectRatio) }}</dd>
            <dt>Umschl. Rechteck</dt><dd>{{ num(metrics.mrr.width, 1) }} × {{ num(metrics.mrr.height, 1) }} m</dd>
          </dl>
        </section>

        <section class="tafel">
          <div class="tafel__kopf"><h3>Preis</h3><div class="dehnen"></div><span class="chip">BORIS</span></div>
          <dl class="werteliste">
            <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
            <dt>Angebot je m²</dt><dd>{{ euroPerSqm(metrics.pricePerSqm) }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }} <span class="zart">Zone {{ plot.brwZone }}</span></dd>
            <dt>Stichtag</dt><dd>{{ date(plot.brwReferenceDate) }}</dd>
          </dl>
          <div v-if="Number.isFinite(plot.bodenrichtwert)" class="preisband">
            <div class="preisband__skala">
              <div class="preisband__achse"></div>
              <div class="preisband__spanne" :style="{ left: pricePosition(plot.bodenrichtwert * .85) + '%', width: (pricePosition(plot.bodenrichtwert * 1.15) - pricePosition(plot.bodenrichtwert * .85)) + '%' }"></div>
              <div class="preisband__brw" :style="{ left: pricePosition(plot.bodenrichtwert) + '%' }"></div>
              <div v-if="metrics.pricePerSqm !== null" class="preisband__marke"
                   :style="{ left: pricePosition(metrics.pricePerSqm) + '%' }"
                   :title="`Angebot ${euroPerSqm(metrics.pricePerSqm)}/m²`"></div>
            </div>
            <div class="preisband__achsentext">
              <span>{{ Math.round(priceRange.lo) }} €</span>
              <span>{{ Math.round(plot.bodenrichtwert) }} €</span>
              <span>{{ Math.round(priceRange.hi) }} €</span>
            </div>
            <p v-if="metrics.deviation !== null" class="preisband__aussage">
              Das Angebot liegt <b>{{ percent(metrics.deviation) }}
              {{ metrics.deviation > 0 ? "über" : "unter" }} dem Bodenrichtwert</b> der Zone.
            </p>
            <p v-else class="preisband__aussage">
              Ohne Kaufpreis lässt sich das Angebot nicht mit dem Bodenrichtwert vergleichen.
              Der Preis steht im Inserat und kann oben eingetragen werden.
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
            <tr v-for="(boundary, i) in boundaries" :key="i">
              <td>{{ boundary.name }}</td>
              <td class="zahl">{{ metres(boundary.length) }}</td>
              <td class="zahl">
                <input type="number" min="0" max="20" step="0.1" class="tiefe"
                       :value="plot.setbacks[i]" :aria-label="`Abstandstiefe ${boundary.name}`"
                       @input="setSetback(i, $event.target.value)">
              </td>
            </tr>
          </tbody>
        </table>
        <div class="regler nicht-drucken">
          <label for="wandhoehe">Wandhöhe</label>
          <output class="daten">{{ metres(plot.wallHeight) }}</output>
          <input id="wandhoehe" type="range" min="2.5" max="12" step="0.1"
                 :value="plot.wallHeight" @input="setWallHeight($event.target.value)">
          <p class="regler__hinweis">
            0,4 · H = <b>{{ metres(plot.wallHeight * 0.4) }}</b>
            <template v-if="plot.wallHeight * 0.4 < 3"> — unter dem Mindestmaß von 3 m, deshalb greift der Mindestwert.</template>
            <template v-else> — maßgeblich, weil größer als das Mindestmaß von 3 m.</template>
          </p>
        </div>
      </section>

      <section class="tafel">
        <div class="tafel__kopf"><h3>Baukörper</h3></div>
        <div class="feld feld--gerahmt nicht-drucken">
          <label for="haustyp">Haustyp</label>
          <select id="haustyp" :value="plot.houseTypeId" @change="setHouseType($event.target.value)">
            <option v-for="h in state.data.houseTypes" :key="h.id" :value="h.id">
              {{ h.manufacturer }} {{ h.name }} — {{ num(h.builtArea) }} m² bebaut
            </option>
            <option :value="CUSTOM_SIZE">Eigene Maße …</option>
          </select>
        </div>

        <div v-if="isCustomSize" class="eigenmass nicht-drucken">
          <div class="feld">
            <label for="em-laenge">Länge</label>
            <input id="em-laenge" type="number" min="4" max="30" step="0.1"
                   :value="customSize.length" @input="setCustomSize('length', $event.target.value)">
          </div>
          <div class="feld">
            <label for="em-breite">Breite</label>
            <input id="em-breite" type="number" min="4" max="30" step="0.1"
                   :value="customSize.width" @input="setCustomSize('width', $event.target.value)">
          </div>
          <p class="eigenmass__hinweis">
            Ergibt {{ area(customSize.length * customSize.width, 1) }} bebaute Fläche.
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button type="button" class="knopf knopf--zweit knopf--klein" @click="saveAsHouseType">
            Als Haustyp in den Katalog
          </button>
        </div>

        <dl class="werteliste">
          <!-- On paper the <select> is hidden, so without this the printed
               sheet never says which house type it is about. -->
          <template v-if="houseType">
            <dt>Haustyp</dt><dd>{{ houseType.manufacturer }} {{ houseType.name }}</dd>
          </template>
          <dt>Bebaute Fläche</dt><dd>{{ area(builtArea, 2) }}</dd>
          <dt v-if="houseType">Wohnfläche ges.</dt><dd v-if="houseType">{{ area(houseType.livingArea, 2) }}</dd>
          <dt>Außenmaß</dt>
          <dd>{{ num(building.width, 1) }} × {{ num(building.depth, 1) }} m
            <span v-if="building.estimated" class="zart" title="aus der bebauten Fläche geschätzt">≈</span></dd>
          <dt>Drehung</dt><dd>{{ degrees(plot.house.rotation) }}</dd>
          <dt>GRZ</dt><dd>{{ num(builtArea / plot.officialArea, 2) }}</dd>
        </dl>

        <div class="ausrichten nicht-drucken">
          <button type="button" class="knopf knopf--zweit" @click="alignToStreet">
            An der Straße ausrichten
          </button>
          <p class="regler__hinweis">
            Dreht den Baukörper parallel zur Straßenfront ({{ degrees(streetAngle) }})
            und schiebt ihn zurück ins Fenster, falls er dabei herausrutscht.
          </p>
        </div>

        <div v-if="building.estimated" class="regler nicht-drucken">
          <label for="verhaeltnis">Seitenverhältnis</label>
          <output class="daten">{{ num(plot.ratio) }}</output>
          <input id="verhaeltnis" type="range" min="1" max="2.2" step="0.01"
                 :value="plot.ratio" @input="setRatio($event.target.value)">
          <p class="regler__hinweis">Aus der bebauten Fläche geschätzt — das Datenblatt liefert keine Außenmaße.</p>
        </div>

        <div class="regler nicht-drucken">
          <label for="drehung">Drehung</label>
          <output class="daten">{{ degrees(plot.house.rotation) }}</output>
          <input id="drehung" type="range" min="-90" max="90" step="1"
                 :value="plot.house.rotation" @input="setRotation($event.target.value)">
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
            Für jedes hinterlegte Ziel Auto, Rad und ÖPNV, gerechnet vom Grundstück aus.
            Ziele gelten für alle Grundstücke.
          </p>
        </div>
        <div class="dehnen"></div>
        <button type="button" class="knopf nicht-drucken"
                :disabled="!routesPossible || routesBusy" @click="computeRoutes">
          {{ routesBusy ? "Rechnet…" : "Wege berechnen" }}
        </button>
        <button type="button" class="knopf knopf--still nicht-drucken" @click="state.view = 'destinations'">
          Ziele bearbeiten
        </button>
      </div>

      <p v-if="routesError" class="band band--fehler">{{ routesError }}</p>
      <p v-else-if="!plot.anchor" class="band">
        Dieses Grundstück hat keine Koordinate — ohne sie gibt es keinen Startpunkt für eine Route.
      </p>
      <p v-else-if="!locatedDestinations.length && state.data.destinations.length" class="band">
        Keines der Ziele ist verortet. Unter „Ziele bearbeiten“ die Adressen nachschlagen lassen.
      </p>

      <RouteCards :plot="plot" />
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import RouteCards from "../components/RouteCards.vue";
import { state, plotById, placement, houseTypeById, houseFootprint, save, addHouseType, newId, setRoutes, CUSTOM_SIZE }
  from "../lib/store.js";
import { reachability } from "../lib/api.js";
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
      state, CUSTOM_SIZE,
      measurement: { points: [], length: 0 },
      routesBusy: false,
      routesError: null,
      backdrops: [
        { id: "none", name: "Ohne" },
        { id: "map", name: "Karte" },
        { id: "aerial", name: "Luftbild" },
        { id: "cadastre", name: "Kataster" }
      ]
    };
  },
  computed: {
    /** Only destinations that carry a coordinate can be routed to. */
    locatedDestinations() {
      return state.data.destinations.filter(d => Number.isFinite(d.lat) && Number.isFinite(d.lon));
    },
    routesPossible() { return Boolean(this.plot.anchor) && this.locatedDestinations.length > 0; },
    plot() { return plotById(state.openPlotId) || state.data.plots[0] || null; },
    hasAnchor() { return Boolean(this.plot?.anchor); },
    building() { return placement(this.plot); },
    houseType() { return houseTypeById(this.plot.houseTypeId); },
    isCustomSize() { return this.plot.houseTypeId === CUSTOM_SIZE; },
    customSize() { return this.plot.customSize || { length: 11.4, width: 8.5 }; },
    builtArea() {
      const f = houseFootprint(this.plot);
      return f.width * f.depth;
    },
    metrics() { return plotMetrics(this.plot); },
    envelope() { return buildableArea(this.plot.polygon, this.plot.setbacks); },
    outliers() { return cornersOutside(this.building, this.envelope); },
    violation() { return this.outliers > 0; },
    narrowestSetback() { return smallestSetback(this.building, this.plot.polygon); },
    streetAngle() { return alignmentToEdge(this.plot.polygon, this.plot.streetEdge ?? 0); },
    aspectRatio() {
      const m = this.metrics.mrr;
      return Math.max(m.width, m.height) / Math.min(m.width, m.height);
    },
    priceRange() { return { lo: this.plot.bodenrichtwert * 0.7, hi: this.plot.bodenrichtwert * 1.45 }; },
    boundaries() {
      return polygonEdges(this.plot.polygon).map((edge, i) => ({
        name: `${edgeCompass(this.plot.polygon, i, this.plot.northOffset)} — ${i === (this.plot.streetEdge ?? 0) ? "zur Straße" : "Nachbar"}`,
        length: edge.length
      }));
    },
    index() { return state.data.plots.findIndex(p => p.id === this.plot.id); },
    hasPrevious() { return this.index > 0; },
    hasNext() { return this.index < state.data.plots.length - 1; }
  },
  methods: {
    /** Ask the routing service for every located destination at once and keep
     *  what it answers. Nothing is filled in when a mode has no connection —
     *  the card then says so instead of showing a plausible number. */
    async computeRoutes() {
      this.routesBusy = true;
      this.routesError = null;
      try {
        const response = await reachability(
          { lat: this.plot.anchor.lat, lon: this.plot.anchor.lon },
          this.locatedDestinations.map(d => ({ id: d.id, name: d.name, lat: d.lat, lon: d.lon })),
          ["car", "bike", "transit"]
        );
        const routes = {};
        (response.ergebnisse || []).forEach(e => {
          (routes[e.destination_id] ||= {})[e.mode] = {
            erreichbar: e.erreichbar,
            duration_s: e.duration_s,
            umstiege: e.umstiege,
            geometry: e.geometry,
            hinweis: e.hinweis
          };
        });
        if (!Object.keys(routes).length) {
          this.routesError = "Der Routendienst hat keine einzige Verbindung zurückgegeben.";
        } else {
          setRoutes(this.plot.id, routes, response.quelle);
        }
      } catch (error) {
        this.routesError = error.message;
      } finally {
        this.routesBusy = false;
      }
    },
    area, euro, euroPerSqm, metres, num, percent, degrees, date,
    back() { state.view = "plots"; window.scrollTo({ top: 0 }); },
    step(by) {
      const target = state.data.plots[this.index + by];
      if (target) { state.openPlotId = target.id; window.scrollTo({ top: 0 }); }
    },
    print() { window.print(); },
    toggleMeasuring() {
      state.plan.measuring = !state.plan.measuring;
      if (!state.plan.measuring) this.measurement = { points: [], length: 0 };
    },
    clearMeasurement() {
      this.$refs.plan?.clearMeasurement();
      this.measurement = { points: [], length: 0 };
    },
    pricePosition(value) {
      const { lo, hi } = this.priceRange;
      return Math.max(0, Math.min(100, ((value - lo) / (hi - lo)) * 100));
    },
    moveHouse({ cx, cy }) { this.plot.house.cx = cx; this.plot.house.cy = cy; save(); },
    setSetback(i, value) {
      const v = parseFloat(value);
      this.plot.setbacks[i] = Number.isFinite(v) && v >= 0 ? v : 0;
      save();
    },
    setWallHeight(value) {
      this.plot.wallHeight = parseFloat(value);
      // § 6 SächsBO: the depth follows wall height, with 3 m as the floor.
      const depth = Math.round(Math.max(3, this.plot.wallHeight * 0.4) * 10) / 10;
      this.plot.setbacks = this.plot.setbacks.map(() => depth);
      save();
    },
    setRatio(value) { this.plot.ratio = parseFloat(value); save(); },
    setRotation(value) { this.plot.house.rotation = parseFloat(value); save(); },
    setHouseType(id) {
      this.plot.houseTypeId = id;
      if (id === CUSTOM_SIZE) {
        if (!this.plot.customSize) {
          const f = this.building;
          this.plot.customSize = { length: Math.round(f.width * 10) / 10, width: Math.round(f.depth * 10) / 10 };
        }
      } else {
        const type = houseTypeById(id);
        if (type?.ratio) this.plot.ratio = type.ratio;
      }
      save();
    },
    setCustomSize(field, value) {
      const v = parseFloat(value);
      if (!Number.isFinite(v)) return;
      this.plot.customSize = { ...this.customSize, [field]: Math.min(30, Math.max(4, v)) };
      save();
    },
    saveAsHouseType() {
      const { length, width } = this.customSize;
      const type = addHouseType({
        id: newId("house"), manufacturer: "Eigene Maße", name: `${num(length, 1)} × ${num(width, 1)} m`,
        builtArea: Math.round(length * width * 100) / 100, livingArea: null,
        livingAreaGround: null, livingAreaUpper: null, length, width,
        roofShape: "offen", priceFrom: null, ratio: length / width,
        source: null, readAt: new Date().toISOString().slice(0, 10), custom: true
      });
      this.plot.houseTypeId = type.id;
      save();
    },
    alignToStreet() {
      const next = alignToEdge(this.plot.polygon, this.envelope, this.building, this.plot.streetEdge ?? 0);
      this.plot.house = { cx: next.cx, cy: next.cy, rotation: Math.round(next.rotation * 10) / 10 };
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
.messband{ display: flex; align-items: center; gap: var(--w2b-raum-3); border-bottom: 1px solid var(--w2b-linie); }
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
