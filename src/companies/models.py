from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """Subscription plans with quota limits."""

    class PlanTier(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        PROFESSIONAL = "professional", "Professional"
        ENTERPRISE = "enterprise", "Enterprise"

    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=20, choices=PlanTier.choices, default=PlanTier.FREE)
    price_monthly_cents = models.PositiveIntegerField(default=0, help_text="Preço mensal em centavos (BRL)")
    price_yearly_cents = models.PositiveIntegerField(default=0, help_text="Preço anual em centavos (BRL)")

    # Quotas
    max_documents = models.PositiveIntegerField(default=10, help_text="Máximo de documentos armazenados")
    max_pages_per_doc = models.PositiveIntegerField(default=20, help_text="Máximo de páginas por documento")
    max_ai_queries_month = models.PositiveIntegerField(default=50, help_text="Consultas IA por mês")
    max_users = models.PositiveIntegerField(default=1, help_text="Máximo de usuários na empresa")
    max_storage_mb = models.PositiveIntegerField(default=100, help_text="Armazenamento máximo em MB")

    # Features
    has_erp_integration = models.BooleanField(default=False)
    has_api_access = models.BooleanField(default=False)
    has_priority_support = models.BooleanField(default=False)
    has_custom_branding = models.BooleanField(default=False)
    has_pdf_reports = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_monthly_cents']

    def __str__(self):
        return f"{self.name} ({self.tier})"


class Company(models.Model):
    """Multi-tenant company with subscription and billing info."""

    name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, blank=True, unique=True, null=True, help_text="CNPJ formatado")
    email = models.EmailField(blank=True, help_text="Email principal da empresa")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    # Subscription
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='companies')
    subscription_status = models.CharField(
        max_length=20,
        choices=[
            ('trial', 'Trial'),
            ('active', 'Active'),
            ('past_due', 'Past Due'),
            ('cancelled', 'Cancelled'),
            ('expired', 'Expired'),
        ],
        default='trial',
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_started_at = models.DateTimeField(null=True, blank=True)
    subscription_ends_at = models.DateTimeField(null=True, blank=True)

    # Billing
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    # Usage tracking (reset monthly)
    ai_queries_used_this_month = models.PositiveIntegerField(default=0)
    usage_reset_at = models.DateTimeField(null=True, blank=True)

    # Onboarding
    onboarding_completed = models.BooleanField(default=False)
    owner = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_companies',
        help_text="Usuário que criou a empresa"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def is_trial_active(self) -> bool:
        if self.subscription_status != 'trial':
            return False
        if not self.trial_ends_at:
            return True
        return timezone.now() < self.trial_ends_at

    @property
    def is_subscription_active(self) -> bool:
        return self.subscription_status in ('trial', 'active') and (
            self.is_trial_active or self.subscription_status == 'active'
        )

    @property
    def documents_count(self) -> int:
        from documents.models import Document
        return Document.objects.filter(company=self).count()

    @property
    def users_count(self) -> int:
        from accounts.models import UserProfile
        return UserProfile.objects.filter(company=self).count()

    def check_quota(self, resource: str) -> tuple[bool, str]:
        """Check if company is within quota limits. Returns (allowed, message)."""
        if not self.plan:
            return False, "Nenhum plano ativo."

        if not self.is_subscription_active:
            return False, "Assinatura inativa ou expirada."

        if resource == 'document':
            if self.documents_count >= self.plan.max_documents:
                return False, f"Limite de {self.plan.max_documents} documentos atingido."
        elif resource == 'ai_query':
            if self.ai_queries_used_this_month >= self.plan.max_ai_queries_month:
                return False, f"Limite de {self.plan.max_ai_queries_month} consultas IA/mês atingido."
        elif resource == 'user':
            if self.users_count >= self.plan.max_users:
                return False, f"Limite de {self.plan.max_users} usuários atingido."

        return True, "OK"

    def increment_ai_usage(self):
        """Increment AI query counter."""
        self.ai_queries_used_this_month += 1
        self.save(update_fields=['ai_queries_used_this_month'])

    def reset_monthly_usage(self):
        """Reset monthly counters (called by scheduler)."""
        self.ai_queries_used_this_month = 0
        self.usage_reset_at = timezone.now()
        self.save(update_fields=['ai_queries_used_this_month', 'usage_reset_at'])
