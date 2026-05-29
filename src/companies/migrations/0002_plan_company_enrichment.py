"""
Data migration to create default subscription plans.
Run: python manage.py migrate companies
"""
from django.db import migrations


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
            'price_monthly_cents': 9900,  # R$ 99/mês
            'price_yearly_cents': 95000,  # R$ 950/ano
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
            'price_monthly_cents': 29900,  # R$ 299/mês
            'price_yearly_cents': 290000,  # R$ 2.900/ano
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
            'price_monthly_cents': 79900,  # R$ 799/mês
            'price_yearly_cents': 770000,  # R$ 7.700/ano
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
    ]

    operations = [
        migrations.RunPython(create_default_plans, reverse_plans),
    ]
