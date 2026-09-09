"""/api/shares -- a plot shared by link.

Four endpoints, and the split between them is the whole design:

* **Three belong to an account.** Making a link, listing one's own, and
  withdrawing one all resolve the account from the session cookie, exactly like
  every other route in ``storage.py``.
* **One belongs to nobody.** ``GET /api/shares/{token}`` has no session at all:
  the token *is* the access, and requiring a sign-in would defeat the point of
  a link somebody sends to their family or a surveyor.

That makes the token the only thing standing between a URL and a real plot's
address, which is why it is 16 random bytes and why the share is a **copy**:
what was shared stays what it was on the day, so a link handed out weeks ago
cannot start showing a corrected price.

What a link carries beyond the plot itself is chosen switch by switch, and
every switch defaults to *off* -- a link is public, and the safe default for a
public thing is the least it can be. The cutting happens in
``Storage.create_share``, not here and not in the browser, because a promise
the frontend keeps is one a bug in the frontend can break.

Every link has an end. Without one this table only grows, and an abandoned
share would sit there for ever; ``STORAGE_SHARE_DAYS`` says how long and the
sweep job removes what is past it. An expired token answers 404 rather than
410: to whoever holds the link the two are the same, and 410 would confirm that
something was once there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request, Response

from ..deps import current_account, preview_service, storage_service
from ..errors import NotFoundError
from ..schemas import (
    FreigabeAngelegt,
    FreigabeAnfrage,
    FreigabeAntwort,
    FreigabenAntwort,
    FreigabeUmfang,
)
from ..services.oidc import Identity
from ..services import sharemeta
from ..services.preview import PreviewService
from ..services.storage import Storage, share_scope
from ..settings import get_settings

router = APIRouter(prefix="/api/shares", tags=["Freigaben"])

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

_TOKEN = Path(
    min_length=8,
    max_length=64,
    pattern=r"^[A-Za-z0-9_-]+$",
    description="Der Schlüssel aus dem geteilten Link.",
)


@router.post(
    "",
    response_model=FreigabeAngelegt,
    status_code=201,
    summary="Grundstück per Link teilen",
    responses={
        401: {"description": "Nicht angemeldet"},
        409: {"description": "Zu viele offene Freigaben"},
        413: {"description": "Das Dokument ist zu groß"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def create(
    payload: FreigabeAnfrage,
    response: Response,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> FreigabeAngelegt:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    share = await storage.create_share(
        identity, payload.dokument, payload.umfang.model_dump()
    )
    return FreigabeAngelegt(
        id=share.id, angelegt=share.angelegt, laeuft_ab=share.laeuft_ab
    )


@router.get(
    "",
    response_model=FreigabenAntwort,
    summary="Eigene Freigaben",
    responses={
        401: {"description": "Nicht angemeldet"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def mine(
    response: Response,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> FreigabenAntwort:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    held = await storage.shares(identity)
    return FreigabenAntwort(
        eintraege=[
            FreigabeAngelegt(
                id=share.id,
                angelegt=share.angelegt,
                laeuft_ab=share.laeuft_ab,
                name=str(share.dokument.get("name") or "") or None,
                grundstueck=str(share.dokument.get("id") or "") or None,
                # Read off the row, not remembered from the request: a list
                # that says what a link carries has to be checkable against the
                # thing itself.
                umfang=FreigabeUmfang(**share_scope(share.dokument)),
            )
            for share in held
        ]
    )


@router.delete(
    "/{token}",
    status_code=204,
    summary="Freigabe zurückziehen",
    responses={
        204: {"description": "Zurückgezogen, oder es gab sie nicht"},
        401: {"description": "Nicht angemeldet"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def withdraw(
    token: str = _TOKEN,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> Response:
    storage.require_configured()
    await storage.delete_share(identity, token)
    return Response(status_code=204, headers=_NO_STORE)


@router.get(
    "/{token}",
    response_model=FreigabeAntwort,
    summary="Ein geteiltes Grundstück ansehen",
    responses={
        404: {"description": "Diesen Link gibt es nicht (mehr)"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def shared(
    response: Response,
    token: str = _TOKEN,
    storage: Storage = Depends(storage_service),
) -> FreigabeAntwort:
    """The one route here without a session. The token is the access.

    Not cached either, even though the document never changes: withdrawing a
    link has to take effect, and an intermediary holding the last answer would
    keep serving a plot after its owner took it back.
    """

    response.headers.update(_NO_STORE)
    storage.require_configured()
    share = await storage.share(token)
    if share is None:
        raise NotFoundError(
            "Diesen geteilten Link gibt es nicht mehr. Er kann zurückgezogen worden "
            "oder abgelaufen sein."
        )
    return FreigabeAntwort(
        dokument=share.dokument, angelegt=share.angelegt, laeuft_ab=share.laeuft_ab
    )


# HEAD as well, and as a route of its own rather than a second method on the
# one below: a link expander asks HEAD first to see the type and the size, and
# Starlette adds none for a GET route -- but two methods on one decorator give
# both operations the same id and the OpenAPI document warns about the clash.
# Out of the schema, because a documented HEAD is noise.
@router.head("/{token}/vorschau.jpg", include_in_schema=False)
@router.get(
    "/{token}/vorschau.jpg",
    summary="Das Vorschaubild eines geteilten Grundstücks",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Die Karte, 1200 × 630"},
        404: {"description": "Diesen Link gibt es nicht (mehr)"},
    },
)
async def preview(
    token: str = _TOKEN,
    storage: Storage = Depends(storage_service),
    previews: PreviewService = Depends(preview_service),
) -> Response:
    """The card a chat shows when somebody pastes the link.

    Public and without a budget, like the page it belongs to: it is drawn once
    per share and read from disk after that, so a link doing the rounds costs a
    file read. A budget shared with everything else behind the same proxy would
    answer a group chat with a broken image.

    A missing share answers 404 with no body -- a picture cannot carry a German
    sentence anybody would read, and no image is the right outcome for a link
    that is gone.
    """

    if not storage.configured:
        return Response(status_code=404)
    share = await storage.share(token)
    if share is None:
        return Response(status_code=404)
    return Response(
        await previews.card(share.id, share.dokument),
        media_type="image/jpeg",
        # Long enough that a chat's own cache carries a link doing the rounds,
        # short enough that withdrawing one takes effect the same day.
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _public_base(request: Request) -> str:
    """The origin the caller actually reached us on.

    Only the caller knows it: behind the compose nginx the app answers on
    :8080, on a server it answers on a name this process never sees. The
    forwarded scheme is trusted only where ``APP_PROXY_HOPS`` says a proxy of
    ours stands in front -- the same rule the request budget follows, and for
    the same reason: a header a caller can write is not evidence.

    `$http_host`, not `$host`, is what nginx has to forward here: `$host` drops
    the port, and on the compose default every og:url would then name port 80.
    """

    host = request.headers.get("host") or request.url.netloc
    scheme = request.url.scheme
    if get_settings().app.proxy_hops > 0:
        forwarded = request.headers.get("x-forwarded-proto", "")
        if forwarded:
            scheme = forwarded.split(",")[-1].strip() or scheme
    return f"{scheme}://{host}"


@router.get(
    "/{token}/vorschau-kopf",
    summary="Die og:-Angaben eines geteilten Grundstücks, als Fragment",
    response_class=Response,
    responses={200: {"content": {"text/html": {}}, "description": "Der <meta>-Block"}},
)
async def preview_head(
    request: Request,
    token: str = _TOKEN,
    storage: Storage = Depends(storage_service),
) -> Response:
    """What nginx splices into the head of `index.html` on a shared link.

    Not a page and not JSON: a fragment, because a preview bot runs no
    JavaScript and the built app would otherwise hand it the same title for
    every plot ever shared. Doing it this way means every caller gets the tags
    -- there is nothing to recognise a bot by, and nothing to get wrong.

    No session: the token is the access, exactly as for the snapshot itself.
    An unknown or withdrawn token answers **200 with an empty body** rather
    than 404: nginx substitutes nothing for a failed include, so the page is
    the same either way, and 200 keeps it out of the error log. The reader then
    sees the app's own „Dieser Link führt nirgendwohin".
    """

    empty = Response("", media_type="text/html; charset=utf-8")
    if not storage.configured:
        return empty
    share = await storage.share(token)
    if share is None:
        return empty
    return Response(
        sharemeta.head(share.dokument, share.id, share.angelegt, _public_base(request)),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )
