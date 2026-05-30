"""
Migration to add Plan model, enrich Company with subscription fields, and seed default plans.
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def create_default_plans(apps, schema_editor):
    Plan = apps.get_model('companies', 'Plan')

    plans = [
        {
            'name': 'Free',
            'tier': 'free',
            'price_monthly_cents': 0,
            'price_yearly_cents': 0,
            'max_documents': 10,
            'max_pages_per_doc': 10,
            'max_ai_queries_month': 20,
            'max_users': 1,
            'max_storage_mb': 50,
            'has_erp_integration': False,
            'has_api_access': False,
            'has_priority_support': False,
            'has_custom_branding': False,
            'has_pdf_reports': False,
        },
        {
            'name': 'Starter',
            'tier': 'starter',
            'price_monthly_cents': 9900,
            'price_yearly_cents': 95000,
            'max_documents': 100,
            'max_pages_per_doc': 50,
            'max_ai_queries_month': 200,
            'max_users': 3,
            'max_storage_mb': 500,
            'has_erp_integration': False,
            'has_api_access': False,
            'has_priority_support': False,
            'has_custom_branding': False,
            'has_pdf_reports': True,
        },
        {
            'name': 'Professional',
            'tier': 'professional',
            'price_monthly_cents': 29900,
            'price_yearly_cents': 290000,
            'max_documents': 1000,
            'max_pages_per_doc': 100,
            'max_ai_queries_month': 1000,
            'max_users': 10,
            'max_storage_mb': 5000,
            'has_erp_integration': True,
            'has_api_access': True,
            'has_priority_support': False,
            'has_custom_branding': False,
            'has_pdf_reports': True,
        },
        {
            'name': 'Enterprise',
            'tier': 'enterprise',
            'price_monthly_cents': 79900,
            'price_yearly_cents': 770000,
            'max_documents': 99999,
            'max_pages_per_doc': 500,
            'max_ai_queries_month': 99999,
            'max_users': 50,
            'max_storage_mb': 50000,
            'has_erp_integration': True,
            'has_api_access': True,
            'has_priority_support': True,
            'has_custom_branding': True,
            'has_pdf_reports': True,
        },
    ]

    for plan_data in plans:
        Plan.objects.get_or_create(tier=plan_data['tier'], defaults=plan_data)


def reverse_plans(apps, schema_editor):
    Plan = apps.get_model('companies', 'Plan')
    Plan.objects.filter(tier__in=['free', 'starter', 'professional', 'enterprise']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create Plan model
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('tier', models.CharField(choices=[('free', 'Free'), ('starter', 'Starter'), ('professional', 'Professional'), ('enterprise', 'Enterprise')], default='free', max_length=20)),
                ('price_monthly_cents', models.PositiveIntegerField(default=0, help_text='Preço mensal em centavos (BRL)')),
                ('price_yearly_cents', models.PositiveIntegerField(default=0, help_text='Preço anual em centavos (BRL)')),
                ('max_documents', models.PositiveIntegerField(default=10, help_text='Máximo de documentos armazenados')),
                ('max_pages_per_doc', models.PositiveIntegerField(default=20, help_text='Máximo de páginas por documento')),
                ('max_ai_queries_month', models.PositiveIntegerField(default=50, help_text='Consultas IA por mês')),
                ('max_users', models.PositiveIntegerField(default=1, help_text='Máximo de usuários na empresa')),
                ('max_storage_mb', models.PositiveIntegerField(default=100, help_text='Armazenamento máximo em MB')),
                ('has_erp_integration', models.BooleanField(default=False)),
                ('has_api_access', models.BooleanField(default=False)),
                ('has_priority_support', models.BooleanField(default=False)),
                ('has_custom_branding', models.BooleanField(default=False)),
                ('has_pdf_reports', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['price_monthly_cents'],
            },
        ),
        # 2. Add new fields to Company
        migrations.AddField(model_name='company', name='cnpj', field=models.CharField(blank=True, max_length=18, null=True, unique=True, help_text='CNPJ formatado')),
        migrations.AddField(model_name='company', name='email', field=models.EmailField(blank=True, max_length=254, help_text='Email principal da empresa')),
        migrations.AddField(model_name='company', name='phone', field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name='company', name='address', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='company', name='plan', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='companies', to='companies.plan')),
        migrations.AddField(model_name='company', name='subscription_status', field=models.CharField(choices=[('trial', 'Trial'), ('active', 'Active'), ('past_due', 'Past Due'), ('cancelled', 'Cancelled'), ('expired', 'Expired')], default='trial', max_length=20)),
        migrations.AddField(model_name='company', name='trial_ends_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='company', name='subscription_started_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='company', name='subscription_ends_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='company', name='stripe_customer_id', field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name='company', name='stripe_subscription_id', field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name='company', name='ai_queries_used_this_month', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='company', name='usage_reset_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='company', name='onboarding_completed', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='company', name='owner', field=models.ForeignKey(blank=True, help_text='Usuário que criou a empresa', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_companies', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='company', name='updated_at', field=models.DateTimeField(auto_now=True)),
        # 3. Seed default plans
        migrations.RunPython(create_default_plans, reverse_plans),
    ]
