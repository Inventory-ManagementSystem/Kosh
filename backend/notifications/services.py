from django.db import transaction
from .models import Notification
from .push import send_push_to_user


def _push_after_commit(user_id, title, body):
  transaction.on_commit(lambda: send_push_to_user(user_id, title, body))


def notify(user, title, body="", kind=Notification.Kind.GENERAL, push=True):
  notification = Notification.objects.create(
    user=user,
    kind=kind,
    title=title[:150],
    body=body,
  )
  if push:
    _push_after_commit(user.pk, notification.title, body)
  return notification


def notify_many(users, title, body="", kind=Notification.Kind.GENERAL, push=True):
  users = list(users)
  notifications = Notification.objects.bulk_create([
    Notification(user=user, kind=kind, title=title[:150], body=body)
    for user in users
  ])
  if push:
    for user in users:
      _push_after_commit(user.pk, title[:150], body)
  return notifications
