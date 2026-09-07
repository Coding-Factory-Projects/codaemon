from django.urls import path

from bot import views

urlpatterns = [
    path("broadcast", views.broadcast_class, name="broadcast"),
    path("onboard", views.onboard, name="onboard"),
    path("healthz", views.healthz, name="healthz"),
]
