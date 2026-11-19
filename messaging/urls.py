from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("send/", views.compose, name="compose"),
    path("history/", views.history, name="history"),
    path("history/<uuid:attempt_id>/", views.detail, name="message_detail"),
    path("history/<uuid:attempt_id>/refresh/", views.refresh_status, name="refresh_status"),
    path("contacts/", views.contacts, name="contacts"),
    path("contacts/new/", views.edit_contact, name="contact_add"),
    path("contacts/<int:contact_id>/edit/", views.edit_contact, name="contact_edit"),
    path("contacts/<int:contact_id>/delete/", views.delete_contact, name="contact_delete"),
    path("settings/", views.provider_settings, name="provider_settings"),
    path("webhooks/textbee/status/", views.textbee_callback, name="textbee_callback"),
]
