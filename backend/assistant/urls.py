from django.urls import path

from . import views

urlpatterns = [
  path("chat/", views.ChatApi.as_view(), name="assistant-chat"),
  path("conversations/", views.ConversationListApi.as_view(), name="assistant-conversation-list"),
  path("conversations/<uuid:pk>/",views.ConversationDetailApi.as_view(),name="assistant-conversation-detail"),
]