"""``/geteilt/…`` -- the page a preview bot reads, and the picture it shows.

Everything else this backend serves lives under ``/api`` and answers JSON. This
one does not, and the reason is the whole of its design: a chat client, a
messenger or a search engine fetching a shared link runs **no JavaScript**. It
reads the ``og:`` tags out of the HTML it is handed and stops. The app's own
page is a Vue route, so what such a fetch gets from the static build is the
empty shell -- one title for every plot ever shared.

So nginx sends exactly those callers here (see ``frontend/nginx.conf``), and
this router answers the same URL with a small document that says which plot it
is, plus a card drawn server-side. A browser is never routed here; if one
arrives anyway -- an unrecognised bot-ish user agent -- the page is a real page
with the plot's name, its card and the way into the app, not a blank.

Two things it deliberately does not do. It asks for no session: the token is
the access, exactly as in ``shares.py``. And it carries no request budget: the
card is drawn once per share and read from disk afterwards, so a link doing the
rounds costs a file read, while a budget shared with a proxy's other callers
would answer a chat with a broken image.
"""

from __future__ import annotations

import html
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Request, Response

from ..deps import storage_service
from ..services.preview import CARD
from ..services.storage import Share, Storage
from ..settings import get_settings

router = APIRouter(tags=["Freigaben"], include_in_schema=False)

_TOKEN = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

# Long enough that a chat's own cache does the work for a link doing the rounds,
# short enough that withdrawing one takes effect the same day.
_CACHE = "public, max-age=3600"


def _public_base(request: Request) -> str:
    """The origin the caller actually reached us on.

    Only the caller knows it: behind the compose nginx the app answers on
    :8080, on a server it answers on a name this process never sees. The
    forwarded scheme is trusted only where ``APP_PROXY_HOPS`` says a proxy of
    ours stands in front -- the same rule the request budget follows, and for
    the same reason: a header a caller can write is not evidence.
    """

    host = request.headers.get("host") or request.url.netloc
    scheme = request.url.scheme
    if get_settings().app.proxy_hops > 0:
        forwarded = request.headers.get("x-forwarded-proto", "")
        if forwarded:
            scheme = forwarded.split(",")[-1].strip() or scheme
    return f"{scheme}://{host}"


def _description(document: dict, share: Share) -> str:
    """One sentence, composed from what was actually shared.

    Same rule as everywhere else in the app: the text is assembled from fields,
    never written by a model, and a figure that is not in the document does not
    appear. The document has already been cut to what the sharer switched on,
    so a price here is a price somebody chose to share.
    """

    parts: list[str] = []
    where = " · ".join(
        str(document[key]) for key in ("gemarkung", "municipality") if document.get(key)
    )
    if where:
        parts.append(where)
    area = document.get("officialArea")
    if isinstance(area, (int, float)) and area > 0:
        parts.append(f"{round(area):,} m² amtliche Fläche".replace(",", "."))
    price = document.get("askingPrice")
    if isinstance(price, (int, float)) and price > 0:
        parts.append(f"{round(price):,} € Kaufpreis".replace(",", "."))
    reference = document.get("bodenrichtwert")
    if isinstance(reference, (int, float)) and reference > 0:
        parts.append(f"Bodenrichtwert {round(reference):,} € je m²".replace(",", "."))
    stand = share.angelegt.strftime("%d.%m.%Y") if isinstance(share.angelegt, datetime) else ""
    tail = f" Momentaufnahme vom {stand}." if stand else ""
    return ("; ".join(parts) + "." if parts else "Ein geprüftes Grundstück in Sachsen.") + tail


def _page(document: dict, share: Share, base: str, path: str) -> str:
    title = str(document.get("name") or "Geteiltes Grundstück").strip() or "Geteiltes Grundstück"
    description = _description(document, share)
    image = f"{base}/api/shares/{share.id}/vorschau.jpg"
    url = f"{base}{path}"
    e = lambda value: html.escape(str(value), quote=True)
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · where2build</title>
<meta name="description" content="{e(description)}">
<!-- A shared link is meant for the people it was sent to; a preview is not an
     invitation to index it. Every messenger ignores this, which is exactly
     what makes it the right place to say it. -->
<meta name="robots" content="noindex, nofollow">
<meta property="og:type" content="website">
<meta property="og:site_name" content="where2build">
<meta property="og:locale" content="de_DE">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(image)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="{CARD[0]}">
<meta property="og:image:height" content="{CARD[1]}">
<meta property="og:image:alt" content="Lageplan von {e(title)}">
<meta name="twitter:card" content="summary_large_image">
<style>
body{{margin:0;background:#F1EBE1;color:#1E1A16;
     font-family:'Public Sans',system-ui,sans-serif;line-height:1.5}}
main{{max-width:660px;margin:0 auto;padding:48px 24px}}
img{{width:100%;height:auto;border-radius:12px;border:1px solid #DCD3C6}}
h1{{font-size:2rem;margin:24px 0 4px}}
p{{color:#6F675C;margin:0 0 24px}}
a{{display:inline-block;background:#2F4A3A;color:#F7F4EE;text-decoration:none;
   padding:12px 20px;border-radius:8px}}
</style>
</head>
<body><main>
<img src="{e(image)}" alt="Lageplan von {e(title)}">
<h1>{e(title)}</h1>
<p>{e(description)}</p>
<a href="{e(url)}">Grundstück ansehen</a>
</main></body>
</html>
"""


_GONE = """<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Link nicht mehr gültig · where2build</title>
<meta name="robots" content="noindex, nofollow">
<style>body{margin:0;background:#F1EBE1;color:#1E1A16;
font-family:system-ui,sans-serif;line-height:1.5}
main{max-width:520px;margin:0 auto;padding:64px 24px}</style></head>
<body><main><h1>Dieser Link führt nirgendwohin</h1>
<p>Diesen geteilten Link gibt es nicht mehr. Er kann zurückgezogen worden oder
abgelaufen sein.</p></main></body></html>
"""


async def _share(token: str, storage: Storage) -> Share | None:
    if not storage.configured:
        return None
    return await storage.share(token)


# HEAD as well as GET, and that is not politeness. Several link expanders --
# Slack's among them -- ask HEAD first to see what they are about to fetch, and
# Starlette adds no HEAD for a GET route, so the answer was 405 and the preview
# was skipped before the page was ever read.
@router.head("/geteilt/{token}")
@router.head("/geteilt/{token}/{slug:path}")
@router.get("/geteilt/{token}")
@router.get("/geteilt/{token}/{slug:path}")
async def page(
    request: Request,
    token: str = _TOKEN,
    slug: str = "",
    storage: Storage = Depends(storage_service),
) -> Response:
    """The shared plot, as a preview bot sees it.

    The slug is read and ignored on purpose: it is there so a link can grow a
    readable tail later without any link already sent going dead.
    """

    share = await _share(token, storage)
    if share is None:
        return Response(_GONE, status_code=404, media_type="text/html; charset=utf-8")
    return Response(
        _page(share.dokument, share, _public_base(request), request.url.path),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": _CACHE},
    )
