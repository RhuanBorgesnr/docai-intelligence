from django.db import models
from pgvector.django import VectorField


class Document(models.Model):

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class DocumentType(models.TextChoices):
        CONTRACT = "contract", "Contrato"
        INVOICE = "invoice", "Nota Fiscal"
        BALANCE = "balance", "Balanço"
        DRE = "dre", "DRE"
        CERTIFICATE = "certificate", "Certidão"
        REPORT = "report", "Relatório"
        OTHER = "other", "Outro"

    file = models.FileField(upload_to="documents/")
    title = models.CharField(max_length=512, blank=True)
    extracted_text = models.TextField(blank=True, null=True)
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE, null=True
    )

    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.OTHER
    )
    reference_date = models.DateField(
        null=True, blank=True,
        help_text="Data de referência/competência do documento"
    )
    expiration_date = models.DateField(
        null=True, blank=True,
        help_text="Data de vencimento do documento"
    )

    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )

    total_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document {self.id} - {self.file.name}"


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks"
    )

    content = models.TextField()

    embedding = VectorField(dimensions=384)

    chunk_index = models.PositiveIntegerField()
    token_count = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document"]),
        ]
        ordering = ["chunk_index"]

    def __str__(self):
        return f"Chunk {self.chunk_index} (Doc {self.document_id})"


class FinancialIndicator(models.Model):
    """Stores financial indicators extracted from documents."""

    class IndicatorType(models.TextChoices):
        RECEITA_BRUTA = "receita_bruta", "Receita Bruta"
        RECEITA_LIQUIDA = "receita_liquida", "Receita Líquida"
        CUSTO = "custo", "Custo dos Produtos/Serviços"
        LUCRO_BRUTO = "lucro_bruto", "Lucro Bruto"
        DESPESAS_OPERACIONAIS = "despesas_op", "Despesas Operacionais"
        EBITDA = "ebitda", "EBITDA"
        LUCRO_OPERACIONAL = "lucro_op", "Lucro Operacional"
        LUCRO_LIQUIDO = "lucro_liquido", "Lucro Líquido"
        ATIVO_TOTAL = "ativo_total", "Ativo Total"
        PASSIVO_TOTAL = "passivo_total", "Passivo Total"
        PATRIMONIO_LIQUIDO = "patrimonio_liq", "Patrimônio Líquido"
        MARGEM_BRUTA = "margem_bruta", "Margem Bruta (%)"
        MARGEM_LIQUIDA = "margem_liquida", "Margem Líquida (%)"
        MARGEM_EBITDA = "margem_ebitda", "Margem EBITDA (%)"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="financial_indicators"
    )
    indicator_type = models.CharField(
        max_length=30,
        choices=IndicatorType.choices
    )
    value = models.DecimalField(max_digits=18, decimal_places=2)
    period = models.DateField(
        null=True, blank=True,
        help_text="Período de referência do indicador"
    )
    extracted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "indicator_type"]),
        ]
        unique_together = ["document", "indicator_type", "period"]

    def __str__(self):
        return f"{self.get_indicator_type_display()}: {self.value} (Doc {self.document_id})"


class ExpirationNotification(models.Model):
    """Tracks expiration notifications sent to avoid duplicates."""

    class NotificationType(models.TextChoices):
        DAYS_7 = "7_days", "7 dias antes"
        DAYS_3 = "3_days", "3 dias antes"
        DAYS_1 = "1_day", "1 dia antes"
        EXPIRED = "expired", "Vencido"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="expiration_notifications"
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices
    )
    sent_to = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["document", "notification_type", "sent_to"]

    def __str__(self):
        return f"Notification {self.notification_type} for Doc {self.document_id}"


class ContractClause(models.Model):
    """Stores clauses detected in contracts."""

    class ClauseType(models.TextChoices):
        MULTA = "multa", "Multa/Penalidade"
        REAJUSTE = "reajuste", "Reajuste/Correção"
        RESCISAO = "rescisao", "Rescisão"
        VIGENCIA = "vigencia", "Vigência/Prazo"
        RENOVACAO = "renovacao", "Renovação Automática"
        CONFIDENCIALIDADE = "confidencialidade", "Confidencialidade"
        GARANTIA = "garantia", "Garantia"
        PAGAMENTO = "pagamento", "Condições de Pagamento"
        RESPONSABILIDADE = "responsabilidade", "Responsabilidade/Obrigações"
        FORO = "foro", "Foro/Jurisdição"
        OUTRO = "outro", "Outra Cláusula Importante"

    class RiskLevel(models.TextChoices):
        LOW = "low", "Baixo"
        MEDIUM = "medium", "Médio"
        HIGH = "high", "Alto"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="clauses"
    )
    clause_type = models.CharField(
        max_length=30,
        choices=ClauseType.choices
    )
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Texto completo da cláusula")
    summary = models.TextField(blank=True, help_text="Resumo gerado pela IA")
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.MEDIUM
    )
    extracted_value = models.CharField(
        max_length=255, blank=True,
        help_text="Valor extraído (ex: 2% ao mês, 30 dias)"
    )
    extracted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "clause_type"]),
        ]

    def __str__(self):
        return f"{self.get_clause_type_display()}: {self.title[:50]} (Doc {self.document_id})"