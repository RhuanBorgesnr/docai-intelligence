"""
Token-based email verification and password reset.

Uses Django's built-in token generator (cryptographically secure, time-limited).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

logger = logging.getLogger(__name__)

User = get_user_model()

FRONTEND_URL = settings.CSRF_TRUSTED_ORIGINS[0] if settings.CSRF_TRUSTED_ORIGINS else 'http://localhost:3000'


def send_verification_email(user) -> bool:
    """Send email verification link to user."""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    verification_url = f"{FRONTEND_URL}/verify-email/{uid}/{token}"

    subject = "DocAI — Confirme seu email"
    message = (
        f"Olá {user.first_name or user.username},\n\n"
        f"Confirme seu email clicando no link abaixo:\n\n"
        f"{verification_url}\n\n"
        f"Este link expira em 24 horas.\n\n"
        f"— Equipe DocAI"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to send verification email to %s: %s", user.email, e)
        return False


def verify_email_token(uidb64: str, token: str) -> tuple[bool, str]:
    """Verify the email confirmation token. Returns (success, message)."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False, "Link inválido."

    if not default_token_generator.check_token(user, token):
        return False, "Link expirado ou já utilizado."

    user.is_active = True
    user.save(update_fields=['is_active'])
    logger.info("Email verified for user %s", user.username)
    return True, "Email verificado com sucesso."


def send_password_reset_email(email: str) -> bool:
    """Send password reset link. Always returns True to prevent email enumeration."""
    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        # Don't reveal if email exists
        return True

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = f"{FRONTEND_URL}/reset-password/{uid}/{token}"

    subject = "DocAI — Redefinir senha"
    message = (
        f"Olá {user.first_name or user.username},\n\n"
        f"Clique no link abaixo para redefinir sua senha:\n\n"
        f"{reset_url}\n\n"
        f"Se você não solicitou, ignore este email.\n"
        f"Este link expira em 24 horas.\n\n"
        f"— Equipe DocAI"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Password reset email sent to %s", email)
    except Exception as e:
        logger.error("Failed to send password reset email: %s", e)

    return True


def reset_password_with_token(uidb64: str, token: str, new_password: str) -> tuple[bool, str]:
    """Validate token and set new password. Returns (success, message)."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False, "Link inválido."

    if not default_token_generator.check_token(user, token):
        return False, "Link expirado ou já utilizado."

    if len(new_password) < 8:
        return False, "Senha deve ter no mínimo 8 caracteres."

    user.set_password(new_password)
    user.save()
    logger.info("Password reset for user %s", user.username)
    return True, "Senha redefinida com sucesso."
