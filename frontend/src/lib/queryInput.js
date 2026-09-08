/**
 * What did the user type — an address, a parcel, or a coordinate?
 *
 * The search field takes all three, and guessing wrong is expensive in both
 * directions: querying the address index for "51.33652, 12.44176" is wasted
 * work, and refusing to query it for "Lessingweg 44" leaves the field dead.
 *
 * Three signals carry almost all of the decision, cheapest first:
 *
 *  - **A German address never begins with a digit.** "Lessingweg 44", never
 *    "44 Lessingweg". So a leading digit rules the address index out after the
 *    first character — which is the point at which we can stop querying it.
 *  - **A coordinate is two numbers and nothing else.** Once the non-numeric
 *    characters are separators, degree signs or hemisphere letters, what is
 *    left is a pair — and the pair either falls inside Germany or it does not.
 *  - **A parcel number is a number, optionally over a denominator** (`85/1`,
 *    `41/e`), and it needs a cadastral district beside it to mean anything.
 *  - **A link and a listing text are neither**: one is fetched, the other
 *    read, and asking any index about them is wasted work.
 *
 * Where two readings stay plausible the answer says so rather than picking:
 * both indexes are local, so searching both and grouping the results costs a
 * few milliseconds and never shows the user a wrong guess.
 */

/** Saxony sits well inside these; the bounds are Germany's, generously drawn. */
const LAT_RANGE = [47.0, 55.2];
const LON_RANGE = [5.6, 15.3];

/** UTM zone 33N, the projection the Saxon cadastre answers in. */
const EASTING_RANGE = [180000, 900000];
const NORTHING_RANGE = [5200000, 6100000];

/** The AdV parcel key: 20 characters, digits padded with underscores. */
const ADV_KEY = /^\d{6}[\d_]{9}[\d_]{5}$/;

/** A parcel number: numerator, optionally a denominator that may be a letter. */
const PARCEL_NUMBER = /^(\d{1,5})(?:\s*\/\s*([0-9a-z]{1,3}))?$/i;

/** Six- or four-digit cadastral district key. */
const DISTRICT_KEY = /^(?:14)?\d{4}$/;

/** Beyond this, a line is not a query any more but the text of a listing.
 *  The longest real address measured in the Saxon index is well under it. */
const PROSE_LENGTH = 160;

const inRange = (value, [low, high]) => value >= low && value <= high;

/**
 * Pull the plain numbers out of a coordinate-ish string.
 *
 * Handles the German decimal comma, degree signs and hemisphere letters. The
 * awkward case is "51,33652, 12,44176", where the comma is both the decimal
 * mark and the separator; splitting on whitespace first and only then on a
 * comma that is not between digits keeps the two apart.
 */
function readNumbers(text) {
  const cleaned = text
    .replace(/[NnSsEeOoWw]\b/g, " ")
    .replace(/[°'"´`]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return [];
  // A comma with a digit on both sides is a decimal mark; any other comma or
  // semicolon separates. Normalise the first to a dot, the second to a space.
  const normalised = cleaned
    .replace(/(\d)\s*,\s*(\d{3,})/g, "$1.$2")
    .replace(/[,;]/g, " ");
  const parts = normalised.split(/\s+/).filter(Boolean);
  if (!parts.every(part => /^-?\d+(?:\.\d+)?$/.test(part))) return [];
  return parts.map(Number);
}

/** Would a coordinate reading of these numbers land in Germany? */
function asCoordinate(numbers) {
  if (numbers.length !== 2) return null;
  const [first, second] = numbers;
  if (inRange(first, LAT_RANGE) && inRange(second, LON_RANGE)) {
    return { lat: first, lon: second, system: "wgs84", swapped: false };
  }
  // Some sources write lon first. Only accept it when the other order does not
  // read at all, so an ambiguous pair is never silently reordered.
  if (inRange(second, LAT_RANGE) && inRange(first, LON_RANGE)) {
    return { lat: second, lon: first, system: "wgs84", swapped: true };
  }
  if (inRange(first, EASTING_RANGE) && inRange(second, NORTHING_RANGE)) {
    return { easting: first, northing: second, system: "utm33" };
  }
  return null;
}

/**
 * Classify what is in the search field.
 *
 * @param {string} raw what the user has typed so far
 * @returns {{kind: string, certain: boolean, search: string[], …}}
 *   `kind` is the reading; `search` names the indexes worth querying, so a
 *   caller can act on the answer without re-deriving it. `kind: "unclear"`
 *   with an empty `search` means: too little typed to look anything up.
 */
export function classifyQuery(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return { kind: "empty", certain: true, search: [] };

  // 0 — a link, and a whole listing text. Neither is a place to look up: the
  //     first is fetched, the second is read. Both would otherwise fall
  //     through to the letters-only case and query the address index with a
  //     paragraph.
  if (/^https?:\/\/\S{6,}$/i.test(text)) {
    return { kind: "url", certain: true, search: [], url: text };
  }
  if (text.length > PROSE_LENGTH || text.includes("\n")) {
    return { kind: "prose", certain: true, search: [], text };
  }

  const compact = text.replace(/\s+/g, "");

  // 1 — the 20-character parcel key is unmistakable.
  if (ADV_KEY.test(compact)) {
    return { kind: "parcel", certain: true, search: ["parcel"], parcelKey: compact };
  }

  // 2 — a pair of numbers that lands in Germany.
  const numbers = readNumbers(text);
  const coordinate = asCoordinate(numbers);
  if (coordinate) {
    return { kind: "coordinate", certain: true, search: ["coordinate"], coordinate };
  }

  const startsWithDigit = /^\d/.test(text);

  // 3 — a bare parcel number. Means nothing without a district, so say which
  //     half is missing rather than searching for it.
  const bare = PARCEL_NUMBER.exec(text);
  if (bare) {
    if (DISTRICT_KEY.test(text) && !text.includes("/")) {
      // Four or six digits alone read as a district key just as well as a
      // parcel number — both, and let the caller show both.
      return {
        kind: "parcel", certain: false, search: ["district", "parcel"],
        missing: "parcelNumber", districtKey: text
      };
    }
    return {
      kind: "parcel", certain: false, search: [],
      missing: "district",
      parcelNumber: { numerator: bare[1], denominator: bare[2] ?? null }
    };
  }

  // 4 — district and parcel number together: "Mölkau 204", "143044 85/1".
  const split = text.match(/^(.*?)[\s,;]+(\d{1,5}(?:\s*\/\s*[0-9a-z]{1,3})?)$/i);
  if (split) {
    const head = split[1].trim();
    const tail = split[2].replace(/\s+/g, "");
    // A house number is short and the head reads as a street; a parcel
    // denominator ("85/1") cannot appear in an address, so it decides.
    if (tail.includes("/")) {
      return {
        kind: "parcel", certain: true, search: ["parcel"],
        district: head, parcelNumber: parseParcelNumber(tail)
      };
    }
    if (DISTRICT_KEY.test(head)) {
      return {
        kind: "parcel", certain: true, search: ["parcel"],
        districtKey: head, parcelNumber: parseParcelNumber(tail)
      };
    }
    // "Lessingweg 44" and "Mölkau 204" are the same shape. Both indexes are
    // local; ask both and group what comes back.
    return {
      kind: "ambiguous", certain: false, search: ["address", "parcel"],
      street: head, houseNumber: tail, district: head,
      parcelNumber: parseParcelNumber(tail)
    };
  }

  // 5 — starts with a digit but is neither a coordinate nor a parcel number:
  //     nothing in the address index will match, so do not ask it.
  if (startsWithDigit) {
    return { kind: "unclear", certain: false, search: [] };
  }

  // 6 — letters only. A street on its way to being typed, or a district name.
  return { kind: "ambiguous", certain: false, search: ["address", "district"], text };
}

function parseParcelNumber(token) {
  const match = PARCEL_NUMBER.exec(token);
  if (!match) return null;
  return { numerator: match[1], denominator: match[2] ?? null };
}

/** German label for what was recognised — for the badge beside the field. */
export function queryKindLabel(result) {
  switch (result.kind) {
    case "coordinate":
      return result.coordinate?.system === "utm33" ? "Koordinate (UTM 33)" : "Koordinate";
    case "parcel":
      return result.certain ? "Flurstück" : "Flurstück, Gemarkung fehlt";
    case "address":
      return "Adresse";
    case "ambiguous":
      return "Adresse oder Flurstück";
    case "url":
      return "Link zur Anzeige";
    case "prose":
      return "Beschreibungstext";
    default:
      return "";
  }
}
