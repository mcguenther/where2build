/* ---------- Suchfeld: erkennen, entprellen, vorschlagen ----------
   classifyQuery ist wortgleich aus frontend/src/lib/queryInput.js uebernommen,
   damit der Mockup dasselbe entscheidet wie die Anwendung. */
(function(){
  "use strict";
  var D = JSON.parse(document.getElementById("daten").textContent);
  var LAT = [47.0, 55.2], LON = [5.6, 15.3];
  var EAST = [180000, 900000], NORTH = [5200000, 6100000];
  var ADV_KEY = /^\d{6}[\d_]{9}[\d_]{5}$/;
  var PARCEL_NUMBER = /^(\d{1,5})(?:\s*\/\s*([0-9a-z]{1,3}))?$/i;
  var DISTRICT_KEY = /^(?:14)?\d{4}$/;
  var inRange = function(v, r){ return v >= r[0] && v <= r[1]; };

  function readNumbers(text){
    var cleaned = text.replace(/[NnSsEeOoWw]\b/g, " ").replace(/[°'"´`]/g, " ").replace(/\s+/g, " ").trim();
    if (!cleaned) return [];
    var norm = cleaned.replace(/(\d)\s*,\s*(\d{3,})/g, "$1.$2").replace(/[,;]/g, " ");
    var parts = norm.split(/\s+/).filter(Boolean);
    for (var i = 0; i < parts.length; i++) if (!/^-?\d+(?:\.\d+)?$/.test(parts[i])) return [];
    return parts.map(Number);
  }
  function asCoordinate(n){
    if (n.length !== 2) return null;
    if (inRange(n[0], LAT) && inRange(n[1], LON)) return {lat:n[0], lon:n[1], system:"wgs84", swapped:false};
    if (inRange(n[1], LAT) && inRange(n[0], LON)) return {lat:n[1], lon:n[0], system:"wgs84", swapped:true};
    if (inRange(n[0], EAST) && inRange(n[1], NORTH)) return {easting:n[0], northing:n[1], system:"utm33"};
    return null;
  }
  function parseParcelNumber(token){
    var m = PARCEL_NUMBER.exec(token);
    return m ? {numerator:m[1], denominator:m[2] || null} : null;
  }
  function classifyQuery(raw){
    var text = String(raw == null ? "" : raw).trim();
    if (!text) return {kind:"empty", certain:true, search:[]};
    var compact = text.replace(/\s+/g, "");
    if (ADV_KEY.test(compact)) return {kind:"parcel", certain:true, search:["parcel"], parcelKey:compact};
    var coordinate = asCoordinate(readNumbers(text));
    if (coordinate) return {kind:"coordinate", certain:true, search:["coordinate"], coordinate:coordinate};
    var bare = PARCEL_NUMBER.exec(text);
    if (bare){
      if (DISTRICT_KEY.test(text) && text.indexOf("/") === -1)
        return {kind:"parcel", certain:false, search:["district","parcel"], missing:"parcelNumber", districtKey:text};
      return {kind:"parcel", certain:false, search:[], missing:"district",
              parcelNumber:{numerator:bare[1], denominator:bare[2] || null}};
    }
    var split = text.match(/^(.*?)[\s,;]+(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)$/i);
    if (split){
      var head = split[1].trim(), tail = split[2].replace(/\s+/g, "");
      if (tail.indexOf("/") !== -1)
        return {kind:"parcel", certain:true, search:["parcel"], district:head, parcelNumber:parseParcelNumber(tail)};
      if (DISTRICT_KEY.test(head))
        return {kind:"parcel", certain:true, search:["parcel"], districtKey:head, parcelNumber:parseParcelNumber(tail)};
      return {kind:"ambiguous", certain:false, search:["address","parcel"],
              street:head, houseNumber:tail, district:head, parcelNumber:parseParcelNumber(tail)};
    }
    if (/^\d/.test(text)) return {kind:"unclear", certain:false, search:[]};
    return {kind:"ambiguous", certain:false, search:["address","district"], text:text};
  }
  function queryKindLabel(r){
    if (r.kind === "coordinate") return r.coordinate.system === "utm33" ? "Koordinate (UTM 33)" : "Koordinate";
    if (r.kind === "parcel") return r.certain ? "Flurstück" : "Flurstück — Gemarkung fehlt";
    if (r.kind === "ambiguous") return "Adresse oder Flurstück";
    return "";
  }
  var INDEX_NAME = {address:"Adressen", parcel:"Flurstücke", district:"Gemarkungen", coordinate:"—"};

  var eingabe = document.getElementById("q"), liste = document.getElementById("treffer"),
      erkannt = document.getElementById("erkannt"), zaehler = document.getElementById("zaehler"),
      gesucht = document.getElementById("gesucht");
  var timer = null, laeufe = 0, WARTE = 120;

  function adressen(key){
    var tr = D.vorschlaege[key];
    if (tr) return tr;
    var beste = null;
    Object.keys(D.vorschlaege).forEach(function(k){
      if (key.toLowerCase().indexOf(k.toLowerCase()) === 0 && (!beste || k.length > beste.length)) beste = k;
    });
    return beste ? D.vorschlaege[beste] : [];
  }

  function suche(text){
    var r = classifyQuery(text);
    erkannt.textContent = queryKindLabel(r);
    erkannt.setAttribute("data-sicher", r.certain ? "1" : "0");

    if (!r.search.length){
      // Der Punkt, an dem wir gar nichts nachschlagen -- und das auch sagen.
      gesucht.innerHTML = r.kind === "parcel" && r.missing === "district"
        ? "<b>Gemarkung fehlt</b> — nichts nachgeschlagen"
        : "gesucht in: <b>—</b>";
      liste.hidden = true; eingabe.setAttribute("aria-expanded", "false");
      return;
    }
    laeufe++; zaehler.textContent = laeufe;
    gesucht.innerHTML = "gesucht in: <b>" + r.search.map(function(s){ return INDEX_NAME[s]; }).join(" + ") + "</b>";
    zeige(r.search.indexOf("address") !== -1 ? adressen(text.trim()) : [], text.trim(), r);
  }

  function zeige(tr, key, r){
    liste.textContent = "";
    if (r.kind === "coordinate"){
      var d = document.createElement("div");
      d.className = "treffer"; d.setAttribute("role", "option");
      var a = document.createElement("span"); a.className = "treffer__adr";
      a.textContent = r.coordinate.system === "utm33"
        ? "UTM 33: " + r.coordinate.easting + " / " + r.coordinate.northing
        : r.coordinate.lat.toFixed(5).replace(".", ",") + " · " + r.coordinate.lon.toFixed(5).replace(".", ",");
      var o = document.createElement("span"); o.className = "treffer__ort";
      o.textContent = r.coordinate.swapped ? "Reihenfolge getauscht" : "Punkt auf der Karte";
      d.appendChild(a); d.appendChild(o); liste.appendChild(d);
      fuss("kein Verzeichnis nötig — die Koordinate ist der Ort");
      liste.hidden = false; eingabe.setAttribute("aria-expanded", "true");
      return;
    }
    if (!key || !tr.length){ liste.hidden = true; eingabe.setAttribute("aria-expanded", "false"); return; }
    tr.slice(0, 6).forEach(function(t, i){
      var b = document.createElement("button");
      b.type = "button"; b.className = "treffer"; b.setAttribute("role", "option");
      b.setAttribute("aria-selected", i === 0 ? "true" : "false");
      var a = document.createElement("span"); a.className = "treffer__adr";
      a.textContent = t.strasse + " " + t.hnr;
      var o = document.createElement("span"); o.className = "treffer__ort";
      o.textContent = t.plz + " " + t.ort + (t.ortsteil && t.ortsteil !== t.ort ? " · " + t.ortsteil : "");
      b.appendChild(a); b.appendChild(o);
      b.addEventListener("click", function(){
        eingabe.value = t.strasse + " " + t.hnr; liste.hidden = true;
        eingabe.setAttribute("aria-expanded", "false");
      });
      liste.appendChild(b);
    });
    fuss("amtliche Hauskoordinaten Sachsen · 990.090 Adressen · lokal");
    liste.hidden = false; eingabe.setAttribute("aria-expanded", "true");
  }
  function fuss(text){
    var f = document.createElement("div");
    f.className = "liste__fuss"; f.textContent = text; liste.appendChild(f);
  }

  eingabe.addEventListener("input", function(){
    var v = eingabe.value;
    // Erkennen kostet nichts und laeuft sofort; nachgeschlagen wird entprellt.
    var r = classifyQuery(v);
    erkannt.textContent = queryKindLabel(r);
    erkannt.setAttribute("data-sicher", r.certain ? "1" : "0");
    if (timer) clearTimeout(timer);
    timer = setTimeout(function(){ suche(v); }, WARTE);
  });
  eingabe.addEventListener("blur", function(){
    setTimeout(function(){ liste.hidden = true; eingabe.setAttribute("aria-expanded", "false"); }, 160);
  });
  eingabe.addEventListener("focus", function(){ if (eingabe.value) suche(eingabe.value); });
  erkannt.textContent = queryKindLabel(classifyQuery(eingabe.value));
})();
