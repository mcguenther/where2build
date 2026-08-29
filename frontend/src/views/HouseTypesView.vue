<template>
  <div class="stapel">
    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Für alle Grundstücke</p>
        <h1>Haustypen</h1>
        <p class="seitenkopf__unter">
          Der Katalog gilt für alle Grundstücke. Jede Karte prüft selbst, auf welche Kandidaten
          der Baukörper überhaupt passt — geprüft wird, ob sich das Rechteck in irgendeiner
          Drehung vollständig in das Bebauungsfenster legen lässt.
        </p>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf" @click="adding = !adding">
        {{ adding ? "Aufnahme schließen" : "Haustyp hinzufügen" }}
      </button>
    </div>

    <p v-if="error" class="band band--fehler" role="alert">{{ error }}</p>

    <section v-if="adding" class="aufnahme">
      <div class="tafel">
        <div class="tafel__kopf"><h3>Vom Hersteller lesen</h3></div>
        <div class="tafel__leib stapel">
          <p class="hinweis">
            Link zu einem Haustyp — von jedem Hersteller, es gibt keine Liste
            erlaubter Anbieter. Gelesen wird nur die Seite, die hier steht; das
            Ergebnis je Adresse dauerhaft zwischengespeichert.
          </p>
          <div class="feld">
            <label for="ht-url">Adresse der Haustyp-Seite</label>
            <input id="ht-url" type="text" v-model="url">
          </div>
          <div class="reihe">
            <button type="button" class="knopf" :disabled="busy" @click="read">
              {{ busy ? "Wird gelesen …" : "Haustyp lesen" }}
            </button>
            <span class="chip">allowed_domains: {{ domain }}</span>
          </div>
        </div>
      </div>

      <div class="tafel">
        <div class="tafel__kopf"><h3>Von Hand eintragen</h3></div>
        <div class="tafel__leib stapel">
          <p class="hinweis">Wenn kein Datenblatt vorliegt oder ihr einfach Maße durchprobieren wollt.</p>
          <div class="drei">
            <div class="feld"><label for="e-name">Bezeichnung</label><input id="e-name" type="text" v-model="custom.name"></div>
            <div class="feld"><label for="e-laenge">Länge</label><input id="e-laenge" type="number" min="4" max="30" step="0.1" v-model.number="custom.length"></div>
            <div class="feld"><label for="e-breite">Breite</label><input id="e-breite" type="number" min="4" max="30" step="0.1" v-model.number="custom.width"></div>
          </div>
          <p class="hinweis">
            Ergibt {{ area(custom.length * custom.width, 1) }} bebaute Fläche.
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button type="button" class="knopf knopf--zweit" :disabled="!customValid" @click="addCustom">
            In den Katalog
          </button>
        </div>
      </div>

      <div class="notiz notiz--mahnung">
        <h4>Wohnfläche ist nicht Grundfläche</h4>
        <p>Der häufigste Fehler beim Fertighaus. Beim ELK All in One 159 sind 159,21 m² die
          Netto-Raumfläche über alle Geschosse — die <em>bebaute</em> Fläche beträgt 96,88 m².
          Wer die falsche Zahl auf die Karte legt, zeichnet ein Haus mit fast doppelter Grundfläche.</p>
        <p>Fehlen die Außenmaße, wird aus der bebauten Fläche ein Rechteck mit Seitenverhältnis
          1,35 abgeleitet — im Lageplan per Regler korrigierbar.</p>
      </div>
    </section>

    <p v-if="types.length" class="massstab-hinweis">Alle Grundrisse im gleichen Maßstab gezeichnet.</p>

    <div v-if="!types.length" class="leerstelle">
      <h3>Noch kein Haustyp im Katalog</h3>
      <p>Einen Link zu einer Haustyp-Seite einlesen lassen oder die Maße von Hand eintragen.
        Erst dann lässt sich ein Baukörper auf ein Grundstück legen.</p>
      <button type="button" class="knopf knopf--zweit" @click="adding = true">Haustyp hinzufügen</button>
    </div>

    <div v-else class="katalog">
      <article v-for="type in types" :key="type.id" class="typkarte tafel">
        <svg viewBox="0 0 300 130" class="typkarte__riss" role="img" :aria-label="`Grundriss ${type.name}`">
          <rect x="0" y="0" width="300" height="130" fill="var(--w2b-karte-grund)" />
          <rect :x="outline(type).x" :y="outline(type).y" :width="outline(type).w" :height="outline(type).h" rx="2"
                fill="var(--w2b-karte-entwurf)" fill-opacity=".8"
                stroke="var(--w2b-karte-entwurf-rand)" stroke-width="1.6" />
          <line :x1="outline(type).x" :y1="outline(type).y + outline(type).h + 13"
                :x2="outline(type).x + outline(type).w" :y2="outline(type).y + outline(type).h + 13"
                stroke="var(--w2b-karte-grenze)" stroke-width="1" />
          <text x="150" :y="outline(type).y + outline(type).h + 26" class="typkarte__mass">{{ num(dimensions(type).length, 1) }} m</text>
          <text :x="outline(type).x - 11" y="62" class="typkarte__mass"
                :transform="`rotate(-90, ${outline(type).x - 11}, 62)`">{{ num(dimensions(type).width, 1) }} m</text>
        </svg>

        <div class="typkarte__rumpf">
          <h3>{{ type.name }}</h3>
          <p class="typkarte__hersteller">{{ type.manufacturer }}</p>
          <dl>
            <dt>Bebaute Fläche</dt><dd>{{ area(type.builtArea, 2) }}</dd>
            <dt>Wohnfläche</dt><dd>{{ type.livingArea ? area(type.livingArea, 2) : "—" }}</dd>
            <dt>Außenmaß</dt>
            <dd>{{ num(dimensions(type).length, 1) }} × {{ num(dimensions(type).width, 1) }} m
              <span v-if="!type.length" class="zart" title="aus der bebauten Fläche geschätzt">≈</span></dd>
            <dt>Dach</dt><dd>{{ type.roofShape }}</dd>
            <dt>Preis ab</dt><dd>{{ type.priceFrom ? euro(type.priceFrom) : "—" }}</dd>
          </dl>
          <div class="typkarte__marken">
            <span class="chip">gelesen {{ date(type.readAt) }}</span>
            <span v-if="!type.length" class="chip chip--warn">Maße geschätzt</span>
            <span v-if="type.custom" class="chip chip--messing">eigene Maße</span>
          </div>
        </div>

        <div class="passt">
          <p class="passt__kopf">Passt auf {{ fit(type).count }} von {{ plots.length }} Grundstücken</p>
          <div v-for="row in fit(type).rows" :key="row.plot.id" class="passt__zeile">
            <span class="chip" :class="row.placement ? 'chip--gut' : 'chip--fehler'">{{ row.placement ? "passt" : "zu groß" }}</span>
            <span class="passt__name">{{ row.plot.name }}</span>
            <button v-if="row.placement" type="button" class="passt__knopf" @click="tryOn(type, row)">Ausprobieren</button>
          </div>
        </div>

        <div class="typkarte__fuss">
          <div class="dehnen"></div>
          <button type="button" class="knopf knopf--still knopf--klein" @click="remove(type)">Entfernen</button>
        </div>
      </article>
    </div>
  </div>
</template>

<script>
import { state, addHouseType, removeHouseType, newId, save } from "../lib/store.js";
import { buildableArea, findPlacement, footprintFromArea } from "../lib/geometry.js";
import { readHouseType } from "../lib/api.js";
import { houseTypeFromResponse } from "../lib/houseTypes.js";
import { area, euro, num, date } from "../lib/format.js";

export default {
  name: "HouseTypesView",
  data() {
    return {
      adding: false,
      busy: false,
      error: "",
      url: "https://www.schwoererhaus.de/haeuser/bungalow-128",
      custom: { name: "Eigener Entwurf", length: 12, width: 9 }
    };
  },
  computed: {
    types() { return state.data.houseTypes; },
    plots() { return state.data.plots; },
    domain() {
      try { return new URL(this.url).hostname.replace(/^www\./, ""); } catch { return "—"; }
    },
    customValid() {
      const { length, width } = this.custom;
      return length >= 4 && length <= 30 && width >= 4 && width <= 30;
    },
    catalogueScale() {
      const all = this.types.map(t => this.dimensions(t));
      const longest = Math.max(1, ...all.map(d => d.length));
      const widest = Math.max(1, ...all.map(d => d.width));
      return Math.min(206 / longest, 74 / widest);
    }
  },
  methods: {
    area, euro, num, date,
    dimensions(type) {
      if (type.length && type.width) return { length: type.length, width: type.width };
      const f = footprintFromArea(type.builtArea, type.ratio || 1.35);
      return { length: f.width, width: f.depth };
    },
    /** One scale for the whole catalogue, set by the largest type. Fitting each
     *  plan to its own box would draw a 14 × 14 m house the same size as a
     *  10 × 7 m one, which is exactly the comparison this page exists for. */
    outline(type) {
      const { length, width } = this.dimensions(type);
      const w = length * this.catalogueScale, h = width * this.catalogueScale;
      return { x: 150 - w / 2, y: 60 - h / 2, w, h };
    },
    /** Does this footprint fit into each plot's setback envelope, in any rotation? */
    fit(type) {
      const { length, width } = this.dimensions(type);
      const rows = this.plots.map(plot => ({
        plot,
        placement: findPlacement(buildableArea(plot.polygon, plot.setbacks), length, width)
      }));
      return { rows, count: rows.filter(r => r.placement).length };
    },
    tryOn(type, { plot, placement }) {
      plot.houseTypeId = type.id;
      if (type.ratio) plot.ratio = type.ratio;
      plot.house = {
        cx: placement.cx, cy: placement.cy,
        rotation: placement.rotation > 90 ? placement.rotation - 180 : placement.rotation
      };
      save();
      state.openPlotId = plot.id;
      state.view = "plot";
      window.scrollTo({ top: 0 });
    },
    async read() {
      this.busy = true;
      this.error = "";
      try {
        addHouseType(houseTypeFromResponse(await readHouseType(this.url.trim())));
        this.adding = false;
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
    addCustom() {
      const { name, length, width } = this.custom;
      addHouseType({
        id: newId("house"), manufacturer: "Von Hand eingetragen", name,
        builtArea: Math.round(length * width * 100) / 100, livingArea: null,
        livingAreaGround: null, livingAreaUpper: null, length, width,
        roofShape: "offen", priceFrom: null, ratio: length / width,
        source: null, readAt: new Date().toISOString().slice(0, 10), custom: true
      });
      this.adding = false;
    },
    remove(type) {
      const confirmed = window.confirm(`„${type.name}“ aus dem Katalog entfernen? Grundstücke mit diesem Typ fallen auf den ersten übrigen zurück.`);
      if (confirmed) removeHouseType(type.id);
    }
  }
};
</script>

<style scoped>
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 70ch; }
.hinweis{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.zart{ color: var(--w2b-gedaempft); }
.aufnahme{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--w2b-raum-4); align-items: start; }
.drei{ display: grid; grid-template-columns: 1fr 90px 90px; gap: var(--w2b-raum-3); }
@media (max-width: 560px){ .drei{ grid-template-columns: 1fr; } }

.massstab-hinweis{ font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.leerstelle{
  border: 1px dashed var(--w2b-linie); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-raum-3); padding: var(--w2b-raum-7) var(--w2b-raum-5); text-align: center;
}
.leerstelle h3{ color: var(--w2b-graphit); font-size: var(--w2b-schrift-l); }
.leerstelle p{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); max-width: 46ch; }
.katalog{ display: grid; grid-template-columns: repeat(auto-fill, minmax(304px, 1fr)); gap: var(--w2b-raum-4); }
.typkarte{ display: flex; flex-direction: column; }
.typkarte__riss{ display: block; width: 100%; height: auto; border-bottom: 1px solid var(--w2b-linie); }
.typkarte__mass{ font-family: var(--w2b-daten); font-size: 10px; fill: var(--w2b-karte-grenze); text-anchor: middle; }
.typkarte__rumpf{ padding: var(--w2b-raum-3) var(--w2b-raum-4); display: flex; flex-direction: column; gap: var(--w2b-raum-2); flex: 1; }
.typkarte__hersteller{ font-family: var(--w2b-daten); font-size: 10.5px; color: var(--w2b-gedaempft); margin-top: -4px; }
.typkarte__rumpf dl{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px var(--w2b-raum-3); font-size: var(--w2b-schrift-s); }
.typkarte__rumpf dt{ color: var(--w2b-graphit); }
.typkarte__rumpf dd{ margin: 0; text-align: right; font-family: var(--w2b-daten); font-variant-numeric: tabular-nums; }
.typkarte__marken{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; padding-top: var(--w2b-raum-1); }
.passt{ border-top: 1px solid var(--w2b-linie-zart); padding: var(--w2b-raum-3) var(--w2b-raum-4); display: flex; flex-direction: column; gap: 7px; }
.passt__kopf{ font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-xs); letter-spacing: .06em; color: var(--w2b-gedaempft); }
.passt__zeile{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-s); }
.passt__name{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--w2b-graphit); }
.passt__knopf{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-xs); }
.passt__knopf:hover{ text-decoration: underline; }
.typkarte__fuss{ display: flex; padding: var(--w2b-raum-3) var(--w2b-raum-4); border-top: 1px solid var(--w2b-linie-zart); }
</style>
