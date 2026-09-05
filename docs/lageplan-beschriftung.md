# Labelling the site plan — where the current approach ends, and what would replace it

**Written 2026-09-02.** English, like all developer documentation; only the
interface is German.

This is a design note, not a plan of record. The current behaviour is good
enough and stays; this is written down so the reasoning is not lost, and so
that whoever picks the problem up does not start from the failure again.

## What is drawn today

`SitePlan.dimensionChains()` gives every boundary segment its own dimension
chain: two witness lines, an arrowed measure line at a **fixed offset outward
from the segment**, and the length as text at the middle of that line.

```js
const EDGE_CHAIN_PX   = 18;        // the ring every chain sits on
const SHORT_LABEL_PX  = [36, 54];  // two further rings for labels with no room
const MAX_LABELLED_EDGES = 16;     // above this, no per-edge chain at all
```

Two mechanisms keep it from collapsing:

1. **A segment too short to carry its own text keeps the label on a leader**,
   pushed out to one of two further rings, alternating between them in the
   order the crowded segments were found.
2. **Above sixteen segments nothing per-edge is drawn.** The field a district
   address resolves to has 159 of them; a chain each turned the plan into a
   black band. The overall size — the minimum rotated rectangle — still stands,
   and `Abstandsflächen` on the plot page lists every segment length anyway.

The offsets are **pixels**, deliberately. Reserving the room in metres needs a
scale, and the reservation then changes that scale; a 35 m plot ended up at a
third of its frame while the two chased each other. `trialScale` fits the
outline alone to break the circularity, and `margin` reserves the pixels once.

## Where it fails

The rings are geometry-blind. Two adjacent, nearly parallel short sides get
offset along nearly the same normal and land nearly on top of each other; the
alternation between the two leader rings avoids that **by luck**, because it
alternates in discovery order rather than by where the labels actually are. On
a parcel with a run of slivers along one boundary — which is the common shape,
not a pathological one — pairs of labels touch or overlap.

Three further weaknesses follow from the same root:

- **`LABEL_CHARACTER_PX = 6.2` is a guess at a character's width.** It decides
  which segments count as crowded. A `1 234,5 m` and a `9 m` are treated as
  proportional to their character count, which for tabular figures is roughly
  true and for the ` m` suffix and the comma is not.
- **There is no way to drop one label.** A label either fits its ring or is
  pushed further out; nothing can decide that *this* one is the least useful
  and omit it. That is exactly why `MAX_LABELLED_EDGES` has to be a blunt
  all-or-nothing cap — with no ability to drop the worst few, the only safe
  answer above sixteen segments is to drop them all.
- **The reserved margin is the worst case.** `overallOffsetPx` reserves room
  for the outermost ring that *might* be used, so one crowded sliver costs the
  whole drawing 18 px of frame whether or not the rest needed it.

## What would replace it

Real label placement: candidates, a collision test, and a choice. This is the
classic point-feature label placement problem, and at n ≤ 60 labels the greedy
form of it is both sufficient and cheap.

**1. Measure the text instead of estimating it.** SVG gives exact extents with
`getComputedTextLength()`, and a `<canvas>` 2D context's `measureText` gives
them without a mount. Either replaces `LABEL_CHARACTER_PX` with the truth and
turns "crowded" from a guess into a fact.

**2. Generate candidates per label, not one position.** For each segment, in
descending order of preference:

- on the chain at `EDGE_CHAIN_PX`, centred on the segment (what is drawn today);
- the same, slid along the segment by ±¼ and ±⅓ of its length;
- *inside* the outline, when the parcel is deep enough there to hold the box;
- on a leader at 36 px, then 54 px, at the segment's midpoint normal ±20°.

Each candidate is a rectangle in drawing coordinates: the measured text box,
inflated by a padding, rotated with the plan.

**3. Place greedily, most-constrained first.** Sort labels by how few
candidates are free — shortest segment first is a good proxy — and for each,
take the first candidate that collides with nothing already placed, with the
house footprint, with the north arrow and scale bar, or with the frame edge.
Collision against a uniform grid of the drawing keeps it linear; with ≤ 60
labels an all-pairs test is also fine and simpler to read.

**4. A label with no free candidate is dropped, not overlapped.** The plan then
says so — one line under the drawing, in German, naming how many segment
lengths are not shown and that the setback table lists all of them. Dropping is
what makes the sixteen-segment cap unnecessary: the same mechanism that solves
a 20-segment parcel solves a 159-segment one, by drawing the few labels that
have room and admitting the rest.

**5. Draw a leader only when the chosen candidate is not adjacent to its
segment.** Today every crowded label gets one; most would not need one once the
label can slide along its own chain.

**6. Reserve the margin from the placement that actually happened.** Run the
placement once against `trialScale` — which is what `crowdedEdges` already does
— take the outermost box it used, and reserve that. The circularity stays
broken, and a plan whose labels all fit on the inner ring stops paying for
rings it never used.

## What this would cost, and why it is not being done now

The placement itself is perhaps 150 lines and a test file: parcels of known
shape, asserting that no two chosen boxes intersect and that the drop count is
what it should be. The fixtures for it already exist — `parcel-many-corners`
(159 segments) is the hard case and `parcel-moelkau` (5) the easy one.

The reason to wait is that the two failures it fixes are cosmetic and rare on
the shapes this tool is actually used on: an ordinary building plot has four to
eight sides and every label fits its first candidate. The blunt cap is honest
about what it does, the overall size — the number a user is actually asking for
— is never dropped, and every individual length is in the table one panel down.
Spending the effort here before the plan is otherwise finished would be
optimising the rarest case first.

Two things would change that judgement: plots with many short sides turning out
to be common in real use, or the printed sheet becoming the primary artefact —
on paper the table is a page away, and the drawing has to stand alone.
