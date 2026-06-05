"""Outbound email (Mailgun over SMTP via Django's email backend)."""

from django.conf import settings
from django.core.mail import send_mail


def send_onboarding_email(to_email: str, link: str) -> None:
    send_mail(
        subject="Inscription au serveur de la Coding Factory",
        message=(
            "Salut !\n\n"
            "Pour finaliser ton inscription au serveur Discord de la Coding Factory, "
            f"suis ce lien :\n{link}\n\n"
            "Ce lien expire dans une heure."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
    )
