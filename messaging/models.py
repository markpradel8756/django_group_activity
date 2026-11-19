import uuid

from django.db import models

from .validators import SMS_BYTE_LIMIT, validate_phone, validate_sms_length


class SMSMessage(models.Model):
    class Provider(models.TextChoices):
        TEXTBEE = "textbee", "textbee.dev"
        TWILIO = "twilio", "Twilio"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        UNDELIVERED = "UNDELIVERED", "Undelivered"
        UNKNOWN = "UNKNOWN", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.CharField(max_length=16, validators=[validate_phone])
    body = models.TextField(max_length=SMS_BYTE_LIMIT, validators=[validate_sms_length])
    provider = models.CharField(max_length=12, choices=Provider.choices, default=Provider.TEXTBEE)
    provider_reference = models.CharField(max_length=34, unique=True, null=True, blank=True)
    provider_device_id = models.CharField(max_length=24, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error_code = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.recipient} · {self.get_status_display()}"

    @property
    def can_refresh(self):
        return bool(
            self.provider == self.Provider.TEXTBEE and self.provider_reference and self.provider_device_id
        )


class Contact(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=16, unique=True, validators=[validate_phone])
    description = models.TextField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name
