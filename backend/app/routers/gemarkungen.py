"""GET /api/gemarkungen -- the cadastral districts an input mask offers as a choice.

Served whole by default. 5 339 districts are about half a megabyte of JSON, the
list is the same for everybody, and a browser that holds it can filter without
asking again; ``q`` exists for the caller that would rather not hold it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ..deps import gemarkung_directory
from ..errors import NotConfiguredError
from ..gemarkung_index import GemarkungDirectory
from ..schemas import Gemarkung, GemarkungenResponse
from ..settings import Settings, get_settings

router = APIRouter(prefix="/api", tags=["Flurstücke"])

NOT_BUILT = (
    "Das Gemarkungsverzeichnis ist auf diesem Server nicht vorhanden. Es wird "
    "einmalig aus dem Katasterdienst (ALKIS) erzeugt: "
    "python scripts/build_gemarkung_index.py. Bis dahin lässt sich die Gemarkung "
    "von Hand eintragen — Name oder sechsstelliger Schlüssel, beides wird erkannt."
)


@router.get(
    "/gemarkungen",
    response_model=GemarkungenResponse,
    summary="Gemarkungen suchen",
)
async def gemarkungen(
    response: Response,
    q: str | None = Query(
        default=None,
        max_length=100,
        description=(
            "Teilstring in Name oder Schlüssel. Groß-/Kleinschreibung und Umlaute "
            "sind egal: „molkau“, „moelkau“ und „Mölkau“ finden dasselbe. "
            "Ohne Angabe kommt das vollständige Verzeichnis."
        ),
    ),
    directory: GemarkungDirectory | None = Depends(gemarkung_directory),
    settings: Settings = Depends(get_settings),
) -> GemarkungenResponse:
    # A missing file is a server that was never set up, not an empty Saxony.
    if directory is None:
        raise NotConfiguredError(NOT_BUILT)
    response.headers["Cache-Control"] = (
        f"public, max-age={settings.alkis.gemarkung_cache_ttl_s}"
    )
    response.headers["X-Attribution"] = "GeoSN, dl-de/by-2-0"
    return GemarkungenResponse(
        stand=directory.stand,
        gemarkungen=[Gemarkung(**entry.as_dict()) for entry in directory.search(q)],
    )
