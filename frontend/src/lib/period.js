/**
 * The period the administration area asks about.
 *
 * Three presets and a free range, and one rule behind both: the browser works
 * out the two moments and sends them, rather than sending a word like
 * „Woche“ for the server to interpret. A week begins where the person
 * standing in front of the screen is, and the server has no way of knowing
 * that — it would have to agree with the browser about the time zone, and two
 * places computing one period is where an off-by-one hour comes from.
 *
 * The grid follows the span rather than being chosen: hours over a short
 * period, days over a long one. Hourly buckets over a month are 720 bars in a
 * chart that is 600 pixels wide, which is not a chart.
 */

const DAY_MS = 24 * 3600 * 1000;

/** How far back each preset reaches, and how its points are grouped. */
export const PRESETS = [
  { id: "day", label: "24 Stunden", days: 1, grid: "stunde" },
  { id: "week", label: "7 Tage", days: 7, grid: "tag" },
  { id: "month", label: "30 Tage", days: 30, grid: "tag" }
];

/** Hours up to three days, days beyond that. */
export const gridFor = (from, to) => (to - from <= 3 * DAY_MS ? "stunde" : "tag");

/** The period of one preset, ending now. */
export function rangeFor(id) {
  const preset = PRESETS.find(entry => entry.id === id) || PRESETS[0];
  const to = new Date();
  return { from: new Date(to.getTime() - preset.days * DAY_MS), to, grid: preset.grid };
}

/**
 * A period from two `<input type="date">` values.
 *
 * The end is the end of its day, not its midnight: somebody who picks the same
 * date twice means that day, and a period of zero length would answer 400.
 */
export function rangeFromDates(fromValue, toValue) {
  const from = new Date(`${fromValue}T00:00:00`);
  const to = new Date(`${toValue}T23:59:59`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to <= from) return null;
  return { from, to, grid: gridFor(from, to) };
}

/** A date as `<input type="date">` wants it — local, never the UTC of toISOString. */
export const dateValue = date =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

/** The start of the hour or the day a moment falls in, locally. */
const floorTo = (moment, grid) => {
  const start = new Date(moment);
  start.setMinutes(0, 0, 0);
  if (grid === "tag") start.setHours(0, 0, 0, 0);
  return start;
};

/**
 * One entry per hour or day of the period, whether or not anything was counted.
 *
 * The server answers only the buckets it has rows for, which is right for a
 * table and wrong for a chart: a quiet night would close the gap and put
 * yesterday's bar next to this morning's, so the picture would show a busy
 * stretch that never happened. An hour with no row means no request was
 * counted in it, and a bar of height zero is what that looks like.
 *
 * Bounded, because the period is: 400 days by hour would be ten thousand bars,
 * and the grid only ever produces hours over short spans.
 */
export function fillSeries(points, from, to, grid) {
  const known = new Map(
    points.map(point => [floorTo(new Date(point.zeit), grid).getTime(), point])
  );
  const slots = [];
  const cursor = floorTo(from, grid);
  while (cursor.getTime() <= to.getTime() && slots.length < 1000) {
    const key = cursor.getTime();
    slots.push(
      known.get(key) || {
        zeit: new Date(key).toISOString(),
        anfragen: 0,
        fehler: 0,
        limitiert: 0,
        dauer_ms: 0,
        tokens_ein: 0,
        tokens_aus: 0
      }
    );
    if (grid === "tag") cursor.setDate(cursor.getDate() + 1);
    else cursor.setHours(cursor.getHours() + 1);
  }
  return slots;
}
