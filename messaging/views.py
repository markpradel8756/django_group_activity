import json
import uuid
from datetime import timedelta
from functools import wraps
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import textbee_service as textbee
from .forms import ContactForm, HistoryFilterForm, SMSForm
from .models import Contact, SMSMessage
from .validators import E164_PATTERN, GSM_BASIC, GSM_EXTENDED, SMS_BYTE_LIMIT

Status = SMSMessage.Status
SUBMISSION_SALT = "relay.sms-submission"


def workspace(view):
    """Permit a simple local demo and require login for a shared workspace."""
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if settings.REQUIRE_WORKSPACE_LOGIN and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return view(request, *args, **kwargs)
    return wrapped


def _activity():
    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    counts = dict(
        SMSMessage.objects.filter(created_at__date__range=(days[0], days[-1]))
        .annotate(day=TruncDate("created_at"))
        .values("day").annotate(total=Count("id")).order_by("day")
        .values_list("day", "total")
    )
    series = [{"day": day, "count": counts.get(day, 0)} for day in days]
    step = max(1, ceil(max(item["count"] for item in series) / 4))
    for index, item in enumerate(series):
        item["x"] = index * 100
        item["y"] = round(128 - 128 * item["count"] / (step * 4), 2)
    return {
        "series": series,
        "axis": range(step * 4, -1, -step),
        "points": " ".join(f'{item["x"]},{item["y"]}' for item in series),
        "total": sum(item["count"] for item in series),
    }


@require_GET
@workspace
def dashboard(request):
    attempts = SMSMessage.objects.all()
    stats = attempts.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status=Status.SUBMITTED)),
        delivered=Count("id", filter=Q(status=Status.DELIVERED)),
        failed=Count("id", filter=Q(status__in=[Status.FAILED, Status.UNDELIVERED])),
    )
    return render(request, "messaging/dashboard.html", {
        "section": "dashboard",
        "title": "Dashboard",
        "recent": attempts[:5],
        "activity": _activity(),
        "metrics": [
            ("Total SMS attempts", stats["total"], "messages-square", "blue", "All recorded attempts"),
            ("Submitted messages", stats["submitted"], "send", "indigo", "Awaiting delivery confirmation"),
            ("Delivered messages", stats["delivered"], "circle-check", "green", "Confirmed by the provider"),
            ("Failed messages", stats["failed"], "circle-alert", "red", "Failed or undelivered"),
        ],
        "provider_ready": textbee.credentials_configured() and textbee.sender_configured(),
        "callback_ready": textbee.webhook_configured(),
    })


def _submission_token(request):
    nonce = request.session.setdefault("sms_nonce", uuid.uuid4().hex)
    return signing.dumps([nonce, str(uuid.uuid4())], salt=SUBMISSION_SALT)


def _attempt_id(request, token):
    nonce, attempt_id = signing.loads(token, salt=SUBMISSION_SALT, max_age=24 * 60 * 60)
    if nonce != request.session.get("sms_nonce"):
        raise signing.BadSignature
    return uuid.UUID(attempt_id)


def _send_feedback(request, attempt):
    if attempt.status == Status.DELIVERED:
        messages.success(request, "textbee confirmed delivery.")
    elif attempt.status == Status.SUBMITTED:
        messages.success(request, "textbee accepted your SMS. Delivery confirmation is pending.")
    elif attempt.status in (Status.FAILED, Status.UNDELIVERED):
        messages.error(request, attempt.error_message or "textbee could not send this SMS.")
    else:
        messages.warning(
            request, attempt.error_message or "The SMS status is unknown. Check again for an update."
        )


@require_http_methods(["GET", "POST"])
@workspace
def compose(request):
    if request.method == "POST":
        form = SMSForm(request.POST)
        if form.is_valid():
            try:
                attempt_id = _attempt_id(request, form.cleaned_data["submission_token"])
            except (signing.BadSignature, ValueError, TypeError):
                data = request.POST.copy()
                data["submission_token"] = _submission_token(request)
                form = SMSForm(data)
                form.add_error(None, "Your form session expired. Review the message and submit again.")
            else:
                attempt, created = SMSMessage.objects.get_or_create(pk=attempt_id, defaults={
                    "recipient": form.cleaned_data["recipient"], "body": form.cleaned_data["body"],
                    "provider_device_id": settings.TEXTBEE_DEVICE_ID if textbee.sender_configured() else "",
                })
                if not created:
                    messages.info(request, "This form was already submitted. Here is its message record.")
                    return redirect("message_detail", attempt_id=attempt.pk)
                try:
                    batch_id = textbee.send_sms(attempt)
                except textbee.ProviderError as exc:
                    attempt.status = Status.UNKNOWN if exc.uncertain else Status.FAILED
                    attempt.error_code = exc.code
                    attempt.error_message = str(exc)
                    attempt.save(update_fields=["status", "error_code", "error_message", "updated_at"])
                else:
                    attempt.status = Status.SUBMITTED
                    attempt.provider_reference = batch_id
                    attempt.submitted_at = timezone.now()
                    attempt.save(update_fields=["status", "provider_reference", "submitted_at", "updated_at"])
                attempt.refresh_from_db()
                _send_feedback(request, attempt)
                return redirect("message_detail", attempt_id=attempt.pk)
    else:
        initial = {"submission_token": _submission_token(request)}
        contact_id = request.GET.get("contact", "")
        if contact_id.isdecimal() and len(contact_id) <= 18:
            initial["recipient"] = Contact.objects.filter(pk=contact_id).values_list(
                "phone", flat=True
            ).first()
        form = SMSForm(initial=initial)
    return render(request, "messaging/compose.html", {
        "section": "compose",
        "title": "Send SMS",
        "form": form,
        "contacts": Contact.objects.all(),
        "provider_ready": textbee.credentials_configured() and textbee.sender_configured(),
        "sms_encoding": {
            "basic": GSM_BASIC, "extension": GSM_EXTENDED,
            "byteLimit": SMS_BYTE_LIMIT,
        },
    })


@require_GET
@workspace
def history(request):
    form = HistoryFilterForm(request.GET)
    attempts = SMSMessage.objects.all()
    form.is_valid()
    query = form.cleaned_data.get("q")
    status = form.cleaned_data.get("status")
    date = form.cleaned_data.get("date")
    if query:
        attempts = attempts.filter(Q(recipient__icontains=query) | Q(body__icontains=query))
    if status:
        attempts = attempts.filter(status=status)
    if date:
        attempts = attempts.filter(created_at__date=date)
    return render(request, "messaging/history.html", {
        "section": "history",
        "title": "Message History",
        "form": form,
        "filtered": bool(query or status or date),
        "page": Paginator(attempts, 10).get_page(request.GET.get("page")),
    })


@require_GET
@workspace
def detail(request, attempt_id):
    attempt = get_object_or_404(SMSMessage, pk=attempt_id)
    return render(request, "messaging/detail.html", {
        "section": "history",
        "title": "Message Details",
        "attempt": attempt,
    })


@require_POST
@workspace
def refresh_status(request, attempt_id):
    attempt = get_object_or_404(SMSMessage, pk=attempt_id)
    if not attempt.can_refresh:
        messages.info(request, "This attempt has no textbee batch to check.")
    else:
        try:
            result = textbee.fetch_status(attempt)
            textbee.apply_delivery(SMSMessage.objects.filter(pk=attempt.pk), result)
        except textbee.ProviderError as exc:
            messages.error(request, str(exc))
        else:
            attempt.refresh_from_db()
            messages.success(request, f"Status checked with textbee · {attempt.get_status_display()}.")
    return redirect("message_detail", attempt_id=attempt.pk)


@require_GET
@workspace
def contacts(request):
    query = request.GET.get("q", "").strip()[:100]
    rows = Contact.objects.all()
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    return render(request, "messaging/contacts.html", {
        "section": "contacts",
        "title": "Contacts",
        "query": query,
        "page": Paginator(rows, 10).get_page(request.GET.get("page")),
    })


@require_http_methods(["GET", "POST"])
@workspace
def edit_contact(request, contact_id=None):
    contact = get_object_or_404(Contact, pk=contact_id) if contact_id else None
    form = ContactForm(request.POST if request.method == "POST" else None, instance=contact)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            if Contact.objects.filter(phone=form.cleaned_data["phone"]).exclude(
                pk=form.instance.pk
            ).exists():
                form.add_error("phone", "A contact with this phone number already exists.")
            else:
                raise
        else:
            messages.success(request, "Contact updated." if contact else "Contact added.")
            return redirect("contacts")
    return render(request, "messaging/contact_form.html", {
        "section": "contacts",
        "title": "Edit Contact" if contact else "Add Contact",
        "form": form,
    })


@require_http_methods(["GET", "POST"])
@workspace
def delete_contact(request, contact_id):
    contact = get_object_or_404(Contact, pk=contact_id)
    if request.method == "POST":
        contact.delete()
        messages.success(request, "Contact deleted.")
        return redirect("contacts")
    return render(request, "messaging/contact_delete.html", {
        "section": "contacts",
        "title": "Delete Contact",
        "contact": contact,
    })


@require_http_methods(["GET", "POST"])
@workspace
def provider_settings(request):
    if request.method == "POST":
        try:
            ready = textbee.check_connection()
        except textbee.ProviderError as exc:
            request.session["textbee_connection"] = "Failed"
            messages.error(request, str(exc))
        else:
            request.session["textbee_connection"] = "Device enabled" if ready else "Device disabled"
            if ready:
                messages.success(request, "Connected to textbee. Your registered device is enabled.")
            else:
                messages.warning(request, "Connected to textbee. Enable the device in your textbee dashboard.")
        return redirect("provider_settings")
    return render(request, "messaging/settings.html", {
        "section": "settings",
        "title": "Settings",
        "credentials_ready": textbee.credentials_configured(),
        "sender_ready": textbee.sender_configured(),
        "callback_ready": textbee.webhook_configured(),
        "last_check": request.session.get("textbee_connection", "Not checked"),
        "login_required": settings.REQUIRE_WORKSPACE_LOGIN,
        "timezone": settings.TIME_ZONE,
    })


@csrf_exempt
@require_POST
def textbee_callback(request):
    body = request.body
    if not textbee.valid_signature(request.headers.get("X-Textbee-Signature", ""), body):
        return HttpResponse(status=401)
    try:
        payload = json.loads(body)
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse(status=400)
    result = textbee.webhook_delivery(payload)
    if result is None:
        return HttpResponse()
    batch_id, device_id = payload.get("smsBatchId"), payload.get("deviceId")
    recipient = payload.get("recipient")
    if (
        not textbee.valid_id(batch_id) or not textbee.valid_id(device_id)
        or not isinstance(recipient, str) or not E164_PATTERN.fullmatch(recipient)
    ):
        return HttpResponse(status=400)
    candidates = SMSMessage.objects.filter(
        provider=SMSMessage.Provider.TEXTBEE, provider_device_id=device_id, recipient=recipient
    )
    batch = candidates.filter(provider_reference=batch_id)
    if not textbee.apply_delivery(batch, result) and not batch.exists() and candidates.filter(
        provider_reference__isnull=True, status=Status.PENDING,
        created_at__gte=timezone.now() - timedelta(seconds=30),
    ).exists():
        # A fast phone can report before the send response saves the batch ID.
        # Ask textbee to retry instead of guessing which in-flight attempt it belongs to.
        return HttpResponse(status=503)
    return HttpResponse()
