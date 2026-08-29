<template>
  <div class="stapel">
    <nav class="krume" aria-label="Pfad">
      <button type="button" @click="abbrechen">Grundstücke</button>
      <span aria-hidden="true">›</span>
      <span>Grundstück hinzufügen</span>
    </nav>

    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Aufnahme</p>
        <h1>Grundstück hinzufügen</h1>
      </div>
      <div class="dehnen"></div>
      <button type="button" class="knopf knopf--still" @click="abbrechen">Abbrechen</button>
    </div>

    <ol class="schrittleiste" aria-label="Schritte">
      <li v-for="(s, i) in schritte" :key="s.id"
          :class="{ 'ist-hier': i === schritt, 'ist-fertig': i < schritt }"
          :aria-current="i === schritt ? 'step' : null">
        <span class="schrittleiste__zahl">{{ i < schritt ? "✓" : i + 1 }}</span>
        <span class="schrittleiste__name">{{ s.name }}</span>
      </li>
    </ol>

    <!-- 1 · Quelle -->
    <section v-if="schritt === 0" class="stapel">
      <p class="seitenkopf__unter">Drei Wege hinein. Welcher passt zu dem, was vorliegt?</p>
      <div class="quellen">
        <label v-for="q in quellen" :key="q.id" class="quelle" :class="{ 'quelle--gewaehlt': quelle === q.id }">
          <input type="radio" name="quelle" :value="q.id" v-model="quelle">
          <span class="quelle__kopf">
            <span class="quelle__name">{{ q.name }}</span>
            <span class="chip">{{ q.kennung }}</span>
          </span>
          <span class="quelle__text">{{ q.text }}</span>
        </label>
      </div>

      <div class="tafel">
        <div class="tafel__leib stapel">
          <template v-if="quelle === 'url'">
            <div class="feld">
              <label for="q-url">Adresse der Anzeige</label>
              <input id="q-url" type="text" v-model="url">
            </div>
          </template>
          <template v-else-if="quelle === 'flurstueck'">
            <div class="drei">
              <div class="feld">
                <label for="q-gemarkung">Gemarkung</label>
                <input id="q-gemarkung" type="text" v-model="gemarkung" list="gemarkungen">
                <datalist id="gemarkungen">
                  <option v-for="g in gemarkungen" :key="g" :value="g"></option>
                </datalist>
              </div>
              <div class="feld"><label for="q-zaehler">Zähler</label><input id="q-zaehler" type="text" v-model="zaehler"></div>
              <div class="feld"><label for="q-nenner">Nenner</label><input id="q-nenner" type="text" v-model="nenner"></div>
            </div>
          </template>
          <template v-else>
            <div class="feld">
              <label for="q-paste">Anzeige hier einfügen</label>
              <textarea id="q-paste" v-model="einfuegetext"
                        placeholder="Strg+V — die kopierte Anzeigenseite"></textarea>
            </div>
            <p class="band">
              ImmoScout24 beantwortet Serverabrufe mit 401 — dort ist dieser Weg der einzige.
              Formatierter Einfügetext bewahrt Links und Struktur.
            </p>
          </template>

          <div class="reihe">
            <button type="button" class="knopf" :disabled="laeuft || !bereit" @click="lesen">
              {{ laeuft ? "Wird gelesen …" : "Lesen" }}
            </button>
            <span v-if="laeuft" class="zart">Der Abruf kann einen Moment dauern.</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 2 · Prüfen -->
    <section v-else-if="schritt === 1" class="stapel">
      <div class="reihe">
        <p class="seitenkopf__unter" style="flex:1">
          Jedes Feld führt die Quelle mit, aus der es stammt. Erst nach Bestätigung wandern die
          Werte in die Planung — das Modell antwortet auch dann, wenn die Seite die Zahl gar nicht hergibt.
        </p>
        <span v-if="fund && fund.simuliert" class="chip chip--warn" :title="fund.grund">
          Beispieldaten: {{ fund.grund }}
        </span>
      </div>

      <div class="vorschlaege">
        <div v-for="(f, i) in fund.felder" :key="i" class="vorschlag"
             :class="{ 'vorschlag--bestaetigt': f.bestaetigt === true, 'vorschlag--leer': f.bestaetigt === null }">
          <span class="vorschlag__kopf">
            <span class="feldname">{{ f.feld }}</span>
            <span class="vorschlag__marke">
              {{ f.bestaetigt === null ? "nicht belegt" : f.bestaetigt ? "bestätigt" : "automatisch gelesen" }}
            </span>
          </span>
          <input type="text" v-model="f.wert" :aria-label="f.feld"
                 :placeholder="f.bestaetigt === null ? 'steht nicht auf der Seite' : ''">
          <span class="vorschlag__quelle">{{ f.quelle }}</span>
        </div>
      </div>

      <div class="reihe">
        <button type="button" class="knopf" @click="schritt = 2">Werte übernehmen</button>
        <button type="button" class="knopf knopf--still" @click="schritt = 0">Zurück</button>
      </div>
    </section>

    <!-- 3 · Flurstück -->
    <section v-else-if="schritt === 2" class="stapel">
      <p class="seitenkopf__unter">
        So liegt das Flurstück im Kataster. Stimmt der Zuschnitt, geht es weiter;
        sonst zurück und die Kennung korrigieren.
      </p>
      <div class="pruefgitter">
        <div class="tafel">
          <SitePlan :plot="entwurf" :koerper="entwurfKoerper" :breite="640" :hoehe="440" />
        </div>
        <div class="tafel">
          <div class="tafel__kopf"><h3>Was übernommen wird</h3></div>
          <dl class="werteliste">
            <dt>Gemarkung</dt><dd>{{ entwurf.gemarkung }}</dd>
            <dt>Flurstücke</dt><dd>{{ entwurf.flurstuecke.join(" · ") }}</dd>
            <dt>Fläche amtlich</dt><dd>{{ area(entwurf.flaecheAmtlich) }}</dd>
            <dt>Fläche gerechnet</dt><dd>{{ area(gerechneteFlaeche, 1) }}</dd>
            <dt>Kaufpreis</dt><dd>{{ euro(entwurf.kaufpreis) }}</dd>
            <dt>Bodenrichtwert</dt><dd>{{ euroPerSqm(entwurf.bodenrichtwert) }}</dd>
          </dl>
          <p class="tafel__fussnote">
            Mehrere Flurstücke werden zu einem Grundstück vereinigt: Polygone verschmolzen,
            amtliche Flächen summiert.
          </p>
        </div>
      </div>
      <div class="reihe">
        <button type="button" class="knopf" @click="schritt = 3">Passt</button>
        <button type="button" class="knopf knopf--still" @click="schritt = 1">Zurück</button>
      </div>
    </section>

    <!-- 4 · Benennen -->
    <section v-else class="stapel">
      <div class="tafel">
        <div class="tafel__leib stapel">
          <div class="feld">
            <label for="q-name">Name in der Übersicht</label>
            <input id="q-name" type="text" v-model="entwurf.name">
          </div>
          <div class="feld">
            <label for="q-ort">Ort</label>
            <input id="q-ort" type="text" v-model="entwurf.ort">
          </div>
          <div class="feld">
            <label for="q-notiz">Notiz</label>
            <input id="q-notiz" type="text" v-model="entwurf.notiz" placeholder="Optional — was auffiel">
          </div>
          <p class="band band--gut">
            Danach öffnet sich der Lageplan. Haustyp, Abstandsflächen und Wege lassen sich
            dort jederzeit ändern.
          </p>
          <div class="reihe">
            <button type="button" class="knopf" @click="anlegen">Anlegen und öffnen</button>
            <button type="button" class="knopf knopf--still" @click="schritt = 2">Zurück</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import SitePlan from "../components/SitePlan.vue";
import { state, addPlot, newId, placement, centreOf } from "../lib/store.js";
import { inseratLesen, seiteLesen, flurstueckSuchen } from "../lib/api.js";
import { polygonArea } from "../lib/geometry.js";
import { area, euro, euroPerSqm } from "../lib/format.js";

/** Parse "212.000 €" or "1.104 m²" the way a German listing writes it. */
function zahlAus(text) {
  if (!text) return null;
  const treffer = String(text).replace(/\./g, "").replace(",", ".").match(/-?\d+(\.\d+)?/);
  return treffer ? parseFloat(treffer[0]) : null;
}

export default {
  name: "WizardView",
  components: { SitePlan },
  data() {
    return {
      schritt: 0,
      quelle: "url",
      url: "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck-leipzig/2947103821",
      gemarkung: "Baalsdorf",
      zaehler: "61",
      nenner: "3",
      einfuegetext: "",
      laeuft: false,
      fund: null,
      entwurf: null,
      schritte: [
        { id: "quelle", name: "Quelle" },
        { id: "pruefen", name: "Werte prüfen" },
        { id: "flurstueck", name: "Flurstück" },
        { id: "benennen", name: "Benennen" }
      ],
      quellen: [
        { id: "url", name: "Link einwerfen", kennung: "F-01",
          text: "Adresse einer Anzeige. Das Modell holt die Seite und liest Adresse, Flurstück, Kaufpreis und Fläche heraus." },
        { id: "flurstueck", name: "Flurstück direkt", kennung: "F-11",
          text: "Gemarkung, Zähler und Nenner — ohne Umweg über Adresse und Geocoding." },
        { id: "einfuegen", name: "Seite einfügen", kennung: "F-12",
          text: "Für Portale, die keinen Serverabruf zulassen. Die kopierte Anzeigenseite einfügen." }
      ],
      gemarkungen: ["Liebertwolkwitz", "Holzhausen", "Zuckelhausen", "Baalsdorf", "Mölkau", "Engelsdorf"]
    };
  },
  computed: {
    bereit() {
      if (this.quelle === "url") return this.url.trim().length > 8;
      if (this.quelle === "flurstueck") return this.gemarkung.trim() && this.zaehler.trim();
      return this.einfuegetext.trim().length > 20;
    },
    entwurfKoerper() { return this.entwurf ? placement(this.entwurf) : null; },
    gerechneteFlaeche() { return this.entwurf ? polygonArea(this.entwurf.polygon) : 0; }
  },
  methods: {
    area, euro, euroPerSqm,
    abbrechen() { state.ansicht = "grundstuecke"; window.scrollTo({ top: 0 }); },
    async lesen() {
      this.laeuft = true;
      try {
        if (this.quelle === "url") this.fund = await inseratLesen(this.url);
        else if (this.quelle === "flurstueck") this.fund = await flurstueckSuchen(this.gemarkung, this.zaehler, this.nenner);
        else this.fund = await seiteLesen(this.einfuegetext);
        this.entwurfBauen();
        this.schritt = 1;
      } finally {
        this.laeuft = false;
      }
    },
    /**
     * Turn the read fields into a plot. Until ALKIS supplies real geometry the
     * outline is a plausible stand-in sized to the area that was read, so the
     * plan step shows something meaningful rather than an empty frame.
     */
    entwurfBauen() {
      const wert = name => this.fund.felder.find(f => f.feld === name)?.wert;
      const flaeche = zahlAus(wert("Grundstücksfläche") || wert("Amtliche Fläche")) || 800;
      const preis = zahlAus(wert("Kaufpreis"));
      const seite = Math.sqrt(flaeche / 1.55);
      const polygon = [
        { x: 0, y: 0 },
        { x: seite * 1.55, y: 0.6 },
        { x: seite * 1.55 + 1.1, y: seite * 1.02 },
        { x: 1.2, y: seite * 1.06 }
      ];
      const flurstuecke = (wert("Flurstücke") || wert("Kennzeichen") || "neu")
        .split(/[,;]/).map(s => s.trim()).filter(Boolean);

      this.entwurf = {
        id: newId("gs"),
        name: this.fund.name,
        ort: this.fund.ort,
        gemarkung: this.fund.gemarkung,
        flurstuecke,
        flaecheAmtlich: Math.round(flaeche),
        kaufpreis: preis ?? 0,
        bodenrichtwert: 200,
        brwZone: "—",
        brwStichtag: "2026-01-01",
        nordVersatz: 0,
        polygon,
        teilung: null,
        haustypId: state.daten.haustypen[0]?.id ?? null,
        haus: centreOf(polygon),
        verhaeltnis: 1.35,
        wandhoehe: 6.4,
        tiefen: polygon.map(() => 3),
        quelle: this.quelle === "url" ? this.url : this.quelle === "einfuegen" ? "Aus der Zwischenablage eingefügt" : "ALKIS",
        notiz: "",
        wege: {}
      };
    },
    anlegen() {
      const plot = addPlot(this.entwurf);
      state.offenesGrundstueck = plot.id;
      state.ansicht = "grundstueck";
      window.scrollTo({ top: 0 });
    }
  }
};
</script>

<style scoped>
.krume{ display: flex; align-items: center; gap: var(--w2b-raum-2); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
.krume button{ background: none; border: 0; padding: 0; cursor: pointer; color: var(--w2b-primaer); font: inherit; }
.seitenkopf{ display: flex; align-items: flex-end; gap: var(--w2b-raum-4); flex-wrap: wrap; }
.seitenkopf__unter{ color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 68ch; }
.zart{ color: var(--w2b-gedaempft); font-size: var(--w2b-schrift-s); }

.schrittleiste{
  display: flex; gap: var(--w2b-raum-2); flex-wrap: wrap; list-style: none; margin: 0; padding: 0;
}
.schrittleiste li{
  display: flex; align-items: center; gap: var(--w2b-raum-2);
  padding: 9px var(--w2b-raum-4) 9px 10px; border-radius: var(--w2b-radius-voll);
  border: 1px solid var(--w2b-linie); background: var(--w2b-flaeche);
  font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-s);
  color: var(--w2b-gedaempft);
}
.schrittleiste__zahl{
  display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
  background: var(--w2b-linie-zart); color: var(--w2b-graphit);
  font-family: var(--w2b-daten); font-size: var(--w2b-schrift-xs);
}
.schrittleiste .ist-hier{ border-color: var(--w2b-primaer); color: var(--w2b-tinte); }
.schrittleiste .ist-hier .schrittleiste__zahl{ background: var(--w2b-primaer); color: var(--w2b-primaer-auf); }
.schrittleiste .ist-fertig{ color: var(--w2b-primaer); border-color: var(--w2b-primaer-schleier); }
.schrittleiste .ist-fertig .schrittleiste__zahl{ background: var(--w2b-primaer-schleier); color: var(--w2b-primaer); }

.quellen{ display: grid; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr)); gap: var(--w2b-raum-3); }
.quelle{
  display: flex; flex-direction: column; gap: var(--w2b-raum-2); cursor: pointer;
  padding: var(--w2b-raum-4); border: 1.5px solid var(--w2b-linie); border-radius: var(--w2b-radius-m);
  background: var(--w2b-flaeche);
}
.quelle input{ position: absolute; opacity: 0; pointer-events: none; }
.quelle--gewaehlt{ border-color: var(--w2b-primaer); background: var(--w2b-primaer-schleier); }
.quelle__kopf{ display: flex; align-items: center; gap: var(--w2b-raum-2); }
.quelle__name{ font-family: var(--w2b-anzeige); font-weight: 600; font-size: var(--w2b-schrift-l); }
.quelle__text{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }

.drei{ display: grid; grid-template-columns: 1fr 90px 90px; gap: var(--w2b-raum-3); }
@media (max-width: 560px){ .drei{ grid-template-columns: 1fr; } }

.vorschlaege{ display: grid; grid-template-columns: repeat(auto-fill, minmax(244px, 1fr)); gap: var(--w2b-raum-3); }
.vorschlag{
  display: flex; flex-direction: column; gap: var(--w2b-raum-2);
  padding: var(--w2b-raum-3) var(--w2b-raum-4);
  border: 1.5px dashed var(--w2b-sekundaer); border-radius: var(--w2b-radius-m);
  background: var(--w2b-sekundaer-schleier);
}
.vorschlag--bestaetigt{ border-style: solid; border-color: var(--w2b-linie); background: var(--w2b-flaeche); }
.vorschlag--leer{ border-color: var(--w2b-fehler); background: var(--w2b-fehler-flaeche); }
.vorschlag__kopf{ display: flex; align-items: center; gap: var(--w2b-raum-2); flex-wrap: wrap; }
.vorschlag__marke{
  font-family: var(--w2b-daten); font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase;
  padding: 1px 7px; border-radius: var(--w2b-radius-voll);
  border: 1px solid var(--w2b-sekundaer-text); color: var(--w2b-sekundaer-text);
}
.vorschlag--bestaetigt .vorschlag__marke{ border-color: var(--w2b-primaer); color: var(--w2b-primaer); }
.vorschlag--leer .vorschlag__marke{ border-color: var(--w2b-fehler); color: var(--w2b-fehler); }
.vorschlag__quelle{ font-family: var(--w2b-daten); font-size: 10px; color: var(--w2b-gedaempft); overflow-wrap: anywhere; line-height: 1.45; }

.pruefgitter{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: var(--w2b-raum-4); align-items: start; }
@media (max-width: 900px){ .pruefgitter{ grid-template-columns: 1fr; } }
.werteliste{ margin: 0; display: grid; grid-template-columns: auto 1fr; }
.werteliste dt, .werteliste dd{ padding: 8px var(--w2b-raum-4); border-bottom: 1px solid var(--w2b-linie-zart); margin: 0; display: flex; align-items: center; }
.werteliste dt{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.werteliste dd{ justify-content: flex-end; font-family: var(--w2b-daten); font-size: var(--w2b-schrift-s); font-variant-numeric: tabular-nums; }
.tafel__fussnote{ padding: var(--w2b-raum-3) var(--w2b-raum-4); font-size: var(--w2b-schrift-xs); color: var(--w2b-gedaempft); }
</style>
