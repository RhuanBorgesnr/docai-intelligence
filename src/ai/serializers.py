from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    document_ids = serializers.ListField(
        child=serializers.IntegerField()
    )
    question = serializers.CharField()