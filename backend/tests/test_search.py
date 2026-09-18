"""POST /api/parcels/search -- the staircase, its short circuit and its conflicts.

Every cadastral answer here is a recorded one: the counts and the two parcels in
``alkis_grossbothen_band.gml`` were fetched from the live WFS on 05.09.2026 and
are the same figures ``docs/research/flurstueck-identifikation.md`` reports.
"""

from __future__ import annotations

import asyncio
import io
import json

import httpx
import pytest
from shapely.geometry import Polygon, box
import respx
from fastapi.testclient import TestClient

from app.gemarkung_index import GemarkungDirectory, GemarkungEntry
from app.schemas import Indiz, ParcelSearchRequest
from app.search.envelope import common_envelope
from app.search.indicia import (
    AreaStatement,
    collect_indicia,
    district_matches,
    describes_part_area,
    federal_state,
    municipality_name,
    municipality_spelling,
    normalise_parcel_number,
    outside_saxony,
    read_area,
    read_dimensions,
)
from app.search import distance
from app.search.blocks import split_blocks
from app.search.distance import read_distances
from app.search.ladder import tolerance_ladder
from app.search.scoring import land_use, score, street_match
from app.services import ocr
from app.services.alkis import Flurstueck, parse_feature_collection

from app.deps import alkis_service
from app.search.engine import Reference, SearchEngine

from .conftest import ALKIS_URL, fixture_bytes, fixture_json, fixture_text

def _drain(events):
    """Every event of an async generator, as a list."""

    async def collect():
        return [event async for event in events]

    return asyncio.run(collect())


# The three district names the reference listing contains, plus the second
# Höfgen -- a name is not a key, and two of these share one.
DIRECTORY = GemarkungDirectory(
    [
        GemarkungEntry("Großbothen", "144241", "Stadt Grimma"),
        GemarkungEntry("Grimma", "144236", "Stadt Grimma"),
        GemarkungEntry("Höfgen", "144245", "Stadt Grimma"),
        GemarkungEntry("Höfgen", "146132", "Stadt Colditz"),
        GemarkungEntry("Mölkau", "143156", "Stadt Leipzig"),
        # The districts the four recorded adverts turn on. Two Plagwitz, and
        # only the municipality tells them apart.
        GemarkungEntry("Plagwitz", "140427", "Stadt Leipzig"),
        GemarkungEntry("Plagwitz", "148642", "Machern"),
        GemarkungEntry("Machern", "148635", "Machern"),
        GemarkungEntry("Püchau", "148643", "Machern"),
        GemarkungEntry("Lobstädt", "141894", "Neukieritzsch"),
        GemarkungEntry("Neukieritzsch", "141896", "Neukieritzsch"),
        GemarkungEntry("Leipzig", "140415", "Stadt Leipzig"),
        # The two halves of the Leipzig Ortsteil „Burghausen-Rückmarsdorf“,
        # which is itself no Gemarkung — and the two Grünau, both 80 km away,
        # which is why splitting a compound needs the municipality's consent.
        GemarkungEntry("Burghausen", "145507", "Stadt Leipzig"),
        GemarkungEntry("Rückmarsdorf", "145614", "Stadt Leipzig"),
        GemarkungEntry("Lausen", "145611", "Stadt Leipzig"),
        GemarkungEntry("Grünau", "148814", "Großolbersdorf"),
        GemarkungEntry("Grünau", "148916", "Langenweißbach"),
        GemarkungEntry("Borna", "141810", "Stadt Borna"),
        GemarkungEntry("Thräna", "141922", "Stadt Borna"),
        GemarkungEntry("Bad Lausick", "143836", "Stadt Bad Lausick"),
        GemarkungEntry("Etzoldshain", "143840", "Stadt Bad Lausick"),
        # A common German noun that is also a real Gemarkung. The Machern
        # advert contains it in „geprägt von Wiesen und Feldern".
        GemarkungEntry("Wiesen", "148950", "Stadt Wildenfels"),
        # Three Saxon Roitzsch, none of them the one near Bitterfeld the Brehna
        # advert names — 148654 holds a parcel of exactly its stated 600 m².
        GemarkungEntry("Roitzsch", "143027", "Stadt Dresden"),
        GemarkungEntry("Roitzsch", "146088", "Stadt Lommatzsch"),
        GemarkungEntry("Roitzsch", "148654", "Stadt Wurzen"),
        # A name that begins with the word the column also puts in front of
        # it. The real register spells this one „Stadt Stadt Wehlen".
        GemarkungEntry("Wehlen", "122015", "Stadt Stadt Wehlen"),
    ],
    stand="2026-09-05",
)

# Four real adverts, read on 05.09.2026, with the parcel each resolves to. The
# descriptions are the portal's own, not the whole page: what the search reads
# is the listing, and the difference is a cookie banner and a category tree.
LISTINGS = fixture_json("inserate-sachsen.json")

LISTING = (
    "Baugrundstück in ruhiger Lage am Ortsrand von Großbothen, einem OT von Grimma. "
    "Das Grundstück ist 502 m² groß und liegt an der Wiesenstraße. "
    "Über die B107 erreichen Sie die ca. 6 km entfernte Kreisstadt Grimma. "
    "Sehenswert sind das Kloster Nimbschen und die Schiffsmühle in Höfgen."
)


def _hits(count: int) -> httpx.Response:
    """A ``resultType=hits`` answer, in the shape the service really sends."""

    name = {0: "alkis_hits_null.xml", 1: "alkis_hits_eins.xml", 1131: "alkis_hits_gemarkung.xml"}
    if count in name:
        return httpx.Response(200, content=fixture_bytes(name[count]))
    body = fixture_bytes("alkis_hits_eins.xml").decode("utf-8")
    return httpx.Response(200, content=body.replace('numberMatched="1"', f'numberMatched="{count}"'))


def _gml(name: str) -> httpx.Response:
    return httpx.Response(200, content=fixture_bytes(name))


def _cadastre(counts: dict[str, int], features: dict[str, str]):
    """An ALKIS stub that answers by what was asked, not by call order.

    The search decides how many anchors are worth a request, and that number
    moves whenever the reading of a listing improves. A stub keyed on the
    request body keeps the tests about *behaviour* -- which district was asked,
    what came back -- instead of about a sequence that a better reading breaks.

    ``counts`` and ``features`` map a substring of the request (a district key,
    an area) to a hit count and to a fixture; the first match wins, and the
    fallbacks are "nothing there".
    """

    def answer(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8")
        if 'resultType="hits"' in body:
            for needle, count in counts.items():
                if all(part in body for part in needle.split("+")):
                    return _hits(count)
            return _hits(0)
        for needle, fixture in features.items():
            if all(part in body for part in needle.split("+")):
                return _gml(fixture)
        return _gml("alkis_leer.gml")

    return answer


def _stream(client: TestClient, payload: dict) -> list[dict]:
    answer = client.post("/api/parcels/search", json=payload)
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in answer.text.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _directory(monkeypatch: pytest.MonkeyPatch):
    """Serve the small district list instead of the committed 5 339."""

    monkeypatch.setattr("app.routers.search.gemarkung_directory", lambda: DIRECTORY)


# --------------------------------------------------------------------------
# Reading the listing
# --------------------------------------------------------------------------


def test_a_garbled_parcel_number_is_rejected_before_it_reaches_the_cadastre():
    """The 7-degree misreading that returned „Flurstück 790717“.

    An empty answer is harmless; a plausible wrong number resolves to a real
    but foreign parcel, and that is exactly the error validating against ALKIS
    cannot catch. Five digits is the width the AdV parcel key gives the
    numerator, so six is structurally impossible.
    """

    assert normalise_parcel_number("790/11") == ("790", "11")
    assert normalise_parcel_number("476") == ("476", None)
    assert normalise_parcel_number("41/e") == ("41", "e")
    assert normalise_parcel_number("790717") is None


def test_a_place_is_read_by_its_relation_and_not_by_how_often_it_is_named():
    """Grimma is named as often as Großbothen -- because it is 6 km away."""

    indicia = collect_indicia(text=LISTING, directory=DIRECTORY)
    districts = {i.wert: i for i in indicia if i.art == "gemarkung"}
    grimma = [i for i in indicia if i.wert == "Grimma"]

    assert districts["Großbothen"].beziehung == "liegt_in"
    assert districts["Höfgen"].beziehung == "liegt_in"
    # The one the text places the plot *in* outranks the one it merely mentions.
    distant = next(i for i in grimma if i.beziehung == "entfernt_von")
    assert districts["Großbothen"].sicherheit > distant.sicherheit
    # And the distant one is not offered as a cadastral district at all: the
    # sentence names the town, and the register knows Grimma as one.
    assert {i.art for i in grimma} == {"gemeinde"}


def test_an_ambiguous_name_says_so_rather_than_picking_one():
    indicia = collect_indicia(text=LISTING, directory=DIRECTORY)
    hoefgen = next(i for i in indicia if i.wert == "Höfgen")

    assert hoefgen.schluessel is None
    assert "2-mal" in hoefgen.text


def test_the_authoritys_own_address_is_not_read_as_a_street():
    """`Olbrichtplatz` is the GeoSN's office, printed on every sheet it issues."""

    text = (
        "Flurstück 790/11 an der Wiesenstraße. "
        "Staatsbetrieb Geobasisinformation und Vermessung Sachsen, Olbrichtplatz 3, Dresden."
    )
    streets = {i.wert for i in collect_indicia(text=text, directory=DIRECTORY) if i.art == "strasse"}

    assert "Wiesenstraße" in streets
    assert not any("Olbrichtplatz" in street for street in streets)


def test_the_pin_is_collected_but_never_trusted():
    indicia = collect_indicia(lat=51.244012, lon=12.721705, text=LISTING, directory=DIRECTORY)
    pin = next(i for i in indicia if i.art == "pin")

    assert pin.sicherheit == pytest.approx(0.15)
    assert pin.sicherheit == min(i.sicherheit for i in indicia)


# --------------------------------------------------------------------------
# The tolerance staircase
# --------------------------------------------------------------------------


def test_the_staircase_comes_from_the_wording_not_from_a_constant():
    exact = tolerance_ladder(read_area("502 m²"))
    rounded = tolerance_ladder(read_area("ca. 500 m²"))
    bound = tolerance_ladder(read_area("ab 450 m²"))
    span = tolerance_ladder(read_area("450–600 m²"))

    # An exactly written figure starts at zero and may filter hard.
    assert (exact[0].lower, exact[0].upper) == (502, 502)
    assert exact[0].hard is True
    # „ca. 500" is precisely the claim that the value is not 500.
    assert rounded[0].lower == 495
    assert not any(rung.hard for rung in rounded)
    # A lower bound is not a band, and a stated range is taken literally.
    assert bound[0].lower == 450 and len(bound) == 1
    assert (span[0].lower, span[0].upper) == (450, 600)


def test_an_area_with_no_number_produces_no_rungs():
    assert tolerance_ladder(None) == []


# --------------------------------------------------------------------------
# Scoring: it orders, it never removes
# --------------------------------------------------------------------------


def test_a_parcel_without_an_address_is_not_demoted_for_it():
    """„ohne Lage“ is missing data, not a contradiction.

    Measured: 577 of the 1 131 parcels in Gemarkung Großbothen carry it, and
    the parcel actually being sold is one of them. A street filter that reads
    the gap as a "no" deletes the right answer.
    """

    hit, name = street_match("Wiesenstraße 12", "Wiesenstraße")
    gap, gap_name = street_match("ohne Lage", "Wiesenstraße")

    assert hit == 1.0 and name == "Wiesenstraße 12"
    # It contributes nothing -- and, crucially, is not reported as a mismatch.
    assert gap_name is None and gap > 0


def test_land_use_ranks_and_never_excludes():
    building, kind = land_use("Wohnbaufläche;502")
    road, road_kind = land_use("Straßenverkehr;1062")

    assert building == 1.0 and kind == "Wohnbaufläche"
    assert road_kind == "Straßenverkehr"
    # A carriageway sinks; it does not vanish, because "Baugrundstück means
    # Wohnbaufläche" is an inference and only official facts may exclude.
    assert 0 < road < building


def test_the_right_parcel_outranks_its_neighbour_on_recorded_data():
    """790/11 at 502 m² against 238/3 at 500 m², both real."""

    parcels = {p.attributes["flstnrzae"]: p for p in parse_feature_collection(
        fixture_bytes("alkis_grossbothen_band.gml")
    )}

    right, _ = score(parcels["790"], stated_area=502, street="Wiesenstraße")
    neighbour, _ = score(parcels["238"], stated_area=502, street="Wiesenstraße")

    assert right > neighbour


# --------------------------------------------------------------------------
# The common envelope
# --------------------------------------------------------------------------


def test_the_envelope_names_the_district_when_the_parcel_is_open():
    parcels = parse_feature_collection(fixture_bytes("alkis_grossbothen_band.gml"))

    huelle = common_envelope(parcels)

    assert huelle.art == "gemarkung"
    assert "Großbothen" in huelle.text
    assert huelle.geometry is not None


def test_the_envelope_names_the_parcel_when_there_is_only_one():
    parcels = parse_feature_collection(fixture_bytes("alkis_grossbothen_790_11.gml"))

    huelle = common_envelope(parcels)

    assert huelle.art == "flurstueck"
    assert "790/11" in huelle.text


def test_a_shared_street_is_only_claimed_when_every_candidate_carries_one():
    """One parcel addressed and one „ohne Lage“ share no street.

    Claiming one anyway would be inventing an answer out of a gap -- and the
    recorded pair is exactly that mix.
    """

    parcels = parse_feature_collection(fixture_bytes("alkis_grossbothen_band.gml"))

    assert common_envelope(parcels).art != "strasse"


# --------------------------------------------------------------------------
# The run itself
# --------------------------------------------------------------------------


@respx.mock
def test_a_district_and_a_number_stop_after_two_requests(client: TestClient):
    """The happy case takes the short circuit and does nothing else."""

    route = respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_790_11.gml"})
    )

    events = _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11", "flaeche_m2": 502,
         "flaeche_text": "502 m²"},
    )

    final = events[-1]
    assert final["art"] == "ergebnis"
    assert final["status"] == "bestaetigt"
    assert final["anfragen"] == 2
    assert route.call_count == 2
    # No staircase ran at all.
    assert not any(event.get("phase") == "treppe" for event in events)


@respx.mock
def test_a_contested_district_is_settled_by_the_parcel_number(client: TestClient):
    """Four districts, one number: the cadastre answers the question.

    Measured -- 790/11 exists in Großbothen and in none of Grimma, Höfgen
    (144245) or Höfgen (146132) -- so no relation extraction and no model call
    is needed, and the user is never asked.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "144241": "alkis_grossbothen_790_11.gml"})
    )

    events = _stream(
        client,
        {
            "text": LISTING,
            "flaeche_m2": 502,
            "flaeche_text": "502 m²",
            "indizien": [
                Indiz(
                    id="ocr1", art="flurstueck", wert="790/11",
                    text="Flurstück 790/11 auf dem Katasterauszug",
                    beleg="Titelzeile des Auszugs", quelle="bild", sicherheit=0.95,
                ).model_dump(mode="json")
            ],
        },
    )

    conflicts = [event["konflikt"] for event in events if event["art"] == "konflikt"]
    assert conflicts, "the three district names must be reported as a conflict"
    # Reported first as open, then as settled -- the map has to see both.
    assert conflicts[0].get("aufgeloest_durch") is None
    assert "Großbothen" in conflicts[-1]["aufgeloest_durch"]
    assert events[-1]["status"] == "bestaetigt"


@respx.mock
def test_the_user_can_choose_which_reading_applies(client: TestClient):
    """A decision restricts the search rather than merely reordering the list.

    The whole point of showing a conflict is that answering it changes what
    happens next. Without this the choice would be decoration.
    """

    payload = {"text": LISTING, "flaeche_m2": 502, "flaeche_text": "502 m²",
               "flurstuecksnummer": "790/11"}
    # Whichever id the reading gives Höfgen, choosing it must be what is asked.
    hoefgen = next(
        indiz
        for indiz in collect_indicia(directory=DIRECTORY, **payload)
        if indiz.art == "gemarkung" and indiz.wert == "Höfgen"
    )

    route = respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))
    _stream(client, {**payload, "entscheidungen": {"gemarkung": hoefgen.id}})

    asked = "".join(call.request.content.decode("utf-8") for call in route.calls)
    # Only the chosen reading is queried. Großbothen -- which the search would
    # otherwise have ranked first -- is never asked about. Of the two Höfgen
    # only the one in Grimma is asked, because the text names that municipality
    # and the directory knows which Höfgen belongs to it.
    assert "144245" in asked
    assert "144241" not in asked


@respx.mock
def test_the_staircase_stops_at_the_first_rung_that_answers(client: TestClient):
    """No parcel number: exact area, four districts, one hit."""

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            # Großbothen holds the parcel of exactly this size; the Höfgen the
            # text also names holds parcels, but none of them that size.
            counts={"144241+502": 1, "144245+502": 0, "144241": 1131, "144245": 812},
            features={"144241+502": "alkis_grossbothen_790_11.gml",
                      "144241": "alkis_grossbothen_band.gml",
                      "KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml"},
        )
    )

    events = _stream(client, {"text": LISTING, "flaeche_m2": 502, "flaeche_text": "502 m²"})

    # The place named as distant never becomes a place to search in.
    assert not any(
        e["art"] == "phase" and "Grimma" in (e.get("text") or "") for e in events
    )
    # The map is given the districts in play before any candidate exists.
    areas = next(e for e in events if e["art"] == "gebiete")
    assert areas["gebiete"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")

    rungs = [e["text"] for e in events if e.get("phase") == "treppe"]
    # Five rungs are planned; only the first is ever asked for.
    assert any("exakt" in text for text in rungs)
    assert not any("±0,5" in text for text in rungs)
    check = next(e for e in events if e.get("phase") == "gegenprobe")
    assert "können den Treffer nicht kippen" in check["text"]
    assert events[-1]["status"] == "bestaetigt"


@respx.mock
def test_a_rounded_area_alone_is_never_confirmed(client: TestClient):
    """„ca. 500 m²“ leaves no hard filter, so one survivor is still ambiguous.

    Nothing official picked this parcel -- a tolerance somebody chose did -- and
    a run that calls that "bestätigt" is a run that will eventually be
    confidently wrong.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            counts={"144241": 2},
            features={"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                      "144241": "alkis_grossbothen_790_11.gml"},
        )
    )

    events = _stream(
        client,
        {"gemarkung": "144241", "text": "Baugrundstück von ca. 500 m² in Großbothen.",
         "flaeche_text": "ca. 500 m²"},
    )

    assert events[-1]["status"] == "mehrdeutig"


@respx.mock
def test_a_number_that_contradicts_the_stated_area_is_not_confirmed(client: TestClient):
    """The short circuit checks before it stops.

    790/11 measures 502 m². A listing that says 2 000 m² is describing another
    plot, or the number was misread -- either way the run may not report a hit.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_790_11.gml"})
    )

    events = _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11", "flaeche_m2": 2000,
         "flaeche_text": "2000 m²"},
    )

    final = events[-1]
    assert final["status"] == "mehrdeutig"
    assert "widersprechen sich" in final["text"]


@respx.mock
def test_an_upstream_failure_travels_as_a_line_of_the_stream(client: TestClient):
    """Headers are long gone by then, so an error cannot be a status code."""

    respx.post(ALKIS_URL).mock(return_value=httpx.Response(500, text="kaputt"))

    events = _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11"},
    )

    assert events[-1]["art"] == "fehler"
    assert events[-1]["text"]


@respx.mock
def test_the_complete_endpoint_answers_the_same_run_in_one_object(client: TestClient):
    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_790_11.gml"})
    )

    answer = client.post(
        "/api/parcels/search/complete",
        json={"gemarkung": "Großbothen", "flurstuecksnummer": "790/11"},
    )

    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "bestaetigt"
    assert body["huelle"]["art"] == "flurstueck"
    assert body["kandidaten"][0]["properties"]["flurstuecksnummer"] == "790/11"
    assert body["gemarkung_umriss"]["type"] in ("Polygon", "MultiPolygon")


def test_a_search_with_nothing_to_go_on_is_refused_in_german(client: TestClient):
    answer = client.post("/api/parcels/search", json={})

    assert answer.status_code == 422
    assert "mindestens eine Angabe" in answer.json()["detail"]


def test_the_request_carries_no_contact_details():
    """The schema cannot hold a name or a phone number, so none can be stored."""

    fields = set(ParcelSearchRequest.model_fields)

    assert not fields & {"name", "telefon", "anbieter", "makler", "email"}


@respx.mock
def test_a_number_without_a_denominator_is_narrowed_by_the_area(client: TestClient):
    """„238“ alone also finds 238/3. The area settles it, and costs nothing.

    Both parcels arrive in one answer with their official areas, so this is a
    rule applied to what is already in hand rather than another request.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_band.gml"})
    )

    events = _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790", "flaeche_m2": 502,
         "flaeche_text": "502 m²"},
    )

    final = events[-1]
    assert final["status"] == "bestaetigt"
    assert [c["properties"]["flurstuecksnummer"] for c in final["kandidaten"]] == ["790/11"]
    assert any("exakten Fläche" in (e.get("text") or "") for e in events)


@respx.mock
def test_several_numbers_from_one_source_are_a_plot_and_not_a_dispute(client: TestClient):
    """„Flurstück 790/11 sowie 238/3“ is one plot made of two.

    A plot is a set of parcels -- the normal case in this project, not the
    exception -- so asking which of the two is meant would be asking a question
    that is not there.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_band.gml"})
    )

    events = _stream(
        client,
        {"gemarkung": "Großbothen",
         "text": "Verkauft werden Flurstück 790/11 sowie Flurstück 238/3 in Großbothen."},
    )

    assert not [e for e in events if e["art"] == "konflikt" and e["konflikt"]["art"] == "flurstueck"]
    assert "besteht oft aus mehreren" in events[-1]["text"]


@respx.mock
def test_numbers_from_different_sources_are_a_dispute(client: TestClient):
    """An image naming one parcel and the text another is a real contradiction."""

    respx.post(ALKIS_URL).mock(side_effect=[_gml("alkis_grossbothen_band.gml")] * 6)

    events = _stream(
        client,
        {
            "gemarkung": "Großbothen",
            "text": "Baugrundstück, Flurstück 238/3 in Großbothen.",
            "indizien": [
                Indiz(
                    id="ocr1", art="flurstueck", wert="790/11",
                    text="Flurstück 790/11 auf dem Katasterauszug",
                    beleg="Titelzeile des Auszugs", quelle="bild", sicherheit=0.95,
                ).model_dump(mode="json")
            ],
        },
    )

    conflicts = [e["konflikt"] for e in events if e["art"] == "konflikt"]
    assert any(conflict["art"] == "flurstueck" for conflict in conflicts)


# --------------------------------------------------------------------------
# Reading the listing's images
#
# Both fixtures are real images from the reference advert, downloaded on
# 05.09.2026: one Geoportal print and one photograph of the plot. The pair is
# the whole argument for reading every image and filtering by pattern rather
# than classifying images first -- and the photograph is the more important of
# the two, because a false parcel number is the one failure validating against
# ALKIS cannot catch.
# --------------------------------------------------------------------------

_HAS_TESSERACT = ocr.available()
_needs_tesseract = pytest.mark.skipif(
    not _HAS_TESSERACT, reason="Tesseract ist auf diesem Rechner nicht installiert"
)


@_needs_tesseract
def test_the_cadastral_extract_gives_up_its_parcel_number():
    reading = ocr.read_image(fixture_bytes("inserat-katasterauszug.jpg"))

    assert reading.parcels == ["790/11"]
    # The first pass is enough for an upright sheet; the second only runs when
    # nothing matched, and here it never has to.
    assert reading.modes == ["6"]
    assert "Wiesenstraße" in reading.text


@_needs_tesseract
def test_a_photograph_of_the_plot_invents_no_parcel_number():
    reading = ocr.read_image(fixture_bytes("inserat-grundstuecksfoto.jpg"))

    assert reading.parcels == []
    assert reading.districts == []
    # Both passes ran and neither matched, which is the expensive-but-correct
    # outcome: an empty answer is harmless, a plausible wrong one is not.
    assert reading.modes == ["6", "1"]


def test_a_misread_number_never_leaves_the_reader():
    """The 7-degree misreading, as text: „Flurstück 790717“."""

    good, _ = ocr.patterns("Untertitel: Flurstück 790/11")
    garbled, _ = ocr.patterns("Untertitel: Flurstück 790717")

    assert good == ["790/11"]
    assert garbled == []


def test_the_authoritys_own_district_line_is_not_read_as_the_plots():
    _, districts = ocr.patterns(
        "Gemarkung Großbothen\nStaatsbetrieb Geobasisinformation, Gemarkung Dresden"
    )

    assert districts == ["Großbothen"]


def test_a_listing_image_is_enlarged_before_it_is_read():
    """What a portal serves is smaller than what the reader wants.

    Measured on the reference advert: Kleinanzeigen's largest variant is
    678 x 960 for the cadastral print and 960 x 720 for a photograph -- both
    under the 1 500 px the measurements call for, so the upscale that repaired
    a 7 degree tilt and a 180 degree flip runs on real input every time rather
    than being the exception it looked like.
    """

    from PIL import Image

    original = fixture_bytes("inserat-katasterauszug.jpg")
    with Image.open(io.BytesIO(original)) as before:
        assert max(before.size) < ocr.TARGET_LONG_EDGE

    with Image.open(io.BytesIO(ocr.upscale(original))) as after:
        assert max(after.size) == ocr.TARGET_LONG_EDGE

    # Anything already large enough is handed on untouched.
    assert ocr.upscale(original, target=100) is original


@respx.mock
def test_the_images_are_left_unread_once_the_text_has_settled_it(client: TestClient):
    """A listing the text already confirmed is not worth three seconds an image."""

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "144241": "alkis_grossbothen_790_11.gml"})
    )
    images = respx.get("https://bilder.example.org/1.jpg").mock(
        return_value=httpx.Response(200, content=fixture_bytes("inserat-katasterauszug.jpg"))
    )

    _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11",
         "bilder": ["https://bilder.example.org/1.jpg"]},
    )

    assert images.call_count == 0


@respx.mock
@_needs_tesseract
def test_a_cadastral_extract_answers_a_listing_whose_text_does_not(client: TestClient):
    """The whole chain: image to parcel number to a confirmed parcel."""

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "144241": "alkis_grossbothen_790_11.gml"})
    )
    respx.get("https://bilder.example.org/1.jpg").mock(
        return_value=httpx.Response(200, content=fixture_bytes("inserat-katasterauszug.jpg"))
    )

    events = _stream(
        client,
        {"text": "Baugrundstück am Ortsrand von Großbothen. 502 m².",
         "flaeche_text": "502 m²",
         "bilder": ["https://bilder.example.org/1.jpg"]},
    )

    read = [e["indiz"] for e in events if e["art"] == "indiz" and e["indiz"]["quelle"] == "bild"]
    assert [i["wert"] for i in read] == ["790/11"]
    # The Beleg is the line it was read from -- an Indiz whose evidence cannot
    # be looked at is one nobody can resolve a contradiction with.
    assert "Flurstück 790/11" in read[0]["beleg"]
    assert events[-1]["status"] == "bestaetigt"


@respx.mock
@_needs_tesseract
def test_the_images_come_after_the_text_and_not_before_it(client: TestClient):
    """Reading the pictures used to be phase 0.

    So every run began with a Tesseract pass of up to a few seconds an image —
    in front of the first thing the map could draw, for a channel most listings
    do not even have. The text and the metadata are what the search runs on.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "144241": "alkis_grossbothen_790_11.gml"})
    )
    respx.get("https://bilder.example.org/1.jpg").mock(
        return_value=httpx.Response(200, content=fixture_bytes("inserat-katasterauszug.jpg"))
    )

    events = _stream(
        client,
        {"text": "Baugrundstück am Ortsrand von Großbothen. 502 m².",
         "flaeche_text": "502 m²",
         "bilder": ["https://bilder.example.org/1.jpg"]},
    )

    phases = [e.get("phase") for e in events if e["art"] == "phase"]
    first_image = phases.index("bilder")
    # Everything the text can do has happened by then: the clues are out and
    # the cadastre has been asked.
    assert "ernten" in phases[:first_image]
    assert any(p in ("raum", "treppe", "kurzschluss") for p in phases[:first_image])

    kinds = [e["art"] for e in events]
    first_text_indiz = kinds.index("indiz")
    image_phase_at = next(
        i for i, e in enumerate(events) if e["art"] == "phase" and e.get("phase") == "bilder"
    )
    assert first_text_indiz < image_phase_at


@respx.mock
def test_a_server_without_tesseract_says_so_instead_of_going_quiet(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ocr, "available", lambda: False)
    respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))

    events = _stream(
        client,
        {"text": "Baugrundstück in Großbothen.", "bilder": ["https://bilder.example.org/1.jpg"]},
    )

    said = [e["text"] for e in events if e.get("phase") == "bilder"]
    assert said and "keine Texterkennung eingerichtet" in said[0]


# --------------------------------------------------------------------------
# Four adverts that did not work, and what each one taught
# --------------------------------------------------------------------------


def _indicia_of(key: str):
    listing = LISTINGS[key]
    return collect_indicia(
        titel=listing["titel"],
        text=listing["beschreibung"],
        adresse=listing["ort"],
        flaeche_text=listing["angaben"].get("Grundstücksfläche"),
        lat=listing["lat"],
        lon=listing["lon"],
        directory=DIRECTORY,
    )


def _engine_of(key: str) -> SearchEngine:
    listing = LISTINGS[key]
    engine = SearchEngine(
        ParcelSearchRequest(
            titel=listing["titel"],
            text=listing["beschreibung"],
            adresse=listing["ort"],
            flaeche_text=listing["angaben"].get("Grundstücksfläche"),
        ),
        alkis_service(),
        DIRECTORY,
    )
    engine.state.indicia = _indicia_of(key)
    return engine


def _anchor_names(key: str) -> list[str]:
    return [f"{a.name}/{a.schluessel}" for a in _engine_of(key).anchors()]


def test_ortsteil_names_the_district_and_the_municipality_in_one_breath():
    """„im malerischen Ortsteil Plagwitz von Machern“ — both, one level apart."""

    indicia = _indicia_of("3375124391")
    districts = [i for i in indicia if i.art == "gemarkung" and i.beziehung == "liegt_in"]
    municipalities = [i.wert for i in indicia if i.art == "gemeinde"]

    assert [i.wert for i in districts] == ["Plagwitz"]
    assert "Machern" in municipalities


def test_the_generic_word_in_front_of_a_municipality_is_not_part_of_its_name():
    """„ein kleiner Ortsteil der Kreisstadt Borna" names Borna.

    Measured 18.09.2026: the Gemeinde Indizien carried „Kreisstadt Borna" and
    „Stadt Sandersdorf-Brehna", and neither can match anything in ALKIS. It was
    the model channel that showed it — the same sentences came back from a
    model as „Borna" and „Brehna", which is exactly what the divergence log is
    for.
    """

    indicia = _indicia_of("2418686487")
    placing = {i.wert for i in indicia if i.art == "gemeinde" and i.beziehung == "liegt_in"}
    # A set: the location field and the sentence both name it, which is two
    # Indizien of one value and a separate question.
    assert placing == {"Borna"}
    # And nothing anywhere still carries the article's noun.
    assert not [i for i in indicia if i.wert.lower().startswith(("stadt ", "kreisstadt "))]


def test_a_municipality_only_mentioned_neither_filters_nor_anchors():
    """`anchors` has filtered Gemarkung Indizien on the relation since „Anbindung
    an Leipzig" put Gemarkung Leipzig up next to Lobstädt. The municipality did
    not, so a Gemeinde Indiz without a placing relation still narrowed the
    anchors to itself — and a model may report exactly that: „Leipzig,
    entfernt_von"."""

    engine = SearchEngine(
        ParcelSearchRequest(text="Baugrundstück in Lobstädt."), alkis_service(), DIRECTORY
    )
    engine.state.indicia = [
        Indiz(
            id="a",
            art="gemarkung",
            wert="Lobstädt",
            text="…",
            quelle="fliesstext",
            beziehung="liegt_in",
            sicherheit=0.6,
        ),
        Indiz(
            id="b",
            art="gemeinde",
            wert="Leipzig",
            text="…",
            quelle="modell",
            beziehung="entfernt_von",
            sicherheit=0.2,
        ),
    ]

    assert engine.municipalities() == []
    assert [a.name for a in engine.anchors()] == ["Lobstädt"]


def test_a_city_the_text_only_mentions_is_not_offered_as_a_gemarkung():
    """„Anbindung an Leipzig" is a sentence about transport.

    There *is* a Gemarkung Leipzig, so the name resolves and the Indiz used to
    be emitted at that level — fourteen times over the recorded corpus, with
    Groitzsch, Borna, Bad Lausick, Chemnitz and Taucha once each, and a model
    read every one of them as the municipality. Where the sentence does not
    place the plot, the level is not the lookup's to decide.
    """

    indicia = collect_indicia(
        text="Baugrundstück in Lobstädt. Gute Anbindung an Leipzig.",
        directory=DIRECTORY,
    )
    by_name = {i.wert: i for i in indicia}
    assert by_name["Leipzig"].art == "gemeinde"
    assert by_name["Leipzig"].beziehung == "erwaehnt"
    # The district it does place the plot in is untouched.
    assert (by_name["Lobstädt"].art, by_name["Lobstädt"].beziehung) == (
        "gemarkung",
        "liegt_in",
    )


def test_a_municipality_that_is_also_the_district_survives_being_named():
    """„Ihr neues Wohngrundstück in Groitzsch" places the plot, and Groitzsch is
    a municipality *and* the cadastral district meant. The rule above must not
    reach it — which is why it asks about the relation first."""

    indicia = collect_indicia(
        text="Ihr neues Wohngrundstück in Bad Lausick", directory=DIRECTORY
    )
    lausick = next(i for i in indicia if i.wert == "Bad Lausick")
    assert (lausick.art, lausick.beziehung) == ("gemarkung", "liegt_in")


def test_a_name_that_is_a_generic_word_keeps_it():
    """Stadt Wehlen is a town called Stadt Wehlen, and the directory says so
    itself: it lists the place as „Stadt Stadt Wehlen", the column's word in
    front of a name that begins with the same word. Strip one and the name is
    left; strip greedily and it is not."""

    assert municipality_spelling(DIRECTORY, "Stadt Stadt Wehlen") == "Stadt Wehlen"
    assert municipality_spelling(DIRECTORY, "Stadt Wehlen") == "Stadt Wehlen"
    assert municipality_name(DIRECTORY, "Stadt Wehlen") == "Stadt Wehlen"
    # And the ordinary case, from both directions.
    assert municipality_name(DIRECTORY, "Kreisstadt Borna") == "Borna"
    assert municipality_name(DIRECTORY, "Stadt Borna") == "Borna"
    assert municipality_name(DIRECTORY, "Borna") == "Borna"
    # „Borna" must not match „Bornaer Land".
    assert municipality_spelling(DIRECTORY, "Bornaer Land") is None


def test_a_municipality_outside_saxony_still_loses_the_generic_word():
    """The directory cannot confirm Sandersdorf-Brehna, and „Stadt
    Sandersdorf-Brehna" is not a name any register carries either."""

    assert municipality_name(DIRECTORY, "Stadt Sandersdorf-Brehna") == "Sandersdorf-Brehna"
    assert municipality_name(None, "Kreisstadt Borna") == "Borna"


def test_the_municipality_tells_two_districts_of_one_name_apart():
    """There are two Gemarkungen called Plagwitz. Only one is in Machern.

    Nothing used the directory's own ``gemeinde`` column before, and it is what
    turned this advert from two candidates into one.
    """

    assert _anchor_names("3375124391") == ["Plagwitz/148642"]


def test_a_common_noun_that_is_also_a_district_is_not_searched():
    """„geprägt von Wiesen und Feldern“ — German capitalises every noun.

    A bare directory match is not a statement about where the plot is. It stays
    in the protocol as weak evidence and costs no request.
    """

    mentioned = {i.wert: i for i in _indicia_of("3375124391") if i.art == "gemarkung"}

    assert "Wiesen" in mentioned
    assert mentioned["Wiesen"].beziehung == "erwaehnt"
    assert "Wiesen/148950" not in _anchor_names("3375124391")


def test_a_connection_to_a_city_is_not_a_location_in_it():
    """„gute Anbindung an Leipzig“ put Gemarkung Leipzig up as an anchor.

    Leipzig holds parcels of every size, so it produced two false candidates of
    exactly the stated area next to the right one.
    """

    assert _anchor_names("3423861748") == ["Lobstädt/141894"]


def test_the_locality_field_gives_up_its_municipality():
    """The pin derived from it is 6 km out; the name it was geocoded from is not."""

    for key, expected in (
        ("3499632623", "Grimma"),
        ("3375124391", "Machern"),
        ("3423861748", "Neukieritzsch"),
        ("3503721553", "Bad Lausick"),
    ):
        from_field = [
            i.wert for i in _indicia_of(key) if i.art == "gemeinde" and i.quelle == "standortfeld"
        ]
        assert from_field == [expected], key


def test_the_portals_own_area_field_is_the_one_that_counts():
    """A title may hedge („ca. 1.025qm“) where the attribute list does not."""

    listing = LISTINGS["3423861748"]

    assert "ca." in listing["titel"]
    assert listing["angaben"]["Grundstücksfläche"] == "1.025 m²"
    assert tolerance_ladder(read_area(listing["angaben"]["Grundstücksfläche"]))[0].hard


@respx.mock
def test_an_exact_area_widens_the_place_before_it_widens_the_number(client: TestClient):
    """„1.076 m² in Bad Lausick“ has no match in Gemarkung Bad Lausick.

    It has exactly one in the *municipality*: Flurstück 502/47 in Gemarkung
    Etzoldshain, at „Am Kurpark" — which is what the advert is titled after.
    An exactly stated area is an official fact and a Gemarkung read out of
    prose is not, so it is the guess that gives way.
    """

    listing = LISTINGS["3503721553"]
    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            # Nothing that size in the district; one in the municipality. The
            # municipality key is the one the recorded parcel carries -- the
            # search learns it from any parcel of the district, which is the
            # single extra request this step costs.
            counts={"143836+1076": 0, "14729010+1076": 1, "143836": 2363},
            features={"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                      "14729010+1076": "alkis_etzoldshain_502_47.gml",
                      "143836": "alkis_etzoldshain_502_47.gml"},
        )
    )

    events = _stream(
        client,
        {"titel": listing["titel"], "text": listing["beschreibung"], "adresse": listing["ort"],
         "flaeche_text": listing["angaben"]["Grundstücksfläche"]},
    )

    widened = [e for e in events if e.get("phase") == "gemeinde"]
    assert widened, "the municipality was never tried"
    assert "kein Flurstück dieser Größe" in widened[0]["text"]
    assert events[-1]["status"] == "bestaetigt"
    found = events[-1]["kandidaten"][0]["properties"]
    assert (found["flurstuecksnummer"], found["gemarkung"]) == ("502/47", "Etzoldshain")
    assert found["lagebezeichnung"] == "Am Kurpark"
    # The tolerance was never opened: what gave way is the place.
    assert not any("±0,5" in (e.get("text") or "") for e in events)


def test_the_listing_page_yields_its_description_and_not_the_portal_around_it():
    """The whole page is navigation, cookie banner and category tree.

    Reading all of it as evidence is what put „Alle Kategorien" next to the one
    sentence that names the Ortsteil.
    """

    from app.services.portals import parse_page

    seite = parse_page("https://www.kleinanzeigen.de/x", fixture_text("inserat-kleinanzeigen.html"))

    assert seite.beschreibung and len(seite.beschreibung) < 4000
    assert "Ortsteil Lobstädt bei Neukieritzsch" in seite.beschreibung
    assert "Alle Kategorien" not in seite.beschreibung
    assert seite.angaben["Grundstücksfläche"] == "1.025 m²"
    # One URL per picture, not the six sizes each is served at.
    assert 0 < len(seite.bilder) <= 8
    assert len(set(seite.bilder)) == len(seite.bilder)


@respx.mock
def test_the_districts_are_drawn_before_the_clues_are_narrated(client: TestClient):
    """The map used to sit on the whole state while the list named a village.

    The clues play one at a time so a run can be followed, and the districts
    were emitted after all of them — so for the first seconds the map showed
    nothing at all, which reads as a map that is broken rather than one that is
    waiting. Nothing extra is fetched: it is the same request, one step earlier.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_790_11.gml"})
    )

    events = _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11", "flaeche_m2": 502,
         "flaeche_text": "502 m²"},
    )

    kinds = [event["art"] for event in events]
    assert "gebiete" in kinds
    assert kinds.index("gebiete") < kinds.index("indiz")


@_needs_tesseract
def test_a_garbled_label_still_gives_up_its_parcel_number():
    """The Borna advert's Liegenschaftskarte, read as the reader really reads it.

    Tesseract returns „Fiurstück: 107/60“ — the l as an i — so the one number
    on the sheet that means anything was thrown away while the Gemarkung beside
    it was read correctly. The rest of the word carries the specificity, so
    tolerating the confusion costs no precision.
    """

    reading = ocr.read_image(fixture_bytes("inserat-liegenschaftskarte.jpg"))

    assert reading.parcels == ["107/60"]
    # „Thräna“ without its umlaut; the directory folds diacritics, so that is
    # not a problem — the *label* being unreadable would have been.
    assert reading.districts == ["Thrana"]
    assert "Fiurstück" in reading.text


def test_the_loosened_label_does_not_start_matching_prose():
    for text in ("Fust 12/3", "First 12", "Die Flur ist 12 ha groß", "Furst 40"):
        assert ocr.patterns(text)[0] == [], text
    for text in ("Fiurstück: 107/60", "F1urstück 85/1", "Flurstück 790/11"):
        assert ocr.patterns(text)[0], text


@_needs_tesseract
def test_the_neighbours_printed_all_over_the_sheet_are_not_read_as_the_plot():
    """That sheet carries dozens of numbers: 107/61, 107/13, 105/6, 74/3 …

    Only the title block is labelled, and only a labelled number is taken. The
    in-map labels come out as garbage anyway, which is the property that makes
    reading every image and filtering by pattern safe.
    """

    reading = ocr.read_image(fixture_bytes("inserat-liegenschaftskarte.jpg"))

    assert reading.parcels == ["107/60"]


# --------------------------------------------------------------------------
# A plot that has no Flurstück yet
# --------------------------------------------------------------------------


def test_a_part_area_is_recognised_from_the_advert_s_own_words():
    """„eine noch zu vermessende Teilfläche“ — the sentence, so it can be shown."""

    listing = LISTINGS["2418686487"]

    found = describes_part_area(listing["beschreibung"])

    assert found and "noch zu vermessende Teilfläche" in found


def test_a_pending_survey_is_not_read_into_a_finished_one():
    assert describes_part_area("Die Vermessung ist bereits erfolgt.") is None
    assert describes_part_area("Das Grundstück ist 502 m² groß.") is None


def test_a_part_area_s_size_may_not_filter():
    """748,50 m² is the size of a parcel that does not exist yet.

    Used as a hard filter it finds *some other* parcel of that size and calls it
    confirmed — the one kind of wrong answer this search is built to refuse.
    """

    exact = AreaStatement(value=748.5, wording="")
    assert exact.exact is True

    part = AreaStatement(value=748.5, wording="", part_of="noch zu vermessende Teilfläche")
    assert part.exact is False


@respx.mock
@_needs_tesseract
def test_the_borna_advert_answers_with_the_parcel_it_is_cut_from(client: TestClient):
    """The whole case, end to end.

    The advert names no parcel and its Liegenschaftskarte's title block reads
    „Fiurstück: 107/60“ — the l as an i. With that label understood the run
    resolves 107/60 in Gemarkung Thräna, and stops there: the plot is a part of
    it, so „bestätigt“ would be a claim about a parcel that does not exist yet.
    """

    listing = LISTINGS["2418686487"]
    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"flstnrzae": "alkis_thraena_107_60.gml"})
    )
    respx.get("https://bilder.example.org/1.jpg").mock(
        return_value=httpx.Response(200, content=fixture_bytes("inserat-liegenschaftskarte.jpg"))
    )

    events = _stream(
        client,
        {
            "titel": listing["titel"],
            "text": listing["beschreibung"],
            "adresse": listing["ort"],
            "flaeche_m2": 748.5,
            "flaeche_text": listing["angaben"]["Grundstücksfläche"],
            "bilder": ["https://bilder.example.org/1.jpg"],
        },
    )

    read = [e["indiz"] for e in events if e["art"] == "indiz" and e["indiz"]["quelle"] == "bild"]
    assert "107/60" in [i["wert"] for i in read]

    final = events[-1]
    # Not „bestätigt“: the stated size belongs to a parcel that does not exist.
    assert final["status"] == "mehrdeutig"
    assert "Teilfläche" in final["text"]
    assert "herausgemessen" in final["text"]
    # And the area mismatch is not reported as an objection — it is the point.
    assert "bitte die Flurstücksnummer prüfen" not in final["text"]


# --------------------------------------------------------------------------
# An advert outside Saxony — the sixth, and the one where finding something
# was the failure
# --------------------------------------------------------------------------


def test_the_location_field_names_the_federal_state():
    """All six recorded adverts carry it, and „Sachsen-Anhalt“ is not „Sachsen“."""

    assert federal_state("Sachsen-Anhalt - Brehna") == "Sachsen-Anhalt"
    assert federal_state("04668 Sachsen – Grimma") == "Sachsen"
    # A street with the state's name in it is not a statement about the state.
    assert federal_state("Am Sachsenplatz 3") is None
    assert federal_state(None) is None


def test_only_a_state_actually_named_stops_a_run():
    assert outside_saxony("Sachsen-Anhalt - Brehna") == "Sachsen-Anhalt"
    assert outside_saxony("Sachsen - Borna") is None
    # Absence is not evidence: a listing that names no state is searched.
    assert outside_saxony("04103 Leipzig") is None
    assert outside_saxony(None) is None


def test_an_amenity_is_somewhere_to_go_not_where_the_plot_is():
    """„weiterführende Schulen in Roitzsch“ — the schools are there, not the plot.

    Roitzsch is a real Gemarkung near Wurzen, ~100 km from the Brehna advert
    that sentence comes from, and it holds a parcel of exactly the stated
    600 m². Read as a location it produced that parcel as the answer.
    """

    indicia = _indicia_of("3381469778")
    roitzsch = [i for i in indicia if i.art == "gemarkung" and i.wert == "Roitzsch"]

    assert roitzsch and roitzsch[0].beziehung == "erwaehnt"


@respx.mock
def test_a_place_the_cadastre_does_not_know_is_not_offered_as_a_choice(
    client: TestClient,
):
    """Picking „Brehna“ re-ran the search with the same anchors and the same answer.

    A question whose answer changes nothing is worse than no question: it reads
    as a button that does not work.
    """

    listing = LISTINGS["3381469778"]
    respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))

    events = _stream(
        client,
        {
            "titel": listing["titel"],
            "text": listing["beschreibung"],
            "adresse": listing["ort"],
            "flaeche_text": listing["angaben"]["Grundstücksfläche"],
        },
    )

    brehna = next(
        e["indiz"] for e in events
        if e["art"] == "indiz" and e["indiz"]["art"] == "gemarkung" and e["indiz"]["wert"] == "Brehna"
    )
    assert brehna["verworfen"] is True
    assert "Gemarkungsverzeichnis" in brehna["verworfen_grund"]
    assert not [e for e in events if e["art"] == "konflikt"]


@respx.mock
def test_an_advert_outside_saxony_is_answered_without_asking_the_cadastre(
    client: TestClient,
):
    """Advert 3381469778 — 600 m² in Brehna, Sachsen-Anhalt.

    Before: eleven requests and Flurstück 50 in Gemarkung Roitzsch near Wurzen,
    a real parcel a hundred kilometres away that happens to measure 600 m².
    ALKIS is state-specific, so no request could have produced a right answer —
    and the listing says which state it is in.
    """

    listing = LISTINGS["3381469778"]
    route = respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))

    events = _stream(
        client,
        {
            "titel": listing["titel"],
            "text": listing["beschreibung"],
            "adresse": listing["ort"],
            "flaeche_m2": 600.0,
            "flaeche_text": listing["angaben"]["Grundstücksfläche"],
            "lat": listing["lat"],
            "lon": listing["lon"],
        },
    )

    final = events[-1]
    assert final["status"] == "erfolglos"
    assert final["anzahl"] == 0
    assert "Sachsen-Anhalt" in final["text"]
    # Not „die Angaben reichen nicht aus“: nothing the seller could add helps.
    assert "reichen nicht aus" not in final["text"]
    # And the cadastre was never asked — every answer it could give is somebody
    # else's parcel.
    assert route.call_count == 0
    assert final["anfragen"] == 0


@respx.mock
def test_prose_naming_another_state_explains_an_empty_run(client: TestClient):
    """The text path has no location field, and the prose still says where it is.

    A state read out of the body may never *stop* a run — „40 Minuten bis
    Sachsen-Anhalt" is a sentence about a Saxon plot. It may explain one that
    found nothing, and then „für eine Eingrenzung fehlt eine Ortsangabe" is the
    wrong thing to say: the location is stated plainly, it is simply not here.
    """

    listing = LISTINGS["3381469778"]
    respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))

    events = _stream(
        client,
        {
            "titel": listing["titel"],
            "text": listing["beschreibung"],
            "flaeche_m2": 600.0,
            "flaeche_text": listing["angaben"]["Grundstücksfläche"],
        },
    )

    final = events[-1]
    assert final["status"] == "erfolglos"
    assert "Sachsen-Anhalt" in final["text"]
    assert "Kaufvertrag" not in final["text"]


@respx.mock
def test_a_saxon_listing_that_merely_mentions_another_state_is_still_searched(
    client: TestClient,
):
    """The guard above must not fire on a plot that is here.

    „Anbindung an Sachsen-Anhalt" is a sentence about how well connected a
    Saxon plot is — the same trap „Anbindung an Leipzig" already taught.
    """

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            counts={"144241+502": 1, "144241": 1131},
            features={"144241+502": "alkis_grossbothen_790_11.gml",
                      "KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml"},
        )
    )

    events = _stream(
        client,
        {
            "titel": "Baugrundstück in Großbothen",
            "text": (
                "Das Grundstück liegt in Großbothen und ist 502 m² groß. "
                "Gute Anbindung nach Sachsen-Anhalt und Thüringen."
            ),
            "adresse": "Sachsen - Grimma",
            "flaeche_m2": 502.0,
            "flaeche_text": "502 m²",
        },
    )

    final = events[-1]
    assert final["status"] == "bestaetigt"
    assert "Sachsen-Anhalt" not in (final.get("text") or "")


# ---------------------------------------------------------------------------
# The pin as a seed for the anchor set
#
# The gap this closes: a Stadtteil is usually not a Gemarkung. „Grünau-Siedlung"
# in Leipzig is none, and the two Saxon Gemarkungen called „Grünau" are 80 km
# away in the Erzgebirge, so the name cannot be looked up and Stadt Leipzig's
# 76 districts are too many to ask one by one. The recording is the real answer
# to one BBOX request around the advert's own point
# (`alkis_katasterbezirke_gruenau.gml`, fetched 09.09.2026): seven districts,
# Lausen and Kleinzschocher among them.


@respx.mock
def test_the_pin_says_which_districts_to_ask_when_the_listing_names_none(client: TestClient):
    """One request turns a point into a set, and the area decides inside it.

    Not „the plot is here": the point is the platform's geocode of a place name
    and may sit kilometres off. It is only allowed to pick the districts that
    get asked — and the safety of that is one-directional, which is what lets
    the radius be chosen without a corpus: a box too small to contain the right
    district makes every count zero and the run reports nothing found. It can
    never turn a bad pin into a wrong parcel.
    """

    respx.get(ALKIS_URL).mock(
        side_effect=lambda request: _gml("alkis_katasterbezirke_gruenau.gml")
        if "KatasterBezirk" in request.url.query.decode()
        else _gml("alkis_leer.gml")
    )
    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            # Only Gemarkung Lausen holds a parcel of exactly that size.
            {"145573+742": 1},
            {"145573": "alkis_grossbothen_790_11.gml"},
        )
    )

    events = _stream(
        client,
        {
            "adresse": "04207 Leipzig, Sachsen",
            "text": "Wohnbaugrundstück im Leipziger Stadtteil Grünau-Siedlung.",
            "lat": 51.30595,
            "lon": 12.27605,
            "flaeche_m2": 742,
            "flaeche_text": "742 m²",
        },
    )

    said = " ".join(event.get("text") or "" for event in events)
    assert "Die Anzeige nennt keine Gemarkung" in said
    assert "Gemarkungen" in said
    # The sentence has to say what the point is worth, or the run reads as
    # though the pin located the plot.
    assert "nicht das Grundstück" in said

    final = events[-1]
    assert final["art"] == "ergebnis"
    # Never „bestätigt" off a pin: the anchor is not an official statement
    # about this plot, so one survivor is a single candidate, not a verdict.
    assert final["status"] != "bestaetigt"


@respx.mock
def test_a_pin_is_not_asked_when_the_listing_names_a_district(client: TestClient):
    """The cheap route stays the route. A district in the text is a statement;
    the pin is a geocode, and asking it anyway would spend a request to make
    the answer weaker."""

    districts = respx.get(ALKIS_URL).mock(
        side_effect=lambda request: _gml("alkis_katasterbezirke_gruenau.gml")
    )
    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre({}, {"KatasterBezirk": "alkis_katasterbezirk_grossbothen.gml",
                                   "flstnrzae": "alkis_grossbothen_790_11.gml"})
    )

    _stream(
        client,
        {"gemarkung": "Großbothen", "flurstuecksnummer": "790/11", "flaeche_m2": 502,
         "flaeche_text": "502 m²", "lat": 51.189265, "lon": 12.85},
    )

    assert districts.call_count == 0


@respx.mock
def test_a_pin_outside_saxony_asks_nothing(client: TestClient):
    """A box around a point in Sachsen-Anhalt would return Saxon districts on
    the border, and every one of them is a namesake trap. The run that already
    knows the state is wrong must not spend a request to find that out again."""

    districts = respx.get(ALKIS_URL).mock(
        side_effect=lambda request: _gml("alkis_katasterbezirke_gruenau.gml")
    )
    respx.post(ALKIS_URL).mock(side_effect=_cadastre({}, {}))

    _stream(
        client,
        {"adresse": "06796 Sachsen-Anhalt - Brehna", "text": "600 m² Baugrundstück in Brehna.",
         "lat": 51.5852, "lon": 12.2478, "flaeche_m2": 600, "flaeche_text": "600 m²"},
    )

    assert districts.call_count == 0


# --------------------------------------------------------------------------
# A fifth advert: the location field states the Ortsteil, and it is a compound
# --------------------------------------------------------------------------
#
# ImmoScout advert 170438443, read 09.09.2026: „Burghausen-Rückmarsdorf, 04178
# Leipzig“ in the location field, 866 m² exactly, and prose that names the
# Ortsteil twice more. The field was read as one opaque line, so the run had no
# cadastral anchor at all and fell back to the whole of Stadt Leipzig: 31
# candidates spread over the city, where the Ortsteil holds exactly two parcels
# of that size.

BURGHAUSEN = "Burghausen-Rückmarsdorf, 04178 Leipzig, Sachsen"


def _field(adresse: str, text: str | None = None):
    return collect_indicia(adresse=adresse, text=text, directory=DIRECTORY)


def _places(indicia, art: str) -> list[str]:
    return [i.wert for i in indicia if i.art == art]


def test_the_location_field_names_the_district_in_front_of_the_postcode():
    """Five digits are the only fixed point in a German location line.

    Behind them stands the municipality, in front of them the Ortsteil — and
    ImmoScout puts its own `obj_regio4` there. Reading the line as one string
    threw both away.
    """

    found = _field(BURGHAUSEN)

    assert _places(found, "gemeinde") == ["Leipzig"]
    assert _places(found, "gemarkung") == ["Burghausen", "Rückmarsdorf"]


def test_a_compound_ortsteil_is_taken_apart_into_its_gemarkungen():
    """„Burghausen-Rückmarsdorf“ is no Gemarkung; both its halves are.

    Measured against all 63 Leipzig Ortsteile: every compound resolves to its
    own Gemarkungen and none to a namesake elsewhere.
    """

    keys = {i.wert: i.schluessel for i in _field(BURGHAUSEN) if i.art == "gemarkung"}

    assert keys == {"Burghausen": "145507", "Rückmarsdorf": "145614"}


def test_a_compound_only_gives_up_the_halves_of_its_own_municipality():
    """„Grünau-Siedlung, 04207 Leipzig“ must contribute nothing.

    Gemarkung Grünau exists exactly twice, in Großolbersdorf and in
    Langenweißbach — both in the Erzgebirge or Vogtland, 80 km from the Leipzig
    plot. The municipality is what makes splitting safe, and here it refuses:
    „Lausen-Grünau“ keeps Lausen and drops Grünau in the same breath.
    """

    assert _places(_field("Grünau-Siedlung, 04207 Leipzig, Sachsen"), "gemarkung") == []
    assert _places(_field("Lausen-Grünau, 04207 Leipzig, Sachsen"), "gemarkung") == ["Lausen"]


def test_the_prose_names_the_compound_too_and_is_read_the_same_way():
    """„in Leipzig – Stadtteil Burghausen-Rückmarsdorf“.

    A clipboard copy of an ImmoScout page brings the two prose blocks and no
    title, so the Ortsteil has to be readable out of the sentence as well as
    out of the field.
    """

    found = _field(
        "04178 Leipzig, Sachsen",
        "Verkauf eines attraktiven Baugrundstücks in Leipzig – Stadtteil "
        "Burghausen-Rückmarsdorf. Der Leipziger Ortsteil Burghausen-Rückmarsdorf "
        "befindet sich im Westen der Stadt.",
    )

    assert set(_places(found, "gemarkung")) >= {"Burghausen", "Rückmarsdorf"}


def test_one_indiz_per_district_however_often_the_name_stands_there():
    """The compound stands in the field and twice in the prose.

    Each occurrence names the same two Gemarkungen. The anchors were never
    affected — they are keyed by Gemarkungsschlüssel — but the Verlauf the user
    reads showed five rows for two claims.
    """

    found = _field(
        BURGHAUSEN,
        "Stadtteil Burghausen-Rückmarsdorf. Der Leipziger Ortsteil "
        "Burghausen-Rückmarsdorf liegt im Westen.",
    )
    districts = _places(found, "gemarkung")

    assert len(districts) == len(set(districts))


def test_the_municipality_is_not_a_rival_reading_of_the_district():
    """„in Leipzig – Stadtteil Burghausen-Rückmarsdorf“ names both levels.

    Gemarkung Leipzig holds parcels of every size, so leaving it as an anchor
    next to the two the Ortsteil names is what produced the 31.
    """

    found = _field(BURGHAUSEN, "Ein Baugrundstück in Leipzig, Stadtteil Burghausen-Rückmarsdorf.")
    leipzig = next(i for i in found if i.art == "gemarkung" and i.wert == "Leipzig")

    assert leipzig.beziehung == "erwaehnt"


def test_a_municipality_that_is_also_the_gemarkung_stays_an_anchor():
    """„Sachsen - Bad Lausick“ names one place, and it is both levels at once.

    Demoting it there leaves the run with no anchor at all — and that advert's
    area has no match in Gemarkung Bad Lausick and exactly one in the
    municipality, so the anchor is what the widening step hangs off.
    """

    found = _field("Sachsen - Bad Lausick", "Ein Grundstück in Bad Lausick.")
    district = next(i for i in found if i.art == "gemarkung" and i.wert == "Bad Lausick")

    assert district.beziehung == "liegt_in"


def test_a_street_in_front_of_the_postcode_is_not_a_district():
    """ohne-makler writes „Maschinenhausstraße, 01587 Riesa, Sachsen“."""

    found = _field("Maschinenhausstraße, 01587 Riesa, Sachsen")

    assert _places(found, "gemeinde") == ["Riesa"]
    assert _places(found, "gemarkung") == []


def test_the_field_without_a_postcode_is_still_read():
    """The recorded adverts carry „Sachsen - Machern“, with no postcode at all."""

    assert _places(_field("Sachsen - Machern"), "gemeinde") == ["Machern"]
    assert _places(_field("04668 Sachsen – Grimma"), "gemeinde") == ["Grimma"]
    assert _places(_field("06796 Sachsen-Anhalt - Brehna"), "gemeinde") == ["Brehna"]


def test_the_anchors_are_the_ortsteil_and_not_the_whole_city():
    """The 31, at the point where they were made.

    Without the Ortsteil the only anchor left was Gemarkung Leipzig, and with
    an exact area that has no match — so the run widened to the whole of Stadt
    Leipzig, where 112 589 Flurstücke hold 31 of exactly 866 m². The Ortsteil
    holds two, and both of them are in the answer.
    """

    engine = SearchEngine(
        ParcelSearchRequest(
            adresse=BURGHAUSEN,
            text="Verkauf eines Baugrundstücks in Leipzig – Stadtteil Burghausen-Rückmarsdorf.",
            flaeche_text="866 m²",
        ),
        alkis_service(),
        DIRECTORY,
    )
    engine.state.indicia = collect_indicia(
        adresse=BURGHAUSEN,
        text="Verkauf eines Baugrundstücks in Leipzig – Stadtteil Burghausen-Rückmarsdorf.",
        flaeche_text="866 m²",
        directory=DIRECTORY,
    )

    assert [f"{a.name}/{a.schluessel}" for a in engine.anchors()] == [
        "Burghausen/145507",
        "Rückmarsdorf/145614",
    ]


def test_the_halves_of_one_ortsteil_are_not_put_to_the_user_as_rivals():
    """„Stadtteil Burghausen-Rückmarsdorf“ is one statement, not two readings.

    Both Gemarkungen are searched and both survivors are in the answer, where
    the user picks a *parcel*. Asking „welche Gemarkung ist gemeint?“ calls the
    listing contradictory when nothing in it contradicts — the same rule as
    several parcel numbers from one source, which are a plot and not a dispute.
    """

    payload = ParcelSearchRequest(
        adresse=BURGHAUSEN,
        text="Baugrund in Rückmarsdorf. Stadtteil Burghausen-Rückmarsdorf.",
        flaeche_text="866 m²",
    )
    engine = SearchEngine(payload, alkis_service(), DIRECTORY)
    engine.state.indicia = collect_indicia(
        adresse=payload.adresse,
        text=payload.text,
        flaeche_text=payload.flaeche_text,
        directory=DIRECTORY,
    )

    districts = [i.wert for i in engine.state.indicia if i.art == "gemarkung"]
    assert set(districts) >= {"Burghausen", "Rückmarsdorf"}
    assert [k.art for k in engine._conflicts()] == []


def test_two_districts_that_came_from_two_names_still_disagree():
    """Großbothen against Höfgen is a real contradiction and stays a question.

    The suppression above turns on *one* compound having produced both readings.
    Two names read separately have no compound in common, so the Grimma
    advert's three districts are reported as a conflict exactly as before —
    asserted end to end in `test_three_district_names_are_a_conflict…` and here
    at the condition itself.
    """

    engine = _engine_of("3499632623")
    districts = [i for i in engine.state.indicia if i.art == "gemarkung"]

    assert len(districts) >= 2
    assert not engine.halves_of_one_ortsteil(districts)


# --------------------------------------------------------------------------
# „Bestätigt" means nothing contradicts, not merely that one candidate is left
# --------------------------------------------------------------------------


def test_stated_measures_are_read_only_where_a_word_says_what_was_measured():
    """A metre with no word beside it is a setback, a street or a lake."""

    assert read_dimensions("Der Bebauungsplan sieht einen Abstand von 15 m vor") is None

    both = read_dimensions(
        "Die Abmessungen von etwa 14,00 Metern Breite und ca. 40,00 Metern Tiefe"
    )
    assert both is not None and both.sides == (14.0, 40.0)

    front = read_dimensions("1.489 m² pure Freiheit (Frontbreite ca. 26 m) am Rand")
    assert front is not None and front.width == 26.0 and front.depth is None
    # And a frontage alone is not a shape: it may not object to anything.
    assert front.sides is None


def test_a_parcel_shaped_unlike_the_listing_is_an_objection_not_a_confirmation():
    """Advert 3508042470: 577 m² is 14 x 40 or 22 x 27, and only one is the plot."""

    engine = SearchEngine(
        ParcelSearchRequest(text="Die Abmessungen von etwa 14,00 Metern Breite und "
                                 "ca. 40,00 Metern Tiefe bieten Platz."),
        alkis_service(),
        DIRECTORY,
    )
    engine._dimensions = read_dimensions(engine.payload.text)

    # 21,7 x 26,7 m -- the parcel the run confirmed before this check existed.
    wrong = Flurstueck(gml_id="a", attributes={"flaeche": "577"},
                       geometry=box(0, 0, 21.7, 26.7))
    # 17,3 x 34,1 m -- the one in the district the location field names.
    right = Flurstueck(gml_id="b", attributes={"flaeche": "577"},
                       geometry=box(0, 0, 17.3, 34.1))

    engine.state.candidates = [wrong]
    objection = engine.cross_check()
    assert objection is not None and "14 × 40" in objection
    assert engine.verdict() == "mehrdeutig"

    engine.state.candidates = [right]
    assert engine.cross_check() is None

    # A plot that is not a rectangle cannot be checked against one. Measured on
    # advert 3375124391: 1 489 m² of wedge inside 39,8 x 71,5 m of rectangle.
    wedge = Flurstueck(
        gml_id="c",
        attributes={"flaeche": "1489"},
        geometry=Polygon([(0, 0), (39.8, 0), (39.8, 71.5), (0, 0)]),
    )
    engine.state.candidates = [wedge]
    assert engine.cross_check() is None


def test_the_relation_is_read_when_the_trigger_stands_behind_the_name():
    """„Thräna ist … ein Ortsteil der Kreisstadt Borna" — every window that
    looks to the left of the name misses it, and it is the one advert in the
    corpus whose answer is Thräna."""

    indicia = collect_indicia(
        text="Thräna ist mit seinen etwa 765 Einwohnern ein kleiner Ortsteil "
             "der Kreisstadt Borna.",
        directory=DIRECTORY,
    )
    district = next(i for i in indicia if i.art == "gemarkung" and i.wert == "Thräna")
    assert district.beziehung == "liegt_in"
    assert any(i.art == "gemeinde" and "Borna" in i.wert for i in indicia)


def test_a_capitalised_noun_is_not_a_district_however_the_sentence_reads():
    """German capitalises every noun, so the same shape carries things that are
    not places — and only the directory can tell."""

    indicia = collect_indicia(
        text="Das Grundstück ist ein ruhiger Ortsteil von Machern.",
        directory=DIRECTORY,
    )
    assert not any(i.art == "gemarkung" and "Grundstück" in i.wert for i in indicia)


# --------------------------------------------------------------------------
# A parcel number that resolves to the wrong parcel used to close the search
# --------------------------------------------------------------------------


@respx.mock
def test_a_contradicted_parcel_number_opens_the_area_route(client):
    """The short circuit found *a* parcel, so the staircase never ran — and the
    parcel was 2 994 m² against the 502 the listing states."""

    respx.post(ALKIS_URL).mock(
        side_effect=_cadastre(
            # The number resolves inside Großbothen, and the exact area finds
            # the right parcel there.
            {"144241+502": 1, "144241": 1131},
            {
                "flstnrzae": "alkis_thraena_107_60.gml",   # 2 994 m², the wrong one
                "502": "alkis_grossbothen_790_11.gml",     # the right one
            },
        )
    )

    events = _stream(
        client,
        {
            "gemarkung": "Großbothen",
            "flurstuecksnummer": "107/60",
            "flaeche_m2": 502,
            "flaeche_text": "502 m²",
        },
    )

    said = " ".join(e.get("text") or "" for e in events if e.get("art") == "phase")
    assert "widersprechen sich" in said
    # The staircase ran after the contradiction, and it is what answered.
    result = next(e for e in events if e["art"] == "ergebnis")
    assert result["anzahl"] >= 1
    number = next(
        e["indiz"] for e in events
        if e.get("art") == "indiz" and e["indiz"]["art"] == "flurstueck"
        and e["indiz"]["verworfen"]
    )
    assert "verlässlichere" in number["verworfen_grund"]


# ----------------------------------------------------------------------
# Distance bands
# ----------------------------------------------------------------------


def test_a_stated_distance_is_read_with_the_place_it_names():
    """Advert 3499632623: „die ca. 6 km entfernte Kreisstadt Grimma“."""

    statements = read_distances(
        "Großbothen liegt an der B107, die ca. 6 km entfernte Kreisstadt Grimma "
        "ist gut erreichbar.\nFernbahnhof 1,6 km\nBus 300 m"
    )
    by_metres = {round(s.meters): s for s in statements}
    assert by_metres[6000].target == "Grimma"
    assert by_metres[6000].named
    # A kind of place is not a place. „Fernbahnhof" and „Bus" are read, kept
    # and shown -- and never resolved to an outline, because there is none.
    assert by_metres[1600].target is None and by_metres[1600].label == "Fernbahnhof"
    assert by_metres[300].target is None


def test_a_dimension_is_not_a_distance():
    """„14 x 40 m“ and „15 m Abstand“ are about the plot, not about where it is."""

    assert read_distances("Die Abmessungen betragen 14 x 40 m.") == []
    assert read_distances("Der Bebauungsplan sieht einen Abstand von 15 m vor.") == []
    assert read_distances("Das Grundstück ist ca. 20 m breit.") == []


def test_a_name_across_a_paragraph_break_is_not_the_reference():
    """„im 3 km entfernten Machern\n\nDie verwendeten Bilder …“ — the greedy
    qualifier swallowed Machern and read the next capital word instead, which
    made „Die“ a place three kilometres away."""

    statements = read_distances(
        "Einkaufsmöglichkeiten im 3 km entfernten Machern\n\nDie verwendeten Bilder "
        "wurden teilweise nachbearbeitet."
    )
    assert [s.target for s in statements] == ["Machern"]


def test_a_class_word_is_never_read_as_a_place_and_a_place_never_as_a_class():
    """Whole words and German compound endings — never a substring, or
    „Waldheim“ becomes a forest and „Seelitz“ a lake."""

    assert read_distances("Bushaltestelle: ca. 300 m")[0].target is None
    assert read_distances("Autobahnanschlussstelle A38: ca. 3 km")[0].target is None
    assert read_distances("ca. 4 km bis Waldheim")[0].target == "Waldheim"
    assert read_distances("ca. 2 km bis zur A14")[0].target is None


def test_the_band_is_an_interval_and_so_is_the_candidate():
    """The whole design in one assertion: nothing is reduced to a number.

    Measured 16.09.2026 from Flurstück 790/11 against Grimma's built-up
    outline: 5,3 km to the edge, 6,0 km to the middle. The advert says
    „ca. 6 km“, which is the band 4,6 to 7,5 km. Read as the edge alone, or as
    the middle alone, neither is the stated figure — as an interval they
    overlap, and the right parcel survives.
    """

    reading = (5300.0, 6000.0)
    band = (6000 / distance.DETOUR, 6000 * (1 + distance.SLACK))
    assert distance.overlaps(reading, band)
    assert distance.membership(reading, band) == 1.0
    assert not distance.refuted(reading, band)


def test_a_distance_objects_outwards_and_only_outwards():
    """A route is never shorter than the straight line, so that is the one
    direction in which a broker's figure proves anything."""

    band = (6000 / distance.DETOUR, 6000 * (1 + distance.SLACK))
    # 29,9 km from Grimma — advert 3508042470's parcel in Leipzig.
    assert distance.refuted((29900.0, 30900.0), band)
    # Far too close is not a refutation: the seller may have measured a detour,
    # and the straight line says nothing about how long that was.
    assert not distance.refuted((200.0, 900.0), band)
    assert distance.membership((200.0, 900.0), band) < 1.0


def test_a_band_orders_the_candidates_and_never_confirms():
    """Role 2 and role 3 of the plan, and the rule that bounds both."""

    engine = SearchEngine(
        ParcelSearchRequest(text="Die ca. 6 km entfernte Kreisstadt Grimma ist nah."),
        alkis_service(),
        DIRECTORY,
    )
    engine._read_distances()
    indiz = next(i for i in engine.state.indicia if i.art == "entfernung")
    assert indiz.band is not None and indiz.band.bezug == "Grimma"
    assert round(indiz.band.innen_m) == round(6000 / distance.DETOUR)
    assert round(indiz.band.aussen_m) == 7500
    # Never near the threshold that separates „bestätigt“ from „mehrdeutig“.
    assert indiz.sicherheit <= 0.25

    # A resolved reference 6 km from the near candidate and 30 km from the far
    # one, stood in for here so the test asks nothing of the live service.
    town = box(0, 0, 1000, 1000)
    engine._references = [
        (
            next(s for s in read_distances(engine.payload.text)),
            Reference(name="Grimma", area=town, centre=town.centroid),
        )
    ]
    near = Flurstueck(gml_id="a", attributes={"flaeche": "502"},
                      geometry=box(6000, 0, 6020, 1000))
    far = Flurstueck(gml_id="b", attributes={"flaeche": "502"},
                     geometry=box(30000, 0, 30020, 1000))

    assert engine._distance_fit(near)[0] == 1.0
    assert engine._distance_fit(far)[0] == 0.0
    assert engine._distance_objection(near) is None
    assert "zu weit" in (engine._distance_objection(far) or "")

    # And it may not decide. One candidate, a band that fits perfectly, and the
    # verdict still comes from the hard filters alone.
    engine.state.candidates = [near]
    assert engine.verdict() == "mehrdeutig"


def test_an_unresolvable_reference_is_shown_and_not_computed():
    """„Penny 500 m“ reads exactly like a place name, and the cadastral
    directory is what says it is a shop."""

    engine = SearchEngine(
        ParcelSearchRequest(text="Penny und Nahkauf sind 500 m entfernt."),
        alkis_service(),
        DIRECTORY,
    )
    engine._read_distances()
    assert [i.wert for i in engine.state.indicia if i.art == "entfernung"] == ["500 m"]
    assert not district_matches(DIRECTORY, "Penny")


def test_thirteen_unresolvable_distances_are_one_row():
    """Advert 3375124391 lists thirteen of them and is settled by its exact
    area in five requests. One row per statement would push every finding that
    did contribute out of view."""

    engine = SearchEngine(
        ParcelSearchRequest(
            text="Einkaufsmöglichkeiten im 3 km entfernten Machern.\n"
                 "Kindergarten 2 km\nGrundschule 2 km\nRealschule 6 km\n"
                 "Gymnasium 6,8 km\nFlughafen 35 km\nFernbahnhof 3,8 km\n"
                 "Autobahn 9,7 km\nBus 500 m\nZentrum 3 km"
        ),
        alkis_service(),
        DIRECTORY,
    )
    engine._read_distances()
    rows = [i for i in engine.state.indicia if i.art == "entfernung"]
    assert [i.wert for i in rows] == ["3 km", "9 Angaben"]
    # Which is not the same as dropping them: the collapsed row names what it
    # collapsed and says why nothing is computed from it.
    assert "Kindergarten 2 km" in rows[1].text and "und 5 weitere" in rows[1].text
    assert rows[1].band is None


def test_the_band_travels_in_degrees_and_only_once():
    """The reference outline is UTM 33 in the engine and WGS 84 on the wire.

    It went out through `_geojson`, which projects out of UTM 33 itself, after
    being projected once already — and a band 6 km around Grimma arrived at
    10,51° E, 0,0005° N, in the Gulf of Guinea. Nothing threw, the legend
    counted one band, and the map drew it where nobody was looking.
    """

    engine = SearchEngine(
        ParcelSearchRequest(text="Die ca. 6 km entfernte Kreisstadt Grimma ist nah."),
        alkis_service(),
        DIRECTORY,
    )
    engine._read_distances()
    # Grimma's own outline, in the coordinates the cadastre answers in.
    town = box(320_000, 5_675_000, 322_000, 5_677_000)

    async def resolved(name):
        return Reference(name="Grimma", area=town, centre=town.centroid)

    engine._resolve_reference = resolved
    events = _drain(engine.resolve_bands())
    band = next(e.indiz.band for e in events if e.art == "indiz")
    assert band.aufgeloest
    lon, lat = band.mitte["coordinates"]
    assert 11.8 < lon < 15.1 and 50.1 < lat < 51.7, (lon, lat)
    for ring in band.umriss["coordinates"]:
        for point in ring:
            assert 11.8 < point[0] < 15.1 and 50.1 < point[1] < 51.7


# ----------------------------------------------------------------------
# Stufe 0 -- the blocks a listing is written in
# ----------------------------------------------------------------------


def test_a_listing_is_cut_into_the_blocks_it_was_written_in():
    """Heading, pair, bullet, paragraph — the four shapes the recordings use."""

    pieces = split_blocks(
        "Willkommen in Eilenburg\n"
        "\n"
        "Hier bieten wir Ihnen eines der letzten Baugrundstücke an.\n"
        "\n"
        "# Eckdaten\n"
        "Objektart: Baugrundstück\n"
        "Grundstücksfläche: ca. 711 m²\n"
        "\n"
        "- Voll erschlossen\n"
    )
    assert [(b.kind, b.label) for b in pieces] == [
        ("ueberschrift", None),
        ("absatz", None),
        ("ueberschrift", None),
        ("paar", "Objektart"),
        ("paar", "Grundstücksfläche"),
        ("punkt", None),
    ]
    assert pieces[4].text == "ca. 711 m²"


def test_a_sentence_with_a_colon_in_it_is_not_a_label():
    """Three shapes out of advert 3441433250, each of which produced a label
    for half a paragraph or for a URL."""

    def labels(line):
        return [b.label for b in split_blocks(line) if b.is_pair]

    assert labels("- https://www.ohne-makler.net/immobilie/file/1611841.pdf (Überblick)") == []
    assert labels("Die Verkehrsanbindung ist hervorragend: Über den S-Bahn-Anschluss …") == []
    assert labels("Familien profitieren von der nahen Infrastruktur: Die Grundschule …") == []
    assert labels("Stellen Sie sich vor: Ihr Haus auf diesem Grundstück") == []
    # And the ones that are labels still are.
    assert labels("Autobahnanschlussstelle A38 „Leipzig-Südwest“: ca. 3 km") == [
        "Autobahnanschlussstelle A38 „Leipzig-Südwest“"
    ]


def test_the_area_of_the_plot_is_not_whichever_number_comes_first():
    """Three figures in m², one plot. Which one the cadastre gets filtered on
    is the difference between an answer and a confidently wrong one."""

    # A labelled pair wins outright -- advert 3464790207.
    assert read_area(
        "In diesem Neubaugebiet bietet Ihnen das ca. 711 m² große Grundstück …\n"
        "\n"
        "Grundstücksfläche: ca. 680 m²\n"
    ).value == 680.0

    # A building footprint is not a plot area -- advert 3381469778 states both.
    assert read_area("Die zulässige Grundfläche beträgt insgesamt ca. 240 m².") is None
    assert read_area("Mit einer bebaubaren Fläche von ca. 240 m²") is None
    assert read_area("Wohnfläche: 140 m²") is None

    # And a sentence about the other plots in the estate is not about this one.
    # Advert 3441433250 writes this and states 590 m² in its attribute list;
    # the reader used to answer 360.
    assert read_area(
        "Die Grundstücke variieren in ihrer Größe zwischen ca. 360 m² und 800 m²."
    ) is None


def test_a_beleg_and_a_relation_stop_at_the_block_they_were_read_in():
    """„# Lagebeschreibung“ glued to the sentence under it is a Beleg whose
    first two words belong to another line."""

    indicia = collect_indicia(
        text="Kaufpreis pro m²: 92,00 €\n# Lagebeschreibung\nThräna ist ein kleiner "
             "Ortsteil der Kreisstadt Borna.",
        directory=DIRECTORY,
    )
    district = next(i for i in indicia if i.art == "gemarkung" and i.wert == "Thräna")
    assert "Lagebeschreibung" not in (district.beleg or "")
    assert "Kaufpreis" not in (district.beleg or "")
    assert district.beziehung == "liegt_in"


# ----------------------------------------------------------------------
# B2 -- a source is a document, not a channel
# ----------------------------------------------------------------------


def _numbers(*indicia):
    engine = SearchEngine(ParcelSearchRequest(text="x"), alkis_service(), DIRECTORY)
    engine.state.indicia = list(indicia)
    return engine


def _number(id, wert, quelle, fundort):
    return Indiz(id=id, art="flurstueck", wert=wert, text=wert, quelle=quelle,
                 sicherheit=0.9, fundort=fundort)


def test_two_numbers_off_two_sheets_are_two_readings_not_one_plot():
    """B2. Every OCR find carries `quelle="bild"`, so the channel could not tell
    one Geoportal print from another — and two numbers from one source are a
    plot made of several parcels, which is never put to the user as a question.
    A print carries dozens of numbers in its map image, so two prints in one
    listing is not a rare shape."""

    one_sheet = _numbers(
        _number("a", "790/11", "bild", "bild:https://example.org/1.jpg"),
        _number("b", "238/3", "bild", "bild:https://example.org/1.jpg"),
    )
    assert one_sheet.named_as_a_set()
    assert not [k for k in one_sheet._conflicts() if k.art == "flurstueck"]

    two_sheets = _numbers(
        _number("a", "790/11", "bild", "bild:https://example.org/1.jpg"),
        _number("b", "238/3", "bild", "bild:https://example.org/2.jpg"),
    )
    assert not two_sheets.named_as_a_set()
    question = next(k for k in two_sheets._conflicts() if k.art == "flurstueck")
    assert question.optionen == ["a", "b"]


def test_two_numbers_in_one_text_are_still_one_plot():
    """„790/11 sowie 238/3“ is the normal case, not a dispute — and the body
    text is one document however many paragraphs it has."""

    indicia = collect_indicia(
        text="Verkauft werden Flurstück 790/11 sowie Flurstück 238/3 der Gemarkung "
             "Großbothen.",
        directory=DIRECTORY,
    )
    numbers = [i for i in indicia if i.art == "flurstueck"]
    assert {i.wert for i in numbers} == {"790/11", "238/3"}
    assert {i.fundort for i in numbers} == {"anzeigentext"}
    engine = _numbers(*numbers)
    assert engine.named_as_a_set()


def test_an_indiz_without_a_fundort_behaves_as_it_did():
    """A caller may hand in an Indiz of its own, and the channel is the fallback."""

    engine = _numbers(
        _number("a", "790/11", "bild", None),
        _number("b", "238/3", "bild", None),
    )
    assert engine.named_as_a_set()
