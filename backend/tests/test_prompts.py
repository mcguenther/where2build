"""What the model is told, and what it is deliberately not told.

The second half is the one that matters. A teacher shown the student's answers
is not a teacher: if the request carried what the patterns concluded, the model
would agree with us and the divergence log would measure nothing at all.
"""

from __future__ import annotations

import json
from typing import get_args

import httpx
import pytest
import respx

from app.deps import llm_client
from app.routers.listings import _known_districts
from app.schemas import (
    BEFUND_VORLAGE,
    InseratBefund,
    Ortsbeziehung,
    Ortsebene,
)
from app.services import prompts

from .test_listings import CHAT_URL, completion

# Advert 3499632623, the part every reader in this project has been measured on.
INSERAT = (
    "Baugrundstück in Großbothen, einem OT von Grimma.\n"
    "Das Grundstück ist 502 m² groß und liegt an der Wiesenstraße.\n"
    "Über die B107 erreichen Sie die ca. 6 km entfernte Kreisstadt Grimma."
)


def test_the_instructions_travel_as_a_system_prompt_and_the_listing_as_the_message():
    """One blob re-sent per advert pays for the instructions again every time,
    and neither API can cache a prefix that changes."""

    message = prompts.user_message(INSERAT, ["Großbothen", "Grimma"])
    assert INSERAT in message
    # The instructions are not in it — they are the other half.
    assert "beziehung:" not in message
    assert "Rechne nichts aus" in prompts.SYSTEM


@respx.mock
async def test_the_system_prompt_is_a_field_of_its_own_on_both_wire_formats():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=completion(json.dumps({"vorlage": "inserat-befund/1"}))
        )
    )

    await llm_client().structure(
        "Der Inseratstext.", InseratBefund, "befund", "", system=prompts.SYSTEM
    )

    messages = json.loads(route.calls[0].request.content)["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == prompts.SYSTEM
    assert messages[1]["content"] == "Der Inseratstext."


def test_the_vocabulary_the_search_supports_is_the_vocabulary_the_prompt_names():
    """A name in an enum conveys nothing. The schema says „liegt_in" is allowed;
    it does not say that „die ca. 6 km entfernte Kreisstadt Grimma" is the
    opposite of it."""

    for level in ("gemarkung", "ortsteil", "gemeinde", "strasse", "unbekannt"):
        assert level in prompts.SYSTEM
    for relation in ("liegt_in", "liegt_an", "entfernt_von", "erwaehnt"):
        assert relation in prompts.SYSTEM
    # And every trap this project measured and got wrong first.
    for trap in ("Thräna", "Anbindung an Leipzig", "Schulen in Roitzsch", "Kitzen"):
        assert trap in prompts.SYSTEM


def test_the_register_is_sent_as_material_and_never_as_an_answer():
    """Which names exist is data about Saxony. Which one the advert means is
    the question — and sending our own reading of it would make the model agree
    with us."""

    hints = _known_districts(INSERAT)
    assert "Großbothen" in hints and "Grimma" in hints
    # A street is not a district, and neither is a sentence's first word.
    assert "Wiesenstraße" not in hints
    assert "Baugrundstück" not in hints

    message = prompts.user_message(INSERAT, hints)
    assert "Großbothen" in message
    # Nothing about what our patterns concluded: no level, no relation, no
    # area, no verdict. The words alone.
    for leak in ("liegt_in", "ebene=", "beziehung", "502", "Kandidat", "bestätigt"):
        assert leak not in message.replace(INSERAT, "")


def test_a_listing_without_a_known_name_still_travels():
    assert prompts.user_message("Ein Grundstück.", []) == (
        "Das Inserat steht zwischen den Zeilen aus Prozentzeichen.\n\n"
        "%%%%\nEin Grundstück.\n%%%%"
    )


def test_the_listing_is_fenced_and_the_fence_is_announced():
    """An advert is prose with headings and its own „Hinweis:" lines, and it
    arrives after a hint of ours. Without a delimiter, where the seller's text
    begins is a matter of interpretation."""

    message = prompts.user_message(INSERAT, ["Großbothen"])
    assert f"{prompts.FENCE}\n{INSERAT}\n{prompts.FENCE}" in message
    # Announced in both halves: the rule in the stable one, the fence itself
    # in the one that carries the text.
    assert "Prozentzeichen" in message
    assert "Prozentzeichen" in prompts.SYSTEM
    # The hint stands outside the fence.
    assert message.index("Gemarkungsverzeichnis") < message.index(prompts.FENCE)


def test_the_fence_grows_until_the_listing_cannot_contain_it():
    """A fence that occurs inside the advert would end the text early — the one
    failure a delimiter exists to prevent."""

    assert prompts.fence_for("Ein Grundstück.") == "%%%%"
    assert prompts.fence_for("Rabatt %%%% auf alles") == "%%%%%"
    tricky = "%%%% und %%%%%"
    fence = prompts.fence_for(tricky)
    assert fence not in tricky
    assert prompts.user_message(tricky, []).count(fence) == 2


def test_the_shape_carries_exactly_the_fields_the_schema_has():
    """A skeleton in a prompt is a second statement of the schema, and two
    statements drift. Strip the comments and what is left has to parse, with
    the key set `InseratBefund` actually has — no field missing, none invented.
    """

    naked = "\n".join(
        line for line in prompts.SHAPE.splitlines() if not line.lstrip().startswith("//")
    )
    skeleton = json.loads(naked)

    schema = InseratBefund.model_json_schema()
    properties = set(schema.get("properties", {}))
    for definition in schema.get("$defs", {}).values():
        properties |= set(definition.get("properties", {}))

    shown = set()

    def keys(node):
        if isinstance(node, dict):
            shown.update(node)
            for value in node.values():
                keys(value)
        elif isinstance(node, list):
            for value in node:
                keys(value)

    keys(skeleton)
    assert shown == properties
    assert skeleton["vorlage"] == BEFUND_VORLAGE

    # And the two enumerations, whose values the skeleton spells out.
    place = skeleton["orte"][0]
    assert set(place["ebene"].split(" | ")) == set(get_args(Ortsebene))
    assert set(place["beziehung"].split(" | ")) == set(get_args(Ortsbeziehung))


def test_the_shape_says_what_a_strict_schema_cannot():
    """A JSON schema rejects a wrong shape and states nothing: not that an
    absent value is null rather than an omitted key, not that `wortlaut` keeps
    the rounding `wert` drops, not that a denominator can be a letter."""

    assert "ausschließlich mit einem JSON-Objekt" in prompts.SYSTEM
    assert "bekommt null" in prompts.SYSTEM
    assert "ohne Einheit und Tausenderpunkt" in prompts.SYSTEM
    assert "kann ein Buchstabe sein" in prompts.SYSTEM
    # A skeleton, not a worked example — nothing in it can be copied as a value.
    assert "Kommentarzeilen" in prompts.SYSTEM
    assert "748" not in prompts.SHAPE


def test_the_fetch_prompt_asks_for_the_page_and_not_for_fields():
    """Telling a fetch call about fields is an invitation to summarise instead
    of quote — and the Beleg gate then refuses everything it returns."""

    assert "unverändert" in prompts.FETCH
    for field in ("Kaufpreis", "Flurstück", "beziehung"):
        assert field not in prompts.FETCH
