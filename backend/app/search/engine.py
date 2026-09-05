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
from dataclasses import dataclass, field
from typing import AsyncIterator, Sequence

from ..errors import UpstreamError
from ..gemarkung_index import GemarkungDirectory, fold
from ..schemas import (
    Indiz,
    Kandidat,
    KandidatProperties,
    Konflikt,
    ParcelSearchRequest,
    SuchEreignis,
    Suchgebiet,
    SuchStatus,
)
from ..services.alkis import (
    AlkisService,
    Flurstueck,
    KatasterBezirk,
    between,
    equals,
    expand_gemarkung_key,
    like,
)
from .envelope import _geojson, common_envelope, next_question
from .indicia import collect_indicia, normalise_parcel_number, read_area, AreaStatement
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

# How many district outlines are drawn as the search space. Enough to show a
# genuine ambiguity, few enough that the map does not become a patchwork and
# the run does not spend a request per wash.
MAX_DRAWN_AREAS = 4

# What the short circuit accepts as agreement between the parcel it resolved
# and the area the listing states. Wider than the plausibility check's factor
# of four on purpose: this only decides whether one more phase runs.
SHORT_CIRCUIT_AREA_FACTOR = 2.0


@dataclass
class Anchor:
    """One spatial container the search may filter inside.

    Not "the most accurate point" -- the narrowest container worth trusting.
    The platform's pin never becomes one: measured 6 235 m from the parcel
    actually offered, because the platform geocodes its own location field.
    """

    art: str
    schluessel: str
    name: str
    indiz_id: str
    confidence: float

    @property
    def condition(self) -> str:
        return equals("gemaschl" if self.art == "gemarkung" else "gmdschl", self.schluessel)


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
    ) -> None:
        self.payload = payload
        self.alkis = alkis
        self.directory = directory
        self.state = SearchState()
        self._area: AreaStatement | None = None
        self._street: str | None = None

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

        area_indiz = next((i for i in self.active("flaeche")), None)
        if area_indiz is not None:
            self._area = read_area(area_indiz.beleg or "") or AreaStatement(
                value=float(area_indiz.wert), wording=""
            )
        street_indiz = next(iter(self.active("strasse")), None)
        self._street = street_indiz.wert if street_indiz else None

        for indiz in self.state.indicia:
            yield SuchEreignis(art="indiz", indiz=indiz)

        for conflict in self._conflicts():
            self.state.conflicts.append(conflict)
            yield SuchEreignis(art="konflikt", konflikt=conflict)

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
                # A place the text says the plot is *away from* is not a rival
                # reading of where it is; it is evidence against itself.
                if indiz.beziehung != "entfernt_von"
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

        active = [i for i in self.active("gemarkung") if i.beziehung != "entfernt_von"]
        chosen_id = self.payload.entscheidungen.get("gemarkung")
        if chosen_id:
            # A person who picked one has settled it; searching the rejected
            # readings anyway would be ignoring the answer we asked for.
            decided = [indiz for indiz in active if indiz.id == chosen_id]
            active = decided or active

        out: list[Anchor] = []
        seen: set[str] = set()
        for indiz in active:
            for key in self._district_keys(indiz):
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Anchor(
                        art="gemarkung",
                        schluessel=key,
                        name=indiz.wert,
                        indiz_id=indiz.id,
                        confidence=indiz.sicherheit,
                    )
                )
        return out or self._municipality_anchors()

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
            if not districts or len(districts) > MAX_MUNICIPALITY_DISTRICTS:
                continue
            out.extend(
                Anchor(
                    art="gemarkung",
                    schluessel=expand_gemarkung_key(entry.schluessel),
                    name=entry.name,
                    indiz_id=indiz.id,
                    confidence=indiz.sicherheit * 0.6,
                )
                for entry in districts
            )
        return out

    def _district_keys(self, indiz: Indiz) -> list[str]:
        """Every cadastral district this Indiz could mean.

        5 339 districts share 4 880 names, so a name is not a key. All of the
        matches are kept: each costs one count request, and dropping an
        ambiguous name would throw away the very case this search is for.
        """

        if indiz.schluessel:
            return [expand_gemarkung_key(indiz.schluessel)]
        if indiz.wert.strip().isdigit():
            return [expand_gemarkung_key(indiz.wert.strip())]
        if not self.directory:
            return []
        needle = fold(indiz.wert)
        return [
            expand_gemarkung_key(entry.schluessel)
            for entry in self.directory.entries
            if fold(entry.name) == needle
        ]

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

        if self._area is not None and official:
            factor = official / self._area.value
            if factor >= SHORT_CIRCUIT_AREA_FACTOR or factor <= 1 / SHORT_CIRCUIT_AREA_FACTOR:
                return (
                    f"Das gefundene Flurstück misst amtlich {official:g} m², das Inserat "
                    f"nennt {self._area.value:g} m². Nummer und Fläche widersprechen "
                    "sich — bitte die Flurstücksnummer prüfen."
                )

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

    # ------------------------------------------------------------------
    # Phases 2 and 3 -- the haystack, then the staircase
    # ------------------------------------------------------------------

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
            *(self.alkis.district_outline(anchor.schluessel) for anchor in anchors),
            return_exceptions=True,
        )
        out: list[Suchgebiet] = []
        for anchor, count, outline in zip(anchors, counts, results):
            if not isinstance(outline, KatasterBezirk) or outline is None:
                continue
            out.append(
                Suchgebiet(
                    schluessel=anchor.schluessel,
                    name=outline.name or anchor.name,
                    anzahl=count if isinstance(count, int) else None,
                    geometry=_geojson(outline.geometry),
                )
            )
        return out

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
            )
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
        try:
            self.state.requests += 1
            self.state.outline = await self.alkis.district_outline(key)
        except UpstreamError:
            # A missing wash is a paler map, not a failed search.
            self.state.outline = None

    async def run(self) -> AsyncIterator[SuchEreignis]:
        async for event in self.harvest():
            yield event

        anchors = self.anchors()
        async for event in self.short_circuit():
            yield event

        if not self.state.candidates and anchors:
            async for event in self.measure_space(anchors):
                yield event
            async for event in self.staircase(anchors):
                yield event

        if not self.state.candidates:
            async for event in self.by_number_alone():
                yield event

        if self.state.candidates:
            async for event in self.rank():
                yield event
            await self.fetch_outline()

        self.state.status = self.verdict()
        objection = self.cross_check() or self._set_note()
        huelle = common_envelope(self.state.candidates, district_outline=self.state.outline)
        question = next_question(self.state.candidates, huelle)
        hint = " ".join(p for p in (objection, self.state.hint, question) if p) or None

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
        features = [
            name
            for name, present in (
                ("Straße", bool(self._street)),
                ("Nutzungsart", True),
                ("Fläche", self._area is not None),
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
) -> AsyncIterator[SuchEreignis]:
    engine = SearchEngine(payload, alkis, directory)
    async for event in engine.run():
        yield event


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
