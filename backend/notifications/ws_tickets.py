import secrets

from django.conf import settings
from django.core.cache import cache

PREFIX = "ws_ticket:"


def issue_ticket(user_id):
  ticket = secrets.token_urlsafe(32)
  cache.set(f"{PREFIX}{ticket}", user_id, timeout=settings.WS_TICKET_TTL_SECONDS)
  return ticket


def redeem_ticket(ticket):
  if not ticket:
    return None
  key = f"{PREFIX}{ticket}"
  user_id = cache.get(key)
  if user_id is None:
    return None
 
  if not cache.delete(key):
    return None
  return user_id
