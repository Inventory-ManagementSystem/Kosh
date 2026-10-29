from PIL import Image
from pypdf import PdfReader
from rest_framework import serializers

from .models import ChatConversation, ChatMessage

MAX_MESSAGE_LENGTH = 2000
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_PDF_SIZE = 10 * 1024 * 1024
MAX_PDF_PAGES = 20
ATTACHMENT_TYPES = {
  "jpg": "image/jpeg",
  "jpeg": "image/jpeg",
  "png": "image/png",
  "webp": "image/webp",
  "pdf": "application/pdf",
}


def attachment_mime_type(name):
  return ATTACHMENT_TYPES.get(name.rsplit(".", 1)[-1].lower(), "")


def validate_chat_image(file):
  if file.size > MAX_IMAGE_SIZE:
    raise serializers.ValidationError("Image size must not exceed 5 MB.")
  try:
    Image.open(file).verify()
  except Exception:
    raise serializers.ValidationError("Invalid image file. Please upload a valid image.")


def validate_chat_pdf(file):
  if file.size > MAX_PDF_SIZE:
    raise serializers.ValidationError("PDF size must not exceed 10 MB.")
  if file.read(5) != b"%PDF-":
    raise serializers.ValidationError("Invalid PDF file. Please upload a valid PDF.")
  file.seek(0)
  try:
    reader = PdfReader(file)
    if reader.is_encrypted:
      raise serializers.ValidationError("Password-protected PDFs are not supported.")
    pages = len(reader.pages)
  except serializers.ValidationError:
    raise
  except Exception:
    raise serializers.ValidationError("Invalid PDF file. Please upload a valid PDF.")
  if pages > MAX_PDF_PAGES:
    raise serializers.ValidationError(f"PDF must not have more than {MAX_PDF_PAGES} pages.")


class ChatRequestSerializer(serializers.Serializer):
  message = serializers.CharField(
    max_length=MAX_MESSAGE_LENGTH, trim_whitespace=True, required=False, allow_blank=True,
    default="",
  )
  conversation_id = serializers.UUIDField(required=False, allow_null=True)
  attachment = serializers.FileField(required=False, allow_null=True)

  def validate_attachment(self, file):
    if file is None:
      return None
    mime_type = attachment_mime_type(file.name)
    if not mime_type:
      raise serializers.ValidationError("Only JPG, PNG, WEBP images or PDF files are allowed.")
    if mime_type == "application/pdf":
      validate_chat_pdf(file)
    else:
      validate_chat_image(file)
    file.seek(0)
    return file

  def validate(self, attrs):
    if not attrs.get("message") and not attrs.get("attachment"):
      raise serializers.ValidationError({"message": "Send a message or attach a file."})
    return attrs


class ChatReplySerializer(serializers.Serializer):
  conversation_id = serializers.UUIDField()
  reply = serializers.CharField()
  tools_used = serializers.ListField(child=serializers.CharField())


class ChatMessageSerializer(serializers.ModelSerializer):
  class Meta:
    model = ChatMessage
    fields = [
      "id", "role", "content", "attachment", "attachment_name", "attachment_type",
      "tools_used", "created_at",
    ]


class ChatConversationSerializer(serializers.ModelSerializer):
  class Meta:
    model = ChatConversation
    fields = ["id", "title", "created_at", "updated_at"]


class ChatConversationDetailSerializer(ChatConversationSerializer):
  messages = ChatMessageSerializer(many=True, read_only=True)

  class Meta(ChatConversationSerializer.Meta):
    fields = ChatConversationSerializer.Meta.fields + ["messages"]