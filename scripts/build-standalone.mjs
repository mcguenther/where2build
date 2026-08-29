/* Wickelt mockup/app.html (artefakt-fertig, ohne Rahmen) in eine vollständige
   HTML-Seite für lokales Öffnen, Tests und Screenshots. Eine Quelle, zwei Ziele. */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const quelle = readFileSync(resolve(wurzel, "mockup/app.html"), "utf8");

const seite = `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{color-scheme:light dark}
  *{box-sizing:border-box}
  body{margin:0;font:14px system-ui,-apple-system,sans-serif}
  img{max-width:100%}
  [hidden]{display:none!important}
</style>
${quelle}
</body>
</html>
`;

mkdirSync(resolve(wurzel, "mockup"), { recursive: true });
writeFileSync(resolve(wurzel, "mockup/index.html"), seite);
console.log(`mockup/index.html geschrieben — ${(seite.length / 1024).toFixed(1)} kB`);
