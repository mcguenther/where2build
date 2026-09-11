"""The `<meta>` block a shared link needs, composed from the shared document.

A preview bot -- a chat client, a messenger, a search engine -- runs no
JavaScript: it reads the `og:` tags out of the HTML it is handed and stops. The
app is a Vue route, so the built `index.html` says the same thing for every plot
anybody ever shared.

The way round it here is nginx SSI: `index.html` carries one include, and on the
shared route nginx fetches this block and puts it in the head before the file
goes out. That means **every** caller gets the tags, bot or browser, and nothing
has to guess which is which from a user agent.

The text is composed, never written: fields in, fixed German out, and a figure
that is not in the document does not appear. The document has already been cut
to what the sharer switched on, so a price here is a price somebody chose to
share.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from .preview import CARD


def _german(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def title(document: dict[str, Any]) -> str:
    return str(document.get("name") or "Geteiltes Grundstück").strip() or "Geteiltes Grundstück"


def description(document: dict[str, Any], shared_at: datetime | None) -> str:
    parts: list[str] = []
    where = " · ".join(
        str(document[key]) for key in ("gemarkung", "municipality") if document.get(key)
    )
    if where:
        parts.append(where)
    area = document.get("officialArea")
    if isinstance(area, (int, float)) and area > 0:
        parts.append(f"{_german(area)} m² amtliche Fläche")
    price = document.get("askingPrice")
    if isinstance(price, (int, float)) and price > 0:
        parts.append(f"{_german(price)} € Kaufpreis")
    reference = document.get("bodenrichtwert")
    if isinstance(reference, (int, float)) and reference > 0:
        parts.append(f"Bodenrichtwert {_german(reference)} € je m²")
    stand = shared_at.strftime("%d.%m.%Y") if isinstance(shared_at, datetime) else ""
    tail = f" Momentaufnahme vom {stand}." if stand else ""
    return ("; ".join(parts) + "." if parts else "Ein geprüftes Grundstück in Sachsen.") + tail


def head(document: dict[str, Any], token: str, shared_at: datetime | None, base: str) -> str:
    """The block nginx splices into the head of `index.html`.

    A fragment, not a document: it lands inside a head that already carries a
    charset, a viewport and a title. No second `<title>` -- a browser takes the
    first one it sees and the app sets its own once it runs, while every preview
    reads `og:title` anyway.

    The canonical URL deliberately carries no slug. The readable tail is
    decoration that a link may grow later, and pointing every copy of a link at
    one address is what a canonical URL is for.
    """

    e = lambda value: html.escape(str(value), quote=True)
    name = title(document)
    return f"""<meta name="description" content="{e(description(document, shared_at))}">
<!-- A shared link is meant for the people it was sent to; a preview is not an
     invitation to index it. Every messenger ignores this, which is exactly
     what makes it the right place to say it. -->
<meta name="robots" content="noindex, nofollow">
<meta property="og:type" content="website">
<meta property="og:site_name" content="where2build">
<meta property="og:locale" content="de_DE">
<meta property="og:title" content="{e(name)}">
<meta property="og:description" content="{e(description(document, shared_at))}">
<meta property="og:url" content="{e(base)}/geteilt/{e(token)}">
<meta property="og:image" content="{e(base)}/api/shares/{e(token)}/vorschau.jpg">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="{CARD[0]}">
<meta property="og:image:height" content="{CARD[1]}">
<meta property="og:image:alt" content="Lageplan von {e(name)}">
<meta name="twitter:card" content="summary_large_image">
"""
