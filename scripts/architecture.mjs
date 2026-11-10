// The C4 diagrams of where2build, from the Structurizr DSL to pictures.
//
//   node scripts/architecture.mjs            DSL -> JSON -> layout -> HTML + PNG
//   node scripts/architecture.mjs --no-dsl   start from the committed workspace.json
//
// docs/architektur/workspace.dsl is the source. It is parsed by Structurizr's
// own parser (Java, fetched through Maven into scripts/architecture/lib), so
// what passes here passes in Structurizr Lite too. The layout is computed once,
// here, with ELK -- the page carries finished coordinates and no layout library,
// and the PNGs are screenshots of that same page, so the pictures in the docs
// and the interactive page can never disagree.
//
// Text is measured in the same Chromium that takes the screenshots, in a
// metric-compatible font stack (Liberation Sans = Arial = Helvetica), and the
// line breaks are stored, so another machine draws the same boxes.
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import ELK from "elkjs/lib/elk.bundled.js";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const here = join(root, "scripts", "architecture");
const outDir = join(root, "docs", "architektur");
const dslPath = join(outDir, "workspace.dsl");
const jsonPath = join(outDir, "workspace.json");
const htmlPath = join(outDir, "architektur.html");
const fragmentPath = process.env.W2B_ARCH_FRAGMENT || "";

const FONT = '"Liberation Sans", Arial, Helvetica, sans-serif';

// ---------------------------------------------------------------------------
// 1. DSL -> workspace.json
// ---------------------------------------------------------------------------
function exportDsl() {
  const lib = join(here, "lib");
  const hasJars = existsSync(lib) && readdirSync(lib).some(f => f.startsWith("structurizr-dsl"));
  if (!hasJars) {
    console.log("Fetching the Structurizr DSL parser through Maven …");
    execFileSync("mvn", ["-q", "-f", join(here, "pom.xml"), "dependency:copy-dependencies",
      `-DoutputDirectory=${lib}`], { stdio: "inherit" });
  }
  const out = execFileSync("java", ["-cp", `${lib}/*`, join(here, "DslToJson.java"), dslPath, jsonPath],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  console.log(`workspace.json: ${out.trim()}`);
}

if (!process.argv.includes("--no-dsl")) exportDsl();
else if (statSync(dslPath).mtimeMs > statSync(jsonPath).mtimeMs) {
  console.warn("Warning: workspace.dsl is newer than workspace.json -- run without --no-dsl.");
}
const workspace = JSON.parse(readFileSync(jsonPath, "utf8"));

// ---------------------------------------------------------------------------
// 2. The model as one flat index
// ---------------------------------------------------------------------------
const elements = new Map();
const relationships = new Map();
const tagsOf = s => (s || "").split(",").map(t => t.trim()).filter(Boolean);

function addElement(raw, type, parentId = null, extra = {}) {
  const el = {
    id: raw.id, type, parentId,
    name: raw.name || "", description: raw.description || "", technology: raw.technology || "",
    tags: tagsOf(raw.tags), group: raw.group || "", url: raw.url || "", ...extra
  };
  elements.set(raw.id, el);
  for (const r of raw.relationships || []) relationships.set(r.id, r);
  return el;
}

for (const p of workspace.model.people || []) addElement(p, "person");
for (const s of workspace.model.softwareSystems || []) {
  addElement(s, "system");
  for (const c of s.containers || []) {
    addElement(c, "container", s.id);
    for (const k of c.components || []) addElement(k, "component", c.id);
  }
}
function walkDeployment(node, parentId) {
  addElement(node, "node", parentId, { environment: node.environment });
  for (const ci of node.containerInstances || []) addElement(ci, "instance", node.id, { ref: ci.containerId });
  for (const si of node.softwareSystemInstances || []) addElement(si, "instance", node.id, { ref: si.softwareSystemId });
  for (const inf of node.infrastructureNodes || []) addElement(inf, "infrastructure", node.id);
  for (const child of node.children || []) walkDeployment(child, node.id);
}
for (const n of workspace.model.deploymentNodes || []) walkDeployment(n, null);

/** What a box shows: an instance shows the element it is an instance of. */
const subjectOf = el => (el.type === "instance" ? elements.get(el.ref) : el);

const TYPE_LABEL = {
  person: "Person", system: "Softwaresystem", container: "Container",
  component: "Komponente", infrastructure: "Infrastruktur", node: "Verteilungsknoten"
};

function isExternal(el) {
  const s = subjectOf(el);
  return s.type === "system" && s.tags.includes("Extern");
}

function metaLine(el) {
  const s = subjectOf(el);
  let kind = TYPE_LABEL[s.type];
  if (s.type === "system" && isExternal(s)) kind = "Softwaresystem, extern";
  return s.technology ? `[${kind}: ${s.technology}]` : `[${kind}]`;
}

// Styles as Structurizr applies them: in the order of the element's own tags.
const styleByTag = new Map((workspace.views.configuration?.styles?.elements || []).map(s => [s.tag, s]));
function styleOf(el) {
  const s = subjectOf(el);
  const merged = { background: "#456b52", color: "#ffffff", shape: "RoundedBox", border: "solid" };
  const tags = [...s.tags];
  if (el.type === "instance") tags.push(...el.tags);
  for (const t of tags) Object.assign(merged, Object.fromEntries(
    Object.entries(styleByTag.get(t) || {}).filter(([k]) => ["background", "color", "shape", "border"].includes(k))));
  return merged;
}

// Which view a box drills down into.
const allViews = [
  ...(workspace.views.systemContextViews || []).map(v => ({ ...v, kind: "context", scope: v.softwareSystemId })),
  ...(workspace.views.containerViews || []).map(v => ({ ...v, kind: "container", scope: v.softwareSystemId })),
  ...(workspace.views.componentViews || []).map(v => ({ ...v, kind: "component", scope: v.containerId })),
  ...(workspace.views.dynamicViews || []).map(v => ({ ...v, kind: "dynamic", scope: v.elementId })),
  ...(workspace.views.deploymentViews || []).map(v => ({ ...v, kind: "deployment", scope: v.softwareSystemId }))
].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

const drillTarget = new Map();
for (const v of allViews) if (v.kind === "container" || v.kind === "component") drillTarget.set(v.scope, v.key);

// ---------------------------------------------------------------------------
// 3. One diagram spec per view: boxes, boundaries, edges
// ---------------------------------------------------------------------------
const VIEW_SLUG = { context: "kontext", container: "container", dynamic: "ablauf", deployment: "verteilung" };
const slugOf = v => (v.kind === "component" ? v.key.toLowerCase() : VIEW_SLUG[v.kind]);

function boundariesFor(view, el) {
  if (view.kind === "deployment") {
    const chain = [];
    for (let p = elements.get(el.parentId); p; p = elements.get(p.parentId)) chain.unshift(`n:${p.id}`);
    return chain;
  }
  const s = el;
  const grouped = (owner, g) => (g ? [`g:${owner}:${g}`] : []);
  if (view.kind === "context") return grouped("", s.group);
  if (view.kind === "container" || view.kind === "dynamic") {
    if (s.parentId === view.scope) return [`b:${view.scope}`, ...grouped(view.scope, s.group)];
    return grouped("", s.group);
  }
  // component view: the scoped container sits inside its system, beside its siblings
  const container = elements.get(view.scope);
  const system = container.parentId;
  if (s.parentId === view.scope) return [`b:${system}`, `b:${view.scope}`, ...grouped(view.scope, s.group)];
  // Siblings go without their group: a group box holding the web server (an
  // upstream) and the database (a downstream) forces every edge into a loop.
  if (s.parentId === system) return [`b:${system}`];
  return grouped("", s.group);
}

function boundaryInfo(id) {
  const [kind, ...rest] = id.split(":");
  if (kind === "b") {
    const el = elements.get(rest[0]);
    return { kind: el.type === "system" ? "system" : "container", title: el.name,
      sub: el.type === "system" ? "[Softwaresystem]" : `[Container: ${el.technology}]`, elId: el.id };
  }
  if (kind === "g") return { kind: "group", title: rest.slice(1).join(":"), sub: "" };
  const el = elements.get(rest[0]);
  return { kind: "node", title: el.name, elId: el.id,
    sub: [el.technology && `[${el.technology}]`, el.description].filter(Boolean).join(" · ") };
}

function buildSpec(view) {
  const ids = (view.elements || []).map(e => e.id);
  const boxes = ids.map(id => elements.get(id)).filter(el => el && el.type !== "node");
  const edges = (view.relationships || []).map((r, i) => {
    const rel = relationships.get(r.id);
    const linked = rel.linkedRelationshipId ? relationships.get(rel.linkedRelationshipId) : null;
    return {
      id: `e${i}`, relId: rel.id, src: rel.sourceId, dst: rel.destinationId,
      description: r.description || rel.description || linked?.description || "",
      technology: rel.technology || linked?.technology || "",
      order: r.order ? Number(r.order) : null,
      dashed: false
    };
  }).filter(e => boxes.some(b => b.id === e.src) && boxes.some(b => b.id === e.dst));
  return { view, boxes, edges };
}

// ---------------------------------------------------------------------------
// 4. Text, measured in Chromium
// ---------------------------------------------------------------------------
const browser = await chromium.launch();
const measurePage = await browser.newPage();
await measurePage.setContent(`<canvas></canvas>`);

async function wrapAll(requests) {
  return measurePage.evaluate(reqs => {
    const ctx = document.querySelector("canvas").getContext("2d");
    return reqs.map(({ text, font, max }) => {
      ctx.font = font;
      const lines = [];
      for (const para of String(text).split("\n")) {
        let line = "";
        for (const word of para.split(/\s+/).filter(Boolean)) {
          const trial = line ? `${line} ${word}` : word;
          if (ctx.measureText(trial).width <= max) { line = trial; continue; }
          if (line) lines.push(line);
          // a word wider than the box is cut, not allowed to spill
          let rest = word;
          while (ctx.measureText(rest).width > max) {
            let n = rest.length;
            while (n > 1 && ctx.measureText(rest.slice(0, n)).width > max) n--;
            lines.push(rest.slice(0, n));
            rest = rest.slice(n);
          }
          line = rest;
        }
        if (line) lines.push(line);
      }
      const width = Math.max(0, ...lines.map(l => ctx.measureText(l).width));
      return { lines, width: Math.ceil(width) };
    });
  }, requests);
}

const T = {
  name: { font: `bold 14px ${FONT}`, lh: 17 },
  meta: { font: `11px ${FONT}`, lh: 13.5 },
  desc: { font: `11.5px ${FONT}`, lh: 14.5 },
  edge: { font: `11px ${FONT}`, lh: 13.5 },
  edgeTech: { font: `italic 10px ${FONT}`, lh: 12.5 },
  bTitle: { font: `bold 13px ${FONT}`, lh: 16 },
  bSub: { font: `11px ${FONT}`, lh: 13.5 }
};

const WIDTH = { person: 220, system: 240, container: 240, component: 230, infrastructure: 220 };
const PAD = 12;
const EDGE_LABEL_MAX = 170;

function shapeExtra(shape) {
  if (shape === "Person") return { top: 40, bottom: 0 };
  if (shape === "Cylinder") return { top: 14, bottom: 6 };
  if (shape === "WebBrowser") return { top: 14, bottom: 0 };
  if (shape === "Folder") return { top: 10, bottom: 0 };
  return { top: 0, bottom: 0 };
}

async function measureSpec(spec) {
  const reqs = [];
  const at = [];
  for (const b of spec.boxes) {
    const s = subjectOf(b);
    const w = WIDTH[s.type] || 230;
    const inner = w - 2 * PAD;
    at.push(["box", b.id, w]);
    reqs.push({ text: s.name, font: T.name.font, max: inner });
    reqs.push({ text: metaLine(b), font: T.meta.font, max: inner });
    reqs.push({ text: s.description, font: T.desc.font, max: inner });
  }
  for (const e of spec.edges) {
    const text = e.order ? `${e.order}. ${e.description}` : e.description;
    reqs.push({ text, font: T.edge.font, max: EDGE_LABEL_MAX });
    reqs.push({ text: e.technology ? `[${e.technology}]` : "", font: T.edgeTech.font, max: EDGE_LABEL_MAX });
  }
  const res = await wrapAll(reqs);
  let i = 0;
  const boxText = new Map();
  for (const b of spec.boxes) {
    const [name, meta, desc] = [res[i++], res[i++], res[i++]];
    const s = subjectOf(b);
    const style = styleOf(b);
    const extra = shapeExtra(style.shape);
    const w = WIDTH[s.type] || 230;
    const h = Math.ceil(extra.top + PAD + name.lines.length * T.name.lh + 3 + meta.lines.length * T.meta.lh
      + (desc.lines.length ? 7 + desc.lines.length * T.desc.lh : 0) + PAD + extra.bottom);
    boxText.set(b.id, { w, h, name: name.lines, meta: meta.lines, desc: desc.lines, style, extraTop: extra.top });
  }
  for (const e of spec.edges) {
    const [d, t] = [res[i++], res[i++]];
    e.labelLines = d.lines;
    e.techLines = t.lines;
    e.labelW = Math.max(d.width, t.width) + 8;
    e.labelH = d.lines.length * T.edge.lh + t.lines.length * T.edgeTech.lh + 4;
  }
  return boxText;
}

// ---------------------------------------------------------------------------
// 5. Layout with ELK
// ---------------------------------------------------------------------------
const elk = new ELK();

async function layoutSpec(spec) {
  const { view } = spec;
  const boxText = await measureSpec(spec);

  // the boundary tree
  const bNodes = new Map();
  const rootChildren = [];
  const ensureBoundary = async (path) => {
    let parentList = rootChildren;
    for (const bid of path) {
      if (!bNodes.has(bid)) {
        const info = boundaryInfo(bid);
        const node = { id: bid, info, children: [], parentList };
        bNodes.set(bid, node);
        parentList.push(node);
      }
      parentList = bNodes.get(bid).children;
    }
    return parentList;
  };
  for (const b of spec.boxes) (await ensureBoundary(boundariesFor(view, b))).push({ id: b.id, box: true });

  // boundary labels are wrapped to the narrowest width a boundary can have
  const bList = [...bNodes.values()];
  const bReqs = bList.flatMap(n => [
    { text: n.info.title + (n.info.kind === "group" ? "" : ""), font: T.bTitle.font, max: 250 },
    { text: n.info.sub || "", font: T.bSub.font, max: 250 }
  ]);
  const bRes = await wrapAll(bReqs);
  bList.forEach((n, k) => {
    n.titleLines = bRes[2 * k].lines;
    n.subLines = bRes[2 * k + 1].lines;
    n.labelW = Math.max(bRes[2 * k].width, bRes[2 * k + 1].width);
    n.padTop = 12 + n.titleLines.length * T.bTitle.lh + n.subLines.length * T.bSub.lh + 12;
  });

  const toElk = item => {
    if (item.box) {
      const t = boxText.get(item.id);
      return { id: item.id, width: t.w, height: t.h };
    }
    const n = bNodes.get(item.id);
    return {
      id: item.id,
      layoutOptions: {
        "elk.padding": `[top=${n.padTop},left=18,bottom=18,right=18]`,
        "elk.nodeSize.constraints": "[MINIMUM_SIZE]",
        "elk.nodeSize.minimum": `(${n.labelW + 36}, 60)`
      },
      children: n.children.map(toElk)
    };
  };

  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.json.edgeCoords": "ROOT",
      "elk.json.shapeCoords": "ROOT",
      "elk.padding": "[top=24,left=24,bottom=24,right=24]",
      "elk.spacing.nodeNode": "36",
      "elk.layered.spacing.nodeNodeBetweenLayers": "64",
      "elk.spacing.edgeNode": "18",
      "elk.spacing.edgeEdge": "10",
      "elk.layered.spacing.edgeEdgeBetweenLayers": "10",
      "elk.layered.spacing.edgeNodeBetweenLayers": "18",
      "elk.spacing.edgeLabel": "4",
      "elk.edgeLabels.placement": "CENTER",
      "elk.layered.edgeLabels.sideSelection": "SMART_DOWN",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.layered.crossingMinimization.thoroughness": "40",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
      "elk.layered.mergeEdges": "false"
    },
    children: rootChildren.map(toElk),
    edges: spec.edges.map(e => ({
      id: e.id, sources: [e.src], targets: [e.dst],
      labels: [{ id: `${e.id}l`, text: e.description || "·", width: e.labelW, height: e.labelH }]
    }))
  };

  const laid = await elk.layout(graph);

  const pos = new Map();
  const walk = n => {
    for (const c of n.children || []) { pos.set(c.id, c); walk(c); }
  };
  walk(laid);

  const boxes = spec.boxes.map(b => {
    const p = pos.get(b.id);
    const t = boxText.get(b.id);
    const s = subjectOf(b);
    return {
      id: b.id, el: s.id, x: p.x, y: p.y, w: p.width, h: p.height,
      shape: t.style.shape, bg: t.style.background, fg: t.style.color,
      dashed: t.style.border === "dashed", extraTop: t.extraTop,
      name: t.name, meta: t.meta, desc: t.desc,
      drill: drillTarget.get(s.id) && drillTarget.get(s.id) !== view.key ? drillTarget.get(s.id) : null
    };
  });

  const boundaries = bList.map(n => {
    const p = pos.get(n.id);
    let depth = 0;
    for (let q = n.parentList; q !== rootChildren; depth++) q = [...bNodes.values()].find(m => m.children === q).parentList;
    return {
      id: n.id, kind: n.info.kind, el: n.info.elId || null, x: p.x, y: p.y, w: p.width, h: p.height,
      title: n.titleLines, sub: n.subLines, depth
    };
  }).sort((a, b) => a.depth - b.depth);

  const laidEdges = new Map((laid.edges || []).map(e => [e.id, e]));
  const edges = spec.edges.map(e => {
    const le = laidEdges.get(e.id);
    const sec = le.sections?.[0];
    const points = sec ? [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map(p => [round(p.x), round(p.y)]) : [];
    const lab = le.labels?.[0];
    return {
      id: e.id, rel: e.relId, src: e.src, dst: e.dst, order: e.order, points,
      label: lab ? { x: round(lab.x), y: round(lab.y), w: e.labelW, h: e.labelH } : null,
      lines: e.labelLines, tech: e.techLines, description: e.description, technology: e.technology
    };
  });

  return {
    key: view.key, slug: slugOf(view), kind: view.kind, title: view.name || view.key,
    description: view.description || "", scope: view.scope || null,
    width: Math.ceil(laid.width), height: Math.ceil(laid.height),
    boxes: boxes.map(b => ({ ...b, x: round(b.x), y: round(b.y), w: round(b.w), h: round(b.h) })),
    boundaries: boundaries.map(b => ({ ...b, x: round(b.x), y: round(b.y), w: round(b.w), h: round(b.h) })),
    edges
  };
}
const round = v => Math.round(v * 10) / 10;

// ---------------------------------------------------------------------------
// 6. The page
// ---------------------------------------------------------------------------
const views = [];
for (const v of allViews) {
  const laid = await layoutSpec(buildSpec(v));
  views.push(laid);
  console.log(`${laid.slug.padEnd(11)} ${laid.boxes.length} boxes, ${laid.edges.length} edges, ${laid.width}×${laid.height}`);
}

// Everything the side panel can say about an element, for every element on a view.
const onViews = new Map();
for (const v of views) for (const b of v.boxes) {
  if (!onViews.has(b.el)) onViews.set(b.el, []);
  if (!onViews.get(b.el).includes(v.slug)) onViews.get(b.el).push(v.slug);
}
const catalogue = {};
for (const [id, views_] of onViews) {
  const el = elements.get(id);
  const parent = el.parentId ? elements.get(el.parentId) : null;
  catalogue[id] = {
    name: el.name, type: el.type, kind: metaLine(el).slice(1, -1), description: el.description,
    technology: el.technology, group: el.group, parent: parent?.name || "",
    tags: el.tags.filter(t => !["Element", "Person", "Software System", "Container", "Component"].includes(t)),
    external: isExternal(el), views: views_,
    drill: drillTarget.get(id) ? views.find(v => v.key === drillTarget.get(id)).slug : null
  };
}

const data = {
  name: workspace.name, description: workspace.description,
  generated: new Date().toISOString().slice(0, 10),
  views, elements: catalogue
};

const css = readFileSync(join(here, "viewer.css"), "utf8");
const js = readFileSync(join(here, "viewer.js"), "utf8");
const body = readFileSync(join(here, "viewer.html"), "utf8");
const head = `<title>where2build Architektur</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
${css}
</style>`;
const content = `${body}
<script>
window.C4_DATA = ${JSON.stringify(data).replace(/</g, "\\u003c")};
</script>
<script>
${js}
</script>`;
const page = `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<!-- Generated by scripts/architecture.mjs from workspace.dsl. Do not edit by hand. -->
${head}
</head>
<body>
${content}
</body>
</html>
`;
mkdirSync(outDir, { recursive: true });
writeFileSync(htmlPath, page);
// The same page without its own skeleton, for hosts that wrap one around it.
if (fragmentPath) writeFileSync(fragmentPath, `${head}\n${content}\n`);
console.log(`${htmlPath} (${Math.round(page.length / 1024)} KiB)`);

// ---------------------------------------------------------------------------
// 7. Pictures of the same page
// ---------------------------------------------------------------------------
const scale = Number(process.env.W2B_ARCH_SCALE || 2);
for (const v of views) {
  const ctx = await browser.newContext({
    viewport: { width: Math.min(v.width + 80, 4000), height: 900 },
    deviceScaleFactor: scale, colorScheme: "light"
  });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", e => errors.push(e.message));
  p.on("console", m => m.type() === "error" && errors.push(m.text()));
  await p.goto(`${pathToFileURL(htmlPath).href}?bild#${v.slug}`);
  await p.waitForSelector("#zeichnung svg[data-fertig]");
  const shot = join(outDir, `c4-${v.slug}.png`);
  await p.locator("#zeichnung svg").screenshot({ path: shot });
  if (errors.length) throw new Error(`${v.slug}: ${errors.join("; ")}`);
  console.log(`  ${shot}`);
  await ctx.close();
}
await browser.close();
