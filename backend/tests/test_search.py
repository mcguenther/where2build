"""POST /api/parcels/search -- the staircase, its short circuit and its conflicts.

Every cadastral answer here is a recorded one: the counts and the two parcels in
``alkis_grossbothen_band.gml`` were fetched from the live WFS on 05.09.2026 and
are the same figures ``docs/research/flurstueck-identifikation.md`` reports.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.gemarkung_index import GemarkungDirectory, GemarkungEntry
from app.schemas import Indiz, ParcelSearchRequest
from app.search.envelope import common_envelope
from app.search.indicia import (
    AreaStatement,
    collect_indicia,
    normalise_parcel_number,
    read_area,
)
from app.search.ladder import tolerance_ladder
from app.search.scoring import land_use, score, street_match
from app.services.alkis import parse_feature_collection

from .conftest import ALKIS_URL, fixture_bytes

# The three district names the reference listing contains, plus the second
# Höfgen -- a name is not a key, and two of these share one.
DIRECTORY = GemarkungDirectory(
    [
        GemarkungEntry("Großbothen", "144241", "Stadt Grimma"),
        GemarkungEntry("Grimma", "144236", "Stadt Grimma"),
        GemarkungEntry("Höfgen", "144245", "Stadt Grimma"),
        GemarkungEntry("Höfgen", "146132", "Stadt Colditz"),
        GemarkungEntry("Mölkau", "143156", "Stadt Leipzig"),
    ],
    stand="2026-09-05",
)

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

    assert districts["Großbothen"].beziehung == "liegt_in"
    assert districts["Höfgen"].beziehung == "liegt_in"
    # The one the text places the plot *in* outranks the one it merely mentions.
    assert districts["Großbothen"].sicherheit > districts["Grimma"].sicherheit


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
        side_effect=[
            _gml("alkis_grossbothen_790_11.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
        side_effect=[
            _gml("alkis_grossbothen_790_11.gml"),  # Großbothen: the hit
            _gml("alkis_leer.gml"),  # Grimma
            _gml("alkis_leer.gml"),  # Höfgen 144245
            _gml("alkis_leer.gml"),  # Höfgen 146132
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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

    route = respx.post(ALKIS_URL).mock(side_effect=[_gml("alkis_leer.gml")] * 20)
    _stream(client, {**payload, "entscheidungen": {"gemarkung": hoefgen.id}})

    asked = "".join(call.request.content.decode("utf-8") for call in route.calls)
    # Only the chosen reading's districts are queried. Großbothen -- which the
    # search would otherwise have ranked first -- is never asked about.
    assert "144245" in asked and "146132" in asked
    assert "144241" not in asked


@respx.mock
def test_the_staircase_stops_at_the_first_rung_that_answers(client: TestClient):
    """No parcel number: exact area, four districts, one hit."""

    respx.post(ALKIS_URL).mock(
        side_effect=[
            # Three anchors: Großbothen and the two Höfgen. Grimma is named as
            # "6 km entfernte Kreisstadt" and is therefore never an anchor.
            _hits(1131), _hits(1131), _hits(1131),   # phase 2, the counts
            # The search space, drawn: one outline per anchor, so the map has
            # something to frame on before the first candidate exists.
            _gml("alkis_katasterbezirk_grossbothen.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
            _hits(1), _hits(0), _hits(0),            # rung 0
            _gml("alkis_grossbothen_790_11.gml"),    # fetch the survivor
            _gml("alkis_grossbothen_band.gml"),      # confirmation rung
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
    )

    events = _stream(client, {"text": LISTING, "flaeche_m2": 502, "flaeche_text": "502 m²"})

    # The place named as distant never becomes a place to search in.
    assert not any(
        e["art"] == "phase" and "Grimma" in (e.get("text") or "") for e in events
    )
    # The map is given the districts in play before any candidate exists.
    areas = next(e for e in events if e["art"] == "gebiete")
    assert areas["gebiete"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert areas["gebiete"][0]["anzahl"] == 1131

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
        side_effect=[
            _hits(1131),
            _gml("alkis_katasterbezirk_grossbothen.gml"),   # the search space
            _hits(2),
            _gml("alkis_grossbothen_790_11.gml"),
            _gml("alkis_grossbothen_band.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
        side_effect=[
            _gml("alkis_grossbothen_790_11.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
        side_effect=[
            _gml("alkis_grossbothen_790_11.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
        side_effect=[
            _gml("alkis_grossbothen_band.gml"),   # 238/3 at 500 m² and 790/11 at 502
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
        side_effect=[
            _gml("alkis_grossbothen_band.gml"),   # both, in one answer
            _gml("alkis_leer.gml"),
            _gml("alkis_katasterbezirk_grossbothen.gml"),
        ]
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
