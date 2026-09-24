"""POST /api/listings/extract -- portal adapters, paste path, error answers."""

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from .conftest import LLM_URL, fixture_text
from .test_llm import completion

CHAT_URL = f"{LLM_URL}/chat/completions"
KLEINANZEIGEN_URL = (
    "https://www.kleinanzeigen.de/s-anzeige/-wohnbaugrundstueck-fuer-efh-mit-b-plan-688-m-/"
    "3425157266-207-4059"
)
IMMOSCOUT_URL = "https://www.immobilienscout24.de/expose/110185322"

# What a model answers now: a Befund, in which every value travels with the
# sentence it was read from. The Belege here stand verbatim in the fixture
# page, because that is the first thing `services.beleg` checks — a Beleg the
# page does not carry is a value the gate refuses, however right it looks.
INSERAT_JSON = {
    "vorlage": "inserat-befund/1",
    "felder": {
        "adresse": {
            "wert": "Muldentalstraße, 01589 Riesa",
            "beleg": "Lage: Muldentalstraße, 01589 Riesa.",
        },
        "kaufpreis_eur": {
            "wert": 89000,
            "wortlaut": "89.000 €",
            "beleg": "Preis: 89.000 €",
        },
        "grundstuecksflaeche_m2": {
            "wert": 688,
            "wortlaut": "ca. 688 m²",
            "beleg": "Gesamtfläche von ca. 688 m²",
        },
    },
    "orte": [
        {
            "name": "Riesa",
            "ebene": "gemeinde",
            "beziehung": "liegt_in",
            "beleg": "Lage: Muldentalstraße, 01589 Riesa.",
        }
    ],
    "flurstuecke": [
        {"zaehler": 790, "beleg": "(Flurstück 790 sowie 706)"},
        {"zaehler": 706, "beleg": "(Flurstück 790 sowie 706)"},
    ],
}


def _kleinanzeigen_page() -> httpx.Response:
    return httpx.Response(
        200,
        text=fixture_text("kleinanzeigen_inserat.html"),
        headers={"content-type": "text/html; charset=utf-8"},
    )


@respx.mock
def test_immobilienscout24_is_not_fetched_and_points_at_the_paste_field(client: TestClient):
    portal = respx.get(url__startswith="https://www.immobilienscout24.de").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": IMMOSCOUT_URL})

    assert answer.status_code == 400
    assert "Seite einfügen" in answer.json()["detail"]
    assert portal.call_count == 0
    assert llm.call_count == 0


@respx.mock
def test_immowelt_is_not_fetched_and_says_why(client: TestClient):
    """DataDome answers every exposé with a 403 challenge, measured 24.09.2026.

    Before it was blocked the request went out and came back as the generic
    502, which advised copying and never named the bookmarklet.
    """

    url = "https://www.immowelt.de/expose/c1fc6775-3423-4549-b881-424be15286ac"
    portal = respx.get(url__startswith="https://www.immowelt.de").mock(
        return_value=httpx.Response(403, text="<html></html>")
    )
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": url})

    assert answer.status_code == 400
    detail = answer.json()["detail"]
    assert "immowelt.de" in detail
    assert "Lesezeichen" in detail and "Seite einfügen" in detail
    assert portal.call_count == 0
    assert llm.call_count == 0


@respx.mock
def test_kleinanzeigen_coordinates_come_from_meta_tags_without_a_model_call(
    without_llm, client: TestClient
):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "meta-tags"
    assert body["felder"]["lat"]["wert"] == 51.39235087498254
    assert body["felder"]["lon"]["wert"] == 13.3868408203125
    assert body["felder"]["lat"]["bestaetigt"] is False
    assert llm.call_count == 0


@respx.mock
def test_kleinanzeigen_description_is_structured_by_the_model(client: TestClient):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    body = answer.json()
    # One call only: the page is already in hand, so no web_fetch is needed.
    assert llm.call_count == 1
    payload = json.loads(llm.calls[0].request.content)
    assert "tools" not in payload
    assert payload["response_format"]["json_schema"]["strict"] is True

    assert body["weg"] == "meta-tags"
    assert body["felder"]["kaufpreis_eur"]["wert"] == 89000
    assert body["felder"]["grundstuecksflaeche_m2"]["wert"] == 688
    # The deterministic coordinate wins over anything the model produces — and a
    # coordinate is not in the model's schema at all, so it cannot produce one.
    assert body["felder"]["lat"]["wert"] == 51.39235087498254
    # The parcel numbers and the place arrive as Indizien, not as fields: a
    # model value may rank the search and never filter it.
    assert [(i["art"], i["wert"]) for i in body["indizien"]] == [
        ("gemeinde", "Riesa"),
        ("flurstueck", "790"),
        ("flurstueck", "706"),
    ]
    assert all(i["quelle"] == "modell" and i["beleg"] for i in body["indizien"])


@respx.mock
def test_unknown_domain_goes_through_web_fetch_then_structuring(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=completion("Baugrundstück in Riesa, 89.000 €, 688 m²")),
            httpx.Response(200, json=completion(json.dumps(INSERAT_JSON))),
        ]
    )

    answer = client.post(
        "/api/listings/extract", json={"url": "https://www.beispielportal.de/objekt/17"}
    )

    assert answer.status_code == 200
    assert llm.call_count == 2
    first = json.loads(llm.calls[0].request.content)
    second = json.loads(llm.calls[1].request.content)
    assert "response_format" not in first and "tools" in first
    assert "tools" not in second and "response_format" in second
    assert answer.json()["weg"] == "llm"


@respx.mock
def test_pasted_text_needs_no_url(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    answer = client.post(
        "/api/listings/extract",
        json={"text": "Baugrundstück 688 m², Flurstück 790 sowie 706, 89.000 €"},
    )

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "eingefuegter-text"
    assert body["quelle_url"] is None
    assert body["felder"]["adresse"]["quelle_url"] is None
    # Pasting must not trigger a fetch, only the structuring call.
    assert llm.call_count == 1
    assert "tools" not in json.loads(llm.calls[0].request.content)


@respx.mock
def test_second_request_for_the_same_url_is_served_from_the_cache(client: TestClient):
    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    first = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})
    second = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL + "?utm_source=x"})

    assert first.json() == second.json()
    assert llm.call_count == 1


def test_request_without_url_or_text_is_a_422(client: TestClient):
    answer = client.post("/api/listings/extract", json={})

    assert answer.status_code == 422
    # The frontend shows `detail`, so `detail` has to say what is missing.
    assert answer.json()["detail"] == "Entweder eine URL oder ein eingefügter Text wird benötigt."


@respx.mock
def test_page_without_any_locator_is_a_400(client: TestClient):
    llm = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=completion("Nur Werbetext ohne Angaben")),
            httpx.Response(
                200,
                json=completion(
                    json.dumps(
                        {
                            "adresse": None,
                            "lat": None,
                            "lon": None,
                            "flurstuecke": [],
                            "kaufpreis_eur": None,
                            "grundstuecksflaeche_m2": None,
                        }
                    )
                ),
            ),
        ]
    )

    answer = client.post(
        "/api/listings/extract", json={"url": "https://www.beispielportal.de/objekt/18"}
    )

    assert answer.status_code == 400
    detail = answer.json()["detail"]
    assert "einfügen" in detail or "eintragen" in detail
    assert llm.call_count == 2


@respx.mock
def test_bare_text_without_a_provider_says_what_to_paste_instead(without_llm, client: TestClient):
    """A sentence with no address and no coordinate needs a model. HTML does not.

    So the refusal names the way round it — copy the page itself — rather than
    only reporting a missing key.
    """

    answer = client.post("/api/listings/extract", json={"text": "Baugrundstück 688 m²"})

    assert answer.status_code == 503
    detail = answer.json()["detail"]
    assert "nicht eingerichtet" in detail
    assert "Strg+A" in detail


def test_a_whole_document_is_read_without_a_model_at_all(without_llm, client: TestClient):
    """This way in exists for portals that refuse a server-side fetch.

    Requiring a model here made it useless in exactly that case. A whole
    document -- what the bookmarklet hands over -- carries its meta tags, its
    price and its attribute list, and the parcel search reads the prose itself.
    """

    answer = client.post(
        "/api/listings/extract", json={"text": fixture_text("inserat-kleinanzeigen.html")}
    )

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "eingefuegter-text"
    assert body["felder"]["kaufpreis_eur"]["wert"] == 80000
    assert body["felder"]["grundstuecksflaeche_m2"]["wert"] == 1025
    # The coordinate is in `<head>`, which is what separates a handed-over
    # document from a clipboard copy -- see the test below.
    assert body["felder"]["lat"]["wert"] == pytest.approx(51.13430038927799)
    assert "Ortsteil Lobstädt bei Neukieritzsch" in body["beschreibung"]
    assert body["bilder"]


def test_a_clipboard_copy_keeps_the_body_and_loses_the_head(without_llm, client: TestClient):
    """What the paste field can and cannot do, pinned against the difference.

    `Strg+A` selects the document's *body*, so a pasted page arrives without
    `<head>` and without any `<script>` -- measured in Chromium, see
    `docs/research/immobilienscout24-zugang.md` § 4. The price, the attribute
    list, the images and the prose are body markup and survive; the coordinate
    lives in `og:latitude` and does not. That is why a pasted ImmoScout page
    read as having no address, no coordinate and no parcel number, which was
    recorded as a fact about the portal and is a fact about the clipboard.
    """

    page = fixture_text("inserat-kleinanzeigen.html")
    body_only = page[page.index("<body") :]
    assert "og:latitude" not in body_only

    answer = client.post("/api/listings/extract", json={"text": body_only})

    assert answer.status_code == 200
    read = answer.json()["felder"]
    assert read["kaufpreis_eur"]["wert"] == 80000
    assert read["grundstuecksflaeche_m2"]["wert"] == 1025
    assert read["lat"]["wert"] is None
    assert read["lon"]["wert"] is None


def test_a_handed_over_document_may_be_megabytes(without_llm, client: TestClient):
    """The cap has to hold a whole portal page, not a clipboard's worth.

    It was 400 000 characters while the clipboard was the only way in.
    `document.documentElement.outerHTML` runs past a megabyte, and there is no
    safe place to cut it: JSON-LD is routinely the last thing in the body.
    """

    page = fixture_text("inserat-kleinanzeigen.html")
    padding = "<!-- {} -->".format("x" * 1_000_000)
    inflated = page.replace("</body>", padding + "</body>")
    assert len(inflated) > 1_000_000

    answer = client.post("/api/listings/extract", json={"text": inflated})
    assert answer.status_code == 200
    assert answer.json()["felder"]["kaufpreis_eur"]["wert"] == 80000

    too_much = "x" * 3_000_001
    assert client.post("/api/listings/extract", json={"text": too_much}).status_code == 422


@respx.mock
def test_provider_timeout_becomes_a_504(client: TestClient):
    respx.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("zu langsam"))

    answer = client.post("/api/listings/extract", json={"text": "Baugrundstück"})

    assert answer.status_code == 504


@respx.mock
def test_an_answer_cached_by_an_older_reader_is_not_served(client: TestClient):
    """The cache that holds an extracted listing never expires.

    So an answer written before the price parser existed would be served for
    ever, and the field stayed empty on exactly the listings the fix was
    written for. The version in the key is what retires it.
    """

    from app.deps import llm_client
    from app.routers.listings import EXTRACTION_VERSION
    from app.services.llm import normalize_url

    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    llm = client.app.dependency_overrides.get(llm_client, llm_client)()
    stale = {
        "quelle_url": KLEINANZEIGEN_URL,
        "weg": "meta-tags",
        "felder": {},
        "beschreibung": None,
        "bilder": [],
    }
    # Exactly the key the deployed build wrote: the URL and nothing else. That
    # entry is what is sitting in the cache volume right now.
    llm.cache.set_json(f"inserat:{normalize_url(KLEINANZEIGEN_URL)}", stale)
    assert EXTRACTION_VERSION >= 2

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    # The page is read again rather than the empty answer being handed back.
    assert answer.json()["felder"]["kaufpreis_eur"]["wert"] == 89000


def test_a_page_whose_prose_is_searchable_needs_no_locator(without_llm, client: TestClient):
    """A dropped ImmoScout page carries none of the three locators.

    No coordinate, often only a district for an address, never a parcel
    number — and prose that names the Ortsteil, the area and the street, which
    is everything the parcel search runs on. Refusing it sent the one portal
    the paste field exists for straight back out again.
    """

    answer = client.post(
        "/api/listings/extract",
        json={
            "text": (
                "Baugrundstück im Ortsteil Oelzschau, zugehörig zur Stadt Rötha. "
                "Das Grundstück umfasst eine Gesamtfläche von ca. 1.300 m²."
            )
        },
    )

    assert answer.status_code == 200
    body = answer.json()
    assert "Oelzschau" in body["beschreibung"]
    # No locator was read, and that is not an error any more.
    assert body["felder"]["adresse"]["wert"] is None


def test_prose_that_names_nowhere_is_still_refused(without_llm, client: TestClient):
    """An area is not an anchor.

    „Baugrundstück 688 m²“ names no place, and every parcel in Saxony of that
    size is not a candidate set — so this still gets the message that says what
    to paste instead, rather than a search that cannot go anywhere.
    """

    answer = client.post("/api/listings/extract", json={"text": "Baugrundstück 688 m²"})

    assert answer.status_code == 503
    assert "Strg+A" in answer.json()["detail"]


def test_a_paste_with_no_markup_at_all_is_read_too(without_llm, client: TestClient):
    """The plainest paste there is: the rendered page, as text.

    The deterministic reader used to run only when the text contained a „<“,
    which was true of the parsers when that gate was written and stopped being
    true once `portal_fields` began going by the German word and the value's
    unit. So somebody who selected an ImmoScout exposé and pasted it got every
    field back empty — „Grundstücksfläche ca. 866 m²“ and „199.000 €“ standing
    in the text they had just handed over, and „Gelesene Werte“ showing
    nothing.
    """

    text = (
        "Preisreduziert! Baugrund in Rückmarsdorf sucht Hausbauer\n"
        "Burghausen-Rückmarsdorf, 04178 Leipzig\n"
        "199.000 €\nKaufpreis 229,79 €/m²\n"
        "Grundstücksfläche ca.\n866 m²\n"
        "Zum Verkauf steht ein schönes Baugrundstück in einer gewachsenen Wohnsiedlung."
    )
    assert "<" not in text

    answer = client.post("/api/listings/extract", json={"text": text})

    assert answer.status_code == 200
    read = answer.json()["felder"]
    assert read["grundstuecksflaeche_m2"]["wert"] == 866
    assert read["kaufpreis_eur"]["wert"] == 199_000
    assert read["adresse"]["wert"] == "04178 Leipzig"


# --------------------------------------------------------------------------
# A link without a model: the same test as a paste
# --------------------------------------------------------------------------

LOBSTAEDT_URL = (
    "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck-ca-1-025qm-direkt-bebaubar/"
    "3423861748-207-3935"
)
FOREIGN_URL = "https://www.ohne-makler.net/immobilie/476452/"
_COORDINATE_TAGS = re.compile(r'<meta property="og:(?:latitude|longitude)"[^>]*>')


def _without_coordinates(name: str) -> str:
    """A recorded page with its coordinate taken out, and nothing added.

    Kleinanzeigen leaves `og:latitude` off an advert whose seller withheld the
    location; this is that page, made from a real one rather than written.
    """

    page = fixture_text(name)
    stripped = _COORDINATE_TAGS.sub("", page)
    assert stripped != page and "og:latitude" not in stripped
    return stripped


def _html(text: str) -> httpx.Response:
    return httpx.Response(200, text=text, headers={"content-type": "text/html; charset=utf-8"})


@respx.mock
def test_a_kleinanzeigen_link_without_a_coordinate_is_read_without_a_model(
    without_llm, client: TestClient
):
    """What went through as a paste was refused as a link.

    The page names its Ortsteil — „Ortsteil Lobstädt bei Neukieritzsch“ — and
    states its area and price in markup, which is everything the parcel search
    runs on. The coordinate is the one thing missing, and the search only ever
    used it to rule places out.
    """

    respx.get(LOBSTAEDT_URL).mock(
        return_value=_html(_without_coordinates("inserat-kleinanzeigen.html"))
    )
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": LOBSTAEDT_URL})

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "abgerufene-seite"
    assert llm.call_count == 0
    assert body["felder"]["lat"]["wert"] is None
    assert body["felder"]["grundstuecksflaeche_m2"]["wert"] == 1025
    assert body["felder"]["kaufpreis_eur"]["wert"] == 80000
    assert "Ortsteil Lobstädt bei Neukieritzsch" in body["beschreibung"]
    # The description, not the page around it.
    assert "Cookie" not in body["beschreibung"]
    assert body["bilder"]


@respx.mock
def test_another_portal_s_link_is_read_without_a_model(without_llm, client: TestClient):
    """ohne-makler.net: no coordinate anywhere, and a place in its prose."""

    respx.get(FOREIGN_URL).mock(return_value=_html(fixture_text("inserat-ohne-makler.html")))
    llm = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("x")))

    answer = client.post("/api/listings/extract", json={"url": FOREIGN_URL})

    assert answer.status_code == 200
    body = answer.json()
    assert body["weg"] == "abgerufene-seite"
    assert llm.call_count == 0
    assert body["felder"]["lat"]["wert"] is None
    # The deterministic fields travel as they do for Kleinanzeigen: they used to
    # be dropped on this path even when the page carried them.
    assert body["felder"]["grundstuecksflaeche_m2"]["wert"] == 5366
    assert body["felder"]["kaufpreis_eur"]["wert"] == 115000
    assert body["felder"]["adresse"]["wert"] == "Maschinenhausstraße, 01587 Riesa, Sachsen"
    assert "Riesa" in body["beschreibung"]


@respx.mock
def test_a_link_to_a_page_that_names_nowhere_says_so(without_llm, client: TestClient):
    """A recorded page with no locator and no place: a house, not a plot.

    The refusal says what is missing and names the bookmarklet — never „nicht
    konfiguriert“, which sent people looking for a server setting.
    """

    url = "https://www.beispielportal.de/objekt/18"
    respx.get(url).mock(return_value=_html(fixture_text("hersteller_haustyp.html")))

    answer = client.post("/api/listings/extract", json={"url": url})

    assert answer.status_code == 503
    detail = answer.json()["detail"]
    assert "nicht konfiguriert" not in detail
    assert "keinen Ort" in detail
    assert "Lesezeichen unter „Seite einfügen“" in detail
    # A refusal is not cached: the same link is asked again next time.
    assert client.post("/api/listings/extract", json={"url": url}).status_code == 503
    assert respx.calls.call_count >= 2


@respx.mock
def test_with_a_model_a_page_without_a_coordinate_still_goes_to_it(client: TestClient):
    """Nothing changes when a model is configured: it reads the page."""

    respx.get(KLEINANZEIGEN_URL).mock(
        return_value=_html(_without_coordinates("kleinanzeigen_inserat.html"))
    )
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    answer = client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL})

    assert answer.status_code == 200
    body = answer.json()
    assert llm.call_count == 1
    assert body["weg"] == "llm"
    assert body["felder"]["lat"]["wert"] is None
    assert body["felder"]["kaufpreis_eur"]["wert"] == 89000


@respx.mock
def test_a_page_read_without_a_model_is_read_again_once_there_is_one(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """The cache never expires, so it has to know whether a model answered."""

    from app.deps import reset_services

    respx.get(KLEINANZEIGEN_URL).mock(return_value=_kleinanzeigen_page())
    llm = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion(json.dumps(INSERAT_JSON)))
    )

    monkeypatch.setenv("LLM_API_KEY", "")
    reset_services()
    assert client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL}).status_code == 200
    assert llm.call_count == 0

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    reset_services()
    assert client.post("/api/listings/extract", json={"url": KLEINANZEIGEN_URL}).status_code == 200
    assert llm.call_count == 1
