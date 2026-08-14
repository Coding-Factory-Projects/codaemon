"""JSON API (Django Ninja).

learnd -> codaemon, protected by the shared secret header. The onboarding flow
(student-facing) lives in bot/views.py as a normal Django view, not here.
"""

import logging

from django.conf import settings
from django.utils.crypto import constant_time_compare
from ninja import NinjaAPI, Schema

from bot import discord_actions

logger = logging.getLogger(__name__)

api = NinjaAPI(title="codaemon", docs_url=None)


def shared_secret(request):
    """Ninja auth: require the shared secret header (used by learnd -> codaemon)."""
    provided = request.headers.get(settings.SHARED_SECRET_HEADER, "")
    if (
        provided
        and settings.SHARED_SECRET
        and constant_time_compare(provided, settings.SHARED_SECRET)
    ):
        return provided
    return None


class PromotionCreatedIn(Schema):
    name: str
    campus: str
    discord_role_id: str | None = None


class PromotionCreatedOut(Schema):
    roleId: str
    categoryId: str


@api.post("/on-promotion-created", response=PromotionCreatedOut, auth=shared_secret)
def on_promotion_created(request, payload: PromotionCreatedIn):
    role_id, category_id = discord_actions.create_class_category(
        payload.name, payload.campus, payload.discord_role_id
    )
    return {"roleId": role_id, "categoryId": category_id}
