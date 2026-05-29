import logging

from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .serializers import UserProfileSerializer, RegisterSerializer
from .tokens import (
    send_verification_email,
    verify_email_token,
    send_password_reset_email,
    reset_password_with_token,
)

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    """Register a new user account + create company (onboarding start)."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()

            # Create company if company_name provided
            company_name = request.data.get('company_name')
            if company_name:
                from companies.models import Company, Plan
                # Get or create free plan
                free_plan = Plan.objects.filter(tier='free').first()
                company = Company.objects.create(
                    name=company_name,
                    cnpj=request.data.get('cnpj', ''),
                    email=user.email,
                    plan=free_plan,
                    subscription_status='trial',
                    trial_ends_at=timezone.now() + timedelta(days=14),
                    owner=user,
                )
                # Link user to company
                profile = UserProfile.objects.get(user=user)
                profile.company = company
                profile.save(update_fields=['company'])

            # Send verification email
            if user.email:
                send_verification_email(user)

            return Response(
                {
                    "message": "Conta criada com sucesso. Verifique seu email.",
                    "username": user.username,
                    "email_sent": bool(user.email),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Registration error: %s", e)
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class VerifyEmailView(APIView):
    """Verify email address via token link."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        if not uid or not token:
            return Response({"error": "uid e token são obrigatórios."}, status=400)

        success, message = verify_email_token(uid, token)
        if success:
            return Response({"message": message})
        return Response({"error": message}, status=400)


class PasswordResetRequestView(APIView):
    """Request a password reset email."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email é obrigatório."}, status=400)

        send_password_reset_email(email)
        # Always return success to prevent email enumeration
        return Response({"message": "Se o email existir, enviaremos um link de redefinição."})


class PasswordResetConfirmView(APIView):
    """Confirm password reset with token and set new password."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')

        if not all([uid, token, new_password]):
            return Response({"error": "uid, token e new_password são obrigatórios."}, status=400)

        success, message = reset_password_with_token(uid, token, new_password)
        if success:
            return Response({"message": message})
        return Response({"error": message}, status=400)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """Get or update the current user's profile."""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile
