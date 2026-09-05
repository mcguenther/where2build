<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Für alle Grundstücke</p>
        <h1>Haustypen</h1>
        <p class="page-head__sub">
          Der Katalog gilt für alle Grundstücke. Jede Karte prüft selbst, auf welche Kandidaten
          der Baukörper überhaupt passt — geprüft wird, ob sich das Rechteck in irgendeiner
          Drehung vollständig in das Bebauungsfenster legen lässt.
        </p>
      </div>
      <div class="spacer"></div>
      <button type="button" class="btn" @click="adding = !adding">
        {{ adding ? "Aufnahme schließen" : "Haustyp hinzufügen" }}
      </button>
    </div>

    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <section v-if="adding" class="intake">
      <div class="panel">
        <div class="panel__head"><h3>Vom Hersteller lesen</h3></div>
        <div class="panel__body stack">
          <p class="hint">
            Link zu einem Haustyp — von jedem Hersteller, es gibt keine Liste
            erlaubter Anbieter. Gelesen wird nur die Seite, die hier steht; das
            Ergebnis je Adresse dauerhaft zwischengespeichert.
          </p>
          <div class="field">
            <label for="ht-url">Adresse der Haustyp-Seite</label>
            <input id="ht-url" type="text" v-model="url">
          </div>
          <div class="row">
            <button type="button" class="btn" :disabled="busy" @click="read">
              {{ busy ? "Wird gelesen …" : "Haustyp lesen" }}
            </button>
            <span class="chip">allowed_domains: {{ domain }}</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>Von Hand eintragen</h3></div>
        <div class="panel__body stack">
          <p class="hint">Wenn kein Datenblatt vorliegt oder ihr einfach Maße durchprobieren wollt.</p>
          <div class="field-trio">
            <div class="field"><label for="manual-name">Bezeichnung</label><input id="manual-name" type="text" v-model="custom.name"></div>
            <div class="field"><label for="manual-length">Länge</label><input id="manual-length" type="number" min="4" max="30" step="0.1" v-model.number="custom.length"></div>
            <div class="field"><label for="manual-width">Breite</label><input id="manual-width" type="number" min="4" max="30" step="0.1" v-model.number="custom.width"></div>
          </div>
          <p class="hint">
            Ergibt {{ area(customArea, 1) }} bebaute Fläche.
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button type="button" class="btn btn--secondary" :disabled="!customValid" @click="addCustom">
            In den Katalog
          </button>
        </div>
      </div>

      <div class="callout callout--caution">
        <h4>Wohnfläche ist nicht Grundfläche</h4>
        <p>Der häufigste Fehler beim Fertighaus. Beim ELK All in One 159 sind 159,21 m² die
          Netto-Raumfläche über alle Geschosse — die <em>bebaute</em> Fläche beträgt 96,88 m².
          Wer die falsche Zahl auf die Karte legt, zeichnet ein Haus mit fast doppelter Grundfläche.</p>
        <p>Fehlen die Außenmaße, wird aus der bebauten Fläche ein Rechteck mit Seitenverhältnis
          1,35 abgeleitet — im Lageplan per Regler korrigierbar.</p>
      </div>
    </section>

    <p v-if="types.length" class="scale-hint">Alle Grundrisse im gleichen Maßstab gezeichnet.</p>

    <div v-if="!types.length" class="empty-state">
      <h3>Noch kein Haustyp im Katalog</h3>
      <p>Einen Link zu einer Haustyp-Seite einlesen lassen oder die Maße von Hand eintragen.
        Erst dann lässt sich ein Baukörper auf ein Grundstück legen.</p>
      <button type="button" class="btn btn--secondary" @click="adding = true">Haustyp hinzufügen</button>
    </div>

    <div v-else class="catalogue">
      <article v-for="type in types" :key="type.id" class="type-card panel">
        <svg viewBox="0 0 300 130" class="type-card__plan" role="img" :aria-label="`Grundriss ${type.name}`">
          <rect x="0" y="0" width="300" height="130" fill="var(--w2b-map-ground)" />
          <rect :x="outline(type).x" :y="outline(type).y" :width="outline(type).w" :height="outline(type).h" rx="2"
                fill="var(--w2b-map-design)" fill-opacity=".8"
                stroke="var(--w2b-map-design-edge)" stroke-width="1.6" />
          <line :x1="outline(type).x" :y1="outline(type).y + outline(type).h + 13"
                :x2="outline(type).x + outline(type).w" :y2="outline(type).y + outline(type).h + 13"
                stroke="var(--w2b-map-boundary)" stroke-width="1" />
          <text x="150" :y="outline(type).y + outline(type).h + 26" class="type-card__dimension">{{ num(dimensions(type).length, 1) }} m</text>
          <text :x="outline(type).x - 11" y="62" class="type-card__dimension"
                :transform="`rotate(-90, ${outline(type).x - 11}, 62)`">{{ num(dimensions(type).width, 1) }} m</text>
        </svg>

        <div class="type-card__body">
          <h3>{{ type.name }}</h3>
          <p class="type-card__manufacturer">{{ type.manufacturer }}</p>
          <dl>
            <dt>Bebaute Fläche</dt><dd>{{ area(type.builtArea, 2) }}</dd>
            <dt>Wohnfläche</dt><dd>{{ type.livingArea ? area(type.livingArea, 2) : "—" }}</dd>
            <dt>Außenmaß</dt>
            <dd>{{ num(dimensions(type).length, 1) }} × {{ num(dimensions(type).width, 1) }} m
              <span v-if="!type.length" class="faint" title="aus der bebauten Fläche geschätzt">≈</span></dd>
            <dt>Dach</dt><dd>{{ type.roofShape }}</dd>
            <dt>Preis ab</dt><dd>{{ type.priceFrom ? euro(type.priceFrom) : "—" }}</dd>
          </dl>
          <div class="type-card__chips">
            <span class="chip">gelesen {{ date(type.readAt) }}</span>
            <span v-if="!type.length" class="chip chip--warn">Maße geschätzt</span>
            <span v-if="type.custom" class="chip chip--brass">eigene Maße</span>
          </div>
        </div>

        <div class="fits">
          <p class="fits__head">Passt auf {{ fit(type).count }} von {{ plots.length }} Grundstücken</p>
          <div v-for="row in fit(type).rows" :key="row.plot.id" class="fits__row">
            <span class="chip" :class="row.placement ? 'chip--good' : 'chip--error'">{{ row.placement ? "passt" : "zu groß" }}</span>
            <span class="fits__name">{{ row.plot.name }}</span>
            <button v-if="row.placement" type="button" class="fits__button" @click="tryOn(type, row)">Ausprobieren</button>
          </div>
        </div>

        <div class="type-card__foot">
          <div class="spacer"></div>
          <button type="button" class="btn btn--quiet btn--small" @click="remove(type)">Entfernen</button>
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
    /** An emptied field is not a zero: with a missing edge the area stays "—". */
    customArea() {
      const { length, width } = this.custom;
      return Number.isFinite(length) && Number.isFinite(width) ? length * width : null;
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
      this.$router.push({ name: "plot", params: { id: plot.id } });
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
.page-head__sub{ max-width: 70ch; }
.hint{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.faint{ color: var(--w2b-muted); }
.intake{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--w2b-space-4); align-items: start; }
.field-trio{ display: grid; grid-template-columns: 1fr 90px 90px; gap: var(--w2b-space-3); }
@media (max-width: 560px){ .field-trio{ grid-template-columns: 1fr; } }

.scale-hint{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); }
.empty-state{
  border: 1px dashed var(--w2b-line); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-space-3); padding: var(--w2b-space-7) var(--w2b-space-5); text-align: center;
}
.empty-state h3{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); }
.empty-state p{ color: var(--w2b-muted); font-size: var(--w2b-text-s); max-width: 46ch; }
.catalogue{ display: grid; grid-template-columns: repeat(auto-fill, minmax(304px, 1fr)); gap: var(--w2b-space-4); }
.type-card{ display: flex; flex-direction: column; }
.type-card__plan{ display: block; width: 100%; height: auto; border-bottom: 1px solid var(--w2b-line); }
.type-card__dimension{ font-family: var(--w2b-font-mono); font-size: 10px; fill: var(--w2b-map-boundary); text-anchor: middle; }
.type-card__body{ padding: var(--w2b-space-3) var(--w2b-space-4); display: flex; flex-direction: column; gap: var(--w2b-space-2); flex: 1; }
.type-card__manufacturer{ font-family: var(--w2b-font-mono); font-size: 10.5px; color: var(--w2b-muted); margin-top: -4px; }
.type-card__body dl{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px var(--w2b-space-3); font-size: var(--w2b-text-s); }
.type-card__body dt{ color: var(--w2b-graphite); }
.type-card__body dd{ margin: 0; text-align: right; font-family: var(--w2b-font-mono); font-variant-numeric: tabular-nums; }
.type-card__chips{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; padding-top: var(--w2b-space-1); }
.fits{ border-top: 1px solid var(--w2b-line-faint); padding: var(--w2b-space-3) var(--w2b-space-4); display: flex; flex-direction: column; gap: 7px; }
.fits__head{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs); letter-spacing: .06em; color: var(--w2b-muted); }
.fits__row{ display: flex; align-items: center; gap: var(--w2b-space-2); font-size: var(--w2b-text-s); }
.fits__name{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--w2b-graphite); }
.fits__button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primary); font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-xs); }
.fits__button:hover{ text-decoration: underline; }
.type-card__foot{ display: flex; padding: var(--w2b-space-3) var(--w2b-space-4); border-top: 1px solid var(--w2b-line-faint); }
</style>
