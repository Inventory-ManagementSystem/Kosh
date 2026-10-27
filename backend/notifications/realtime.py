import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction

from .consumers import user_group
from .serializers import NotificationSerializer

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 3

async def _send_all(items):
  layer = get_channel_layer()
  if layer is None:
    return
  results = await asyncio.wait_for(
    asyncio.gather(
      *(
        layer.group_send(group, {"type": "notify.event", "payload": payload})
        for group, payload in items
      ),
      return_exceptions=True,
    ),
    timeout=SEND_TIMEOUT,
  )
  for result in results:
    if isinstance(result, Exception):
      logger.warning("Live notification send failed: %r", result)


def push_notifications(notifications):
  if not settings.REALTIME_PUSH_ENABLED:
    return
  notifications = list(notifications)
  if not notifications:
    return

  def run():
    try:
      items = [
        (
          user_group(n.user_id),
          {"type": "notification.created", "data": dict(NotificationSerializer(n).data)},
        )
        for n in notifications
      ]
      async_to_sync(_send_all)(items)
    except Exception:
      logger.exception("Live notification push failed")

  transaction.on_commit(run)
