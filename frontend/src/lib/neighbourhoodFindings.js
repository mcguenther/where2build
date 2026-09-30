/**
 * The sentences under the neighbourhood analysis — composed, not written.
 *
 * Input is what `analyseNeighbourhood` and `checkHouse` return; output is
 * fixed German text in the shape the check list already uses, plus what the
 * plan needs to point at a building. Three rules from the statute and the
 * data hold for every template here:
 *
 * - The 6-m-Zone is never an obligation. Six metres is 3 + 3, the arithmetic
 *   of two minimal setback areas (§ 6 Abs. 5 and Abs. 3 SächsBO); where our
 *   wall would stand closer, the two areas would overlap, and whether that
 *   matters is a question for the Bauaufsicht.
 * - No wall height is ever stated. Neither ALKIS nor OSM carries one, so every
 *   figure rests on the 3 m floor, and the texts say so where it matters.
 * - A missing input gives no sentence or „—" (via format.js), never a number.
 */
import { num, metres, area } from "./format.js";
import {
  CLASS_BOUNDARY, CLASS_OVERLAP, CLASS_ACCESSORY, CLASS_OWN, CLASS_CLEAR,
  READING_BOUNDARY, HOUSE_INSIDE, HOUSE_ZONE, HOUSE_OUTSIDE, MINIMUM_SETBACK_M, ZONE_M
} from "./neighbourhood.js";

export const NEIGHBOURHOOD_STATUS_LABELS = {
  [CLASS_BOUNDARY]: "an der Grenze",
  [CLASS_OVERLAP]: "Überdeckung",
  [CLASS_ACCESSORY]: "zählt nicht",
  [CLASS_OWN]: "Bestand",
  [CLASS_CLEAR]: "ohne Befund",
  band: "Orientierung",
  heights: "offen"
};

export const HOUSE_STATUS_LABELS = {
  [HOUSE_INSIDE]: "im Bebauungsfenster",
  [HOUSE_ZONE]: "in der 6-m-Zone",
  [HOUSE_OUTSIDE]: "außerhalb"
};

/** Order of attention: the plan's markers run 1 … n in this order. */
const ATTENTION = [CLASS_BOUNDARY, CLASS_OVERLAP, CLASS_ACCESSORY, CLASS_OWN];

const THREE = metres(MINIMUM_SETBACK_M, 0);
const SIX = metres(ZONE_M, 0);

/** „12,3–28,1 m", or one value where both ends agree. */
function span(from, to) {
  if (!Number.isFinite(from) || !Number.isFinite(to)) return "—";
  return Math.abs(to - from) < 0.05 ? metres(from, 1) : `${num(from, 1)}–${num(to, 1)} m`;
}

const squareMetres = value => area(value, 1);

/** The building as a noun: the cadastre's own function, or plain „Gebäude". */
const noun = b => b.use || "Gebäude";

const titleOf = b => b.address || (b.class === CLASS_ACCESSORY ? "Nebengebäude" : noun(b));

/** Where along our boundary a building stands. Sides are measured from the
 *  street, so a span there reads „hinter der Straße"; the rear and the street
 *  front are named instead. */
function whereOnBoundary(facing) {
  if (!facing) return null;
  const { boundary, face } = facing;
  if (boundary === "left" || boundary === "right") return `${span(face.from, face.to)} hinter der Straße`;
  return boundary === "rear" ? "an der hinteren Grenze" : "an der Straßengrenze";
}

/** „3 m" for a whole number, „3,5 m" otherwise — the strip is as deep as our
 *  setback on that edge. */
const stripDepth = depth => num(depth, Number.isInteger(depth) ? 0 : 1);

/**
 * The two readings of a Grenzbebauung, each as one sentence. Exported so the
 * interface can show the one not chosen beside the switch.
 */
export function boundaryReadingSentences(b) {
  const zone = b.zone;
  const setback = zone
    ? `Abstand nötig: Die 6-m-Zone reicht hier bis ${metres(zone.depthFromBoundary)} von der Grenze, `
      + `${metres(zone.depth)} ins Bebauungsfenster (${squareMetres(zone.area)}). `
      + `Hier stünden die Häuser näher als ${SIX} – das klärt die Bauaufsicht.`
    : `Abstand nötig: Das Bebauungsfenster liegt überall mindestens ${SIX} von diesem Gebäude entfernt; `
      + "eine 6-m-Zone entsteht hier nicht.";
  const strip = b.maybeBuildable;
  const boundary = "An die Grenze darf gebaut werden: Dann braucht eine Wand an der Grenze keine "
    + "Abstandsfläche (§ 6 Abs. 1 Satz 3 SächsBO), auch unsere nicht."
    + (strip
      ? ` Der ${stripDepth(strip.depth)}-m-Streifen auf diesen ${metres(strip.length, 1)} wäre möglicherweise `
        + `bebaubar (${squareMetres(strip.area)}); das Bebauungsfenster bleibt gezeichnet, wie es ist.`
      : " Das Bebauungsfenster bleibt gezeichnet, wie es ist.");
  return { setback, boundary };
}

function boundaryFinding(b) {
  const where = whereOnBoundary(b.facing);
  const readings = boundaryReadingSentences(b);
  return {
    sentences: [
      `${noun(b)}, ${metres(b.gap)} vor unserer Grenze, auf ${metres(b.facing?.face.length, 1)} Länge ${where}.`,
      "Ob hier an die Grenze gebaut werden darf, sagt das Planungsrecht; bis das geklärt ist, gelten zwei Lesarten.",
      b.reading === READING_BOUNDARY ? readings.boundary : readings.setback
    ],
    reading: b.reading,
    readingSentences: readings
  };
}

function overlapFinding(b) {
  const where = whereOnBoundary(b.facing);
  const sentences = [`${noun(b)}, ${metres(b.gap)} vor unserer Grenze${where ? `, ${where}` : ""}.`];
  if (b.reach) {
    sentences.push(`Der Mindestabstand dieses Gebäudes von ${THREE} reicht ${metres(b.reach.depth)} `
      + `auf unser Grundstück (${squareMetres(b.reach.area)}).`);
  }
  sentences.push(b.zone
    ? `Im Bebauungsfenster liegt dort die 6-m-Zone, ${squareMetres(b.zone.area)}, bis ${metres(b.zone.depth)} tief: `
      + `Hier stünden die Häuser näher als ${SIX}, die Abstandsflächen würden sich überdecken `
      + "(§ 6 Abs. 3 SächsBO). Das klärt die Bauaufsicht; das Bebauungsfenster bleibt, wie es ist."
    : `Das Bebauungsfenster liegt überall mindestens ${SIX} von diesem Gebäude entfernt; eine 6-m-Zone entsteht nicht.`);
  return { sentences };
}

function accessoryFinding(b) {
  const beyond = b.facing?.beyond ?? 0;
  return {
    sentences: [
      `Laut Kataster ${noun(b)}, ${squareMetres(b.area)}, nach Größe eine Garage oder ein Schuppen; `
        + `${metres(b.gap)} vor unserer Grenze, an ihr ${metres(b.facing?.span.length, 1)} lang`
        + (beyond >= 0.05 ? `, davon ${metres(beyond, 1)} hinter unserer Ecke.` : "."),
      "Garagen und Gebäude ohne Aufenthaltsräume und Feuerstätten mit bis zu 3 m mittlerer Wandhöhe "
        + "und 9 m Länge je Grenze haben keine eigenen Abstandsflächen (§ 6 Abs. 8 Nr. 1 SächsBO). "
        + "Als ein solches ist es hier eingeordnet; die Wandhöhe führt das Kataster nicht."
    ]
  };
}

function ownFinding(own) {
  const listed = own.map(b => `${noun(b)} mit ${squareMetres(b.area)}`);
  const list = listed.length > 1 ? `${listed.slice(0, -1).join(", ")} und ${listed[listed.length - 1]}` : listed[0];
  const nearest = Math.min(...own.map(b => b.toBoundary).filter(Number.isFinite));
  const sentences = [own.length === 1
    ? `Auf dem Grundstück steht ein Gebäude: ${list}.`
    : `Auf dem Grundstück stehen ${own.length} Gebäude: ${list}.`];
  if (Number.isFinite(nearest)) sentences.push(`Der geringste Abstand zur Grenze beträgt ${metres(nearest)}.`);
  sentences.push("Das Bebauungsfenster gilt für das, was neu gebaut wird.");
  return { sentences };
}

/** The § 34 band: orientation for „Einfügen", never a limit. */
export function bandFinding(band) {
  if (!band) return null;
  const window = metres(band.window, 0);
  const note = "Ein Anhalt dafür, was sich nach § 34 BauGB einfügt, keine Grenze.";
  const n = band.houses.length;
  let first;
  if (!n) {
    first = `Auf unserer Straßenseite steht bis ${window} entlang der Straße kein Wohnhaus, `
      + "an dem sich ablesen ließe, wie tief hier gebaut wird.";
    return { id: "band", marker: null, buildingId: null, status: "band", statusLabel: NEIGHBOURHOOD_STATUS_LABELS.band,
      title: "Umgebung (§ 34 BauGB)", sentences: [first] };
  }
  first = n === 1
    ? `Das Nachbarhaus auf unserer Straßenseite (bis ${window} entlang der Straße) steht `
      + `${span(band.front.min, band.front.max)} hinter der Straße und reicht bis ${metres(band.rear.max, 1)} tief.`
    : `Die ${n} Nachbarhäuser auf unserer Straßenseite (bis ${window} entlang der Straße) stehen `
      + `${span(band.front.min, band.front.max)} hinter der Straße und reichen bis ${metres(band.rear.max, 1)} tief.`;
  return {
    id: "band", marker: null, buildingId: null, status: "band", statusLabel: NEIGHBOURHOOD_STATUS_LABELS.band,
    title: "Umgebung (§ 34 BauGB)", sentences: [first, note]
  };
}

/** Everything else within reach, in one line. */
export function clearFinding(clear) {
  if (!clear) return null;
  const reach = metres(clear.reach, 0);
  let sentence;
  if (!clear.count) sentence = `Bis ${reach} um das Grundstück steht kein weiteres Gebäude.`;
  else if (clear.count === 1) {
    sentence = `Das übrige Gebäude bis ${reach} steht ${metres(clear.nearest, 1)} von unseren Grenzen entfernt.`;
  } else {
    sentence = `Die übrigen ${clear.count} Gebäude bis ${reach} stehen mindestens ${THREE} von unseren Grenzen `
      + `entfernt, das nächste ${metres(clear.nearest, 1)}.`;
  }
  return { id: "clear", marker: null, buildingId: null, status: CLASS_CLEAR,
    statusLabel: NEIGHBOURHOOD_STATUS_LABELS[CLASS_CLEAR], title: "Übrige Gebäude", sentences: [sentence] };
}

/** Said once, because every number above rests on it. */
export function wallHeightFinding() {
  return {
    id: "heights", marker: null, buildingId: null, status: "heights", statusLabel: NEIGHBOURHOOD_STATUS_LABELS.heights,
    title: "Wandhöhen",
    sentences: [`Die Gebäudeumrisse tragen keine Wandhöhen. Gerechnet ist überall das Mindestmaß von ${THREE}, `
      + "nie 0,4 H; ein höheres Nachbarhaus hätte eine tiefere Abstandsfläche."]
  };
}

/**
 * The analysis as an ordered list of findings.
 *
 * First the buildings, numbered 1 … n by how much attention they need
 * (Grenzbebauung, Überdeckung, Nebengebäude, our own Bestand — within a class
 * the nearest first); these are the ones the plan carries a marker for. Then,
 * unnumbered, the § 34 band, the summary of everything clear and the note on
 * wall heights. Every entry is
 * `{ id, marker, buildingId, status, statusLabel, title, sentences[] }`; a
 * Grenzbebauung also carries `reading` and `readingSentences`.
 * An analysis with no buildings at all gives an empty list: whether the
 * source had none or failed is for the caller to say.
 */
export function neighbourhoodFindings(analysis) {
  if (!analysis || analysis.empty || !analysis.buildings?.length) return [];
  const byGap = (a, b) => (a.gap ?? 0) - (b.gap ?? 0);
  const numbered = [];
  for (const kind of ATTENTION) {
    const members = analysis.buildings.filter(b => b.class === kind).sort(byGap);
    if (kind === CLASS_OWN) {
      if (!members.length) continue;
      const main = members.find(b => b.useKind === "residential") ?? [...members].sort((a, b) => b.area - a.area)[0];
      numbered.push({
        id: `own-${main.id}`, buildingId: main.id, status: CLASS_OWN,
        statusLabel: NEIGHBOURHOOD_STATUS_LABELS[CLASS_OWN],
        title: main.address ? `${main.address} (Bestand)` : "Bestand",
        buildingIds: members.map(b => b.id),
        ...ownFinding(members)
      });
      continue;
    }
    for (const b of members) {
      const body = kind === CLASS_BOUNDARY ? boundaryFinding(b)
        : kind === CLASS_OVERLAP ? overlapFinding(b) : accessoryFinding(b);
      numbered.push({
        id: `building-${b.id}`, buildingId: b.id, status: kind,
        statusLabel: NEIGHBOURHOOD_STATUS_LABELS[kind], title: titleOf(b), ...body
      });
    }
  }
  const list = numbered.map((f, i) => ({ ...f, marker: i + 1 }));
  return [...list, bandFinding(analysis.band), clearFinding(analysis.clear), wallHeightFinding()].filter(Boolean);
}

/**
 * The line under the placed house: green inside the envelope and clear of
 * every zone that applies, amber where it reaches into one, red where a
 * corner leaves the envelope. `check` is what `checkHouse` returned.
 */
export function houseCheckFinding(check) {
  if (!check) return null;
  const base = { id: "house", marker: null, buildingId: null, status: check.status,
    statusLabel: HOUSE_STATUS_LABELS[check.status], title: "Baukörper" };
  const nearest = Number.isFinite(check.toBoundary) ? `Geringster Grenzabstand ${metres(check.toBoundary)}.` : null;
  if (check.status === HOUSE_OUTSIDE) {
    const k = check.cornersOutside;
    return { ...base, sentences: [
      `${k} Gebäudeecke${k > 1 ? "n liegen" : " liegt"} außerhalb des Bebauungsfensters.`,
      nearest,
      check.inMaybeBuildable
        ? `${k > 1 ? "Sie liegen" : "Sie liegt"} im Streifen, der möglicherweise bebaubar ist, wenn an die Grenze `
          + "gebaut werden darf – das klärt die Bauaufsicht."
        : null
    ].filter(Boolean) };
  }
  if (check.status === HOUSE_ZONE) {
    const name = z => z.address || "einem Nachbargebäude";
    const [first, ...rest] = check.zones;
    const more = rest.map(z => ` und ${metres(z.intrusion)} in die zu ${name(z)}`).join("");
    return { ...base, sentences: [
      `Baukörper liegt im Bebauungsfenster, reicht aber ${metres(first.intrusion)} in die 6-m-Zone zu `
        + `${name(first)}${more} – eine Frage an die Bauaufsicht.`
    ] };
  }
  return { ...base, sentences: ["Baukörper liegt im Bebauungsfenster.", nearest].filter(Boolean) };
}
