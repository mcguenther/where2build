/**
 * Matching against the cadastral district directory.
 *
 * Two components search the same 5 300 entries — the picker in the wizard and
 * the search field — and they have to agree about what "Mölkau" and "3044"
 * mean, so the matching lives here rather than twice.
 */

/** Every Saxon key is six digits and starts with 14 — see CLAUDE.md. */
export const LAND_PREFIX = "14";
export const DISTRICT_NUMBER_LENGTH = 4;

/** Lower case, without diacritics, so "Molkau" finds "Mölkau". */
export function fold(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/**
 * The forms of one key a user may have in front of them. The Geoportal prints
 * the six-digit key on its Gemarkung layer and the four-digit district number
 * on its Flurstueck layer, and a number that has been through a spreadsheet
 * has lost its leading zero.
 */
export function keyForms(key) {
  const forms = [key];
  if (key.length === LAND_PREFIX.length + DISTRICT_NUMBER_LENGTH && key.startsWith(LAND_PREFIX)) {
    const short = key.slice(LAND_PREFIX.length);
    forms.push(short, short.replace(/^0+/, ""));
  }
  return forms;
}

/** How well an entry answers the query, or `null` if it does not. Lower is better. */
export function rankDistrict(entry, typed) {
  const needle = fold(typed).trim();
  if (!needle) return null;
  const name = fold(entry.name);
  if (name.startsWith(needle)) return 0;
  const trimmed = String(typed).trim();
  if (/^\d+$/.test(trimmed) && keyForms(entry.schluessel).some(form => form.startsWith(trimmed))) return 1;
  if (name.includes(needle)) return 2;
  return null;
}

/** The directory entries a query matches, best first. */
export function searchDistricts(directory, typed, limit = 50) {
  const scored = [];
  (directory ?? []).forEach(entry => {
    const rank = rankDistrict(entry, typed);
    if (rank !== null) scored.push({ entry, rank });
  });
  scored.sort((a, b) => a.rank - b.rank);
  return { hits: scored.slice(0, limit).map(s => s.entry), total: scored.length };
}

/** The entries the text names outright, rather than merely resembles. */
export function exactDistricts(directory, typed) {
  const needle = fold(typed).trim();
  const trimmed = String(typed).trim();
  if (!needle) return [];
  return (directory ?? []).filter(
    entry => fold(entry.name) === needle || keyForms(entry.schluessel).includes(trimmed)
  );
}
