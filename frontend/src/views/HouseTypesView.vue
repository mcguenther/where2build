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
      <button type="button" class="knopf" @click="aufnahme = !aufnahme">
        {{ aufnahme ? "Aufnahme schließen" : "Haustyp hinzufügen" }}
      </button>
    </div>

    <section v-if="aufnahme" class="aufnahme">
      <div class="tafel">
        <div class="tafel__kopf"><h3>Vom Hersteller lesen</h3></div>
        <div class="tafel__leib stapel">
          <p class="hinweis">
            Link zu einem Haustyp. Der Abruf ist auf die Herstellerdomain begrenzt,
            das Ergebnis je URL dauerhaft zwischengespeichert.
          </p>
          <div class="feld">
            <label for="ht-url">Adresse der Haustyp-Seite</label>
            <input id="ht-url" type="text" v-model="url">
          </div>
          <div class="reihe">
            <button type="button" class="knopf" :disabled="laeuft" @click="lesen">
              {{ laeuft ? "Wird gelesen …" : "Haustyp lesen" }}
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
            <div class="feld"><label for="e-name">Bezeichnung</label><input id="e-name" type="text" v-model="eigen.name"></div>
            <div class="feld"><label for="e-laenge">Länge</label><input id="e-laenge" type="number" min="4" max="30" step="0.1" v-model.number="eigen.laenge"></div>
            <div class="feld"><label for="e-breite">Breite</label><input id="e-breite" type="number" min="4" max="30" step="0.1" v-model.number="eigen.breite"></div>
          </div>
          <p class="hinweis">
            Ergibt {{ area(eigen.laenge * eigen.breite, 1) }} bebaute Fläche.
            Kantenlängen unter 4 m oder über 30 m sind kein Haus, sondern ein Tippfehler.
          </p>
          <button type="button" class="knopf knopf--zweit" :disabled="!eigenGueltig" @click="eigenAnlegen">
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

    <p class="massstab-hinweis">Alle Grundrisse im gleichen Maßstab gezeichnet.</p>

    <div class="katalog">
      <article v-for="typ in typen" :key="typ.id" class="typkarte tafel">
        <svg viewBox="0 0 300 130" class="typkarte__riss" role="img" :aria-label="`Grundriss ${typ.name}`">
          <rect x="0" y="0" width="300" height="130" fill="var(--w2b-karte-grund)" />
          <rect :x="riss(typ).x" :y="riss(typ).y" :width="riss(typ).w" :height="riss(typ).h" rx="2"
                fill="var(--w2b-karte-entwurf)" fill-opacity=".8"
                stroke="var(--w2b-karte-entwurf-rand)" stroke-width="1.6" />
          <line :x1="riss(typ).x" :y1="riss(typ).y + riss(typ).h + 13"
                :x2="riss(typ).x + riss(typ).w" :y2="riss(typ).y + riss(typ).h + 13"
                stroke="var(--w2b-karte-grenze)" stroke-width="1" />
          <text x="150" :y="riss(typ).y + riss(typ).h + 26" class="typkarte__mass">{{ num(masse(typ).laenge, 1) }} m</text>
          <text :x="riss(typ).x - 11" y="62" class="typkarte__mass"
                :transform="`rotate(-90, ${riss(typ).x - 11}, 62)`">{{ num(masse(typ).breite, 1) }} m</text>
        </svg>

        <div class="typkarte__rumpf">
          <h3>{{ typ.name }}</h3>
          <p class="typkarte__hersteller">{{ typ.hersteller }}</p>
          <dl>
            <dt>Bebaute Fläche</dt><dd>{{ area(typ.bebauteFlaeche, 2) }}</dd>
            <dt>Wohnfläche</dt><dd>{{ typ.wohnflaeche ? area(typ.wohnflaeche, 2) : "—" }}</dd>
            <dt>Außenmaß</dt>
            <dd>{{ num(masse(typ).laenge, 1) }} × {{ num(masse(typ).breite, 1) }} m
              <span v-if="!typ.laenge" class="zart" title="aus der bebauten Fläche geschätzt">≈</span></dd>
            <dt>Dach</dt><dd>{{ typ.dachform }}</dd>
            <dt>Preis ab</dt><dd>{{ typ.preisAb ? euro(typ.preisAb) : "—" }}</dd>
          </dl>
          <div class="typkarte__marken">
            <span class="chip">gelesen {{ date(typ.gelesenAm) }}</span>
            <span v-if="!typ.laenge" class="chip chip--warn">Maße geschätzt</span>
            <span v-if="typ.eigen" class="chip chip--messing">eigene Maße</span>
          </div>
        </div>

        <div class="passt">
          <p class="passt__kopf">Passt auf {{ treffer(typ).anzahl }} von {{ grundstuecke.length }} Grundstücken</p>
          <div v-for="p in treffer(typ).zeilen" :key="p.plot.id" class="passt__zeile">
            <span class="chip" :class="p.lage ? 'chip--gut' : 'chip--fehler'">{{ p.lage ? "passt" : "zu groß" }}</span>
            <span class="passt__name">{{ p.plot.name }}</span>
            <button v-if="p.lage" type="button" class="passt__knopf" @click="ausprobieren(typ, p)">Ausprobieren</button>
          </div>
        </div>

        <div class="typkarte__fuss">
          <div class="dehnen"></div>
          <button type="button" class="knopf knopf--still knopf--klein" @click="entfernen(typ)">Entfernen</button>
        </div>
      </article>
    </div>
  </div>
</template>

<script>
import { state, addHouseType, removeHouseType, newId, save } from "../lib/store.js";
import { buildableArea, findPlacement, footprintFromArea } from "../lib/geometry.js";
import { haustypLesen } from "../lib/api.js";
import { area, euro, num, date } from "../lib/format.js";

export default {
  name: "HouseTypesView",
  data() {
    return {
      aufnahme: false,
      laeuft: false,
      url: "https://www.schwoererhaus.de/haeuser/bungalow-128",
      eigen: { name: "Eigener Entwurf", laenge: 12, breite: 9 }
    };
  },
  computed: {
    typen() { return state.daten.haustypen; },
    grundstuecke() { return state.daten.grundstuecke; },
    domain() {
      try { return new URL(this.url).hostname.replace(/^www\./, ""); } catch { return "—"; }
    },
    eigenGueltig() {
      const { laenge, breite } = this.eigen;
      return laenge >= 4 && laenge <= 30 && breite >= 4 && breite <= 30;
    },
    katalogMassstab() {
      const masse = this.typen.map(t => this.masse(t));
      const laengste = Math.max(1, ...masse.map(m => m.laenge));
      const breiteste = Math.max(1, ...masse.map(m => m.breite));
      return Math.min(206 / laengste, 74 / breiteste);
    }
  },
  methods: {
    area, euro, num, date,
    masse(typ) {
      if (typ.laenge && typ.breite) return { laenge: typ.laenge, breite: typ.breite };
      const f = footprintFromArea(typ.bebauteFlaeche, typ.verhaeltnis || 1.35);
      return { laenge: f.width, breite: f.depth };
    },
    /** One scale for the whole catalogue, set by the largest type. Fitting each
     *  plan to its own box would draw a 14 × 14 m house the same size as a
     *  10 × 7 m one, which is exactly the comparison this page exists for. */
    riss(typ) {
      const { laenge, breite } = this.masse(typ);
      const w = laenge * this.katalogMassstab, h = breite * this.katalogMassstab;
      return { x: 150 - w / 2, y: 60 - h / 2, w, h };
    },
    /** Does this footprint fit into each plot's setback envelope, in any rotation? */
    treffer(typ) {
      const { laenge, breite } = this.masse(typ);
      const zeilen = this.grundstuecke.map(plot => ({
        plot,
        lage: findPlacement(buildableArea(plot.polygon, plot.tiefen), laenge, breite)
      }));
      return { zeilen, anzahl: zeilen.filter(z => z.lage).length };
    },
    ausprobieren(typ, { plot, lage }) {
      plot.haustypId = typ.id;
      if (typ.verhaeltnis) plot.verhaeltnis = typ.verhaeltnis;
      plot.haus = { cx: lage.cx, cy: lage.cy, rotation: lage.rotation > 90 ? lage.rotation - 180 : lage.rotation };
      save();
      state.offenesGrundstueck = plot.id;
      state.ansicht = "grundstueck";
      window.scrollTo({ top: 0 });
    },
    async lesen() {
      this.laeuft = true;
      try {
        const gelesen = await haustypLesen(this.url);
        addHouseType({
          id: newId("ht"), hersteller: gelesen.hersteller, name: gelesen.name,
          bebauteFlaeche: gelesen.bebauteFlaeche, wohnflaeche: gelesen.wohnflaeche,
          wohnflaecheEg: gelesen.wohnflaecheEg, wohnflaecheOg: gelesen.wohnflaecheOg,
          laenge: gelesen.laenge, breite: gelesen.breite, dachform: gelesen.dachform,
          preisAb: gelesen.preisAb, verhaeltnis: gelesen.verhaeltnis,
          quelle: gelesen.quelle, gelesenAm: new Date().toISOString().slice(0, 10), eigen: false
        });
        this.aufnahme = false;
      } finally {
        this.laeuft = false;
      }
    },
    eigenAnlegen() {
      const { name, laenge, breite } = this.eigen;
      addHouseType({
        id: newId("ht"), hersteller: "Eigene Maße", name,
        bebauteFlaeche: Math.round(laenge * breite * 100) / 100, wohnflaeche: null,
        wohnflaecheEg: null, wohnflaecheOg: null, laenge, breite,
        dachform: "offen", preisAb: null, verhaeltnis: laenge / breite,
        quelle: null, gelesenAm: new Date().toISOString().slice(0, 10), eigen: true
      });
      this.aufnahme = false;
    },
    entfernen(typ) {
      const sicher = window.confirm(`„${typ.name}“ aus dem Katalog entfernen? Grundstücke mit diesem Typ fallen auf den ersten übrigen zurück.`);
      if (sicher) removeHouseType(typ.id);
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
