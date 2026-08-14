import pytest

from bot.discord_api import members
from bot.models import OnboardingLog
from bot.usecases.onboard import make_token, read_token


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "version": "dev"}


def test_token_roundtrip():
    token = make_token("123", "a@edu.esiee-it.fr")
    assert read_token(token) == {"discord_id": "123", "email": "a@edu.esiee-it.fr"}


def test_onboard_get_renders_confirm_form(client):
    token = make_token("123", "a@edu.esiee-it.fr")
    response = client.get(f"/onboard?token={token}")
    assert response.status_code == 200
    assert b"Confirmer" in response.content
    assert token.encode() in response.content


def test_onboard_rejects_bad_token(client):
    response = client.post("/onboard", {"token": "garbage"})
    assert response.status_code == 200
    assert "invalide" in response.content.decode().lower()


def test_onboard_rejects_bad_domain(client):
    token = make_token("123", "foo@gmail.com")
    response = client.post("/onboard", {"token": token})
    assert "autoris" in response.content.decode().lower()


@pytest.mark.django_db
def test_onboard_happy_path(client, monkeypatch):
    monkeypatch.setattr(
        "bot.learnd.patch_student",
        lambda email, user_id: {
            "firstName": "Jean",
            "lastName": "Dupont",
            "promotion": {"discord_role_id": "77"},
        },
    )
    calls = {}
    monkeypatch.setattr(
        members,
        "apply_onboard",
        lambda user_id, nickname, add_role_ids, remove_role_ids: calls.update(
            user_id=user_id,
            nickname=nickname,
            add=add_role_ids,
            remove=remove_role_ids,
        ),
    )
    token = make_token("123", "jean.dupont@edu.esiee-it.fr")
    response = client.post("/onboard", {"token": token})

    assert response.status_code == 200
    assert "Jean DUPONT" in response.content.decode()
    assert calls["add"] == ["10", "77"]
    assert calls["remove"] == ["20"]
    assert OnboardingLog.objects.count() == 1
