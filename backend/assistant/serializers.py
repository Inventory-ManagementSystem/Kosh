from rest_framework import serializers

from .models import ChatConversation, ChatMessage

MAX_MESSAGE_LENGTH = 2000


class ChatRequestSerializer(serializers.Serializer):
  message = serializers.CharField(max_length=MAX_MESSAGE_LENGTH, trim_whitespace=True)
  conversation_id = serializers.UUIDField(required=False, allow_null=True)


class ChatReplySerializer(serializers.Serializer):
  conversation_id = serializers.UUIDField()
  reply = serializers.CharField()
  tools_used = serializers.ListField(child=serializers.CharField())


class ChatMessageSerializer(serializers.ModelSerializer):
  class Meta:
    model = ChatMessage
    fields = ["id", "role", "content", "tools_used", "created_at"]


class ChatConversationSerializer(serializers.ModelSerializer):
  class Meta:
    model = ChatConversation
    fields = ["id", "title", "created_at", "updated_at"]


class ChatConversationDetailSerializer(ChatConversationSerializer):
  messages = ChatMessageSerializer(many=True, read_only=True)

  class Meta(ChatConversationSerializer.Meta):
    fields = ChatConversationSerializer.Meta.fields + ["messages"]