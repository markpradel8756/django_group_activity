from django import forms

from .models import Contact, SMSMessage
from .validators import SMS_BYTE_LIMIT, validate_phone

PHONE_ATTRS = {
    "type": "tel",
    "inputmode": "tel",
    "autocomplete": "tel",
    "placeholder": "+639171234567",
    "aria-describedby": "phone-help",
}


class SMSForm(forms.ModelForm):
    submission_token = forms.CharField(widget=forms.HiddenInput, max_length=200)
    recipient = forms.CharField(
        max_length=16,
        validators=[validate_phone],
        label="Recipient phone number",
        error_messages={"required": "Enter a recipient phone number."},
        widget=forms.TextInput(attrs=PHONE_ATTRS),
    )
    body = forms.CharField(
        strip=False,
        label="Message",
        error_messages={"required": "Enter a message."},
        widget=forms.Textarea(attrs={
            "rows": 6,
            "maxlength": SMS_BYTE_LIMIT,
            "placeholder": "Write your message here…",
            "aria-describedby": "message-help",
        }),
    )

    class Meta:
        model = SMSMessage
        fields = ["recipient", "body"]

    def clean_body(self):
        body = self.cleaned_data["body"].replace("\r\n", "\n").replace("\r", "\n")
        if not body.strip():
            raise forms.ValidationError("Enter a message with text.", code="blank_message")
        return body


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "phone", "description"]
        labels = {"name": "Contact name", "phone": "Phone number"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Alex Rivera"}),
            "phone": forms.TextInput(attrs=PHONE_ATTRS),
            "description": forms.Textarea(attrs={
                "placeholder": "Add a note about this contact", "rows": 4
            }),
        }
        error_messages = {
            "name": {"required": "Enter a contact name."},
            "phone": {
                "required": "Enter a phone number.",
                "unique": "A contact with this phone number already exists.",
            },
        }


class HistoryFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=160, label="Search")
    status = forms.ChoiceField(
        required=False, choices=[("", "All statuses"), *SMSMessage.Status.choices]
    )
    date = forms.DateField(
        required=False, input_formats=["%Y-%m-%d"], widget=forms.DateInput(attrs={"type": "date"})
    )
