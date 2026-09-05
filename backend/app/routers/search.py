"""POST /api/parcels/search -- a listing to the parcel it is selling.

Two shapes of the same run. The streaming one is what the interface uses: the
map has to grow while the search is going, and a search that shows nothing for
two minutes is a search nobody trusts.

**NDJSON over a chunked POST response**, not Server-Sent Events. ``EventSource``
can only GET, so the indicia would have to be posted first and fetched back
under an id -- server-side job state, in a backend that deliberately has no
database and nothing to clean it up with. One endpoint, one call, one JSON
object per line. ``frontend/nginx.conf`` already sets ``proxy_buffering off``
for ``/api/``, so this needs no configuration change.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..deps import alkis_service, gemarkung_directory
from ..gemarkung_index import GemarkungDirectory
from ..schemas import ParcelSearchRequest, ParcelSearchResponse, SuchEreignis
from ..search import run_search
from ..services.alkis import AlkisService

router = APIRouter(prefix="/api/parcels", tags=["Flurstücke"])


def _line(event: SuchEreignis) -> bytes:
    return json.dumps(event.model_dump(mode="json", exclude_none=True), ensure_ascii=False).encode() + b"\n"


async def _stream(
    payload: ParcelSearchRequest,
    alkis: AlkisService,
    directory: GemarkungDirectory | None,
) -> AsyncIterator[bytes]:
    try:
        async for event in run_search(payload, alkis, directory):
            yield _line(event)
    except Exception as exc:  # noqa: BLE001 - the stream has to carry its own failure
        # Headers are long gone by the time an upstream fails, so an error can
        # only travel as one more line. A stream that simply stops leaves the
        # map showing a half-finished search with no explanation.
        message = getattr(exc, "message", None) or (
            "Die Suche ist unterwegs abgebrochen. Bitte noch einmal versuchen."
        )
        yield _line(SuchEreignis(art="fehler", text=message, status="erfolglos"))


@router.post(
    "/search",
    summary="Flurstück aus einem Inserat suchen",
    response_model=None,
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": (
                "Ein JSON-Objekt je Zeile: phase, indiz, konflikt, kandidaten, "
                "ergebnis, fehler. Die Karte wächst mit dem Strom mit."
            ),
        }
    },
)
async def search(
    payload: ParcelSearchRequest,
    alkis: AlkisService = Depends(alkis_service),
    directory: GemarkungDirectory | None = Depends(gemarkung_directory),
) -> StreamingResponse:
    return StreamingResponse(
        _stream(payload, alkis, directory),
        media_type="application/x-ndjson",
        # Nginx is configured for this already; the header says so to anything
        # else that might buffer the answer into uselessness.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/search/complete",
    response_model=ParcelSearchResponse,
    summary="Dieselbe Suche, aber als eine Antwort",
)
async def search_complete(
    payload: ParcelSearchRequest,
    alkis: AlkisService = Depends(alkis_service),
    directory: GemarkungDirectory | None = Depends(gemarkung_directory),
) -> ParcelSearchResponse:
    """The whole run at once, for callers that cannot read a stream.

    Same engine, same order; only the last event carries the answer.
    """

    events: list[SuchEreignis] = []
    async for event in run_search(payload, alkis, directory):
        events.append(event)

    final = events[-1] if events else None
    indicia = [event.indiz for event in events if event.indiz is not None]
    conflicts = {
        event.konflikt.art: event.konflikt for event in events if event.konflikt is not None
    }
    return ParcelSearchResponse(
        status=(final.status if final and final.status else "erfolglos"),
        indizien=indicia,
        konflikte=list(conflicts.values()),
        kandidaten=(final.kandidaten if final and final.kandidaten else []),
        huelle=(
            final.huelle
            if final and final.huelle
            else {"art": "offen", "text": "Die Lage ließ sich nicht eingrenzen."}
        ),
        gemarkung_umriss=final.gemarkung_umriss if final else None,
        anfragen=(final.anfragen if final and final.anfragen else 0),
        hinweis=final.text if final else None,
    )
