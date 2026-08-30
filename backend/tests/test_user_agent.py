"""Who learns the operator's contact address.

Transitous asks for a way of contact in the User-Agent and gets one. No other
upstream asks, so no other upstream is told: a single string shared by all of
them would hand a mail address to the cadastre, the land-value register, three
tile servers and a commercial model provider as a side effect of a setting
nobody re-reads.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.schemas import Koordinate, Ziel
from app.settings import AppSettings

from .conftest import ALKIS_URL, MOTIS_URL, fixture_bytes, fixture_json

pytestmark = pytest.mark.anyio

CONTACT = "kontakt@example.org"


def test_the_contact_is_appended_only_where_it_is_asked_for():
    settings = AppSettings(contact=CONTACT)

    assert CONTACT not in settings.user_agent
    assert CONTACT in settings.contact_user_agent
    # Still the same application either way.
    assert settings.contact_user_agent.startswith(settings.user_agent)


def test_without_a_contact_both_agents_are_the_plain_one():
    settings = AppSettings(contact="")

    assert settings.contact_user_agent == settings.user_agent
    assert "@" not in settings.user_agent


def test_the_shipped_default_carries_no_address():
    """A checkout that was never configured must not leak anyone's address.

    Read off the field defaults, not an instance: an instance would pick up
    whatever .env happens to sit next to the package.
    """
    fields = AppSettings.model_fields
    assert "@" not in fields["user_agent"].default
    assert fields["contact"].default == ""


@respx.mock
async def test_transitous_is_told_and_the_cadastre_is_not(monkeypatch):
    """The split, as the wire sees it."""
    from app.deps import alkis_service, motis_service, reset_services

    monkeypatch.setenv("APP_CONTACT", CONTACT)
    reset_services()
    try:
        motis = respx.get(url__startswith=MOTIS_URL).mock(
            return_value=httpx.Response(200, json=fixture_json("motis_plan_car.json"))
        )
        alkis = respx.get(ALKIS_URL).mock(
            return_value=httpx.Response(200, content=fixture_bytes("alkis_flurstueck_single.gml"))
        )

        await motis_service().route(
            Koordinate(lat=51.3397, lon=12.3731),
            Ziel(id="arbeit", lat=51.0400, lon=13.7322, name="Dresden Hbf"),
            "car",
        )
        await alkis_service().by_kennzeichen("140415___00604000202")

        assert CONTACT in motis.calls[0].request.headers["user-agent"]
        assert CONTACT not in alkis.calls[0].request.headers["user-agent"]
    finally:
        reset_services()
