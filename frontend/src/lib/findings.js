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

/* The neighbourhood's templates live beside this file, because they read a
   geometric analysis rather than one service's answer; they follow the same
   rules and are re-exported so every finding is reached from here. */
export {
  neighbourhoodFindings, houseCheckFinding, bandFinding, clearFinding, wallHeightFinding,
  boundaryReadingSentences, boundaryHeading, boundaryStatusLabel, clearBoundarySentence, sectionHeading,
  READING_DEFAULT_REASON, NEIGHBOURHOOD_STATUS_LABELS, HOUSE_STATUS_LABELS
} from "./neighbourhoodFindings.js";

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
 * How loud is that, in terms someone can picture?
 *
 * The bands are the survey's own 5 dB steps; what each one gets is a plain
 * label and one everyday consequence. The consequences are qualitative on
 * purpose: L_DEN is a rating level over 24 hours with evening and night
 * penalties, not a sound you could stand next to, so "as loud as a hairdryer"
 * would be wrong. What can honestly be said is what the level costs you —
 * whether the traffic intrudes on a conversation in the garden, whether a
 * window can stay open.
 *
 * The reference values are the WHO's, as reproduced in the UBA position paper
 * on the WHO environmental noise guidelines (2019): for road traffic, L_DEN
 * 53 dB(A) and L_night 45 dB(A) are the levels it recommends not exceeding,
 * and above L_DEN 65 dB(A) the cardiovascular risk rises measurably.
 */
const NOISE_LEVELS = [
  { upTo: 49, label: "leise",
    everyday: "Der Verkehr ist auf dem Grundstück kaum wahrnehmbar." },
  { upTo: 54, label: "mäßig",
    everyday: "Der Verkehr ist hörbar, ein Gespräch im Garten stört er nicht." },
  { upTo: 59, label: "deutlich hörbar",
    everyday: "Der Verkehr ist dauernd da; im Garten hebt man beim Sprechen die Stimme." },
  { upTo: 64, label: "laut",
    everyday: "Bei geöffnetem Fenster stört der Verkehr Gespräch und Fernsehen." },
  { upTo: 69, label: "sehr laut",
    everyday: "Dauerhaft laut. Ruhiges Wohnen setzt Schallschutzfenster voraus." },
  { upTo: Infinity, label: "sehr laut",
    everyday: "Sehr hohe Dauerbelastung. Schallschutz ist hier keine Frage der Bequemlichkeit." }
];

/** WHO values per source, as reproduced by the UBA (2019), in dB(A). */
export const WHO_LIMITS = {
  road: { den: 53, night: 45 },
  rail: { den: 54, night: 44 },
  air: { den: 45, night: 40 }
};
const RISK_DEN = 65;

const levelFor = value => NOISE_LEVELS.find(band => value <= band.upTo);

/**
 * Put a measured span in everyday terms and against the recommended value.
 *
 * The louder end of the span decides the wording: a plot that reaches 59 dB(A)
 * somewhere is not described by its quiet corner.
 */
export function noiseInterpretation(daySpan, nightSpan, source = "road") {
  if (!daySpan) return null;
  const loudest = daySpan[1] === null ? daySpan[0] : daySpan[1];
  const band = levelFor(loudest);
  const limits = WHO_LIMITS[source] ?? WHO_LIMITS.road;

  const notes = [];
  if (loudest > limits.den) {
    notes.push(`Über dem Wert von ${limits.den} dB(A), den die WHO für Straßenverkehr empfiehlt.`);
  } else {
    notes.push(`Unter dem Wert von ${limits.den} dB(A), den die WHO für Straßenverkehr empfiehlt.`);
  }
  if (loudest >= RISK_DEN) {
    notes.push(`Ab ${RISK_DEN} dB(A) steigt das Herz-Kreislauf-Risiko nachweislich.`);
  }
  if (nightSpan) {
    const nightLoudest = nightSpan[1] === null ? nightSpan[0] : nightSpan[1];
    notes.push(nightLoudest > limits.night
      ? `Nachts über der Empfehlung von ${limits.night} dB(A): bei gekipptem Fenster kann der Verkehr den Schlaf stören.`
      : `Nachts unter der Empfehlung von ${limits.night} dB(A).`);
  }
  return {
    label: band.label,
    everyday: band.everyday,
    notes,
    source: "WHO-Leitlinien, wiedergegeben im UBA-Positionspapier 2019"
  };
}

/**
 * Noise.
 *
 * A hit gives the range. Anything else is no value, and no value is never
 * quiet: the state survey maps main roads, trams in three cities and two
 * airports, so the street in front of a plot in no band is simply not in it —
 * a Bahnhofstraße in Naunhof, with a mapped Bundesstraße 1,5 km away, looked
 * as green as a meadow. Both no-value cases are therefore something to look at,
 * and they differ only in what can be said about the surroundings.
 *
 * @param {{day: Object<string,string[]>, night: Object<string,string[]>,
 *          mappedNearby: boolean, radius: string}} data
 */
export function noiseFinding(data) {
  const { day = {}, night = {}, mappedNearby = false, radius = "2 km" } = data ?? {};
  const sources = Object.keys(day).filter(key => (day[key] ?? []).length);
  const daySpan = bandSpan(sources.flatMap(key => day[key]));

  if (!daySpan) {
    const unknown = "Wie laut es am Grundstück ist, sagt die Karte damit nicht — "
      + "das lässt sich nur vor Ort hören, am besten zur Hauptverkehrszeit.";
    if (!mappedNearby) {
      return {
        status: NOTE,
        value: "keine Lärmdaten",
        text: `Im Umkreis von ${radius} ist nichts kartiert. Die Umgebungslärmkartierung `
          + "erfasst nur Hauptverkehrsstraßen, die Straßenbahn in Leipzig, Dresden und Chemnitz "
          + `und die Flughäfen. ${unknown}`
      };
    }
    return {
      status: NOTE,
      value: "keine Lärmdaten",
      text: "Das Grundstück liegt in keinem Lärmband. Kartiert sind nur Hauptverkehrsstraßen, "
        + "Straßenbahn und Flughäfen; die Straßen am Grundstück selbst sind darin nicht "
        + `erfasst. ${unknown}`
    };
  }

  const nightSources = Object.keys(night).filter(key => (night[key] ?? []).length);
  const nightSpan = bandSpan(nightSources.flatMap(key => night[key]));
  const names = join(sources.map(key => SOURCE_NAMES[key] ?? key));

  const sentences = [`${names}, tags ${spanText(daySpan)}.`];
  if (nightSpan) sentences.push(`Nachts ${spanText(nightSpan)}.`);
  if (daySpan[1] !== null && daySpan[1] - daySpan[0] > 5) {
    sentences.push("Das Grundstück schneidet mehrere Bänder; der Wert gilt über die ganze Fläche, nicht für einen Punkt.");
  }
  // Named without an article: "Kein Straßenbahn" would be wrong, and the
  // genders differ across the sources.
  const quiet = Object.keys(SOURCE_NAMES).filter(key => !sources.includes(key) && key in day);
  if (quiet.length) sentences.push(`${join(quiet.map(k => SOURCE_NAMES[k]))}: nicht kartiert.`);

  // 55 dB(A) L_DEN is where the EU reporting threshold sits, so a plot that
  // reaches that band anywhere is worth a note -- even when its quieter half
  // pulls the lower bound down.
  const loudest = Math.max(...sources.flatMap(key => day[key]).map(readBand).filter(Boolean).map(b => b[0]));
  const main = sources.includes("road") ? "road" : sources[0];
  return {
    status: loudest >= 55 ? NOTE : GOOD,
    value: spanText(daySpan),
    text: sentences.join(" "),
    interpretation: noiseInterpretation(daySpan, nightSpan, main)
  };
}

/**
 * A designated area the plot either sits in or does not — protected area,
 * water protection zone, flood extent, radon precaution area.
 *
 * @param {{name: string, hit: boolean, distanceFrom: number, distanceTo: number,
 *          alsoNearby: number, nearbyRadius: string, subject: string,
 *          absent: string}} data
 */
export function designationFinding(data) {
  const { hit = false, name = null, distanceFrom = null, distanceTo = null,
          alsoNearby = 0, nearbyRadius = "eines Kilometers", subject = "Gebiet",
          absent = null, absentValue = null } = data ?? {};

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
    // Plural-correct: the service answers with however many are in the ring,
    // and "Ein weiteres" beside three of them would be wrong.
    const more = alsoNearby > 0
      ? ` ${alsoNearby === 1 ? "Ein weiteres liegt" : `${alsoNearby} weitere liegen`}`
        + ` innerhalb ${nearbyRadius === "eines Kilometers" ? nearbyRadius : `von ${nearbyRadius}`}.`
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
 * @param {{station: string, distanceKm: number, values: Object<string,number>,
 *          hours: number, skipped: number}} data
 */
export function airQualityFinding(data) {
  const { station = null, distanceKm = null, values = {}, hours = null,
          skipped = 0 } = data ?? {};
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
  /* Why not the nearest one on the map: the station list mixes in research and
     historic sites that carry no measurements at all. Saying so turns a
     distance that looks careless into the reason it is what it is. */
  const nearer = skipped > 0
    ? ` ${skipped === 1 ? "Eine nähere Station liefert" : `${skipped} nähere Stationen liefern`}`
      + " keine Messwerte."
    : "";
  return {
    status: GOOD,
    value: `${LABELS[entries[0][0]] ?? entries[0][0]} ${num(entries[0][1], 1)} µg/m³`,
    text: `Station ${station}, ${num(distanceKm, 1)} km entfernt: ${listed} µg/m³${window}.${nearer}`
  };
}

/**
 * What the soil map's own wording means for someone building on it.
 *
 * "Hortisol über erodierter Parabraunerde aus gemischtem Schluff über tiefem
 * periglaziärem Kies führendem Lehm" is precise and tells a buyer nothing. The
 * words that carry the practical meaning are the grain sizes, and the soil map
 * spells them out in plain German — so the classification reads them straight
 * out of the text rather than parsing the KA5 code beside it.
 *
 * Clay, loam and silt make a cohesive soil: it holds water and drains slowly.
 * Sand and gravel make a coarse one that drains fast. Which of the two a plot
 * sits on decides whether soaking rainwater away on site is even a candidate,
 * and that is a question the buyer will have to answer anyway.
 *
 * What it deliberately does not say is anything about bearing capacity. A
 * 1:50 000 soil map is not a ground investigation, and the sentence says so.
 */
const COHESIVE_WORDS = ["ton", "lehm", "schluff"];
const COARSE_WORDS = ["sand", "kies"];

/** Air capacity class from the soil-parameter map, as its legend defines it. */
const AIR_CAPACITY = {
  LK_I: { label: "sehr gering", range: "< 2 Vol.-%", drains: false },
  LK_II: { label: "gering", range: "2 – 5 Vol.-%", drains: false },
  LK_III: { label: "mittel", range: "5 – 13 Vol.-%", drains: null },
  LK_IV: { label: "hoch", range: "13 – 26 Vol.-%", drains: true },
  LK_V: { label: "sehr hoch", range: "ab 26 Vol.-%", drains: true }
};

export function classifySoil(soilText, airCapacityClass = null) {
  const text = String(soilText ?? "").toLowerCase();
  if (!text) return null;
  const cohesive = COHESIVE_WORDS.filter(word => text.includes(word));
  const coarse = COARSE_WORDS.filter(word => text.includes(word));
  if (!cohesive.length && !coarse.length) return null;

  const capitalise = word => word[0].toUpperCase() + word.slice(1);
  const grains = [...cohesive, ...coarse].map(capitalise);
  const kind = cohesive.length && coarse.length ? "gemischt"
             : cohesive.length ? "bindig" : "rollig";
  const air = airCapacityClass ? AIR_CAPACITY[airCapacityClass] ?? null : null;

  const sentences = [];
  sentences.push(kind === "bindig"
    ? `Bindiger Boden (${grains.join(", ")}): er hält Wasser und lässt es langsam durch.`
    : kind === "rollig"
      ? `Rolliger Boden (${grains.join(", ")}): Wasser läuft rasch ab.`
      : `Gemischter Boden (${grains.join(", ")}): bindige und rollige Lagen wechseln sich ab.`);
  if (air) {
    sentences.push(`Luftkapazität ${air.label} (${air.range}).`);
  }
  if (kind === "bindig" && air && air.drains === true) {
    sentences.push("Ob Regenwasser vor Ort versickern kann, ist damit offen und muss geprüft werden.");
  } else if (kind === "bindig") {
    sentences.push("Regenwasser versickert hier voraussichtlich schlecht; ein Anschluss oder eine Rigole ist einzuplanen.");
  }
  return { kind, grains, air, text: sentences.join(" ") };
}

/**
 * Ground: what the soil is, what drilling evidence sits nearby, and the plain
 * statement that neither replaces a ground investigation.
 *
 * @param {{soilText: string, airCapacityClass: string, boreholes: number,
 *          radiusM: number, nearestM: number, nearestDepthM: number,
 *          deepest: Object, boreholesAsked: boolean}} data
 */
export function groundFinding(data) {
  const { soilText = null, airCapacityClass = null, boreholes = 0, radiusM = 300,
          nearestM = null, nearestDepthM = null, deepest = null,
          boreholesAsked = true } = data ?? {};
  if (!soilText && !boreholes) {
    return { status: OPEN, value: "—", text: "Keine Bodenkarte und keine Aufschlussdaten am Ort." };
  }
  const soil = classifySoil(soilText, airCapacityClass);
  const parts = [];
  if (soil) parts.push(soil.text);
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
  // A query the service refused and a neighbourhood nobody has drilled both
  // arrive as zero; only one of them is a statement about this plot.
  if (!boreholesAsked) {
    parts.push("Zu den Bohrungen in der Umgebung hat die Aufschlussdatenbank nicht geantwortet.");
  }
  parts.push("Die Bodenkarte 1:50.000 ersetzt keine Baugrunduntersuchung.");
  return {
    status: NOTE,
    value: soil ? soil.kind : "Bodenkarte",
    text: parts.join(" "),
    soil,
    detail: soilText ?? null
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

/* ------------------------------------------------------------------------ */
/* Bauleitplanung (RAPIS Sachsen) and Baulasten                             */
/* ------------------------------------------------------------------------ */

/** „2015-05-16" → „16.05.2015", read as the calendar day it is. Going
 *  through `Date` would move a date-only string by the viewer's time zone. */
function calendarDay(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? "");
  return match ? `${match[3]}.${match[2]}.${match[1]}` : null;
}

/** „der Stadt" for „Stadt Leipzig" or „Leipzig, Stadt", else „der Gemeinde". */
export function authorityOf(municipality) {
  return /(^|[\s,])Stadt($|[\s,])/.test(municipality ?? "") ? "der Stadt" : "der Gemeinde";
}

const isLeipzig = municipality => /\bLeipzig\b/.test(municipality ?? "");

const list = items => (items.length > 1 ? `${items.slice(0, -1).join(", ")} und ${items[items.length - 1]}` : items[0]);

/**
 * What RAPIS says about the plot, as findings in the shape of the
 * neighbourhood list: `{ id, status, statusLabel, title, sentences }`.
 *
 * An empty list of plans is a statement — RAPIS was asked and knows none — but
 * RAPIS is not complete, so it is never worded as „kein Bebauungsplan": the
 * sentence says what the register holds and who answers bindingly. A failed
 * request never reaches this function; the caller shows the backend's
 * `detail` instead.
 */
export function planningFindings(answer, municipality) {
  if (!answer || typeof answer !== "object") return [];
  const authority = authorityOf(municipality);
  const plans = Array.isArray(answer.bebauungsplaene) ? answer.bebauungsplaene : [];
  const statutes = Array.isArray(answer.satzungen) ? answer.satzungen : [];
  const out = [];

  for (const plan of plans) {
    const inForce = plan.status === "in Kraft";
    const sentences = inForce
      ? [`Liegt im Geltungsbereich von ${plan.name} (laut RAPIS Sachsen).`]
      : [`In RAPIS Sachsen ist hier ${plan.name} im Verfahren verzeichnet`
          + (plan.verfahrensstand && plan.verfahrensstand !== "im Verfahren"
            ? `, Verfahrensstand „${plan.verfahrensstand}“.` : ".")];
    const uses = (plan.art_der_nutzung ?? []).filter(Boolean);
    if (uses.length) sentences.push(`Art der Nutzung: ${list(uses)}.`);
    if (!inForce && plan.planstand) sentences.push(`Planstand: ${plan.planstand}.`);
    const announced = calendarDay(plan.bekanntgemacht_am);
    if (inForce && announced) sentences.push(`Bekannt gemacht am ${announced}.`);
    if (plan.info) sentences.push(`RAPIS vermerkt: ${plan.info}.`.replace(/\.\.$/, "."));
    sentences.push(inForce
      ? `Was er festsetzt, sagt der Plan selbst; verbindlich ist die städtebauliche Auskunft ${authority}.`
      : `Ein Plan im Verfahren ist noch nicht in Kraft; verbindlich ist die städtebauliche Auskunft ${authority}.`);
    out.push({
      id: `plan-${plan.rok_nr ?? plan.name}`,
      status: inForce ? "plan" : "procedure",
      statusLabel: inForce ? "in Kraft" : "im Verfahren",
      title: "Bebauungsplan",
      sentences
    });
  }

  for (const statute of statutes) {
    const inForce = statute.status === "in Kraft";
    const basis = statute.rechtsgrundlage ? ` (${statute.rechtsgrundlage})` : "";
    out.push({
      id: `statute-${statute.rok_nr ?? statute.name}`,
      status: inForce ? "plan" : "procedure",
      statusLabel: inForce ? "in Kraft" : "im Verfahren",
      title: "Satzung",
      sentences: [
        inForce
          ? `Liegt im Geltungsbereich der Satzung ${statute.name}${basis} (laut RAPIS Sachsen).`
          : `In RAPIS Sachsen ist hier die Satzung ${statute.name}${basis} im Verfahren verzeichnet.`
      ]
    });
  }

  if (!plans.length && !statutes.length) {
    out.push({
      id: "plan-none",
      status: "likely34",
      statusLabel: "wahrscheinlich § 34",
      title: "Bebauungsplan",
      sentences: [
        "In RAPIS kein Bebauungsplan verzeichnet – wahrscheinlich § 34 BauGB. "
          + `Verbindlich ist die städtebauliche Auskunft ${authority}.`
      ]
    });
  }

  const fnp = Array.isArray(answer.fnp) ? answer.fnp : [];
  if (fnp.length) {
    out.push({
      id: "fnp",
      status: "fnp",
      statusLabel: "Darstellung",
      title: "Flächennutzungsplan",
      sentences: fnp.map(entry => {
        const shown = (entry.darstellungen ?? []).filter(Boolean);
        const announced = calendarDay(entry.bekanntgemacht_am);
        const when = announced ? `, bekannt gemacht am ${announced}` : "";
        return shown.length
          ? `${list(shown)} (${entry.name}${when}).`
          : `${entry.name}${when}; eine Darstellung für das Grundstück führt RAPIS nicht.`;
      })
    });
  } else {
    out.push({
      id: "fnp",
      status: "open",
      statusLabel: "offen",
      title: "Flächennutzungsplan",
      sentences: ["In RAPIS ist für das Grundstück kein wirksamer Flächennutzungsplan verzeichnet."]
    });
  }
  return out;
}

/**
 * Baulasten are in no dataset: not in ALKIS, not in RAPIS. What can be said is
 * where they are kept and what it costs to ask — for Leipzig from the city's
 * own service page (docs/research/bebauungsplaene-sachsen.md), elsewhere only
 * which authority keeps the register.
 */
export function easementFinding(municipality) {
  const where = isLeipzig(municipality)
    ? "Auskunft gibt die Stadt Leipzig, Amt für Bauordnung und Denkmalpflege, bei berechtigtem Interesse "
      + "(§ 83 Abs. 5 SächsBO): 22–70 € je Grundstück, etwa vier Wochen."
    : "Auskunft gibt die untere Bauaufsichtsbehörde, die das Baulastenverzeichnis führt – für "
      + `${municipality || "das Grundstück"} der Landkreis oder die kreisfreie Stadt –, bei berechtigtem `
      + "Interesse (§ 83 Abs. 5 SächsBO).";
  return {
    id: "easement",
    status: "open",
    statusLabel: "nicht öffentlich",
    title: "Baulasten",
    sentences: [
      `Baulasten stehen nicht im Kataster und sind nicht öffentlich. ${where}`,
      "Eine Abstandsflächen-Baulast (§ 6 Abs. 2 SächsBO) stünde nur dort."
    ]
  };
}
