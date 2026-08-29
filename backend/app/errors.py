"""Application errors.

Every message here reaches a user, so every message here is German. The
HTTP mapping lives in ``app.main``.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for errors that carry a user-facing German message."""

    status_code = 500
    default_message = "Unerwarteter Fehler im Server."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


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
