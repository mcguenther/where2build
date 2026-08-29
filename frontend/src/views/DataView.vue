<template>
  <div class="stapel">
    <div class="seitenkopf">
      <div>
        <p class="marke-klein">Sicherung und Umzug</p>
        <h1>Daten</h1>
        <p class="seitenkopf__unter">
          Alles, was ihr hier eingebt, liegt im Speicher dieses Browsers — kein Konto, kein
          Server. Zum Mitnehmen auf einen anderen Rechner oder als Sicherung gibt es den
          Austausch als JSON.
        </p>
      </div>
    </div>

    <div class="zweispalt">
      <section class="tafel">
        <div class="tafel__kopf"><h3>Ausgeben</h3><div class="dehnen"></div><span class="chip">{{ groesse }}</span></div>
        <div class="tafel__leib stapel">
          <p class="hinweis">
            Der vollständige Stand: Grundstücke samt Geometrie und Baukörperlage, Haustypen,
            Ziele und Wegezeiten.
          </p>
          <textarea class="datenfeld" readonly :value="ausgabe" aria-label="Ausgegebene Daten als JSON"></textarea>
          <div class="reihe">
            <button type="button" class="knopf" @click="kopieren">In die Zwischenablage</button>
            <button type="button" class="knopf knopf--zweit" @click="alsDatei">Als Datei sichern</button>
          </div>
          <p v-if="meldungAus" class="band" :class="{ 'band--fehler': fehlerAus, 'band--gut': !fehlerAus }">{{ meldungAus }}</p>
        </div>
      </section>

      <section class="tafel">
        <div class="tafel__kopf"><h3>Einlesen</h3></div>
        <div class="tafel__leib stapel">
          <p class="hinweis">
            JSON einfügen oder eine gesicherte Datei wählen. Der bisherige Stand wird ersetzt —
            vorher ausgeben, wenn er noch gebraucht wird.
          </p>
          <textarea class="datenfeld" v-model="eingabe"
                    placeholder="Hier den gesicherten JSON-Stand einfügen"
                    aria-label="Einzulesende Daten als JSON"></textarea>
          <div class="reihe">
            <button type="button" class="knopf" @click="einlesen">Einlesen</button>
            <label class="knopf knopf--zweit dateiwahl">
              Datei wählen
              <input type="file" accept="application/json,.json" @change="datei">
            </label>
          </div>
          <p v-if="meldungEin" class="band" :class="{ 'band--fehler': fehlerEin, 'band--gut': !fehlerEin }">{{ meldungEin }}</p>
        </div>
      </section>
    </div>

    <section class="tafel">
      <div class="tafel__kopf"><h3>Zurücksetzen</h3></div>
      <div class="tafel__leib reihe">
        <p class="hinweis" style="flex:1; min-width: 260px">
          Löscht den Browser-Speicher und stellt die vier Beispielgrundstücke wieder her.
        </p>
        <button type="button" class="knopf knopf--still" @click="zuruecksetzen">
          Auf Beispieldaten zurücksetzen
        </button>
      </div>
    </section>
  </div>
</template>

<script>
import { state, exportJson, importJson, resetToSample } from "../lib/store.js";

export default {
  name: "DataView",
  data() {
    return { eingabe: "", meldungAus: "", fehlerAus: false, meldungEin: "", fehlerEin: false, stand: 0 };
  },
  computed: {
    ausgabe() {
      this.stand; // re-read after an import or reset
      return exportJson();
    },
    groesse() { return `${(new Blob([this.ausgabe]).size / 1024).toFixed(1)} kB`; }
  },
  methods: {
    async kopieren() {
      try {
        await navigator.clipboard.writeText(this.ausgabe);
        this.melden("aus", "In die Zwischenablage gelegt.");
      } catch {
        this.melden("aus", "Der Browser lässt das Kopieren nicht zu — den Text im Feld markieren und Strg+C.", true);
      }
    },
    alsDatei() {
      try {
        const a = document.createElement("a");
        const blob = new Blob([this.ausgabe], { type: "application/json" });
        a.href = URL.createObjectURL(blob);
        a.download = `where2build-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        this.melden("aus", "Datei gesichert.");
      } catch {
        this.melden("aus", "Sichern hier nicht möglich — bitte über die Zwischenablage.", true);
      }
    },
    einlesen() {
      try {
        const d = importJson(this.eingabe);
        this.stand++;
        this.eingabe = "";
        this.melden("ein", `Übernommen: ${d.grundstuecke.length} Grundstücke, ${d.haustypen.length} Haustypen, ${d.ziele.length} Ziele.`);
      } catch (fehler) {
        this.melden("ein", `Nicht übernommen: ${fehler.message}`, true);
      }
    },
    async datei(ereignis) {
      const f = ereignis.target.files?.[0];
      if (!f) return;
      try {
        this.eingabe = await f.text();
        this.einlesen();
      } catch {
        this.melden("ein", "Die Datei ließ sich nicht lesen.", true);
      }
      ereignis.target.value = "";
    },
    zuruecksetzen() {
      if (!window.confirm("Alles zurücksetzen? Der jetzige Stand geht verloren.")) return;
      resetToSample();
      this.stand++;
      this.melden("ein", "Auf die vier Beispielgrundstücke zurückgesetzt.");
    },
    melden(wo, text, fehler = false) {
      if (wo === "aus") { this.meldungAus = text; this.fehlerAus = fehler; }
      else { this.meldungEin = text; this.fehlerEin = fehler; }
    }
  }
};
</script>

<style scoped>
.seitenkopf__unter{ margin-top: var(--w2b-raum-2); color: var(--w2b-graphit); font-size: var(--w2b-schrift-s); max-width: 68ch; }
.hinweis{ font-size: var(--w2b-schrift-s); color: var(--w2b-graphit); }
.zweispalt{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--w2b-raum-4); align-items: start; }
.datenfeld{ min-height: 210px; font-size: 11.5px; line-height: 1.5; }
.dateiwahl{ cursor: pointer; display: inline-flex; align-items: center; }
.dateiwahl input{ display: none; }
</style>
