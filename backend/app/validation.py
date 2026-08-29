"""Turning pydantic's validation errors into sentences a user can act on.

The frontend shows ``detail`` and nothing else, so ``detail`` is where the
usable sentence has to be -- and pydantic's own wording ("Input should be less
than or equal to 90") is both English and about the schema rather than about
what the user typed. Everything below translates the handful of error types
this API can actually produce; anything unmapped falls back to a neutral
German sentence rather than leaking the original.
"""

from __future__ import annotations

from typing import Any

GENERIC = "Die Anfrage ist unvollständig oder ungültig."

# Prefixes pydantic puts in front of a message raised by our own validators.
_OWN_MESSAGE_PREFIXES = ("Value error, ", "Assertion failed, ")

_BY_TYPE: dict[str, str] = {
    "missing": "Diese Angabe fehlt.",
    "json_invalid": "Der Anfragekörper ist kein gültiges JSON.",
    "string_type": "Hier wird Text erwartet.",
    "int_type": "Hier wird eine ganze Zahl erwartet.",
    "int_parsing": "Hier wird eine ganze Zahl erwartet.",
    "float_type": "Hier wird eine Zahl erwartet.",
    "float_parsing": "Hier wird eine Zahl erwartet.",
    "bool_parsing": "Hier wird „true“ oder „false“ erwartet.",
    "datetime_parsing": "Hier wird ein Zeitpunkt im ISO-Format erwartet, etwa 2026-08-29T08:00:00.",
    "datetime_type": "Hier wird ein Zeitpunkt im ISO-Format erwartet.",
    "dict_type": "Hier wird ein Objekt erwartet.",
    "list_type": "Hier wird eine Liste erwartet.",
    "model_attributes_type": "Hier wird ein Objekt erwartet.",
    "url_parsing": "Hier wird eine vollständige Adresse erwartet, etwa https://…",
    "url_scheme": "Die Adresse muss mit http:// oder https:// beginnen.",
    "url_type": "Hier wird eine vollständige Adresse erwartet, etwa https://…",
}


def _from_context(error_type: str, ctx: dict[str, Any]) -> str | None:
    if error_type == "greater_than_equal":
        return f"Der Wert muss mindestens {ctx.get('ge')} betragen."
    if error_type == "greater_than":
        return f"Der Wert muss größer als {ctx.get('gt')} sein."
    if error_type == "less_than_equal":
        return f"Der Wert darf höchstens {ctx.get('le')} betragen."
    if error_type == "less_than":
        return f"Der Wert muss kleiner als {ctx.get('lt')} sein."
    if error_type in ("string_too_long", "too_long"):
        return f"Höchstens {ctx.get('max_length')} Zeichen bzw. Einträge sind erlaubt."
    if error_type in ("string_too_short", "too_short"):
        return f"Mindestens {ctx.get('min_length')} Zeichen bzw. Einträge werden benötigt."
    if error_type == "literal_error":
        return f"Erlaubt ist nur: {ctx.get('expected')}."
    return None


def _field_name(location: tuple[Any, ...]) -> str | None:
    """The field a message belongs to, or None for a whole-request error."""

    parts = [str(part) for part in location if part not in ("body", "query", "path")]
    return ".".join(parts) or None


def _message(error: dict[str, Any]) -> tuple[str, bool]:
    """One error as (German sentence, came from one of our own validators)."""

    raw = str(error.get("msg") or "")
    for prefix in _OWN_MESSAGE_PREFIXES:
        if raw.startswith(prefix):
            return raw[len(prefix) :], True
    error_type = str(error.get("type") or "")
    ctx = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
    return _from_context(error_type, ctx) or _BY_TYPE.get(error_type) or "Die Angabe ist ungültig.", False


def readable_validation_error(errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Body for a 422: a readable ``detail`` plus the machine-readable fields."""

    felder: list[dict[str, Any]] = []
    sentences: list[str] = []
    for error in errors:
        location = tuple(error.get("loc", ()))
        text, own = _message(error)
        name = _field_name(location)
        felder.append(
            {"pfad": [str(part) for part in location], "meldung": text}
        )
        # Our own validators speak about the request as a whole and already
        # name the fields they mean; pydantic's do not.
        sentences.append(text if own or not name else f"„{name}“: {text}")

    unique: list[str] = []
    for sentence in sentences:
        if sentence not in unique:
            unique.append(sentence)
    return {"detail": " ".join(unique) or GENERIC, "felder": felder}
