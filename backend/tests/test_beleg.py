"""The gate a model value passes before it becomes an Indiz.

Every case here is one a model actually produces. The first is the one the
whole thing was built for: advert 2418686487 states 748,50 m² and „92,00 € pro
m²“ and never states a price, 748,5 x 92 is 68 862 €, and a model rounds that
to 69 000 € and writes a Beleg for it that stands nowhere on the page.
"""

from __future__ import annotations

from app.schemas import InseratBefund, InseratFelder
from app.services import befund as befund_service
from app.services import beleg

# Advert 2418686487, the part that matters.
TEXT = (
    "Zum Verkauf steht ein attraktives, ca. 748,50 m² großes Baugrundstück in Thräna.\n"
    "Kaufpreis pro m²: 92,00 €\n"
    "Thräna ist mit seinen etwa 765 Einwohnern ein kleiner Ortsteil der "
    "Kreisstadt Borna.\n"
    "Flurstück: 107/60"
)


def test_a_price_nobody_wrote_is_not_a_statement_in_a_listing():
    """Rechnen ist nicht Lesen. The figure is arithmetically right and the
    sentence carrying it does not exist."""

    verdict = beleg.check(
        "kaufpreis_eur", 69000, "Der Kaufpreis beträgt 69.000 €", TEXT
    )
    assert verdict.verworfen
    assert "steht so nicht im Anzeigentext" in verdict.grund


def test_a_beleg_that_quotes_another_sentence_is_refused():
    """The sentence is real, the value is not in it. „92,00 €“ is a price per
    square metre and the model reported it as the asking price."""

    assert beleg.check("kaufpreis_eur", 89000, "Kaufpreis pro m²: 92,00 €", TEXT).verworfen


def test_the_normalisation_covers_whitespace_quotes_and_case_and_nothing_else():
    """Strict on purpose: a normalisation that also dropped punctuation would
    let „6 km entfernt.“ pass for „6 km entfernt?“."""

    assert beleg.quotes_the_text("KAUFPREIS   pro m²: 92,00 €", TEXT)
    assert beleg.quotes_the_text("„Flurstück: 107/60“", TEXT)
    assert not beleg.quotes_the_text("Kaufpreis pro m² 92,00 €", TEXT)


def test_german_notation_is_one_number_however_it_is_written():
    """„1.076“ and „1076“ are the same figure, and „748,50“ is 748,5."""

    assert beleg.german_numbers("ca. 748,50 m² für 199.000 €") == [748.5, 199000.0]
    # A thousands dot is only one when three digits follow it, or „1.5“ would
    # be fifteen hundred — and a listing writes both shapes.
    assert beleg.german_numbers("1.5 km") == [1.5]
    assert beleg.states_the_value(1076, "Grundstücksfläche: 1.076 m²")
    assert beleg.states_the_value(748.5, "ca. 748,50 m² großes Baugrundstück")


def test_an_implausible_value_is_a_reading_error_not_a_plot():
    verdict = beleg.check(
        "grundstuecksflaeche_m2", 4.0, "ca. 748,50 m² großes Baugrundstück", TEXT
    )
    assert verdict.verworfen


def test_the_page_wins_where_the_two_disagree():
    """The fourth test. Shown, never resolved quietly — the rule this project
    applies to every other contradiction."""

    verdict = beleg.check(
        "grundstuecksflaeche_m2",
        748.5,
        "ca. 748,50 m² großes Baugrundstück",
        TEXT,
        known=700,
    )
    assert verdict.verworfen
    assert "Die Angabe der Seite gilt" in verdict.grund
    # A rounding is not a disagreement, and a gap is not one either.
    assert beleg.check(
        "grundstuecksflaeche_m2", 748.5, "ca. 748,50 m² großes Baugrundstück", TEXT, 748
    ).angenommen
    assert beleg.check(
        "grundstuecksflaeche_m2", 748.5, "ca. 748,50 m² großes Baugrundstück", TEXT, None
    ).angenommen


def test_a_value_without_a_beleg_is_no_value():
    assert beleg.check("kaufpreis_eur", 89000, None, TEXT).verworfen
    assert beleg.check("kaufpreis_eur", 89000, "   ", TEXT).verworfen


def test_the_refusals_are_said_out_loud_with_their_reasons():
    """„drei Werte verworfen“ tells nobody which three, and the whole reason a
    model value carries its Beleg is that a person can look it up."""

    note = beleg.refusal_note(
        [
            beleg.check("kaufpreis_eur", 69000, "Der Kaufpreis beträgt 69.000 €", TEXT),
            beleg.check("grundstuecksflaeche_m2", 748.5, "ca. 748,50 m² großes Baugrundstück", TEXT),
        ]
    )
    assert note.startswith("Eine Angabe des Modells wurde nicht übernommen.")
    assert "69.000" in note
    assert beleg.refusal_note([]) is None


# ----------------------------------------------------------------------
# What survives becomes a field or an Indiz — never an answer
# ----------------------------------------------------------------------


def _befund(**parts) -> InseratBefund:
    return InseratBefund.model_validate(parts)


def test_the_level_and_the_relation_are_what_a_model_earns_its_keep_with():
    """„Thräna ist ein kleiner Ortsteil der Kreisstadt Borna“ names a district
    and the municipality above it. Telling those two apart is what the patterns
    in `search.indicia` are maintained for, and where they measurably fail."""

    indicia, _ = befund_service.indicia_from(
        _befund(
            orte=[
                {
                    "name": "Thräna",
                    "ebene": "gemarkung",
                    "beziehung": "liegt_in",
                    "beleg": "Thräna ist mit seinen etwa 765 Einwohnern ein kleiner "
                             "Ortsteil der Kreisstadt Borna",
                },
                {
                    "name": "Borna",
                    "ebene": "gemeinde",
                    "beziehung": "liegt_in",
                    "beleg": "ein kleiner Ortsteil der Kreisstadt Borna",
                },
            ]
        ),
        TEXT,
    )
    assert [(i.art, i.wert, i.beziehung) for i in indicia] == [
        ("gemarkung", "Thräna", "liegt_in"),
        ("gemeinde", "Borna", "liegt_in"),
    ]
    # Below the body text, so it may order the search and can never filter it.
    assert all(i.quelle == "modell" and i.sicherheit <= 0.45 for i in indicia)
    # And the sentence under it is composed here, not taken from the model.
    assert indicia[0].text.startswith("Gemarkung Thräna —")


def test_a_place_the_page_does_not_mention_never_arrives():
    indicia, verdicts = befund_service.indicia_from(
        _befund(
            orte=[
                {
                    "name": "Leipzig",
                    "ebene": "gemeinde",
                    "beziehung": "entfernt_von",
                    "entfernung_km": 30,
                    "beleg": "rund 30 km bis Leipzig",
                }
            ]
        ),
        TEXT,
    )
    assert indicia == []
    assert verdicts[0].verworfen


def test_a_made_up_parcel_number_is_dropped_before_it_costs_a_request():
    """The AdV key's two widths are the whole validity test a number can be
    given without asking the cadastre — and a model's number goes through the
    same one as a garbled OCR reading."""

    indicia, _ = befund_service.indicia_from(
        _befund(
            flurstuecke=[
                {"zaehler": 107, "nenner": "60", "beleg": "Flurstück: 107/60"},
                {"zaehler": 790717, "beleg": "Flurstück: 107/60"},
            ]
        ),
        TEXT,
    )
    assert [i.wert for i in indicia] == ["107/60"]


def test_a_field_the_page_already_states_is_not_a_gap_to_fill():
    fields, verdicts = befund_service.fields_from(
        _befund(
            felder={
                "grundstuecksflaeche_m2": {
                    "wert": 748.5,
                    "beleg": "ca. 748,50 m² großes Baugrundstück",
                }
            }
        ),
        TEXT,
        InseratFelder(grundstuecksflaeche_m2=700),
    )
    assert fields.grundstuecksflaeche_m2 is None
    assert verdicts[0].verworfen
