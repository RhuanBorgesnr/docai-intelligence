"""
PDF Report generation service for financial documents.
"""
import io
import logging
from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from documents.models import Document, FinancialIndicator

logger = logging.getLogger(__name__)


def format_currency(value):
    """Format value as Brazilian currency."""
    if value is None:
        return "-"
    try:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(value)


def format_percent(value):
    """Format value as percentage."""
    if value is None:
        return "-"
    try:
        return f"{value:.2f}%"
    except (ValueError, TypeError):
        return str(value)


def get_variation_text(current, previous):
    """Calculate and format variation between two values."""
    if current is None or previous is None or previous == 0:
        return "-"
    variation = ((current - previous) / abs(previous)) * 100
    sign = "+" if variation > 0 else ""
    return f"{sign}{variation:.1f}%"


class FinancialReportGenerator:
    """Generates PDF financial reports from document indicators."""

    def __init__(self, document: Document, company_name: str = ""):
        self.document = document
        self.company_name = company_name
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Configure custom styles for the report."""
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1e40af'),
            spaceBefore=15,
            spaceAfter=10
        ))
        self.styles.add(ParagraphStyle(
            name='SubTitle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=30
        ))
        self.styles.add(ParagraphStyle(
            name='IndicatorValue',
            parent=self.styles['Normal'],
            fontSize=18,
            textColor=colors.HexColor('#059669'),
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        ))

    def _get_indicators_by_category(self):
        """Group indicators by category."""
        indicators = self.document.financial_indicators.all()

        income_types = ['receita_bruta', 'receita_liquida', 'custo', 'lucro_bruto',
                        'despesas_op', 'ebitda', 'lucro_op', 'lucro_liquido']
        balance_types = ['ativo_total', 'passivo_total', 'patrimonio_liq']
        margin_types = ['margem_bruta', 'margem_liquida', 'margem_ebitda']

        income = []
        balance = []
        margins = []

        for ind in indicators:
            item = {
                'type': ind.indicator_type,
                'label': ind.get_indicator_type_display(),
                'value': ind.value
            }
            if ind.indicator_type in income_types:
                income.append(item)
            elif ind.indicator_type in balance_types:
                balance.append(item)
            elif ind.indicator_type in margin_types:
                margins.append(item)

        # Sort by predefined order
        def sort_key(item, order):
            try:
                return order.index(item['type'])
            except ValueError:
                return 999

        income.sort(key=lambda x: sort_key(x, income_types))
        balance.sort(key=lambda x: sort_key(x, balance_types))
        margins.sort(key=lambda x: sort_key(x, margin_types))

        return income, balance, margins

    def _build_header(self, elements):
        """Build report header."""
        elements.append(Paragraph("Relatório Financeiro", self.styles['ReportTitle']))

        doc_title = self.document.title or self.document.file.name.split('/')[-1]
        ref_date = self.document.reference_date.strftime('%d/%m/%Y') if self.document.reference_date else 'N/A'

        subtitle = f"{doc_title}<br/>"
        if self.company_name:
            subtitle += f"Empresa: {self.company_name}<br/>"
        subtitle += f"Período de Referência: {ref_date}"

        elements.append(Paragraph(subtitle, self.styles['SubTitle']))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
        elements.append(Spacer(1, 20))

    def _build_margins_summary(self, elements, margins):
        """Build margins summary cards."""
        if not margins:
            return

        elements.append(Paragraph("Indicadores de Margem", self.styles['SectionTitle']))

        data = [
            [Paragraph(m['label'], self.styles['Normal']) for m in margins],
            [Paragraph(format_percent(m['value']), self.styles['IndicatorValue']) for m in margins]
        ]

        table = Table(data, colWidths=[5*cm] * len(margins))
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.white),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

    def _build_indicators_table(self, elements, indicators, title):
        """Build a table of indicators."""
        if not indicators:
            return

        elements.append(Paragraph(title, self.styles['SectionTitle']))

        data = [['Indicador', 'Valor']]
        for ind in indicators:
            if 'margem' in ind['type']:
                value = format_percent(ind['value'])
            else:
                value = format_currency(ind['value'])
            data.append([ind['label'], value])

        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            # Grid
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

    def _build_footer(self, elements):
        """Build report footer."""
        elements.append(Spacer(1, 30))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
        elements.append(Spacer(1, 10))

        footer_text = f"Relatório gerado automaticamente em {date.today().strftime('%d/%m/%Y')}<br/>"
        footer_text += "Plataforma Inteligência de Documentos"
        elements.append(Paragraph(footer_text, self.styles['Footer']))

    def generate(self) -> bytes:
        """Generate the PDF report and return as bytes."""
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        elements = []

        # Build report sections
        self._build_header(elements)

        income, balance, margins = self._get_indicators_by_category()

        # Margins summary
        self._build_margins_summary(elements, margins)

        # Income statement
        self._build_indicators_table(elements, income, "Demonstração de Resultado")

        # Balance sheet
        self._build_indicators_table(elements, balance, "Balanço Patrimonial")

        # Footer
        self._build_footer(elements)

        doc.build(elements)

        pdf = buffer.getvalue()
        buffer.close()

        return pdf


def generate_financial_report(document_id: int) -> HttpResponse:
    """
    Generate a PDF financial report for a document.

    Args:
        document_id: The document ID to generate report for.

    Returns:
        HttpResponse with PDF content.
    """
    document = Document.objects.select_related('company').get(pk=document_id)
    company_name = document.company.name if document.company else ""

    generator = FinancialReportGenerator(document, company_name)
    pdf_bytes = generator.generate()

    # Build filename
    doc_title = document.title or f"documento_{document_id}"
    safe_title = "".join(c for c in doc_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filename = f"relatorio_{safe_title}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


def generate_comparison_report(doc1_id: int, doc2_id: int) -> HttpResponse:
    """
    Generate a PDF comparison report between two documents.
    """
    doc1 = Document.objects.select_related('company').get(pk=doc1_id)
    doc2 = Document.objects.select_related('company').get(pk=doc2_id)
    company_name = doc1.company.name if doc1.company else ""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Title', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#1e40af'), spaceAfter=20, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='SubTitle', parent=styles['Normal'], fontSize=12, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=30))

    elements = []

    # Header
    elements.append(Paragraph("Comparativo Financeiro", styles['Title']))

    period1 = doc1.reference_date.strftime('%d/%m/%Y') if doc1.reference_date else doc1.title
    period2 = doc2.reference_date.strftime('%d/%m/%Y') if doc2.reference_date else doc2.title
    elements.append(Paragraph(f"{period1} vs {period2}<br/>{company_name}", styles['SubTitle']))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
    elements.append(Spacer(1, 20))

    # Get indicators
    ind1 = {i.indicator_type: i.value for i in doc1.financial_indicators.all()}
    ind2 = {i.indicator_type: i.value for i in doc2.financial_indicators.all()}

    all_types = set(ind1.keys()) | set(ind2.keys())

    # Build comparison table
    data = [['Indicador', period1, period2, 'Variação']]

    order = ['receita_liquida', 'lucro_bruto', 'ebitda', 'lucro_liquido', 'margem_bruta', 'margem_liquida', 'margem_ebitda']

    for ind_type in order:
        if ind_type not in all_types:
            continue

        label = ind_type
        for choice in FinancialIndicator.IndicatorType.choices:
            if choice[0] == ind_type:
                label = choice[1]
                break

        val1 = ind1.get(ind_type)
        val2 = ind2.get(ind_type)

        is_percent = 'margem' in ind_type
        fmt = format_percent if is_percent else format_currency

        variation = get_variation_text(val2, val1)

        data.append([label, fmt(val1), fmt(val2), variation])

    table = Table(data, colWidths=[6*cm, 4*cm, 4*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)

    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(f"Gerado em {date.today().strftime('%d/%m/%Y')} | Plataforma Inteligência",
                              ParagraphStyle(name='Footer', fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="comparativo_{doc1_id}_vs_{doc2_id}.pdf"'
    return response
