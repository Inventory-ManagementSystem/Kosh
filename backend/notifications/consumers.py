from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .ws_tickets import redeem_ticket


def user_group(user_id):
  return f"user_{user_id}"


class NotificationConsumer(AsyncJsonWebsocketConsumer):
  async def connect(self):
    query = parse_qs(self.scope["query_string"].decode())
    ticket = query.get("ticket", [""])[0]
    user_id = await sync_to_async(redeem_ticket)(ticket)
    if user_id is None:
      await self.close(code=4401)
      return
    self.group_name = user_group(user_id)
    await self.channel_layer.group_add(self.group_name, self.channel_name)
    await self.accept()

  async def disconnect(self, code):
    group_name = getattr(self, "group_name", None)
    if group_name:
      await self.channel_layer.group_discard(group_name, self.channel_name)

  async def receive_json(self, content, **kwargs):
    pass

  async def notify_event(self, event):
    await self.send_json(event["payload"])
