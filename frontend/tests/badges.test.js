/**
 * Merging the candidates' number badges where they would overlap.
 */
import { describe, expect, it } from "vitest";
import { MERGE_DISTANCE_PX, compactRanges, groupByDistance } from "../src/lib/badges.js";

describe("Die Beschriftung einer zusammengelegten Marke", () => {
  it("schreibt zwei Nachbarn als Aufzählung", () => {
    // „1–2“ reads as a span with something in between.
    expect(compactRanges([1, 2])).toBe("1, 2");
  });

  it("fasst ab drei aufeinanderfolgenden Nummern zu einem Bereich zusammen", () => {
    expect(compactRanges([1, 2, 3, 4, 5])).toBe("1–5");
  });

  it("mischt Aufzählung und Bereich", () => {
    expect(compactRanges([7, 1, 5, 2, 4, 6])).toBe("1, 2, 4–7");
  });

  it("lässt eine einzelne Nummer stehen", () => {
    expect(compactRanges([3])).toBe("3");
  });
});

describe("Das Zusammenlegen", () => {
  it("legt zusammen, was sich berühren würde, und nur das", () => {
    const near = MERGE_DISTANCE_PX - 1;
    const groups = groupByDistance([
      { x: 0, y: 0 }, { x: 500, y: 0 }, { x: near, y: 0 }
    ]);

    expect(groups).toEqual([[0, 2], [1]]);
  });

  it("verbindet eine Kette, auch wenn ihre Enden weit auseinander liegen", () => {
    // Three badges in a row, each touching the next: one badge, not two
    // overlapping ones.
    const step = MERGE_DISTANCE_PX - 4;
    const groups = groupByDistance([0, 1, 2].map(i => ({ x: i * step, y: 0 })));

    expect(groups).toEqual([[0, 1, 2]]);
  });

  it("trennt wieder, sobald genug Abstand ist", () => {
    const groups = groupByDistance([{ x: 0, y: 0 }, { x: MERGE_DISTANCE_PX, y: 0 }]);

    expect(groups).toEqual([[0], [1]]);
  });
});
