<template>
  <div v-if="plot" class="stack plot-page">
    <nav class="breadcrumb no-print" aria-label="Pfad">
      <RouterLink :to="{ name: 'plots' }">Grundstücke</RouterLink>
      <span aria-hidden="true">›</span>
      <span>{{ plot.name }}</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Gemarkung {{ plot.gemarkung }} · {{ plot.flurstuecke.length }} Flurstück{{ plot.flurstuecke.length > 1 ? 'e' : '' }}</p>
        <h1>{{ plot.name }}</h1>
        <p class="page-head__sub">
          {{ plot.municipality }} · Flurstück {{ plot.flurstuecke.join(" und ") }} ·
          {{ area(plot.officialArea) }} · {{ euro(plot.askingPrice) }}
        </p>
        <p v-if="plot.note" class="page-head__note">{{ plot.note }}</p>
      </div>
      <div class="spacer"></div>
      <div class="row no-print">
        <button type="button" class="btn btn--quiet" :disabled="!hasPrevious" @click="step(-1)">‹ Voriges</button>
        <button type="button" class="btn btn--quiet" :disabled="!hasNext" @click="step(1)">Nächstes ›</button>
        <RouterLink v-if="hasAnchor" class="btn btn--secondary"
                    :to="{ name: 'location', params: { id: plot.id } }">Standort prüfen</RouterLink>
        <button type="button" class="btn btn--secondary" @click="print">Drucken</button>
      </div>
    </div>

    <div class="plan-grid print-sheet">
      <div class="plan-frame panel print-sheet__plan">
        <div class="plan-bar no-print">
          <span class="plan-bar__label">Grund</span>
          <div class="button-group" role="group" aria-label="Kartenhintergrund">
            <button v-for="b in backdrops" :key="b.id" type="button"
                    :disabled="b.id !== 'none' && !hasAnchor"
                    :title="b.id !== 'none' && !hasAnchor ? 'Ohne Koordinate lässt sich keine Karte darunterlegen.' : null"
                    :aria-pressed="String(state.plan.backdrop === b.id)"
                    @click="state.plan.backdrop = b.id">{{ b.name }}</button>
          </div>
          <span class="plan-bar__label">Ausrichtung</span>
          <div class="button-group" role="group" aria-label="Kartenausrichtung">
            <button type="button" :aria-pressed="String(state.plan.northUp)"
                    @click="state.plan.northUp = true">Genordet</button>
            <button type="button" :aria-pressed="String(!state.plan.northUp)"
                    @click="state.plan.northUp = false">Straßenparallel</button>
          </div>
          <div class="spacer"></div>
          <button type="button" class="toggle" :aria-pressed="String(state.plan.showDimensions)"
                  @click="state.plan.showDimensions = !state.plan.showDimensions">Maße</button>
          <button type="button" class="toggle" :aria-pressed="String(state.plan.showSetbacks)"
                  @click="state.plan.showSetbacks = !state.plan.showSetbacks">Abstandsflächen</button>
          <button type="button" class="toggle" :aria-pressed="String(state.plan.measuring)"
                  @click="toggleMeasuring">Messen</button>
          <button type="button" class="toggle" :disabled="!hasAnchor"
                  :title="hasAnchor ? null : 'Ohne Koordinate lassen sich keine Nachbargebäude finden.'"
                  :aria-pressed="String(showNeighbours)"
                  @click="toggleNeighbours">Nachbarn</button>
        </div>

        <p class="notice" :class="violation ? 'notice--error' : 'notice--good'" role="status">
          <span v-if="violation">
            <b>{{ outliers }} Gebäudeecke{{ outliers > 1 ? 'n liegen' : ' liegt' }} außerhalb des Bebauungsfensters.</b>
            Geringster Grenzabstand {{ metres(narrowestSetback) }}.
          </span>
          <span v-else>
            <b>Baukörper liegt im Bebauungsfenster.</b>
            Geringster Grenzabstand {{ metres(narrowestSetback) }}.
          </span>
        </p>

        <p v-if="showNeighbours" class="notice neighbour-note" role="status">
          <span v-if="neighboursBusy">Nachbargebäude werden geholt …</span>
          <span v-else-if="neighboursError">{{ neighboursError }}</span>
          <span v-else-if="neighbourHint">
            <b>Schraffiert: hier reicht die Abstandsfläche des Nachbargebäudes herüber.</b>
            § 6 SächsBO verlangt das nicht von uns — jedes Gebäude hält seine Abstandsfläche
            auf dem eigenen Grundstück. Wo beide sich überdecken würden, ist das eine Frage
            an die Bauaufsicht, keine Prüfung. Umrisse aus {{ neighbourSource }}, ohne
            Wandhöhen, gerechnet mit dem Mindestmaß von 3 m.
          </span>
          <span v-else-if="neighbourBuildings.length">
            <b>Kein Nachbargebäude steht näher als 3 m an der Grenze.</b>
            {{ neighbourBuildings.length }} Umrisse aus {{ neighbourSource }} geprüft.
          </span>
          <span v-else>In der Umgebung ist dort kein Gebäude erfasst.</span>
        </p>

        <p v-if="state.plan.measuring" class="notice measure-bar">
          <span v-if="!measurement.points.length">Auf den Plan klicken, um zu messen. Jeder weitere Klick verlängert den Streckenzug.</span>
          <span v-else><b>{{ metres(measurement.length) }}</b> über {{ measurement.points.length - 1 }}
            {{ measurement.points.length === 2 ? "Abschnitt" : "Abschnitte" }}.</span>
          <button v-if="measurement.points.length" type="button" class="btn btn--quiet btn--small"
                  style="margin-left:auto" @click="clearMeasurement">Zurücksetzen</button>
        </p>

        <SitePlan ref="plan" :plot="plot" :building="building" interactive
                  :measuring="state.plan.measuring" @measured="m => (measurement = m)"
                  :backdrop="state.plan.backdrop" :north-up="state.plan.northUp"
                  :show-dimensions="state.plan.showDimensions" :show-setbacks="state.plan.showSetbacks"
                  :confine-to-envelope="confineHouse" :neighbour-depths="neighbourDepths"
                  @move="moveHouse" />

        <div class="plan-foot">
          <span>ETRS89 / UTM33N — EPSG:25833</span>
          <span>© GeoSN, dl-de/by-2-0</span>
        </div>
      </div>

      <aside class="facts">
        <section class="panel">
          <div class="panel__head"><h3>Grundstück</h3><div class="spacer"></div><span class="chip">ALKIS</span></div>
          <dl class="value-list">
            <dt>Gemarkung</dt><dd>{{ plot.gemarkung }}</dd>
            <dt>Flurstücke</dt><dd>{{ plot.flurstuecke.join(" · ") }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(metrics.computedArea, 1) }}</dd>
            <dt>Grenzpunkte</dt><dd>{{ plot.polygon.length }}</dd>
            <dt>Straßenfront</dt><dd>{{ metres(metrics.streetFrontage) }}</dd>
          </dl>
          <p class="panel__footnote">
            Für den Preisvergleich zählt die amtliche Fläche. Die aus dem Polygon
            gerechnete weicht regelmäßig um ein paar Quadratmeter ab.
          </p>
        </section>

        <section class="panel">
          <div class="panel__head"><h3>Form</h3></div>
          <dl class="value-list">
            <dt>Rechteckigkeit</dt><dd>{{ num(metrics.rectangularity, 3) }}</dd>
            <dt>Einstufung</dt><dd><span class="chip chip--good">{{ metrics.shapeClass }}</span></dd>
            <dt>Seitenverhältnis</dt><dd>1 : {{ num(aspectRatio) }}</dd>
            <dt>Umschl. Rechteck</dt><dd>{{ num(metrics.mrr.width, 1) }} × {{ num(metrics.mrr.height, 1) }} m</dd>
          </dl>
        </section>

        <section class="panel">
          <div class="panel__head"><h3>Preis</h3><div class="spacer"></div><span class="chip">BORIS</span></div>
          <dl class="value-list">
            <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
            <dt>Angebot je m²</dt><dd>{{ euroPerSqm(metrics.pricePerSqm) }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }} <span class="faint">Zone {{ plot.brwZone }}</span></dd>
            <dt>Stichtag</dt><dd>{{ date(plot.brwReferenceDate) }}</dd>
          </dl>
          <div v-if="Number.isFinite(plot.bodenrichtwert)" class="price-band">
            <div class="price-band__scale">
              <div class="price-band__axis"></div>
              <div class="price-band__range" :style="{ left: pricePosition(plot.bodenrichtwert * .85) + '%', width: (pricePosition(plot.bodenrichtwert * 1.15) - pricePosition(plot.bodenrichtwert * .85)) + '%' }"></div>
              <div class="price-band__brw" :style="{ left: pricePosition(plot.bodenrichtwert) + '%' }"></div>
              <div v-if="metrics.pricePerSqm !== null" class="price-band__marker"
                   :style="{ left: pricePosition(metrics.pricePerSqm) + '%' }"
                   :title="`Angebot ${euroPerSqm(metrics.pricePerSqm)}/m²`"></div>
            </div>
            <div class="price-band__axis-labels">
              <span>{{ Math.round(priceRange.lo) }} €</span>
              <span>{{ Math.round(plot.bodenrichtwert) }} €</span>
              <span>{{ Math.round(priceRange.hi) }} €</span>
            </div>
            <p v-if="metrics.deviation !== null" class="price-band__statement">
              Das Angebot liegt <b>{{ percent(metrics.deviation) }}
              {{ metrics.deviation > 0 ? "über" : "unter" }} dem Bodenrichtwert</b> der Zone.
            </p>
            <p v-else class="price-band__statement">
              Ohne Kaufpreis lässt sich das Angebot nicht mit dem Bodenrichtwert vergleichen.
              Der Preis steht im Inserat und kann oben eingetragen werden.
            </p>
          </div>
        </section>
      </aside>
    </div>

    <div class="tools">
      <section class="panel">
        <div class="panel__head"><h3>Abstandsflächen</h3><div class="spacer"></div><span class="chip chip--warn">§ 6 SächsBO</span></div>
        <table class="data-table setback-table">
          <thead><tr><th>Grenze</th><th class="num">Länge</th><th class="num">Tiefe</th></tr></thead>
          <tbody>
            <tr v-for="(boundary, i) in boundaries" :key="i">
              <td>{{ boundary.name }}</td>
              <td class="num">{{ metres(boundary.length) }}</td>
              <td class="num">
                <input type="number" min="0" max="20" step="0.1" class="depth"
                       :value="plot.setbacks[i]" :aria-label="`Abstandstiefe ${boundary.name}`"
                       @input="setSetback(i, $event.target.value)">
              </td>
            </tr>
          </tbody>
        </table>
        <div class="slider no-print">
          <label for="wall-height">Wandhöhe</label>
          <output class="mono">{{ metres(plot.wallHeight) }}</output>
          <input id="wall-height" type="range" min="2.5" max="12" step="0.1"
                 :value="plot.wallHeight" @input="setWallHeight($event.target.value)">
          <p class="slider__hint">
            0,4 · H = <b>{{ metres(plot.wallHeight * 0.4) }}</b>
            <template v-if="plot.wallHeight * 0.4 < 3"> — unter dem Mindestmaß von 3 m, deshalb greift der Mindestwert.</template>
            <template v-else> — maßgeblich, weil größer als das Mindestmaß von 3 m.</template>
          </p>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Baukörper</h3></div>
        <div class="field field--framed no-print">
          <label for="house-type">Haustyp</label>
          <select id="house-type" :value="plot.houseTypeId" @change="setHouseType($event.target.value)">
            <option v-for="h in state.data.houseTypes" :key="h.id" :value="h.id">
              {{ h.manufacturer }} {{ h.name }} — {{ num(h.builtArea) }} m² bebaut
            </option>
            <option :value="CUSTOM_SIZE">Eigene Maße …</option>
          </select>
        </div>

        <div v-if="isCustomSize" class="custom-size no-print">
          <div class="field">
            <label for="custom-length">Länge</label>
            <input id="custom-length" type="number" :min="MIN_EDGE" :max="MAX_EDGE" step="0.1"
                   :value="customField('length')" @input="typeCustomSize('length', $event.target.value)"
                   @change="commitCustomSize('length')" @blur="commitCustomSize('length')"
                   @keyup.enter="commitCustomSize('length')">
          </div>
          <div class="field">
            <label for="custom-width">Breite</label>
            <input id="custom-width" type="number" :min="MIN_EDGE" :max="MAX_EDGE" step="0.1"
                   :value="customField('width')" @input="typeCustomSize('width', $event.target.value)"
                   @change="commitCustomSize('width')" @blur="commitCustomSize('width')"
                   @keyup.enter="commitCustomSize('width')">
          </div>
          <p class="custom-size__hint" :class="{ 'custom-size__hint--warn': customSizeOutOfRange }">
            <template v-if="customSizeOutOfRange">
              Beim Verlassen des Feldes wird auf 4 m bis 30 m gesetzt; gezeichnet ist weiter
              {{ num(customSize.length, 1) }} × {{ num(customSize.width, 1) }} m.
            </template>
            <template v-else>Ergibt {{ area(customSize.length * customSize.width, 1) }} bebaute Fläche.</template>
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button v-if="!naming" type="button" class="btn btn--secondary btn--small" @click="startNaming">
            Als Haustyp in den Katalog
          </button>

          <div v-else class="naming no-print">
            <div class="field">
              <label for="house-type-name">Name</label>
              <input id="house-type-name" ref="nameField" type="text" maxlength="60"
                     v-model="typeName" @keyup.enter="confirmHouseType" @keyup.esc="cancelNaming">
            </div>
            <div class="naming__buttons">
              <button type="button" class="btn btn--small" @click="confirmHouseType">Speichern</button>
              <button type="button" class="btn btn--quiet btn--small" @click="cancelNaming">Abbrechen</button>
            </div>
            <p class="naming__hint">
              Kommt unter „Eigene Maße“ in den Katalog und ist danach für dieses Grundstück
              ausgewählt. Ohne Namen steht dort das Maß.
            </p>
          </div>
        </div>

        <dl class="value-list">
          <!-- On paper the <select> is hidden, so without this the printed
               sheet never says which house type it is about. -->
          <template v-if="houseType">
            <dt>Haustyp</dt><dd>{{ houseType.manufacturer }} {{ houseType.name }}</dd>
          </template>
          <dt>Bebaute Fläche</dt><dd>{{ area(builtArea, 2) }}</dd>
          <dt v-if="houseType">Wohnfläche ges.</dt><dd v-if="houseType">{{ area(houseType.livingArea, 2) }}</dd>
          <dt>Außenmaß</dt>
          <dd>{{ num(building.width, 1) }} × {{ num(building.depth, 1) }} m
            <span v-if="building.estimated" class="faint" title="aus der bebauten Fläche geschätzt">≈</span></dd>
          <dt>Drehung</dt><dd>{{ degrees(plot.house.rotation) }}</dd>
          <dt>GRZ</dt><dd>{{ num(builtArea / plot.officialArea, 2) }}</dd>
        </dl>

        <div class="align no-print">
          <button type="button" class="btn btn--secondary" @click="alignToStreet">
            An der Straße ausrichten
          </button>
          <p class="slider__hint">
            Dreht den Baukörper parallel zur Straßenfront ({{ degrees(streetAngle) }})
            und schiebt ihn zurück ins Fenster, falls er dabei herausrutscht.
          </p>
        </div>

        <div v-if="building.estimated" class="slider no-print">
          <label for="ratio">Seitenverhältnis</label>
          <output class="mono">{{ num(plot.ratio) }}</output>
          <input id="ratio" type="range" min="1" max="2.2" step="0.01"
                 :value="plot.ratio" @input="setRatio($event.target.value)">
          <p class="slider__hint">Aus der bebauten Fläche geschätzt — das Datenblatt liefert keine Außenmaße.</p>
        </div>

        <div class="slider no-print">
          <label for="rotation">Drehung</label>
          <output class="mono">{{ degrees(plot.house.rotation) }}</output>
          <input id="rotation" type="range" min="-90" max="90" step="1"
                 :value="plot.house.rotation" @input="setRotation($event.target.value)">
          <p class="slider__hint">Haus mit der Maus ziehen, mit den Pfeiltasten fein verschieben.</p>
        </div>

        <div class="confine no-print">
          <button type="button" class="toggle" :aria-pressed="String(confineHouse)"
                  @click="toggleConfine">Im Bebauungsfenster halten</button>
          <p class="slider__hint">
            Der Baukörper lässt sich dann nicht über die Abstandsflächen hinausschieben:
            Ziehen und Pfeiltasten enden an der Grenze des Fensters, an der er entlanggleitet.
            Passt er überhaupt nirgends hinein, greift die Begrenzung nicht — dann ist er frei
            verschiebbar, und die roten Ecken zeigen, wo er hinausragt.
          </p>
        </div>
      </section>

      <div class="callout callout--caution">
        <h4>Keine bauordnungsrechtliche Prüfung</h4>
        <p>Die Abstandstiefe bemisst sich nach § 6 SächsBO grundsätzlich nach der Wandhöhe;
          3 m sind der Mindestwert, nicht die Regel. Grenzgaragen sind privilegiert, ein
          Bebauungsplan kann abweichende Baugrenzen festsetzen.</p>
        <p>Nach § 15 Abs. 2 ImmoWertV kann ein einzelnes Grundstück innerhalb der
          Richtwertzone eine abweichende Nutzungsart haben — dann gilt der Zonenwert nicht.</p>
      </div>
    </div>

    <section class="stack">
      <div class="page-head">
        <div>
          <p class="eyebrow">Erreichbarkeiten</p>
          <h2>Wege von hier</h2>
          <p class="page-head__sub">
            Für jedes hinterlegte Ziel Auto, Rad und ÖPNV, gerechnet vom Grundstück aus.
            Beim ÖPNV wird der Weg zur ersten Haltestelle mitgewählt — zu Fuß, mit dem
            Rad oder mit dem Auto bis Park-and-Ride. Ziele gelten für alle Grundstücke.
          </p>
        </div>
        <div class="spacer"></div>
        <button type="button" class="btn no-print"
                :disabled="!routesPossible || routesBusy" @click="computeRoutes">
          {{ routesBusy ? "Rechnet…" : "Neu berechnen" }}
        </button>
        <button type="button" class="btn btn--quiet no-print" @click="$router.push({ name: 'destinations' })">
          Ziele bearbeiten
        </button>
      </div>

      <p v-if="routesError" class="notice notice--error">{{ routesError }}</p>
      <p v-else-if="!plot.anchor" class="notice">
        Dieses Grundstück hat keine Koordinate — ohne sie gibt es keinen Startpunkt für eine Route.
      </p>
      <p v-else-if="!locatedDestinations.length && state.data.destinations.length" class="notice">
        Keines der Ziele ist verortet. Unter „Ziele bearbeiten“ die Adressen nachschlagen lassen.
      </p>

      <!-- Routing several destinations takes seconds, and a page that shows
           nothing in that time reads as one that found nothing. The cards draw
           themselves as placeholders while they wait. -->
      <RouteCards :plot="plot" :busy="routesBusy && !hasRoutes" />

      <NearbyPanel :plot="plot" auto />

      <p v-if="hasAnchor" class="row no-print">
        <RouterLink class="btn btn--quiet" :to="{ name: 'surroundings', params: { id: plot.id } }">
          Auf der Umgebungskarte ansehen
        </RouterLink>
        <RouterLink class="btn btn--quiet" :to="{ name: 'location', params: { id: plot.id } }">
          Lärm, Hochwasser, Baugrund und Luft prüfen
        </RouterLink>
      </p>
    </section>
  </div>

  <div v-else class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Grundstück</p>
        <h1>Dieses Grundstück liegt nicht in diesem Browser</h1>
        <p class="page-head__sub">
          Grundstücke werden nur hier gespeichert, nicht auf einem Server: ein weitergegebener
          Link öffnet sie deshalb bei niemandem sonst, und nach „Alles löschen“ sind sie fort.
          Unter <span class="mono">{{ id }}</span> ist hier keines hinterlegt.
        </p>
      </div>
    </div>
    <div class="missing">
      <p>Ein gesicherter Stand lässt sich unter „Daten“ wieder einlesen.</p>
      <div class="row">
        <RouterLink class="btn" :to="{ name: 'plots' }">Zur Übersicht</RouterLink>
        <RouterLink class="btn btn--quiet" :to="{ name: 'data' }">Zu den Daten</RouterLink>
      </div>
    </div>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import RouteCards from "../components/RouteCards.vue";
import NearbyPanel from "../components/NearbyPanel.vue";
import {
  state, plotById, placement, houseTypeById, houseFootprint, save, addHouseType,
  newId, setRoutes, CUSTOM_SIZE, DEFAULT_FOOTPRINT
} from "../lib/store.js";
import { reachability, neighbourBuildings as fetchNeighbourBuildings } from "../lib/api.js";
import { zubringerOf } from "../lib/routes.js";
import { toLocal } from "../lib/projection.js";
import { plotMetrics } from "../lib/metrics.js";
import {
  polygonEdges, edgeCompass, buildableArea, cornersOutside, smallestSetback,
  alignToEdge, alignmentToEdge, findPlacement, neighbourSetbackDepths, hasNeighbourHint
} from "../lib/geometry.js";
import { area, euro, euroPerSqm, metres, num, percent, degrees, date } from "../lib/format.js";

/** Edge lengths a house can plausibly have, in metres. Anything outside is a typo. */
const MIN_EDGE = 4;
const MAX_EDGE = 30;

export default {
  name: "PlotView",
  components: { SitePlan, RouteCards, NearbyPanel },
  props: {
    /** The plot's id, straight out of the URL. */
    id: { type: String, required: true }
  },
  data() {
    return {
      state, CUSTOM_SIZE, MIN_EDGE, MAX_EDGE,
      /** What stands in the two edge-length fields while they are being typed
       *  in. `null` means nobody is editing, so the stored size is shown. */
      sizeDraft: { length: null, width: null },
      measurement: { points: [], length: 0 },
      naming: false,
      typeName: "",
      /** Outlines are not stored with the plot: they are somebody else's data,
       *  they are large, and the backend keeps them for a month anyway. Only
       *  the preference lives in the document. */
      neighbourBuildings: [],
      /** Which register the outlines came from — the answer says so, and the
       *  sentence beside the drawing must not claim a different one. */
      neighbourSource: "dem Liegenschaftskataster",
      neighboursBusy: false,
      neighboursError: null,
      routesBusy: false,
      routesError: null,
      /** Which plot this browser session has already routed. Asking again on
       *  every visit would put the routing service through the whole set for a
       *  page the user only opened to read the area. */
      routedFor: null,
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
    routesPossible() { return Boolean(this.plot?.anchor) && this.locatedDestinations.length > 0; },
    /** Whether this plot already carries routes, from this session or an
     *  earlier one — the document keeps them. */
    hasRoutes() { return Object.keys(this.plot?.routes ?? {}).length > 0; },
    plot() { return plotById(this.id); },
    hasAnchor() { return Boolean(this.plot?.anchor); },
    building() { return placement(this.plot); },
    houseType() { return houseTypeById(this.plot.houseTypeId); },
    isCustomSize() { return this.plot.houseTypeId === CUSTOM_SIZE; },
    /* Optional chaining, because a watcher now hangs off `dimensionLabel`: a
     * watched computed is evaluated whether or not the template reached it, and
     * the id in the URL may name no plot in this browser at all. */
    customSize() { return this.plot?.customSize || DEFAULT_FOOTPRINT; },
    /** True while a field holds something that is not a usable edge length —
     *  an empty field included. The stored size is untouched in that state. */
    customSizeOutOfRange() {
      return ["length", "width"].some(field => {
        const draft = this.sizeDraft[field];
        if (draft === null) return false;
        const entered = parseFloat(draft);
        return !Number.isFinite(entered) || entered < MIN_EDGE || entered > MAX_EDGE;
      });
    },
    builtArea() {
      const f = houseFootprint(this.plot);
      return f.width * f.depth;
    },
    /** What a self-measured type is called when nobody names it. */
    dimensionLabel() { return `${num(this.customSize.length, 1)} × ${num(this.customSize.width, 1)} m`; },
    metrics() { return plotMetrics(this.plot); },
    envelope() { return buildableArea(this.plot.polygon, this.plot.setbacks); },
    /* Stored with the plot, and on unless it was switched off: documents
       written before the setting existed carry no field, and those plots have
       always been dragged with the house kept inside as of this version. */
    confineHouse() { return this.plot?.confineHouse !== false; },
    showNeighbours() { return Boolean(this.plot?.showNeighbours) && this.hasAnchor; },
    /** The outlines in this plot's own metre frame. */
    neighbourOutlines() {
      if (!this.showNeighbours || !this.plot.anchor) return [];
      return this.neighbourBuildings.map(b => toLocal(b.umriss, this.plot.anchor));
    },
    neighbourDepths() {
      if (!this.neighbourOutlines.length) return null;
      return neighbourSetbackDepths(this.plot.polygon, this.plot.setbacks, this.neighbourOutlines);
    },
    neighbourHint() {
      return Boolean(this.neighbourDepths)
        && hasNeighbourHint(this.plot.setbacks, this.neighbourDepths);
    },
    /** What the house *is*, apart from where it stands. A change to any of it
     *  can leave the house outside a window it was inside a moment ago. */
    houseShape() {
      // A watcher reads this on every update, including the one that renders
      // the "no such plot" notice, where there is no house to describe.
      if (!this.plot) return "";
      return [this.building.width, this.building.depth, this.building.rotation,
              ...this.plot.setbacks].join("|");
    },
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
  /* A plot that was left with the neighbour hint on comes back with it on, so
     the outlines have to be fetched again — they are not in the document. */
  created() {
    if (this.showNeighbours) this.loadNeighbours();
    this.routeAutomatically();
  },
  watch: {
    "plot.id"() { this.routeAutomatically(); },
    /** A default nobody has touched follows the fields above it. */
    dimensionLabel(next, previous) {
      if (this.naming && this.typeName === previous) this.typeName = next;
    },
    /* Another plot in the same view: its outlines are somewhere else. */
    "plot.id"() {
      this.neighbourBuildings = [];
      this.neighboursError = null;
      if (this.showNeighbours) this.loadNeighbours();
    },
    /* Another house type, other dimensions, another angle, deeper setbacks: any
       of them can push a house that was inside out of the window, and with the
       constraint on, dragging can no longer be what puts it back. So it is put
       back once, here. Only the shape is watched — the position is not, or
       every drag would fight the correction. */
    houseShape() { this.reseatHouse(); }
  },
  methods: {
    /** The ways are computed on arrival, not on a button press.
     *
     * Waiting for a click made the page look like it had nothing to say about
     * getting anywhere. Once per plot per session: the routes live in the
     * document, so a plot that already carries them is not asked again, and
     * neither is one whose routing just failed — that would hammer a service
     * that is already down. */
    routeAutomatically() {
      // The view also renders for an id that names no plot here — that page is
      // the whole reason `plot` may be null, and a hook that reads through it
      // would empty exactly the page meant to explain the id.
      if (!this.plot || !this.routesPossible || this.routesBusy) return;
      if (this.hasRoutes || this.routedFor === this.plot.id) return;
      this.routedFor = this.plot.id;
      this.computeRoutes();
    },

    /** Ask the routing service for every located destination at once and keep
     *  what it answers. Nothing is filled in when a mode has no connection —
     *  the card then says so instead of showing a plausible number. */
    async computeRoutes() {
      this.routesBusy = true;
      this.routesError = null;
      try {
        const response = await reachability(
          { lat: this.plot.anchor.lat, lon: this.plot.anchor.lon },
          // `zubringer` travels with the destination: the way to the first stop
          // is decided per destination, and the backend needs several answers
          // to decide it when nothing is pinned.
          this.locatedDestinations.map(d => ({
            id: d.id, name: d.name, lat: d.lat, lon: d.lon, zubringer: zubringerOf(d)
          })),
          ["car", "bike", "transit_auto"]
        );
        const routes = {};
        // Keyed by the mode that was actually routed, not by the one asked for:
        // "transit_auto" answers with the variant it chose, and that key is
        // what makes the card able to label the row "Rad + ÖPNV".
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
    step(by) {
      const target = state.data.plots[this.index + by];
      if (target) this.$router.push({ name: "plot", params: { id: target.id } });
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
      this.naming = false;
      this.plot.houseTypeId = id;
      this.sizeDraft = { length: null, width: null };
      if (id === CUSTOM_SIZE) {
        this.plot.customSize ||= {
          length: Math.round(this.building.width * 10) / 10,
          width: Math.round(this.building.depth * 10) / 10
        };
      } else {
        const type = houseTypeById(id);
        if (type?.ratio) this.plot.ratio = type.ratio;
      }
      save();
    },
    customField(field) {
      const draft = this.sizeDraft[field];
      return draft === null ? this.customSize[field] : draft;
    },
    /**
     * Typing must never rewrite what is in the field: on the way to 14 the
     * digit 1 is not a 4 m house, it is half of a number. The text therefore
     * stands as entered, and only a plausible value reaches the drawing.
     */
    typeCustomSize(field, value) {
      this.sizeDraft[field] = value;
      const entered = parseFloat(value);
      if (!Number.isFinite(entered) || entered < MIN_EDGE || entered > MAX_EDGE) return;
      this.storeCustomSize(field, entered);
    },
    /** Leaving the field ends the entry: now it is clamped, and an unusable
     *  entry falls back to the size that is stored rather than to nothing. */
    commitCustomSize(field) {
      const entered = parseFloat(this.sizeDraft[field]);
      if (Number.isFinite(entered)) {
        this.storeCustomSize(field, Math.min(MAX_EDGE, Math.max(MIN_EDGE, entered)));
      }
      this.sizeDraft[field] = null;
    },
    storeCustomSize(field, value) {
      if (this.customSize[field] === value) return;
      this.plot.customSize = { ...this.customSize, [field]: value };
      save();
    },
    /** Step one of saving: the catalogue is a list people read later, so a
     *  type goes into it under a name, not under its own dimensions. */
    startNaming() {
      this.typeName = this.dimensionLabel;
      this.naming = true;
      // Selected, not just focused: typing replaces the default, Enter keeps it.
      this.$nextTick(() => {
        this.$refs.nameField?.focus();
        this.$refs.nameField?.select();
      });
    },
    cancelNaming() { this.naming = false; },
    confirmHouseType() {
      const { length, width } = this.customSize;
      const type = addHouseType({
        id: newId("house"), manufacturer: "Eigene Maße", name: this.typeName.trim() || this.dimensionLabel,
        builtArea: Math.round(length * width * 100) / 100, livingArea: null,
        livingAreaGround: null, livingAreaUpper: null, length, width,
        roofShape: "offen", priceFrom: null, ratio: length / width,
        source: null, readAt: new Date().toISOString().slice(0, 10), custom: true
      });
      this.naming = false;
      this.plot.houseTypeId = type.id;
      save();
    },
    alignToStreet() {
      const next = alignToEdge(this.plot.polygon, this.envelope, this.building, this.plot.streetEdge ?? 0);
      this.plot.house = { cx: next.cx, cy: next.cy, rotation: Math.round(next.rotation * 10) / 10 };
      save();
    },
    toggleNeighbours() {
      this.plot.showNeighbours = !this.plot.showNeighbours;
      save();
      if (this.plot.showNeighbours) this.loadNeighbours();
    },
    /** One question per plot; the backend answers repeats from disk. */
    async loadNeighbours() {
      if (!this.plot?.anchor || this.neighbourBuildings.length || this.neighboursBusy) return;
      this.neighboursBusy = true;
      this.neighboursError = null;
      try {
        const answer = await fetchNeighbourBuildings(this.plot.anchor.lat, this.plot.anchor.lon);
        this.neighbourBuildings = answer?.gebaeude ?? [];
        this.neighbourSource = /OpenStreetMap|overpass/i.test(answer?.quelle ?? "")
          ? "OpenStreetMap"
          : "dem Liegenschaftskataster";
      } catch (error) {
        this.neighboursError = error.message;
      } finally {
        this.neighboursBusy = false;
      }
    },
    toggleConfine() {
      this.plot.confineHouse = !this.confineHouse;
      save();
      // Switching it on with the house already outside would otherwise leave a
      // violation that dragging can no longer undo.
      this.reseatHouse();
    },
    /** Back into the window, once, after something other than a drag put the
     *  house outside it. Keeps the angle and stays as near the old position as
     *  the window allows; does nothing if the footprint fits nowhere. */
    reseatHouse() {
      if (!this.plot || !this.confineHouse) return;
      if (!cornersOutside(this.building, this.envelope)) return;
      const seat = findPlacement(this.envelope, this.building.width, this.building.depth, {
        rotation: this.building.rotation,
        near: { x: this.building.cx, y: this.building.cy }
      });
      if (!seat) return;
      this.plot.house.cx = seat.cx;
      this.plot.house.cy = seat.cy;
      save();
    }
  }
};
</script>

<style scoped>

.page-head__sub{ max-width: 64ch; }

.plan-grid{ display: grid; grid-template-columns: minmax(0, 1fr) 336px; gap: var(--w2b-space-4); align-items: start; }
@media (max-width: 1140px){ .plan-grid{ grid-template-columns: 1fr; } }
.plan-frame{ position: sticky; top: var(--w2b-space-3); }
@media (max-width: 1140px){ .plan-frame{ position: static; } }

.notice{ border-radius: 0; }
.measure-bar{ display: flex; align-items: center; gap: var(--w2b-space-3); border-bottom: 1px solid var(--w2b-line); }

.facts{ display: flex; flex-direction: column; gap: var(--w2b-space-4); }

.price-band{ padding: var(--w2b-space-4); }
.price-band__scale{ position: relative; height: 34px; margin-bottom: var(--w2b-space-2); }
.price-band__axis{ position: absolute; left: 0; right: 0; top: 17px; height: 1px; background: var(--w2b-line); }
.price-band__range{ position: absolute; top: 15px; height: 5px; border-radius: var(--w2b-radius-full); background: var(--w2b-primary-veil); }
.price-band__brw{ position: absolute; top: 7px; width: 2px; height: 21px; background: var(--w2b-primary); border-radius: 1px; }
.price-band__marker{ position: absolute; top: 11px; width: 12px; height: 12px; margin-left: -6px; border-radius: 3px; background: var(--w2b-secondary); border: 1.5px solid var(--w2b-secondary-text); transform: rotate(45deg); }
.price-band__axis-labels{ display: flex; justify-content: space-between; font-family: var(--w2b-font-mono); font-size: 10.5px; color: var(--w2b-muted); }
.price-band__statement{ margin-top: var(--w2b-space-3); font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.price-band__statement b{ color: var(--w2b-ink); }

.tools{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--w2b-space-4); align-items: start; }
.depth{ width: 72px; padding: 4px 7px; text-align: right; }
.slider{ display: grid; grid-template-columns: 1fr auto; gap: 5px var(--w2b-space-3); align-items: center; padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }
.slider label{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs); letter-spacing: .09em; text-transform: uppercase; color: var(--w2b-muted); }
.slider input[type="range"]{ grid-column: 1 / -1; }
.slider__hint{ grid-column: 1 / -1; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.field--framed{ padding: var(--w2b-space-3) var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line); }
.custom-size{ display: grid; grid-template-columns: 1fr 1fr; gap: var(--w2b-space-3); padding: var(--w2b-space-3) var(--w2b-space-4); border-bottom: 1px solid var(--w2b-line); background: var(--w2b-secondary-veil); }
.custom-size__hint{ grid-column: 1 / -1; font-size: var(--w2b-text-xs); color: var(--w2b-secondary-text); }
.naming{ grid-column: 1 / -1; display: grid; gap: var(--w2b-space-2); min-width: 0; }
.naming input{ font-family: var(--w2b-font-body); }
.naming__buttons{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-2); }
.naming__hint{ font-size: var(--w2b-text-xs); color: var(--w2b-secondary-text); }
.align{ display: flex; flex-direction: column; gap: var(--w2b-space-2); padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }
.custom-size__hint--warn{ color: var(--w2b-warning-text); }
.neighbour-note{ font-size: var(--w2b-text-xs); }
.align, .confine{ display: flex; flex-direction: column; align-items: flex-start; gap: var(--w2b-space-2); padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }

</style>
