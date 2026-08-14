import json

from bot.discord_api import categories as discord_categories

JSON = "application/json"


def _post(client, path, body, **headers):
    return client.post(path, data=json.dumps(body), content_type=JSON, **headers)


def test_webhook_rejects_without_secret(client):
    response = _post(client, "/on-promotion-created", {"name": "M1", "campus": "paris"})
    assert response.status_code == 401


def test_webhook_accepts_with_secret(client, monkeypatch):
    monkeypatch.setattr(
        discord_categories,
        "create_class_category",
        lambda *args, **kwargs: ("555", "777"),
    )
    response = _post(
        client,
        "/on-promotion-created",
        {"name": "M1", "campus": "paris"},
        HTTP_X_SHARED_SECRET="topsecret",
    )
    assert response.status_code == 200
    assert response.json() == {"roleId": "555", "categoryId": "777"}
