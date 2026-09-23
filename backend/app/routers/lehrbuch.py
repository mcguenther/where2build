"""GET /api/lehrbuch -- what a model read that the patterns did not.

A diagnostic view, not a feature. It answers what is in the divergence log so
the pipeline can be improved from real listings rather than from imagined ones,
and it carries nothing personal: a Beleg is scrubbed on the way in and the
listing itself is never stored, only named by a hash.

Read-only and unauthenticated on purpose. There is no account behind any of
this -- the rows are notes about the readers, made while reading somebody's
advert, and the advert is exactly what is not kept. A deployment that does not
want the view open turns the whole thing off by not configuring a model.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import lehrbuch
from ..schemas import Abweichungen, AbweichungZeile
from ..services.lehrbuch import ARTEN, Lehrbuch

router = APIRouter(prefix="/api/lehrbuch", tags=["Lehrbuch"])

# How many rows one call answers. The log is read to write a pattern against a
# handful of sentences, not to be paged through.
MAX_ROWS = 500


@router.get("", response_model=Abweichungen, summary="Abweichungen zwischen Modell und Mustern")
async def divergences(
    art: str | None = Query(
        default=None,
        description=(
            f"Eine von {', '.join(ARTEN)}. Ohne Angabe zeigt die Liste die Befunde "
            "und lässt „einig“ weg — das steht in der Statistik."
        ),
    ),
    feld: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_ROWS),
    book: Lehrbuch = Depends(lehrbuch),
) -> Abweichungen:
    rows = await book.rows(art=art, feld=feld, limit=limit)
    tally = await book.tally()
    return Abweichungen(
        anzahl=len(rows),
        speicher="postgres" if book.pool() is not None else "datei",
        statistik={art: sum(felder.values()) for art, felder in tally.items()},
        je_feld=tally,
        zeilen=[AbweichungZeile.model_validate(row) for row in rows],
    )
