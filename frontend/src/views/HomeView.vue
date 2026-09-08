<template>
  <div class="home">
    <section class="hero" :class="{ 'hero--slim': hasPlots }">
      <!-- The ground: a cadastral fabric carrying no labels at all. It shows
           what this is about without wanting to be read, which is why it fades
           out towards the middle, where the field stands. Decorative, so it is
           hidden from anything that reads the page aloud. -->
      <div class="hero__art" aria-hidden="true">
        <svg viewBox="0 0 1440 820" preserveAspectRatio="xMidYMid slice">
          <g opacity=".9">
        <polygon points="-342.5,587.1 1746.0,367.6 1753.1,435.2 -335.4,654.7" fill="var(--w2b-map-street-surface)"></polygon>
        <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
        <polygon points="-322.6,585.0 -173.4,569.3 -203.2,285.9 -352.4,301.6"></polygon>
        <polygon points="-173.4,569.3 -77.9,559.3 -104.0,310.7 -199.5,320.7"></polygon>
        <polygon points="-77.9,559.3 25.5,548.4 -0.6,299.8 -104.0,310.7"></polygon>
        <polygon points="25.5,548.4 174.7,532.7 148.6,284.1 -0.6,299.8"></polygon>
        <polygon points="341.8,515.2 445.2,504.3 419.1,255.7 315.6,266.5"></polygon>
        <polygon points="445.2,504.3 540.7,494.3 509.3,195.9 413.8,205.9"></polygon>
        <polygon points="540.7,494.3 644.1,483.4 614.3,200.0 510.9,210.8"></polygon>
        <polygon points="644.1,483.4 747.5,472.5 716.2,174.2 612.7,185.0"></polygon>
        <polygon points="747.5,472.5 851.0,461.7 824.8,213.0 721.4,223.9"></polygon>
        <polygon points="851.0,461.7 978.3,448.3 952.1,199.6 824.8,213.0"></polygon>
        <polygon points="978.3,448.3 1145.3,430.7 1114.0,132.4 946.9,149.9"></polygon>
        <polygon points="1145.3,430.7 1248.8,419.8 1219.0,136.4 1115.6,147.3"></polygon>
        <polygon points="1248.8,419.8 1352.2,409.0 1322.4,125.5 1219.0,136.4"></polygon>
        <polygon points="1352.2,409.0 1501.4,393.3 1470.0,94.9 1320.8,110.6"></polygon>
        <polygon points="1501.4,393.3 1628.7,379.9 1602.6,131.3 1475.3,144.7"></polygon>
        <polygon points="1628.7,379.9 1795.8,362.4 1771.7,133.6 1604.6,151.2"></polygon>
        <polygon points="-375.1,658.9 -233.9,644.1 -214.0,833.0 -355.3,847.9"></polygon>
        <polygon points="-233.9,644.1 -138.4,634.0 -116.5,842.9 -212.0,852.9"></polygon>
        <polygon points="-138.4,634.0 2.8,619.2 22.6,808.1 -118.6,823.0"></polygon>
        <polygon points="2.8,619.2 98.3,609.1 124.4,857.8 28.9,867.8"></polygon>
        <polygon points="98.3,609.1 229.5,595.3 249.4,784.3 118.1,798.1"></polygon>
        <polygon points="229.5,595.3 360.8,581.5 380.7,770.5 249.4,784.3"></polygon>
        <polygon points="360.8,581.5 492.1,567.8 512.0,756.7 380.7,770.5"></polygon>
        <polygon points="492.1,567.8 587.6,557.7 613.7,806.3 518.2,816.4"></polygon>
        <polygon points="587.6,557.7 728.8,542.9 754.9,791.5 613.7,806.3"></polygon>
        <polygon points="728.8,542.9 885.9,526.4 912.1,775.0 754.9,791.5"></polygon>
        <polygon points="885.9,526.4 1027.1,511.5 1053.3,760.1 912.1,775.0"></polygon>
        <polygon points="1027.1,511.5 1184.3,495.0 1210.4,743.6 1053.3,760.1"></polygon>
        <polygon points="1184.3,495.0 1279.8,485.0 1301.7,693.8 1206.2,703.8"></polygon>
        <polygon points="1279.8,485.0 1375.2,474.9 1397.2,683.8 1301.7,693.8"></polygon>
        <polygon points="1375.2,474.9 1516.4,460.1 1542.6,708.7 1401.4,723.6"></polygon>
        <polygon points="1516.4,460.1 1657.7,445.2 1683.8,693.9 1542.6,708.7"></polygon>
        <polygon points="1657.7,445.2 1814.8,428.7 1834.7,617.7 1677.5,634.2"></polygon>
        </g>
        <polygon points="174.7,532.7 341.8,515.2 312.0,231.7 144.9,249.3" fill="var(--w2b-map-surface)"></polygon>
        <path d="M174.7,532.7 L341.8,515.2 L312.0,231.7 L144.9,249.3 Z M197.8,504.2 L313.2,492.0 L288.8,260.3 L173.5,272.4 Z" fill="var(--w2b-map-setback)" fill-rule="evenodd"></path>
        <polygon points="174.7,532.7 341.8,515.2 312.0,231.7 144.9,249.3" fill="none" stroke="var(--w2b-map-halo)" stroke-width="7" stroke-linejoin="round"></polygon>
        <polygon points="174.7,532.7 341.8,515.2 312.0,231.7 144.9,249.3" fill="none" stroke="var(--w2b-map-boundary)" stroke-width="2.4" stroke-linejoin="round"></polygon>
        <polygon points="197.8,504.2 313.2,492.0 288.8,260.3 173.5,272.4" fill="none" stroke="var(--w2b-map-envelope)" stroke-width="1.6" stroke-dasharray="8 6"></polygon>
        <polygon points="207.6,462.9 299.1,453.3 288.4,351.9 196.9,361.5" fill="var(--w2b-map-design)" fill-opacity=".85" stroke="var(--w2b-map-design-edge)" stroke-width="1.8" stroke-linejoin="round"></polygon>
          </g>
        </svg>
      </div>

      <div class="hero__inner">
        <p class="eyebrow hero__eyebrow">{{ hasPlots ? "Willkommen zurück" : "Sachsen · Liegenschaftskataster, Bodenrichtwert, Fahrplan" }}</p>
        <h1 v-if="hasPlots">Woran heute weiterarbeiten?</h1>
        <h1 v-else>Aus einer Anzeige wird ein <em>geprüftes Grundstück</em>.</h1>

        <p class="hero__sub" v-if="hasPlots">
          Ein neuer Fall beginnt hier — unten steht, was zuletzt dazukam.
        </p>
        <p class="hero__sub" v-else>
          Link einfügen — gesucht wird das Flurstück im Liegenschaftskataster, gemessen wird
          amtlich, der Preis geht gegen den Bodenrichtwert, und das Haus stellt sich in die
          Abstandsflächen.
        </p>

        <QueryBox class="hero__query panel" :busy="busy" @resolve="startResolve" @read="startRead" />

        <p v-if="!backendUp" class="notice notice--error hero__notice" role="alert">
          Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
          Seiten auslesen — gespeicherte Grundstücke bleiben aber sichtbar.
        </p>

        <div v-if="!hasPlots" class="trust">
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
            <b>Amtliche Flurstücke</b> aus ALKIS
          </span>
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 3v18M8 7h6.5a2.5 2.5 0 0 1 0 5H9a2.5 2.5 0 0 0 0 5h7" />
            </svg>
            <b>Bodenrichtwert</b> zum Stichtag
          </span>
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" />
            </svg>
            <b>Wege nach Fahrplan</b>, nicht Luftlinie
          </span>
        </div>
      </div>
    </section>

    <!-- With a stand: what came in last, and the way to all of it. -->
    <section v-if="hasPlots" class="stack">
      <div class="section-head">
        <h2>Weitermachen</h2>
        <span class="hint">zuletzt hinzugefügt</span>
        <div class="spacer"></div>
        <RouterLink :to="{ name: 'plots' }">{{ allLabel }}</RouterLink>
      </div>
      <div class="card-grid">
        <PlotCard v-for="plot in recent" :key="plot.id" :plot="plot" :selectable="false"
                  @open="open(plot.id)" @remove="remove(plot)" />
      </div>
    </section>

    <!-- Without one: what the thing does, for whoever has not seen it. -->
    <section v-else class="panel">
      <div class="steps">
        <div class="steps__item">
          <p class="eyebrow">Erstens</p>
          <h4>Das Flurstück finden</h4>
          <p>Aus dem, was die Anzeige hergibt: Ortsteil, Fläche, Straße, ein Bild vom
            Katasterauszug. Jeder Schritt steht im Protokoll und lässt sich anfechten.</p>
        </div>
        <div class="steps__item">
          <p class="eyebrow">Zweitens</p>
          <h4>Prüfen, was darauf passt</h4>
          <p>Amtliche Fläche gegen Bodenrichtwert, Abstandsflächen nach § 6 SächsBO,
            Lärm, Hochwasser, Radon — und ein Haustyp im Baufenster.</p>
        </div>
        <div class="steps__item">
          <p class="eyebrow">Drittens</p>
          <h4>Wege messen</h4>
          <p>Zu Arbeit, Schule, Bahnhof — mit dem Fahrplan gerechnet, und die Karte
            druckt sich mit aus.</p>
        </div>
      </div>
      <p class="home__storage">
        Alles bleibt im Speicher dieses Browsers — zum Mitnehmen gibt es unter „Daten“
        den Austausch als JSON.
      </p>
    </section>
  </div>
</template>

<script>
/**
 * The way in.
 *
 * One field for everything, and underneath it either what is already here or
 * what this is for. The page resolves nothing itself: the wizard owns every
 * step after the input, so the input is handed over (`lib/handoff.js`) and the
 * wizard picks it up in its first stage.
 */
import QueryBox from "../components/QueryBox.vue";
import PlotCard from "../components/PlotCard.vue";
import { state, removePlot } from "../lib/store.js";
import { backendHealth } from "../lib/api.js";
import { handOff } from "../lib/handoff.js";
import { wizardStage } from "../router/stages.js";

/** Enough to pick up where one left off; the list is one click away. */
const RECENT = 3;

export default {
  name: "HomeView",
  components: { QueryBox, PlotCard },
  data() {
    return { state, backendUp: true, busy: false };
  },
  computed: {
    hasPlots() { return state.data.plots.length > 0; },
    plotCount() { return state.data.plots.length; },
    allLabel() {
      return this.plotCount === 1 ? "Zum Grundstück →" : `Alle ${this.plotCount} Grundstücke →`;
    },
    /** Newest first. There is no "changed at" in the document — `readAt` is
     *  when the parcel was read from the cadastre — so the heading says
     *  "hinzugefügt" and not something the data cannot support. */
    recent() {
      return [...state.data.plots]
        .sort((a, b) => String(b.readAt ?? "").localeCompare(String(a.readAt ?? "")))
        .slice(0, RECENT);
    }
  },
  async created() {
    this.backendUp = Boolean(await backendHealth());
  },
  methods: {
    open(id) { this.$router.push({ name: "plot", params: { id } }); },
    remove(plot) {
      const confirmed = window.confirm(`„${plot.name}“ aus der Liste entfernen? Der Stand dieses Grundstücks geht verloren.`);
      if (confirmed) removePlot(plot.id);
    },
    startResolve(payload) {
      handOff({ resolve: payload });
      this.$router.push(wizardStage(0));
    },
    startRead(payload) {
      handOff({ read: payload });
      this.$router.push(wizardStage(0));
    }
  }
};
</script>

<style scoped>
.home{ display: flex; flex-direction: column; gap: var(--w2b-space-6); }

/* The reception. It bleeds to both edges, so it steps out of the container it
   sits in and brings its own. */
.hero{
  position: relative; overflow: hidden;
  margin: calc(-1 * var(--w2b-space-5)) calc(-1 * var(--w2b-space-5)) 0;
  padding: var(--w2b-space-6) var(--w2b-space-5) var(--w2b-space-7);
  border-bottom: 1px solid var(--w2b-line);
  background: var(--w2b-surface);
}
.hero--slim{ padding-top: var(--w2b-space-5); padding-bottom: var(--w2b-space-5); }
.hero--slim h1{ font-size: clamp(26px, 3.2vw, 34px); }
.hero--slim .hero__sub{ font-size: var(--w2b-text-m); }
.hero--slim .hero__query{ margin-top: var(--w2b-space-5); }
/* The cards below carry the picture; here the fabric is only texture. */
.hero--slim .hero__art{ opacity: .34; }

.hero__art{ position: absolute; inset: 0; pointer-events: none; }
.hero__art svg{ width: 100%; height: 100%; display: block; }
/* Towards the middle the fabric gives way to paper: a drawing behind a field
   is a background, and a background must not be read. */
.hero__art::after{
  content: ""; position: absolute; inset: 0;
  background:
    radial-gradient(34% 44% at 50% 40%, var(--w2b-surface) 0 42%, rgba(250,247,241,.84) 72%, transparent 100%),
    linear-gradient(180deg, transparent 68%, var(--w2b-paper));
}
.hero__inner{
  position: relative; display: flex; flex-direction: column; align-items: center;
  text-align: center; max-width: 860px; margin: 0 auto;
}
.hero__eyebrow{ margin-bottom: var(--w2b-space-3); }
.hero h1{ margin-bottom: var(--w2b-space-3); max-width: 20ch; }
.hero h1 em{ font-style: normal; color: var(--w2b-primary); }
.hero__sub{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); max-width: 56ch; text-wrap: balance; }
.hero__query{ width: 100%; max-width: 760px; margin-top: var(--w2b-space-6); padding: var(--w2b-space-4); text-align: left; }
.hero__notice{ margin-top: var(--w2b-space-4); text-align: left; }

.trust{
  display: flex; gap: var(--w2b-space-5); flex-wrap: wrap; justify-content: center;
  margin-top: var(--w2b-space-5); font-size: var(--w2b-text-s); color: var(--w2b-muted);
}
.trust span{ display: inline-flex; align-items: center; gap: 8px; }
.trust svg{ flex: none; color: var(--w2b-primary); }
.trust b{ font-family: var(--w2b-font-display); font-weight: 600; color: var(--w2b-graphite); }

.section-head{ display: flex; align-items: baseline; gap: var(--w2b-space-3); flex-wrap: wrap; }
.section-head h2{ font-size: var(--w2b-text-xl); font-weight: 600; }
.section-head a{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-s); text-decoration: none; }
.section-head a:hover{ text-decoration: underline; }

.steps{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--w2b-space-5); padding: var(--w2b-space-5); }
.steps__item h4{ margin-bottom: var(--w2b-space-1); }
.steps__item p{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.steps__item .eyebrow{ margin-bottom: var(--w2b-space-2); }
.home__storage{
  padding: var(--w2b-space-3) var(--w2b-space-5);
  border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-s); color: var(--w2b-muted);
}

@media (max-width: 560px){
  .hero{ margin-left: calc(-1 * var(--w2b-space-4)); margin-right: calc(-1 * var(--w2b-space-4)); padding: var(--w2b-space-5) var(--w2b-space-4) var(--w2b-space-6); }
  .hero__sub{ font-size: var(--w2b-text-m); }
}
</style>
