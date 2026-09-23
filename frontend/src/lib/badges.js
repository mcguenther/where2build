/**
 * The candidates' number badges, and what happens when two of them meet.
 *
 * At district scale two plots a street apart land on the same pixel, and one
 * badge hides the other — the map then shows "2" and the table two rows. So
 * badges that would overlap are merged into one that says what it holds.
 */

/** How close two badge centres may come before they merge, in CSS pixels.
 *  A badge is 24 px wide; below this the rings touch. */
export const MERGE_DISTANCE_PX = 28;

/**
 * Group screen points that lie within `distance` of each other, transitively.
 *
 * Single linkage rather than a grid: a grid splits two touching badges that
 * straddle a cell edge and merges two that do not touch. The candidate list is
 * capped well below where the pairwise loop would cost anything.
 *
 * @param {{x: number, y: number}[]} points
 * @returns {number[][]} indices into `points`, each group ascending, the groups
 *   ordered by their first index
 */
export function groupByDistance(points, distance = MERGE_DISTANCE_PX) {
  const parent = points.map((_, i) => i);
  const root = i => (parent[i] === i ? i : (parent[i] = root(parent[i])));
  const limit = distance * distance;
  for (let a = 0; a < points.length; a++) {
    for (let b = a + 1; b < points.length; b++) {
      const dx = points[a].x - points[b].x;
      const dy = points[a].y - points[b].y;
      if (dx * dx + dy * dy < limit) parent[root(b)] = root(a);
    }
  }
  const groups = new Map();
  points.forEach((_, i) => {
    const key = root(i);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(i);
  });
  return [...groups.values()].sort((g, h) => g[0] - h[0]);
}

/**
 * Row numbers as compact German text: `1, 2, 4–7`.
 *
 * A run of three or more becomes a range with an en dash; two neighbours stay
 * a list, because „1–2“ reads as a span with something between.
 */
export function compactRanges(numbers) {
  const sorted = [...new Set(numbers)].sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < sorted.length;) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    if (j - i >= 2) parts.push(`${sorted[i]}–${sorted[j]}`);
    else for (let k = i; k <= j; k++) parts.push(String(sorted[k]));
    i = j + 1;
  }
  return parts.join(", ");
}
