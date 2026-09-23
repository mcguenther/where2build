"""Turning a model's Befund into the values and Indizien the app already has.

The gate in `beleg` decides *whether* a model value survives; this decides what
it becomes. Two destinations, and the split is the rule from `CLAUDE.md` in
another shape:

* **A field** — address, price, area — fills a gap the deterministic readers
  left. Nothing more: `_merge` in the listings router already refuses to
  overwrite a value a portal stated.
* **An Indiz** — a place with its level and relation, a parcel number — goes
  into the search at ``quelle="modell"``, which `SOURCE_CONFIDENCE` puts at
  0.45, below the body text. That is where a model earns its keep: „Thräna ist
  ein kleiner Ortsteil der Kreisstadt Borna" names a district and the
  municipality above it, and telling those two apart is what the patterns in
  `search.indicia` are maintained for and where they measurably fail.

A model Indiz can therefore rank, and it can open a branch that an official
filter then checks. It can never filter and never produce „bestätigt“ — that
follows from its confidence alone and needs no special case, which is the
reason this whole channel was built as an Indiz rather than as an answer.
"""

from __future__ import annotations

from ..schemas import (
    BefundFlurstueck,
    BefundOrt,
    Indiz,
    InseratBefund,
    InseratFelder,
)
from ..search.blocks import fold
from ..search.indicia import normalise_parcel_number, parcel_label
from . import beleg

# Where a model value sits between the body text (0.60) and the platform's own
# pin (0.15). `SOURCE_CONFIDENCE` names 0.45 for the channel; a place whose
# relation the model actually stated is worth that, and a bare mention less.
CONFIDENCE = 0.45
MENTION_CONFIDENCE = 0.2

# Which level the model reported becomes which kind of Indiz. „ortsteil" is a
# district in everything but name, and „strasse" is the one level the
# deterministic reader is better at — it is read here anyway so the answer can
# show what the model saw, at a confidence that only ever orders.
_ART_OF_LEVEL = {
    "gemarkung": "gemarkung",
    "ortsteil": "gemarkung",
    "gemeinde": "gemeinde",
    "strasse": "strasse",
    "unbekannt": "ort",
}

# The fields a Befund may fill, and what the deterministic side calls them.
_FIELDS = ("adresse", "kaufpreis_eur", "grundstuecksflaeche_m2")


def fields_from(
    befund: InseratBefund, text: str, known: InseratFelder
) -> tuple[InseratFelder, list[beleg.Urteil]]:
    """The model's field values that passed the gate, and every verdict.

    ``known`` is what the deterministic readers found; it is the fourth test's
    other side, and a value it already carries is a gap the model was not
    asked to fill.
    """

    verdicts: list[beleg.Urteil] = []
    accepted: dict[str, object] = {}
    for name in _FIELDS:
        entry = getattr(befund.felder, name)
        verdict = beleg.check(
            name, entry.wert, entry.beleg, text, getattr(known, name, None)
        )
        if entry.wert is not None:
            verdicts.append(verdict)
        if verdict.angenommen:
            accepted[name] = _as_field(name, verdict.wert)
    return InseratFelder.model_validate(accepted), verdicts


def _as_field(name: str, value: object) -> object:
    """A gated value in the type its field has. Both money fields are integers."""

    if name in ("kaufpreis_eur", "grundstuecksflaeche_m2") and isinstance(value, (int, float)):
        return int(round(float(value)))
    return value


def indicia_from(
    befund: InseratBefund, text: str, start: int = 0
) -> tuple[list[Indiz], list[beleg.Urteil]]:
    """The places and parcel numbers that passed the gate, as Indizien.

    Every one of them carries the sentence the gate found in the page, because
    that is the Beleg the user is offered when two readings disagree — and a
    contradiction nobody can look up is one nobody can resolve.
    """

    out: list[Indiz] = []
    verdicts: list[beleg.Urteil] = []
    seen: set[tuple[str, str, str]] = set()
    count = start

    for place in befund.orte:
        verdict = beleg.check(f"ort:{place.name}", place.name, place.beleg, text)
        verdicts.append(verdict)
        if not verdict.angenommen:
            continue
        indiz = _place_indiz(place, f"m{count + 1}")
        if _repeated(indiz.art, indiz.wert, indiz.beziehung, seen):
            continue
        count += 1
        out.append(indiz)

    for parcel in befund.flurstuecke:
        label = _parcel_label(parcel)
        if label is None:
            continue
        verdict = beleg.check(f"flurstueck:{label}", label, parcel.beleg, text)
        verdicts.append(verdict)
        if not verdict.angenommen:
            continue
        if _repeated("flurstueck", label, None, seen):
            continue
        count += 1
        out.append(
            Indiz(
                id=f"m{count}",
                art="flurstueck",
                wert=label,
                text=f"Flurstück {label} — vom Modell aus dem Anzeigentext gelesen",
                beleg=parcel.beleg,
                quelle="modell",
                sicherheit=CONFIDENCE,
                fundort="modell",
            )
        )
    return out, verdicts


def _repeated(art: str, value: str, relation: str | None, seen: set) -> bool:
    """Whether this claim has already been made *in this answer*.

    The prompt asks for one entry per statement, so an advert that says three
    things about Borna yields Borna three times. That is one claim stated
    thrice, not three findings: it must not become three Indizien, three rows
    in the divergence log, or three lines under the map.

    Only within the one answer. The same name from the location field, from the
    body text and from a model is *corroboration*, and those stay apart — each
    carries its own `SOURCE_CONFIDENCE`, and which source said what is the
    whole basis of the trust order and of every Konflikt the user is shown.

    The relation belongs in the key. „Grimma" as the municipality the plot lies
    in and „Grimma" as the town 6 km away are two different statements about
    one name, and the prompt goes out of its way to ask for both.
    """

    key = (art, fold(value), relation or "")
    if key in seen:
        return True
    seen.add(key)
    return False


def _parcel_label(parcel: BefundFlurstueck) -> str | None:
    """A model's parcel number, through the same validity test as any other.

    The AdV key's two widths are the whole check a number can be given without
    asking the cadastre, and they are exactly what catches a made-up one.
    """

    parsed = normalise_parcel_number(
        f"{parcel.zaehler}/{parcel.nenner}" if parcel.nenner else str(parcel.zaehler)
    )
    return parcel_label(*parsed) if parsed else None


def _place_indiz(place: BefundOrt, id: str) -> Indiz:
    """One named place, as the Indiz the search weighs.

    The sentence under it is composed here from the level and the relation the
    model reported — never taken from the model's own prose. A template is
    reviewable and reads the same way twice; a sentence a model wrote is
    neither, and this interface has no place a model may write into.
    """

    art = _ART_OF_LEVEL.get(place.ebene, "ort")
    placed = place.beziehung in ("liegt_in", "liegt_an")
    return Indiz(
        id=id,
        art=art,  # type: ignore[arg-type]
        wert=place.name,
        text=_sentence(place),
        beleg=place.beleg,
        quelle="modell",
        sicherheit=CONFIDENCE if placed else MENTION_CONFIDENCE,
        beziehung=place.beziehung,
        fundort="modell",
    )


def _sentence(place: BefundOrt) -> str:
    """The German line under a place a model read. Composed, never written."""

    level = {
        "gemarkung": "Gemarkung",
        "ortsteil": "Ortsteil",
        "gemeinde": "Gemeinde",
        "strasse": "Straße",
    }.get(place.ebene)
    lead = f"{level} {place.name}" if level else place.name
    if place.beziehung == "liegt_in":
        return f"{lead} — das Modell liest den Text so, dass das Grundstück dort liegt"
    if place.beziehung == "liegt_an":
        return f"{lead} — das Modell liest den Text so, dass das Grundstück daran grenzt"
    if place.beziehung == "entfernt_von":
        distance = (
            f" ({place.entfernung_km:g} km)".replace(".", ",")
            if place.entfernung_km
            else ""
        )
        return f"{lead}{distance} wird als entfernt beschrieben — spricht gegen diesen Ort"
    return f"{lead} wird erwähnt, ohne zu sagen wie"


__all__ = ["CONFIDENCE", "MENTION_CONFIDENCE", "fields_from", "indicia_from"]
