// The interactive C4 page. Everything it draws was laid out by
// scripts/architecture.mjs; this file only draws, pans, zooms and explains.
(function () {
  "use strict";

  const data = window.C4_DATA;
  const pictureMode = /(^|[?&])bild\b/.test(location.search);
  const views = data.views;
  const bySlug = new Map(views.map(v => [v.slug, v]));
  const byKey = new Map(views.map(v => [v.key, v]));
  const $ = id => document.getElementById(id);

  const stage = $("zeichnung");
  const panel = $("tafel");
  const pathBar = $("pfad");
  const stepBar = $("schritte");

  const state = {
    view: null,
    t: { x: 0, y: 0, k: 1 },
    hover: null,          // { kind: "box"|"edge", id }
    selected: null,       // { kind: "box"|"edge", id }
    step: 0,
    timer: null,
    matches: new Set()
  };

  // ---- helpers -------------------------------------------------------
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const el = id => data.elements[id];
  const r1 = n => Math.round(n * 10) / 10;

  function viewEyebrow(v) {
    return { context: "Ebene 1", container: "Ebene 2", component: "Ebene 3", dynamic: "Ablauf", deployment: "Verteilung" }[v.kind];
  }
  function viewTitle(v) {
    if (v.kind === "context") return "Systemkontext";
    if (v.kind === "container") return "Container";
    if (v.kind === "component") return el(v.scope) ? el(v.scope).name : v.title;
    if (v.kind === "dynamic") return "Inserat → Flurstück";
    return "docker compose";
  }

  // ---- drawing -------------------------------------------------------
  function roundedPath(pts, radius) {
    if (pts.length < 2) return "";
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [px, py] = pts[i - 1], [cx, cy] = pts[i], [nx, ny] = pts[i + 1];
      const l1 = Math.hypot(cx - px, cy - py), l2 = Math.hypot(nx - cx, ny - cy);
      const r = Math.min(radius, l1 / 2, l2 / 2);
      const ax = cx - ((cx - px) / l1) * r, ay = cy - ((cy - py) / l1) * r;
      const bx = cx + ((nx - cx) / l2) * r, by = cy + ((ny - cy) / l2) * r;
      d += ` L${r1(ax)},${r1(ay)} Q${cx},${cy} ${r1(bx)},${r1(by)}`;
    }
    const last = pts[pts.length - 1];
    return d + ` L${last[0]},${last[1]}`;
  }

  function shapeSvg(b) {
    const { x, y, w, h, bg } = b;
    const f = `class="form" fill="${bg}"`;
    switch (b.shape) {
      case "Person":
        return `<circle ${f} cx="${x + w / 2}" cy="${y + 19}" r="18"/>` +
          `<rect ${f} x="${x}" y="${y + 32}" width="${w}" height="${h - 32}" rx="24"/>` +
          `<rect class="kontur" x="${x - 3}" y="${y + 29}" width="${w + 6}" height="${h - 26}" rx="26"/>`;
      case "Cylinder":
        return `<path ${f} d="M${x},${y + 9} A${w / 2},9 0 0 1 ${x + w},${y + 9} V${y + h - 9} A${w / 2},9 0 0 1 ${x},${y + h - 9} Z"/>` +
          `<ellipse cx="${x + w / 2}" cy="${y + 9}" rx="${w / 2}" ry="9" fill="${bg}" stroke="rgba(255,255,255,.45)"/>` +
          `<rect class="kontur" x="${x - 3}" y="${y - 3}" width="${w + 6}" height="${h + 6}" rx="12"/>`;
      case "Folder":
        return `<rect ${f} x="${x}" y="${y}" width="78" height="16" rx="4"/>` +
          `<rect ${f} x="${x}" y="${y + 8}" width="${w}" height="${h - 8}" rx="6"/>` +
          `<rect class="kontur" x="${x - 3}" y="${y - 3}" width="${w + 6}" height="${h + 6}" rx="9"/>`;
      case "WebBrowser":
        return `<rect ${f} x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/>` +
          `<line x1="${x}" x2="${x + w}" y1="${y + 16}" y2="${y + 16}" stroke="rgba(255,255,255,.35)"/>` +
          [0, 1, 2].map(i => `<circle cx="${x + 11 + i * 9}" cy="${y + 8}" r="2.6" fill="rgba(255,255,255,.55)"/>`).join("") +
          `<rect class="kontur" x="${x - 3}" y="${y - 3}" width="${w + 6}" height="${h + 6}" rx="11"/>`;
      default:
        return `<rect ${f} x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/>` +
          `<rect class="kontur" x="${x - 3}" y="${y - 3}" width="${w + 6}" height="${h + 6}" rx="11"/>`;
    }
  }

  function boxSvg(b) {
    const cx = b.x + b.w / 2;
    let cursor = b.y + b.extraTop + 12;
    const out = [];
    for (const line of b.name) { out.push(`<text class="name" x="${cx}" y="${r1(cursor + 13)}">${esc(line)}</text>`); cursor += 17; }
    cursor += 3;
    for (const line of b.meta) { out.push(`<text class="meta" x="${cx}" y="${r1(cursor + 10.5)}">${esc(line)}</text>`); cursor += 13.5; }
    if (b.desc.length) cursor += 7;
    for (const line of b.desc) { out.push(`<text class="text" x="${cx}" y="${r1(cursor + 11)}">${esc(line)}</text>`); cursor += 14.5; }
    const drill = b.drill
      ? `<g class="tiefer-g" color="${b.fg}"><title>Doppelklick: tiefere Ebene öffnen</title>` +
        `<rect class="tiefer" x="${b.x + b.w - 26}" y="${b.y + b.extraTop + 7}" width="18" height="18" rx="4"/>` +
        `<path class="tiefer-zeichen" d="M${b.x + b.w - 21},${b.y + b.extraTop + 16} h8 M${b.x + b.w - 17},${b.y + b.extraTop + 12} v8"/></g>`
      : "";
    const cls = ["knoten", b.dashed ? "gestrichelt" : ""].filter(Boolean).join(" ");
    return `<g class="${cls}" data-box="${esc(b.id)}" tabindex="0" role="button" aria-label="${esc(b.name.join(" "))}">` +
      shapeSvg(b) + `<g fill="${b.fg}" text-anchor="middle">${out.join("")}</g>${drill}</g>`;
  }

  function boundarySvg(b) {
    const lines = [];
    let cursor = b.y + 12;
    for (const t of b.title) { lines.push(`<text class="titel" x="${b.x + 12}" y="${cursor + 12}">${esc(t)}</text>`); cursor += 16; }
    for (const t of b.sub) { lines.push(`<text class="unter" x="${b.x + 12}" y="${cursor + 10.5}">${esc(t)}</text>`); cursor += 13.5; }
    const target = b.el && el(b.el) && el(b.el).drill && el(b.el).drill !== state.view.slug ? el(b.el).drill : "";
    return `<g class="rahmen ${b.kind}${target ? " zielbar" : ""}" ${target ? `data-goto="${target}"` : ""}>` +
      `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="${b.kind === "group" ? 10 : 6}"/>${lines.join("")}</g>`;
  }

  function edgeSvg(e) {
    if (!e.points.length) return "";
    const d = roundedPath(e.points, 7);
    let label = "";
    if (e.label && (e.lines.length || e.tech.length)) {
      const { x, y, w, h } = e.label;
      const cx = x + w / 2;
      let cursor = y + 2;
      const t = [];
      for (const line of e.lines) { t.push(`<text x="${cx}" y="${r1(cursor + 10.5)}">${esc(line)}</text>`); cursor += 13.5; }
      for (const line of e.tech) { t.push(`<text class="tech" x="${cx}" y="${r1(cursor + 9.5)}">${esc(line)}</text>`); cursor += 12.5; }
      label = `<g class="schild" text-anchor="middle"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3"/>${t.join("")}</g>`;
    }
    return `<g class="kante" data-edge="${e.id}">` +
      `<path class="linie" d="${d}" marker-end="url(#spitze)"/>` +
      `<path class="greif" d="${d}"/>${label}</g>`;
  }

  function svgFor(v) {
    const size = pictureMode ? `width="${v.width}" height="${v.height}" viewBox="0 0 ${v.width} ${v.height}"` : "";
    return `<svg class="c4" xmlns="http://www.w3.org/2000/svg" ${size} role="img" ` +
      `aria-label="${esc(`${viewTitle(v)}: ${v.description}`)}">` +
      `<defs>` +
      `<marker id="spitze" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto"><path class="spitze" d="M0,0.8 L10,5 L0,9.2 z"/></marker>` +
      `<marker id="spitze-an" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto"><path class="spitze-an" d="M0,0.8 L10,5 L0,9.2 z"/></marker>` +
      `</defs>` +
      (pictureMode ? `<rect width="${v.width}" height="${v.height}" fill="var(--papier)"/>` : "") +
      `<g class="welt">` +
      v.boundaries.map(boundarySvg).join("") +
      v.boxes.map(boxSvg).join("") +
      v.edges.map(edgeSvg).join("") +
      `</g></svg>`;
  }

  // ---- camera --------------------------------------------------------
  function applyTransform() {
    const g = stage.querySelector(".welt");
    if (g) g.setAttribute("transform", `translate(${r1(state.t.x)},${r1(state.t.y)}) scale(${state.t.k.toFixed(4)})`);
  }
  function fit() {
    const v = state.view;
    const rect = stage.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const top = 44, pad = 20;
    // On a wide screen a whole 4000-pixel view shrinks past legibility; stop
    // at a scale where the names can still be read and let the reader pan.
    const whole = Math.min((rect.width - 2 * pad) / v.width, (rect.height - top - pad - 56) / v.height, 1.25);
    const k = rect.width > 700 ? Math.max(whole, 0.32) : whole;
    state.t = { k, x: (rect.width - v.width * k) / 2, y: top + (rect.height - top - 56 - v.height * k) / 2 };
    applyTransform();
  }
  function zoomAt(factor, px, py) {
    const k = Math.min(4, Math.max(0.08, state.t.k * factor));
    const f = k / state.t.k;
    state.t.x = px - (px - state.t.x) * f;
    state.t.y = py - (py - state.t.y) * f;
    state.t.k = k;
    applyTransform();
  }
  function centreOn(box) {
    const rect = stage.getBoundingClientRect();
    const k = Math.max(state.t.k, 0.75);
    state.t = { k, x: rect.width / 2 - (box.x + box.w / 2) * k, y: rect.height / 2 - (box.y + box.h / 2) * k };
    applyTransform();
  }

  // ---- highlighting --------------------------------------------------
  function edgesOfBox(id) { return state.view.edges.filter(e => e.src === id || e.dst === id); }

  function currentFocus() {
    if (state.hover) return state.hover;
    if (state.selected) return state.selected;
    if (state.view.kind === "dynamic" && state.step > 0) return { kind: "edge", id: stepEdges()[state.step - 1].id };
    return null;
  }

  function highlight() {
    const svg = stage.querySelector("svg");
    if (!svg) return;
    const focus = currentFocus();
    const onBoxes = new Set(), onEdges = new Set();
    if (focus && focus.kind === "box") {
      onBoxes.add(focus.id);
      for (const e of edgesOfBox(focus.id)) { onEdges.add(e.id); onBoxes.add(e.src); onBoxes.add(e.dst); }
    } else if (focus && focus.kind === "edge") {
      const e = state.view.edges.find(x => x.id === focus.id);
      if (e) { onEdges.add(e.id); onBoxes.add(e.src); onBoxes.add(e.dst); }
    }
    stage.classList.toggle("fokus", !!focus);
    svg.querySelectorAll(".knoten").forEach(n => {
      const id = n.dataset.box;
      n.classList.toggle("an", onBoxes.has(id));
      n.classList.toggle("gewaehlt", !!state.selected && state.selected.kind === "box" && state.selected.id === id);
      n.classList.toggle("treffer-an", state.matches.has(boxEl(id)));
    });
    svg.querySelectorAll(".kante").forEach(n => {
      const on = onEdges.has(n.dataset.edge);
      n.classList.toggle("an", on);
      n.querySelector(".linie").setAttribute("marker-end", on ? "url(#spitze-an)" : "url(#spitze)");
      // a highlighted edge is drawn last, so its label is never under another line
      if (on) n.parentNode.appendChild(n);
    });
  }
  const boxById = id => state.view.boxes.find(b => b.id === id);
  const boxEl = id => (boxById(id) || {}).el;

  // ---- dynamic view --------------------------------------------------
  function stepEdges() { return state.view.edges.filter(e => e.order).sort((a, b) => a.order - b.order); }
  function setStep(n) {
    const steps = stepEdges();
    state.step = Math.max(0, Math.min(steps.length, n));
    state.selected = null;
    $("schritt-stand").textContent = state.step ? `${state.step} / ${steps.length}` : `– / ${steps.length}`;
    highlight();
    renderPanel();
  }
  function stopPlaying() {
    clearInterval(state.timer);
    state.timer = null;
    $("abspielen").textContent = "Abspielen";
    $("abspielen").setAttribute("aria-pressed", "false");
  }
  function togglePlaying() {
    if (state.timer) return stopPlaying();
    if (state.step >= stepEdges().length) setStep(0);
    $("abspielen").textContent = "Anhalten";
    $("abspielen").setAttribute("aria-pressed", "true");
    setStep(state.step + 1);
    state.timer = setInterval(() => {
      if (state.step >= stepEdges().length) return stopPlaying();
      setStep(state.step + 1);
    }, 1700);
  }

  // ---- side panel ----------------------------------------------------
  function legendLabel(e, b) {
    if (e.tags.includes("Amtlich")) return "Amtlicher Dienst";
    if (e.external) return e.tags.includes("Optional") ? "Externes System, optional" : "Externes System";
    if (e.tags.includes("Fremdprodukt")) return b.shape === "Cylinder" ? "Fremdprodukt, Speicher" : "Fremdprodukt im Stapel";
    if (e.type === "person") return "Person";
    if (e.type === "system") return "where2build";
    if (e.type === "component") return "Komponente";
    if (b.shape === "Cylinder") return "Datenbank";
    if (b.shape === "Folder") return "Volume";
    if (b.shape === "WebBrowser") return "Container im Browser";
    if (e.tags.includes("Einmalig")) return "Container, läuft einmal";
    return "Container";
  }
  function swatch(b) {
    const dash = b.dashed ? ` stroke="currentColor" stroke-dasharray="3 2" stroke-width="1.4"` : "";
    if (b.shape === "Person") return `<svg width="22" height="18" aria-hidden="true"><circle cx="11" cy="5" r="4.5" fill="${b.bg}"/><rect x="2" y="9" width="18" height="9" rx="4.5" fill="${b.bg}"/></svg>`;
    if (b.shape === "Cylinder") return `<svg width="22" height="18" aria-hidden="true"><path d="M2,4 A9,3 0 0 1 20,4 V14 A9,3 0 0 1 2,14 Z" fill="${b.bg}"/></svg>`;
    if (b.shape === "Folder") return `<svg width="22" height="18" aria-hidden="true"><rect x="2" y="2" width="8" height="5" rx="1.5" fill="${b.bg}"/><rect x="2" y="5" width="18" height="11" rx="2" fill="${b.bg}"/></svg>`;
    return `<svg width="22" height="18" aria-hidden="true"><rect x="1.5" y="2.5" width="19" height="13" rx="3" fill="${b.bg}"${dash}/></svg>`;
  }

  function legendHtml(v) {
    const seen = new Map();
    for (const b of v.boxes) {
      const label = legendLabel(el(b.el), b);
      if (!seen.has(label)) seen.set(label, b);
    }
    const items = [...seen].map(([label, b]) => `<li>${swatch(b)}<span>${esc(label)}</span></li>`);
    const kinds = new Set(v.boundaries.map(b => b.kind));
    if (kinds.has("system") || kinds.has("container")) items.push(`<li><svg width="22" height="18" aria-hidden="true"><rect x="1.5" y="2.5" width="19" height="13" rx="2" fill="none" stroke="var(--rahmen)" stroke-dasharray="4 2.5"/></svg><span>Grenze eines Systems oder Containers</span></li>`);
    if (kinds.has("group")) items.push(`<li><svg width="22" height="18" aria-hidden="true"><rect x="1.5" y="2.5" width="19" height="13" rx="4" fill="none" stroke="var(--rahmen)" stroke-dasharray="1 2.5" stroke-linecap="round" stroke-width="1.4"/></svg><span>Gruppe</span></li>`);
    if (kinds.has("node")) items.push(`<li><svg width="22" height="18" aria-hidden="true"><rect x="1.5" y="2.5" width="19" height="13" rx="2" fill="none" stroke="var(--rahmen)"/></svg><span>Verteilungsknoten</span></li>`);
    items.push(`<li><svg width="22" height="18" aria-hidden="true"><path d="M1,9 H17" stroke="var(--kante)" stroke-width="1.3"/><path d="M14,5.5 L21,9 L14,12.5 z" fill="var(--kante)"/></svg><span>Beziehung: was, <i>[womit]</i></span></li>`);
    return `<ul class="legende">${items.join("")}</ul>`;
  }

  function relationButton(e, perspective) {
    const other = perspective === "out" ? e.dst : perspective === "in" ? e.src : null;
    const head = perspective === "step"
      ? `<span><span class="nr">${e.order}</span><b>${esc(el(boxEl(e.src)).name)}</b> → <b>${esc(el(boxEl(e.dst)).name)}</b></span>`
      : `<span>${perspective === "out" ? "→" : "←"} <b>${esc(el(boxEl(other)).name)}</b></span>`;
    const current = perspective === "step" && state.step && stepEdges()[state.step - 1].id === e.id;
    return `<li><button type="button" data-select-edge="${e.id}" ${perspective !== "step" ? `data-select-box="${esc(other)}"` : ""}` +
      ` aria-current="${current ? "true" : "false"}">${head}` +
      `<small>${esc(e.description)}${e.technology ? ` [${esc(e.technology)}]` : ""}</small></button></li>`;
  }

  function panelForView(v) {
    const parts = [];
    parts.push(`<div><div class="art">${esc(viewEyebrow(v))}</div><h2>${esc(viewTitle(v))}</h2></div>`);
    parts.push(`<p>${esc(v.description)}</p>`);
    if (v.kind === "dynamic") {
      parts.push(`<section><h3>Schritte</h3><ol class="beziehungen">${stepEdges().map(e => relationButton(e, "step")).join("")}</ol></section>`);
    }
    parts.push(`<section><h3>Legende</h3>${legendHtml(v)}</section>`);
    parts.push(`<section><h3>Bedienung</h3><ul class="bedienung">` +
      `<li>Ziehen verschiebt, Mausrad oder zwei Finger zoomen.</li>` +
      `<li>Ein Klick auf einen Kasten zeigt, mit wem er spricht.</li>` +
      `<li>Doppelklick auf einen Kasten mit + öffnet die tiefere Ebene.</li>` +
      (v.kind === "dynamic" ? `<li>← und → gehen die Schritte durch.</li>` : "") +
      `<li>Taste 0 passt ein, Esc hebt die Auswahl auf.</li></ul></section>`);
    parts.push(`<p class="fuss">${v.boxes.length} Elemente, ${v.edges.length} Beziehungen. Erzeugt am ${esc(data.generated.split("-").reverse().join("."))} aus <code>docs/architektur/workspace.dsl</code>.</p>`);
    return parts.join("");
  }

  function panelForBox(id) {
    const b = boxById(id);
    const e = el(b.el);
    const parts = [];
    parts.push(`<div><div class="art">${esc(e.kind)}</div><h2>${esc(e.name)}</h2></div>`);
    if (e.description) parts.push(`<p>${esc(e.description)}</p>`);
    if (e.technology) parts.push(`<section><h3>Technik</h3><p class="technik">${esc(e.technology)}</p></section>`);
    const where = [e.parent && `Teil von ${e.parent}`, e.group && `Gruppe „${e.group}“`].filter(Boolean);
    const tags = e.tags.filter(t => !["Container Instance", "Software System Instance"].includes(t));
    if (where.length || tags.length) {
      parts.push(`<div class="etiketten">${where.concat(tags).map(t => `<span class="etikett">${esc(t)}</span>`).join("")}</div>`);
    }
    const actions = [];
    if (e.drill && e.drill !== state.view.slug) actions.push(`<button class="knopf haupt" type="button" data-goto="${e.drill}">${esc(viewTitle(bySlug.get(e.drill)))} öffnen</button>`);
    for (const slug of e.views) if (slug !== state.view.slug && slug !== e.drill) {
      actions.push(`<button class="knopf" type="button" data-goto="${slug}" data-then="${esc(b.el)}">In „${esc(viewTitle(bySlug.get(slug)))}“</button>`);
    }
    if (actions.length) parts.push(`<div class="aktionen">${actions.join("")}</div>`);
    const out = state.view.edges.filter(x => x.src === id);
    const inc = state.view.edges.filter(x => x.dst === id);
    if (out.length) parts.push(`<section><h3>Ausgehend · ${out.length}</h3><ul class="beziehungen">${out.map(x => relationButton(x, "out")).join("")}</ul></section>`);
    if (inc.length) parts.push(`<section><h3>Eingehend · ${inc.length}</h3><ul class="beziehungen">${inc.map(x => relationButton(x, "in")).join("")}</ul></section>`);
    parts.push(`<div class="aktionen"><button class="knopf" type="button" data-clear>Zur Übersicht</button></div>`);
    return parts.join("");
  }

  function panelForEdge(id) {
    const e = state.view.edges.find(x => x.id === id);
    const parts = [];
    parts.push(`<div><div class="art">Beziehung${e.order ? ` · Schritt ${e.order}` : ""}</div>` +
      `<h2>${esc(el(boxEl(e.src)).name)} → ${esc(el(boxEl(e.dst)).name)}</h2></div>`);
    parts.push(`<p>${esc(e.description)}</p>`);
    if (e.technology) parts.push(`<section><h3>Technik</h3><p class="technik">${esc(e.technology)}</p></section>`);
    parts.push(`<div class="aktionen">` +
      `<button class="knopf" type="button" data-select-box="${esc(e.src)}">${esc(el(boxEl(e.src)).name)}</button>` +
      `<button class="knopf" type="button" data-select-box="${esc(e.dst)}">${esc(el(boxEl(e.dst)).name)}</button>` +
      `<button class="knopf" type="button" data-clear>Zur Übersicht</button></div>`);
    return parts.join("");
  }

  function renderPanel() {
    const s = state.selected;
    panel.innerHTML = s && s.kind === "box" ? panelForBox(s.id) : s && s.kind === "edge" ? panelForEdge(s.id) : panelForView(state.view);
  }

  // ---- navigation ----------------------------------------------------
  function renderTabs() {
    $("sichten").innerHTML = views.map(v =>
      `<button class="sicht" type="button" data-goto="${v.slug}" aria-current="${v === state.view}">` +
      `<small>${esc(viewEyebrow(v))}</small><span>${esc(viewTitle(v))}</span></button>`).join("");
  }
  function renderPath() {
    const v = state.view;
    const ctx = views.find(x => x.kind === "context");
    const cont = views.find(x => x.kind === "container");
    const trail = v.kind === "context" ? [v] : v.kind === "container" ? [ctx, v] : v.kind === "component" ? [ctx, cont, v] : [ctx, v];
    pathBar.innerHTML = trail.filter(Boolean).map(x => x === v
      ? `<li aria-current="page">${esc(viewTitle(x))}</li>`
      : `<li><button type="button" data-goto="${x.slug}">${esc(viewTitle(x))}</button></li>`).join("");
  }

  function show(slug, thenSelect) {
    const v = bySlug.get(slug) || views[0];
    stopPlaying();
    state.view = v;
    state.hover = null;
    state.selected = null;
    state.step = 0;
    stage.innerHTML = svgFor(v);
    renderTabs();
    renderPath();
    stepBar.hidden = v.kind !== "dynamic";
    if (v.kind === "dynamic") setStep(0);
    if (pictureMode) {
      stage.querySelector("svg").setAttribute("data-fertig", "");
      return;
    }
    fit();
    if (thenSelect) {
      const box = v.boxes.find(b => b.el === thenSelect);
      if (box) { state.selected = { kind: "box", id: box.id }; centreOn(box); }
    }
    highlight();
    renderPanel();
    document.title = `${viewTitle(v)} · where2build Architektur`;
  }

  function go(slug, thenSelect) {
    if (location.hash.slice(1) !== slug) {
      pendingSelect = thenSelect || null;
      location.hash = slug;            // hashchange renders
    } else {
      show(slug, thenSelect);
    }
  }
  let pendingSelect = null;
  window.addEventListener("hashchange", () => {
    show(location.hash.slice(1), pendingSelect);
    pendingSelect = null;
  });

  // ---- events --------------------------------------------------------
  document.addEventListener("click", ev => {
    const t = ev.target.closest("[data-goto], [data-select-box], [data-select-edge], [data-clear]");
    if (!t || stage.contains(t)) return;
    if (t.hasAttribute("data-goto")) return go(t.dataset.goto, t.dataset.then);
    if (t.hasAttribute("data-clear")) { state.selected = null; highlight(); renderPanel(); return; }
    if (state.view.kind === "dynamic" && t.dataset.selectEdge && !t.dataset.selectBox) {
      const idx = stepEdges().findIndex(e => e.id === t.dataset.selectEdge);
      return setStep(idx + 1);
    }
    if (t.dataset.selectBox) {
      state.selected = { kind: "box", id: t.dataset.selectBox };
      centreOn(boxById(t.dataset.selectBox));
    } else {
      state.selected = { kind: "edge", id: t.dataset.selectEdge };
    }
    highlight();
    renderPanel();
  });

  // pointer: pan, pinch, click
  const pointers = new Map();
  let dragStart = null, moved = false, pinch = null;
  stage.addEventListener("pointerdown", ev => {
    stage.setPointerCapture(ev.pointerId);
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    moved = false;
    if (pointers.size === 1) dragStart = { x: ev.clientX, y: ev.clientY, tx: state.t.x, ty: state.t.y };
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: state.t.k };
    }
  });
  stage.addEventListener("pointermove", ev => {
    if (!pointers.has(ev.pointerId)) {
      const t = ev.target.closest("[data-box], [data-edge]");
      const next = t ? (t.dataset.box ? { kind: "box", id: t.dataset.box } : { kind: "edge", id: t.dataset.edge }) : null;
      if (JSON.stringify(next) !== JSON.stringify(state.hover)) { state.hover = next; highlight(); }
      return;
    }
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const rect = stage.getBoundingClientRect();
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      zoomAt((pinch.k * d / pinch.d) / state.t.k, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      moved = true;
      return;
    }
    if (dragStart) {
      const dx = ev.clientX - dragStart.x, dy = ev.clientY - dragStart.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) { moved = true; stage.classList.add("zieht"); }
      state.t.x = dragStart.tx + dx;
      state.t.y = dragStart.ty + dy;
      applyTransform();
    }
  });
  const release = ev => {
    pointers.delete(ev.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 0) { dragStart = null; stage.classList.remove("zieht"); }
  };
  stage.addEventListener("pointerup", ev => {
    const wasDrag = moved;
    release(ev);
    if (wasDrag) return;
    const t = document.elementFromPoint(ev.clientX, ev.clientY);
    const hit = t && t.closest("[data-box], [data-edge], [data-goto]");
    if (hit && hit.dataset.goto) return go(hit.dataset.goto);
    if (hit && hit.dataset.box) state.selected = { kind: "box", id: hit.dataset.box };
    else if (hit && hit.dataset.edge) {
      const e = state.view.edges.find(x => x.id === hit.dataset.edge);
      if (state.view.kind === "dynamic" && e.order) { setStep(stepEdges().indexOf(e) + 1); return; }
      state.selected = { kind: "edge", id: hit.dataset.edge };
    } else state.selected = null;
    highlight();
    renderPanel();
  });
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("pointerleave", () => { if (state.hover) { state.hover = null; highlight(); } });
  stage.addEventListener("dblclick", ev => {
    // the stage holds pointer capture, so the target is the stage itself
    const under = document.elementFromPoint(ev.clientX, ev.clientY);
    const t = under && under.closest("[data-box]");
    if (!t) return;
    const target = el(boxEl(t.dataset.box)).drill;
    if (target && target !== state.view.slug) go(target);
  });
  stage.addEventListener("wheel", ev => {
    ev.preventDefault();
    const rect = stage.getBoundingClientRect();
    zoomAt(Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015)), ev.clientX - rect.left, ev.clientY - rect.top);
  }, { passive: false });
  stage.addEventListener("keydown", ev => {
    const t = ev.target.closest("[data-box]");
    if (!t || (ev.key !== "Enter" && ev.key !== " ")) return;
    ev.preventDefault();
    if (state.selected && state.selected.id === t.dataset.box) {
      const target = el(boxEl(t.dataset.box)).drill;
      if (target && target !== state.view.slug) return go(target);
    }
    state.selected = { kind: "box", id: t.dataset.box };
    highlight();
    renderPanel();
  });
  stage.addEventListener("focusin", ev => {
    const t = ev.target.closest("[data-box]");
    if (t) { state.hover = { kind: "box", id: t.dataset.box }; highlight(); }
  });
  stage.addEventListener("focusout", () => { state.hover = null; highlight(); });

  document.addEventListener("keydown", ev => {
    if (ev.target.matches("input")) return;
    const rect = stage.getBoundingClientRect();
    if (ev.key === "+" || ev.key === "=") zoomAt(1.25, rect.width / 2, rect.height / 2);
    else if (ev.key === "-") zoomAt(0.8, rect.width / 2, rect.height / 2);
    else if (ev.key === "0") fit();
    else if (ev.key === "Escape") { state.selected = null; highlight(); renderPanel(); }
    else if (state.view.kind === "dynamic" && ev.key === "ArrowRight") { stopPlaying(); setStep(state.step + 1); }
    else if (state.view.kind === "dynamic" && ev.key === "ArrowLeft") { stopPlaying(); setStep(state.step - 1); }
  });

  $("zoom-rein").addEventListener("click", () => { const r = stage.getBoundingClientRect(); zoomAt(1.25, r.width / 2, r.height / 2); });
  $("zoom-raus").addEventListener("click", () => { const r = stage.getBoundingClientRect(); zoomAt(0.8, r.width / 2, r.height / 2); });
  $("einpassen").addEventListener("click", fit);
  $("schritt-vor").addEventListener("click", () => { stopPlaying(); setStep(state.step + 1); });
  $("schritt-zurueck").addEventListener("click", () => { stopPlaying(); setStep(state.step - 1); });
  $("abspielen").addEventListener("click", togglePlaying);
  $("beschriftung").addEventListener("change", ev => document.body.classList.toggle("ohne-text", !ev.target.checked));
  window.addEventListener("resize", () => state.view && !pictureMode && fit());

  // search over every element of every view
  const field = $("suchfeld"), hits = $("treffer");
  const norm = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  field.addEventListener("input", () => {
    const q = norm(field.value.trim());
    state.matches = new Set();
    if (!q) { hits.hidden = true; highlight(); return; }
    const found = Object.entries(data.elements)
      .map(([id, e]) => ({ id, e, score: norm(e.name).includes(q) ? 0 : norm(e.technology).includes(q) ? 1 : norm(e.description).includes(q) ? 2 : 9 }))
      .filter(x => x.score < 9).sort((a, b) => a.score - b.score || a.e.name.localeCompare(b.e.name, "de")).slice(0, 12);
    found.forEach(x => state.matches.add(x.id));
    hits.innerHTML = found.length
      ? found.map(({ id, e }) => {
          const slug = e.views.includes(state.view.slug) ? state.view.slug : e.views[0];
          return `<li><button type="button" data-goto="${slug}" data-then="${esc(id)}"><span>${esc(e.name)}</span>` +
            `<small>${esc(e.kind)} · ${esc(viewTitle(bySlug.get(slug)))}</small></button></li>`;
        }).join("")
      : `<li class="leer">Kein Element passt zu „${esc(field.value.trim())}“.</li>`;
    hits.hidden = false;
    highlight();
  });
  hits.addEventListener("click", () => { hits.hidden = true; });
  document.addEventListener("pointerdown", ev => { if (!ev.target.closest(".suche")) hits.hidden = true; });
  field.addEventListener("keydown", ev => {
    if (ev.key === "Enter") { const first = hits.querySelector("button"); if (first) first.click(); }
    if (ev.key === "Escape") { field.value = ""; field.dispatchEvent(new Event("input")); field.blur(); }
  });

  // theme: system, light, dark
  const themes = [["", "System"], ["light", "Hell"], ["dark", "Dunkel"]];
  let theme = "";
  try { theme = localStorage.getItem("c4-thema") || ""; } catch (_) { /* storage may be blocked */ }
  function applyTheme() {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
    $("thema").textContent = themes.find(t => t[0] === theme)[1];
  }
  $("thema").addEventListener("click", () => {
    const i = themes.findIndex(t => t[0] === theme);
    theme = themes[(i + 1) % themes.length][0];
    try { localStorage.setItem("c4-thema", theme); } catch (_) { /* fine without */ }
    applyTheme();
  });

  if (pictureMode) document.documentElement.classList.add("bild");
  applyTheme();
  show(location.hash.slice(1) || views[0].slug);
})();
