<template>
  <div class="stack">
    <p v-if="busy" class="hint">Wird geladen …</p>

    <section v-else-if="failure" class="panel">
      <div class="panel__body stack">
        <h1>Dieser Link führt nirgendwohin</h1>
        <p>{{ failure }}</p>
        <p>
          <RouterLink class="btn" :to="{ name: 'home' }">Ein eigenes Grundstück prüfen</RouterLink>
        </p>
      </div>
    </section>

    <template v-else-if="plot">
      <div class="page-head">
        <div>
          <p class="eyebrow">Geteiltes Grundstück · Stand {{ date(sharedAt) }}</p>
          <h1>{{ plot.name }}</h1>
          <p class="page-head__sub">
            {{ plot.gemarkung }}<template v-if="parcels"> · Flurstück {{ parcels }}</template>
            <template v-if="plot.municipality"> · {{ plot.municipality }}</template>
          </p>
        </div>
      </div>

      <section class="panel">
        <div class="panel__body">
          <SitePlan :plot="plot" :building="building" backdrop="map" :height="520" />
        </div>
      </section>

      <div class="two-columns">
        <section class="panel">
          <div class="panel__head"><h3>Das Grundstück</h3><div class="spacer"></div><span class="chip">ALKIS</span></div>
          <div class="panel__body">
            <dl class="value-list">
              <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
              <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
              <dt>Preis je m²</dt><dd>{{ euroPerSqm(pricePerSqm) }}</dd>
              <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }}</dd>
              <dt>Gegen den Richtwert</dt><dd>{{ percent(againstReference) }}</dd>
            </dl>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head"><h3>Was daraufpasst</h3></div>
          <div class="panel__body">
            <dl v-if="building" class="value-list">
              <dt>Haustyp</dt><dd>{{ plot.houseTypeName || "eigenes Maß" }}</dd>
              <dt>Grundfläche</dt><dd>{{ metres(building.width) }} × {{ metres(building.depth) }}</dd>
            </dl>
            <p v-else class="missing">
              In dieser Momentaufnahme war noch kein Haus gestellt.
            </p>
          </div>
        </section>
      </div>

      <!-- What this page is not, said plainly. A shared link is a snapshot of
           somebody else's working state, and reading it as an offer or as a
           current appraisal would be a mistake worth preventing. -->
      <section class="panel">
        <div class="panel__body stack">
          <p class="hint">
            Das ist eine Momentaufnahme vom {{ date(sharedAt) }}, geteilt von jemandem, der
            dieses Grundstück geprüft hat. Sie ändert sich nicht mehr, auch wenn sich am
            Grundstück etwas ändert. Der Link läuft am {{ date(expiresAt) }} ab.
            Persönliche Notizen und Wegezeiten sind nicht enthalten.
          </p>
          <p>
            <RouterLink class="btn" :to="{ name: 'home' }">Eigenes Grundstück prüfen</RouterLink>
          </p>
        </div>
      </section>
    </template>
  </div>
</template>

<script>
/**
 * A plot somebody shared, for whoever opens the link.
 *
 * Nothing here touches the store: the document comes from the server and
 * belongs to somebody else, and writing it into this browser's state would put
 * a stranger's plot into the reader's own list.
 *
 * It also asks no service anything. Everything on the page is in the snapshot,
 * which keeps a link that gets passed around from spending somebody's request
 * budget on the cadastre — the map tiles are the one exception, and they have
 * a budget of their own.
 */
import SitePlan from "../components/SitePlan.vue";
import { sharedPlot } from "../lib/api.js";
import { area, euro, euroPerSqm, metres, percent, date } from "../lib/format.js";

export default {
  name: "SharedPlotView",
  components: { SitePlan },
  props: {
    token: { type: String, required: true },
    /** The readable part of the link. Never read; see the route. */
    slug: { type: [String, Array], default: "" }
  },
  data() {
    return { plot: null, sharedAt: null, expiresAt: null, busy: true, failure: "" };
  },
  computed: {
    parcels() {
      return Array.isArray(this.plot?.flurstuecke) ? this.plot.flurstuecke.join(" · ") : "";
    },
    /** Resolved when the link was made: the house type lives in another
     *  document, which a snapshot of one plot cannot reach. */
    building() { return this.plot?.placedBuilding || null; },
    pricePerSqm() {
      const { askingPrice, officialArea } = this.plot ?? {};
      // Never computed from a missing input: that is where "0,00 €" came from.
      return Number.isFinite(askingPrice) && officialArea > 0 ? askingPrice / officialArea : null;
    },
    againstReference() {
      const reference = this.plot?.bodenrichtwert;
      const price = this.pricePerSqm;
      return Number.isFinite(reference) && reference > 0 && Number.isFinite(price)
        ? (price / reference - 1) * 100
        : null;
    }
  },
  async created() {
    try {
      const answer = await sharedPlot(this.token);
      this.plot = answer.dokument;
      this.sharedAt = answer.angelegt;
      this.expiresAt = answer.laeuft_ab;
    } catch (error) {
      this.failure = error.message;
    } finally {
      this.busy = false;
    }
  },
  methods: { area, euro, euroPerSqm, metres, percent, date }
};
</script>
