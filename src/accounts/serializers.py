from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import UserProfile

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Include ``is_staff`` and company info in the JWT so the frontend can gate routes."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["is_staff"] = user.is_staff
        token["username"] = user.username

        # Add company context
        profile = getattr(user, 'userprofile', None)
        if profile and profile.company:
            token["company_id"] = profile.company.id
            token["company_name"] = profile.company.name
        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    company_name = serializers.CharField(required=False, allow_blank=True)
    cnpj = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 'company_name', 'cnpj', 'first_name', 'last_name']
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este email já está cadastrado.")
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Senhas não conferem."})
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('company_name', None)
        validated_data.pop('cnpj', None)
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        # UserProfile is created automatically via signal
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    # Quota info
    plan_name = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    quota = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'company_name',
            'phone',
            'notification_preference',
            'notify_expiration_days',
            'plan_name',
            'subscription_status',
            'quota',
        ]
        read_only_fields = ['id', 'email', 'username', 'first_name', 'last_name', 'company_name']

    def get_plan_name(self, obj):
        if obj.company and obj.company.plan:
            return obj.company.plan.name
        return None

    def get_subscription_status(self, obj):
        if obj.company:
            return obj.company.subscription_status
        return None

    def get_quota(self, obj):
        if not obj.company or not obj.company.plan:
            return None
        plan = obj.company.plan
        company = obj.company
        return {
            'documents': {'used': company.documents_count, 'limit': plan.max_documents},
            'ai_queries': {'used': company.ai_queries_used_this_month, 'limit': plan.max_ai_queries_month},
            'users': {'used': company.users_count, 'limit': plan.max_users},
            'storage_mb': {'limit': plan.max_storage_mb},
            'has_erp_integration': plan.has_erp_integration,
            'has_api_access': plan.has_api_access,
            'has_pdf_reports': plan.has_pdf_reports,
        }
