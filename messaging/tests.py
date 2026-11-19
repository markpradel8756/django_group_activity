import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from requests.exceptions import Timeout

from . import textbee_service as textbee
from .forms import SMSForm
from .models import Contact, SMSMessage

PHONE = "+639171234567"
OTHER_PHONE = "+12025550123"
API_KEY = "test-textbee-key"
DEVICE = "1" * 24
BATCH = "2" * 24
SECRET = "test-webhook-signing-secret"
Status = SMSMessage.Status


class SMSFormTests(TestCase):
    def form(self, **overrides):
        return SMSForm({"recipient": PHONE, "body": "Hello!", "submission_token": "test", **overrides})

    def test_valid_sms(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient"], PHONE)

    def test_missing_phone_number(self):
        self.assertEqual(self.form(recipient="").errors["recipient"], ["Enter a recipient phone number."])

    def test_empty_and_whitespace_messages(self):
        for body in ("", "  \n\t "):
            with self.subTest(body=body):
                self.assertIn("body", self.form(body=body).errors)

    def test_invalid_phone_number(self):
        for number in ("09171234567", "+0123456789", "+1234567", "+999123456789", "+63-9171234567"):
            with self.subTest(number=number):
                self.assertIn("recipient", self.form(recipient=number).errors)

    def test_modified_utf8_byte_limit(self):
        for character, count in (("a", 9000), ("é", 4500), ("漢", 3000), ("😀", 1500)):
            with self.subTest(character=character):
                self.assertTrue(self.form(body=character * count).is_valid())
                self.assertIn("body", self.form(body=character * (count + 1)).errors)

    def test_line_endings_are_normalized_and_outer_spaces_are_preserved(self):
        form = self.form(body="  first\r\nsecond  ")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["body"], "  first\nsecond  ")

        multiline = self.form(body="a" * 8998 + "\r\nb")
        self.assertTrue(multiline.is_valid(), multiline.errors)


@override_settings(TEXTBEE_API_KEY=API_KEY, TEXTBEE_DEVICE_ID=DEVICE)
@patch("messaging.textbee_service.requests.request")
class TextbeeServiceTests(TestCase):
    def setUp(self):
        self.attempt = SMSMessage(
            recipient=PHONE, body="Test SMS", provider_reference=BATCH, provider_device_id=DEVICE,
        )

    @staticmethod
    def response(request, status_code, data):
        request.return_value = SimpleNamespace(status_code=status_code, json=lambda: {"data": data})

    def test_send_uses_api_key_and_selected_device(self, request):
        self.response(request, 200, {"success": True, "smsBatchId": BATCH, "recipientCount": 1})
        self.assertEqual(textbee.send_sms(self.attempt), BATCH)
        request.assert_called_once_with(
            "POST", "https://api.textbee.dev/api/v1/gateway/send-sms",
            headers={"x-api-key": API_KEY}, timeout=(5, 10), allow_redirects=False,
            json={"recipients": [PHONE], "message": "Test SMS", "deviceId": DEVICE},
        )

    def test_provider_rejection_uses_safe_messages(self, request):
        for status, message in ((401, "API key"), (400, "recipient"), (429, "limit")):
            with self.subTest(status=status):
                self.response(request, status, {"message": "private diagnostic"})
                with self.assertRaises(textbee.ProviderError) as raised:
                    textbee.send_sms(self.attempt)
                self.assertIn(message, str(raised.exception))
                self.assertNotIn("private diagnostic", str(raised.exception))
                self.assertEqual(raised.exception.code, str(status))
                self.assertFalse(raised.exception.uncertain)

    def test_timeout_is_uncertain_and_sends_only_once(self, request):
        request.side_effect = Timeout("private url")
        with self.assertRaises(textbee.ProviderError) as raised:
            textbee.send_sms(self.attempt)
        self.assertTrue(raised.exception.uncertain)
        self.assertNotIn("private url", str(raised.exception))
        request.assert_called_once()

    def test_unexpected_batch_id_is_rejected(self, request):
        self.response(request, 200, {"success": True, "smsBatchId": "private diagnostic"})
        with self.assertRaises(textbee.ProviderError) as raised:
            textbee.send_sms(self.attempt)
        self.assertTrue(raised.exception.uncertain)
        self.assertNotIn("private diagnostic", str(raised.exception))

    @override_settings(TEXTBEE_API_KEY="")
    def test_missing_key_stops_provider_requests(self, request):
        with self.assertRaisesMessage(textbee.ProviderError, "Set your textbee API key"):
            textbee.send_sms(self.attempt)
        request.assert_not_called()

    def test_connection_check_reads_device_status(self, request):
        self.response(request, 200, {"_id": DEVICE, "enabled": True})
        self.assertTrue(textbee.check_connection())
        self.response(request, 200, {"_id": DEVICE, "enabled": False})
        self.assertFalse(textbee.check_connection())
        self.assertEqual(
            request.call_args.args, ("GET", f"{textbee.API_ROOT}/devices/{DEVICE}")
        )

    @override_settings(TEXTBEE_DEVICE_ID="9" * 24)
    def test_batch_refresh_uses_saved_device_and_recipient_status(self, request):
        self.response(request, 200, {
            "batch": {"_id": BATCH, "status": "completed"},
            "messages": [{"recipient": PHONE, "status": "sent"}],
        })
        self.assertEqual(textbee.fetch_status(self.attempt).state, "sent")
        self.assertEqual(
            request.call_args.args, ("GET", f"{textbee.API_ROOT}/devices/{DEVICE}/sms-batch/{BATCH}")
        )
        self.response(request, 200, {
            "batch": {"_id": BATCH}, "messages": [{"recipient": OTHER_PHONE, "status": "delivered"}],
        })
        with self.assertRaises(textbee.ProviderError):
            textbee.fetch_status(self.attempt)


@override_settings(REQUIRE_WORKSPACE_LOGIN=False)
class WorkspaceTests(TestCase):
    def sms_data(self, **overrides):
        response = self.client.get(reverse("compose"))
        token = response.context["form"]["submission_token"].value()
        return {"recipient": PHONE, "body": "Group meeting at 3 PM.", "submission_token": token, **overrides}

    def test_empty_dashboard_loads_and_counts_zero(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "No messages yet")
        self.assertEqual([metric[1] for metric in response.context["metrics"]], [0, 0, 0, 0])

    def test_dashboard_uses_database_statuses_and_daily_counts(self):
        for status in Status.values:
            SMSMessage.objects.create(recipient=PHONE, body=status, status=status)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual([metric[1] for metric in response.context["metrics"]], [6, 1, 1, 2])
        self.assertEqual(response.context["activity"]["total"], 6)
        self.assertEqual(response.context["activity"]["series"][-1]["count"], 6)

    def test_compose_loads(self):
        response = self.client.get(reverse("compose"))
        self.assertContains(response, "Message preview")
        self.assertContains(response, "sms-encoding")
        self.assertTrue(response.context["form"]["submission_token"].value())

    @override_settings(TEXTBEE_DEVICE_ID=DEVICE)
    @patch("messaging.textbee_service.send_sms")
    def test_compose_saves_attempt_before_sending_and_deduplicates(self, send_sms):
        def provider_call(attempt):
            saved = SMSMessage.objects.get(pk=attempt.pk)
            self.assertEqual(saved.status, Status.PENDING)
            self.assertEqual(saved.body, data["body"])
            self.assertEqual(saved.provider_device_id, DEVICE)
            return BATCH

        data = self.sms_data()
        send_sms.side_effect = provider_call
        first = self.client.post(reverse("compose"), data, follow=True)
        self.assertContains(first, "Delivery confirmation is pending")
        attempt = SMSMessage.objects.get()
        self.assertEqual(attempt.status, Status.SUBMITTED)
        self.assertEqual(attempt.recipient, PHONE)
        self.assertEqual(attempt.provider_reference, BATCH)
        self.assertEqual(attempt.provider, SMSMessage.Provider.TEXTBEE)
        self.assertIsNotNone(attempt.submitted_at)
        self.assertIsNone(attempt.delivered_at)
        replay = self.client.post(reverse("compose"), data, follow=True)
        self.assertContains(replay, "already submitted")
        self.assertEqual(SMSMessage.objects.count(), 1)
        send_sms.assert_called_once()

    @override_settings(TEXTBEE_API_KEY="", TEXTBEE_DEVICE_ID=DEVICE)
    def test_missing_configuration_records_a_safe_failure(self):
        response = self.client.post(reverse("compose"), self.sms_data(), follow=True)
        self.assertContains(response, "Set your textbee API key")
        self.assertEqual(SMSMessage.objects.get().status, Status.FAILED)

    @patch("messaging.textbee_service.send_sms")
    def test_invalid_forms_make_no_attempt(self, send_sms):
        response = self.client.post(reverse("compose"), self.sms_data(recipient="bad", body=" "))
        self.assertContains(response, "Enter a valid international phone number")
        self.assertContains(response, "Enter a message with text")
        self.assertFalse(SMSMessage.objects.exists())
        send_sms.assert_not_called()

    @patch("messaging.textbee_service.send_sms")
    def test_attempt_token_is_bound_to_browser_session(self, send_sms):
        response = Client().post(reverse("compose"), self.sms_data())
        self.assertContains(response, "Your form session expired")
        self.assertFalse(SMSMessage.objects.exists())
        send_sms.assert_not_called()

    def test_history_filters_and_paginates(self):
        SMSMessage.objects.bulk_create([
            SMSMessage(recipient=PHONE, body="Group meeting", status=Status.SUBMITTED)
            for _ in range(11)
        ])
        SMSMessage.objects.create(recipient=OTHER_PHONE, body="A different message")
        path = reverse("history")
        response = self.client.get(path, {
            "q": "group", "status": Status.SUBMITTED, "date": timezone.localdate().isoformat(),
        })
        self.assertContains(response, "Group meeting")
        self.assertNotContains(response, "A different message")
        page = response.context["page"]
        self.assertEqual(len(page.object_list), 10)
        self.assertEqual(page.paginator.count, 11)
        self.assertContains(response, "page=2")
        self.assertContains(self.client.get(path, {"q": OTHER_PHONE}), "A different message")
        self.assertContains(self.client.get(path, {"date": "2000-01-01"}), "No matching messages")

    def test_message_details_escape_user_content(self):
        record = SMSMessage.objects.create(recipient=PHONE, body="<script>alert(1)</script>")
        response = self.client.get(reverse("message_detail", args=[record.pk]))
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    @patch("messaging.textbee_service.fetch_status")
    def test_refresh_updates_existing_message(self, fetch):
        record = SMSMessage.objects.create(
            recipient=PHONE, body="Hi", provider_reference=BATCH,
            provider_device_id=DEVICE, status=Status.SUBMITTED,
        )
        fetch.return_value = textbee.DeliveryResult("delivered")
        url = reverse("refresh_status", args=[record.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.post(url, follow=True), "Status checked with textbee")
        record.refresh_from_db()
        self.assertEqual(record.status, Status.DELIVERED)
        self.assertIsNotNone(record.delivered_at)
        fetch.assert_called_once_with(record)

    @patch("messaging.textbee_service.fetch_status")
    def test_historical_twilio_attempt_is_read_only(self, fetch):
        record = SMSMessage.objects.create(
            recipient=PHONE, body="Legacy message", provider=SMSMessage.Provider.TWILIO,
            provider_reference="SM" + "a" * 32, status=Status.DELIVERED,
        )
        detail = reverse("message_detail", args=[record.pk])
        response = self.client.get(detail)
        self.assertContains(response, record.provider_reference)
        self.assertContains(response, "Twilio")
        self.assertNotContains(response, "Refresh status")
        self.client.post(reverse("refresh_status", args=[record.pk]))
        fetch.assert_not_called()

    def test_contact_creation_search_and_selection(self):
        response = self.client.post(reverse("contact_add"), {
            "name": "Alex", "phone": PHONE, "description": "Group member",
        }, follow=True)
        contact = Contact.objects.get()
        self.assertContains(response, "Contact added")
        self.assertContains(self.client.get(reverse("contacts"), {"q": "alex"}), "Group member")
        compose = self.client.get(reverse("compose"), {"contact": contact.pk})
        self.assertEqual(compose.context["form"]["recipient"].value(), PHONE)

    def test_contact_validation_and_uniqueness(self):
        self.client.post(reverse("contact_add"), {"name": "Bad number", "phone": "123"})
        self.assertFalse(Contact.objects.exists())
        Contact.objects.create(name="First contact", phone=PHONE)
        response = self.client.post(reverse("contact_add"), {"name": "Duplicate", "phone": PHONE})
        self.assertContains(response, "A contact with this phone number already exists")
        self.assertEqual(Contact.objects.count(), 1)

    def test_contact_edit(self):
        contact = Contact.objects.create(name="Alex", phone=PHONE)
        response = self.client.post(reverse("contact_edit", args=[contact.pk]), {
            "name": "Alex Rivera", "phone": OTHER_PHONE,
        }, follow=True)
        self.assertContains(response, "Contact updated")
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.phone), ("Alex Rivera", OTHER_PHONE))

    def test_contact_delete_requires_post_and_csrf(self):
        contact = Contact.objects.create(name="Alex", phone=PHONE)
        url = reverse("contact_delete", args=[contact.pk])
        csrf = Client(enforce_csrf_checks=True)
        self.assertContains(csrf.get(url), "Delete Contact")
        self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())
        self.assertEqual(csrf.post(url).status_code, 403)
        self.assertContains(self.client.post(url, follow=True), "Contact deleted")
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())

    @override_settings(TEXTBEE_API_KEY=API_KEY, TEXTBEE_DEVICE_ID=DEVICE, TEXTBEE_WEBHOOK_SECRET=SECRET)
    @patch("messaging.textbee_service.check_connection", return_value=True)
    def test_settings_check_does_not_disclose_credentials(self, check_connection):
        url = reverse("provider_settings")
        response = self.client.get(url)
        check_connection.assert_not_called()
        for value in (API_KEY, DEVICE, SECRET):
            self.assertNotContains(response, value)
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Connected to textbee")
        check_connection.assert_called_once()

    @override_settings(REQUIRE_WORKSPACE_LOGIN=True)
    def test_shared_workspace_requires_django_login(self):
        self.assertRedirects(self.client.get(reverse("dashboard")), "/login/?next=/")
        self.assertEqual(self.client.post(reverse("contact_add")).status_code, 302)
        user = get_user_model().objects.create_user(username="relay-team")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("dashboard")), "relay-team")

    @override_settings(DEBUG=True)
    @patch("messaging.textbee_service.send_sms", side_effect=RuntimeError("private diagnostic"))
    def test_unexpected_view_error_does_not_expose_diagnostic(self, send_sms):
        with (
            self.assertLogs("messaging.middleware", level="ERROR"),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = self.client.post(reverse("compose"), self.sms_data())
        self.assertContains(response, "Request interrupted", status_code=500)
        self.assertNotContains(response, "private diagnostic", status_code=500)
        self.assertEqual(SMSMessage.objects.get().status, Status.PENDING)


@override_settings(TEXTBEE_WEBHOOK_SECRET=SECRET, REQUIRE_WORKSPACE_LOGIN=True)
class CallbackTests(TestCase):
    def setUp(self):
        self.attempt = SMSMessage.objects.create(
            recipient=PHONE, body="Hi", provider_reference=BATCH,
            provider_device_id=DEVICE, status=Status.SUBMITTED,
        )
        self.path = reverse("textbee_callback")
        self.webhook = Client(enforce_csrf_checks=True)

    def callback(self, *, timestamp=None, signature=None, **overrides):
        payload = {
            "smsBatchId": BATCH, "deviceId": DEVICE, "recipient": PHONE,
            "webhookEvent": "MESSAGE_DELIVERED", "deliveredAt": "2026-11-19T04:00:00Z",
            **overrides,
        }
        body = json.dumps(payload).encode()
        if timestamp is None:
            timestamp = int(time.time())
        if signature is None:
            digest = hmac.digest(SECRET.encode(), f"{timestamp}.".encode() + body, "sha256").hex()
            signature = f"t={timestamp},v1={digest}"
        return self.webhook.post(
            self.path, body, content_type="application/json", HTTP_X_TEXTBEE_SIGNATURE=signature,
        )

    def test_signed_delivery_and_late_progress_event(self):
        self.assertEqual(self.callback().status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.DELIVERED)
        self.assertEqual(self.attempt.delivered_at.isoformat(), "2026-11-19T04:00:00+00:00")
        updated_at = self.attempt.updated_at
        self.assertEqual(self.callback(webhookEvent="MESSAGE_SENT").status_code, 200)
        self.assertEqual(self.callback().status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.DELIVERED)
        self.assertEqual(self.attempt.updated_at, updated_at)

    def test_failed_event_records_safe_error(self):
        response = self.callback(webhookEvent="MESSAGE_FAILED", errorCode="4", errorMessage="secret")
        self.assertEqual(response.status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.FAILED)
        self.assertEqual(self.attempt.error_code, "4")
        self.assertIn("no mobile service", self.attempt.error_message)
        self.assertNotIn("secret", self.attempt.error_message)
        self.assertIsNone(self.attempt.delivered_at)

    def test_invalid_missing_and_expired_signatures_are_rejected(self):
        self.assertEqual(self.callback(signature="bad").status_code, 401)
        self.assertEqual(self.callback(timestamp=int(time.time()) - 301).status_code, 401)
        self.assertEqual(self.webhook.post(self.path, {}).status_code, 401)
        self.assertEqual(self.webhook.get(self.path).status_code, 405)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.SUBMITTED)

    def test_unrelated_batches_recipients_and_devices_do_not_update(self):
        for overrides in ({"smsBatchId": "9" * 24}, {"deviceId": "9" * 24}, {"recipient": OTHER_PHONE}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.callback(**overrides).status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.SUBMITTED)
        self.assertEqual(SMSMessage.objects.count(), 1)

    def test_early_callback_retries_until_batch_is_known(self):
        self.attempt.provider_reference = None
        self.attempt.status = Status.PENDING
        self.attempt.save()
        self.assertEqual(self.callback().status_code, 503)
        self.attempt.provider_reference = BATCH
        self.attempt.status = Status.SUBMITTED
        self.attempt.save()
        self.assertEqual(self.callback().status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Status.DELIVERED)
