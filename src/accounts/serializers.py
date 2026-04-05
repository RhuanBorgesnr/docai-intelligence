from rest_framework import serializers

from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'email',
            'username',
            'company_name',
            'phone',
            'notification_preference',
            'notify_expiration_days',
        ]
        read_only_fields = ['id', 'email', 'username', 'company_name']
