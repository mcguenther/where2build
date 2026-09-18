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
from ..deps import admin_store, current_admin, storage_service
from ..errors import BadRequestError, ConflictError, NotFoundError
from ..schemas import (
    Dienstlage,
    Fehlereintrag,
    Fehlerliste,
    Freigabenliste,
    FreigabeZeile,
    Konten,
    Konto,
    LoeschAnfrage,
    LoeschErgebnis,
    LoeschVorbereitung,
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
    bereich: str | None = Query(default=None, pattern="^(anfrage|dienst|modell)$"),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Statistik:
    response.headers.update(_NO_STORE)
    store.require_configured()
    start, end = _window(von, bis)
    series = await store.series(start, end, grid=raster, area=bereich)
    per_service = await store.by_service(start, end)
    total = Zeitpunktwerte()
    for row in per_service:
        total.anfragen += row["anfragen"]
        total.fehler += row["fehler"]
        total.limitiert += row["limitiert"]
        total.dauer_ms += row["dauer_ms"]
        total.tokens_ein += row["tokens_ein"]
        total.tokens_aus += row["tokens_aus"]
    return Statistik(
        von=start,
        bis=end,
        raster=raster,
        zeitreihe=[Zeitpunktwerte(**point) for point in series],
        nach_dienst=[Zeitpunktwerte(**row) for row in per_service],
        summe=total,
    )


@router.get("/konten", response_model=Konten, summary="Konten und ihr Verbrauch")
async def accounts(
    response: Response,
    von: datetime | None = Query(default=None),
    bis: datetime | None = Query(default=None),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Konten:
    response.headers.update(_NO_STORE)
    store.require_configured()
    start, end = _window(von, bis)
    rows = await store.accounts(start, end)
    return Konten(von=start, bis=end, konten=[Konto(**vars(row)) for row in rows])


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
    anzahl: int = Query(default=200, ge=1, le=2000),
    dienst: str | None = Query(default=None, max_length=120),
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
        entries = [
            Fehlereintrag(**entry.as_row())
            for entry in telemetry.recorder().recent_errors(anzahl)
            if start <= entry.zeit < end and (dienst is None or entry.dienst == dienst)
        ]
        return Fehlerliste(von=start, bis=end, quelle="speicher", eintraege=entries)
    rows = await store.errors(start, end, limit=anzahl, service=dienst)
    return Fehlerliste(
        von=start, bis=end, quelle="datenbank", eintraege=[Fehlereintrag(**row) for row in rows]
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
        rows: list[dict[str, Any]] = await store.errors(start, end, limit=anzahl)
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
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Freigabenliste:
    response.headers.update(_NO_STORE)
    store.require_configured()
    rows = await store.shares()
    return Freigabenliste(
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


@router.get("/protokoll", response_model=Protokoll, summary="Was Verwalter geändert haben")
async def audit(
    response: Response,
    anzahl: int = Query(default=200, ge=1, le=2000),
    _: Identity = Depends(current_admin),
    store: AdminStore = Depends(admin_store),
) -> Protokoll:
    response.headers.update(_NO_STORE)
    store.require_configured()
    rows = await store.audit(limit=anzahl)
    return Protokoll(eintraege=[Protokolleintrag(**row) for row in rows])


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


def _forget_expired_keys() -> None:
    now = time.monotonic()
    for key, (expiry, _) in list(_wipe_keys.items()):
        if expiry <= now:
            del _wipe_keys[key]


async def _one_account(store: AdminStore, kennung: str) -> Konto:
    """The row that was just changed, so the interface can redraw one line."""

    end = datetime.now(timezone.utc)
    rows = await store.accounts(end - _DEFAULT_WINDOW, end)
    for row in rows:
        if row.kennung == kennung:
            return Konto(**vars(row))
    raise NotFoundError("Für diese Kennung ist hier nichts gespeichert.")
