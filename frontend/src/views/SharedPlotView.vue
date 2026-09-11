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
            <!-- Only what was actually shared. A row of dashes for a price
                 that was deliberately withheld reads as missing data rather
                 than as a decision, and it invites the reader to wonder what
                 else is broken. -->
            <dl class="value-list">
              <dt>Fläche amtlich</dt><dd>{{ area(plot.officialArea) }}</dd>
              <template v-if="hasPrice">
                <dt>Kaufpreis</dt><dd>{{ euro(plot.askingPrice) }}</dd>
                <dt>Preis je m²</dt><dd>{{ euroPerSqm(pricePerSqm) }}</dd>
              </template>
              <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(plot.bodenrichtwert) }}</dd>
              <template v-if="hasPrice">
                <dt>Gegen den Richtwert</dt><dd>{{ percent(againstReference) }}</dd>
              </template>
            </dl>
          </div>
        </section>

        <section v-if="building" class="panel">
          <div class="panel__head"><h3>Was daraufpasst</h3></div>
          <div class="panel__body">
            <dl class="value-list">
              <dt>Haustyp</dt><dd>{{ plot.houseTypeName || "eigenes Maß" }}</dd>
              <dt>Grundfläche</dt><dd>{{ metres(building.width) }} × {{ metres(building.depth) }}</dd>
            </dl>
          </div>
        </section>

        <section v-if="ways.length" class="panel">
          <div class="panel__head"><h3>Wege</h3><div class="spacer"></div><span class="chip">Fahrplan</span></div>
          <div class="panel__body">
            <dl class="value-list">
              <template v-for="way in ways" :key="way.id">
                <dt>{{ way.name }}</dt><dd>{{ duration(way.seconds) }}</dd>
              </template>
            </dl>
          </div>
        </section>
      </div>

      <section v-if="plot.note" class="panel">
        <div class="panel__head"><h3>Notiz</h3></div>
        <div class="panel__body"><p>{{ plot.note }}</p></div>
      </section>

      <!-- What this page is not, said plainly. A shared link is a snapshot of
           somebody else's working state, and reading it as an offer or as a
           current appraisal would be a mistake worth preventing. -->
      <section class="panel">
        <div class="panel__body stack">
          <p class="hint">
            Das ist eine Momentaufnahme vom {{ date(sharedAt) }}, geteilt von jemandem, der
            dieses Grundstück geprüft hat. Sie ändert sich nicht mehr, auch wenn sich am
            Grundstück etwas ändert. Der Link läuft am {{ date(expiresAt) }} ab.
            Geteilt wird nur, was die teilende Person ausgewählt hat.
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
import { area, euro, euroPerSqm, metres, percent, date, duration } from "../lib/format.js";

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
    hasPrice() { return Number.isFinite(this.plot?.askingPrice); },
    /** The fastest mode per destination, named. Both halves travel under the
     *  same switch, so either both are here or neither is. */
    ways() {
      const names = Object.fromEntries(
        (this.plot?.sharedDestinations ?? []).map(d => [d.id, d.name])
      );
      return Object.entries(this.plot?.routes ?? {})
        .map(([id, entry]) => {
          const reachable = Object.values(entry?.modes ?? {})
            .filter(m => m?.erreichbar && Number.isFinite(m.duration_s));
          if (!reachable.length) return null;
          return { id, name: names[id] ?? "Ziel", seconds: Math.min(...reachable.map(m => m.duration_s)) };
        })
        .filter(Boolean)
        .sort((a, b) => a.seconds - b.seconds);
    },
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
  methods: { area, euro, euroPerSqm, metres, percent, date, duration }
};
</script>
