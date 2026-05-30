from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = "Perfil"
    verbose_name_plural = "Perfil"


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active", "is_superuser")


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "empresa", "telefone", "preferencia_notificacao")
    search_fields = ("user__username", "user__email", "company__name")
    list_filter = ("notification_preference",)
    raw_id_fields = ("user", "company")

    @admin.display(description="Empresa")
    def empresa(self, obj):
        return obj.company.name if obj.company else "—"

    @admin.display(description="Telefone")
    def telefone(self, obj):
        return obj.phone or "—"

    @admin.display(description="Notificação")
    def preferencia_notificacao(self, obj):
        return obj.get_notification_preference_display() if hasattr(obj, 'get_notification_preference_display') else obj.notification_preference


# Customizar títulos do admin
admin.site.site_header = "DocAI Intelligence — Administração"
admin.site.site_title = "DocAI Admin"
admin.site.index_title = "Painel Administrativo"
