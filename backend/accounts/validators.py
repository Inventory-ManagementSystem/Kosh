import re

from rest_framework import serializers

PHONE_REGEX = re.compile(r"[0-9]{10}")
PHONE_ERROR = "Enter a valid 10-digit phone number."


def validate_phone_number(value):
    """Phone is optional: allow empty, otherwise exactly 10 digits."""
    value = (value or "").strip()
    if value and not PHONE_REGEX.fullmatch(value):
        raise serializers.ValidationError(PHONE_ERROR)
    return value
