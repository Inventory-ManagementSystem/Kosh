from django.shortcuts import render

# Create your views here.
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.pagination import StandardPagination
from accounts.permissions import HasBusinessAccess
from accounts.responses import error_response, success_response, validation_error_response

from .llm import AssistantError, GeminiAgent
from .models import ChatConversation, ChatMessage
from .serializers import (
  ChatConversationDetailSerializer,
  ChatConversationSerializer,
  ChatReplySerializer,
  ChatRequestSerializer,
)

HISTORY_LIMIT = 20 


def get_agent():
  return GeminiAgent()


def user_conversations(request):
  return ChatConversation.objects.filter(business=request.business, user=request.user)


class ConversationPagination(StandardPagination):
  message = "Conversations fetched."


@extend_schema(
  tags=["Assistant"],
  summary="Ask the AI assistant a question about your business data",
  description=(
    "Send `message`. Leave out `conversation_id` to start a new conversation; send the "
    "returned `conversation_id` with follow-up questions to keep context."
  ),
  request=ChatRequestSerializer,
  responses={200: ChatReplySerializer},
)
class ChatApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]

  def post(self, request):
    serializer = ChatRequestSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    message = serializer.validated_data["message"]
    conversation_id = serializer.validated_data.get("conversation_id")

    conversation = None
    history = []
    if conversation_id:
      conversation = get_object_or_404(user_conversations(request), pk=conversation_id)
      recent = conversation.messages.order_by("-created_at", "role")[:HISTORY_LIMIT]
      history = list(reversed(recent))

    try:
      result = get_agent().run(
        business=request.business, user=request.user, history=history, message=message
      )
    except AssistantError as exc:
      return error_response(exc.message, exc.code, status=exc.status)

    with transaction.atomic():
      if conversation is None:
        conversation = ChatConversation.objects.create(
          business=request.business, user=request.user, title=message[:60],
        )
      ChatMessage.objects.create(
        conversation=conversation, role=ChatMessage.Role.USER, content=message,
      )
      ChatMessage.objects.create(
        conversation=conversation, role=ChatMessage.Role.ASSISTANT,
        content=result.reply, tools_used=result.tools_used,
      )
      conversation.save(update_fields=["updated_at"])

    return success_response(
      "Reply generated.",
      {
        "conversation_id": str(conversation.id),
        "reply": result.reply,
        "tools_used": result.tools_used,
      },
    )


@extend_schema(tags=["Assistant"], summary="List your assistant conversations",
               responses={200: ChatConversationSerializer(many=True)})
class ConversationListApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]

  def get(self, request):
    paginator = ConversationPagination()
    page = paginator.paginate_queryset(user_conversations(request), request)
    return paginator.get_paginated_response(ChatConversationSerializer(page, many=True).data)


@extend_schema(tags=["Assistant"], responses={200: ChatConversationDetailSerializer})
class ConversationDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]

  def get_conversation(self, request, pk):
    return get_object_or_404(user_conversations(request), pk=pk)

  @extend_schema(summary="Get one conversation with its messages")
  def get(self, request, pk):
    conversation = self.get_conversation(request, pk)
    return success_response(
      "Conversation fetched.", ChatConversationDetailSerializer(conversation).data
    )

  @extend_schema(summary="Delete a conversation")
  def delete(self, request, pk):
    self.get_conversation(request, pk).delete()
    return success_response("Conversation deleted.", status=status.HTTP_200_OK)