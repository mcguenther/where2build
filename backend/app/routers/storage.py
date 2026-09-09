"""/api/plots and /api/settings -- the account's copy of the document.

Five endpoints and one rule: whoever is signed in sees their own rows and
nothing else. The separation is in the primary key rather than in a WHERE
clause somebody has to remember (see ``app/schema.sql``), and every statement
resolves the account from the session cookie, never from anything the request
carries.

Three answers matter as much as the data:

* **401** when nobody is signed in. There is no anonymous half of this API;
  without an account the frontend keeps working exactly as it always has, in
  the browser.
* **503** when this deployment has no server storage at all. That is a
  complete, working deployment, not a failure, and the frontend reads it as
  "stay local" rather than as an error to show.
* **409** when the stand the sender built on is no longer the stored one. A
  contradiction is shown, never resolved quietly: the answer carries what is
  stored under ``aktuell`` so the interface can put both to the user.

Nothing here may be cached: every answer is one person's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response

from ..deps import current_account, storage_service
from ..schemas import (
    EinstellungenAntwort,
    EinstellungenGespeichert,
    GespeichertesGrundstueck,
    GrundstueckGespeichert,
    GrundstueckeAntwort,
    SpeicherAnfrage,
)
from ..services.oidc import Identity
from ..services.storage import Storage

router = APIRouter(prefix="/api", tags=["Konto"])

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# Long enough for any id the frontend makes ("plot-x7k2a9f") and for a UUID,
# short enough that the path is not a place to put data.
_MAX_ID_LENGTH = 200

_ID = Path(
    min_length=1,
    max_length=_MAX_ID_LENGTH,
    description="Kennung des Grundstücks, wie sie das Frontend vergibt.",
)


@router.get(
    "/plots",
    response_model=GrundstueckeAntwort,
    summary="Grundstücke des Kontos",
    responses={
        401: {"description": "Nicht angemeldet"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def plots(
    response: Response,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> GrundstueckeAntwort:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    stored = await storage.plots(identity)
    return GrundstueckeAntwort(
        eintraege=[
            GespeichertesGrundstueck(
                id=entry.id, geaendert_am=entry.geaendert_am, dokument=entry.dokument
            )
            for entry in stored
        ]
    )


@router.put(
    "/plots/{plot_id}",
    response_model=GrundstueckGespeichert,
    summary="Grundstück speichern",
    responses={
        401: {"description": "Nicht angemeldet"},
        409: {"description": "Der Stand wurde inzwischen anderswo geändert; „aktuell“ sagt, was dort steht"},
        413: {"description": "Das Dokument ist zu groß"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def save_plot(
    payload: SpeicherAnfrage,
    response: Response,
    plot_id: str = _ID,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> GrundstueckGespeichert:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    stand = await storage.save_plot(
        identity, plot_id, payload.dokument, expected=payload.geaendert_am
    )
    return GrundstueckGespeichert(id=plot_id, geaendert_am=stand)


@router.delete(
    "/plots/{plot_id}",
    status_code=204,
    summary="Grundstück löschen",
    responses={
        204: {"description": "Gelöscht, oder war schon nicht mehr da"},
        401: {"description": "Nicht angemeldet"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def delete_plot(
    plot_id: str = _ID,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> Response:
    storage.require_configured()
    # Idempotent on purpose: the frontend sends a delete for every plot it no
    # longer has, and a 404 for one it already sent would turn a finished job
    # into an error the interface has to explain away.
    await storage.delete_plot(identity, plot_id)
    return Response(status_code=204, headers=dict(_NO_STORE))


@router.get(
    "/settings",
    response_model=EinstellungenAntwort,
    summary="Haustypen, Ziele und Auswahl",
    responses={
        401: {"description": "Nicht angemeldet"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def settings(
    response: Response,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> EinstellungenAntwort:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    stored = await storage.settings_document(identity)
    # Nothing stored yet is an empty document with no stand, not a 404: the
    # frontend hangs its "shall I take this browser's work along?" question on
    # exactly that pair being empty.
    if stored is None:
        return EinstellungenAntwort(dokument={}, geaendert_am=None)
    return EinstellungenAntwort(dokument=stored.dokument, geaendert_am=stored.geaendert_am)


@router.put(
    "/settings",
    response_model=EinstellungenGespeichert,
    summary="Haustypen, Ziele und Auswahl speichern",
    responses={
        401: {"description": "Nicht angemeldet"},
        409: {"description": "Der Stand wurde inzwischen anderswo geändert; „aktuell“ sagt, was dort steht"},
        413: {"description": "Das Dokument ist zu groß"},
        503: {"description": "Kein Serverspeicher eingerichtet"},
    },
)
async def save_settings(
    payload: SpeicherAnfrage,
    response: Response,
    identity: Identity = Depends(current_account),
    storage: Storage = Depends(storage_service),
) -> EinstellungenGespeichert:
    response.headers.update(_NO_STORE)
    storage.require_configured()
    stand = await storage.save_settings(
        identity, payload.dokument, expected=payload.geaendert_am
    )
    return EinstellungenGespeichert(geaendert_am=stand)
