/* ---------- Lageplan: schwenken, zoomen, Ebenen ---------- */
(function(){
  "use strict";
  var D = JSON.parse(document.getElementById("daten").textContent);
  var NS = "http://www.w3.org/2000/svg";
  var svg = document.getElementById("plan");
  var welt = document.getElementById("welt");
  var schrift = document.getElementById("schrift");

  /* Sicht: Massstab in Pixeln je Meter, Mittelpunkt in Metern. */
  var sicht = { s: 4, mx: 3, my: 2 }, grund = null;
  var breite = 0, hoehe = 0;

  function pfad(ring){
    var d = "", i;
    for (i = 0; i < ring.length; i++) d += (i ? "L" : "M") + ring[i][0] + " " + ring[i][1];
    return d + "Z";
  }
  function el(name, attrs){
    var n = document.createElementNS(NS, name), k;
    for (k in attrs) if (attrs[k] !== null) n.setAttribute(k, attrs[k]);
    return n;
  }
  var px = function(x){ return breite / 2 + (x - sicht.mx) * sicht.s; };
  var py = function(y){ return hoehe / 2 - (y - sicht.my) * sicht.s; };

  function strasseAusLage(lage){
    if (!lage) return null;
    var teil = String(lage).split(";")[0].trim();
    var m = /^(.*?)(?:\s+\d.*)?$/.exec(teil);
    return (m ? m[1].trim() : teil) || null;
  }
  /* Lange Kanten unterteilen: sonst liegt bei nahem Zoom kein Stuetzpunkt im
     Bild und die Beschriftung findet keinen Anker. */
  function verdichte(ring, maxLaenge){
    var out = [], i, a, b, n, k;
    for (i = 0; i < ring.length - 1; i++){
      a = ring[i]; b = ring[i + 1];
      out.push(a);
      n = Math.floor(Math.hypot(b[0] - a[0], b[1] - a[1]) / maxLaenge);
      for (k = 1; k < n; k++) out.push([a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n]);
    }
    out.push(ring[ring.length - 1]);
    return out;
  }
  /* Anker und Laufrichtung aus den Punkten, die gerade im Bild liegen. */
  function sichtbarerAnker(ring){
    var innen = [], i, x, y;
    for (i = 0; i < ring.length; i++){
      x = px(ring[i][0]); y = py(ring[i][1]);
      if (x > 30 && x < breite - 30 && y > 26 && y < hoehe - 26) innen.push([x, y]);
    }
    if (innen.length < 2) return null;
    var sx = 0, sy = 0, minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
    for (i = 0; i < innen.length; i++){
      sx += innen[i][0]; sy += innen[i][1];
      if (innen[i][0] < minx) minx = innen[i][0];
      if (innen[i][0] > maxx) maxx = innen[i][0];
      if (innen[i][1] < miny) miny = innen[i][1];
      if (innen[i][1] > maxy) maxy = innen[i][1];
    }
    var w = Math.atan2(maxy - miny, maxx - minx) * 180 / Math.PI;
    if (w > 90) w -= 180;
    return {x: sx / innen.length, y: sy / innen.length, winkel: w};
  }
  /* Jede sichtbare Strassenflaeche bekommt den Namen des naechsten
     Flurstuecks -- und jeder Name wird nur einmal gesetzt, am zentralsten Ort. */
  function zeichneStrassennamen(){
    var kandidaten = [];
    strassenFlaechen.forEach(function(f){
      f.node.style.display = "none";
      if (sicht.s < 1.4) return;
      var a = sichtbarerAnker(f.ring);
      if (!a) return;
      var wx = sicht.mx + (a.x - breite / 2) / sicht.s;
      var wy = sicht.my - (a.y - hoehe / 2) / sicht.s;
      var best = null, bestD = Infinity, i, d;
      for (i = 0; i < benannt.length; i++){
        d = (benannt[i].c[0] - wx) * (benannt[i].c[0] - wx) + (benannt[i].c[1] - wy) * (benannt[i].c[1] - wy);
        if (d < bestD){ bestD = d; best = benannt[i].name; }
      }
      if (best) kandidaten.push({f: f, a: a, name: best,
        mitte: Math.hypot(a.x - breite / 2, a.y - hoehe / 2)});
    });
    var gesetzt = {};
    kandidaten.sort(function(p, q){ return p.mitte - q.mitte; });
    kandidaten.forEach(function(k){
      if (gesetzt[k.name]) return;
      gesetzt[k.name] = true;
      k.f.node.textContent = k.name;
      k.f.node.style.display = "";
      k.f.node.setAttribute("x", k.a.x);
      k.f.node.setAttribute("y", k.a.y);
      k.f.node.setAttribute("transform", "rotate(" + k.a.winkel.toFixed(1) + " " + k.a.x + " " + k.a.y + ")");
    });
  }

  /* ---- Ebenen, von unten nach oben ---- */
  var NUTZ_FARBE = {
    "Wohnbaufläche": "var(--map-wohnen)",
    "Landwirtschaft": "var(--map-gruen)",
    "Sport-, Freizeit- und Erholungsfläche": "var(--map-gruen)",
    "Industrie- und Gewerbefläche": "var(--map-gewerbe)",
    "Fläche besonderer funktionaler Prägung": "var(--map-gewerbe)",
    "Straßenverkehr": "var(--map-strasse)"
  };
  var gOrtho = el("g", {id: "orthoebene", opacity: "0", "aria-hidden": "true"});
  var gNutz  = el("g", {});
  var gLaerm = el("g", {id: "laermebene", opacity: "0", "aria-hidden": "true"});
  var gParz  = el("g", {});
  var gGeb   = el("g", {});
  var gZiel  = el("g", {});
  welt.appendChild(gOrtho); welt.appendChild(gNutz); welt.appendChild(gLaerm);
  /* Das Luftbild ist nach Norden ausgerichtet, die Weltgruppe spiegelt y --
     also einmal zurueckspiegeln, sonst steht es auf dem Kopf. */
  (function(){
    var r = D.ortho.radius;
    var g = el("g", {transform: "scale(1,-1)"});
    var bild = el("image", {x: -r, y: -r, width: 2 * r, height: 2 * r,
      preserveAspectRatio: "none"});
    bild.setAttributeNS("http://www.w3.org/1999/xlink", "href", D.ortho.datauri);
    bild.setAttribute("href", D.ortho.datauri);
    g.appendChild(bild); gOrtho.appendChild(g);
  })();
  welt.appendChild(gParz); welt.appendChild(gGeb); welt.appendChild(gZiel);

  D.nutzung.forEach(function(o){
    gNutz.appendChild(el("path", {d: pfad(o.ring), fill: NUTZ_FARBE[o.art] || "var(--map-wohnen)", stroke: "none"}));
  });

  var FARBE = {Lden5054:"var(--db1)", Lden5559:"var(--db2)", Lden6064:"var(--db3)",
               Lden6569:"var(--db4)", Lden7074:"var(--db5)", LdenAb75:"var(--db5)"};
  ["Lden5054","Lden5559","Lden6064","Lden6569","Lden7074","LdenAb75"].forEach(function(cat){
    D.laerm.forEach(function(b){
      if (b.cat === cat) gLaerm.appendChild(el("path", {d: pfad(b.ring), fill: FARBE[cat], stroke: "none", opacity: ".8"}));
    });
  });

  /* Flurstuecke: nur Grenzen mit Halo. Keine deckende Fuellung -- sonst
     verschwindet der Laermverlauf darunter. */
  var ziel = null;
  D.parzellen.forEach(function(p){
    if (p.nr === "204") { ziel = p; return; }
    var d = pfad(p.ring);
    gParz.appendChild(el("path", {d: d, fill: "none", stroke: "var(--map-halo)",
      "stroke-width": "2.4", "vector-effect": "non-scaling-stroke", opacity: ".55"}));
    gParz.appendChild(el("path", {d: d, "class": "grenze", fill: "none",
      stroke: "var(--map-grenze)", "stroke-width": ".9", "vector-effect": "non-scaling-stroke"}));
  });
  D.gebaeude.forEach(function(r){
    gGeb.appendChild(el("path", {d: pfad(r), "class": "gebaeude", fill: "var(--map-gebaeude)",
      stroke: "var(--map-gebaeude-kante)", "stroke-width": ".7", "vector-effect": "non-scaling-stroke", opacity: ".92"}));
  });
  if (ziel){
    var dz = pfad(ziel.ring);
    gZiel.appendChild(el("path", {id: "zielfuellung", d: dz, fill: "var(--map-ziel-fuellung)", stroke: "none"}));
    gZiel.appendChild(el("path", {d: dz, fill: "none", stroke: "var(--map-halo)",
      "stroke-width": "5", "vector-effect": "non-scaling-stroke", opacity: ".6"}));
    gZiel.appendChild(el("path", {d: dz, fill: "none", stroke: "var(--map-ziel)",
      "stroke-width": "2.4", "vector-effect": "non-scaling-stroke"}));
  }

  /* ---- Beschriftung: eigene, ungespiegelte Ebene ---- */
  var labels = [];
  // Ein Strassenpolygon zieht sich ueber mehrere Strassen, und sein Schwerpunkt
  // liegt meist ausserhalb des Bildes. Anker und Name werden deshalb bei jedem
  // Zeichnen aus dem *sichtbaren* Abschnitt bestimmt.
  var strassenFlaechen = [];
  D.nutzung.forEach(function(o){
    if (o.art !== "Straßenverkehr") return;
    var node = el("text", {"class": "strassenname"});
    schrift.appendChild(node);
    strassenFlaechen.push({ring: verdichte(o.ring, 6), node: node});
  });
  var benannt = [];
  D.parzellen.forEach(function(p){
    var name = strasseAusLage(p.lage);
    if (name) benannt.push({c: p.c, name: name});
  });
  D.parzellen.forEach(function(p){
    if (p.nr === "204" || !p.gross) return;
    var t = el("text", {"class": "flstnr"});
    t.textContent = p.nen ? p.nr + "/" + p.nen : p.nr;
    schrift.appendChild(t);
    labels.push({node: t, pos: p.c, art: "nr"});
  });
  if (ziel){
    var tz = el("text", {"class": "flstnr flstnr--ziel"});
    tz.textContent = "204";
    schrift.appendChild(tz);
    labels.push({node: tz, pos: ziel.c, art: "ziel"});
  }

  /* ---- Sicht anwenden ---- */
  var SCHRITTE = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500];
  function zeichne(){
    welt.setAttribute("transform",
      "translate(" + (breite / 2) + "," + (hoehe / 2) + ") scale(" + sicht.s + "," + (-sicht.s) + ")" +
      " translate(" + (-sicht.mx) + "," + (-sicht.my) + ")");
    zeichneStrassennamen();
    labels.forEach(function(l){
      var x = px(l.pos[0]), y = py(l.pos[1]);
      l.node.setAttribute("x", x); l.node.setAttribute("y", y);
      var raus = x < 6 || x > breite - 6 || y < 10 || y > hoehe - 6;
      l.node.style.display = (raus || (l.art === "nr" && sicht.s < 2.4)) ? "none" : "";
    });
    // Massstabsbalken: zwei Haelften, wie im Lageplan
    var ziel_px = 70, schritt = SCHRITTE[0], i;
    for (i = 0; i < SCHRITTE.length; i++){ if (SCHRITTE[i] * sicht.s <= ziel_px) schritt = SCHRITTE[i]; else break; }
    var w = schritt * sicht.s, X0 = 6;
    document.getElementById("mb1").setAttribute("x", X0);
    document.getElementById("mb1").setAttribute("width", w);
    document.getElementById("mb2").setAttribute("x", X0 + w);
    document.getElementById("mb2").setAttribute("width", w);
    document.getElementById("mlinie").setAttribute("x1", X0);
    document.getElementById("mlinie").setAttribute("x2", X0 + w * 2);
    document.getElementById("manfang").setAttribute("x", X0);
    document.getElementById("mmitte").setAttribute("x", X0 + w);
    document.getElementById("mmitte").textContent = schritt;
    document.getElementById("mende").setAttribute("x", X0 + w * 2);
    document.getElementById("mende").textContent = schritt * 2 + " m";
    document.querySelector(".massstab").setAttribute("width", X0 * 2 + w * 2 + 18);
  }

  function passe(){
    var b = svg.getBoundingClientRect();
    if (!b.width || !b.height) return;
    breite = Math.round(b.width); hoehe = Math.round(b.height);
    svg.setAttribute("viewBox", "0 0 " + breite + " " + hoehe);
    if (grund === null){
      // Einpassen auf das Zielflurstueck mit Umfeld
      var R = 70;
      grund = Math.min(breite / (2 * R), hoehe / (2 * R));
      sicht.s = grund;
    }
    zeichne();
  }

  /* ---- Bedienung ---- */
  var MIN = 0.35, MAX = 14, zieht = null;
  function setzeMassstab(neu, ax, ay){
    neu = Math.max(grund * MIN, Math.min(grund * MAX, neu));
    if (neu === sicht.s) return;
    // Punkt unter dem Zeiger festhalten
    var wx = sicht.mx + (ax - breite / 2) / sicht.s;
    var wy = sicht.my - (ay - hoehe / 2) / sicht.s;
    sicht.s = neu;
    sicht.mx = wx - (ax - breite / 2) / sicht.s;
    sicht.my = wy + (ay - hoehe / 2) / sicht.s;
    zeichne();
  }
  svg.addEventListener("wheel", function(e){
    e.preventDefault();
    var r = svg.getBoundingClientRect();
    setzeMassstab(sicht.s * Math.pow(1.0016, -e.deltaY), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  svg.addEventListener("pointerdown", function(e){
    zieht = {x: e.clientX, y: e.clientY};
    svg.setPointerCapture(e.pointerId); svg.classList.add("plan--zieht");
  });
  svg.addEventListener("pointermove", function(e){
    if (!zieht) return;
    sicht.mx -= (e.clientX - zieht.x) / sicht.s;
    sicht.my += (e.clientY - zieht.y) / sicht.s;
    zieht = {x: e.clientX, y: e.clientY};
    zeichne();
  });
  function los(e){ zieht = null; svg.classList.remove("plan--zieht");
    if (e && e.pointerId !== undefined && svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId); }
  svg.addEventListener("pointerup", los);
  svg.addEventListener("pointercancel", los);
  svg.addEventListener("keydown", function(e){
    var d = 40 / sicht.s, k = e.key;
    if (k === "ArrowLeft") sicht.mx -= d; else if (k === "ArrowRight") sicht.mx += d;
    else if (k === "ArrowUp") sicht.my += d; else if (k === "ArrowDown") sicht.my -= d;
    else if (k === "+" || k === "=") setzeMassstab(sicht.s * 1.3, breite / 2, hoehe / 2);
    else if (k === "-") setzeMassstab(sicht.s / 1.3, breite / 2, hoehe / 2);
    else return;
    e.preventDefault(); zeichne();
  });
  document.getElementById("rein").addEventListener("click", function(){ setzeMassstab(sicht.s * 1.4, breite / 2, hoehe / 2); });
  document.getElementById("raus").addEventListener("click", function(){ setzeMassstab(sicht.s / 1.4, breite / 2, hoehe / 2); });
  document.getElementById("zurueck").addEventListener("click", function(){
    sicht.s = grund; sicht.mx = 3; sicht.my = 2; zeichne();
  });

  var schalter = document.getElementById("laermAn"), legende = document.getElementById("legende");
  var orthoSchalter = document.getElementById("orthoAn");
  function ebenen(){
    var laerm = schalter.checked, ortho = orthoSchalter.checked;
    gLaerm.setAttribute("opacity", laerm ? "1" : "0");
    legende.setAttribute("data-an", laerm ? "1" : "0");
    gOrtho.setAttribute("opacity", ortho ? "1" : "0");
    // Ueber dem Luftbild wuerden die Nutzungsflaechen es zudecken.
    gNutz.setAttribute("opacity", ortho ? "0" : "1");
    // Auf dem Luftbild ist Lärm nur als Schleier lesbar, sonst verschwindet
    // das Bild darunter.
    gLaerm.setAttribute("fill-opacity", ortho ? ".5" : "1");
    var zf = document.getElementById("zielfuellung");
    if (zf) zf.setAttribute("opacity", laerm || ortho ? "0.25" : "1");
    var plan = document.getElementById("plan");
    plan.classList.toggle("plan--laerm", laerm);
    plan.classList.toggle("plan--ortho", ortho);
  }
  schalter.addEventListener("change", ebenen);
  orthoSchalter.addEventListener("change", ebenen);

  window.addEventListener("resize", passe);
  if (window.ResizeObserver) new ResizeObserver(passe).observe(svg);
  passe();
})();
