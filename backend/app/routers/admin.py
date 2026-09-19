"""/api/verwaltung/... -- the operator's own view of this deployment.

Every route here is behind ``current_admin``: signed in, and either named in
``ADMIN_ACCOUNTS`` or carrying the flag in the database. Nothing is behind a
hidden URL -- the frontend only *draws* the menu entry from
``/api/auth/me``, and a browser that asks anyway is refused here.

What the area deliberately does not do:

* **It does not read anybody's plot.** The account list counts documents and
  measures them; the share list holds tokens and dates. An operator can see how
  much there is and can remove it, and cannot look at it. The one exception is
  the one they already have: their own.
* **It does not invent history.** Everything on the statistics page comes from
  counters written since this feature was deployed. An empty chart means
  nothing was counted, and the page says so rather than drawing a flat line.
* **It does not offer a repair it cannot make.** The buttons are the ones the
  backend can actually carry out: promote, block, delete, clear a cache, sweep,
  empty a table.

The wipe is two requests, not one: ``/datenbank/vorbereiten`` hands out a
single-use key with a short life, and ``/datenbank/leeren`` needs that key
*and* the sentence typed back. A double confirmation that is only in the
browser is a confirmation the browser can skip.
"""

from __future__ import annotations

import logging
import secrets
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Path as PathParam, Query, Response
from fastapi.responses import StreamingResponse

from .. import telemetry
from .. import jobs as jobslib
from ..deps import admin_store, current_admin, llm_prices, storage_service
from ..errors import AppError, BadRequestError, ConflictError, NotFoundError
from ..prices import Prices
from ..schemas import (
    Ansage,
    AnsageAnfrage,
    Dienstlage,
    Fehlereintrag,
    Fehlerliste,
    JobZeile,
    Jobs,
    Freigabenliste,
    FreigabeZeile,
    Konten,
    Konto,
    LoeschAnfrage,
    LoeschErgebnis,
    LoeschVorbereitung,
    Preisstand,
    Protokoll,
    Protokolleintrag,
    RollenAenderung,
    Sperre,
    SperrAnfrage,
    Statistik,
    VerwaltungsUebersicht,
    Zeitpunktwerte,
    Zwischenspeicher,
)
from ..services.admin import SCOPES, AdminStore
from ..services.oidc import Identity
from ..services.storage import Storage
from ..settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verwaltung", tags=["Verwaltung"])

# Nothing here may sit in a cache: every answer is about the moment it was
# asked, and several of them are about one account.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# The sentence the second confirmation has to carry, and how long the key from
# the first one lives. Two minutes is long enough to read the dialog and short
# enough that a key left in a tab is no use tomorrow.
WIPE_PHRASE = "ALLES LÖSCHEN"
WIPE_KEY_TTL_S = 120

# Outstanding keys: key -> (expiry, account key of the administrator who asked).
# In this process, like the rate limiter and for the same reason -- and with a
# consequence worth knowing: behind several workers the second request has to
# reach the worker that handed the key out, and gets a fresh dialog otherwise.
# A wipe that has to be started twice is the harmless direction.
_wipe_keys: dict[str, tuple[float, str]] = {}

# How far back a window reaches when the caller names no bounds.
_DEFAULT_WINDOW = timedelta(days=1)
# And how far it may reach: a year of hourly buckets is 8 760 rows per service,
# which is a page that renders; ten years is one that does not.
_MAX_WINDOW = timedelta(days=400)


def _window(von: datetime | None, bis: datetime | None) -> tuple[datetime, datetime]:
    """The period asked for, bounded and always with a time zone.

    A naive moment is read as UTC rather than refused: the frontend always
    sends an offset, and a hand-written request that does not is asking about
    a moment, not about a time zone.
    """

    end = bis or datetime.now(timezone.utc)
    start = von or end - _DEFAULT_WINDOW
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise BadRequestError("Das Ende des Zeitraums muss nach seinem Anfang liegen.")
    if end - start > _MAX_WINDOW:
        raise BadRequestError("Der Zeitraum ist zu lang; höchstens 400 Tage auf einmal.")
    return start, end


def _cache_dirs(settings: Settings) -> list[Zwischenspeicher]:
    """Every cache under the cache directory, measured.

    One directory per cache, which is how ``DiskCache`` lays them out. Walked
    rather than asked: the caches are built lazily by the services that use
    them, so a process that has not answered a tile request yet would report
    no tile cache while the files are on disk.
    """

    root = Path(settings.app.cache_dir)
    found: list[Zwischenspeicher] = []
    if not root.is_dir():
        return found
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        files = 0
        size = 0
        for path in directory.rglob("*"):
            if path.is_file():
                files += 1
                try:
                    size += path.stat().st_size
                except OSError:
                    pass
        found.append(Zwischenspeicher(name=directory.name, dateien=files, bytes=size))
    return found


@router.get(
    "/uebersicht",
    response_model=VerwaltungsUebersicht,
    summary="Kennzahlen des Betriebs",
    responses={401: {"description": "Nicht angemeldet"}, 403: {"description": "Kein Verwalter"}},
)
async def overview(
    response: Response,
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> VerwaltungsUebersicht:
    response.headers.update(_NO_STORE)
    store.require_configured()
    settings = get_settings()
    counts = await store.counts()
    return VerwaltungsUebersicht(
        konten=counts["konten"],
        grundstuecke=counts["grundstuecke"],
        freigaben=counts["freigaben"],
        sperren=counts["sperren"],
        fehler=counts["fehler"],
        protokoll=counts["protokoll"],
        datenbank_bytes=counts["bytes"],
        cache_bytes=sum(entry.bytes for entry in _cache_dirs(settings)),
        verwalter=await store.admin_count(),
        aus_konfiguration=len(settings.admin.bootstrap_accounts),
    )


@router.get(
    "/statistik",
    response_model=Statistik,
    summary="Aufrufe, Fehler und Tokens über einen Zeitraum",
)
async def statistics(
    response: Response,
    von: datetime | None = Query(default=None, description="Anfang des Zeitraums."),
    bis: datetime | None = Query(default=None, description="Ende des Zeitraums."),
    raster: str = Query(default="stunde", pattern="^(stunde|tag)$"),
    bereich: str | None = Query(default=None, pattern="^(anfrage|dienst|modell|suche)$"),
    vergleich: bool = Query(
        default=False, description="Denselben, gleich langen Zeitraum davor mitliefern."
    ),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
    prices: Prices = Depends(llm_prices),
) -> Statistik:
    """The numbers for one period -- and, if asked, the one before it.

    The comparison is a *choice* rather than always-on: it doubles the work and
    it is only meaningful where the two periods are comparable. It is the same
    length, immediately before, so „diese Woche gegen letzte" is exactly what
    it says.

    Cost is attached to the per-service rows and to the total, never to the
    points of the series: a bucket holds the tokens of every model at once, and
    a price belongs to one model. Splitting the series by model would be a
    second series per model, which is a different chart.
    """

    response.headers.update(_NO_STORE)
    store.require_configured()
    start, end = _window(von, bis)
    series = await store.series(start, end, grid=raster, area=bereich)
    per_service = await store.by_service(start, end)
    rows = [Zeitpunktwerte(**row) for row in per_service]
    total = Zeitpunktwerte()
    for row in rows:
        row.kosten_eur = _cost(prices, row)
        total.anfragen += row.anfragen
        total.fehler += row.fehler
        total.limitiert += row.limitiert
        total.dauer_ms += row.dauer_ms
        total.tokens_ein += row.tokens_ein
        total.tokens_aus += row.tokens_aus
        if row.kosten_eur is not None:
            total.kosten_eur = (total.kosten_eur or 0.0) + row.kosten_eur

    before: list[Zeitpunktwerte] | None = None
    before_total: Zeitpunktwerte | None = None
    if vergleich:
        span = end - start
        earlier = await store.series(start - span, start, grid=raster, area=bereich)
        before = [Zeitpunktwerte(**point) for point in earlier]
        before_rows = await store.by_service(start - span, start)
        before_total = Zeitpunktwerte()
        for row_before in before_rows:
            before_total.anfragen += row_before["anfragen"]
            before_total.fehler += row_before["fehler"]
            before_total.limitiert += row_before["limitiert"]
            before_total.dauer_ms += row_before["dauer_ms"]
            before_total.tokens_ein += row_before["tokens_ein"]
            before_total.tokens_aus += row_before["tokens_aus"]

    return Statistik(
        von=start,
        bis=end,
        raster=raster,
        zeitreihe=[Zeitpunktwerte(**point) for point in series],
        nach_dienst=rows,
        summe=total,
        vergleich=before,
        vergleich_summe=before_total,
        preise=_price_state(prices),
    )


def _cost(prices: Prices, row: Zeitpunktwerte) -> float | None:
    """What one service row cost, or nothing at all.

    Only the model area has a price: a call to the cadastre costs nothing per
    request, and putting 0,00 € next to it would read as a measurement.
    """

    if row.bereich != "modell" or not row.dienst:
        return None
    return prices.euro(row.dienst, row.tokens_ein, row.tokens_aus)


def _price_state(prices: Prices) -> Preisstand:
    return Preisstand(
        vorhanden=prices.usable,
        stand=prices.stand,
        usd_je_eur=prices.usd_per_euro,
        kurs_stand=prices.rate_day,
        quellen=prices.sources,
        modelle=len(prices.models),
        hinweis=prices.problem
        or (
            None
            if prices.usable
            else "Die Preisliste enthält keinen Kurs; ohne ihn lässt sich nicht umrechnen."
        ),
    )


@router.get("/konten", response_model=Konten, summary="Konten und ihr Verbrauch")
async def accounts(
    response: Response,
    von: datetime | None = Query(default=None),
    bis: datetime | None = Query(default=None),
    suche: str = Query(default="", max_length=120, description="Teil eines Namens oder einer Kennung."),
    sortierung: str = Query(default="anfragen", pattern="^(anfragen|neu|umfang|name)$"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Konten:
    """One page of the accounts.

    Paged from the first version rather than when it hurts: this is the table
    that grows with the deployment, and „alle Konten" at a thousand of them is
    a page nobody can read and a megabyte nobody needs.
    """

    response.headers.update(_NO_STORE)
    store.require_configured()
    start, end = _window(von, bis)
    rows, total = await store.accounts(
        start, end, limit=limit, offset=offset, search=suche, order=sortierung
    )
    return Konten(
        von=start,
        bis=end,
        konten=[Konto(**vars(row)) for row in rows],
        gesamt=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/konten/{kennung}/auskunft",
    summary="Alles, was über ein Konto gespeichert ist (Art. 15 DSGVO)",
    responses={404: {"description": "Für diese Kennung ist hier nichts gespeichert"}},
)
async def account_record(
    kennung: str = PathParam(min_length=8, max_length=64, pattern="^[0-9a-f]+$"),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Response:
    """The whole record of one account, as a file.

    For the request a person is entitled to make and the operator has to
    answer. Complete rather than summarised -- the plot documents and the
    settings go in verbatim, because an Auskunft that abridged what is held
    would be one more thing to take on trust. It is an administrative act on
    somebody else's data, so it lands in the audit trail like every other.
    """

    store.require_configured()
    record = await store.account_record(kennung)
    if record is None:
        raise NotFoundError(
            "Für diese Kennung ist hier nichts gespeichert. Ein Konto entsteht erst mit "
            "dem ersten gesicherten Grundstück."
        )
    await store.note(
        kennung=admin.account_key, name=admin.name, action="auskunft-erteilt", target=kennung
    )
    import json as _json

    body = _json.dumps(record, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="auskunft-{kennung}.json"',
            **_NO_STORE,
        },
    )


@router.post(
    "/konten/{kennung}/rolle",
    response_model=Konto,
    summary="Verwaltungsrecht geben oder nehmen",
    responses={
        404: {"description": "Für diese Kennung ist hier nichts gespeichert"},
        409: {"description": "Das wäre der letzte Verwalter"},
    },
)
async def set_role(
    response: Response,
    kennung: str = PathParam(min_length=8, max_length=64, pattern="^[0-9a-f]+$"),
    change: RollenAenderung = Body(),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Konto:
    """Promote or demote one account.

    Two refusals, and both are about locking the door from inside. Demoting the
    last administrator in the database is refused unless the configuration
    names one, because the area would then be reachable by nobody; and an
    account with no row here cannot be promoted, because there is nothing to
    write the flag on -- it appears the moment they store something.
    """

    response.headers.update(_NO_STORE)
    store.require_configured()
    settings = get_settings()
    if not change.ist_admin:
        remaining = await store.admin_count() - 1
        if remaining <= 0 and not settings.admin.bootstrap_accounts:
            raise ConflictError(
                "Das ist der letzte Verwalter. Bitte zuerst jemand anderen zum "
                "Verwalter machen — sonst kommt niemand mehr in diesen Bereich."
            )
    if not await store.set_admin(kennung, change.ist_admin):
        raise NotFoundError(
            "Für diese Kennung ist hier nichts gespeichert. Ein Konto entsteht erst, "
            "wenn zum ersten Mal etwas gesichert wird — vorher lässt sich kein "
            "Verwaltungsrecht daran hängen."
        )
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="rolle" if change.ist_admin else "rolle-entzogen",
        target=kennung,
        details={"ist_admin": change.ist_admin},
    )
    return await _one_account(store, kennung)


@router.post("/konten/{kennung}/sperre", response_model=Sperre, summary="Konto sperren")
async def block(
    response: Response,
    kennung: str = PathParam(min_length=8, max_length=64, pattern="^[0-9a-f]+$"),
    request: SperrAnfrage = Body(),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Sperre:
    """Stop an account now, here, and everywhere else within one flush.

    Written to this process first so the very next request from that account is
    refused by the worker that serves it, and to the database in the same call
    so the other workers pick it up and the interface can show it.
    """

    response.headers.update(_NO_STORE)
    store.require_configured()
    if kennung == admin.account_key:
        raise ConflictError("Das eigene Konto lässt sich hier nicht sperren.")
    reason = request.grund.strip() or "Vom Betreiber gesperrt."
    placed = await store.set_block(
        kennung, minutes=request.minuten, grund=reason, durch=admin.account_key
    )
    telemetry.recorder().set_block(placed)
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="sperre",
        target=kennung,
        details={"minuten": request.minuten, "grund": reason},
    )
    return Sperre(kennung=placed.kennung, bis=placed.bis, grund=placed.grund, automatisch=False)


@router.delete(
    "/konten/{kennung}/sperre", status_code=204, summary="Sperre aufheben"
)
async def unblock(
    kennung: str = PathParam(min_length=8, max_length=64, pattern="^[0-9a-f]+$"),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Response:
    store.require_configured()
    await store.clear_block(kennung)
    telemetry.recorder().clear_block(kennung)
    await store.note(
        kennung=admin.account_key, name=admin.name, action="sperre-aufgehoben", target=kennung
    )
    return Response(status_code=204, headers=dict(_NO_STORE))


@router.delete("/konten/{kennung}", status_code=204, summary="Konto und seine Daten löschen")
async def delete_account(
    kennung: str = PathParam(min_length=8, max_length=64, pattern="^[0-9a-f]+$"),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Response:
    """Erase one account: its plots, its settings and its shared links.

    204 whether or not a row was there: "already gone" is the outcome asked
    for. Deleting one's own is refused -- it would end the session of the
    person doing it, half-way through the work they are doing.
    """

    store.require_configured()
    if kennung == admin.account_key:
        raise ConflictError(
            "Das eigene Konto lässt sich hier nicht löschen — dafür gibt es die Kontoseite."
        )
    removed = await store.delete_account(kennung)
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="konto-geloescht",
        target=kennung,
        details={"vorhanden": removed},
    )
    return Response(status_code=204, headers=dict(_NO_STORE))


@router.get("/fehler", response_model=Fehlerliste, summary="Fehler der letzten Zeit")
async def errors(
    response: Response,
    von: datetime | None = Query(default=None),
    bis: datetime | None = Query(default=None),
    suche: str = Query(default="", max_length=200, description="Teil eines Dienstes, einer Route oder einer Meldung."),
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Fehlerliste:
    """The stored failures -- or, without a database, this process's own.

    The fallback is the point: a deployment that has no server storage still
    fails, and an operations page that goes blank exactly when something is
    wrong is worse than one that says where its numbers come from.
    """

    response.headers.update(_NO_STORE)
    start, end = _window(von, bis)
    if not store.configured:
        held = [
            entry
            for entry in telemetry.recorder().recent_errors(10000)
            if start <= entry.zeit < end and _matches(entry, suche)
        ]
        page = held[offset : offset + limit]
        return Fehlerliste(
            von=start,
            bis=end,
            quelle="speicher",
            eintraege=[Fehlereintrag(**entry.as_row()) for entry in page],
            gesamt=len(held),
            offset=offset,
            limit=limit,
        )
    rows, total = await store.errors(start, end, limit=limit, offset=offset, search=suche)
    return Fehlerliste(
        von=start,
        bis=end,
        quelle="datenbank",
        eintraege=[Fehlereintrag(**row) for row in rows],
        gesamt=total,
        offset=offset,
        limit=limit,
    )


def _matches(entry: telemetry.ErrorEntry, search: str) -> bool:
    """The same search the SQL does, over the ring this process keeps.

    Two implementations of one filter is a thing to be uneasy about; the
    alternative is a page whose search box works only on deployments that have
    a database, which is worse.
    """

    needle = search.strip().lower()
    if not needle:
        return True
    return any(
        needle in (value or "").lower() for value in (entry.dienst, entry.route, entry.meldung)
    )


@router.get(
    "/fehler.ndjson",
    summary="Fehler als NDJSON herunterladen",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/x-ndjson": {}}}},
)
async def errors_download(
    von: datetime | None = Query(default=None),
    bis: datetime | None = Query(default=None),
    anzahl: int = Query(default=5000, ge=1, le=50000),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> StreamingResponse:
    """One JSON object per line -- the shape a log is read with.

    NDJSON rather than CSV: the messages are German sentences with commas in
    them, and a CSV of those is a file that opens wrong in one spreadsheet out
    of three. Every tool that reads logs reads this, ``jq`` included.
    """

    start, end = _window(von, bis)
    if store.configured:
        rows, _total = await store.errors(start, end, limit=anzahl)
    else:
        rows = [
            entry.as_row()
            for entry in telemetry.recorder().recent_errors(anzahl)
            if start <= entry.zeit < end
        ]

    def lines() -> Any:
        import json

        for row in rows:
            yield json.dumps(row, ensure_ascii=False, default=str) + "\n"

    stamp = start.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="fehler-{stamp}.ndjson"',
            **_NO_STORE,
        },
    )


@router.get("/freigaben", response_model=Freigabenliste, summary="Offene Freigabe-Links")
async def shares(
    response: Response,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Freigabenliste:
    response.headers.update(_NO_STORE)
    store.require_configured()
    rows, total = await store.shares(limit=limit, offset=offset)
    return Freigabenliste(
        gesamt=total,
        offset=offset,
        limit=limit,
        freigaben=[
            FreigabeZeile(
                token=row["id"],
                angelegt=row["angelegt"],
                laeuft_ab=row["laeuft_ab"],
                kennung=row["kennung"],
                anzeigename=row["anzeigename"],
                bytes=int(row["bytes"] or 0),
            )
            for row in rows
        ]
    )


@router.delete("/freigaben/{token}", status_code=204, summary="Freigabe zurückziehen")
async def delete_share(
    token: str = PathParam(min_length=8, max_length=200),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Response:
    store.require_configured()
    removed = await store.delete_share(token)
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="freigabe-zurueckgezogen",
        target=token,
        details={"vorhanden": removed},
    )
    return Response(status_code=204, headers=dict(_NO_STORE))


@router.post("/freigaben/aufraeumen", summary="Abgelaufene Freigaben entfernen")
async def sweep_shares(
    admin: Identity = Depends(current_admin),
    storage: Storage = Depends(storage_service),
    store: AdminStore = Depends(admin_store),
) -> dict[str, int]:
    storage.require_configured()
    removed = await storage.sweep_shares()
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="freigaben-aufgeraeumt",
        details={"entfernt": removed},
    )
    return {"entfernt": removed}


@router.get("/dienste", response_model=Dienstlage, summary="Zwischenspeicher und Kontingente")
async def services(
    response: Response, _: Identity = Depends(current_admin)
) -> Dienstlage:
    response.headers.update(_NO_STORE)
    settings = get_settings()
    caches = _cache_dirs(settings)
    return Dienstlage(
        caches=caches,
        cache_bytes=sum(entry.bytes for entry in caches),
        cache_grenze_bytes=settings.app.cache_max_bytes,
        kontingent_dienste=settings.rate_limit.service_calls,
        kontingent_kacheln=settings.rate_limit.map_tiles,
        kontingent_fenster_s=settings.rate_limit.window_s,
        kontingent_aktiv=settings.rate_limit.enabled,
        sperre_ab=settings.admin.burst_calls,
        sperre_fenster_s=settings.admin.burst_window_s,
        sperre_dauer_min=settings.admin.auto_block_minutes,
        aufbewahrung_tage=settings.admin.retention_days,
    )


@router.post("/cache/leeren", summary="Einen Zwischenspeicher leeren")
async def clear_cache(
    name: str = Body(embed=True, min_length=1, max_length=64),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> dict[str, str]:
    """Delete one cache directory -- by name, and only a name.

    The name is matched against what is actually on disk rather than joined
    into a path: ``..`` in a request that deletes a directory tree is the one
    mistake in this file that could not be taken back.
    """

    settings = get_settings()
    root = Path(settings.app.cache_dir)
    target = next((entry for entry in root.iterdir() if entry.is_dir() and entry.name == name), None)
    if target is None:
        raise NotFoundError("Diesen Zwischenspeicher gibt es auf diesem Server nicht.")
    shutil.rmtree(target, ignore_errors=True)
    if store.configured:
        await store.note(
            kennung=admin.account_key, name=admin.name, action="cache-geleert", target=name
        )
    return {"geleert": name}


@router.get("/jobs", response_model=Jobs, summary="Wiederkehrende Läufe und ihr Zustand")
async def job_list(
    response: Response, _: Identity = Depends(current_admin)
) -> Jobs:
    """What is scheduled, when it last ran, and whether anybody is there to run it.

    The list and the records are the scheduler's own files -- see
    ``app/jobs.py``. Reading them here rather than keeping a second copy means
    the page cannot disagree with ``run_jobs.py list``.
    """

    response.headers.update(_NO_STORE)
    settings = get_settings().admin
    try:
        found = jobslib.describe(settings.jobs_file, settings.state_dir)
    except (OSError, ValueError, KeyError) as error:
        return Jobs(jobs=[], hinweis=f"Die Job-Liste ist nicht lesbar ({settings.jobs_file}): {error}")
    seen = jobslib.scheduler_seen(settings.state_dir)
    alive = jobslib.scheduler_alive(settings.state_dir)
    return Jobs(
        jobs=[
            JobZeile(
                name=job.name,
                zeitplan=job.schedule,
                warum=job.why,
                befehl=job.command,
                zuletzt=_moment(job.last_start),
                exit_code=job.last_exit_code,
                dauer_s=job.last_duration_s,
                laeuft=job.running,
                angefordert=job.requested,
            )
            for job in found
        ],
        scheduler_zuletzt=_moment(seen),
        scheduler_laeuft=alive,
        hinweis=None
        if alive
        else (
            "Zurzeit läuft kein Scheduler. Angeforderte Läufe bleiben liegen, bis einer "
            "startet — mit „docker compose --profile scheduled-jobs up -d“."
        ),
    )


@router.post("/jobs/{name}/starten", response_model=JobZeile, summary="Einen Lauf anfordern")
async def start_job(
    name: str = PathParam(min_length=1, max_length=64, pattern="^[a-z0-9-]+$"),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> JobZeile:
    """Ask the scheduler to run this job on its next tick.

    Not run here: the heavy jobs write into a directory this process mounts
    read-only and take minutes, so the request goes into the directory both
    containers share and the scheduler picks it up -- where the privileges, the
    writable mount and the lock against a second copy already are.
    """

    settings = get_settings().admin
    try:
        found = {job.name: job for job in jobslib.describe(settings.jobs_file, settings.state_dir)}
    except (OSError, ValueError, KeyError) as error:
        raise NotFoundError(f"Die Job-Liste ist nicht lesbar: {error}") from error
    if name not in found:
        raise NotFoundError("Einen Lauf dieses Namens gibt es auf diesem Server nicht.")
    try:
        jobslib.request_run(settings.state_dir, name, by=admin.account_key)
    except OSError as error:
        raise ConflictError(
            f"Der Lauf konnte nicht angefordert werden ({error}). Ist das Verzeichnis "
            f"{settings.state_dir} eingebunden und beschreibbar?"
        ) from error
    if store.configured:
        await store.note(
            kennung=admin.account_key, name=admin.name, action="lauf-angefordert", target=name
        )
    job = jobslib.describe(settings.jobs_file, settings.state_dir)
    entry = next(one for one in job if one.name == name)
    return JobZeile(
        name=entry.name,
        zeitplan=entry.schedule,
        warum=entry.why,
        befehl=entry.command,
        zuletzt=_moment(entry.last_start),
        exit_code=entry.last_exit_code,
        dauer_s=entry.last_duration_s,
        laeuft=entry.running,
        angefordert=entry.requested,
    )


@router.put("/ansage", response_model=Ansage, summary="Betriebsansage setzen")
async def set_announcement(
    request: AnsageAnfrage = Body(),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Ansage:
    """The banner every visitor sees, in the operator's own words.

    Composed here rather than generated: this is the one text in the
    application a person writes, because it is the one thing no template can
    know -- „die Kataster-Schnittstelle antwortet seit heute früh nicht".
    """

    store.require_configured()
    saved = await store.set_announcement(
        text=request.text.strip(),
        art=request.art,
        sichtbar=request.sichtbar and bool(request.text.strip()),
        bis=request.bis,
        von=admin.account_key,
    )
    await store.note(
        kennung=admin.account_key,
        name=admin.name,
        action="ansage",
        details={"sichtbar": saved["sichtbar"], "art": saved["art"]},
    )
    return Ansage(**{key: saved[key] for key in ("text", "art", "sichtbar", "bis", "geaendert_am")})


@router.get("/ansage", response_model=Ansage, summary="Betriebsansage, auch wenn sie aus ist")
async def announcement_for_admin(
    response: Response,
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Ansage:
    response.headers.update(_NO_STORE)
    store.require_configured()
    saved = await store.announcement()
    if saved is None:
        return Ansage()
    return Ansage(**{key: saved[key] for key in ("text", "art", "sichtbar", "bis", "geaendert_am")})


def _moment(value: str | None) -> datetime | None:
    """An ISO moment out of a job record, or nothing.

    The records are written by a separate process, so a field that is missing,
    empty or not a date at all is a state this has to survive rather than a
    reason to fail the page.
    """

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.get("/protokoll", response_model=Protokoll, summary="Was Verwalter geändert haben")
async def audit(
    response: Response,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Protokoll:
    response.headers.update(_NO_STORE)
    store.require_configured()
    rows, total = await store.audit(limit=limit, offset=offset)
    return Protokoll(
        eintraege=[Protokolleintrag(**row) for row in rows],
        gesamt=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/datenbank/vorbereiten",
    response_model=LoeschVorbereitung,
    summary="Erste Bestätigung für das Leeren der Datenbank",
)
async def prepare_wipe(
    admin: Identity = Depends(current_admin), store: AdminStore = Depends(admin_store)
) -> LoeschVorbereitung:
    store.require_configured()
    _forget_expired_keys()
    key = secrets.token_urlsafe(24)
    _wipe_keys[key] = (time.monotonic() + WIPE_KEY_TTL_S, admin.account_key)
    return LoeschVorbereitung(
        schluessel=key,
        gueltig_bis=datetime.now(timezone.utc) + timedelta(seconds=WIPE_KEY_TTL_S),
        satz=WIPE_PHRASE,
    )


@router.post(
    "/datenbank/leeren",
    response_model=LoeschErgebnis,
    summary="Datenbank leeren",
    responses={400: {"description": "Schlüssel oder Wortlaut stimmen nicht"}},
)
async def wipe(
    request: LoeschAnfrage = Body(),
    admin: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> LoeschErgebnis:
    """The red button. Both confirmations are checked here, not in the browser.

    The key comes from ``/datenbank/vorbereiten``, is single use, expires, and
    only counts for the administrator who asked for it -- a key is not a thing
    to pass around. The sentence has to be typed back exactly. What the wipe
    never touches is the audit trail: the entry written a line below is the
    record of this very act, and a wipe that erased it would leave nobody
    answerable for it.
    """

    store.require_configured()
    _forget_expired_keys()
    holder = _wipe_keys.pop(request.schluessel, None)
    if holder is None or holder[1] != admin.account_key:
        raise BadRequestError(
            "Diese Bestätigung ist abgelaufen oder gehört zu einer anderen Anmeldung. "
            "Bitte erneut beginnen."
        )
    if request.bestaetigung.strip() != WIPE_PHRASE:
        raise BadRequestError(
            f"Zum Löschen muss „{WIPE_PHRASE}“ genau so eingetippt werden."
        )
    scopes = [scope for scope in request.umfang if scope in SCOPES]
    if not scopes:
        raise BadRequestError(
            "Es ist nicht ausgewählt, was geleert werden soll: „konten“, "
            "„statistik“ oder „sperren“."
        )
    # Written before the tables go, so the entry exists even if the wipe itself
    # fails half-way -- "somebody pressed this" is the fact worth keeping.
    await store.note(
        kennung=admin.account_key, name=admin.name, action="datenbank-geleert", details={"umfang": scopes}
    )
    removed = await store.wipe(scopes)
    if "sperren" in scopes:
        # The table is empty, so this process must not keep enforcing what was
        # in it; the other workers learn the same thing on their next flush.
        telemetry.recorder().adopt_blocks([])
    logger.warning("Database emptied by %s: %s", admin.account_key, removed)
    return LoeschErgebnis(geleert=removed)


# The one route in this file that is not behind an administrator. It is the
# banner, and a banner nobody can read is not a banner -- so it answers
# everybody, signed in or not, and carries nothing that was not written to be
# public. Its own router because a prefix is one per router.
public = APIRouter(prefix="/api", tags=["Betrieb"])


@public.get("/ansage", response_model=Ansage, summary="Betriebsansage")
async def announcement(
    response: Response, store: AdminStore = Depends(admin_store)
) -> Ansage:
    """What the deployment currently says to everybody.

    An empty, invisible announcement is the normal state and answers 200 with
    ``sichtbar: false`` rather than 404: the frontend asks once per page load,
    and a 404 in the console on every load of a perfectly healthy deployment is
    noise that hides the real ones.
    """

    response.headers.update({"Cache-Control": "no-cache"})
    if not store.configured:
        return Ansage()
    try:
        saved = await store.announcement()
    except AppError:
        # The database is down. That is worth an error on the routes that need
        # it, and not worth a broken page for everybody else.
        return Ansage()
    if saved is None or not saved["sichtbar"]:
        return Ansage()
    if saved["bis"] is not None and saved["bis"] <= datetime.now(timezone.utc):
        # Past its end. Left in the table on purpose -- an announcement that
        # deleted itself could not be switched back on with one click.
        return Ansage()
    return Ansage(**{key: saved[key] for key in ("text", "art", "sichtbar", "bis", "geaendert_am")})


def _forget_expired_keys() -> None:
    now = time.monotonic()
    for key, (expiry, _) in list(_wipe_keys.items()):
        if expiry <= now:
            del _wipe_keys[key]


async def _one_account(store: AdminStore, kennung: str) -> Konto:
    """The row that was just changed, so the interface can redraw one line."""

    end = datetime.now(timezone.utc)
    rows, _total = await store.accounts(end - _DEFAULT_WINDOW, end, search=kennung, limit=5)
    for row in rows:
        if row.kennung == kennung:
            return Konto(**vars(row))
    raise NotFoundError("Für diese Kennung ist hier nichts gespeichert.")
