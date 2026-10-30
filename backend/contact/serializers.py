from rest_framework import serializers


class ContactSerializer(serializers.Serializer):
  email = serializers.EmailField(max_length=254)
  message = serializers.CharField(min_length=10, max_length=2000)
  website = serializers.CharField(required=False, allow_blank=True, max_length=200)

