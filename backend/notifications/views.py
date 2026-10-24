from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from accounts.pagination import StandardPagination
from accounts.responses import error_response, success_response, validation_error_response
from accounts.swagger import UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

from .models import DeviceToken, Notification
from .push import push_enabled, send_push_to_user
from .serializers import DeviceTokenSerializer, NotificationSerializer
from .ws_tickets import issue_ticket


NOTIFICATION_EXAMPLE = {
  "id": 12,
  "kind": "low_stock",
  "title": "Parle-G Biscuits 200g is running low",
  "body": "Stock is 45, below the reorder point of 230. Suggested order: 1,180 units.",
  "is_read": False,
  "read_at": None,
  "created_at": "2026-10-11T09:00:00Z",
}


class NotificationPagination(StandardPagination):
  message = "Notifications fetched."


def my_notifications(request):
  return Notification.objects.filter(user=request.user)


class NotificationListApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="List My Notifications",
    description=(
      "The logged-in user's notifications, newest first, paginated. Works for "
      "every role: owner, employee and supplier."
    ),
    parameters=[
      OpenApiParameter(
        "is_read", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
        description="`false` for unread only, `true` for read only. Leave out for all.",
      ),
      OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY),
      OpenApiParameter(
        "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY,
        description="Default 10, maximum 50.",
      ),
    ],
    responses={
      200: resp("One page of notifications.",
                ok_example("Notifications", "Notifications fetched.",
                           data={"count": 1, "next": None, "previous": None,
                                 "results": [NOTIFICATION_EXAMPLE]})),
      400: resp("Bad filter value.",
                err_example("Bad Filter", "Request failed.", "BAD_REQUEST",
                            errors={"is_read": "Use true or false."})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def get(self, request):
    notifications = my_notifications(request)

    is_read = request.query_params.get("is_read")
    if is_read is not None:
      value = is_read.lower()
      if value not in ("true", "false"):
        raise ValidationError({"is_read": "Use true or false."})
      notifications = notifications.filter(is_read=(value == "true"))

    paginator = NotificationPagination()
    page = paginator.paginate_queryset(notifications, request)
    serializer = NotificationSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


class UnreadCountApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Unread Notification Count",
    description="The number to show on the bell icon.",
    responses={
      200: resp("Unread count.",
                ok_example("Count", "Unread count fetched.", data={"unread": 3})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def get(self, request):
    count = my_notifications(request).filter(is_read=False).count()
    return success_response("Unread count fetched.", {"unread": count})


class MarkReadApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Mark Notification as Read",
    description=(
      "Marks one of your notifications as read. Marking one that is already read "
      "is fine and changes nothing. Another user's notification returns 404."
    ),
    request=None,
    responses={
      200: resp("Marked as read.",
                ok_example("Read", "Notification marked as read.",
                           data={**NOTIFICATION_EXAMPLE, "is_read": True,
                                 "read_at": "2026-10-11T09:05:00Z"})),
      401: UNAUTHORIZED_RESPONSE,
      404: resp("Not found, or not yours.",
                err_example("Not Found", "No Notification matches the given query.",
                            "NOT_FOUND")),
    },
  )
  def post(self, request, pk):
    notification = get_object_or_404(my_notifications(request), pk=pk)
    if not notification.is_read:
      notification.is_read = True
      notification.read_at = timezone.now()
      notification.save(update_fields=["is_read", "read_at"])
    return success_response(
      "Notification marked as read.",
      NotificationSerializer(notification).data,
    )


class MarkAllReadApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Mark All Notifications as Read",
    request=None,
    responses={
      200: resp("All marked as read.",
                ok_example("All Read", "All notifications marked as read.",
                           data={"updated": 3})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def post(self, request):
    updated = my_notifications(request).filter(is_read=False).update(
      is_read=True, read_at=timezone.now(),
    )
    return success_response("All notifications marked as read.", {"updated": updated})


class DeleteNotificationApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Delete Notification",
    description=(
      "Permanently deletes one of your notifications, read or unread. "
      "Another user's notification returns 404."
    ),
    request=None,
    responses={
      200: resp("Deleted.", ok_example("Deleted", "Notification deleted.")),
      401: UNAUTHORIZED_RESPONSE,
      404: resp("Not found, or not yours.",
                err_example("Not Found", "No Notification matches the given query.",
                            "NOT_FOUND")),
    },
  )
  def delete(self, request, pk):
    notification = get_object_or_404(my_notifications(request), pk=pk)
    notification.delete()
    return success_response("Notification deleted.")


class DeleteAllNotificationsApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Delete All Notifications",
    description=(
      "Permanently deletes all of your notifications. Add `?is_read=true` to delete "
      "only the ones already read (a \"Clear read\" button), or `?is_read=false` for "
      "only unread ones. Only ever touches your own notifications."
    ),
    parameters=[
      OpenApiParameter(
        "is_read", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
        description="`true` = only read ones, `false` = only unread ones. Leave out for all.",
      ),
    ],
    request=None,
    responses={
      200: resp("Deleted.",
                ok_example("All Deleted", "Notifications deleted.", data={"deleted": 12}),
                ok_example("Nothing To Delete", "Notifications deleted.", data={"deleted": 0})),
      400: resp("Bad filter value.",
                err_example("Bad Filter", "Request failed.", "BAD_REQUEST",
                            errors={"is_read": "Use true or false."})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def delete(self, request):
    notifications = my_notifications(request)
    is_read = request.query_params.get("is_read")
    if is_read is not None:
      value = is_read.lower()
      if value not in ("true", "false"):
        raise ValidationError({"is_read": "Use true or false."})
      notifications = notifications.filter(is_read=(value == "true"))
    deleted, _ = notifications.delete()
    return success_response("Notifications deleted.", {"deleted": deleted})


PUSH_DISABLED_RESPONSE = resp(
  "Push is not configured on the server (Firebase settings missing).",
  err_example("Push Disabled", "Push notifications are not configured.", "PUSH_DISABLED"),
)


def push_disabled_error():
  return error_response(
    "Push notifications are not configured.", "PUSH_DISABLED",
    status=status.HTTP_503_SERVICE_UNAVAILABLE,
  )


def firebase_web_config():
  return {
    "apiKey": settings.FIREBASE_WEB_API_KEY,
    "projectId": settings.FIREBASE_PROJECT_ID,
    "messagingSenderId": settings.FIREBASE_MESSAGING_SENDER_ID,
    "appId": settings.FIREBASE_APP_ID,
  }


class PushConfigApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Get Firebase Web Config",
    description=(
      "The public Firebase config and VAPID key the frontend needs to call "
      "`getToken()`. These values are designed to be public."
    ),
    responses={
      200: resp("Config.",
                ok_example("Config", "Push config fetched.",
                           data={"firebase": {"apiKey": "AIza...", "projectId": "kosh-demo",
                                              "messagingSenderId": "1234567890",
                                              "appId": "1:1234567890:web:abc123"},
                                 "vapid_key": "BOr8...base64url..."})),
      401: UNAUTHORIZED_RESPONSE,
      503: PUSH_DISABLED_RESPONSE,
    },
  )
  def get(self, request):
    if not push_enabled():
      return push_disabled_error()
    return success_response("Push config fetched.", {
      "firebase": firebase_web_config(),
      "vapid_key": settings.FIREBASE_VAPID_KEY,
    })


class RegisterDeviceApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Register This Device for Push",
    description=(
      "Saves the FCM token from Firebase `getToken()`. Calling it again with the "
      "same token is fine. If the token belonged to another account (shared "
      "computer), it moves to the logged-in user."
    ),
    request=DeviceTokenSerializer,
    responses={
      200: resp("Registered.", ok_example("Registered", "Push enabled for this device.",
                                          data={"registered": True})),
      400: resp("Missing token.",
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"token": ["This field is required."]})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def post(self, request):
    serializer = DeviceTokenSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    DeviceToken.objects.update_or_create(
      token=serializer.validated_data["token"],
      defaults={
        "user": request.user,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
      },
    )
    return success_response("Push enabled for this device.", {"registered": True})


class UnregisterDeviceApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Unregister This Device from Push",
    description="Call on logout or when the user turns push off.",
    request=DeviceTokenSerializer,
    responses={
      200: resp("Unregistered.", ok_example("Unregistered", "Push disabled for this device.",
                                            data={"removed": 1})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def post(self, request):
    serializer = DeviceTokenSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    removed, _ = DeviceToken.objects.filter(
      user=request.user, token=serializer.validated_data["token"],
    ).delete()
    return success_response("Push disabled for this device.", {"removed": removed})


class PushTestApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Send a Test Push to Myself",
    description="Sends a test push to every device you registered. Does not create an in-app notification.",
    request=None,
    responses={
      200: resp("Sent.", ok_example("Sent", "Test push sent.", data={"sent": 1})),
      401: UNAUTHORIZED_RESPONSE,
      503: PUSH_DISABLED_RESPONSE,
    },
  )
  def post(self, request):
    if not push_enabled():
      return push_disabled_error()
    sent = send_push_to_user(request.user.pk, "Kosh test notification", "Push is working.")
    return success_response("Test push sent.", {"sent": sent})

class WsTicketApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Get a WebSocket Ticket",
    description=(
      "Returns a random one-time ticket that is valid for 30 seconds. Open "
      "`wss://<host>/ws/notifications/?ticket=<ticket>` with it to receive "
      "notifications live. Each ticket works once, so fetch a new one for "
      "every connection attempt."
    ),
    request=None,
    responses={
      200: resp("Ticket issued.",
                ok_example("Ticket", "WebSocket ticket issued.",
                           data={"ticket": "q3F...urlsafe...", "expires_in": 30})),
      401: UNAUTHORIZED_RESPONSE,
    },
  )
  def post(self, request):
    ticket = issue_ticket(request.user.pk)
    return success_response(
      "WebSocket ticket issued.",
      {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_SECONDS},
    )
