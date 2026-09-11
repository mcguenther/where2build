"""The picture a chat shows when somebody pastes a shared link.

The point of this file is a channel nobody can see while working: a preview is
rendered by somebody else's server, in somebody else's app, and nothing about a
mistake here shows up in a browser. So what is checked is what that fetch
actually gets -- the `og:` block carrying the plot's own name, and a card of the
right size and format.

The block is a **fragment**, not a page: nginx splices it into the head of
`index.html` on the shared route, so bot and browser get the same page and
nothing has to guess which is which. What nginx does with it is checked against
a real nginx, not here; what is checked here is what it is handed.

Nothing needs a database or a tile server. The routes run against a stubbed
store, because what they do is not SQL; the drawing runs with no tile service at
all, because a card whose ground did not arrive is a real outcome and the
outline has to survive it.
"""

from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.deps import storage_service
from app.main import app as fastapi_app
from app.services import preview
from app.services.storage import Share

# A plot as the browser stores one: the outline in metres about its own anchor.
# Mölkau 204, squared off -- the shape only has to be a real one, not the real
# one, and every figure here is measured rather than invented.
PLOT = {
    "id": "plot-moelkau",
    "name": "Lessingweg 44",
    "gemarkung": "Mölkau",
    "municipality": "Stadt Leipzig",
    "flurstuecke": ["204"],
    "officialArea": 650,
    "bodenrichtwert": 210,
    "anchor": {"lat": 51.33649066335928, "lon": 12.441900107576787},
    "polygon": [
        {"x": -38.0, "y": 6.0},
        {"x": 24.0, "y": 19.0},
        {"x": 30.0, "y": -6.0},
        {"x": -32.0, "y": -19.0},
    ],
}

BUILDING = {"width": 11.4, "depth": 8.5, "cx": 0.0, "cy": 0.0, "rotation": -12.0}


def _share(document: dict, token: str = "AbCdEf123456789012") -> Share:
    now = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)
    return Share(id=token, dokument=document, angelegt=now, laeuft_ab=now + timedelta(days=90))


class _Store:
    """Just enough of ``Storage`` for the two routes: is there one, and which."""

    def __init__(self, share: Share | None, configured: bool = True) -> None:
        self._share = share
        self.configured = configured

    async def share(self, token: str) -> Share | None:
        return self._share if self._share and self._share.id == token else None


@pytest.fixture
def shared(request):
    """A client whose store holds one share (or none, when asked for none)."""

    document = getattr(request, "param", PLOT)
    store = _Store(_share(document) if document is not None else None)
    fastapi_app.dependency_overrides[storage_service] = lambda: store
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.pop(storage_service, None)


def _card(document: dict) -> Image.Image:
    """The card, drawn with no tile service -- so no test reaches the network."""

    return Image.open(io.BytesIO(asyncio.run(preview.card(document, None))))


# -- the drawing --------------------------------------------------------------


def test_die_karte_hat_das_mass_das_jeder_dienst_zuschneidet():
    card = _card(PLOT)

    assert card.size == preview.CARD == (1200, 630)
    # JPEG, not PNG: the same card with a photograph behind it is over half a
    # megabyte as a PNG, and several clients show no preview at all above a few
    # hundred kilobytes -- with nothing anywhere to say why.
    assert card.format == "JPEG"


def test_die_karte_entsteht_ohne_kartendienst():
    # A slow or broken WMS must cost the outline nothing: the ground is the
    # only part of the card that can fail, and it fails to paper.
    drawn = asyncio.run(preview.card(PLOT, None))

    assert len(drawn) > 5_000


def test_das_haus_wird_nur_gezeichnet_wenn_es_geteilt_wurde():
    # The switch is upstream of this: `for_sharing` cut the field, so what the
    # drawing must never do is invent one back.
    ohne = _card(PLOT).convert("RGB")
    mit = _card({**PLOT, "placedBuilding": BUILDING}).convert("RGB")

    def has_building(image: Image.Image) -> bool:
        return any(
            abs(r - preview.BUILDING[0]) < 12
            and abs(g - preview.BUILDING[1]) < 12
            and abs(b - preview.BUILDING[2]) < 12
            for _, (r, g, b) in image.getcolors(maxcolors=200_000) or []
        )

    assert has_building(mit)
    assert not has_building(ohne)


def test_ein_grundstueck_ohne_umriss_wird_nicht_erfunden():
    # No polygon is no drawing. A card is 1200 x 630 whatever happens, so the
    # temptation is to put *something* in the frame; a shape nobody measured
    # would be example data with a plot's name under it.
    card = _card({"name": "Ohne Umriss", "gemarkung": "Mölkau"})

    assert card.size == preview.CARD


def test_die_zeile_unter_dem_namen_nennt_nur_was_dasteht():
    assert preview._subtitle(PLOT) == "Mölkau · Flurstück 204 · 650 m²"
    assert preview._subtitle({"gemarkung": "Mölkau"}) == "Mölkau"
    # A missing area is left out rather than dashed: at thumbnail size a dash
    # reads as a figure nobody could measure.
    assert "m²" not in preview._subtitle({**PLOT, "officialArea": None})


def test_die_karte_wird_einmal_gezeichnet_und_dann_gelesen(tmp_path: Path):
    service = preview.PreviewService(tiles=None, cache_dir=tmp_path)
    first = asyncio.run(service.card("AbCdEf123456789012", PLOT))
    again = asyncio.run(service.card("AbCdEf123456789012", {**PLOT, "name": "Etwas anderes"}))

    # The token is the key and a shared document never changes, so the second
    # call must not draw: the changed name proves the stored file came back.
    assert again == first


def test_eine_geaenderte_zeichnung_erreicht_auch_alte_links(tmp_path: Path):
    """A cache key that does not name what produced the answer outlives the fix.

    Twice before in this repo, and a third time on this very card: switching it
    from PNG to JPEG kept serving the stored PNG, which every client renders
    anyway -- so nothing looked wrong and the file stayed five times too big for
    a preview. The version is in the key for exactly that.
    """

    service = preview.PreviewService(tiles=None, cache_dir=tmp_path)
    before = asyncio.run(service.card("AbCdEf123456789012", PLOT))

    preview.CARD_VERSION += 1
    try:
        after = asyncio.run(service.card("AbCdEf123456789012", {**PLOT, "name": "Etwas anderes"}))
    finally:
        preview.CARD_VERSION -= 1

    # A new version misses the stored entry, so the card is drawn again -- and
    # the changed name is what makes the difference visible in the bytes.
    assert after != before


# -- the block nginx splices in -------------------------------------------------

HEAD = "/api/shares/AbCdEf123456789012/vorschau-kopf"


def test_der_block_traegt_den_namen_des_grundstuecks(shared: TestClient):
    answer = shared.get(HEAD)

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/html")
    assert '<meta property="og:title" content="Lessingweg 44">' in answer.text
    assert '<meta name="twitter:card" content="summary_large_image">' in answer.text
    assert "/api/shares/AbCdEf123456789012/vorschau.jpg" in answer.text


def test_der_block_ist_ein_fragment_und_keine_seite(shared: TestClient):
    """It lands inside a head that already has one.

    A second `<title>` or another `<html>` would not throw anywhere -- a
    browser takes the first title and ignores the rest -- so nothing would look
    broken while the tab of every shared plot showed the wrong name.
    """

    text = shared.get(HEAD).text

    for stray in ("<html", "<head", "<title", "<!doctype"):
        assert stray not in text.lower()


def test_die_kanonische_adresse_traegt_keinen_lesbaren_zusatz(shared: TestClient):
    # The tail is decoration a link may grow later. Pointing every copy of a
    # link at one address is what a canonical URL is for.
    assert '<meta property="og:url" content="http://testserver/geteilt/AbCdEf123456789012">' in (
        shared.get(HEAD).text
    )


def test_die_beschreibung_nennt_nur_geteilte_zahlen(shared: TestClient):
    ohne = shared.get(HEAD).text
    assert "Kaufpreis" not in ohne
    assert "650 m² amtliche Fläche" in ohne

    store = _Store(_share({**PLOT, "askingPrice": 349000}))
    fastapi_app.dependency_overrides[storage_service] = lambda: store
    mit = shared.get(HEAD).text

    assert "349.000 € Kaufpreis" in mit


def test_ein_name_mit_spitzen_klammern_bleibt_text(shared: TestClient):
    # The name is somebody's own text and it lands in an attribute. Escaped at
    # the door rather than cleaned on the way in: the document is a copy of
    # what the browser stored, and nothing else reads it as markup.
    store = _Store(_share({**PLOT, "name": 'Wiese "<script>alert(1)</script>"'}))
    fastapi_app.dependency_overrides[storage_service] = lambda: store
    answer = shared.get(HEAD)

    assert "<script>" not in answer.text
    assert "&lt;script&gt;" in answer.text


def test_der_block_bittet_darum_nicht_indexiert_zu_werden(shared: TestClient):
    # Every messenger ignores this, which is what makes it the right place to
    # say it: a link meant for a family is not an invitation to a search index.
    assert '<meta name="robots" content="noindex, nofollow">' in shared.get(HEAD).text


@pytest.mark.parametrize("shared", [None], indirect=True)
def test_ein_abgelaufener_link_liefert_nichts_und_keinen_fehler(shared: TestClient):
    """200 and empty, not 404.

    nginx substitutes nothing for a failed include either way, so the page is
    the same -- but a 404 per fetch would fill the error log, and the reader
    still gets the app's own „Dieser Link führt nirgendwohin".
    """

    answer = shared.get(HEAD)

    assert answer.status_code == 200
    assert answer.text == ""


@pytest.mark.parametrize("shared", [None], indirect=True)
def test_ein_abgelaufener_link_hat_auch_kein_bild(shared: TestClient):
    assert shared.get("/api/shares/AbCdEf123456789012/vorschau.jpg").status_code == 404


def test_das_bild_kommt_als_jpeg(shared: TestClient):
    answer = shared.get("/api/shares/AbCdEf123456789012/vorschau.jpg")

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(answer.content)).size == preview.CARD


def test_das_bild_beantwortet_auch_ein_head(shared: TestClient):
    # A link expander asks HEAD first to see what it is about to fetch, and
    # Starlette adds no HEAD for a GET route -- the 405 that answered made
    # clients skip the preview entirely.
    assert shared.head("/api/shares/AbCdEf123456789012/vorschau.jpg").status_code == 200


def test_die_schnittstellenbeschreibung_bleibt_eindeutig():
    """Two methods on one decorator give both operations the same id.

    FastAPI answers that with a warning and an OpenAPI document in which one
    operation quietly overwrites the other -- nothing fails, and the generated
    client is missing a route. The HEAD is therefore a route of its own, out of
    the schema.
    """

    ids = [
        operation["operationId"]
        for path in fastapi_app.openapi()["paths"].values()
        for operation in path.values()
        if "operationId" in operation
    ]

    assert len(ids) == len(set(ids))
    assert "/api/shares/{token}/vorschau.jpg" in fastapi_app.openapi()["paths"]


def test_ohne_serverspeicher_gibt_es_keine_vorschau():
    store = _Store(None, configured=False)
    fastapi_app.dependency_overrides[storage_service] = lambda: store
    try:
        client = TestClient(fastapi_app)
        assert client.get(HEAD).text == ""
        assert client.get("/api/shares/AbCdEf123456789012/vorschau.jpg").status_code == 404
    finally:
        fastapi_app.dependency_overrides.pop(storage_service, None)


def test_die_absolute_adresse_folgt_dem_weitergereichten_schema(
    shared: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """og:url has to name the origin the caller reached, and https matters.

    A messenger handed `http://` for a site served over TLS fetches the picture
    over plain HTTP, and several refuse it outright. The forwarded scheme is
    believed only where APP_PROXY_HOPS says a proxy of ours is in front -- the
    same rule the request budget follows, for the same reason.
    """

    from app.deps import reset_services

    headers = {"X-Forwarded-Proto": "https", "Host": "wo.example"}
    assert "http://wo.example/geteilt" in shared.get(HEAD, headers=headers).text

    monkeypatch.setenv("APP_PROXY_HOPS", "1")
    reset_services()
    assert "https://wo.example/geteilt" in shared.get(HEAD, headers=headers).text
