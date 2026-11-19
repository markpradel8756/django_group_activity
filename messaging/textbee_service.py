"""Send SMS and track delivery through the textbee.dev REST API."""
import hashlib
import hmac
import re
import time
from dataclasses import dataclass

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import SMSMessage

API_ROOT = "https://api.textbee.dev/api/v1/gateway"
Status = SMSMessage.Status
EVENT_STATES = {
    "MESSAGE_SENT": "sent",
    "MESSAGE_DELIVERED": "delivered",
    "MESSAGE_FAILED": "failed",
}
MESSAGE_STATES = {
    "pending": Status.SUBMITTED,
    "dispatched": Status.SUBMITTED,
    "sent": Status.SUBMITTED,
    "delivered": Status.DELIVERED,
    "failed": Status.FAILED,
}
PHONE_ERRORS = {
    "2": "The sending phone's mobile radio is off. Check airplane mode.",
    "4": "The sending phone has no mobile service. Check its SIM and signal.",
    "5": "Android stopped the send because the phone reached its SMS limit.",
    "17": "The phone reported a mobile network error.",
}


@dataclass(frozen=True)
class DeliveryResult:
    state: str
    error_code: str = ""
    delivered_at: str | None = None


class ProviderError(Exception):
    def __init__(self, message, *, uncertain=False, code=""):
        super().__init__(message)
        self.uncertain = uncertain
        self.code = code


def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-fA-F]{24}", value))


def credentials_configured():
    key = settings.TEXTBEE_API_KEY
    return bool(key and key.isascii() and key.isprintable() and not any(c.isspace() for c in key))


def sender_configured():
    return valid_id(settings.TEXTBEE_DEVICE_ID)


def webhook_configured():
    return len(settings.TEXTBEE_WEBHOOK_SECRET) >= 20


def _unexpected_response(*, uncertain=False):
    if uncertain:
        return ProviderError(
            "textbee returned an unexpected response. Check its dashboard before sending again.",
            uncertain=True,
        )
    return ProviderError("textbee returned an unexpected response. Try checking again later.")


def _request(method, path, **kwargs):
    if not credentials_configured():
        raise ProviderError("Set your textbee API key in the local .env file.")
    sending = method == "POST"
    try:
        response = requests.request(
            method, API_ROOT + path, headers={"x-api-key": settings.TEXTBEE_API_KEY},
            timeout=(5, 10), allow_redirects=False, **kwargs,
        )
    except requests.RequestException:
        if sending:
            raise ProviderError(
                "Could not confirm the send with textbee. Check its dashboard before sending again.",
                uncertain=True,
            ) from None
        raise ProviderError("Could not reach textbee. Check your internet connection.") from None

    code = response.status_code
    if code >= 500 or code == 408:
        if sending:
            raise ProviderError(
                "textbee did not confirm the send. Check its dashboard before sending again.",
                uncertain=True, code=str(code),
            )
        raise ProviderError("textbee is temporarily unavailable. Try checking again later.", code=str(code))
    if code != 200:
        feedback = {
            400: "textbee rejected the request. Check the recipient, your verified email, and the Android device.",
            401: "textbee rejected the API key. Check that it is correct and has not been revoked.",
            403: "This textbee account does not have access to the requested operation.",
            404: "textbee could not find the selected device or message. Check your account and device ID.",
            429: "Your textbee account reached a message or request limit. Check your plan in the dashboard.",
        }
        if code not in feedback and code < 400:
            raise _unexpected_response(uncertain=sending)
        raise ProviderError(feedback.get(code, "textbee rejected the request."), code=str(code))
    try:
        data = response.json()["data"]
    except (ValueError, KeyError, TypeError):
        raise _unexpected_response(uncertain=sending) from None
    if not isinstance(data, dict):
        raise _unexpected_response(uncertain=sending)
    return data


def send_sms(attempt):
    if not valid_id(attempt.provider_device_id):
        raise ProviderError("Set the Android device ID from your textbee dashboard in the local .env file.")
    data = _request("POST", "/send-sms", json={
        "recipients": [attempt.recipient],
        "message": attempt.body,
        "deviceId": attempt.provider_device_id,
    })
    batch_id = data.get("smsBatchId")
    if data.get("success") is not True or not valid_id(batch_id):
        raise _unexpected_response(uncertain=True)
    return batch_id


def check_connection():
    device_id = settings.TEXTBEE_DEVICE_ID
    if not sender_configured():
        raise ProviderError("Set the Android device ID from your textbee dashboard in the local .env file.")
    data = _request("GET", f"/devices/{device_id}")
    if data.get("_id") != device_id or not isinstance(data.get("enabled"), bool):
        raise _unexpected_response()
    return data["enabled"]


def _delivery_result(data, state):
    code = str(data.get("errorCode") or "")
    if not re.fullmatch(r"[0-9]{1,8}|FCM_[A-Z0-9_]{1,36}|SIM_SLOT_EMPTY", code):
        code = ""
    return DeliveryResult(state, code, data.get("deliveredAt"))


def fetch_status(attempt):
    device_id, batch_id = attempt.provider_device_id, attempt.provider_reference
    if not attempt.can_refresh or not valid_id(device_id) or not valid_id(batch_id):
        raise ProviderError("This attempt has no textbee batch to check.")
    data = _request("GET", f"/devices/{device_id}/sms-batch/{batch_id}")
    batch = data.get("batch")
    messages = data.get("messages")
    if not isinstance(batch, dict) or batch.get("_id") != batch_id or not isinstance(messages, list):
        raise _unexpected_response()
    # A newly created batch may not have a recipient record yet.
    if not messages:
        return DeliveryResult("failed" if batch.get("status") == "failed" else "pending")
    for message in messages:
        if isinstance(message, dict) and message.get("recipient") == attempt.recipient:
            state = message.get("status")
            return _delivery_result(message, state if isinstance(state, str) else "unknown")
    raise _unexpected_response()


def apply_delivery(attempts, result):
    """Apply provider updates atomically, so retries cannot reverse a final result."""
    status = MESSAGE_STATES.get(result.state, Status.UNKNOWN)
    previous = [Status.PENDING, Status.SUBMITTED, Status.UNKNOWN]
    if result.state in ("pending", "dispatched"):
        previous.remove(Status.UNKNOWN)
    changes = {"status": status, "updated_at": timezone.now(), "error_code": "", "error_message": ""}
    if status == Status.DELIVERED:
        delivered_at = None
        if isinstance(result.delivered_at, str):
            try:
                delivered_at = parse_datetime(result.delivered_at)
            except ValueError:
                pass
        changes["delivered_at"] = (
            delivered_at if delivered_at and timezone.is_aware(delivered_at) else changes["updated_at"]
        )
    elif status == Status.FAILED:
        default = "textbee reported that the SMS could not be sent. Check the sending phone."
        if result.error_code.startswith("FCM_"):
            default = "textbee could not reach the sending app. Check that the phone is connected."
        changes.update(
            error_code=result.error_code, error_message=PHONE_ERRORS.get(result.error_code, default)
        )
    return attempts.filter(status__in=previous).exclude(
        status=status, error_code=changes["error_code"], error_message=changes["error_message"]
    ).update(**changes)


def valid_signature(header, body):
    if not webhook_configured():
        return False
    parts = re.fullmatch(r"t=([0-9]{1,12}),v1=([0-9a-f]{64})", header)
    if not parts:
        return False
    timestamp, signature = parts.groups()
    if abs(time.time() - int(timestamp)) > 300:
        return False
    signed_body = timestamp.encode("ascii") + b"." + body
    expected = hmac.new(settings.TEXTBEE_WEBHOOK_SECRET.encode("utf-8"), signed_body, hashlib.sha256)
    return hmac.compare_digest(expected.hexdigest(), signature)


def webhook_delivery(payload):
    event = payload.get("webhookEvent")
    if isinstance(event, str) and event in EVENT_STATES:
        return _delivery_result(payload, EVENT_STATES[event])
    return None
