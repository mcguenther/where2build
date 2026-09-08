<template>
  <div v-if="plot" class="stack surroundings-page">
    <nav class="breadcrumb no-print" aria-label="Pfad">
      <RouterLink :to="{ name: 'plots' }">Grundstücke</RouterLink>
      <span aria-hidden="true">›</span>
      <RouterLink :to="{ name: 'plot', params: { id: plot.id } }">{{ plot.name }}</RouterLink>
      <span aria-hidden="true">›</span>
      <span>Umgebung</span>
    </nav>

    <div class="page-head">
      <div>
        <p class="eyebrow">Verortung</p>
        <h1>{{ plot.name }} in seiner Umgebung</h1>
        <p class="page-head__sub">
          Der Baukörper an der Stelle, an der er geplant ist, mit so viel Karte darum herum,
          dass die Gegend wiederzuerkennen ist, und darin das, was in der Nähe liegt.
        </p>
      </div>
      <div class="spacer"></div>
      <div class="row no-print">
        <RouterLink class="btn btn--quiet" :to="{ name: 'plot', params: { id: plot.id } }">
          Zum Lageplan
        </RouterLink>
      </div>
    </div>

    <p v-if="!plot.anchor" class="notice notice--error">
      Für dieses Grundstück ist keine Koordinate hinterlegt. Ohne sie gibt es keinen Punkt,
      an dem eine Karte ausgerichtet werden könnte.
    </p>

    <template v-else>
      <section class="panel surroundings-page__map">
        <SurroundingsMap :plot="plot" :building="building" :hits="hits"
                         :destinations="destinations" :height="560" />
      </section>

      <div class="surroundings-page__lists">
        <NearbyPanel :plot="plot" auto @loaded="r => (nearbyResult = r)" />

        <section class="panel">
          <div class="panel__head">
            <h3>Eigene Ziele</h3>
            <div class="spacer"></div>
            <RouterLink class="btn btn--quiet btn--small no-print" :to="{ name: 'destinations' }">
              Ziele bearbeiten
            </RouterLink>
          </div>

          <p v-if="!destinations.length" class="surroundings-page__empty">
            Es ist kein verortetes Ziel hinterlegt. Unter „Ziele“ eine Adresse eintragen und
            nachschlagen lassen; auf dem Lageplan lassen sich die Wege dann rechnen.
          </p>
          <table v-else class="data-table">
            <tbody>
              <tr v-for="goal in destinations" :key="goal.id">
                <td>{{ goal.name }}</td>
                <td class="num">{{ goal.note || "Weg noch nicht gerechnet" }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
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
      <div class="row">
        <RouterLink class="btn" :to="{ name: 'plots' }">Zur Übersicht</RouterLink>
        <RouterLink class="btn btn--quiet" :to="{ name: 'data' }">Zu den Daten</RouterLink>
      </div>
    </div>
  </div>
</template>

<script>
import SurroundingsMap from "../components/SurroundingsMap.vue";
import NearbyPanel from "../components/NearbyPanel.vue";
import { state, plotById, placement } from "../lib/store.js";
import { coordinatesOf, fastestMode, MODES } from "../lib/routes.js";
import { duration } from "../lib/format.js";

export default {
  name: "SurroundingsView",
  components: { SurroundingsMap, NearbyPanel },
  props: {
    /** The plot's id, straight out of the URL. */
    id: { type: String, required: true }
  },
  data() {
    return { state, nearbyResult: null };
  },
  computed: {
    plot() { return plotById(this.id); },
    building() { return this.plot ? placement(this.plot) : null; },
    hits() { return this.nearbyResult?.treffer ?? []; },
    /** The destinations this user entered, each with the fastest route that was
     *  actually computed for this plot — the line to draw and the time to name. */
    destinations() {
      if (!this.plot) return [];
      return state.data.destinations
        .filter(d => Number.isFinite(d.lat) && Number.isFinite(d.lon))
        .map(d => {
          const route = this.plot.routes?.[d.id];
          const mode = fastestMode(route);
          const leg = mode ? route.modes[mode] : null;
          return {
            id: d.id,
            name: d.name,
            lat: d.lat,
            lon: d.lon,
            line: leg ? coordinatesOf(leg.geometry) : null,
            note: leg
              ? `${MODES.find(m => m.mode === mode)?.name ?? mode} · ${duration(leg.duration_s)}`
              : ""
          };
        });
    }
  }
};
</script>

<style scoped>
.surroundings-page__map{ padding: var(--w2b-space-4); }
.surroundings-page__lists{
  display: grid; gap: var(--w2b-space-4);
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  align-items: start;
}
.surroundings-page__empty{
  padding: var(--w2b-space-4); color: var(--w2b-muted); font-size: var(--w2b-text-s);
}
</style>
