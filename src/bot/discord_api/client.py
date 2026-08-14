"""Shared Discord REST client infrastructure."""

import time

import httpx
from django.conf import settings

API_BASE = "https://discord.com/api/v10"


def create_client() -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bot {settings.DISCORD_TOKEN}"},
        timeout=30,
    )


def request(
    client: httpx.Client,
    method: str,
    route: str,
    payload: dict | None = None,
) -> httpx.Response:
    for _attempt in range(5):
        response = client.request(method, route, json=payload)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        retry_after = float(response.json().get("retry_after", 1))
        time.sleep(retry_after)
    response.raise_for_status()
    return response


def roles_route() -> str:
    return f"/guilds/{_guild_id()}/roles"


def role_route(role_id: str) -> str:
    return f"/guilds/{_guild_id()}/roles/{role_id}"


def channels_route() -> str:
    return f"/guilds/{_guild_id()}/channels"


def channel_route(channel_id: str) -> str:
    return f"/channels/{channel_id}"


def member_route(user_id: str) -> str:
    return f"/guilds/{_guild_id()}/members/{user_id}"


def member_role_route(user_id: str, role_id: str) -> str:
    return f"/guilds/{_guild_id()}/members/{user_id}/roles/{role_id}"


def _guild_id() -> str:
    return str(settings.DISCORD_GUILD_ID)
