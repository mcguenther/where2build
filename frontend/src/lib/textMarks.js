/**
 * What the browser itself can already see in a pasted description.
 *
 * The folded text in the search field marks these before anything is sent:
 * an area, a Gemarkung name, a statement about planning law. It is a preview
 * of *where* the search will look, not a reading of what it will find — the
 * backend does the reading, and none of this decides anything. So the
 * patterns stay narrow: a mark that is not there is harmless, a mark on the
 * wrong word would tell the user the search understood something it did not.
 */
import { fold } from "./districts.js";

/** „ca. 1.025 qm“, „866 m²“, „rund 1100 Quadratmeter“. */
const AREA = /(?:(?:ca\.?|circa|rund|etwa|ab)\s*)?\d{1,3}(?:\.\d{3})*(?:,\d+)?\s*(?:m²|m2|qm|Quadratmeter)(?![\p{L}\d])/giu;

/** The statements about planning law a listing makes in so many words. */
const LAW = /§\s*3[45]\s*BauGB|Bebauungsplan|B-Plan|Außenbereich|Innenbereich/giu;

/** A Gemarkung name is at most this many words; „Arnsdorf-Hilbersdorf Flur 1“. */
const MAX_NAME_WORDS = 4;
/** Shorter names match inside ordinary prose too often to be worth marking. */
const MIN_NAME_LENGTH = 4;

/** German labels for the kinds of mark, in the order the footer lists them. */
export const MARK_LABELS = { area: "Fläche", law: "Planungsrecht", place: "Ort" };

/** The directory as a set of folded names, built once per directory. */
const nameSets = new WeakMap();
function namesOf(directory) {
  if (!Array.isArray(directory) || !directory.length) return null;
  let names = nameSets.get(directory);
  if (!names) {
    names = new Set(
      directory
        .map(entry => entry?.name)
        .filter(name => name && name.length >= MIN_NAME_LENGTH)
        .map(name => fold(name))
    );
    nameSets.set(directory, names);
  }
  return names;
}

/** Capitalised words with their positions, so a phrase can be cut back out. */
function words(text) {
  const found = [];
  const pattern = /[\p{Lu}][\p{L}\-]*/gu;
  let match;
  while ((match = pattern.exec(text))) {
    found.push({ start: match.index, end: match.index + match[0].length });
  }
  return found;
}

function placeMarks(text, directory) {
  const names = namesOf(directory);
  if (!names) return [];
  const marks = [];
  const list = words(text);
  for (let i = 0; i < list.length; i++) {
    // Longest phrase first: „Altstadt Borna“ before „Altstadt“.
    for (let n = Math.min(MAX_NAME_WORDS, list.length - i); n >= 1; n--) {
      const start = list[i].start;
      const end = list[i + n - 1].end;
      const phrase = text.slice(start, end);
      // Only words separated by single spaces form one name.
      if (n > 1 && /\s{2,}|[^\p{L}\s\-\d]/u.test(phrase)) continue;
      if (names.has(fold(phrase))) {
        marks.push({ start, end, kind: "place" });
        i += n - 1;
        break;
      }
    }
  }
  return marks;
}

function patternMarks(text, pattern, kind) {
  const marks = [];
  pattern.lastIndex = 0;
  let match;
  while ((match = pattern.exec(text))) {
    marks.push({ start: match.index, end: match.index + match[0].length, kind });
  }
  return marks;
}

/**
 * Cut the text into plain and marked pieces.
 *
 * @param {string} text the description as pasted
 * @param {Array<{name: string}>} [directory] the Gemarkung directory, if loaded
 * @returns {{segments: Array<{text: string, kind: string|null}>, kinds: string[], first: number}}
 *   `kinds` lists the kinds that occur, in `MARK_LABELS` order; `first` is the
 *   offset of the first mark, or -1.
 */
export function markText(text, directory = null) {
  const source = String(text ?? "");
  const all = [
    ...patternMarks(source, AREA, "area"),
    ...patternMarks(source, LAW, "law"),
    ...placeMarks(source, directory)
  ].sort((a, b) => a.start - b.start || b.end - a.end);

  // Overlaps go to the mark that starts first; the others are dropped whole.
  const marks = [];
  for (const mark of all) {
    const last = marks[marks.length - 1];
    if (last && mark.start < last.end) continue;
    marks.push(mark);
  }

  const segments = [];
  let at = 0;
  for (const mark of marks) {
    if (mark.start > at) segments.push({ text: source.slice(at, mark.start), kind: null });
    segments.push({ text: source.slice(mark.start, mark.end), kind: mark.kind });
    at = mark.end;
  }
  if (at < source.length) segments.push({ text: source.slice(at), kind: null });

  const present = new Set(marks.map(mark => mark.kind));
  return {
    segments,
    kinds: Object.keys(MARK_LABELS).filter(kind => present.has(kind)),
    first: marks.length ? marks[0].start : -1
  };
}

/** How many words a text has, for the line under a folded description. */
export function wordCount(text) {
  const found = String(text ?? "").match(/[\p{L}\d][\p{L}\d.,'’\-]*/gu);
  return found ? found.length : 0;
}
