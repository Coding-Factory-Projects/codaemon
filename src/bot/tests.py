import contextlib
import json

import pytest

from bot import discord_actions
from bot.models import OnboardingLog
from bot.onboarding import make_token, read_token

JSON = "application/json"


def _post(client, path, body, **headers):
    return client.post(path, data=json.dumps(body), content_type=JSON, **headers)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "version": "dev"}


def test_token_roundtrip():
    token = make_token("123", "a@edu.esiee-it.fr")
    assert read_token(token) == {"discord_id": "123", "email": "a@edu.esiee-it.fr"}


# --- /on-promotion-created (shared secret) ---


def test_webhook_rejects_without_secret(client):
    r = _post(client, "/on-promotion-created", {"name": "M1", "campus": "paris"})
    assert r.status_code == 401


def test_webhook_accepts_with_secret(client, monkeypatch):
    monkeypatch.setattr(discord_actions, "create_class_category", lambda *a, **k: ("555", "777"))
    r = _post(
        client,
        "/on-promotion-created",
        {"name": "M1", "campus": "paris"},
        HTTP_X_SHARED_SECRET="topsecret",
    )
    assert r.status_code == 200
    assert r.json() == {"roleId": "555", "categoryId": "777"}


# --- /onboard (signed token, server-side Django view) ---


def test_onboard_get_renders_confirm_form(client):
    token = make_token("123", "a@edu.esiee-it.fr")
    r = client.get(f"/onboard?token={token}")
    assert r.status_code == 200
    assert b"Confirmer" in r.content
    assert token.encode() in r.content  # token carried in the hidden field


def test_onboard_rejects_bad_token(client):
    r = client.post("/onboard", {"token": "garbage"})
    assert r.status_code == 200
    assert "invalide" in r.content.decode().lower()


def test_onboard_rejects_bad_domain(client):
    token = make_token("123", "foo@gmail.com")
    r = client.post("/onboard", {"token": token})
    assert "autoris" in r.content.decode().lower()


@pytest.mark.django_db
def test_onboard_happy_path(client, monkeypatch):
    monkeypatch.setattr(
        "bot.learnd.patch_student",
        lambda email, uid: {
            "firstName": "Jean",
            "lastName": "Dupont",
            "promotion": {"discord_role_id": "77"},
        },
    )
    calls = {}
    monkeypatch.setattr(
        discord_actions,
        "apply_onboarding",
        lambda uid, nick, add_role_ids, remove_role_ids: calls.update(
            uid=uid, nick=nick, add=add_role_ids, remove=remove_role_ids
        ),
    )
    token = make_token("123", "jean.dupont@edu.esiee-it.fr")
    r = client.post("/onboard", {"token": token})

    assert r.status_code == 200
    assert "Jean DUPONT" in r.content.decode()
    assert calls["add"] == ["10", "77"]  # base role + promotion role
    assert calls["remove"] == ["20"]  # guest role
    assert OnboardingLog.objects.count() == 1


# --- idempotency of provisioning ---


def _patch_client(monkeypatch):
    monkeypatch.setattr(discord_actions, "_client", lambda: contextlib.nullcontext(object()))


def test_create_class_category_is_idempotent(monkeypatch):
    _patch_client(monkeypatch)
    monkeypatch.setattr(discord_actions, "_find_role", lambda c, name: {"id": "999"})
    monkeypatch.setattr(discord_actions, "_find_category", lambda c, name: {"id": "888"})
    created = []
    monkeypatch.setattr(discord_actions, "_create_role", lambda *a: created.append("role"))
    monkeypatch.setattr(discord_actions, "_create_category", lambda *a: created.append("cat"))
    monkeypatch.setattr(discord_actions, "_ensure_channels", lambda c, pid: None)

    role_id, category_id = discord_actions.create_class_category("M1", "paris")

    assert role_id == "999"
    assert category_id == "888"
    assert created == []  # nothing re-created


def test_create_class_category_creates_when_absent(monkeypatch):
    _patch_client(monkeypatch)
    monkeypatch.setattr(discord_actions, "_find_role", lambda c, name: None)
    monkeypatch.setattr(discord_actions, "_find_category", lambda c, name: None)
    monkeypatch.setattr(discord_actions, "_create_role", lambda c, name: {"id": "111"})
    monkeypatch.setattr(discord_actions, "_create_category", lambda c, name, rid: {"id": "222"})
    monkeypatch.setattr(discord_actions, "_ensure_channels", lambda c, pid: None)

    role_id, category_id = discord_actions.create_class_category("M2", "cergy")

    assert role_id == "111"
    assert category_id == "222"
