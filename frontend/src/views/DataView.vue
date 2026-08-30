<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Sicherung und Umzug</p>
        <h1>Daten</h1>
        <p class="page-head__sub">
          Alles, was ihr hier eingebt, liegt im Speicher dieses Browsers — kein Konto, kein
          Server. Zum Mitnehmen auf einen anderen Rechner oder als Sicherung gibt es den
          Austausch als JSON.
        </p>
      </div>
    </div>

    <div class="two-columns">
      <section class="panel">
        <div class="panel__head"><h3>Ausgeben</h3><div class="spacer"></div><span class="chip">{{ size }}</span></div>
        <div class="panel__body stack">
          <p class="hint">
            Der vollständige Stand: Grundstücke samt Geometrie und Baukörperlage, Haustypen,
            Ziele und Wegezeiten.
          </p>
          <textarea class="data-field" readonly :value="output" aria-label="Ausgegebene Daten als JSON"></textarea>
          <div class="row">
            <button type="button" class="btn" @click="copyToClipboard">In die Zwischenablage</button>
            <button type="button" class="btn btn--secondary" @click="downloadFile">Als Datei sichern</button>
          </div>
          <p v-if="exportMessage" class="notice" :class="{ 'notice--error': exportFailed, 'notice--good': !exportFailed }">{{ exportMessage }}</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Einlesen</h3></div>
        <div class="panel__body stack">
          <p class="hint">
            JSON einfügen oder eine gesicherte Datei wählen. Der bisherige Stand wird ersetzt —
            vorher ausgeben, wenn er noch gebraucht wird.
          </p>
          <textarea class="data-field" v-model="input"
                    placeholder="Hier den gesicherten JSON-Stand einfügen"
                    aria-label="Einzulesende Daten als JSON"></textarea>
          <div class="row">
            <button type="button" class="btn" @click="runImport">Einlesen</button>
            <label class="btn btn--secondary file-picker">
              Datei wählen
              <input type="file" accept="application/json,.json" @change="pickFile">
            </label>
          </div>
          <p v-if="importMessage" class="notice" :class="{ 'notice--error': importFailed, 'notice--good': !importFailed }">{{ importMessage }}</p>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel__head"><h3>Alles löschen</h3></div>
      <div class="panel__body row">
        <p class="hint" style="flex:1; min-width: 260px">
          Leert den Browser-Speicher: alle Grundstücke, Haustypen und Ziele. Vorher
          ausgeben, wenn der Stand noch gebraucht wird.
        </p>
        <button type="button" class="btn btn--quiet" @click="clearAll">
          Alles löschen
        </button>
      </div>
    </section>
  </div>
</template>

<script>
import { exportJson, importJson, clear } from "../lib/store.js";

export default {
  name: "DataView",
  data() {
    return { input: "", exportMessage: "", exportFailed: false, importMessage: "", importFailed: false, revision: 0 };
  },
  computed: {
    output() {
      this.revision; // re-read after an import or reset
      return exportJson();
    },
    size() { return `${(new Blob([this.output]).size / 1024).toFixed(1)} kB`; }
  },
  methods: {
    async copyToClipboard() {
      try {
        await navigator.clipboard.writeText(this.output);
        this.report("export", "In die Zwischenablage gelegt.");
      } catch {
        this.report("export", "Der Browser lässt das Kopieren nicht zu — den Text im Feld markieren und Strg+C.", true);
      }
    },
    downloadFile() {
      try {
        const a = document.createElement("a");
        const blob = new Blob([this.output], { type: "application/json" });
        a.href = URL.createObjectURL(blob);
        a.download = `where2build-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        this.report("export", "Datei gesichert.");
      } catch {
        this.report("export", "Sichern hier nicht möglich — bitte über die Zwischenablage.", true);
      }
    },
    runImport() {
      try {
        const d = importJson(this.input);
        this.revision++;
        this.input = "";
        this.report("import", `Übernommen: ${d.plots.length} Grundstücke, ${d.houseTypes.length} Haustypen, ${d.destinations.length} Ziele.`);
      } catch (error) {
        this.report("import", `Nicht übernommen: ${error.message}`, true);
      }
    },
    async pickFile(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        this.input = await file.text();
        this.runImport();
      } catch {
        this.report("import", "Die Datei ließ sich nicht lesen.", true);
      }
      event.target.value = "";
    },
    clearAll() {
      if (!window.confirm("Alles löschen? Der jetzige Stand geht verloren.")) return;
      clear();
      this.revision++;
      this.report("import", "Der Speicher ist geleert.");
    },
    report(where, text, failed = false) {
      if (where === "export") { this.exportMessage = text; this.exportFailed = failed; }
      else { this.importMessage = text; this.importFailed = failed; }
    }
  }
};
</script>

<style scoped>
.page-head__sub{ margin-top: var(--w2b-space-2); color: var(--w2b-graphite); font-size: var(--w2b-text-s); max-width: 68ch; }
.hint{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.two-columns{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--w2b-space-4); align-items: start; }
.data-field{ min-height: 210px; font-size: 11.5px; line-height: 1.5; }
.file-picker{ cursor: pointer; display: inline-flex; align-items: center; }
.file-picker input{ display: none; }
</style>
