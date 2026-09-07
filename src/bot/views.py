import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bot.usecases.broadcast import BroadcastProviderError, broadcast
from bot.usecases.onboard import OnboardError, complete_onboard


@csrf_exempt
@require_POST
def broadcast_class(request: HttpRequest) -> JsonResponse:
    token = settings.CODAEMON_API_TOKEN
    if not token:
        return JsonResponse({"error": _("Authentification invalide.")}, status=401)
    if not constant_time_compare(request.headers.get("Authorization", ""), f"Bearer {token}"):
        return JsonResponse({"error": _("Authentification invalide.")}, status=401)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("JSON invalide.")}, status=400)
    try:
        message_id = broadcast(payload)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    except BroadcastProviderError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"discord_message_id": message_id}, status=201)


@csrf_exempt
def onboard(request: HttpRequest) -> HttpResponse:
    """Public onboarding page.

    GET  /onboard?token=...  -> a confirmation page with a single button.
    POST /onboard            -> performs the onboarding and shows the result.

    Acting on POST (a button click) rather than on GET means email/link scanners,
    which only issue GET requests, cannot trigger an onboarding by accident.
    The signed token is the credential, so the view is CSRF-exempt.
    """
    if request.method == "POST":
        try:
            nickname = complete_onboard(request.POST.get("token", ""))
        except OnboardError as exc:
            return render(request, "onboard.html", {"state": "error", "message": str(exc)})
        return render(request, "onboard.html", {"state": "success", "nickname": nickname})

    return render(
        request,
        "onboard.html",
        {"state": "confirm", "token": request.GET.get("token", "")},
    )


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "version": settings.PROJECT_VERSION})
