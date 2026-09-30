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
        <button type="button" class="btn btn--secondary" :aria-pressed="String(sharing)"
                @click="sharing = !sharing">Teilen</button>
        <button type="button" class="btn btn--secondary" @click="print">Drucken</button>
      </div>
    </div>

    <SharePanel v-if="sharing" :plot="plot" @close="sharing = false"
                @created="$refs.links?.load()" />

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
        </div>

        <!-- Three states once the neighbours are known: inside, inside but
             nearer a neighbour than 6 m, outside. Without them the two the
             envelope alone can tell. -->
        <p class="notice house-check" :class="`notice--${houseNotice.tone}`" role="status"
           :data-house-status="houseNotice.status">
          <span><b>{{ houseNotice.lead }}</b> {{ houseNotice.rest }}</span>
        </p>

        <p v-if="state.plan.measuring" class="notice measure-bar">
          <span v-if="!measurement.points.length">Auf den Plan klicken, um zu messen. Jeder weitere Klick verlängert den Streckenzug.</span>
          <span v-else><b>{{ metres(measurement.length) }}</b> über {{ measurement.points.length - 1 }}
            {{ measurement.points.length === 2 ? "Abschnitt" : "Abschnitte" }}.</span>
          <button v-if="measurement.points.length" type="button" class="btn btn--quiet btn--small"
                  style="margin-left:auto" @click="clearMeasurement">Zurücksetzen</button>
        </p>

        <div class="plan-stage">
          <SitePlan ref="plan" :plot="plot" :building="building" interactive
                    :measuring="state.plan.measuring" @measured="m => (measurement = m)"
                    :backdrop="state.plan.backdrop" :north-up="state.plan.northUp"
                    :show-dimensions="state.plan.showDimensions" :show-setbacks="state.plan.showSetbacks"
                    :confine-to-envelope="confineHouse"
                    :house-selected="sidePane === 'building'"
                    :neighbourhood="neighbourhoodShown ? neighbourhood : null"
                    :neighbour-markers="neighbourMarkers" :active-building="activeBuilding"
                    :neighbour-highlight="neighbourHighlight" :frame="planFrameShown"
                    :house-status="houseCheck ? houseCheck.status : null"
                    @move="moveHouse" @select="selectOnPlan"
                    @neighbour-hover="hoverBuilding" @neighbour-pick="pinBuilding" />
          <!-- The house is laid on the plot to try it out. Saying which one, on
               the drawing itself, keeps it findable while the column beside
               the plan shows the plot. -->
          <div v-if="building" class="house-chip no-print">
            <span class="house-chip__label">Haus</span>
            <span class="house-chip__name">{{ houseLabel }}</span>
            <button type="button" :aria-pressed="String(sidePane === 'building')"
                    @click="showPane(sidePane === 'building' ? 'plot' : 'building')">
              {{ sidePane === "building" ? "Fertig" : "Bearbeiten" }}
            </button>
          </div>
          <!-- How much ground the plan frames, while the neighbourhood is open. -->
          <div v-if="neighbourhoodShown" class="plan-zoom no-print" role="group" aria-label="Ausschnitt">
            <button v-for="f in frames" :key="f.id" type="button" :aria-pressed="String(planFrameShown === f.id)"
                    :disabled="f.id === 'street' && !streetFramePossible"
                    :title="f.id === 'street' && !streetFramePossible ? 'Auf unserer Straßenseite steht kein Nachbarhaus, an dem sich ein Band ablesen ließe.' : null"
                    @click="planFrame = f.id">{{ f.name }}</button>
          </div>
        </div>

        <div class="plan-foot">
          <span>ETRS89 / UTM33N · EPSG:25833</span>
          <span>© GeoSN, dl-de/by-2-0</span>
        </div>
      </div>

      <!-- Two things share this column: the plot, which is what it is, and the
           house laid on it to try, which is the user's. They are two tabs so
           one never reads as part of the other; a click on the house in the
           plan opens its tab, a click anywhere else goes back. -->
      <aside class="facts">
        <div ref="tabs" class="side-tabs no-print" role="tablist" aria-label="Spalte neben dem Plan">
          <button v-for="pane in panes" :id="`tab-${pane.id}`" :key="pane.id" type="button" role="tab"
                  :aria-selected="String(sidePane === pane.id)" :aria-controls="`pane-${pane.id}`"
                  :tabindex="sidePane === pane.id ? 0 : -1"
                  @click="showPane(pane.id)" @keydown="tabKey">
            <span class="side-tabs__mark" :class="`side-tabs__mark--${pane.id}`" aria-hidden="true"></span>
            {{ pane.name }}
          </button>
        </div>

        <!-- v-show, not v-if: paper has no tabs, so both print, and the
             fields keep what is half-typed in them across a switch. -->
        <div v-show="sidePane === 'plot'" id="pane-plot" class="side-pane" role="tabpanel"
             aria-labelledby="tab-plot">
          <section class="panel">
            <div class="panel__head"><h3>Grundstück</h3></div>
            <dl class="value-list">
              <dt>Gemarkung</dt><dd>{{ plot.gemarkung }}</dd>
              <dt>Flurstücke</dt><dd>{{ plot.flurstuecke.join(" · ") }}</dd>
              <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
              <dt>Fläche gerechnet</dt><dd>{{ area(metrics.computedArea, 1) }}</dd>
              <dt>Grenzpunkte</dt><dd>{{ plot.polygon.length }}</dd>
              <dt>Straßenfront</dt><dd>{{ metres(metrics.streetFrontage) }}</dd>
            </dl>
            <HintFold :count="2">
              <p>Gemarkung, Flurstücke und amtliche Fläche stammen aus dem Liegenschaftskataster
                (ALKIS) von GeoSN. Grenzpunkte, gerechnete Fläche und Straßenfront sind aus dem
                Umriss gemessen, den es liefert.</p>
              <p>Für den Preisvergleich zählt die amtliche Fläche. Die aus dem Polygon
                gerechnete weicht regelmäßig um ein paar Quadratmeter ab.</p>
            </HintFold>
          </section>

          <section class="panel">
            <div class="panel__head">
              <h3>Preis</h3><div class="spacer"></div>
              <span v-if="priceVerdict" class="chip" :class="`chip--${metrics.deviationClass}`">{{ priceVerdict.chip }}</span>
            </div>
            <dl class="value-list">
              <dt>Kaufpreis</dt>
              <dd>
                {{ euro(plot.askingPrice) }}
                <button v-if="priceDraft === null" type="button" class="price-edit__open no-print"
                        @click="startPriceEdit">{{ hasPrice ? "Ändern" : "Eintragen" }}</button>
              </dd>
              <dt>Angebot je m²</dt><dd>{{ euroPerSqm(metrics.pricePerSqm) }}</dd>
              <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }} <span class="faint">Zone {{ plot.brwZone }}</span></dd>
              <dt>Stichtag</dt><dd>{{ date(plot.brwReferenceDate) }}</dd>
              <template v-if="plot.brwReferencePlotArea">
                <dt>Richtwertgrundstück</dt><dd>{{ area(plot.brwReferencePlotArea) }}</dd>
              </template>
            </dl>
            <!-- The listing is where the price comes from, and the wizard is
                 not the only way a plot arrives: a parcel picked by number
                 has none, and a price changes after a phone call. -->
            <div v-if="priceDraft !== null" class="price-edit no-print">
              <label for="asking-price">Kaufpreis in Euro</label>
              <input id="asking-price" ref="priceField" type="text" inputmode="decimal"
                     autocomplete="off" placeholder="z. B. 249.000" v-model="priceDraft"
                     :aria-invalid="String(Boolean(priceError))" aria-describedby="asking-price-hint"
                     @keydown.enter.prevent="commitPrice" @keydown.esc.prevent="cancelPrice">
              <div class="price-edit__buttons">
                <button type="button" class="btn btn--small" @click="commitPrice">Übernehmen</button>
                <button type="button" class="btn btn--quiet btn--small" @click="cancelPrice">Abbrechen</button>
              </div>
              <p id="asking-price-hint" class="price-edit__hint" :class="{ 'price-edit__hint--error': priceError }">
                {{ priceError || "Wie im Inserat, mit oder ohne Tausenderpunkte. Ein leeres Feld entfernt den Preis." }}
              </p>
            </div>
            <div v-if="Number.isFinite(plot.bodenrichtwert)" class="price-band">
              <div class="price-band__scale">
                <div class="price-band__axis"></div>
                <div class="price-band__range" :style="{ left: pricePosition(plot.bodenrichtwert * (1 - PRICE_BAND)) + '%', width: (pricePosition(plot.bodenrichtwert * (1 + PRICE_BAND)) - pricePosition(plot.bodenrichtwert * (1 - PRICE_BAND))) + '%' }"></div>
                <div class="price-band__brw" :style="{ left: pricePosition(plot.bodenrichtwert) + '%' }"></div>
                <div v-if="metrics.pricePerSqm !== null" class="price-band__marker"
                     :class="priceVerdict && `price-band__marker--${priceVerdict.stage}`"
                     :style="{ left: pricePosition(metrics.pricePerSqm) + '%' }"
                     :title="`Angebot ${euroPerSqm(metrics.pricePerSqm)}/m²`"></div>
              </div>
              <div class="price-band__axis-labels">
                <span>{{ Math.round(priceRange.lo) }} €</span>
                <span>{{ Math.round(plot.bodenrichtwert) }} €</span>
                <span>{{ Math.round(priceRange.hi) }} €</span>
              </div>
              <p v-if="!priceVerdict" class="price-band__statement">
                Ohne Kaufpreis lässt sich das Angebot nicht mit dem Bodenrichtwert vergleichen.
                <button v-if="priceDraft === null && !hasPrice" type="button"
                        class="btn btn--secondary btn--small price-band__action no-print"
                        @click="startPriceEdit">Kaufpreis eintragen</button>
              </p>
            </div>
            <!-- The magnitude without a sign: „−4,2 % unter" said the direction
                 twice. The word carries it, and the colour follows the same
                 three stages as the chip above. -->
            <p v-if="priceVerdict" class="price-verdict" :class="`price-verdict--${priceVerdict.stage}`">
              <span class="price-verdict__mark" aria-hidden="true">{{ priceVerdict.mark }}</span>
              <span>
                Das Angebot liegt <b>{{ num(Math.abs(metrics.deviation), 1) }} %
                {{ metrics.deviation > 0 ? "über" : "unter" }} dem Bodenrichtwert</b>
                <template v-if="priceVerdict.stage === 'within'">, im Rahmen der Zone (± {{ num(PRICE_BAND * 100, 0) }} %).</template>
                <template v-else> der Zone, {{ priceVerdict.stage === "below" ? "unterhalb" : "oberhalb" }} des üblichen Rahmens.</template>
              </span>
            </p>
            <HintFold v-if="priceHintCount" :count="priceHintCount">
              <p v-if="Number.isFinite(plot.bodenrichtwert)">
                Bodenrichtwert, Zone und Stichtag stammen aus BORIS Sachsen, dem
                Bodenrichtwertportal der Gutachterausschüsse.
              </p>
              <p v-if="conversionNeeded">
                Der Richtwert gilt für ein gedachtes Grundstück von
                {{ area(plot.brwReferencePlotArea) }}. Für {{ area(plot.officialArea) }} ist er
                nach der Umrechnungstabelle des Gutachterausschusses anzupassen. Das Produkt
                aus Wert und Fläche ist also nicht der Bodenwert dieses Grundstücks.
                <a v-if="plot.brwConversionUrl" :href="plot.brwConversionUrl"
                   target="_blank" rel="noopener noreferrer">Umrechnungstabelle</a>
              </p>
              <p v-if="Number.isFinite(plot.bodenrichtwert)">
                Nach § 15 Abs. 2 ImmoWertV kann ein einzelnes Grundstück innerhalb der
                Richtwertzone eine abweichende Nutzungsart haben; dann gilt der Zonenwert nicht.
              </p>
            </HintFold>
          </section>
          <!-- Folded: the shape figures are for the plot that looks odd, and the
               line on the fold already names the verdict. -->
          <details class="panel fold">
            <summary class="panel__head fold__head">
              <h3>Form</h3><span class="spacer"></span>
              <span class="fold__summary">{{ metrics.shapeClass }} · 1 : {{ num(aspectRatio) }}</span>
            </summary>
            <dl class="value-list">
              <dt>Rechteckigkeit</dt><dd>{{ num(metrics.rectangularity, 3) }}</dd>
              <dt>Einstufung</dt><dd><span class="chip chip--good">{{ metrics.shapeClass }}</span></dd>
              <dt>Seitenverhältnis</dt><dd>1 : {{ num(aspectRatio) }}</dd>
              <dt>Umschl. Rechteck</dt><dd>{{ num(metrics.mrr.width, 1) }} × {{ num(metrics.mrr.height, 1) }} m</dd>
            </dl>
          </details>

          <details class="panel fold">
            <summary class="panel__head fold__head">
              <h3>Abstandsflächen</h3><span class="spacer"></span>
              <span class="fold__summary">{{ setbackSummary }}</span>
            </summary>
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
                <template v-if="plot.wallHeight * 0.4 < 3">. Unter dem Mindestmaß von 3 m, deshalb greift der Mindestwert.</template>
                <template v-else>. Maßgeblich, weil größer als das Mindestmaß von 3 m.</template>
              </p>
            </div>
            <HintFold title="Vereinfacht gerechnet, keine Prüfung" caution>
              <p>Die Abstandstiefe bemisst sich nach § 6 SächsBO grundsätzlich nach der Wandhöhe;
                3 m sind der Mindestwert, nicht die Regel. Grenzgaragen sind privilegiert, ein
                Bebauungsplan kann abweichende Baugrenzen festsetzen. Verbindlich entscheidet
                die Bauaufsicht.</p>
            </HintFold>
          </details>
        </div>

        <div v-show="sidePane === 'building'" id="pane-building" class="side-pane" role="tabpanel"
             aria-labelledby="tab-building">
          <section class="panel">
            <div class="panel__head"><h3>Baukörper</h3></div>
            <div class="field field--framed no-print">
              <label for="house-type">Haustyp</label>
              <select id="house-type" :value="plot.houseTypeId" @change="setHouseType($event.target.value)">
                <option v-for="h in state.data.houseTypes" :key="h.id" :value="h.id">
                  {{ h.manufacturer }} {{ h.name }} · {{ num(h.builtArea) }} m² bebaut
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
                  Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
                </template>
                <template v-else>Ergibt {{ area(customSize.length * customSize.width, 1) }} bebaute Fläche.</template>
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
            </div>

            <div v-if="building.estimated" class="slider no-print">
              <label for="ratio">Seitenverhältnis</label>
              <output class="mono">{{ num(plot.ratio) }}</output>
              <input id="ratio" type="range" min="1" max="2.2" step="0.01"
                     :value="plot.ratio" @input="setRatio($event.target.value)">
              <p class="slider__hint">Aus der bebauten Fläche geschätzt; das Datenblatt liefert keine Außenmaße.</p>
            </div>

            <div class="slider no-print">
              <label for="rotation">Drehung</label>
              <output class="mono">{{ degrees(plot.house.rotation) }}</output>
              <input id="rotation" type="range" min="-90" max="90" step="1"
                     :value="plot.house.rotation" @input="setRotation($event.target.value)">
            </div>

            <div class="confine no-print">
              <button type="button" class="toggle" :aria-pressed="String(confineHouse)"
                      @click="toggleConfine">Im Bebauungsfenster halten</button>
            </div>

            <!-- How the controls behave, not what the house is: on paper
                 there is nothing to drag. -->
            <HintFold title="So bedienen Sie den Baukörper" :count="3" class="no-print">
              <p>Haus auf dem Plan anklicken, um es hier zu bearbeiten. Ziehen verschiebt es,
                die Pfeiltasten verschieben es fein.</p>
              <p>„An der Straße ausrichten“ dreht den Baukörper parallel zur Straßenfront
                ({{ degrees(streetAngle) }}) und schiebt ihn zurück ins Fenster, falls er dabei
                herausrutscht.</p>
              <p>„Im Bebauungsfenster halten“: Der Baukörper lässt sich dann nicht über die
                Abstandsflächen hinausschieben. Ziehen und Pfeiltasten enden an der Grenze des
                Fensters, an der er entlanggleitet. Passt er überhaupt nirgends hinein, greift die
                Begrenzung nicht: er ist dann frei verschiebbar, und die roten Ecken zeigen, wo er
                hinausragt.</p>
            </HintFold>
          </section>
        </div>

        <!-- Printed only once there is something in it: a tab nobody opened
             has asked no service. -->
        <div v-show="sidePane === 'neighbourhood'" id="pane-neighbourhood" class="side-pane"
             :class="{ 'no-print': !neighbourhood }" role="tabpanel" aria-labelledby="tab-neighbourhood">
          <NeighbourhoodPane :analysis="neighbourhood" :findings="neighbourhoodList"
                             :busy="neighboursBusy" :error="neighboursError" :source="neighbourSource"
                             :has-anchor="hasAnchor" :planning="planningResult"
                             :planning-busy="planningBusy" :planning-error="planningError"
                             :municipality="plot.municipality" :active-building="activeBuilding"
                             :open="openAnalysis"
                             @hover="hoverBuilding" @pin="pinBuilding" @open="openNeighbourAnalysis"
                             @reading="setReading" @frame="f => (planFrame = f)" />
        </div>
      </aside>
    </div>

    <NeighbourhoodDetail v-if="neighbourhood && neighbourhood.buildings.length"
                         :analysis="neighbourhood" :findings="neighbourhoodList" />

    <!-- What holds at the plot. It used to be a page of its own, with the
         parcel and the land value repeated from this one; here it keeps only
         what is its own: a small map without the house, and the checks. -->
    <section id="standort" class="stack">
      <div class="page-head">
        <div>
          <p class="eyebrow">Standort</p>
          <h2>Was der Standort mitbringt</h2>
          <p class="page-head__sub">
            Lärm, Hochwasser, Radon, Trinkwasserschutz, Schutzgebiete, Hangneigung, Baugrund
            und Luftqualität, gefragt mit dem Umriss des Flurstücks, nicht mit einem Punkt.
            Ein Grundstück schneidet Isophonen und Zonengrenzen; sein Mittelpunkt antwortet
            nur für einen Quadratmeter davon.
          </p>
        </div>
      </div>

      <p v-if="!hasAnchor" class="notice">
        Für dieses Grundstück ist keine Koordinate hinterlegt. Ohne sie gibt es keine Fläche,
        mit der sich die Fachdienste fragen ließen.
      </p>

      <div v-else class="location">
        <section class="panel location__map">
          <div class="plan-bar no-print">
            <span class="plan-bar__label">Grund</span>
            <div class="button-group" role="group" aria-label="Hintergrund der Standortkarte">
              <button v-for="b in locationBackdrops" :key="b.id" type="button"
                      :aria-pressed="String(locationBackdrop === b.id)"
                      @click="locationBackdrop = b.id">{{ b.name }}</button>
            </div>
            <div class="spacer"></div>
            <!-- One unit, so a narrow bar wraps the label with its switch. -->
            <span class="location__layer">
              <span class="plan-bar__label">Ebene</span>
              <button type="button" class="toggle" :aria-pressed="String(Boolean(locationOverlay))"
                      @click="toggleNoise">Lärm</button>
            </span>
          </div>

          <!-- Where the survey has no value for the plot, a map without colour
               on it reads as quiet. So it goes grey and says so; switching the
               layer on brings the colour back, to show where the mapped roads
               are. -->
          <p v-if="noiseMissing" class="location__no-noise" role="note">
            <strong>Keine Lärmwerte am Grundstück</strong>
            Kartiert sind nur Hauptverkehrsstraßen, Straßenbahn und Flughäfen. Ruhig ist es
            deshalb nicht unbedingt.
          </p>
          <div class="location__frame"
               :class="{ 'location__frame--no-noise': noiseMissing && !locationOverlay }">
            <!-- No house: this map is about the ground, and a footprint would be
                 the loudest thing on it. -->
            <SitePlan :plot="plot" :building="null" :show-building="false" navigable cooperative
                      :backdrop="locationBackdrop" :overlay="locationOverlay" north-up
                      :show-dimensions="false" :show-setbacks="false"
                      :width="600" :height="470" />
          </div>

          <div v-if="locationOverlay" class="key">
            <p class="key__head">Schallpegel L<sub>DEN</sub> über 24 Stunden, dB(A)</p>
            <ul class="key__bands">
              <li v-for="band in noiseBands" :key="band.label">
                <span class="key__swatch" :style="{ background: band.colour }"></span>{{ band.label }}
              </li>
            </ul>
          </div>

          <HintFold :count="locationOverlay ? 2 : 1">
            <p class="no-print">Ziehen verschiebt den Ausschnitt, Strg und Mausrad zoomen, ein
              Doppelklick stellt ihn zurück.</p>
            <p v-if="locationOverlay">Die Karte zeichnet erst ab 50 dB(A), und sie kennt nur
              Hauptverkehrsstraßen, die Straßenbahn in Leipzig, Dresden und Chemnitz und die
              Flughäfen. Wo keine Farbe liegt, fehlt der Wert; leise heißt das nicht.</p>
          </HintFold>

          <div class="plan-foot">
            <span>{{ locationOverlay ? "Isophonen: LfULG · " : "" }}Kataster und Luftbild: © GeoSN, dl-de/by-2-0</span>
            <span v-if="siteCheckResult">Abgerufen {{ date(siteCheckResult.abgerufen_am) }}</span>
          </div>
        </section>

        <CheckList :plot="plot" auto @loaded="checksLoaded" />
      </div>
    </section>

    <section class="stack">
      <div class="page-head">
        <div>
          <p class="eyebrow">Erreichbarkeiten</p>
          <h2>Wege von hier</h2>
          <p class="page-head__sub">
            Für jedes hinterlegte Ziel Auto, Rad und ÖPNV, gerechnet vom Grundstück aus.
            Beim ÖPNV wird der Weg zur ersten Haltestelle mitgewählt: zu Fuß, mit dem
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
        Dieses Grundstück hat keine Koordinate. Ohne sie gibt es keinen Startpunkt für eine Route.
      </p>
      <p v-else-if="!locatedDestinations.length && state.data.destinations.length" class="notice">
        Keines der Ziele ist verortet. Unter „Ziele bearbeiten“ die Adressen nachschlagen lassen.
      </p>

      <!-- Routing several destinations takes seconds, and a page that shows
           nothing in that time reads as one that found nothing. The cards draw
           themselves as placeholders while they wait. -->
      <RouteCards :plot="plot" :busy="routesBusy && !hasRoutes" />

      <!-- The map and the list of what is nearby answer the same question and
           belong side by side: the map says where, the table says how far. -->
      <div class="plot-page__surroundings">
        <section v-if="hasAnchor" class="panel plot-page__map">
          <SurroundingsMap :plot="plot" :building="building" :hits="nearbyHits"
                           :destinations="mapDestinations" :height="560" />
        </section>
        <NearbyPanel :plot="plot" auto @loaded="r => (nearbyResult = r)" />
      </div>

      <!-- At the foot of the page and absent while there is nothing: a link
           already handed out is the one thing here somebody needs to be able
           to take back. -->
      <SharedLinks ref="links" :plot="plot" />
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
import { markRaw } from "vue";
import SitePlan from "../components/SitePlan.vue";
import SharePanel from "../components/SharePanel.vue";
import SharedLinks from "../components/SharedLinks.vue";
import RouteCards from "../components/RouteCards.vue";
import NearbyPanel from "../components/NearbyPanel.vue";
import SurroundingsMap from "../components/SurroundingsMap.vue";
import CheckList from "../components/CheckList.vue";
import HintFold from "../components/HintFold.vue";
import NeighbourhoodPane from "../components/NeighbourhoodPane.vue";
import NeighbourhoodDetail from "../components/NeighbourhoodDetail.vue";
import {
  state, plotById, placement, houseTypeById, houseFootprint, save, addHouseType,
  newId, setRoutes, CUSTOM_SIZE, DEFAULT_FOOTPRINT
} from "../lib/store.js";
import { reachability, neighbourBuildings as fetchNeighbourBuildings, planning as fetchPlanning } from "../lib/api.js";
import { zubringerOf, fastestMode, coordinatesOf, MODES } from "../lib/routes.js";
import { toWgs84 } from "../lib/projection.js";
import { analyseNeighbourhood, localBuildings, checkHouse, READING_SETBACK } from "../lib/neighbourhood.js";
import { neighbourhoodFindings, houseCheckFinding } from "../lib/findings.js";
import { NOISE_BANDS } from "../lib/basemap.js";
import { noiseOnPlot } from "../lib/siteChecks.js";
import { plotMetrics, PRICE_BAND } from "../lib/metrics.js";
import {
  polygonEdges, edgeCompass, buildableArea, cornersOutside, smallestSetback,
  alignToEdge, alignmentToEdge, findPlacement
} from "../lib/geometry.js";
import { area, euro, euroPerSqm, metres, num, percent, degrees, date, duration, parseGermanNumber } from "../lib/format.js";

/** What each price stage shows: the chip in the panel head and the mark in
 *  front of the coloured line. „within" is deliberately neutral — a few per
 *  cent either side of a zone value is noise, not a bargain. */
const PRICE_STAGES = {
  below: { chip: "unter Richtwert", mark: "▼" },
  within: { chip: "im Rahmen", mark: "≈" },
  above: { chip: "über Richtwert", mark: "▲" }
};

/** Edge lengths a house can plausibly have, in metres. Anything outside is a typo. */
const MIN_EDGE = 4;
const MAX_EDGE = 30;

export default {
  name: "PlotView",
  components: {
    SitePlan, SharePanel, SharedLinks, RouteCards, NearbyPanel, SurroundingsMap, CheckList, HintFold,
    NeighbourhoodPane, NeighbourhoodDetail
  },
  props: {
    /** The plot's id, straight out of the URL. */
    id: { type: String, required: true }
  },
  data() {
    return {
      state, CUSTOM_SIZE, MIN_EDGE, MAX_EDGE, PRICE_BAND,
      /** What stands in the two edge-length fields while they are being typed
       *  in. `null` means nobody is editing, so the stored size is shown. */
      sizeDraft: { length: null, width: null },
      measurement: { points: [], length: 0 },
      sharing: false,
      /** Which tab the column beside the plan shows: "plot", "building" or
       *  "neighbourhood". The plot comes first — whether the house fits is the
       *  second question. Not stored: a plot opens on its figures. */
      sidePane: "plot",
      /** The plan's frame while the neighbourhood tab is open. */
      planFrame: "neighbours",
      frames: [
        { id: "plot", name: "Grundstück" },
        { id: "neighbours", name: "Nachbarn" },
        { id: "street", name: "Straße" }
      ],
      /** The price field's text while it is open; null while it is closed. */
      priceDraft: null,
      priceError: null,
      panes: [
        { id: "plot", name: "Grundstück" },
        { id: "building", name: "Bebauung" },
        { id: "neighbourhood", name: "Nachbarschaft" }
      ],
      naming: false,
      typeName: "",
      /** Outlines are not stored with the plot: they are somebody else's data,
       *  they are large, and the backend keeps them for a month anyway. Only
       *  the readings chosen for them live in the document. Held raw: the
       *  analysis copies them once, and a deep proxy over 70 rings costs a
       *  trap per coordinate read. */
      neighbourBuildings: markRaw([]),
      /** The plot the outlines above belong to; null before the first answer. */
      neighboursFor: null,
      /** Which register the outlines came from — the answer says so, and the
       *  sentence beside the drawing must not claim a different one. */
      neighbourSource: "dem Liegenschaftskataster",
      neighboursBusy: false,
      neighboursError: null,
      /** The RAPIS answer for this plot, asked once when the tab opens. */
      planningResult: null,
      planningFor: null,
      planningBusy: false,
      planningError: null,
      /** The building the pointer or the keyboard is on, and the one pinned by
       *  a click; the pinned one wins until it is clicked again. */
      hoveredBuilding: null,
      pinnedBuilding: null,
      /** The one analysis open inline: `{ kind, findingId, boundary, section }`. */
      openAnalysis: null,
      routesBusy: false,
      routesError: null,
      /** The last /api/nearby answer, as the panel reports it — the map draws
       *  what the table lists, so both come from the one request. */
      nearbyResult: null,
      /** Which plot this browser session has already routed. Asking again on
       *  every visit would put the routing service through the whole set for a
       *  page the user only opened to read the area. */
      routedFor: null,
      /** The last /api/site-checks answer. It says whether the noise survey
       *  mapped anything here, which the tiles cannot. */
      siteCheckResult: null,
      /* The location map keeps its own ground: it is a second map with another
         job, and switching the plan to the aerial must not switch this one. */
      locationBackdrop: "map",
      /** On by default, and off again once the checks say the plot sits in no
       *  band — unless somebody chose it by hand. */
      locationOverlay: "laerm",
      noiseChosen: false,
      locationBackdrops: [
        { id: "map", name: "Karte" },
        { id: "aerial", name: "Luftbild" },
        { id: "cadastre", name: "Kataster" }
      ],
      backdrops: [
        { id: "none", name: "Ohne" },
        { id: "map", name: "Karte" },
        { id: "aerial", name: "Luftbild" },
        { id: "cadastre", name: "Kataster" }
      ]
    };
  },
  computed: {
    /** What the panel found, for the map to draw. */
    nearbyHits() { return this.nearbyResult?.treffer ?? []; },
    /** Every located destination with the fastest route that was actually
     *  computed for this plot — the line to draw and the time to name. */
    mapDestinations() {
      return this.locatedDestinations.map(destination => {
        const route = this.plot?.routes?.[destination.id];
        const mode = fastestMode(route);
        const leg = mode ? route.modes[mode] : null;
        return {
          id: destination.id,
          name: destination.name,
          lat: destination.lat,
          lon: destination.lon,
          line: leg ? coordinatesOf(leg.geometry) : null,
          note: leg
            ? `${MODES.find(m => m.mode === mode)?.name ?? mode} · ${duration(leg.duration_s)}`
            : ""
        };
      });
    },
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
    hasPrice() { return Number.isFinite(this.plot?.askingPrice); },
    isCustomSize() { return this.plot.houseTypeId === CUSTOM_SIZE; },
    /** The line on the chip over the plan. */
    houseLabel() {
      if (this.houseType) return `${this.houseType.manufacturer} ${this.houseType.name} · ${area(this.builtArea)}`;
      return `Eigene Maße · ${this.dimensionLabel}`;
    },
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
    /** The outlines in this plot's own metre frame, once they are here. */
    localNeighbours() {
      if (!this.plot?.anchor || this.neighboursFor !== this.plot.id) return null;
      return localBuildings(this.neighbourBuildings, this.plot.anchor);
    },
    /** The analysis per building (lib/neighbourhood.js), with the readings the
     *  user chose. Memoised there, so a new reading costs nothing. */
    neighbourhood() {
      if (!this.localNeighbours) return null;
      return analyseNeighbourhood(this.plot, this.localNeighbours, { reading: { ...(this.plot.neighbourReadings ?? {}) } });
    },
    neighbourhoodList() { return neighbourhoodFindings(this.neighbourhood); },
    neighbourhoodShown() { return this.sidePane === "neighbourhood" && Boolean(this.neighbourhood); },
    neighbourMarkers() {
      return this.neighbourhoodList.filter(f => f.marker)
        .map(f => ({ marker: f.marker, buildingId: f.buildingId, title: f.title }));
    },
    activeBuilding() { return this.pinnedBuilding ?? this.hoveredBuilding; },
    /** Leaving the tab returns the plan to the plot. */
    planFrameShown() {
      if (this.sidePane !== "neighbourhood") return "plot";
      return this.planFrame === "street" && !this.streetFramePossible ? "neighbours" : this.planFrame;
    },
    streetFramePossible() { return Boolean(this.neighbourhood?.band?.houses?.length); },
    neighbourHighlight() {
      const open = this.openAnalysis;
      if (!open) return null;
      return open.kind === "section" ? { section: open.section } : { boundary: open.boundary };
    },
    /** Inside, in a 6-m-Zone, or outside — once the neighbours are known.
     *  Cheap enough for every drag: a memoised analysis and four edges
     *  against each zone's outline. */
    houseCheck() {
      if (!this.neighbourhood || !this.building) return null;
      return checkHouse(this.neighbourhood, this.building);
    },
    /** The line over the plan: lead in bold, the rest after it. */
    houseNotice() {
      const finding = houseCheckFinding(this.houseCheck);
      if (finding) {
        const [first, ...rest] = finding.sentences;
        const tone = { inside: "good", zone: "zone", outside: "error" }[finding.status];
        if (finding.status === "zone") {
          const cut = first.indexOf(", reicht aber");
          return { status: finding.status, tone, lead: `${first.slice(0, cut)},`, rest: [first.slice(cut + 2), ...rest].join(" ") };
        }
        return { status: finding.status, tone, lead: first, rest: rest.join(" ") };
      }
      const rest = `Geringster Grenzabstand ${metres(this.narrowestSetback)}.`;
      if (this.violation) {
        const k = this.outliers;
        return { status: "outside", tone: "error", rest,
          lead: `${k} Gebäudeecke${k > 1 ? "n liegen" : " liegt"} außerhalb des Bebauungsfensters.` };
      }
      return { status: "inside", tone: "good", lead: "Baukörper liegt im Bebauungsfenster.", rest };
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
    noiseBands() { return NOISE_BANDS.laerm; },
    /** Where the offer sits against the land value, for the chip, the marker
     *  and the coloured line. Null without an asking price. */
    priceVerdict() {
      const stage = this.metrics.priceStage;
      return stage ? { stage, ...PRICE_STAGES[stage] } : null;
    },
    priceHintCount() {
      // The source and the ImmoWertV note both hang on a land value being there.
      return (this.conversionNeeded ? 1 : 0) + (Number.isFinite(this.plot?.bodenrichtwert) ? 2 : 0);
    },
    /** Only once the checks have answered: before that, nothing is known. */
    noiseMissing() { return noiseOnPlot(this.siteCheckResult) === false; },
    /** Only worth a sentence when the two areas actually differ. */
    conversionNeeded() {
      const reference = this.plot?.brwReferencePlotArea;
      const own = this.plot?.officialArea;
      return Number.isFinite(reference) && Number.isFinite(own) && Math.abs(reference - own) > 1;
    },
    /** The line on the folded setback panel: the depths, not the table. */
    setbackSummary() {
      const depths = (this.plot?.setbacks ?? []).filter(Number.isFinite);
      if (!depths.length) return "—";
      const low = Math.min(...depths);
      const high = Math.max(...depths);
      return low === high ? `${metres(low, 1)} ringsum` : `${num(low, 1)}–${metres(high, 1)}`;
    },
    priceRange() { return { lo: this.plot.bodenrichtwert * 0.7, hi: this.plot.bodenrichtwert * 1.45 }; },
    boundaries() {
      return polygonEdges(this.plot.polygon).map((edge, i) => ({
        name: `${edgeCompass(this.plot.polygon, i, this.plot.northOffset)} · ${i === (this.plot.streetEdge ?? 0) ? "zur Straße" : "Nachbar"}`,
        length: edge.length
      }));
    },
    index() { return state.data.plots.findIndex(p => p.id === this.plot.id); },
    hasPrevious() { return this.index > 0; },
    hasNext() { return this.index < state.data.plots.length - 1; }
  },
  created() {
    this.routeAutomatically();
  },
  watch: {
    /** A default nobody has touched follows the fields above it. */
    dimensionLabel(next, previous) {
      if (this.naming && this.typeName === previous) this.typeName = next;
    },
    /* Another plot in the same view: its outlines are somewhere else, its
       ways may not be computed yet, and its noise is another question. One
       watcher — two `"plot.id"` keys in this object once meant the second
       silently replaced the first, and the next plot was never routed. */
    "plot.id"() {
      this.neighbourBuildings = markRaw([]);
      this.neighboursFor = null;
      this.neighboursError = null;
      this.planningResult = null;
      this.planningFor = null;
      this.planningError = null;
      this.hoveredBuilding = null;
      this.pinnedBuilding = null;
      this.openAnalysis = null;
      if (this.sidePane === "neighbourhood") this.loadNeighbourhood();
      this.routeAutomatically();
      this.siteCheckResult = null;
      this.locationOverlay = "laerm";
      this.noiseChosen = false;
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
    toggleNoise() {
      this.noiseChosen = true;
      this.locationOverlay = this.locationOverlay ? null : "laerm";
    },
    checksLoaded(result) {
      this.siteCheckResult = result;
      if (!this.noiseChosen) this.locationOverlay = noiseOnPlot(result) === false ? null : "laerm";
    },

    showPane(pane) {
      this.sidePane = pane;
      if (pane === "neighbourhood") this.loadNeighbourhood();
    },
    startPriceEdit() {
      this.priceDraft = this.hasPrice ? String(this.plot.askingPrice) : "";
      this.priceError = null;
      this.$nextTick(() => {
        this.$refs.priceField?.focus();
        this.$refs.priceField?.select();
      });
    },
    /** An empty field removes the price; anything that is not a positive
     *  amount keeps the field open and says why, rather than storing a
     *  guess — a stored 0 would read as a free plot. */
    commitPrice() {
      const text = (this.priceDraft ?? "").trim();
      if (!text) {
        this.plot.askingPrice = null;
      } else {
        const amount = parseGermanNumber(text);
        if (amount === null) { this.priceError = "Das ist kein Betrag. Bitte nur die Zahl eintragen, etwa 249.000."; return; }
        if (amount <= 0) { this.priceError = "Ein Kaufpreis ist größer als null."; return; }
        this.plot.askingPrice = Math.round(amount);
      }
      save();
      this.priceDraft = null;
      this.priceError = null;
    },
    cancelPrice() {
      this.priceDraft = null;
      this.priceError = null;
    },
    /** A click on the house opens its tab, a click beside it closes it. */
    selectOnPlan(target) {
      // Beside the house, the building tab closes; the neighbourhood stays
      // open, because its markers are on the plan and a click on one is a
      // click beside the house.
      if (target === "house") this.showPane("building");
      else if (this.sidePane === "building") this.showPane("plot");
      // Below 1140 px the column sits under the plan, where the switch happens
      // out of sight. Scrolled only as far as it takes to see the tabs.
      if (target === "house" && window.matchMedia?.("(max-width: 1140px)").matches) {
        this.$refs.tabs?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      }
    },
    /** Arrow keys move between the tabs, as a tablist does. */
    tabKey(event) {
      const step = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity }[event.key];
      if (step === undefined) return;
      event.preventDefault();
      const ids = this.panes.map(p => p.id);
      const at = ids.indexOf(this.sidePane);
      const next = ids[Math.max(0, Math.min(ids.length - 1, at + step))];
      this.showPane(next);
      this.$nextTick(() => document.getElementById(`tab-${next}`)?.focus());
    },

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
    /** Opening the tab asks both services, once per plot. */
    loadNeighbourhood() {
      this.loadNeighbours();
      this.loadPlanning();
    },
    /** One question per plot; the backend answers repeats from disk. A failed
     *  one is asked again the next time the tab opens. */
    async loadNeighbours() {
      const plot = this.plot;
      if (!plot?.anchor || this.neighboursFor === plot.id || this.neighboursBusy) return;
      this.neighboursBusy = true;
      this.neighboursError = null;
      try {
        const answer = await fetchNeighbourBuildings(plot.anchor.lat, plot.anchor.lon);
        if (this.plot?.id !== plot.id) return;
        this.neighbourBuildings = markRaw(answer?.gebaeude ?? []);
        this.neighbourSource = /OpenStreetMap|overpass/i.test(answer?.quelle ?? "")
          ? "OpenStreetMap"
          : "dem Liegenschaftskataster";
        this.neighboursFor = plot.id;
      } catch (error) {
        if (this.plot?.id === plot.id) this.neighboursError = error.message;
      } finally {
        this.neighboursBusy = false;
      }
    },
    /** RAPIS with the parcel outline, the same ring the location checks send. */
    async loadPlanning() {
      const plot = this.plot;
      if (!plot?.anchor || this.planningFor === plot.id || this.planningBusy) return;
      this.planningBusy = true;
      this.planningError = null;
      try {
        const ring = toWgs84(plot.polygon, plot.anchor);
        const answer = await fetchPlanning([...ring, ring[0]]);
        if (this.plot?.id !== plot.id) return;
        this.planningResult = answer;
        this.planningFor = plot.id;
      } catch (error) {
        if (this.plot?.id === plot.id) this.planningError = error.message;
      } finally {
        this.planningBusy = false;
      }
    },
    hoverBuilding(id) { this.hoveredBuilding = id || null; },
    pinBuilding(id) { this.pinnedBuilding = this.pinnedBuilding === id ? null : id; },
    openNeighbourAnalysis(open) { this.openAnalysis = open; },
    /** The reading of one Grenzbebauung, stored with the plot like its other
     *  settings. The analysis re-runs from its cache. */
    setReading({ buildingId, reading }) {
      const readings = { ...(this.plot.neighbourReadings ?? {}) };
      if (reading === READING_SETBACK) delete readings[buildingId];
      else readings[buildingId] = reading;
      if (Object.keys(readings).length) this.plot.neighbourReadings = readings;
      else delete this.plot.neighbourReadings;
      save();
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
.price-band__action{ display: block; margin-top: var(--w2b-space-2); }
.price-edit__open{
  margin-left: var(--w2b-space-2); padding: 0; border: 0; background: none; cursor: pointer;
  font-family: var(--w2b-font-body); font-size: var(--w2b-text-xs); font-weight: 600;
  color: var(--w2b-primary); text-decoration: underline; text-underline-offset: 2px;
}
.price-edit__open:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: 2px; }
.price-edit{
  display: grid; gap: var(--w2b-space-2); padding: var(--w2b-space-3) var(--w2b-space-4);
  border-top: 1px solid var(--w2b-line-faint); background: var(--w2b-secondary-veil);
}
.price-edit label{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  letter-spacing: .09em; text-transform: uppercase; color: var(--w2b-muted);
}
.price-edit input{ font-family: var(--w2b-font-mono); }
.price-edit__buttons{ display: flex; flex-wrap: wrap; gap: var(--w2b-space-2); }
.price-edit__hint{ margin: 0; font-size: var(--w2b-text-xs); color: var(--w2b-secondary-text); }
.price-edit__hint--error{ color: var(--w2b-error); }
.price-band__marker--below{ background: var(--w2b-good); border-color: var(--w2b-good); }
.price-band__marker--above{ background: var(--w2b-error); border-color: var(--w2b-error); }
.price-verdict{
  display: flex; align-items: flex-start; gap: var(--w2b-space-2); margin: 0;
  padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-s);
}
.price-verdict__mark{ flex: none; font-family: var(--w2b-font-display); font-weight: 700; line-height: 1.35; }
.price-verdict--below{ background: var(--w2b-good-surface); color: var(--w2b-good); }
.price-verdict--above{ background: var(--w2b-error-surface); color: var(--w2b-error); }
.price-verdict--within{ background: var(--w2b-surface-sunken); color: var(--w2b-graphite); }
.price-verdict--within b{ color: var(--w2b-ink); }

/* Map and the list of what is nearby answer the same question from two sides,
   so on a wide screen they stand next to each other: where on the left, how far
   on the right. The map holds still while the table scrolls past it. */
.plot-page__surroundings{
  display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: var(--w2b-space-4); align-items: start;
}
@media (max-width: 1140px){ .plot-page__surroundings{ grid-template-columns: 1fr; } }
.plot-page__map{ padding: var(--w2b-space-4); position: sticky; top: var(--w2b-space-3); }
@media (max-width: 1140px){ .plot-page__map{ position: static; } }

/* The location record: a small map beside the checks. The map is narrower
   than the plan above it on purpose — it says where the noise is, not where
   the house goes — and it holds still while the cards scroll past. */
.location{
  display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: var(--w2b-space-4); align-items: start;
}
@media (max-width: 1000px){ .location{ grid-template-columns: 1fr; } }
.location__map{ position: sticky; top: var(--w2b-space-3); }
@media (max-width: 1000px){ .location__map{ position: static; } }
.location__frame--no-noise :deep(.site-plan-shell){ filter: grayscale(1); opacity: .55; }
.location__no-noise{
  margin: var(--w2b-space-3); padding: var(--w2b-space-2) var(--w2b-space-3);
  background: var(--w2b-warning-surface); border-left: 4px solid var(--w2b-warning);
  border-radius: var(--w2b-radius-s); font-size: var(--w2b-text-s); line-height: 1.4;
}
.location__no-noise strong{ display: block; }
.location__layer{ display: inline-flex; align-items: center; gap: 6px; }

.key{ padding: var(--w2b-space-3); border-top: 1px solid var(--w2b-line); }
.key__head{ margin: 0 0 6px; font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.key__bands{
  display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 0; padding: 0; list-style: none;
  font-family: var(--w2b-font-mono); font-size: 11px; font-variant-numeric: tabular-nums;
}
.key__bands li{ display: flex; align-items: center; gap: 6px; }
.key__swatch{ width: 14px; height: 10px; border-radius: 2px; border: 1px solid var(--w2b-line); }

.side-pane{ display: flex; flex-direction: column; gap: var(--w2b-space-4); min-width: 0; }
.side-tabs{
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3px; padding: 3px;
  background: var(--w2b-surface-sunken); border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s);
}
.side-tabs button{
  display: flex; align-items: center; justify-content: center; gap: 5px; min-width: 0;
  padding: 9px 2px; border: 0; border-radius: var(--w2b-radius-xs); background: transparent;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: 12.5px;
  color: var(--w2b-graphite); cursor: pointer; white-space: nowrap;
}
.side-tabs button:hover{ color: var(--w2b-ink); }
.side-tabs button[aria-selected="true"]{ background: var(--w2b-surface); color: var(--w2b-ink); box-shadow: var(--w2b-shadow); }
.side-tabs button:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: 1px; }
/* The same two marks the plan uses: an outline for the plot, brass for the house. */
.side-tabs__mark{ width: 10px; height: 10px; border-radius: 2px; flex: none; }
.side-tabs__mark--plot{ border: 1.5px solid var(--w2b-map-boundary); border-radius: 1px; }
.side-tabs__mark--building{ background: var(--w2b-map-design); border: 1px solid var(--w2b-map-design-edge); }
.side-tabs__mark--neighbourhood{ background: var(--w2b-map-neighbour-main); border: 1px solid var(--w2b-map-neighbour-main-edge); }

/* The 6-m-Zone is a question, not a violation: the warning tone, never red. */
.notice--zone{ background: var(--w2b-warning-surface); color: var(--w2b-warning-text); }
.plan-zoom{
  position: absolute; right: var(--w2b-space-3); bottom: var(--w2b-space-3);
  display: flex; overflow: hidden; line-height: 1.2;
  background: var(--w2b-surface); border: 1px solid var(--w2b-line); border-radius: var(--w2b-radius-s);
  box-shadow: var(--w2b-shadow);
}
.plan-zoom button{
  border: 0; background: transparent; padding: 6px 10px; cursor: pointer;
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs); color: var(--w2b-muted);
}
.plan-zoom button + button{ border-left: 1px solid var(--w2b-line); }
.plan-zoom button[aria-pressed="true"]{ background: var(--w2b-primary); color: var(--w2b-primary-on); }
.plan-zoom button:disabled{ opacity: .45; cursor: not-allowed; }
.plan-zoom button:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: -2px; }
/* On a phone the scale bar takes the bottom left; the control moves under
   the house chip instead. */
@media (max-width: 520px){ .plan-zoom{ left: var(--w2b-space-3); right: auto; bottom: auto; top: 52px; } }

.plan-stage{ position: relative; }
.house-chip{
  position: absolute; top: var(--w2b-space-3); left: var(--w2b-space-3);
  display: flex; align-items: center; gap: var(--w2b-space-2);
  max-width: calc(100% - 2 * var(--w2b-space-3) - 64px);
  padding: 4px 4px 4px 12px; border: 1px solid var(--w2b-map-design); border-radius: var(--w2b-radius-full);
  background: var(--w2b-surface); box-shadow: var(--w2b-shadow); font-size: var(--w2b-text-s);
}
.house-chip__label{
  font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs);
  letter-spacing: .09em; text-transform: uppercase; color: var(--w2b-secondary-text);
}
.house-chip__name{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.house-chip button{
  flex: none; border: 0; border-radius: var(--w2b-radius-full); padding: 6px 10px; cursor: pointer;
  background: var(--w2b-secondary-veil); color: var(--w2b-secondary-text);
  font-family: var(--w2b-font-body); font-weight: 600; font-size: var(--w2b-text-xs);
}
.house-chip button[aria-pressed="true"]{ background: var(--w2b-secondary-light); box-shadow: inset 0 0 0 1px var(--w2b-secondary); }
.house-chip button:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: 2px; }

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
.align, .confine{ display: flex; flex-direction: column; align-items: flex-start; gap: var(--w2b-space-2); padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }

</style>
