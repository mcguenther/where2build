<template>
  <div class="home">
    <section class="hero" :class="{ 'hero--slim': hasPlots }">
      <!-- The ground: a cadastral fabric carrying no labels at all. It shows
           what this is about without wanting to be read, which is why it fades
           out towards the middle, where the field stands. Decorative, so it is
           hidden from anything that reads the page aloud. -->
      <div class="hero__art" aria-hidden="true">
        <svg viewBox="0 0 1440 1200" preserveAspectRatio="xMidYMin slice">
          <g opacity=".9">
            <polygon points="-402.1,463.4 1845.5,227.1 1852.6,294.8 -395.0,531.0" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-402.1,463.4 -306.7,453.3 -338.0,155.0 -433.5,165.0"></polygon>
            <polygon points="-306.7,453.3 -211.2,443.3 -241.0,159.9 -336.4,169.9"></polygon>
            <polygon points="-211.2,443.3 -83.9,429.9 -115.2,131.6 -242.5,144.9"></polygon>
            <polygon points="-83.9,429.9 33.5,417.6 3.7,134.1 -113.7,146.5"></polygon>
            <polygon points="33.5,417.6 136.9,406.7 105.5,108.4 2.1,119.2"></polygon>
            <polygon points="286.1,391.0 389.5,380.2 363.4,131.5 259.9,142.4"></polygon>
            <polygon points="389.5,380.2 556.6,362.6 525.2,64.2 358.2,81.8"></polygon>
            <polygon points="556.6,362.6 652.1,352.6 622.3,69.1 526.8,79.2"></polygon>
            <polygon points="652.1,352.6 819.1,335.0 793.0,86.4 625.9,103.9"></polygon>
            <polygon points="819.1,335.0 986.2,317.4 960.1,68.8 793.0,86.4"></polygon>
            <polygon points="986.2,317.4 1089.7,306.6 1063.5,57.9 960.1,68.8"></polygon>
            <polygon points="1089.7,306.6 1217.0,293.2 1187.2,9.8 1059.9,23.1"></polygon>
            <polygon points="1217.0,293.2 1384.0,275.6 1357.9,27.0 1190.8,44.6"></polygon>
            <polygon points="1384.0,275.6 1479.5,265.6 1455.5,36.9 1360.0,46.9"></polygon>
            <polygon points="1479.5,265.6 1575.0,255.6 1545.2,-27.9 1449.7,-17.8"></polygon>
            <polygon points="1575.0,255.6 1742.1,238.0 1712.3,-45.4 1545.2,-27.9"></polygon>
            <polygon points="1742.1,238.0 1859.4,225.7 1835.4,-3.1 1718.0,9.3"></polygon>
            <polygon points="-395.0,531.0 -283.6,519.3 -261.7,728.1 -373.1,739.8"></polygon>
            <polygon points="-283.6,519.3 -152.4,505.5 -126.2,754.1 -257.5,767.9"></polygon>
            <polygon points="-152.4,505.5 4.8,489.0 30.9,737.6 -126.2,754.1"></polygon>
            <polygon points="4.8,489.0 146.0,474.1 167.9,683.0 26.7,697.8"></polygon>
            <polygon points="146.0,474.1 303.1,457.6 329.3,706.2 172.1,722.8"></polygon>
            <polygon points="303.1,457.6 398.6,447.6 418.5,636.5 323.0,646.6"></polygon>
            <polygon points="398.6,447.6 555.7,431.1 577.7,639.9 420.6,656.4"></polygon>
            <polygon points="555.7,431.1 687.0,417.3 706.9,606.2 575.6,620.0"></polygon>
            <polygon points="687.0,417.3 818.3,403.5 844.4,652.1 713.2,665.9"></polygon>
            <polygon points="818.3,403.5 949.6,389.7 975.7,638.3 844.4,652.1"></polygon>
            <polygon points="949.6,389.7 1061.0,378.0 1082.9,586.8 971.5,598.5"></polygon>
            <polygon points="1061.0,378.0 1192.2,364.2 1212.1,553.1 1080.8,566.9"></polygon>
            <polygon points="1192.2,364.2 1323.5,350.4 1345.5,559.2 1214.2,573.0"></polygon>
            <polygon points="1323.5,350.4 1419.0,340.3 1440.9,549.2 1345.5,559.2"></polygon>
            <polygon points="1419.0,340.3 1530.4,328.6 1556.5,577.3 1445.1,589.0"></polygon>
            <polygon points="1530.4,328.6 1641.8,316.9 1667.9,565.5 1556.5,577.3"></polygon>
            <polygon points="1641.8,316.9 1773.0,303.1 1792.9,492.1 1661.6,505.9"></polygon>
            <polygon points="1773.0,303.1 1868.5,293.1 1888.4,482.0 1792.9,492.1"></polygon>
            </g>
            <polygon points="-402.1,1003.4 1845.5,767.1 1852.6,834.8 -395.0,1071.0" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-402.1,1003.4 -253.0,987.7 -277.0,758.9 -426.2,774.6"></polygon>
            <polygon points="-253.0,987.7 -149.5,976.8 -173.6,748.1 -277.0,758.9"></polygon>
            <polygon points="-149.5,976.8 -0.3,961.1 -26.5,712.5 -175.7,728.2"></polygon>
            <polygon points="-0.3,961.1 95.1,951.1 69.0,702.5 -26.5,712.5"></polygon>
            <polygon points="95.1,951.1 222.4,937.7 192.6,654.3 65.3,667.7"></polygon>
            <polygon points="222.4,937.7 339.8,925.4 313.7,676.8 196.3,689.1"></polygon>
            <polygon points="339.8,925.4 443.2,914.5 417.1,665.9 313.7,676.8"></polygon>
            <polygon points="443.2,914.5 538.7,904.5 507.3,606.1 411.9,616.2"></polygon>
            <polygon points="538.7,904.5 666.0,891.1 636.2,607.7 508.9,621.0"></polygon>
            <polygon points="666.0,891.1 761.5,881.1 731.7,597.6 636.2,607.7"></polygon>
            <polygon points="761.5,881.1 878.8,868.7 849.0,585.3 731.7,597.6"></polygon>
            <polygon points="878.8,868.7 974.3,858.7 942.9,560.3 847.5,570.4"></polygon>
            <polygon points="974.3,858.7 1077.7,847.8 1046.4,549.5 942.9,560.3"></polygon>
            <polygon points="1077.7,847.8 1173.2,837.8 1143.4,554.4 1047.9,564.4"></polygon>
            <polygon points="1173.2,837.8 1276.6,826.9 1252.6,598.2 1149.2,609.1"></polygon>
            <polygon points="1276.6,826.9 1443.7,809.4 1419.7,580.6 1252.6,598.2"></polygon>
            <polygon points="1443.7,809.4 1547.1,798.5 1517.3,515.0 1413.9,525.9"></polygon>
            <polygon points="1547.1,798.5 1674.4,785.1 1643.1,486.8 1515.8,500.1"></polygon>
            <polygon points="1674.4,785.1 1841.5,767.5 1815.4,518.9 1648.3,536.5"></polygon>
            <polygon points="1841.5,767.5 1944.9,756.7 1915.2,473.2 1811.7,484.1"></polygon>
            <polygon points="-395.0,1071.0 -299.5,1061.0 -273.4,1309.6 -368.9,1319.6"></polygon>
            <polygon points="-299.5,1061.0 -142.4,1044.4 -120.5,1253.3 -277.6,1269.8"></polygon>
            <polygon points="-142.4,1044.4 -1.2,1029.6 24.9,1278.2 -116.3,1293.1"></polygon>
            <polygon points="-1.2,1029.6 155.9,1013.1 182.1,1261.7 24.9,1278.2"></polygon>
            <polygon points="155.9,1013.1 287.2,999.3 309.2,1208.1 177.9,1221.9"></polygon>
            <polygon points="287.2,999.3 418.5,985.5 440.4,1194.3 309.2,1208.1"></polygon>
            <polygon points="418.5,985.5 559.7,970.6 579.6,1159.6 438.4,1174.4"></polygon>
            <polygon points="559.7,970.6 655.2,960.6 677.1,1169.5 581.7,1179.5"></polygon>
            <polygon points="655.2,960.6 796.4,945.8 822.5,1194.4 681.3,1209.2"></polygon>
            <polygon points="796.4,945.8 953.5,929.3 973.4,1118.2 816.3,1134.7"></polygon>
            <polygon points="953.5,929.3 1064.9,917.5 1086.9,1126.4 975.5,1138.1"></polygon>
            <polygon points="1064.9,917.5 1206.2,902.7 1232.3,1151.3 1091.1,1166.2"></polygon>
            <polygon points="1206.2,902.7 1347.4,887.9 1369.3,1096.7 1228.1,1111.5"></polygon>
            <polygon points="1347.4,887.9 1458.8,876.2 1480.7,1085.0 1369.3,1096.7"></polygon>
            <polygon points="1458.8,876.2 1554.2,866.1 1580.4,1114.7 1484.9,1124.8"></polygon>
            <polygon points="1554.2,866.1 1649.7,856.1 1669.6,1045.0 1574.1,1055.1"></polygon>
            <polygon points="1649.7,856.1 1745.2,846.0 1765.0,1035.0 1669.6,1045.0"></polygon>
            <polygon points="1745.2,846.0 1840.7,836.0 1862.6,1044.9 1767.1,1054.9"></polygon>
            <polygon points="1840.7,836.0 1981.9,821.2 2003.8,1030.0 1862.6,1044.9"></polygon>
            </g>
            <polygon points="136.9,406.7 286.1,391.0 256.3,107.6 107.1,123.3" fill="var(--w2b-map-surface)"></polygon>
            <path d="M136.9,406.7 L286.1,391.0 L256.3,107.6 L107.1,123.3 Z M160.0,378.1 L257.5,367.9 L233.1,136.2 L135.7,146.4 Z" fill="var(--w2b-map-setback)" fill-rule="evenodd"></path>
            <polygon points="136.9,406.7 286.1,391.0 256.3,107.6 107.1,123.3" fill="none" stroke="var(--w2b-map-halo)" stroke-width="7" stroke-linejoin="round"></polygon>
            <polygon points="136.9,406.7 286.1,391.0 256.3,107.6 107.1,123.3" fill="none" stroke="var(--w2b-map-boundary)" stroke-width="2.4" stroke-linejoin="round"></polygon>
            <polygon points="160.0,378.1 257.5,367.9 233.1,136.2 135.7,146.4" fill="none" stroke="var(--w2b-map-envelope)" stroke-width="1.6" stroke-dasharray="8 6"></polygon>
            <polygon points="169.8,336.9 243.4,329.2 232.7,227.7 159.1,235.4" fill="var(--w2b-map-design)" fill-opacity=".85" stroke="var(--w2b-map-design-edge)" stroke-width="1.8" stroke-linejoin="round"></polygon>

            <!-- A way out, drawn the way `RouteCards` draws a real one: the
                 mode's own colour over the halo every line here carries. It
                 starts at the middle of the building's lower edge -- where a
                 drive leaves a house -- meets the street where the plot fronts
                 it, and follows the centre line east off the page. Starting at
                 the centroid instead drew the line out through the roof.
                 No marker at either end. The far end would claim a destination
                 the start page knows nothing about, and running off the frame
                 survives every viewport where a fixed point does not. The
                 square that marks a start on a route card read as a warning
                 here: it is drawn in the violation colour, and in a backdrop
                 there is no legend behind it to say otherwise. -->
            <g fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M206.6,333 C208,354 205,378 206,398 Q209,428 240,430 L1560,291"
                    stroke="var(--w2b-map-halo)" stroke-width="13" opacity=".85"></path>
              <path d="M206.6,333 C208,354 205,378 206,398 Q209,428 240,430 L1560,291"
                    stroke="var(--w2b-primary)" stroke-width="4.6"></path>
            </g>
          </g>
        </svg>
      </div>

      <div class="hero__inner">
        <p class="eyebrow hero__eyebrow">{{ greeting }}</p>
        <h1 v-if="hasPlots">Woran heute weiterarbeiten?</h1>
        <h1 v-else>Aus einer Anzeige wird ein <em>geprüftes Grundstück</em>.</h1>

        <p class="hero__sub" v-if="hasPlots">
          Ein neuer Fall beginnt hier. Unten steht, was zuletzt dazukam.
        </p>
        <p class="hero__sub" v-else>
          Link einfügen: gesucht wird das Flurstück im Liegenschaftskataster, gemessen wird
          amtlich, der Preis geht gegen den Bodenrichtwert, und das Haus stellt sich in die
          Abstandsflächen.
        </p>

        <QueryBox class="hero__query panel" :busy="busy" @resolve="startResolve" @read="startRead" />

        <p v-if="signInFailed" class="notice hero__notice" role="alert">
          Die Anmeldung kam nicht zustande. Bitte noch einmal versuchen; ohne Konto lässt sich
          hier ohnehin weiterarbeiten.
        </p>

        <p v-if="!backendUp" class="notice notice--error hero__notice" role="alert">
          Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
          Seiten auslesen. Gespeicherte Grundstücke bleiben sichtbar.
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

        <!-- The way into an account, said out loud. The header carries the
             button, but somebody arriving at an empty app looks at the middle
             of the page, not at the top right corner -- and where no provider
             is configured the header shows nothing at all, which read as the
             sign-in being broken rather than absent. Both states say what
             holds. -->
        <p v-if="!state.account.angemeldet" class="hero__account">
          <template v-if="state.account.eingerichtet">
            <a :href="signInHref">Anmelden oder Konto anlegen</a> — dann liegt der Stand
            auf jedem Rechner. Ohne Konto bleibt er in diesem Browser, und das reicht
            für alles hier.
          </template>
          <template v-else>
            Ohne Konto: der Stand bleibt in diesem Browser, und das reicht für alles
            hier. Eine Anmeldung ist in diesem Betrieb nicht eingerichtet.
          </template>
        </p>
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
            Lärm, Hochwasser, Radon. Dazu ein Haustyp im Baufenster.</p>
        </div>
        <div class="steps__item">
          <p class="eyebrow">Drittens</p>
          <h4>Wege messen</h4>
          <p>Zu Arbeit, Schule, Bahnhof, mit dem Fahrplan gerechnet. Die Karte
            druckt sich mit aus.</p>
        </div>
      </div>
      <!-- „Daten“ is a link and not a word, because in the fresh state the
           header carries no sections: naming a place somebody cannot reach
           from here would make this sentence a dead end. -->
      <p class="home__storage">
        {{ storageNote }}
        Zum Mitnehmen gibt es <RouterLink :to="{ name: 'data' }">unter „Daten“</RouterLink>
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
import { backendHealth, signInUrl } from "../lib/api.js";
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
    /** Named where the provider gave a name, and never claiming a return for
     *  someone who has not been here before. */
    greeting() {
      if (!this.hasPlots) return "Sachsen · Liegenschaftskataster, Bodenrichtwert, Fahrplan";
      const name = state.account.angemeldet ? state.account.name : null;
      return name ? `Willkommen zurück, ${name}` : "Willkommen zurück";
    },
    /** The backend sends the browser back with this when a sign-in broke off.
     *  It carries no detail, and none belongs in a URL. */
    signInFailed() { return this.$route.query.anmeldung === "fehlgeschlagen"; },
    /** Signing in comes back to this page. */
    signInHref() { return signInUrl(this.$route.fullPath); },
    /** Where the stand actually lies. This sentence claimed the server store
     *  was "not built yet" long after it shipped, which is the kind of stale
     *  copy that makes a working feature look missing. It reads the state
     *  instead of asserting one. */
    storageNote() {
      return state.sync.active
        ? "Der Stand liegt in diesem Browser und im Konto, und wird dort gesichert, sobald er sich ändert."
        : "Alles bleibt im Speicher dieses Browsers.";
    },
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
  display: flex; align-items: center;
  margin: calc(-1 * var(--w2b-space-5)) calc(-1 * var(--w2b-space-5)) 0;
  padding: var(--w2b-space-8) var(--w2b-space-5);
  border-bottom: 1px solid var(--w2b-line);
  background: var(--w2b-surface);
  /* The reception is the page for somebody arriving, so it gets the screen
     rather than the top of it: the drawing needs room to read as a place, and
     the field needs air around it to look like the one thing to do. Measured
     against the previous fixed padding, this is about a third taller. The
     viewport share is capped so a tall desktop window does not turn it into a
     slide nobody scrolls past. */
  min-height: clamp(600px, 82vh, 940px);
}
/* With a stand, the reception steps aside for the cards below it: the page is
   then about what is already here, not about the invitation. */
.hero--slim{ min-height: 0; padding-top: var(--w2b-space-5); padding-bottom: var(--w2b-space-5); }
.hero--slim h1{ font-size: clamp(26px, 3.2vw, 34px); }
.hero--slim .hero__sub{ font-size: var(--w2b-text-m); }
.hero--slim .hero__query{ margin-top: var(--w2b-space-5); }
/* The cards below carry the picture; here the fabric is only texture. */
.hero--slim .hero__art{ opacity: .34; }

.hero__art{ position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
/* Fixed box, anchored at the top: the suggestion list makes the reception
   taller, and a ground that rescales with it reads as slipped. Tall enough
   that growing never reaches its lower edge, so nothing looks cut off either. */
.hero__art svg{ display: block; width: 100%; height: max(100%, 1300px); }
/* Towards the middle the fabric gives way to paper: a drawing behind a field
   is a background, and a background must not be read. */
.hero__art::after{
  content: ""; position: absolute; inset: 0;
  background:
    radial-gradient(34% 42% at 50% 50%,
      var(--w2b-surface) 0 42%,
      color-mix(in srgb, var(--w2b-surface) 84%, transparent) 72%,
      transparent 100%),
    linear-gradient(180deg, transparent 68%, var(--w2b-paper));
}
.hero__inner{
  position: relative; display: flex; flex-direction: column; align-items: center;
  text-align: center; width: 100%; max-width: 860px; margin: 0 auto;
}
.hero__eyebrow{ margin-bottom: var(--w2b-space-3); }
/* Bigger than the page's own h1: this one is the only thing above the field,
   and at the body scale it read as a section heading rather than as a claim. */
.hero h1{ margin-bottom: var(--w2b-space-4); max-width: 20ch; font-size: clamp(34px, 4.8vw, 68px); line-height: 1.06; }
.hero h1 em{ font-style: normal; color: var(--w2b-primary); }
.hero__sub{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); max-width: 56ch; text-wrap: balance; }
.hero__query{ width: 100%; max-width: 760px; margin-top: var(--w2b-space-6); padding: var(--w2b-space-4); text-align: left; }
.hero__notice{ margin-top: var(--w2b-space-4); text-align: left; }
.hero__account{
  margin-top: var(--w2b-space-5); max-width: 62ch;
  font-size: var(--w2b-text-s); color: var(--w2b-muted); text-wrap: balance;
}
.hero__account a{ font-family: var(--w2b-font-display); font-weight: 600; color: var(--w2b-primary); }

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
.home__storage a{ color: var(--w2b-primary); font-weight: 600; }

@media (max-width: 700px){
  /* At phone widths the fixed box would crop the fabric to a few huge
     parcels; a lower one keeps it readable as what it is. */
  .hero__art svg{ height: max(100%, 820px); }
  /* On a phone the text fills the reception in both directions: the headline
     and the sentence take nearly the whole width, and the field, the three
     lines and the account note take the whole height. A radial core cannot
     rescue that -- widened enough to clear the text it wipes the drawing out,
     and anywhere it fades the fabric runs straight through a line of type,
     which is where a backdrop stops being one.
     So the drawing itself steps back here, and the core only has to soften the
     middle. The opacity goes on the svg and not on `.hero__art`, because the
     veil below is that element's own pseudo-element and would fade with it. */
  .hero__art svg{ opacity: .42; }
  .hero__art::after{
    background:
      radial-gradient(92% 56% at 50% 48%,
        var(--w2b-surface) 0 46%,
        color-mix(in srgb, var(--w2b-surface) 82%, transparent) 78%,
        transparent 100%),
      linear-gradient(180deg, transparent 76%, var(--w2b-paper));
  }
}

@media (max-width: 560px){
  .hero{ margin-left: calc(-1 * var(--w2b-space-4)); margin-right: calc(-1 * var(--w2b-space-4)); padding: var(--w2b-space-7) var(--w2b-space-4); min-height: 0; }
  .hero__sub{ font-size: var(--w2b-text-m); }
}
</style>
