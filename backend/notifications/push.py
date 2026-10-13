import base64
import json
import logging

from django.conf import settings

from .models import DeviceToken

logger = logging.getLogger(__name__)

_DEAD_TOKEN_ERRORS = ("UnregisteredError", "SenderIdMismatchError", "InvalidArgumentError")


def push_enabled():
  return bool(settings.FIREBASE_CREDENTIALS_B64)


def _firebase_app():
  import firebase_admin
  from firebase_admin import credentials

  try:
    return firebase_admin.get_app()
  except ValueError:
    info = json.loads(base64.b64decode(settings.FIREBASE_CREDENTIALS_B64))
    return firebase_admin.initialize_app(credentials.Certificate(info))


def send_push_to_user(user_id, title, body="", url="/"):
  if not push_enabled():
    return 0

  tokens = list(DeviceToken.objects.filter(user_id=user_id).values_list("token", flat=True))
  if not tokens:
    return 0

  try:
    from firebase_admin import messaging

    message = messaging.MulticastMessage(
      tokens=tokens,
      data={"title": title, "body": body, "url": url},
    )
    result = messaging.send_each_for_multicast(message, app=_firebase_app())
  except Exception:
    logger.exception("FCM push failed for user %s", user_id)
    return 0

  dead = [
    tokens[i]
    for i, response in enumerate(result.responses)
    if not response.success and type(response.exception).__name__ in _DEAD_TOKEN_ERRORS
  ]
  if dead:
    DeviceToken.objects.filter(token__in=dead).delete()
  for i, response in enumerate(result.responses):
    if not response.success and tokens[i] not in dead:
      logger.warning("FCM push to a device of user %s failed: %s", user_id, response.exception)

  return result.success_count
