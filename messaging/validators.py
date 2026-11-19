import re

import phonenumbers
from django.core.exceptions import ValidationError

E164_PATTERN = re.compile(r"\+[1-9][0-9]{1,14}")
PHONE_HELP = "Enter a valid international phone number, such as +639171234567."

# The GSM-7 extension table uses two units per character. Unicode SMS uses
# UTF-16 units, so supplementary characters such as many emoji use two units.
GSM_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_EXTENDED = "\f^{}\\[~]|€"
SMS_BYTE_LIMIT = 9000


def validate_phone(value):
    if E164_PATTERN.fullmatch(value):
        try:
            number = phonenumbers.parse(value)
            canonical = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
            if canonical == value and phonenumbers.is_valid_number(number):
                return
        except phonenumbers.NumberParseException:
            pass
    raise ValidationError(PHONE_HELP, code="invalid_phone")


def validate_sms_length(value):
    try:
        # Modified UTF-8 counts non-BMP characters as six bytes and NUL as two.
        size = len(value.encode("utf-8")) + sum(
            2 if ord(character) > 0xFFFF else character == "\0" for character in value
        )
    except UnicodeEncodeError:
        raise ValidationError(
            "Remove unsupported characters from your message.", code="invalid_text"
        ) from None
    if size > SMS_BYTE_LIMIT:
        raise ValidationError(
            "This SMS exceeds the 9,000-byte limit. Emoji and other characters can use several bytes.",
            code="sms_too_long",
        )
