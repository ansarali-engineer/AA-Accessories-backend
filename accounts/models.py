from django.conf import settings
from django.db import models


class Customer(models.Model):
    class Tier(models.TextChoices):
        STANDARD = "standard", "Standard"
        SILVER = "silver", "Silver"
        GOLD = "gold", "Gold"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer")
    phone = models.CharField(max_length=32, blank=True)
    city = models.CharField(max_length=80, blank=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.STANDARD)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tier", "city"], name="customer_tier_city_idx"),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.tier})"

