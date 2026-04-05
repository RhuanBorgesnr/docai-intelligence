"""
Document API views.
"""
from datetime import date, timedelta

from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import Document, FinancialIndicator, ContractClause
from .serializers import (
    DocumentDetailSerializer, DocumentListSerializer, DocumentUploadSerializer,
    FinancialIndicatorSerializer, ContractClauseSerializer
)
from .tasks import process_document, extract_and_save_indicators, extract_and_save_clauses
from .reports import generate_financial_report, generate_comparison_report


@extend_schema(tags=['Documents'])
class DocumentListCreateView(CreateAPIView, ListAPIView):
    """List documents and upload new documents."""
    queryset = Document.objects.all()
    serializer_class = DocumentListSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Listar documentos",
        description="Retorna todos os documentos da empresa do usuário autenticado.",
        parameters=[
            OpenApiParameter(
                name='document_type',
                type=str,
                description='Filtrar por tipo: dre, balance, contract, certificate, invoice, report, other',
                examples=[
                    OpenApiExample('DRE', value='dre'),
                    OpenApiExample('Contrato', value='contract'),
                ]
            ),
            OpenApiParameter(
                name='expiring_days',
                type=int,
                description='Filtrar documentos vencendo nos próximos X dias',
                examples=[OpenApiExample('7 dias', value=7)]
            ),
        ],
        responses={200: DocumentListSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Upload de documento",
        description="Faz upload de um novo documento PDF para processamento com IA.",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {'type': 'string', 'format': 'binary', 'description': 'Arquivo PDF'},
                    'title': {'type': 'string', 'description': 'Título do documento'},
                    'document_type': {
                        'type': 'string',
                        'enum': ['dre', 'balance', 'contract', 'certificate', 'invoice', 'report', 'other'],
                        'description': 'Tipo do documento'
                    },
                    'expiration_date': {'type': 'string', 'format': 'date', 'description': 'Data de vencimento (opcional)'},
                    'reference_date': {'type': 'string', 'format': 'date', 'description': 'Data de referência (opcional)'},
                },
                'required': ['file', 'title', 'document_type']
            }
        },
        examples=[
            OpenApiExample(
                'Upload DRE',
                value={
                    'title': 'DRE 2024',
                    'document_type': 'dre',
                    'reference_date': '2024-12-31'
                },
                request_only=True
            ),
            OpenApiExample(
                'Upload Contrato',
                value={
                    'title': 'Contrato de Prestação de Serviços',
                    'document_type': 'contract',
                    'expiration_date': '2025-12-31'
                },
                request_only=True
            ),
        ],
        responses={
            201: OpenApiExample(
                'Documento criado',
                value={
                    'id': 1,
                    'title': 'DRE 2024',
                    'document_type': 'dre',
                    'processing_status': 'processing',
                    'created_at': '2024-01-15T10:30:00Z'
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        try:
            company = self.request.user.userprofile.company
            qs = qs.filter(company=company)
        except Exception:
            return qs.none()

        # Filter by document_type
        doc_type = self.request.query_params.get('document_type')
        if doc_type:
            qs = qs.filter(document_type=doc_type)

        # Filter by expiring soon (days)
        expiring_days = self.request.query_params.get('expiring_days')
        if expiring_days:
            try:
                days = int(expiring_days)
                threshold = date.today() + timedelta(days=days)
                qs = qs.filter(
                    expiration_date__isnull=False,
                    expiration_date__lte=threshold,
                    expiration_date__gte=date.today()
                )
            except ValueError:
                pass

        return qs.order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentUploadSerializer
        return DocumentListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Assign company from user's profile when available
        company = None
        try:
            company = request.user.userprofile.company
        except Exception:
            company = None

        instance = serializer.save(company=company)
        process_document.delay(instance.pk)
        return Response(
            DocumentListSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Documents'])
class DocumentDetailView(RetrieveAPIView):
    """Retrieve a single document with chunks."""
    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        # enforce multi-tenant filtering when possible
        try:
            company = self.request.user.userprofile.company
            return qs.filter(company=company)
        except Exception:
            return qs.none()


@extend_schema(
    tags=['Documents'],
    summary="Documentos a vencer",
    description="Lista documentos que vencem nos próximos X dias.",
    parameters=[
        OpenApiParameter(
            name='days',
            type=int,
            default=30,
            description='Número de dias para verificar vencimento'
        )
    ],
    responses={
        200: OpenApiExample(
            'Documentos a vencer',
            value=[
                {
                    'id': 5,
                    'title': 'Contrato XYZ',
                    'document_type': 'contract',
                    'expiration_date': '2024-02-15'
                }
            ]
        )
    }
)
class ExpiringDocumentsView(APIView):
    """List documents expiring within specified days."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        threshold = date.today() + timedelta(days=days)

        try:
            company = request.user.userprofile.company
        except Exception:
            return Response([], status=status.HTTP_200_OK)

        docs = Document.objects.filter(
            company=company,
            expiration_date__isnull=False,
            expiration_date__lte=threshold,
            expiration_date__gte=date.today()
        ).order_by('expiration_date')

        serializer = DocumentListSerializer(docs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentStatsView(APIView):
    """Get document statistics for dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({}, status=status.HTTP_200_OK)

        qs = Document.objects.filter(company=company)

        today = date.today()
        expiring_7_days = qs.filter(
            expiration_date__isnull=False,
            expiration_date__lte=today + timedelta(days=7),
            expiration_date__gte=today
        ).count()

        expiring_30_days = qs.filter(
            expiration_date__isnull=False,
            expiration_date__lte=today + timedelta(days=30),
            expiration_date__gte=today
        ).count()

        expired = qs.filter(
            expiration_date__isnull=False,
            expiration_date__lt=today
        ).count()

        by_type = {}
        for doc_type, label in Document.DocumentType.choices:
            count = qs.filter(document_type=doc_type).count()
            if count > 0:
                by_type[doc_type] = {"label": label, "count": count}

        return Response({
            "total": qs.count(),
            "expiring_7_days": expiring_7_days,
            "expiring_30_days": expiring_30_days,
            "expired": expired,
            "by_type": by_type,
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Financial'],
    summary="Indicadores do documento",
    description="Retorna os indicadores financeiros extraídos de um documento específico.",
    responses={
        200: OpenApiExample(
            'Indicadores',
            value={
                'document_id': 1,
                'document_title': 'DRE 2024',
                'document_type': 'dre',
                'reference_date': '2024-12-31',
                'indicators': [
                    {'indicator_type': 'receita_liquida', 'indicator_display': 'Receita Líquida', 'value': '1234567.89'},
                    {'indicator_type': 'lucro_bruto', 'indicator_display': 'Lucro Bruto', 'value': '567890.00'},
                    {'indicator_type': 'ebitda', 'indicator_display': 'EBITDA', 'value': '345678.00'},
                    {'indicator_type': 'lucro_liquido', 'indicator_display': 'Lucro Líquido', 'value': '123456.00'},
                    {'indicator_type': 'margem_bruta', 'indicator_display': 'Margem Bruta (%)', 'value': '46.00'},
                    {'indicator_type': 'margem_liquida', 'indicator_display': 'Margem Líquida (%)', 'value': '10.00'}
                ]
            }
        )
    }
)
class DocumentIndicatorsView(APIView):
    """Get financial indicators for a specific document."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            document = Document.objects.get(pk=pk, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        indicators = document.financial_indicators.all().order_by('indicator_type')
        serializer = FinancialIndicatorSerializer(indicators, many=True)

        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "document_type": document.document_type,
            "reference_date": document.reference_date,
            "indicators": serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Financial'],
    summary="Extrair indicadores",
    description="Dispara extração de indicadores financeiros usando IA. A extração é assíncrona.",
    request=None,
    responses={
        202: OpenApiExample(
            'Extração iniciada',
            value={'message': 'Extraction started', 'document_id': 1}
        ),
        400: OpenApiExample(
            'Documento não processado',
            value={'error': 'Document must be fully processed first'}
        )
    }
)
class ExtractIndicatorsView(APIView):
    """Trigger financial indicator extraction for a document."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            document = Document.objects.get(pk=pk, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        if document.processing_status != Document.ProcessingStatus.COMPLETED:
            return Response(
                {"error": "Document must be fully processed first"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Trigger async extraction
        extract_and_save_indicators.delay(document.id)

        return Response({
            "message": "Extraction started",
            "document_id": document.id
        }, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    tags=['Financial'],
    summary="Dashboard financeiro",
    description="Retorna dados agregados financeiros para o dashboard da empresa.",
    responses={
        200: OpenApiExample(
            'Dashboard',
            value={
                'docs_with_financial_data': 15,
                'latest_indicators': {
                    'receita_liquida': {'value': 1234567.89, 'label': 'Receita Líquida', 'period': '2024-12'},
                    'lucro_liquido': {'value': 123456.00, 'label': 'Lucro Líquido', 'period': '2024-12'},
                    'ebitda': {'value': 234567.00, 'label': 'EBITDA', 'period': '2024-12'},
                    'margem_bruta': {'value': 45.50, 'label': 'Margem Bruta (%)', 'period': '2024-12'}
                }
            }
        )
    }
)
class FinancialDashboardView(APIView):
    """Get aggregated financial data for company dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum, Avg
        from collections import defaultdict

        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({}, status=status.HTTP_200_OK)

        # Get all financial indicators for company's documents
        indicators = FinancialIndicator.objects.filter(
            document__company=company
        ).select_related('document')

        # Group by indicator type
        by_type = defaultdict(list)
        for ind in indicators:
            by_type[ind.indicator_type].append({
                "value": float(ind.value),
                "period": str(ind.period) if ind.period else None,
                "document_id": ind.document_id,
                "document_title": ind.document.title
            })

        # Get latest values for key indicators
        latest = {}
        key_indicators = [
            'receita_liquida', 'lucro_bruto', 'ebitda', 'lucro_liquido',
            'margem_bruta', 'margem_liquida', 'margem_ebitda'
        ]
        for ind_type in key_indicators:
            ind = indicators.filter(indicator_type=ind_type).order_by('-period', '-extracted_at').first()
            if ind:
                latest[ind_type] = {
                    "value": float(ind.value),
                    "label": ind.get_indicator_type_display(),
                    "period": str(ind.period) if ind.period else None,
                    "document_title": ind.document.title
                }

        # Documents with financial data
        docs_with_data = Document.objects.filter(
            company=company,
            financial_indicators__isnull=False
        ).distinct().count()

        return Response({
            "docs_with_financial_data": docs_with_data,
            "latest_indicators": latest,
            "by_type": dict(by_type)
        }, status=status.HTTP_200_OK)


class IndicatorHistoryView(APIView):
    """Get historical data for a specific indicator type."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from collections import defaultdict

        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        indicator_type = request.query_params.get('type', 'receita_liquida')

        # Get all indicators of this type for company
        indicators = FinancialIndicator.objects.filter(
            document__company=company,
            indicator_type=indicator_type
        ).select_related('document').order_by('period', 'extracted_at')

        if not indicators.exists():
            return Response({
                "indicator_type": indicator_type,
                "data": []
            }, status=status.HTTP_200_OK)

        # Build time series data
        data = []
        for ind in indicators:
            period_label = ind.period.strftime('%b/%Y') if ind.period else 'N/A'
            data.append({
                "period": str(ind.period) if ind.period else None,
                "period_label": period_label,
                "value": float(ind.value),
                "document_id": ind.document_id,
                "document_title": ind.document.title or ind.document.file.name.split('/')[-1]
            })

        # Get indicator label
        label = indicator_type
        for choice in FinancialIndicator.IndicatorType.choices:
            if choice[0] == indicator_type:
                label = choice[1]
                break

        return Response({
            "indicator_type": indicator_type,
            "indicator_label": label,
            "data": data
        }, status=status.HTTP_200_OK)


class AllIndicatorsHistoryView(APIView):
    """Get historical data for all key indicators for charts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        key_indicators = [
            'receita_liquida', 'lucro_bruto', 'ebitda', 'lucro_liquido'
        ]

        result = {}

        for ind_type in key_indicators:
            indicators = FinancialIndicator.objects.filter(
                document__company=company,
                indicator_type=ind_type,
                period__isnull=False
            ).order_by('period')

            data = []
            for ind in indicators:
                data.append({
                    "period": str(ind.period),
                    "period_label": ind.period.strftime('%b/%y'),
                    "value": float(ind.value)
                })

            # Get label
            label = ind_type
            for choice in FinancialIndicator.IndicatorType.choices:
                if choice[0] == ind_type:
                    label = choice[1]
                    break

            result[ind_type] = {
                "label": label,
                "data": data
            }

        return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Financial'],
    summary="Comparar períodos",
    description="Compara indicadores financeiros entre dois documentos/períodos.",
    parameters=[
        OpenApiParameter(name='doc1', type=int, required=True, description='ID do primeiro documento'),
        OpenApiParameter(name='doc2', type=int, required=True, description='ID do segundo documento'),
    ],
    responses={
        200: OpenApiExample(
            'Comparação',
            value={
                'period_1': {'document_id': 1, 'document_title': 'DRE Jan/2024', 'reference_date': '2024-01-31'},
                'period_2': {'document_id': 2, 'document_title': 'DRE Fev/2024', 'reference_date': '2024-02-28'},
                'comparison': [
                    {
                        'indicator_type': 'receita_liquida',
                        'indicator_label': 'Receita Líquida',
                        'value_period_1': 1000000.00,
                        'value_period_2': 1100000.00,
                        'variation': 100000.00,
                        'variation_pct': 10.00
                    }
                ]
            }
        )
    }
)
class ComparePeriodsView(APIView):
    """Compare financial indicators between two periods/documents."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from decimal import Decimal

        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        doc1_id = request.query_params.get('doc1')
        doc2_id = request.query_params.get('doc2')

        if not doc1_id or not doc2_id:
            return Response(
                {"error": "Both doc1 and doc2 parameters are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get documents
        try:
            doc1 = Document.objects.get(pk=doc1_id, company=company)
            doc2 = Document.objects.get(pk=doc2_id, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get indicators for both documents
        indicators1 = {
            i.indicator_type: i.value
            for i in doc1.financial_indicators.all()
        }
        indicators2 = {
            i.indicator_type: i.value
            for i in doc2.financial_indicators.all()
        }

        # Build comparison
        all_types = set(indicators1.keys()) | set(indicators2.keys())
        comparison = []

        for ind_type in all_types:
            val1 = indicators1.get(ind_type)
            val2 = indicators2.get(ind_type)

            # Get label
            label = ind_type
            for choice in FinancialIndicator.IndicatorType.choices:
                if choice[0] == ind_type:
                    label = choice[1]
                    break

            # Calculate variation
            variation = None
            variation_pct = None
            if val1 is not None and val2 is not None and val1 != 0:
                variation = float(val2 - val1)
                variation_pct = float((val2 - val1) / abs(val1) * 100)

            comparison.append({
                "indicator_type": ind_type,
                "indicator_label": label,
                "value_period_1": float(val1) if val1 else None,
                "value_period_2": float(val2) if val2 else None,
                "variation": variation,
                "variation_pct": round(variation_pct, 2) if variation_pct else None
            })

        # Sort by indicator importance
        order = ['receita_bruta', 'receita_liquida', 'custo', 'lucro_bruto',
                 'despesas_op', 'ebitda', 'lucro_op', 'lucro_liquido',
                 'margem_bruta', 'margem_liquida', 'margem_ebitda',
                 'ativo_total', 'passivo_total', 'patrimonio_liq']
        comparison.sort(key=lambda x: order.index(x['indicator_type']) if x['indicator_type'] in order else 999)

        return Response({
            "period_1": {
                "document_id": doc1.id,
                "document_title": doc1.title or doc1.file.name.split('/')[-1],
                "reference_date": str(doc1.reference_date) if doc1.reference_date else None
            },
            "period_2": {
                "document_id": doc2.id,
                "document_title": doc2.title or doc2.file.name.split('/')[-1],
                "reference_date": str(doc2.reference_date) if doc2.reference_date else None
            },
            "comparison": comparison
        }, status=status.HTTP_200_OK)


class ComparableDocumentsView(APIView):
    """List documents available for comparison (DRE/Balance with indicators)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response([], status=status.HTTP_200_OK)

        docs = Document.objects.filter(
            company=company,
            document_type__in=[Document.DocumentType.DRE, Document.DocumentType.BALANCE],
            financial_indicators__isnull=False
        ).distinct().order_by('-reference_date', '-created_at')

        result = []
        for doc in docs:
            result.append({
                "id": doc.id,
                "title": doc.title or doc.file.name.split('/')[-1],
                "document_type": doc.document_type,
                "document_type_display": doc.get_document_type_display(),
                "reference_date": str(doc.reference_date) if doc.reference_date else None,
                "indicators_count": doc.financial_indicators.count()
            })

        return Response(result, status=status.HTTP_200_OK)


class DownloadReportView(APIView):
    """Download PDF financial report for a document."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            document = Document.objects.get(pk=pk, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        if not document.financial_indicators.exists():
            return Response(
                {"error": "No financial indicators available for this document"},
                status=status.HTTP_400_BAD_REQUEST
            )

        return generate_financial_report(document.id)


class DownloadComparisonReportView(APIView):
    """Download PDF comparison report between two documents."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        doc1_id = request.query_params.get('doc1')
        doc2_id = request.query_params.get('doc2')

        if not doc1_id or not doc2_id:
            return Response(
                {"error": "Both doc1 and doc2 parameters are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            doc1 = Document.objects.get(pk=doc1_id, company=company)
            doc2 = Document.objects.get(pk=doc2_id, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        return generate_comparison_report(doc1.id, doc2.id)


@extend_schema(
    tags=['Contracts'],
    summary="Cláusulas do contrato",
    description="Retorna as cláusulas extraídas de um contrato específico, organizadas por nível de risco.",
    responses={
        200: OpenApiExample(
            'Cláusulas',
            value={
                'document_id': 5,
                'document_title': 'Contrato de Prestação de Serviços',
                'clauses_count': 6,
                'high_risk_count': 1,
                'clauses': [
                    {
                        'id': 1,
                        'clause_type': 'multa',
                        'clause_display': 'Multa/Penalidade',
                        'title': 'Cláusula 8 - Multa por Rescisão',
                        'content': 'Em caso de rescisão antecipada...',
                        'summary': 'Multa de 20% sobre o valor restante',
                        'risk_level': 'high',
                        'extracted_value': '20%'
                    }
                ],
                'by_risk': {
                    'high': [{'clause_type': 'multa', 'risk_level': 'high'}],
                    'medium': [],
                    'low': []
                }
            }
        )
    }
)
class DocumentClausesView(APIView):
    """Get contract clauses for a specific document."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            document = Document.objects.get(pk=pk, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        clauses = document.clauses.all().order_by('clause_type')
        serializer = ContractClauseSerializer(clauses, many=True)

        # Group by risk level
        high_risk = [c for c in serializer.data if c['risk_level'] == 'high']
        medium_risk = [c for c in serializer.data if c['risk_level'] == 'medium']
        low_risk = [c for c in serializer.data if c['risk_level'] == 'low']

        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "clauses_count": clauses.count(),
            "high_risk_count": len(high_risk),
            "clauses": serializer.data,
            "by_risk": {
                "high": high_risk,
                "medium": medium_risk,
                "low": low_risk
            }
        }, status=status.HTTP_200_OK)


class ExtractClausesView(APIView):
    """Trigger clause extraction for a contract document."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        try:
            document = Document.objects.get(pk=pk, company=company)
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        if document.processing_status != Document.ProcessingStatus.COMPLETED:
            return Response(
                {"error": "Document must be fully processed first"},
                status=status.HTTP_400_BAD_REQUEST
            )

        extract_and_save_clauses.delay(document.id)

        return Response({
            "message": "Clause extraction started",
            "document_id": document.id
        }, status=status.HTTP_202_ACCEPTED)


class ContractsWithClausesView(APIView):
    """List contracts that have extracted clauses."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            company = request.user.userprofile.company
        except Exception:
            return Response([], status=status.HTTP_200_OK)

        docs = Document.objects.filter(
            company=company,
            document_type=Document.DocumentType.CONTRACT,
            clauses__isnull=False
        ).distinct().order_by('-created_at')

        result = []
        for doc in docs:
            high_risk = doc.clauses.filter(risk_level='high').count()
            result.append({
                "id": doc.id,
                "title": doc.title or doc.file.name.split('/')[-1],
                "clauses_count": doc.clauses.count(),
                "high_risk_count": high_risk,
                "expiration_date": str(doc.expiration_date) if doc.expiration_date else None
            })

        return Response(result, status=status.HTTP_200_OK)
