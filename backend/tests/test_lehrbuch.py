"""The divergence log: what a model read that the patterns did not.

A model here is a teacher whose answer is never trusted and always checked, and
that makes every disagreement worth keeping: where the model read something the
patterns missed, that is the pattern that is missing — with the sentence it is
missing on, which the Beleg gate has already proved stands in the page.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.deps import lehrbuch
from app.services import lehrbuch as lehrbuch_service
from app.services.lehrbuch import Abweichung, Lehrbuch, compare, fingerprint, scrub

from .conftest import fixture_text
from .test_listings import CHAT_URL, KLEINANZEIGEN_URL, completion


@pytest.fixture
def book():
    """The real log, which `isolated_settings` already puts in this test's own
    cache directory. Nothing is patched: what the test drives is the wiring."""

    lehrbuch.cache_clear()
    yield lehrbuch()
    lehrbuch.cache_clear()


def test_a_gap_is_the_pattern_that_is_missing():
    """The reader found nothing, the model found something the gate accepted."""

    found = compare(
        deterministic=[("flaeche", "748")],
        accepted=[("gemarkung", "Thräna", "Thräna ist ein Ortsteil der Kreisstadt Borna")],
        refused=[],
        text_hash=fingerprint("x"),
    )
    assert [(a.art, a.feld, a.regulaer, a.modell) for a in found] == [
        ("luecke", "gemarkung", None, "Thräna")
    ]


def test_an_agreement_produces_nothing():
    """A log that also holds the cases where the pipeline was right is a log
    nobody reads."""

    assert compare(
        deterministic=[("gemarkung", "Thräna")],
        accepted=[("gemarkung", "Thräna", "… Ortsteil …")],
        refused=[],
        text_hash=fingerprint("x"),
    ) == []


def test_a_contradiction_keeps_both_readings():
    found = compare(
        deterministic=[("gemarkung", "Grimma")],
        accepted=[("gemarkung", "Großbothen", "am Ortsrand von Großbothen")],
        refused=[],
        text_hash=fingerprint("x"),
    )
    assert found[0].art == "widerspruch"
    assert found[0].regulaer == "grimma" and found[0].modell == "Großbothen"


def test_the_teacher_being_wrong_is_kept_too():
    """The only kind that can show the gate earning its keep."""

    found = compare(
        deterministic=[],
        accepted=[],
        refused=[("kaufpreis_eur", "69000", "Der Kaufpreis beträgt 69.000 €", "steht so nicht im Text")],
        text_hash=fingerprint("x"),
    )
    assert found[0].art == "verworfen"
    assert found[0].grund == "steht so nicht im Text"


def test_no_contact_detail_reaches_the_log():
    """A Beleg is a whole sentence out of the page, and a sentence can carry
    what the extraction schema cannot."""

    cleaned = scrub("Fragen an Max Mustermann, 0341 1234567 oder makler@example.de")
    assert "0341" not in cleaned and "@" not in cleaned
    assert cleaned.count("[entfernt]") == 2
    # Long enough for the clause a pattern is written against, and no longer.
    assert len(scrub("x" * 1000)) == lehrbuch_service.MAX_BELEG_CHARS


@pytest.mark.anyio
async def test_the_same_listing_read_twice_is_one_row(book):
    """Re-reading is the normal case — the extraction cache has no expiry and a
    changed prompt makes every listing new again."""

    entries = compare(
        deterministic=[],
        accepted=[("gemarkung", "Thräna", "… Ortsteil der Kreisstadt Borna")],
        refused=[],
        text_hash="abc123",
    )
    await book.record(entries)
    await book.record(entries)
    assert len(book.read_file()) == 1


@pytest.mark.anyio
async def test_a_log_that_cannot_be_written_does_not_fail_the_reading(tmp_path):
    """A listing that was read is read whether or not the note about it could
    be filed."""

    # A file where a directory would have to be. Running as root makes a
    # read-only directory writable again, so the impossibility has to be one
    # the file system cannot argue with.
    blocked = tmp_path / "keinordner"
    blocked.write_text("x")
    broken = Lehrbuch(blocked / "unten" / "x.jsonl")
    assert await broken.record(
        [Abweichung("luecke", "gemarkung", None, "Thräna", None, None, "abc")]
    ) == 0


@respx.mock
def test_what_the_model_read_and_the_patterns_did_not_lands_in_the_log(
    client: TestClient, book
):
    """The whole path, on the recorded Kleinanzeigen page: the model answers a
    Befund, the gate checks it, and what the two readers disagreed about is
    filed on the way past."""

    respx.get(KLEINANZEIGEN_URL).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("kleinanzeigen_inserat.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json=completion(
                json.dumps(
                    {
                        "vorlage": "inserat-befund/1",
                        "felder": {
                            # Arithmetic, not reading: the page never states it.
                            "kaufpreis_eur": {
                                "wert": 129000,
                                "beleg": "Der Kaufpreis beträgt 129.000 €",
                            }
                        },
                        "orte": [
                            {
                                "name": "Riesa",
                                "ebene": "gemeinde",
                                "beziehung": "liegt_in",
                                "beleg": "Lage: Muldentalstraße, 01589 Riesa.",
                            }
                        ],
                        "flurstuecke": [],
                        "vorbehalte": [],
                    }
                )
            ),
        )
    )

    assert client.post(
        "/api/listings/extract", json={"url": KLEINANZEIGEN_URL}
    ).status_code == 200

    answer = client.get("/api/lehrbuch")
    assert answer.status_code == 200
    body = answer.json()
    assert body["speicher"] == "datei"
    kinds = {(row["art"], row["feld"]) for row in body["zeilen"]}
    # The invented price, refused by the gate and kept as a note about it.
    assert ("verworfen", "kaufpreis_eur") in kinds
    refused = next(r for r in body["zeilen"] if r["art"] == "verworfen")
    assert "steht so nicht" in refused["grund"]
    assert refused["modell_id"] and refused["vorlage"] == "inserat-befund/1"
    # And the listing itself is named, never stored.
    assert all("Muldentalstraße" not in (row["beleg"] or "") or row["art"] != "verworfen"
               for row in body["zeilen"])
    assert all(row["text_hash"] for row in body["zeilen"])
