from django.contrib import admin
from django.utils.html import format_html

from .models import Company, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "tier", "preco_mensal", "max_documents", "max_ai_queries_month", "max_users", "max_storage_mb", "is_active")
    list_filter = ("tier", "is_active")
    search_fields = ("name",)

    @admin.display(description="Preço/mês")
    def preco_mensal(self, obj):
        return f"R$ {obj.price_monthly_cents / 100:.2f}"

    class Meta:
        verbose_name = "Plano"
        verbose_name_plural = "Planos"


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "cnpj", "plano", "status_assinatura", "queries_ia", "onboarding_completed", "created_at")
    list_filter = ("subscription_status", "plan", "onboarding_completed")
    search_fields = ("name", "cnpj", "email")
    raw_id_fields = ("owner", "plan")
    readonly_fields = ("created_at", "updated_at", "ai_queries_used_this_month", "usage_reset_at")
    fieldsets = (
        ("Dados da Empresa", {
            "fields": ("name", "cnpj", "email", "phone", "address", "owner")
        }),
        ("Assinatura", {
            "fields": ("plan", "subscription_status", "trial_ends_at", "subscription_started_at", "subscription_ends_at")
        }),
        ("Stripe", {
            "fields": ("stripe_customer_id", "stripe_subscription_id"),
            "classes": ("collapse",),
        }),
        ("Uso", {
            "fields": ("ai_queries_used_this_month", "usage_reset_at", "onboarding_completed")
        }),
        ("Datas", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Plano")
    def plano(self, obj):
        return obj.plan.name if obj.plan else "Sem plano"

    @admin.display(description="Status")
    def status_assinatura(self, obj):
        colors = {"active": "green", "trial": "blue", "past_due": "orange", "cancelled": "red", "expired": "gray"}
        color = colors.get(obj.subscription_status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_subscription_status_display())

    @admin.display(description="Queries IA")
    def queries_ia(self, obj):
        limit = obj.plan.max_ai_queries_month if obj.plan else "∞"
        return f"{obj.ai_queries_used_this_month}/{limit}"
