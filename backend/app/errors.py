"""Application errors.

Every message here reaches a user, so every message here is German. The
HTTP mapping lives in ``app.main``.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for errors that carry a user-facing German message."""

    status_code = 500
    default_message = "Unerwarteter Fehler im Server."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)

    @property
    def body(self) -> dict[str, Any]:
        """The whole JSON answer, not only the sentence.

        Almost every error is exactly its ``detail``. A conflict is the
        exception: the browser has to be able to show what is stored, so that
        travels in the same body -- see ``VersionConflictError``.
        """

        return {"detail": self.message}

    @property
    def headers(self) -> dict[str, str] | None:
        """Response headers this error needs, if any.

        Almost none does; a sentence in ``detail`` is the whole answer. The
        exception is 429, where ``Retry-After`` is the machine-readable half of
        what the sentence says in words.
        """

        return None


class BadRequestError(AppError):
    status_code = 400
    default_message = "Die Anfrage konnte so nicht verarbeitet werden."


class NotFoundError(AppError):
    status_code = 404
    default_message = "Für diese Anfrage wurden keine Daten gefunden."


class NotConfiguredError(AppError):
    status_code = 503
    default_message = "Dieser Dienst ist auf dem Server nicht konfiguriert."


class UpstreamError(AppError):
    """An external service answered, but not usefully."""

    status_code = 502
    default_message = "Ein externer Dienst hat nicht verwertbar geantwortet."


class UpstreamTimeout(AppError):
    status_code = 504
    default_message = "Ein externer Dienst hat nicht rechtzeitig geantwortet."


class UnauthorizedError(AppError):
    """Signed out, on a route that only exists for an account."""

    status_code = 401
    default_message = "Bitte zuerst anmelden."


class ForbiddenError(AppError):
    """Signed in, and still not allowed -- or not allowed any more.

    Two callers reach this: somebody who asked for the administration area
    without being an administrator, and an account that is blocked. Both get
    403 rather than 404: pretending the area does not exist would leave an
    administrator who lost the flag looking for a bug, and a blocked account
    has to be told it is blocked, or it will simply keep trying.
    """

    status_code = 403
    default_message = "Dieser Bereich ist für dieses Konto nicht freigegeben."


class ConflictError(AppError):
    """The request is fine; the state it would produce is not."""

    status_code = 409
    default_message = "Das lässt sich im gespeicherten Stand so nicht ablegen."


class VersionConflictError(ConflictError):
    """Somebody else wrote first.

    A contradiction is shown, never resolved quietly: no merge, no last-write-
    wins. The answer carries what is stored under ``aktuell`` so the interface
    can put both to the user. ``None`` is a legitimate value for it -- the row
    may have been deleted elsewhere, and inventing one back would be the same
    silent resolution.
    """

    default_message = "Dieser Stand wurde inzwischen an anderer Stelle geändert."

    def __init__(self, message: str | None = None, *, aktuell: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.aktuell = aktuell

    @property
    def body(self) -> dict[str, Any]:
        return {"detail": self.message, "aktuell": self.aktuell}


class PayloadTooLargeError(AppError):
    status_code = 413
    default_message = "Die Anfrage ist zu groß."


class RateLimitedError(AppError):
    """The account (or the peer) has spent its budget of outward calls.

    Not a fault and not an accusation: the message says what applies and when
    it continues, and ``Retry-After`` says the same in seconds. See
    ``app/ratelimit.py`` for why there is a budget at all.
    """

    status_code = 429
    default_message = (
        "Das Abrufkontingent für diesen Zugang ist vorerst erreicht. "
        "Bitte in einigen Minuten noch einmal versuchen."
    )

    def __init__(self, message: str | None = None, *, retry_after_s: int = 60) -> None:
        super().__init__(message)
        self.retry_after_s = max(1, int(retry_after_s))

    @property
    def headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_s)}
