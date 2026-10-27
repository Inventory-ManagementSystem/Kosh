from django.conf import settings
from django.urls import path
from . import views


urlpatterns = [
  path("", views.NotificationListApi.as_view(), name="notification-list"),
  path("unread-count/", views.UnreadCountApi.as_view(), name="notification-unread-count"),
  path("read-all/", views.MarkAllReadApi.as_view(), name="notification-read-all"),
  path("<int:pk>/read/", views.MarkReadApi.as_view(), name="notification-read"),
  path("<int:pk>/", views.DeleteNotificationApi.as_view(), name="notification-delete"),
  path("delete-all/", views.DeleteAllNotificationsApi.as_view(), name="notification-delete-all"),
  path("push/config/", views.PushConfigApi.as_view(), name="push-config"),
  path("push/register/", views.RegisterDeviceApi.as_view(), name="push-register"),
  path("push/unregister/", views.UnregisterDeviceApi.as_view(), name="push-unregister"),
  path("push/test/", views.PushTestApi.as_view(), name="push-test"),
  path("ws-ticket/", views.WsTicketApi.as_view(), name="ws-ticket"),
]


if settings.DEBUG:
  from . import debug_views
  urlpatterns += [
    path("push/test-page/", debug_views.push_test_page, name="push-test-page"),
    path("push/test-page/sw.js", debug_views.push_test_service_worker, name="push-test-sw"),
  ]
