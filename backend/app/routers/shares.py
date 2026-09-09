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

from fastapi import APIRouter, Depends, Path, Response

from ..deps import current_account, storage_service
from ..errors import NotFoundError
from ..schemas import (
    FreigabeAngelegt,
    FreigabeAnfrage,
    FreigabeAntwort,
    FreigabenAntwort,
)
from ..services.oidc import Identity
from ..services.storage import Storage

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
