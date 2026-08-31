# Is there a 6 m minimum between buildings? — § 6 SächsBO and the neighbours

**Research date: 2026-08-31.** Written in English: this is developer
documentation, only the user interface is German.

> **Legend**
> ✅ **VERIFIED LIVE (2026-08-31)** — a request was made from this shell and its
> answer read.
> 📘 **FROM THE STATUTE** — quoted from the official text at revosax.sachsen.de.
> ⚠️ **NOT VERIFIED** — stated as an open question, not as a fact.

This is not legal advice, and the application says so in its own footer. What
follows is what the statute says and what can be computed from the data that is
actually available.

---

## 1. The short answer

**No. Saxony's building code contains no rule "6 m between buildings".** The
number is a *consequence*, not a norm, and it only holds when both buildings sit
at the minimum:

📘 § 6 Abs. 5 SächsBO — "Die Tiefe der Abstandsflächen beträgt 0,4 H,
mindestens 3 m."

📘 § 6 Abs. 2 SächsBO — the setback areas "müssen auf dem Grundstück selbst
liegen". They may reach onto public streets, green and water surfaces, but only
up to their centre line, and onto another plot only "wenn rechtlich gesichert
ist, dass sie nicht überbaut werden" — that is the Baulast.

📘 § 6 Abs. 3 SächsBO — "Die Abstandsflächen dürfen sich nicht überdecken",
with exceptions, among them outer walls meeting at more than 75°.

Put together: each building keeps its own setback area, on its own plot. Two
neighbouring buildings both at the 3 m floor therefore stand 3 + 3 = 6 m apart.
The moment either wall is higher than 7.5 m, 0.4 H exceeds 3 m and the pair is
further apart than 6 m — so 6 m is a lower bound for the minimal case, not a
rule to be met.

### What this means for the premise behind the marking

A neighbouring building standing closer to the shared boundary than 3 m does
**not** enlarge *our* setback. Ours is measured from *our* wall (0.4 H, at least
3 m) and has to lie on our plot; the neighbour's obligation is theirs. Their
building is either older than the rule (Bestandsschutz), covered by an
Abweichung, or sitting on a Baulast — and a Baulast is the one case that does
touch us, because it is recorded on the *encumbered* plot and can mean part of
our land may not be built on at all.

⚠️ **NOT VERIFIED**: whether Baulasten are available as a queryable dataset in
Saxony. The Baulastenverzeichnis is kept by the lower building authority and is
not part of ALKIS. It has to be asked for.

So a marking that says "you must keep this free as well" would state something
the statute does not say. What *is* true and worth showing:

> In this strip, our setback area and the neighbouring building's would
> overlap — the two buildings would end up closer than the 3 + 3 m that
> § 6 produces in the minimal case. That is a question for the building
> authority, not a computed verdict.

That is the framing the marking should carry.

---

## 2. Where would the neighbouring buildings come from?

### OSM via Overpass ✅ **VERIFIED LIVE (2026-08-31)**

```
[out:json][timeout:60];
way["building"](around:70,51.33653,12.44180);
out geom;
```

against `https://overpass-api.de/api/interpreter`, centred on Mölkau
Flurstück 204 (Lessingweg 44, the plot in
`frontend/tests/fixtures/parcel-moelkau.json`).

**21 building footprints** came back inside 70 m, with street and house number
on most of them (`Lessingweg 48`, `Lessingweg 50`, `Paunsdorfer Straße 55`, …).
Coverage in this ordinary Leipzig residential street is complete enough to work
with.

**But: not one of the 21 carried `building:levels` or `height`.** So wall
heights are not available, and 0.4 H cannot be computed for a neighbour. Only
the 3 m floor is. Every number derived from this is therefore the *most
permissive* reading — the real setback of a taller neighbouring house is
larger, never smaller.

The Overpass policy question is already settled in CLAUDE.md: the endpoint is a
configurable source, and a self-hosted instance or a local extract is the
production answer. A building query is the same shape as the POI query the
`nearby` endpoint already makes.

### The official services

- The ALKIS WFS (`ave:` product) serves `ave:Flurstueck` and
  `ave:KatasterBezirk`. ⚠️ Its capabilities document has not been read for this
  question; whether a building layer is offered is open.
- The ALKIS **WMS** in `settings.py` (`adv_alkis_siedlung`) draws buildings, but
  a WMS answers with a picture. ⚠️ Whether `GetFeatureInfo` yields usable
  geometry there is untested.

Worth one hour before shipping: an official building outline is better than an
OSM one, and the aerial backdrop already shows the neighbours anyway.

---

## 3. Proposed implementation

**Geometry.** The existing `buildableArea(ring, depths)` already takes a depth
*per boundary segment*. So:

1. Project the neighbouring outlines into the plot's local metre frame with
   `toLocal(coordinates, plot.anchor)` — the same call the parcel goes through.
2. For each boundary segment, take the smallest distance `d` from that segment
   to any neighbouring building. Segments with no building within a few tens of
   metres get nothing.
3. `hintDepth[i] = max(setback[i], 3 − d[i] + setback[i])` — the depth at which
   our wall would clear the neighbour's own 3 m. Where `d ≥ 3` this is just
   `setback[i]` and nothing is drawn.
4. Draw the ring between `buildableArea(polygon, setbacks)` and
   `buildableArea(polygon, hintDepths)`.

**Appearance.** Discreet, and unmistakably not the statutory setback strip: a
thin hatch, no fill weight, in a muted tone from `tokens.css` rather than the
`--w2b-map-setback` colour, and out of the print sheet by default.

**Wording (German, next to the drawing).** Something on the order of: this
strip marks where the neighbouring building stands closer to the boundary than
§ 6 SächsBO's minimum — the setback areas would overlap. Whether that matters
here is for the Bauaufsicht to say; the outlines come from OpenStreetMap and
carry no wall heights.

**What to leave out.**

- Any statement that something is or is not permitted.
- Any number derived from a guessed neighbour wall height.
- The marking on plots with no anchor, and on the thumbnails.
