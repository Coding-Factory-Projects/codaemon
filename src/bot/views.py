from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from bot.usecases.onboard import OnboardError, complete_onboard


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
