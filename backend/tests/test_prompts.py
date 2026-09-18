"""What the model is told, and what it is deliberately not told.

The second half is the one that matters. A teacher shown the student's answers
is not a teacher: if the request carried what the patterns concluded, the model
would agree with us and the divergence log would measure nothing at all.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.deps import llm_client
from app.routers.listings import _known_districts
from app.schemas import InseratBefund
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
    assert prompts.user_message("Ein Grundstück.", []) == "Inserat:\n\nEin Grundstück."


def test_the_fetch_prompt_asks_for_the_page_and_not_for_fields():
    """Telling a fetch call about fields is an invitation to summarise instead
    of quote — and the Beleg gate then refuses everything it returns."""

    assert "unverändert" in prompts.FETCH
    for field in ("Kaufpreis", "Flurstück", "beziehung"):
        assert field not in prompts.FETCH
