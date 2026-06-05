from django.urls import path

from bot import views
from bot.api import api

urlpatterns = [
    path("onboard", views.onboarding, name="onboarding"),
    path("healthz", views.healthz, name="healthz"),
    path("", api.urls),
]
