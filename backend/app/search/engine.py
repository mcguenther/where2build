"""The search itself: six phases, each of which may stop the run.

This is a staircase, not a pipeline. The happy case -- a cadastral district and
a parcel number, in the text or on an attached extract -- never reaches phase 2:
it resolves the parcel, checks it against everything else the listing says, and
stops. Every later phase exists only for the listings that case cannot settle.

    0  Ernten          gather Indizien, ask nothing
    1  Anker           the smallest container worth trusting -- possibly several
    2  Raum            how big is the haystack (display only, never an abort)
    3  Toleranz-Treppe hard first, widen only when a rung comes back empty
    4  Weiche Bewertung only orders, never removes
    5  Prüfen          the only phase that may say "found"
    6  Antwort         always everything, never only the result

Two departures from the drafted algorithm, both measured on 05.09.2026 and both
recorded in ``docs/research/flurstueck-identifikation.md``:

* **The short circuit verifies.** The draft jumped straight to the verdict when
  a district and a number were present. But a misread number resolves to a real
  but foreign parcel, and that is precisely the error checking against ALKIS
  does not catch -- so the short circuit now cross-checks the parcel it found
  against the other free statements (the stated area, the municipality) before
  it may say "bestätigt". It costs no extra request: both values ride along
  with the parcel.
* **A parcel number is tested against every contested district at once.** The
  draft chose one anchor and filtered inside it, which made a wrong relation
  the only route to a confidently wrong answer. Measured: 790/11 exists in
  Großbothen and in none of the three other districts the same listing names,
  so four count requests dissolve the conflict with no relation extraction, no
  model call and no question to the user.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Sequence

from ..errors import AppError, UpstreamError
from ..gemarkung_index import GemarkungDirectory, GemarkungEntry, base_name, fold
from ..schemas import (
    Entfernungsband,
    Indiz,
    Kandidat,
    KandidatProperties,
    Konflikt,
    ParcelSearchRequest,
    SuchEreignis,
    Suchgebiet,
    SuchStatus,
)
from ..services import ocr
from ..settings import AppSettings
from ..services.alkis import (
    AlkisService,
    Flurstueck,
    KatasterBezirk,
    between,
    equals,
    expand_gemarkung_key,
    like,
)
from .. import geo
from . import distance
from .distance import DistanceStatement
from .envelope import _geojson, common_envelope, next_question
from .indicia import (
    ANCHORING,
    district_matches,
    AreaStatement,
    Dimensions,
    collect_indicia,
    describes_part_area,
    federal_state,
    normalise_parcel_number,
    outside_saxony,
    read_area,
    read_dimensions,
)
from .ladder import Rung, confirmation_rung, tolerance_ladder
from .scoring import clean_use, parcel_number, score

# Above this many survivors there is nothing left to score, and the interface
# asks for the area instead of searching. The limit sits on the *candidate set
# after the hard filters*, never on the anchor: Stadt Leipzig holds 112 588
# parcels and an exact area still leaves 78 of them, a perfectly scoreable set,
# so a rule that refused large anchors was refuted by measuring it.
MAX_CANDIDATES = 500

# How many candidates are fetched with their geometry. ALKIS cannot be asked
# for attributes without geometry, and at 1.4 kB each the rest are counted
# rather than loaded.
MAX_GEOMETRY = 200

# A parcel number with no district at all is worth a single count request:
# measured, „790/11“ exists 5 times in Saxony and „85/1“ 672 times. Below this
# the set is small enough to show; above it the number alone says nothing.
MAX_STATEWIDE_BY_NUMBER = 40

# How many cadastral districts a named municipality may stand in for. Stadt
# Grimma has 66 of them; asking 66 counts to avoid one question to the user is
# the wrong trade, so above this the municipality only informs the answer.
MAX_MUNICIPALITY_DISTRICTS = 12

# How far around the platform's pin to ask which cadastral districts there are,
# when nothing in the listing named one. Measured 09.09.2026 against the pin of
# the Lobstädt advert -- the one sitting 6 235 m from the parcel actually
# offered: ±1500 m returns 8 districts and Lobstädt is among them, ±3000 m
# returns 23, ±7000 m returns 69. Around Grünau-Siedlung in Leipzig it returns
# 7, against Stadt Leipzig's 76.
#
# The trade is reliability against set size, and it is safe in one direction
# only, which is what allows a number to be chosen without a corpus: a box too
# small to contain the plot's district makes every anchor count zero and the run
# reports that it found nothing. It cannot name a wrong parcel, only no parcel.
# How many of a district's Flure are drawn. Eilenburg has 48, and a map that
# fetches all of them to shade one town is spending 240 kB on a backdrop.
MAX_FLUR_OUTLINES = 12

PIN_RADIUS_M = 1500.0

# How many districts are worth widening to their municipality when the exact
# area found nothing. Two requests each, and the second one rarely differs from
# the first -- neighbouring districts usually share a municipality.
MAX_MUNICIPALITY_PROBES = 2

# How many of a listing's images are read. Measured at roughly 0,9 s each when
# the first pass matches and ~3 s when both passes run and find nothing; a
# dozen covers every advert seen and bounds the worst case.
MAX_IMAGES = 12

# How many district outlines are drawn as the search space. Enough to show a
# genuine ambiguity, few enough that the map does not become a patchwork and
# the run does not spend a request per wash.
MAX_DRAWN_AREAS = 4

# What the short circuit accepts as agreement between the parcel it resolved
# and the area the listing states. Wider than the plausibility check's factor
# of four on purpose: this only decides whether one more phase runs.
# How far the smallest rectangle around a parcel may differ from the measures a
# listing states before the two describe different plots. Generous on purpose:
# a seller measures the frontage and the depth to the back fence, the cadastre
# records a polygon, and the rectangle around an irregular one is bigger than
# either. Measured on advert 3508042470, which states 14 x 40 m: the parcel the
# run confirmed is 21,7 x 26,7 (1,55 times too wide, caught), and the parcel in
# the district its own location field names is 17,3 x 34,1 (1,24 and 0,85,
# passed).
# How many of a listing's distance statements are resolved to an outline. Two
# ALKIS requests each -- the district boundary for a seed point, then the
# built-up area around it -- and the corpus of 16 adverts offers at most one
# resolvable reference per listing anyway: 62 statements, 8 naming a place, 3
# of those a place the cadastral directory carries.
MAX_DISTANCE_REFERENCES = 2

# How many distance statements are read at all, and how many of the
# unresolvable ones the collapsed row names before it says "and n more".
MAX_DISTANCE_STATEMENTS = 20
MAX_DISTANCE_LISTED = 4

SHAPE_TOLERANCE = 0.25

# How much bigger the rectangle around a parcel may be than the parcel itself
# before it stops describing it. A wedge of 1 489 m² sits in 2 845 m² of
# rectangle (1,91) and its stated frontage cannot be checked against that; a
# parcel of 577 m² in a 579 m² rectangle (1,004) can.
SHAPE_RECTANGULARITY = 1.3


@dataclass
class Anchor:
    """One spatial container the search may filter inside.

    Not "the most accurate point" -- the narrowest container worth trusting.
    The platform's pin is never *the* container: measured 6 235 m from the
    parcel actually offered, because the platform geocodes its own location
    field. It may still say which districts to ask, though, and that is a
    different move -- see `anchors_from_pin`, and the radius note there.
    """

    art: str
    schluessel: str
    name: str
    indiz_id: str
    confidence: float
    # The municipality this district belongs to, as the directory spells it.
    # Not decoration: it is what separates the two Gemarkungen called Plagwitz.
    gemeinde: str | None = None
    # Every key this anchor stands for. One district is often filed as several
    # Flure -- Kitzen as eleven, Eilenburg as forty-eight -- and they are one
    # place, not eleven candidates. Asking them together is one request where
    # asking them apart was eleven, and it is why a listing that names such a
    # place costs two requests instead of the thirty the pin fallback cost.
    keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.keys:
            object.__setattr__(self, "keys", (self.schluessel,))

    @property
    def condition(self) -> str:
        name = "gemaschl" if self.art == "gemarkung" else "gmdschl"
        if len(self.keys) == 1:
            return equals(name, self.keys[0])
        return "<fes:Or>" + "".join(equals(name, key) for key in self.keys) + "</fes:Or>"


@dataclass(frozen=True, slots=True)
class Reference:
    """A place a distance was measured to, resolved to everything it may mean.

    Never a point. „6 km bis Grimma" is a statement about a town, and a town
    has an edge and a middle that lie kilometres apart -- so both are kept and
    a candidate is tested against the whole interval between them. ``area`` is
    the built-up outline in UTM 33; ``centre`` its centroid.
    """

    name: str
    area: Any
    centre: Any

    def readings(self, point: Any) -> tuple[float, float]:
        """What this reference admits as "the distance" from one point.

        The near end is the distance to the built-up area itself -- zero inside
        it -- and the far end the distance to its middle. Nothing in between is
        chosen.
        """

        near = float(self.area.distance(point))
        far = float(self.centre.distance(point))
        return (near, far) if near <= far else (far, near)


@dataclass
class SearchState:
    """Everything the run has established, in the shape the answer needs."""

    indicia: list[Indiz] = field(default_factory=list)
    conflicts: list[Konflikt] = field(default_factory=list)
    candidates: list[Flurstueck] = field(default_factory=list)
    outline: KatasterBezirk | None = None
    areas: list[Suchgebiet] = field(default_factory=list)
    requests: int = 0
    status: SuchStatus = "erfolglos"
    hint: str | None = None


class SearchEngine:
    """One run. Stateful, single use, and an async generator of events."""

    def __init__(
        self,
        payload: ParcelSearchRequest,
        alkis: AlkisService,
        directory: GemarkungDirectory | None,
        app_settings: AppSettings | None = None,
    ) -> None:
        self.payload = payload
        self.alkis = alkis
        self.directory = directory
        self.app_settings = app_settings or alkis.app_settings
        self.state = SearchState()
        self._area: AreaStatement | None = None
        self._street: str | None = None
        # The sentence saying the plot is a piece of a bigger parcel, if any.
        self._part_area: str | None = None
        # The federal state the listing names, when it is not Saxony.
        self._outside: str | None = None
        # What the listing says the plot measures, where it says so.
        self._dimensions: Dimensions | None = None
        # The parcel a contradicted number resolved to. Kept, not dropped: if
        # the area route finds nothing, it is the only answer there is.
        self._refuted: list[Flurstueck] = []
        # District outlines already fetched, by key. Drawn once for the map and
        # reused for the wash under a confirmed parcel.
        self._district_outlines: dict[str, KatasterBezirk] = {}
        # The districts the platform's pin lands among. `None` until asked,
        # a list -- possibly empty -- afterwards, so it is asked exactly once.
        self._pin_anchors: list[Anchor] | None = None
        # What the listing says about distance, and the band each statement
        # admits. Read in phase 0, resolved only when there is something to
        # order -- a band never decides, so it never needs to run earlier.
        self._distances: list[tuple[Indiz, DistanceStatement]] = []
        self._references: list[tuple[DistanceStatement, Reference]] = []
        self._bands_resolved = False

    # ------------------------------------------------------------------
    # Small helpers over the Indiz list
    # ------------------------------------------------------------------

    def active(self, art: str) -> list[Indiz]:
        """Indicia of one kind the user has not switched off, strongest first."""

        chosen = self.payload.entscheidungen.get(art)
        found = [
            indiz
            for indiz in self.state.indicia
            if indiz.art == art and not indiz.verworfen
        ]
        if chosen:
            # A decision does not delete the alternatives; it reorders them, so
            # the map keeps showing what was contested.
            found.sort(key=lambda indiz: (indiz.id != chosen, -indiz.sicherheit))
        return found

    async def _count(self, conditions: Sequence[str]) -> int:
        self.state.requests += 1
        return await self.alkis.count(conditions)

    async def _search(self, conditions: Sequence[str], limit: int | None = None) -> list[Flurstueck]:
        self.state.requests += 1
        return await self.alkis.search(conditions, limit=limit)

    # ------------------------------------------------------------------
    # Phase 0 -- gather, and notice contradictions
    # ------------------------------------------------------------------

    async def harvest(self) -> AsyncIterator[SuchEreignis]:
        yield SuchEreignis(art="phase", phase="ernten", text="Angaben aus dem Inserat lesen")

        self.state.indicia = collect_indicia(
            text=self.payload.text,
            titel=self.payload.titel,
            adresse=self.payload.adresse,
            gemarkung=self.payload.gemarkung,
            flurstuecksnummer=self.payload.flurstuecksnummer,
            flaeche_m2=self.payload.flaeche_m2,
            flaeche_text=self.payload.flaeche_text,
            lat=self.payload.lat,
            lon=self.payload.lon,
            directory=self.directory,
            given=self.payload.indizien,
        )
        for indiz in self.state.indicia:
            if indiz.id in self.payload.verworfen:
                indiz.verworfen = True
                indiz.verworfen_grund = "Von Hand abgewählt."

        # A place the cadastre has never heard of cannot be searched, and
        # offering it as a choice was worse than not offering it: picking
        # „Brehna“ re-ran the search with the same anchors and produced the
        # same answer, which reads as a button that does nothing. It is said
        # once, in the protocol, with the reason.
        if self.directory:
            for indiz in self.state.indicia:
                if (
                    indiz.art == "gemarkung"
                    and not indiz.verworfen
                    and indiz.beziehung in ANCHORING
                    and not self._district_entries(indiz)
                ):
                    indiz.verworfen = True
                    indiz.verworfen_grund = (
                        "Steht nicht im sächsischen Gemarkungsverzeichnis — "
                        "als Gemarkung nicht durchsuchbar."
                    )

        # The one statement in a listing this tool can be certain it cannot
        # serve, and it costs nothing: the platform's location field names the
        # Bundesland. ALKIS is state-specific, so a plot in Sachsen-Anhalt has
        # no Saxon Flurstück — while the village it names very often has a
        # Saxon namesake holding a parcel of exactly the stated size. Searching
        # anyway does not fail, it answers, and the answer is a real parcel a
        # hundred kilometres away.
        self._outside = outside_saxony(self.payload.adresse)

        area_indiz = next((i for i in self.active("flaeche")), None)
        if area_indiz is not None:
            self._area = read_area(area_indiz.beleg or "") or AreaStatement(
                value=float(area_indiz.wert), wording=""
            )
            # A plot still to be surveyed out of a bigger parcel has no parcel
            # of its own, so its area belongs to a *future* one. Filtering on it
            # finds some other parcel of that size and confirms it — exactly the
            # confidently wrong answer this search exists to refuse.
            self._part_area = describes_part_area(
                " ".join(part for part in (self.payload.titel, self.payload.text) if part)
            )
            if self._part_area:
                self._area = replace(self._area, part_of=self._part_area)
                area_indiz.text = (
                    f"{area_indiz.text} — noch zu vermessende Teilfläche, "
                    "also die Größe eines künftigen Flurstücks"
                )
                area_indiz.beleg = self._part_area

        street_indiz = next(iter(self.active("strasse")), None)
        self._street = street_indiz.wert if street_indiz else None
        self._read_distances()
        self._dimensions = read_dimensions(
            " ".join(part for part in (self.payload.titel, self.payload.text) if part)
        )

        # The frame before the narration. The clues play out one at a time so a
        # run can be followed, and the districts used to be emitted *after* all
        # of them — so the map sat on the whole of Saxony while the list already
        # named a village, which reads as a map that is not working rather than
        # one that is waiting. Nothing new is fetched here: it is the same
        # request the space step made, one step earlier.
        async for event in self.frame():
            yield event

        for indiz in self.state.indicia:
            yield SuchEreignis(art="indiz", indiz=indiz)

        for conflict in self._conflicts():
            self.state.conflicts.append(conflict)
            yield SuchEreignis(art="konflikt", konflikt=conflict)

    # ------------------------------------------------------------------
    # Distance bands -- they order, they may object, they never confirm
    # ------------------------------------------------------------------

    def _read_distances(self) -> None:
        """Turn the distances the prose states into Indizien.

        A *named* reference gets a row of its own, because it is the only kind
        the cadastre can resolve and therefore the only kind that can order
        anything. Everything else is collapsed into one row.

        That split is measured, not tidiness. Over the 16 recorded adverts the
        prose states 62 distances and 8 of them name a place; advert 3375124391
        alone lists thirteen — „Kindergarten 2 km", „Gymnasium 6,8 km",
        „Flughafen 35 km" — and it is settled by its exact area in five
        requests. Thirteen rows that cannot contribute would push the five that
        did out of view, which is the same reason one district is one Indiz
        however often the text names it.
        """

        body = " ".join(part for part in (self.payload.titel, self.payload.text) if part)
        statements = distance.read_distances(body)
        if not statements:
            return
        counter = 0
        for statement in statements[:MAX_DISTANCE_STATEMENTS]:
            if not statement.named:
                continue
            counter += 1
            inner, outer = statement.band
            indiz = self._distance_indiz(
                f"e{counter}",
                wert=distance.kilometres(statement.meters),
                text=distance.band_sentence(statement),
                beleg=statement.beleg,
                sicherheit=0.25,
                band=Entfernungsband(
                    meter=statement.meters,
                    innen_m=inner,
                    aussen_m=outer,
                    bezug=statement.label,
                    modus=statement.mode,
                ),
            )
            self.state.indicia.append(indiz)
            self._distances.append((indiz, statement))

        rest = [s for s in statements if not s.named]
        if not rest:
            return
        listed = ", ".join(
            f"{s.label} {distance.kilometres(s.meters)}" for s in rest[:MAX_DISTANCE_LISTED]
        )
        more = "" if len(rest) <= MAX_DISTANCE_LISTED else f" und {len(rest) - MAX_DISTANCE_LISTED} weitere"
        self.state.indicia.append(
            self._distance_indiz(
                "e0",
                wert=f"{len(rest)} Angaben",
                text=(
                    f"{listed}{more}. Jede nennt eine Art von Ort statt eines bestimmten, "
                    "also gibt es nichts, wogegen sich messen ließe — sie stehen hier, "
                    "gerechnet wird mit ihnen nicht."
                ),
                beleg=rest[0].beleg,
                sicherheit=0.1,
                band=None,
            )
        )

    def _distance_indiz(
        self,
        id: str,
        *,
        wert: str,
        text: str,
        beleg: str,
        sicherheit: float,
        band: Entfernungsband | None,
    ) -> Indiz:
        indiz = Indiz(
            id=id,
            art="entfernung",
            wert=wert,
            text=text,
            beleg=beleg,
            quelle="fliesstext",
            # Weak on purpose and by rule, not by taste: a band may order the
            # list and may object, so its number is never allowed near the
            # threshold that separates „bestätigt“ from „mehrdeutig“.
            sicherheit=sicherheit,
            beziehung="entfernt_von",
            band=band,
        )
        if indiz.id in self.payload.verworfen:
            indiz.verworfen = True
            indiz.verworfen_grund = "Von Hand abgewählt."
        return indiz

    async def resolve_bands(self) -> AsyncIterator[SuchEreignis]:
        """Resolve the named references to the built-up areas they mean.

        Two requests per reference and at most ``MAX_DISTANCE_REFERENCES`` of
        them, and only once there is more than one candidate to order — a band
        cannot confirm, so on a run the cadastre already settled it would buy
        nothing at all.

        A name the directory does not carry is not resolved and not guessed.
        „Penny 500 m" and „Nahkauf 700 m" read as place names and are shops;
        the directory is what tells them from Machern, and an unresolved
        reference stays in the protocol as a statement nobody could look up.
        """

        if self._bands_resolved:
            return
        self._bands_resolved = True
        named = [
            (indiz, statement)
            for indiz, statement in self._distances
            if statement.named and not indiz.verworfen
        ]
        if not named or not self.directory:
            return

        for indiz, statement in named[:MAX_DISTANCE_REFERENCES]:
            reference = await self._resolve_reference(statement.target or "")
            if reference is None:
                indiz.text = (
                    f"{indiz.text} Der genannte Bezug „{statement.label}“ steht nicht im "
                    "Gemarkungsverzeichnis — das Band wird gezeigt und nicht gerechnet."
                )
                yield SuchEreignis(art="indiz", indiz=indiz)
                continue
            self._references.append((statement, reference))
            band = indiz.band
            if band is not None:
                indiz.band = band.model_copy(
                    update={
                        "aufgeloest": True,
                        # `_geojson` projects out of UTM 33 itself, like every
                        # other geometry that leaves this module.
                        "umriss": _geojson(reference.area),
                        "mitte": _geojson(reference.centre),
                    }
                )
            yield SuchEreignis(art="indiz", indiz=indiz)

        if self._references:
            names = ", ".join(reference.name for _, reference in self._references)
            yield SuchEreignis(
                art="phase",
                phase="bewertung",
                text=(
                    f"Die bebaute Ortslage von {names} als Bezug — der Abstand dorthin ist "
                    "kein Wert, sondern ein Bereich vom Ortsrand bis zur Ortsmitte. Das "
                    "ordnet die Kandidaten, ausschließen kann es nur nach außen."
                ),
            )

    async def _resolve_reference(self, name: str) -> Reference | None:
        """The built-up outline of a named place, or nothing.

        Seeded from the cadastral district of that name, which is *not* the
        town — Gemarkung Grimma reaches to within 1.22 km of a parcel 5.32 km
        from the town's edge, because a district is farmland too. It is only
        ever used here as a point to put the land-use box around, and the
        outline that comes back is the settlement itself.
        """

        entries = district_matches(self.directory, name) if self.directory else []
        if not entries:
            return None
        key = expand_gemarkung_key(entries[0].schluessel)
        try:
            outline = self._district_outlines.get(key)
            if outline is None or outline.geometry is None:
                self.state.requests += 1
                found = await self.alkis.district_outlines([key])
                outline = next((o for o in found if o.geometry is not None), None)
            if outline is None or outline.geometry is None:
                return None
            seed = outline.geometry.centroid
            lon, lat = geo.utm33_to_wgs84(seed.x, seed.y)
            self.state.requests += 1
            built_up = await self.alkis.built_up_area(lat, lon, largest=True)
        except AppError:
            # A band is an ornament on the answer, never the answer. An
            # upstream that cannot draw it is not a reason to end the run.
            return None
        if built_up is None:
            return None
        return Reference(
            name=entries[0].name or name,
            area=built_up.geometry,
            centre=built_up.geometry.centroid,
        )

    def _distance_fit(self, parcel: Flurstueck) -> tuple[float, str] | None:
        """How well one candidate fits every resolved distance statement, as one number.

        One feature, not one per statement. The three distances the reference
        listing states all point into the same village, so their errors are one
        error — averaging them says that, and multiplying them would count it
        three times over.
        """

        if not self._references or parcel.geometry is None:
            return None
        point = parcel.geometry.centroid
        fits: list[float] = []
        phrases: list[str] = []
        for statement, reference in self._references:
            reading = reference.readings(point)
            fits.append(distance.membership(reading, statement.band))
            phrases.append(
                f"{distance.kilometres(reading[0])}–{distance.kilometres(reading[1])} "
                f"bis {reference.name} gegen „{distance.kilometres(statement.meters)}“ "
                "im Inserat"
            )
        return sum(fits) / len(fits), "; ".join(phrases)

    def _distance_objection(self, parcel: Flurstueck) -> str | None:
        """The one thing a stated distance can prove, and only outwards.

        A route is never shorter than the straight line, so a candidate whose
        straight line already exceeds the outer bound cannot satisfy the
        statement in any reading, by any means of travel. It still deletes
        nobody — the sentence goes next to the candidate and the candidate
        sinks.
        """

        if not self._references or parcel.geometry is None:
            return None
        point = parcel.geometry.centroid
        for statement, reference in self._references:
            reading = reference.readings(point)
            if distance.refuted(reading, statement.band):
                return (
                    f"liegt {distance.kilometres(reading[0])} von {reference.name} entfernt, "
                    f"das Inserat nennt „{distance.kilometres(statement.meters)}“ — auch als "
                    "Luftlinie zu weit"
                )
        return None

    async def read_images(self) -> AsyncIterator[SuchEreignis]:
        """Read the listing's images for a cadastral reference, and stop at one.

        Reached only when the text and the metadata did not settle it, and never
        before them: a Tesseract pass costs 0,9 s when it matches and a few
        seconds when it does not, and putting that in front of the first thing
        the map can draw made every run feel broken for the sake of a channel
        most listings do not have.

        One after another, not all at once. Reading them concurrently was the
        obvious idea and it is measurably wrong: Tesseract is CPU-bound, and
        seven of it on one machine push every process past a thirty-second
        timeout -- which then looks exactly like seven pictures of a lawn.
        Sequentially each takes 0,9 s when it matches and a few seconds when it
        does not, and the loop stops at the first parcel number, so the usual
        cost is a fraction of the worst case.

        Nothing read here is a verdict. A number is an Indiz like any other and
        goes through the same cross-check, because the failure this channel can
        produce is not an empty answer but a *plausible wrong* one: at a slight
        tilt the reader once returned „Flurstück 790717", a number that would
        resolve to a real but foreign parcel.
        """

        if not ocr.available():
            yield SuchEreignis(
                art="phase",
                phase="bilder",
                text=(
                    f"{len(self.payload.bilder)} Bilder liegen vor, aber auf diesem "
                    "Server ist keine Texterkennung eingerichtet — sie werden nicht gelesen."
                ),
            )
            return

        urls = self.payload.bilder[:MAX_IMAGES]
        yield SuchEreignis(
            art="phase",
            phase="bilder",
            text=(
                f"Der Text allein hat es nicht entschieden — bis zu {len(urls)} "
                "Bilder werden gelesen"
            ),
            anzahl=len(urls),
        )

        readings: list[ocr.ImageReading] = []
        failures: list[str] = []
        for number, url in enumerate(urls, 1):
            try:
                reading = await self._read_one(url)
            except (UpstreamError, OSError) as exc:
                failures.append(getattr(exc, "message", None) or str(exc))
                continue
            if reading.failed:
                failures.append(reading.failed)
                continue
            readings.append(reading)
            if reading.parcels:
                # The question is answered. The remaining images are more
                # photographs of the same plot.
                yield SuchEreignis(
                    art="phase",
                    phase="bilder",
                    text=f"Bild {number} trägt einen Katasterauszug — die übrigen bleiben ungelesen",
                    anzahl=number,
                )
                break

        found = ocr.as_indicia([r for r in readings if r.useful])
        if found:
            # Added to the pile, not emitted here: phase 0 sends every Indiz it
            # gathered in one pass afterwards, and sending these twice would put
            # each of them in the protocol twice.
            self.state.indicia = sorted(
                [*self.state.indicia, *found], key=lambda indiz: -indiz.sicherheit
            )
            return

        # Nothing found is a different sentence from nothing read. Saying "no
        # cadastral extract attached" after every read failed would be a claim
        # about the listing that the search never checked.
        yield SuchEreignis(
            art="phase",
            phase="bilder",
            text=(
                f"{len(readings)} Bilder gelesen, kein Katasterauszug dabei — Fotos "
                "eines Grundstücks tragen keinen."
                if not failures
                else (
                    f"{len(failures)} von {len(urls)} Bildern ließen sich nicht lesen "
                    f"({failures[0]}). Was gelesen wurde, trug keine Katasterangabe."
                )
            ),
            anzahl=len(readings),
        )

    async def _read_one(self, url: str) -> "ocr.ImageReading":
        data = await ocr.fetch(url, self.app_settings)
        # Tesseract is a subprocess and Pillow is CPU work; both would block the
        # loop that is meanwhile fetching the other images.
        return await asyncio.to_thread(ocr.read_image, data, url, url)

    def _conflicts(self) -> list[Konflikt]:
        """Indicia of one kind that cannot all be true.

        The search never resolves this quietly. It follows the most trustworthy
        reading, says so, and offers the alternatives -- a map extract naming
        one district and a location field naming another can both be honest,
        because the seller may have attached the wrong extract.
        """

        questions = {
            "gemarkung": "Welche Gemarkung ist gemeint?",
            "flurstueck": "Welche Flurstücksnummer ist gemeint?",
            "flaeche": "Welche Grundstücksfläche gilt?",
        }
        out: list[Konflikt] = []
        for art, question in questions.items():
            usable = [
                indiz
                for indiz in self.active(art)
                # Only readings the search would actually act on. A place the
                # text says the plot is *away from* is evidence against itself,
                # and one it merely contains is not a reading at all -- putting
                # either up as an option would ask about something that was
                # never going to be searched. Nor is a name the cadastre does
                # not know: „Brehna“ is not a Saxon Gemarkung, so choosing it
                # re-ran the search with the same anchors and the same answer.
                if art != "gemarkung"
                or (indiz.beziehung in ANCHORING and self._district_entries(indiz))
            ]
            values = {self._conflict_key(indiz) for indiz in usable}
            if len(values) < 2:
                continue
            if art == "flurstueck" and self.named_as_a_set():
                # „Flurstück 790 sowie 706“ is not two readings of one parcel,
                # it is one plot made of two -- which this project treats as the
                # normal case, not the exception. Asking which one is meant
                # would be asking a question that is not there.
                continue
            if art == "gemarkung" and self.halves_of_one_ortsteil(usable):
                # „Stadtteil Burghausen-Rückmarsdorf“ is one statement that
                # admits two Gemarkungen, not two readings that disagree. Both
                # are searched and both survivors are in the answer, where the
                # user picks a *parcel*; asking „welche Gemarkung ist gemeint?“
                # would call the listing contradictory when nothing in it
                # contradicts.
                continue
            chosen = self.payload.entscheidungen.get(art) or usable[0].id
            out.append(
                Konflikt(
                    art=art,  # type: ignore[arg-type]
                    frage=question,
                    optionen=[indiz.id for indiz in usable],
                    gewaehlt=chosen,
                )
            )
        return out

    def halves_of_one_ortsteil(self, districts: list[Indiz]) -> bool:
        """Whether these district readings all come out of one compound name.

        A city Ortsteil is often two former villages joined with a hyphen, and
        both halves are Gemarkungen while the compound is none. The readings are
        then one statement, and the same rule applies as to several parcel
        numbers from one source: it is a set, not a dispute. „in Rückmarsdorf“
        in a title alongside „Stadtteil Burghausen-Rückmarsdorf“ in the prose is
        still that one statement, which is why the compound is carried on the
        surviving reading rather than only on the derived one.
        """

        compounds = {indiz.teil_von for indiz in districts}
        return len(compounds) == 1 and None not in compounds

    def named_as_a_set(self) -> bool:
        """Whether the parcel numbers were listed together rather than in dispute.

        A plot is a set of parcels -- the normal case. Numbers that all come
        from *one* source are that set; numbers from different sources (an
        image against the body text) are rival readings, and only those are a
        contradiction worth putting to the user.
        """

        numbers = self.active("flurstueck")
        return len(numbers) > 1 and len({indiz.quelle for indiz in numbers}) == 1

    @staticmethod
    def _conflict_key(indiz: Indiz) -> str:
        return (indiz.schluessel or fold(indiz.wert)).strip()

    # ------------------------------------------------------------------
    # Phase 1 -- anchors, and the short circuit
    # ------------------------------------------------------------------

    def anchors(self) -> list[Anchor]:
        """Every container worth filtering inside, most trustworthy first.

        Several on purpose, and that is the departure from the drafted
        algorithm. Choosing one anchor makes a misread relation the single route
        to a confidently wrong answer; asking all of them costs one count
        request each and lets the cadastre decide. Measured on the reference
        listing: with an exact area, Großbothen returns 1 and every other place
        the text names returns 0.

        A name that is not unique in the directory contributes *all* of its
        districts -- two Höfgen are two questions, not a reason to drop the
        name -- and an explicit choice by the user replaces the lot.
        """

        # Only a place the text actually *places* the plot in. German
        # capitalises every noun, so a bare directory match finds „Wiesen“ in
        # „geprägt von Wiesen und Feldern“ — a real Gemarkung name and an
        # entirely accidental one. A mention without a positional relation
        # stays in the protocol as weak evidence and is never searched.
        active = [i for i in self.active("gemarkung") if i.beziehung in ANCHORING]
        chosen_id = self.payload.entscheidungen.get("gemarkung")
        if chosen_id:
            # A person who picked one has settled it; searching the rejected
            # readings anyway would be ignoring the answer we asked for.
            decided = [indiz for indiz in active if indiz.id == chosen_id]
            active = decided or active

        out: list[Anchor] = []
        for indiz in active:
            out.extend(
                _group_into_anchors(self._district_entries(indiz), indiz, indiz.sicherheit)
            )
        out = _without_repeats(out)
        return (
            self._filter_by_municipality(out)
            or self._municipality_anchors()
            or list(self._pin_anchors or [])
        )

    def _filter_by_municipality(self, anchors: list[Anchor]) -> list[Anchor]:
        """Drop the districts that belong to a municipality the listing does not name.

        „Anbindung an Leipzig“ put Gemarkung Leipzig up as an anchor next to
        Lobstädt, and Leipzig holds two parcels of exactly the stated size. The
        location field says Neukieritzsch, which is Lobstädt's municipality and
        not Leipzig's -- and that removes both without touching the area.

        Kept as a *filter with a fallback*, never a hard rule: a municipality
        read out of a location field is a strong hint (it was right on all four
        listings measured) but it is not an official fact about this plot, so
        when nothing matches it the whole set stands.
        """

        if len(anchors) < 2:
            return anchors
        for needle in self.municipalities():
            kept = [a for a in anchors if a.gemeinde and needle in fold(a.gemeinde)]
            if kept:
                return kept
        return anchors

    def _municipality_anchors(self) -> list[Anchor]:
        """Fall back to the districts of a named municipality.

        „Großbothen, einem OT von Grimma“ names the level above the one being
        searched. It is a real container and worth using -- but only when no
        cadastral district is known, and only while it stays small: Stadt Grimma
        holds 66 Gemarkungen, and 66 count requests to save one question is the
        wrong trade.
        """

        if not self.directory:
            return []
        out: list[Anchor] = []
        for indiz in self.active("gemeinde"):
            needle = fold(indiz.wert)
            districts = [
                entry
                for entry in self.directory.entries
                if entry.gemeinde and needle in fold(entry.gemeinde)
            ]
            # Counted as places, not as entries. Gemeinde Krostitz is fourteen
            # directory rows and six districts, and refusing it for having
            # fourteen while the pin then offers the same fourteen was the
            # wrong way round -- measured on advert 3495973954.
            grouped = _group_into_anchors(districts, indiz, indiz.sicherheit * 0.6)
            if not grouped or len(grouped) > MAX_MUNICIPALITY_DISTRICTS:
                continue
            out.extend(grouped)
        return _without_repeats(out)

    def _district_entries(self, indiz: Indiz) -> list[GemarkungEntry]:
        """Every cadastral district this Indiz could mean.

        5 339 districts share 4 880 names, so a name is not a key. All of the
        matches are kept -- each costs one count request, and dropping an
        ambiguous name would throw away the very case this search is for --
        *unless* the listing also names a municipality. Then the directory
        answers the question outright: there are two Gemarkungen called
        Plagwitz, one in Machern and one in Leipzig, and „Ortsteil Plagwitz von
        Machern“ leaves exactly one.
        """

        given = indiz.schluessel or (indiz.wert.strip() if indiz.wert.strip().isdigit() else None)
        if given:
            key = expand_gemarkung_key(given)
            known = [e for e in (self.directory.entries if self.directory else []) if e.schluessel == key]
            return known or [GemarkungEntry(name=indiz.wert, schluessel=key)]
        if not self.directory:
            return []
        # Through the same reader the Indizien came from, so a place filed only
        # as „<name> Flur n" resolves here exactly as it did there.
        entries = district_matches(self.directory, indiz.wert)
        return self._within_municipality(entries) or entries

    def municipalities(self) -> list[str]:
        """The municipalities the listing names, folded, strongest first."""

        return [fold(indiz.wert) for indiz in self.active("gemeinde")]

    def _within_municipality(self, entries: list[GemarkungEntry]) -> list[GemarkungEntry]:
        """The entries whose municipality the listing also names.

        Empty when nothing matches -- the caller then keeps all of them rather
        than searching nowhere, because a municipality read out of a location
        field is a hint, not an official fact.
        """

        if len(entries) < 2:
            return entries
        for needle in self.municipalities():
            kept = [
                entry
                for entry in entries
                if entry.gemeinde and needle in fold(entry.gemeinde)
            ]
            if kept:
                return kept
        return []

    async def short_circuit(self) -> AsyncIterator[SuchEreignis]:
        """District plus number: resolve it, check it, and stop.

        The check is the point. It costs nothing -- the official area and the
        municipality arrive with the parcel -- and it is the only thing standing
        between a misread digit and an answer that looks exactly as official as
        the right one.
        """

        numbers = self.active("flurstueck")
        anchors = self.anchors()
        if not numbers or not anchors:
            return

        yield SuchEreignis(
            art="phase",
            phase="kurzschluss",
            text=_combinations_sentence(len(numbers), len(anchors)),
        )

        hits: list[tuple[Anchor, Indiz, Flurstueck]] = []
        for number in numbers:
            parsed = normalise_parcel_number(number.wert)
            if not parsed:
                number.verworfen = True
                number.verworfen_grund = (
                    "Keine gültige Flurstücksnummer — der Zähler hat mehr als fünf "
                    "Stellen. Wahrscheinlich ein Lesefehler."
                )
                yield SuchEreignis(art="indiz", indiz=number)
                continue
            zaehler, nenner = parsed
            for anchor in anchors:
                conditions = [anchor.condition, equals("flstnrzae", zaehler)]
                if nenner:
                    conditions.append(equals("flstnrnen", nenner))
                found = await self._search(conditions, limit=MAX_GEOMETRY)
                for parcel in found:
                    hits.append((anchor, number, parcel))

        if not hits:
            return

        # A number that exists in exactly one of the contested districts has
        # settled the contest itself: no relation extraction, no model, no
        # question to the user.
        districts = {parcel.attributes.get("gemaschl") for _, _, parcel in hits}
        for conflict in self.state.conflicts:
            if conflict.art == "gemarkung" and len(districts) == 1:
                winner = next(a for a, _, _ in hits)
                conflict.gewaehlt = winner.indiz_id
                conflict.aufgeloest_durch = (
                    f"Die Flurstücksnummer gibt es nur in der Gemarkung {winner.name}."
                )
                yield SuchEreignis(art="konflikt", konflikt=conflict)

        self.state.candidates = [parcel for _, _, parcel in hits]

        # „604" without a denominator also finds 604/1 to 604/c. The exact area
        # settles that without a request -- ``flaeche`` came back with each
        # parcel -- and it is a hard filter, so it may decide.
        narrowed = self._narrow_by_area(self.state.candidates)
        if narrowed is not None:
            yield SuchEreignis(
                art="phase",
                phase="kurzschluss",
                text=(
                    f"Die Nummer trifft {len(self.state.candidates)} Flurstücke; mit der "
                    f"exakten Fläche bleibt {'davon eines' if len(narrowed) == 1 else f'{len(narrowed)} davon'} übrig"
                ),
                anzahl=len(narrowed),
            )
            self.state.candidates = narrowed

        yield SuchEreignis(
            art="kandidaten",
            anzahl=len(self.state.candidates),
            kandidaten=self.to_candidates(self.state.candidates),
        )

    def _narrow_by_area(self, parcels: list[Flurstueck]) -> list[Flurstueck] | None:
        """Keep only the parcels whose official area is the one the listing gives.

        ``None`` when there is nothing to narrow with, or when narrowing would
        empty the set -- a filter that deletes everything has refuted itself,
        not the candidates.
        """

        if len(parcels) < 2 or self._area is None or not self._area.exact:
            return None
        if self.named_as_a_set():
            # Their areas are meant to add up, not to match one by one.
            return None
        kept = [p for p in parcels if p.flaeche_amtlich_m2 == self._area.value]
        return kept or None

    def cross_check(self) -> str | None:
        """What contradicts the parcel the short circuit found, if anything.

        Only free comparisons: the official area against the one the listing
        states, and the municipality against the platform's location field.
        Both ride along with the parcel, so this is a rule, not a request.
        """

        if len(self.state.candidates) != 1:
            return None
        parcel = self.state.candidates[0]
        official = parcel.flaeche_amtlich_m2

        # Not for a part-area: a plot to be surveyed out of a bigger parcel is
        # *expected* to be smaller than it, so the mismatch is the situation
        # rather than an objection to it. `_part_area_note` says what is going
        # on; repeating it as „bitte die Nummer prüfen“ would send someone
        # looking for a mistake that is not there.
        if self._area_contradicts(parcel):
            return (
                f"Das gefundene Flurstück misst amtlich {official:g} m², das Inserat "
                f"nennt {self._area.value:g} m². Nummer und Fläche widersprechen "
                "sich — bitte die Flurstücksnummer prüfen."
            )

        shape = self._shape_objection(parcel)
        if shape:
            return shape

        place = next(iter(self.active("ort")), None)
        municipality = (parcel.attributes.get("gemeinde") or "").strip()
        if place and municipality:
            haystack = fold(place.wert)
            if fold(municipality) not in haystack and not any(
                fold(word) in haystack
                for word in municipality.replace("Stadt ", "").split()
                if len(word) > 3
            ):
                return (
                    f"Das Flurstück liegt in {municipality}, das Standortfeld der Anzeige "
                    f"nennt „{place.wert}“. Das muss kein Fehler sein — die Plattform "
                    "geokodiert ihr eigenes Ortsfeld —, ist aber ungeprüft."
                )
        return None

    def _area_contradicts(self, parcel: Flurstueck) -> bool:
        """Whether the parcel's official area is outside anything the wording allows.

        The threshold used to be a factor of two, which let 700 m² pass for a
        stated 502 -- 39 % out and confirmed. It comes from the tolerance
        staircase now: the widest rung the listing's own wording justifies is
        as far as an official area may be from the stated one, which is 5 % for
        a figure written exactly and 10 % for a rounded one.

        Never for a part-area: a plot to be surveyed out of a bigger parcel is
        *expected* to be smaller than it.
        """

        official = parcel.flaeche_amtlich_m2
        if self._area is None or not official or self._part_area:
            return False
        rungs = tolerance_ladder(self._area)
        if not rungs:
            return False
        widest = rungs[-1]
        return not (widest.lower <= official <= widest.upper)

    def _shape_objection(self, parcel: Flurstueck) -> str | None:
        """Whether the parcel is shaped like the plot the listing describes.

        „Bestätigt" has to mean that nothing contradicts, not merely that the
        hard filters left one candidate -- and this is the contradiction the
        area cannot see: two parcels of 577 m² can be 14 by 40 metres and 22 by
        27, and only one of them is the plot with the 14 m frontage.

        It objects; it never removes. The smallest rectangle around a polygon
        is not what a seller measured, so the tolerance is wide and the
        sentence says what was compared.
        """

        stated = self._dimensions
        geometry = getattr(parcel, "geometry", None)
        if stated is None or geometry is None or geometry.is_empty:
            return None
        try:
            corners = list(geometry.minimum_rotated_rectangle.exterior.coords)[:4]
        except (AttributeError, IndexError, ValueError):
            return None
        if len(corners) < 4:
            return None
        edges = sorted(
            ((corners[i][0] - corners[(i + 1) % 4][0]) ** 2
             + (corners[i][1] - corners[(i + 1) % 4][1]) ** 2) ** 0.5
            for i in range(4)
        )
        short, long = edges[0], edges[3]
        if short < 1:
            return None

        def apart(one: float, other: float) -> bool:
            return abs(one - other) / other > SHAPE_TOLERANCE

        sides = stated.sides
        if sides is None:
            # A frontage on its own says nothing here, and measuring showed why:
            # advert 3375124391 states „Frontbreite ca. 26 m" and its parcel
            # (1 489 m², correct) sits in a 39,8 x 71,5 m rectangle, because the
            # plot is a wedge. The width may rank one day; it may not object.
            return None
        if geometry.area and short * long > geometry.area * SHAPE_RECTANGULARITY:
            # The rectangle around a wedge says more about the wedge than about
            # the plot, so it is not evidence either way. Measured: 1 489 m² in
            # a 2 845 m² rectangle is 1,91 -- refused; 577 m² in 579 m² is
            # 1,004, and that is the case this check is for.
            return None
        if not (apart(short, sides[0]) or apart(long, sides[1])):
            return None
        return (
            f"Das Inserat nennt {sides[0]:g} × {sides[1]:g} m; das gefundene Flurstück "
            f"passt in ein Rechteck von {short:.0f} × {long:.0f} m. Fläche und Nummer "
            "stimmen, die Form nicht — das kann an einem anderen Zuschnitt liegen oder "
            "daran, dass es das falsche Flurstück ist."
        )

    # ------------------------------------------------------------------
    # Phases 2 and 3 -- the haystack, then the staircase
    # ------------------------------------------------------------------

    async def frame(self) -> AsyncIterator[SuchEreignis]:
        """The districts in play, drawn before anything else is said.

        Answers „where could this be at all“ from the first seconds. Costs one
        request per district (16,5 kB, measured) and at most `MAX_DRAWN_AREAS`
        of them, which is the same budget the space step always had.
        """

        # Nothing to frame outside Saxony: the districts an anchor would name
        # there are namesakes, and drawing one puts the map on a village the
        # plot has nothing to do with.
        anchors = [] if self._outside else self.anchors()
        if not anchors or self.state.areas:
            return
        self.state.areas = await self._outlines(anchors[:MAX_DRAWN_AREAS], [])
        if self.state.areas:
            yield SuchEreignis(art="gebiete", phase="ernten", gebiete=self.state.areas)

    async def measure_space(self, anchors: list[Anchor]) -> AsyncIterator[SuchEreignis]:
        counts = await asyncio.gather(
            *(self._count([anchor.condition]) for anchor in anchors),
            return_exceptions=True,
        )
        usable = [c for c in counts if isinstance(c, int)]
        if not usable:
            return
        largest = max(usable)

        # The search space, drawn. Sent before any candidate exists so the map
        # can answer "where could this be" from the first seconds instead of
        # sitting on the whole of Saxony until the staircase is finished.
        # 16.5 kB per district, measured, and capped -- a wash nobody can tell
        # apart from its neighbours is not worth a request.
        # Already drawn by `frame`, in phase 0. Re-fetched only if that found
        # nothing to draw — a run reached through a different route.
        if not self.state.areas:
            self.state.areas = await self._outlines(anchors[:MAX_DRAWN_AREAS], counts)
            if self.state.areas:
                yield SuchEreignis(art="gebiete", phase="raum", gebiete=self.state.areas)
        yield SuchEreignis(
            art="phase",
            phase="raum",
            text=(
                f"{_thousands(largest)} Flurstücke hat die größte der "
                f"{len(anchors)} Gemarkungen, die in Frage kommen"
                if len(anchors) > 1
                else f"{_thousands(largest)} Flurstücke hat diese Gemarkung"
            ),
            anzahl=largest,
        )

    async def staircase(self, anchors: list[Anchor]) -> AsyncIterator[SuchEreignis]:
        """Tightest band first, one rung wider only when nothing came back."""

        rungs = tolerance_ladder(self._area)
        if not rungs:
            async for event in self._without_area(anchors):
                yield event
            return

        yield SuchEreignis(
            art="phase",
            phase="treppe",
            text=f"Toleranz-Treppe: {len(rungs)} Stufen, engste zuerst",
        )

        for index, rung in enumerate(rungs):
            counts = await asyncio.gather(
                *(self._count([a.condition, between("flaeche", rung.lower, rung.upper)])
                  for a in anchors)
            )
            total = sum(counts)
            yield SuchEreignis(
                art="phase",
                phase="treppe",
                text=f"Stufe {rung.label} ({rung.text}): {total} Treffer",
                anzahl=total,
            )
            if total == 0:
                # Before opening the tolerance, open the *place*. An exactly
                # written area is an official fact; a Gemarkung read out of
                # prose is not, and widening the number to keep the guess
                # throws away the better of the two. Measured on a real
                # listing: „1.076 m² in Bad Lausick" has no match in Gemarkung
                # Bad Lausick and exactly one in the municipality — Flurstück
                # 502/47 in Gemarkung Etzoldshain, at „Am Kurpark", which is
                # what the advert is titled after.
                if rung.hard:
                    async for event in self._widen_the_place(anchors, rung):
                        yield event
                    if self.state.candidates:
                        return
                continue
            if total > MAX_CANDIDATES:
                self.state.hint = (
                    f"Schon bei Stufe {rung.label} bleiben {total} Flurstücke übrig — "
                    "das lässt sich nicht mehr bewerten. Eine genauere Flächenangabe "
                    "oder die Gemarkung würde hier am meisten helfen."
                )
                return

            survivors = [a for a, c in zip(anchors, counts) if c]
            found: list[Flurstueck] = []
            for anchor in survivors:
                found.extend(
                    await self._search(
                        [anchor.condition, between("flaeche", rung.lower, rung.upper)],
                        limit=MAX_GEOMETRY,
                    )
                )
            self.state.candidates = found
            for settled in self._settle_district_conflict(survivors):
                yield SuchEreignis(art="konflikt", konflikt=settled)
            yield SuchEreignis(
                art="kandidaten",
                anzahl=len(found),
                kandidaten=self.to_candidates(found),
            )

            async for event in self._confirm(rungs, index, survivors, found):
                yield event
            return

        self.state.hint = (
            "Keine Stufe der Toleranz-Treppe hat etwas geliefert. Die Flächenangabe "
            "aus dem Inserat passt zu keinem Flurstück im vermuteten Gebiet — "
            "möglicherweise stimmt die Gemarkung nicht."
        )

    async def _outlines(
        self, anchors: list[Anchor], counts: list[Any]
    ) -> list[Suchgebiet]:
        """District boundaries for the anchors, as far as they can be had.

        A missing outline is a paler map, never a failed search, so each one is
        allowed to fail on its own.
        """

        self.state.requests += len(anchors)
        results = await asyncio.gather(
            *(self.alkis.district_outlines(anchor.keys[:MAX_FLUR_OUTLINES]) for anchor in anchors),
            return_exceptions=True,
        )
        # Padded rather than zipped short: `frame` has no counts yet, and a
        # bare zip would silently return no outlines at all.
        padded = list(counts) + [None] * (len(anchors) - len(counts))
        out: list[Suchgebiet] = []
        for anchor, count, outlines in zip(anchors, padded, results):
            if isinstance(outlines, BaseException) or not outlines:
                continue
            for outline in outlines:
                # Kept whole, not just as GeoJSON: the wash under a confirmed
                # parcel is this same document, and the common envelope needs
                # its geometry.
                self._district_outlines[outline.schluessel or anchor.schluessel] = outline
            # One place, one area on the map: the Flure of a district are drawn
            # as themselves, because a union of eleven of them is a shape the
            # cadastre never records and nobody can look up.
            for outline in outlines:
                out.append(
                    Suchgebiet(
                        schluessel=outline.schluessel or anchor.schluessel,
                        name=anchor.name if len(outlines) > 1 else (outline.name or anchor.name),
                        anzahl=count if isinstance(count, int) and len(outlines) == 1 else None,
                        geometry=_geojson(outline.geometry),
                    )
                )
        return out

    async def _widen_the_place(
        self, anchors: list[Anchor], rung: Rung
    ) -> AsyncIterator[SuchEreignis]:
        """Try the exact area across the whole municipality.

        Costs one request to learn the municipality key -- it rides on any
        parcel of the district -- plus one count. Only ever tried for a rung
        that is a hard filter, so a hit here is as official as one inside the
        named district; what was widened is the guess, not the fact.
        """

        for anchor in anchors[:MAX_MUNICIPALITY_PROBES]:
            sample = await self._search([anchor.condition], limit=1)
            key = sample[0].attributes.get("gmdschl") if sample else None
            if not key:
                continue
            municipality = Anchor(
                art="gemeinde",
                schluessel=key,
                name=sample[0].attributes.get("gemeinde") or anchor.gemeinde or key,
                indiz_id=anchor.indiz_id,
                confidence=anchor.confidence * 0.8,
            )
            conditions = [
                municipality.condition,
                between("flaeche", rung.lower, rung.upper),
            ]
            total = await self._count(conditions)
            yield SuchEreignis(
                art="phase",
                phase="gemeinde",
                text=(
                    f"In der Gemarkung {anchor.name} gibt es kein Flurstück dieser Größe. "
                    f"In der ganzen Gemeinde {municipality.name}: {total}"
                ),
                anzahl=total,
            )
            if 0 < total <= MAX_GEOMETRY:
                self.state.candidates = await self._search(conditions, limit=MAX_GEOMETRY)
                self.state.hint = (
                    f"Gesucht wurde in der ganzen Gemeinde {municipality.name}: in der "
                    f"Gemarkung {anchor.name}, die das Inserat nennt, gibt es kein "
                    "Flurstück dieser Größe. Die Fläche ist die verlässlichere der "
                    "beiden Angaben."
                )
                yield SuchEreignis(
                    art="kandidaten",
                    anzahl=len(self.state.candidates),
                    kandidaten=self.to_candidates(self.state.candidates),
                )
                return

    def _settle_district_conflict(self, survivors: list[Anchor]) -> list[Konflikt]:
        """One anchor left standing settles a contested district by itself.

        Returns what changed, so the interface can stop showing a question the
        cadastre has already answered.
        """

        if len(survivors) != 1:
            return []
        settled: list[Konflikt] = []
        for conflict in self.state.conflicts:
            if conflict.art == "gemarkung" and not conflict.aufgeloest_durch:
                conflict.gewaehlt = survivors[0].indiz_id
                conflict.aufgeloest_durch = (
                    f"Nur in der Gemarkung {survivors[0].name} gibt es ein Flurstück "
                    "dieser Größe."
                )
                settled.append(conflict)
        return settled

    async def _confirm(
        self,
        rungs: list[Rung],
        stopped_at: int,
        anchors: list[Anchor],
        found: list[Flurstueck],
    ) -> AsyncIterator[SuchEreignis]:
        """One rung wider, to see whether the halt was a coincidence.

        When the stopping rung is a hard filter -- an exactly stated area at
        zero tolerance -- the extra candidates fail that filter by definition
        and cannot overturn the hit. They are shown all the same, as other
        parcels of a similar size nearby, and never as an objection.
        """

        wider = confirmation_rung(rungs, stopped_at)
        if wider is None or len(found) > 20:
            return
        extra: list[Flurstueck] = []
        for anchor in anchors:
            extra.extend(
                await self._search(
                    [anchor.condition, between("flaeche", wider.lower, wider.upper)],
                    limit=MAX_GEOMETRY,
                )
            )
        known = {p.attributes.get("flstkennz") for p in found}
        neighbours = [p for p in extra if p.attributes.get("flstkennz") not in known]
        if not neighbours:
            return
        hard = rungs[stopped_at].hard
        yield SuchEreignis(
            art="phase",
            phase="gegenprobe",
            text=(
                f"Gegenprobe eine Stufe weiter ({wider.text}): {len(neighbours)} weitere "
                + (
                    "Flurstücke ähnlicher Größe. Sie erfüllen die exakte Flächenangabe "
                    "nicht und können den Treffer nicht kippen."
                    if hard
                    else "Flurstücke kommen in Frage — die Fläche ist gerundet angegeben, "
                    "also entscheidet sie hier nicht."
                )
            ),
            anzahl=len(neighbours),
        )
        if not hard:
            # A rounded area is no hard filter, so the neighbours are genuine
            # rivals and join the set rather than standing beside it.
            self.state.candidates = found + neighbours
            yield SuchEreignis(
                art="kandidaten",
                anzahl=len(self.state.candidates),
                kandidaten=self.to_candidates(self.state.candidates),
            )

    async def _without_area(self, anchors: list[Anchor]) -> AsyncIterator[SuchEreignis]:
        """No usable area: the land use is all that is left to narrow with.

        It only ranks, so this is a way of getting a scoreable set out of a
        district, not a filter. A district with more parcels than can be scored
        is where the interface asks for the area instead of searching on.
        """

        yield SuchEreignis(
            art="phase",
            phase="treppe",
            text="Keine brauchbare Flächenangabe — es bleibt die Gemarkung",
        )
        for anchor in anchors:
            total = await self._count([anchor.condition, like("tntxt", "*Wohnbau*")])
            if 0 < total <= MAX_CANDIDATES:
                self.state.candidates = await self._search(
                    [anchor.condition, like("tntxt", "*Wohnbau*")], limit=MAX_GEOMETRY
                )
                yield SuchEreignis(
                    art="kandidaten",
                    anzahl=len(self.state.candidates),
                    kandidaten=self.to_candidates(self.state.candidates),
                )
                return
        self.state.hint = (
            "Ohne Flächenangabe bleibt das Gebiet zu groß, um einzelne Flurstücke "
            "zu bewerten. Die Fläche aus dem Inserat ist die wirksamste einzelne "
            "Angabe — gemessen: sie führt von 1 131 auf 1."
        )

    async def by_number_alone(self) -> AsyncIterator[SuchEreignis]:
        """A parcel number with no district at all.

        Worth exactly one count request: measured, „790/11“ exists five times in
        Saxony and „85/1“ 672 times. Small enough and the set is an answer;
        larger and the number says nothing on its own and is left alone.
        """

        numbers = self.active("flurstueck")
        if not numbers or self.state.candidates:
            return
        parsed = normalise_parcel_number(numbers[0].wert)
        if not parsed or not parsed[1]:
            return
        zaehler, nenner = parsed
        conditions = [equals("flstnrzae", zaehler), equals("flstnrnen", nenner)]
        total = await self._count(conditions)
        yield SuchEreignis(
            art="phase",
            phase="nummer-sachsenweit",
            text=(
                f"Die Nummer {numbers[0].wert} kommt in ganz Sachsen {total}-mal vor"
                + ("" if total <= MAX_STATEWIDE_BY_NUMBER else " — zu häufig, um allein zu tragen")
            ),
            anzahl=total,
        )
        if 0 < total <= MAX_STATEWIDE_BY_NUMBER:
            self.state.candidates = await self._search(conditions, limit=MAX_GEOMETRY)
            yield SuchEreignis(
                art="kandidaten",
                anzahl=len(self.state.candidates),
                kandidaten=self.to_candidates(self.state.candidates),
            )

    # ------------------------------------------------------------------
    # Phases 5 and 6 -- verdict and answer
    # ------------------------------------------------------------------

    def to_candidates(self, parcels: Sequence[Flurstueck]) -> list[Kandidat]:
        """Candidates in the shape the map draws, ordered by points.

        The points order and nothing else -- which is why they may be
        uncalibrated. What decides is in ``verdict``.
        """

        out: list[Kandidat] = []
        for parcel in parcels:
            points, reasons = score(
                parcel,
                stated_area=self._area.value if self._area else None,
                street=self._street,
                distance_fit=self._distance_fit(parcel),
            )
            objection = self._distance_objection(parcel)
            if objection:
                reasons = [*reasons, objection]
            out.append(
                Kandidat(
                    id=parcel.attributes.get("flstkennz") or parcel.gml_id or "",
                    geometry=_geojson(parcel.geometry),
                    properties=KandidatProperties(
                        kennzeichen=parcel.attributes.get("flstkennz"),
                        gemarkung=parcel.attributes.get("gemarkung"),
                        gemarkungsnummer=parcel.attributes.get("gemaschl"),
                        flurstuecksnummer=parcel_number(parcel),
                        flaeche_amtlich_m2=parcel.flaeche_amtlich_m2,
                        lagebezeichnung=parcel.attributes.get("lagebeztxt"),
                        gemeinde=parcel.attributes.get("gemeinde"),
                        nutzung=clean_use(parcel.attributes.get("tntxt")),
                    ),
                    punkte=points,
                    begruendung=reasons,
                )
            )
        out.sort(key=lambda candidate: -candidate.punkte)
        return out

    def verdict(self) -> SuchStatus:
        """The only place that may say "found".

        "bestätigt" means the hard filters left exactly one candidate and
        nothing contradicted it. There is no lead threshold and no weight in
        this decision: a run that always produces an answer eventually produces
        a wrong one.
        """

        if not self.state.candidates:
            return "erfolglos"
        if len(self.state.candidates) > 1:
            return "mehrdeutig"
        if self.cross_check():
            return "mehrdeutig"
        # A plot still to be surveyed out of a bigger parcel is not that parcel.
        # „Bestätigt“ would be a claim about a Flurstück that does not exist
        # yet, and the listing itself is what says so — the strongest possible
        # contradiction, and the one no filter can catch.
        if self._part_area:
            return "mehrdeutig"
        # A single candidate reached through a chosen tolerance is not a fact.
        # It is confirmed only when an official statement -- a parcel number or
        # an exactly stated area -- is what left it standing.
        hard = bool(self.active("flurstueck")) or bool(self._area and self._area.exact)
        return "bestaetigt" if hard else "mehrdeutig"

    def _set_note(self) -> str | None:
        """What to say when the listing named several parcels at once."""

        if not self.named_as_a_set() or len(self.state.candidates) < 2:
            return None
        total = sum(p.flaeche_amtlich_m2 or 0.0 for p in self.state.candidates)
        numbers = ", ".join(parcel_number(p) for p in self.state.candidates)
        matches = (
            self._area is not None
            and abs(total - self._area.value) <= max(2.0, self._area.value * 0.01)
        )
        return (
            f"Das Inserat nennt mehrere Flurstücke ({numbers}) — ein Grundstück besteht oft "
            f"aus mehreren. Zusammen messen sie {total:g} m²"
            + (
                f", und das passt zu den {self._area.value:g} m² aus dem Inserat."
                if matches
                else (
                    f"; das Inserat nennt {self._area.value:g} m². Bitte prüfen, ob wirklich "
                    "alle dazugehören."
                    if self._area is not None
                    else "."
                )
            )
        )

    def _part_area_note(self) -> str | None:
        """Said out loud, because it changes what an answer can mean.

        A plot still to be surveyed out of a bigger parcel has no Flurstück of
        its own, so no parcel *can* be the answer — the useful answer is the
        parcel it will be cut from. Leaving that unsaid would make an
        „mehrdeutig“ look like a weak run rather than the right verdict.
        """

        if not self._part_area:
            return None
        return (
            "Das Inserat beschreibt eine noch zu vermessende Teilfläche: "
            f"„{self._part_area}“. Ein eigenes Flurstück gibt es dafür noch nicht, "
            "und die genannte Fläche ist die eines künftigen — sie kann deshalb "
            "nicht filtern, sondern nur ordnen. Gesucht wird das Flurstück, aus "
            "dem herausgemessen wird."
        )

    async def fetch_outline(self) -> None:
        """The district wash under the candidates, when one district is settled.

        The committed directory drops the geometry on purpose, so this is one
        extra request -- 16.5 kB, measured -- and only when it can be drawn.
        """

        keys = {p.attributes.get("gemaschl") for p in self.state.candidates}
        if len(keys) != 1:
            return
        key = keys.pop()
        if not key:
            return
        # `frame` drew the districts in play before anything was narrated, so
        # the one the answer settled on is usually already in hand. Asking for
        # it again would be a second request for a document we have.
        already = self._district_outlines.get(key)
        if already is not None:
            self.state.outline = already
            return
        try:
            self.state.requests += 1
            self.state.outline = await self.alkis.district_outline(key)
        except UpstreamError:
            # A missing wash is a paler map, not a failed search.
            self.state.outline = None

    async def anchors_from_pin(self) -> AsyncIterator[SuchEreignis]:
        """Ask the cadastre which districts the advert's own pin lands among.

        The last way in, and it exists because a *Stadtteil* is usually not a
        Gemarkung. „Grünau-Siedlung" in Leipzig is none — the two Saxon
        Gemarkungen called „Grünau" are 80 km away in the Erzgebirge — so the
        name cannot be looked up, and Stadt Leipzig's 76 districts are too many
        to ask one by one. One BBOX request answers it instead: 7 districts, and
        with the listing's exact 742 m² they leave 3 candidates where the
        municipality alone leaves 24.

        The pin is not trusted as a location here, and it does not have to be.
        It is used to pick a *set* the cadastre then decides between, with the
        area as the hard filter — and if the plot's district is not in the set,
        every count is zero and the run says it found nothing. That is why this
        may run on a point measured 6 235 m off: it cannot turn a bad pin into a
        wrong parcel, only into no parcel. See `PIN_RADIUS_M`.

        Runs only when nothing better named a container, and only once.
        """

        if self._pin_anchors is not None or self._outside:
            return
        if self.anchors():
            return
        pin = next((indiz for indiz in self.active("pin")), None)
        lat, lon = self.payload.lat, self.payload.lon
        if pin is None or lat is None or lon is None:
            return

        self._pin_anchors = []
        try:
            districts = await self.alkis.districts_around(lat, lon, PIN_RADIUS_M)
        except AppError:
            # An upstream that cannot answer this is not a reason to end the
            # run: every other route has already been tried and found nothing.
            return
        if not districts:
            return

        for district in districts:
            key = expand_gemarkung_key(district.schluessel)
            self._district_outlines.setdefault(key, district)
            self._pin_anchors.append(
                Anchor(
                    art="gemarkung",
                    schluessel=key,
                    name=district.name or key,
                    indiz_id=pin.id,
                    # As weak as the pin it came from. It may only ever order
                    # the list; the area is what decides.
                    confidence=min(pin.sicherheit, 0.25),
                    gemeinde=district.gemeinde,
                )
            )

        names = ", ".join(anchor.name for anchor in self._pin_anchors[:6])
        more = "" if len(self._pin_anchors) <= 6 else f" und {len(self._pin_anchors) - 6} weitere"
        yield SuchEreignis(
            art="phase",
            phase="raum",
            text=(
                f"Die Anzeige nennt keine Gemarkung. Um den Kartenpunkt der Anzeige "
                f"liegen {len(self._pin_anchors)} Gemarkungen: {names}{more}. "
                "Der Punkt ist meist der geokodierte Ortsname und nicht das "
                "Grundstück — er sagt hier nur, welche Gemarkungen gefragt werden, "
                "entschieden wird über die Fläche."
            ),
        )

    async def narrow(self) -> AsyncIterator[SuchEreignis]:
        """From the Indizien in hand to a candidate set. Runs at most twice."""

        async for event in self.anchors_from_pin():
            yield event
        anchors = self.anchors()
        async for event in self.short_circuit():
            yield event

        async for event in self._branch_on_contradiction():
            yield event

        if not self.state.candidates and anchors:
            async for event in self.measure_space(anchors):
                yield event
            async for event in self.staircase(anchors):
                yield event

        if not self.state.candidates:
            # The area route found nothing either, so the contradicted parcel
            # is all there is. It comes back with its objection attached --
            # a candidate somebody can look at beats no answer at all.
            self.state.candidates = self._refuted
            self._refuted = []

        if not self.state.candidates:
            async for event in self.by_number_alone():
                yield event

    async def _branch_on_contradiction(self) -> AsyncIterator[SuchEreignis]:
        """A parcel number whose parcel is the wrong size opens the area route.

        The short circuit used to close it: the staircase runs only while the
        candidate list is empty, so a number that resolved to *some* parcel
        stopped the search that would have found the right one. The
        contradiction was reported and never followed.

        Both readings now stand. The number keeps its parcel, marked with what
        contradicts it, and the area is searched as well -- and if that finds
        nothing, the marked parcel is what the answer carries.
        """

        if len(self.state.candidates) != 1 or not self.active("flurstueck"):
            return
        parcel = self.state.candidates[0]
        if not self._area_contradicts(parcel):
            return

        official = parcel.flaeche_amtlich_m2 or 0.0
        for number in self.active("flurstueck"):
            number.verworfen = True
            number.verworfen_grund = (
                f"Das Flurstück dieser Nummer misst amtlich {official:g} m², das Inserat "
                f"nennt {self._area.value:g} m². Die Fläche ist die verlässlichere Angabe, "
                "deshalb wird auch ohne die Nummer gesucht."
            )
            yield SuchEreignis(art="indiz", indiz=number)
        yield SuchEreignis(
            art="phase",
            phase="kurzschluss",
            text=(
                f"Nummer und Fläche widersprechen sich ({official:g} gegen "
                f"{self._area.value:g} m²) — es wird zusätzlich über die Fläche gesucht"
            ),
        )
        self._refuted = self.state.candidates
        self.state.candidates = []

    def _outside_note(self) -> str | None:
        """What to say about a listing that places itself outside Saxony.

        Not „die Angaben reichen nicht aus" — nothing the seller could add
        would help, and asking for more sends someone looking for a mistake
        that is not there. The reason is stated instead, together with what was
        deliberately *not* done.
        """

        if not self._outside:
            return None
        return (
            f"Das Standortfeld der Anzeige nennt {self._outside}. Dieses Werkzeug fragt "
            "das sächsische Liegenschaftskataster (ALKIS) ab und kann außerhalb Sachsens "
            "kein Flurstück nennen. Gleichnamige Orte in Sachsen wurden bewusst nicht "
            "durchsucht: sie ergäben ein echtes, aber fremdes Flurstück."
        )

    def _foreign_state_note(self) -> str | None:
        """Why an empty run was empty, when the prose named another state.

        The location field is the platform's own statement about where the
        object is, and a state named there stops the run outright. Prose is not
        that: „40 Minuten bis Sachsen-Anhalt" is a sentence about a Saxon plot,
        so a state read out of the body may never stop anything.

        It may still *explain*. When the run found no anchor at all — no place
        in the text is a Saxon Gemarkung — and the text names another state,
        that is the reason, and „für eine Eingrenzung fehlt eine Ortsangabe"
        is not: the location is stated plainly, it is simply not here.
        """

        if self._outside or self.state.candidates or self.anchors():
            return None
        state = federal_state(" ".join(p for p in (self.payload.titel, self.payload.text) if p))
        if state in (None, "Sachsen"):
            return None
        return (
            f"Der Anzeigentext nennt {state}, und keine der genannten Ortsangaben ist eine "
            "sächsische Gemarkung. Dieses Werkzeug fragt allein das sächsische "
            "Liegenschaftskataster (ALKIS) ab."
        )

    async def run(self) -> AsyncIterator[SuchEreignis]:
        async for event in self.harvest():
            yield event

        # Outside Saxony there is nothing to ask the cadastre. Every request
        # from here on would be answered — by parcels belonging to somebody
        # else — so the run stops with the clues it read and says why.
        if self._outside:
            yield SuchEreignis(
                art="phase",
                phase="raum",
                text=f"Das Grundstück liegt in {self._outside}, außerhalb des sächsischen Katasters",
            )
            self.state.status = "erfolglos"
            yield SuchEreignis(
                art="ergebnis",
                status="erfolglos",
                kandidaten=[],
                anzahl=0,
                text=self._outside_note(),
                gebiete=self.state.areas or None,
                anfragen=self.state.requests,
            )
            return

        async for event in self.narrow():
            yield event

        # The images come *after* the text, and only when the text did not
        # settle it. They used to be phase 0, which put a Tesseract pass of up
        # to a few seconds an image in front of the first thing the map could
        # draw — for a channel that most listings do not even have. The text and
        # the metadata are what the search runs on; a Geoportal print is the
        # rescue, not the route.
        if self.payload.bilder and self.verdict() != "bestaetigt":
            before = {indiz.id for indiz in self.state.indicia}
            async for event in self.read_images():
                yield event
            fresh = [i for i in self.state.indicia if i.id not in before]
            for indiz in fresh:
                yield SuchEreignis(art="indiz", indiz=indiz)
            # A number off an image is an official statement about *this* plot
            # and outranks what the prose alone reached, so the narrowing runs
            # again rather than the reading being noted and ignored.
            if any(indiz.art in ("flurstueck", "gemarkung") for indiz in fresh):
                self.state.candidates = []
                async for event in self.narrow():
                    yield event

        if self.state.candidates:
            async for event in self.rank():
                yield event
            await self.fetch_outline()

        self.state.status = self.verdict()
        objection = self.cross_check() or self._set_note()
        huelle = common_envelope(self.state.candidates, district_outline=self.state.outline)
        foreign = self._foreign_state_note()
        # „Gemarkung und Flurstücksnummer stehen im Kaufvertrag“ is advice for a
        # listing this tool could serve. Asking for more input when the input is
        # complete and points to another state is the wrong question.
        question = None if foreign else next_question(self.state.candidates, huelle)
        hint = " ".join(
            p for p in (self._part_area_note(), objection, foreign, self.state.hint, question) if p
        ) or None

        yield SuchEreignis(
            art="ergebnis",
            status=self.state.status,
            kandidaten=self.to_candidates(self.state.candidates),
            anzahl=len(self.state.candidates),
            huelle=huelle,
            text=hint,
            gemarkung_umriss=_geojson(getattr(self.state.outline, "geometry", None)),
            gebiete=self.state.areas or None,
            anfragen=self.state.requests,
        )

    async def rank(self) -> AsyncIterator[SuchEreignis]:
        """Phase 4. It removes nobody -- only the check in phase 5 may do that."""

        if len(self.state.candidates) < 2:
            return
        async for event in self.resolve_bands():
            yield event
        features = [
            name
            for name, present in (
                ("Straße", bool(self._street)),
                ("Nutzungsart", True),
                ("Fläche", self._area is not None),
                ("Entfernung", bool(self._references)),
            )
            if present
        ]
        yield SuchEreignis(
            art="phase",
            phase="bewertung",
            text=(
                f"{len(self.state.candidates)} Kandidaten werden nach "
                f"{', '.join(features)} sortiert — das ordnet nur, es scheidet niemanden aus"
            ),
        )
        yield SuchEreignis(
            art="kandidaten",
            anzahl=len(self.state.candidates),
            kandidaten=self.to_candidates(self.state.candidates),
        )


async def run_search(
    payload: ParcelSearchRequest,
    alkis: AlkisService,
    directory: GemarkungDirectory | None,
    app_settings: AppSettings | None = None,
) -> AsyncIterator[SuchEreignis]:
    engine = SearchEngine(payload, alkis, directory, app_settings)
    async for event in engine.run():
        yield event


def _group_into_anchors(
    entries: Sequence[GemarkungEntry], indiz: Indiz, confidence: float
) -> list[Anchor]:
    """One anchor per *place*, however many Flure the directory files it as.

    „Kitzen Flur 1" to „Flur 11" are one district and one request; two
    districts that merely share a base name in different municipalities stay
    two, because the municipality is what tells them apart.
    """

    grouped: dict[tuple[str, str | None], list[GemarkungEntry]] = {}
    for entry in entries:
        key = expand_gemarkung_key(entry.schluessel)
        group = (fold(base_name(entry.name)), entry.gemeinde)
        rows = grouped.setdefault(group, [])
        if all(row.schluessel != key for row in rows):
            rows.append(replace(entry, schluessel=key))

    out: list[Anchor] = []
    for rows in grouped.values():
        printed = base_name(rows[0].name)
        out.append(
            Anchor(
                art="gemarkung",
                schluessel=rows[0].schluessel,
                name=printed if printed and printed != "?" else indiz.wert,
                indiz_id=indiz.id,
                confidence=confidence,
                gemeinde=rows[0].gemeinde,
                keys=tuple(row.schluessel for row in rows),
            )
        )
    return out


def _without_repeats(anchors: list[Anchor]) -> list[Anchor]:
    """The same district named twice is one anchor, and the first wins."""

    seen: set[str] = set()
    out: list[Anchor] = []
    for anchor in anchors:
        if any(key in seen for key in anchor.keys):
            continue
        seen.update(anchor.keys)
        out.append(anchor)
    return out


def _thousands(value: int) -> str:
    """German thousands separator without depending on a locale: 1131 -> „1 131“."""

    return f"{value:,}".replace(",", " ")


def _combinations_sentence(numbers: int, anchors: int) -> str:
    """What the short circuit is about to ask, in German that counts correctly."""

    total = numbers * anchors
    if total == 1:
        return "Flurstücksnummer und Gemarkung liegen vor — sie werden direkt nachgeschlagen"
    return (
        f"Flurstücksnummer und Gemarkung liegen vor, aber nicht eindeutig — "
        f"{total} Kombinationen werden direkt nachgeschlagen"
    )
