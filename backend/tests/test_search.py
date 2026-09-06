"""POST /api/parcels/search -- the staircase, its short circuit and its conflicts.

Every cadastral answer here is a recorded one: the counts and the two parcels in
``alkis_grossbothen_band.gml`` were fetched from the live WFS on 05.09.2026 and
are the same figures ``docs/research/flurstueck-identifikation.md`` reports.
"""

from __future__ import annotations

import io
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
    describes_part_area,
    federal_state,
    normalise_parcel_number,
    outside_saxony,
    read_area,
)
from app.search.ladder import tolerance_ladder
from app.search.scoring import land_use, score, street_match
from app.services import ocr
from app.services.alkis import parse_feature_collection

from app.deps import alkis_service
from app.search.engine import SearchEngine

from .conftest import ALKIS_URL, fixture_bytes, fixture_json, fixture_text

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
        GemarkungEntry("Borna", "141810", "Stadt Borna"),
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


def _anchor_names(key: str) -> list[str]:
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
    return [f"{a.name}/{a.schluessel}" for a in engine.anchors()]


def test_ortsteil_names_the_district_and_the_municipality_in_one_breath():
    """„im malerischen Ortsteil Plagwitz von Machern“ — both, one level apart."""

    indicia = _indicia_of("3375124391")
    districts = [i for i in indicia if i.art == "gemarkung" and i.beziehung == "liegt_in"]
    municipalities = [i.wert for i in indicia if i.art == "gemeinde"]

    assert [i.wert for i in districts] == ["Plagwitz"]
    assert "Machern" in municipalities


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
