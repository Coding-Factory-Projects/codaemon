from django.db import models


class OnboardingLog(models.Model):
    """Audit trail of student onboardings. codaemon stores no roster -- only this log."""

    discord_user_id = models.CharField(max_length=50)
    email = models.EmailField()
    nickname = models.CharField(max_length=100, blank=True)
    promotion_role_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} -> {self.discord_user_id}"
