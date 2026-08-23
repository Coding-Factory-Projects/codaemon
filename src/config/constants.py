from enum import StrEnum


class StudentBackend(StrEnum):
    FIXTURE = "fixture"
    LEARND = "learnd"


class OnboardDelivery(StrEnum):
    EMAIL = "email"
    LINK = "link"
