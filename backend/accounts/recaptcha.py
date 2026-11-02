import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)
VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def verify_recaptcha(token, expected_action):
    if not settings.RECAPTCHA_ENABLED:
        return True
    if not token:
        return False
    try:
        resp = requests.post(
            VERIFY_URL,
            data={"secret": settings.RECAPTCHA_SECRET_KEY, "response": token},
            timeout=5,
        )
        data = resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("reCAPTCHA verification request failed")
        return False

    if not data.get("success"):
        logger.warning("reCAPTCHA rejected: %s", data.get("error-codes"))
        return False
    if data.get("action") != expected_action:
        logger.warning("reCAPTCHA action mismatch: expected %s, got %s",
                       expected_action, data.get("action"))
        return False
    score = data.get("score", 0)
    if score < settings.RECAPTCHA_MIN_SCORE:
        logger.warning("reCAPTCHA low score %.2f for %s", score, expected_action)
        return False
    return True
