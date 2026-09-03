/**
 * The sentence under each check, composed from the data — not written by a
 * model.
 *
 * Every finding is a small pure function: structured input from one service,
 * a fixed German template out. That keeps three promises the project already
 * makes. The wording is reviewable, because there is a finite list of it. The
 * same plot always reads the same way. And a missing input can only ever
 * produce "—" or a "not surveyed" sentence, never a number talked into
 * existence.
 *
 * The templates take the shape of the data seriously. Noise arrives as 5 dB
 * bands, so the text says a range; a protected area arrives with a distance
 * bracket, so the text says "between"; a designation is a yes or a no, so the
 * text is a yes or a no. Where a service answers nothing, the distinction that
 * matters is whether it answered "not affected" or "no data here", and each
 * function carries that apart.
 */

import { num } from "./format.js";

/** The three states a check can end in. `open` never gets a colour. */
export const GOOD = "good";
export const NOTE = "note";
export const OPEN = "open";

/** `Lden5559` → `[55, 59]`, `LdenAb75` → `[75, null]`. */
export function readBand(category) {
  if (typeof category !== "string") return null;
  const open = /Ab(\d{2})$/.exec(category);
  if (open) return [Number(open[1]), null];
  const closed = /(\d{2})(\d{2})$/.exec(category);
  return closed ? [Number(closed[1]), Number(closed[2])] : null;
}

/** The span across a set of bands, as the widest range they cover. */
export function bandSpan(categories) {
  const bands = (categories ?? []).map(readBand).filter(Boolean);
  if (!bands.length) return null;
  const low = Math.min(...bands.map(b => b[0]));
  const highs = bands.map(b => b[1]);
  return highs.includes(null) ? [low, null] : [low, Math.max(...highs)];
}

const spanText = span =>
  span[1] === null ? `ab ${span[0]} dB(A)` : `${span[0]}–${span[1]} dB(A)`;

/** "Straßenverkehr", "Straßenverkehr und Straßenbahn", "A, B und C". */
function join(parts) {
  const list = parts.filter(Boolean);
  if (list.length <= 1) return list[0] ?? "";
  return `${list.slice(0, -1).join(", ")} und ${list[list.length - 1]}`;
}

const SOURCE_NAMES = { road: "Straßenverkehr", tram: "Straßenbahn", air: "Fluglärm", rail: "Schienenverkehr" };

/**
 * Noise.
 *
 * Three outcomes, not two. A hit gives the range. No hit inside a mapped area
 * means below the lowest band the survey draws. No mapping at all means no
 * statement — the plot is not quiet, it is unsurveyed, and the difference is
 * the whole point.
 *
 * @param {{day: Object<string,string[]>, night: Object<string,string[]>,
 *          mappedNearby: boolean, lowestBand: number}} data
 */
export function noiseFinding(data) {
  const { day = {}, night = {}, mappedNearby = false, lowestBand = 45 } = data ?? {};
  const sources = Object.keys(day).filter(key => (day[key] ?? []).length);
  const daySpan = bandSpan(sources.flatMap(key => day[key]));

  if (!daySpan) {
    if (!mappedNearby) {
      return {
        status: OPEN,
        value: "nicht kartiert",
        text: "Für diesen Ort liegt keine Umgebungslärmkartierung vor. Die Kartierung "
          + "erfasst Ballungsräume und Hauptverkehrswege — das Grundstück liegt außerhalb. "
          + "Das ist keine Aussage über die Ruhe am Ort."
      };
    }
    return {
      status: GOOD,
      value: `unter ${lowestBand} dB(A)`,
      text: `Das Grundstück liegt im kartierten Gebiet, aber in keinem Lärmband. `
        + `Damit liegt der Pegel unter der untersten kartierten Stufe von ${lowestBand} dB(A).`
    };
  }

  const nightSources = Object.keys(night).filter(key => (night[key] ?? []).length);
  const nightSpan = bandSpan(nightSources.flatMap(key => night[key]));
  const names = join(sources.map(key => SOURCE_NAMES[key] ?? key));

  const sentences = [`${names}, tags ${spanText(daySpan)}.`];
  if (nightSpan) sentences.push(`Nachts ${spanText(nightSpan)}.`);
  if (daySpan[1] !== null && daySpan[1] - daySpan[0] > 5) {
    sentences.push("Das Grundstück schneidet mehrere Bänder — der Wert gilt über die ganze Fläche, nicht für einen Punkt.");
  }
  // Named without an article: "Kein Straßenbahn" would be wrong, and the
  // genders differ across the sources.
  const quiet = Object.keys(SOURCE_NAMES).filter(key => !sources.includes(key) && key in day);
  if (quiet.length) sentences.push(`${join(quiet.map(k => SOURCE_NAMES[k]))}: nicht kartiert.`);

  // 55 dB(A) L_DEN is where the EU reporting threshold sits, so a plot that
  // reaches that band anywhere is worth a note -- even when its quieter half
  // pulls the lower bound down.
  const loudest = Math.max(...sources.flatMap(key => day[key]).map(readBand).filter(Boolean).map(b => b[0]));
  return {
    status: loudest >= 55 ? NOTE : GOOD,
    value: spanText(daySpan),
    text: sentences.join(" ")
  };
}

/**
 * A designated area the plot either sits in or does not — protected area,
 * water protection zone, flood extent, radon precaution area.
 *
 * @param {{name: string, hit: boolean, distanceFrom: number, distanceTo: number,
 *          alsoNearby: number, subject: string, absent: string}} data
 */
export function designationFinding(data) {
  const { hit = false, name = null, distanceFrom = null, distanceTo = null,
          alsoNearby = 0, subject = "Gebiet", absent = null, absentValue = null } = data ?? {};

  // `subject` is a bare noun. Every one of these is a "…gebiet" compound and
  // therefore neuter, so one set of articles serves them all.
  if (hit) {
    return {
      status: NOTE,
      value: "betroffen",
      text: name ? `Das Grundstück liegt im ${subject} „${name}".`
                 : `Das Grundstück liegt in einem ${subject}.`
    };
  }
  if (name && distanceTo !== null) {
    const distance = distanceFrom !== null
      ? `${num(distanceFrom, 0)}–${num(distanceTo, 0)} m`
      : `unter ${num(distanceTo, 0)} m`;
    const more = alsoNearby > 0
      ? ` Ein weiteres liegt innerhalb eines Kilometers.`
      : "";
    return {
      status: GOOD,
      value: `${distance} entfernt`,
      text: `Nächstes ${subject}: „${name}", ${distance} entfernt.${more}`
    };
  }
  return {
    status: GOOD,
    value: absentValue ?? "nicht betroffen",
    text: absent ?? `Kein ${subject} am Grundstück.`
  };
}

/**
 * Air quality. The station is chosen by whether it answers, not by distance —
 * so the text says how far away the answering one is.
 *
 * @param {{station: string, distanceKm: number, values: Object<string,number>, hours: number}} data
 */
export function airQualityFinding(data) {
  const { station = null, distanceKm = null, values = {}, hours = null } = data ?? {};
  const entries = Object.entries(values).filter(([, v]) => Number.isFinite(v));
  if (!station || !entries.length) {
    return {
      status: OPEN, value: "—",
      text: "Keine Messstation in erreichbarer Nähe liefert Werte."
    };
  }
  const LABELS = { no2: "NO₂", pm10: "PM10", pm25: "PM2,5", o3: "O₃" };
  const listed = entries.map(([key, v]) => `${LABELS[key] ?? key} ${num(v, 1)}`).join(" · ");
  const window = hours ? `, Mittel aus ${hours} Stundenwerten` : "";
  return {
    status: GOOD,
    value: `${LABELS[entries[0][0]] ?? entries[0][0]} ${num(entries[0][1], 1)} µg/m³`,
    text: `Station ${station}, ${num(distanceKm, 1)} km entfernt: ${listed} µg/m³${window}.`
  };
}

/**
 * Ground: the soil map's own description plus how much drilling evidence sits
 * nearby. Neither is a verdict — both are what a surveyor would look up first.
 *
 * @param {{soilText: string, boreholes: number, radiusM: number,
 *          nearestM: number, nearestDepthM: number, deepest: Object}} data
 */
export function groundFinding(data) {
  const { soilText = null, boreholes = 0, radiusM = 300,
          nearestM = null, nearestDepthM = null, deepest = null } = data ?? {};
  if (!soilText && !boreholes) {
    return { status: OPEN, value: "—", text: "Keine Bodenkarte und keine Aufschlussdaten am Ort." };
  }
  const parts = [];
  if (soilText) parts.push(`${soilText}.`);
  if (boreholes) {
    parts.push(`${boreholes} ${boreholes === 1 ? "Bohrung" : "Bohrungen"} im Umkreis von ${num(radiusM, 0)} m.`);
    if (nearestM !== null) {
      parts.push(`Nächste ${num(nearestM, 0)} m entfernt${
        nearestDepthM !== null ? `, Endteufe ${num(nearestDepthM, 1)} m` : ""}.`);
    }
    if (deepest?.depthM) {
      parts.push(`Tiefste in der Nähe ${num(deepest.depthM, 0)} m${deepest.year ? ` (${deepest.year})` : ""}.`);
    }
  }
  return {
    status: NOTE,
    value: boreholes ? `${boreholes} ${boreholes === 1 ? "Bohrung" : "Bohrungen"}` : "Bodenkarte",
    text: parts.join(" ")
  };
}

/**
 * A check with no data behind it. Says why, so the empty row is informative
 * rather than merely empty.
 */
export function unavailableFinding(reason) {
  return { status: OPEN, value: reason?.value ?? "—", text: reason?.text ?? "Für diese Prüfung liegen keine Daten vor." };
}

/** How many checks ended in each state — the counters that replace a score. */
export function tallyFindings(findings) {
  const counts = { [GOOD]: 0, [NOTE]: 0, [OPEN]: 0 };
  for (const finding of findings ?? []) {
    if (finding?.status in counts) counts[finding.status] += 1;
  }
  return counts;
}

/** "6 ohne Befund · 2 zu beachten · 3 offen" — plural-correct, no score. */
export function tallyText(counts) {
  const parts = [];
  if (counts[GOOD]) parts.push(`${counts[GOOD]} ohne Befund`);
  if (counts[NOTE]) parts.push(`${counts[NOTE]} zu beachten`);
  if (counts[OPEN]) parts.push(`${counts[OPEN]} offen`);
  return parts.join(" · ");
}
