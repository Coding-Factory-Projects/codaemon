import contextlib

from bot.discord_api import categories as discord_categories


def _patch_client(monkeypatch):
    monkeypatch.setattr(
        discord_categories.discord,
        "create_client",
        lambda: contextlib.nullcontext(object()),
    )


def test_create_class_category_is_idempotent(monkeypatch):
    _patch_client(monkeypatch)
    monkeypatch.setattr(discord_categories, "_find_role", lambda client, name: {"id": "999"})
    monkeypatch.setattr(
        discord_categories,
        "_find_category",
        lambda client, name: {"id": "888"},
    )
    created = []
    monkeypatch.setattr(
        discord_categories,
        "_create_role",
        lambda *args: created.append("role"),
    )
    monkeypatch.setattr(
        discord_categories,
        "_create_category",
        lambda *args: created.append("category"),
    )
    monkeypatch.setattr(discord_categories, "_ensure_channels", lambda client, parent_id: None)

    role_id, category_id = discord_categories.create_class_category("M1", "paris")

    assert role_id == "999"
    assert category_id == "888"
    assert created == []


def test_create_class_category_creates_when_absent(monkeypatch):
    _patch_client(monkeypatch)
    monkeypatch.setattr(discord_categories, "_find_role", lambda client, name: None)
    monkeypatch.setattr(discord_categories, "_find_category", lambda client, name: None)
    monkeypatch.setattr(
        discord_categories,
        "_create_role",
        lambda client, name: {"id": "111"},
    )
    monkeypatch.setattr(
        discord_categories,
        "_create_category",
        lambda client, name, role_id: {"id": "222"},
    )
    monkeypatch.setattr(discord_categories, "_ensure_channels", lambda client, parent_id: None)

    role_id, category_id = discord_categories.create_class_category("M2", "cergy")

    assert role_id == "111"
    assert category_id == "222"
