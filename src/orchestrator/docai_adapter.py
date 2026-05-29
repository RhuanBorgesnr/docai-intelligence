"""
DocAI Adapter - Integração com o sistema Document Intelligence existente.

Responsabilidades:
- Submeter documentos para análise
- Monitorar progresso
- Normalizar outputs
- Validar confiança
- Lidar com async polling
- Tratamento de timeouts
- Integração com workflow engine
"""

import logging
import asyncio
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Tipos de documentos que DocAI consegue analisar."""
    INVOICE = "nota_fiscal"
    BALANCE_SHEET = "balanco_patrimonial"
    BANK_STATEMENT = "extrato_bancario"
    TAX_RETURN = "declaracao_imposto"
    NEGATIVE_CERTIFICATE = "certidao_negativa"
    FINANCIAL_STATEMENT = "demonstrativo_financeiro"
    CUSTOM = "custom"


class AnalysisStatus(str, Enum):
    """Status da análise de um documento."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REQUIRES_REVIEW = "requires_review"


@dataclass
class DocumentAnalysisResult:
    """Resultado da análise de um documento."""
    
    analysis_id: str
    case_id: str
    document_type: DocumentType
    status: AnalysisStatus
    
    # Dados extraídos
    extracted_data: Dict[str, Any]
    entities: Dict[str, Any]
    relationships: Dict[str, Any]
    
    # Qualidade
    confidence: float  # 0.0 - 1.0
    field_confidences: Dict[str, float]  # {field: confidence}
    warnings: list  # Avisos durante análise
    
    # Metadados
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    processing_time_ms: float = 0.0
    needs_manual_review: bool = False
    manual_review_reason: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    @property
    def is_confident(self) -> bool:
        """Indica se o resultado é confiável."""
        return self.confidence >= 0.85 and not self.needs_manual_review
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "analysis_id": self.analysis_id,
            "case_id": self.case_id,
            "document_type": self.document_type.value,
            "status": self.status.value,
            "extracted_data": self.extracted_data,
            "entities": self.entities,
            "relationships": self.relationships,
            "confidence": self.confidence,
            "field_confidences": self.field_confidences,
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "processing_time_ms": self.processing_time_ms,
            "needs_manual_review": self.needs_manual_review,
            "manual_review_reason": self.manual_review_reason,
            "is_confident": self.is_confident
        }


class DocAIAdapterError(Exception):
    """Erros específicos do DocAI Adapter."""
    pass


class DocAIAdapter:
    """Adapter para integração com DocAI Document Intelligence."""
    
    # Em produção, isso seria consumido da API real
    # Por enquanto, simulamos com in-memory cache
    _analyses: Dict[str, DocumentAnalysisResult] = {}
    _base_url: str = "http://docai:8000/api"  # URL do DocAI
    _timeout: int = 300  # 5 minutos
    _polling_interval: int = 5  # Polling a cada 5 segundos
    
    @classmethod
    async def submit_document(
        cls,
        analysis_id: str,
        case_id: str,
        document_path: str,
        document_type: DocumentType,
        correlation_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentAnalysisResult:
        """
        Submete um documento para análise.
        
        Args:
            analysis_id: ID único da análise
            case_id: Case relacionado
            document_path: Path/URL do documento
            document_type: Tipo de documento
            correlation_id: Para rastreamento
            metadata: Metadata adicional
        
        Returns:
            DocumentAnalysisResult com status PENDING ou PROCESSING
        """
        
        logger.info(
            f"Submetendo documento para análise: "
            f"{document_type.value} (analysis_id={analysis_id}, case_id={case_id})"
        )
        
        try:
            # Em produção, isso seria uma chamada HTTP/REST ao DocAI
            # payload = {
            #     "document_path": document_path,
            #     "document_type": document_type.value,
            #     "correlation_id": correlation_id,
            #     "metadata": metadata or {}
            # }
            # response = requests.post(f"{cls._base_url}/documents/analyze", json=payload)
            # response.raise_for_status()
            
            # Mock para desenvolvimento
            result = DocumentAnalysisResult(
                analysis_id=analysis_id,
                case_id=case_id,
                document_type=document_type,
                status=AnalysisStatus.PROCESSING,
                extracted_data={},
                entities={},
                relationships={},
                confidence=0.0,
                field_confidences={},
                warnings=[]
            )
            
            cls._analyses[analysis_id] = result
            
            logger.info(f"Documento submetido com sucesso: {analysis_id}")
            
            # Emite evento
            await cls._emit_document_submitted_event(analysis_id, case_id)
            
            return result
        
        except Exception as e:
            logger.error(f"Erro ao submeter documento: {str(e)}", exc_info=True)
            raise DocAIAdapterError(f"Falha ao submeter documento: {str(e)}")
    
    @classmethod
    async def get_analysis_status(
        cls,
        analysis_id: str
    ) -> DocumentAnalysisResult:
        """
        Recupera status atual da análise.
        
        Args:
            analysis_id: ID da análise
        
        Returns:
            DocumentAnalysisResult atualizado
        """
        
        # Tenta recuperar do cache local primeiro
        if analysis_id in cls._analyses:
            return cls._analyses[analysis_id]
        
        try:
            # Em produção, faria polling na API do DocAI
            # response = requests.get(f"{cls._base_url}/analyses/{analysis_id}")
            # response.raise_for_status()
            # data = response.json()
            
            # Mock: simula completion após delay
            logger.info(f"Verificando status da análise: {analysis_id}")
            return cls._analyses.get(analysis_id)
        
        except Exception as e:
            logger.error(f"Erro ao verificar status: {str(e)}")
            return None
    
    @classmethod
    async def wait_for_completion(
        cls,
        analysis_id: str,
        timeout_seconds: int = 300
    ) -> Tuple[DocumentAnalysisResult, bool]:
        """
        Aguarda completação da análise com polling.
        
        Args:
            analysis_id: ID da análise
            timeout_seconds: Timeout em segundos
        
        Returns:
            (DocumentAnalysisResult, is_timeout)
        """
        
        logger.info(f"Aguardando análise: {analysis_id} "
                   f"(timeout={timeout_seconds}s)")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            result = await cls.get_analysis_status(analysis_id)
            
            if not result:
                raise DocAIAdapterError(f"Análise não encontrada: {analysis_id}")
            
            # Verifica se completou
            if result.status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                logger.info(f"Análise completada: {analysis_id} "
                          f"(status={result.status.value})")
                return result, False
            
            # Verifica timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(f"Análise expirou por timeout: {analysis_id}")
                result.status = AnalysisStatus.TIMEOUT
                return result, True
            
            # Polling
            await asyncio.sleep(cls._polling_interval)
    
    @classmethod
    async def poll_and_update(
        cls,
        analysis_id: str,
        poll_count: int = 0,
        max_polls: int = 60  # 5 minutos com polling de 5 segundos
    ) -> DocumentAnalysisResult:
        """
        Faz polling contínuo até sucesso ou falha.
        
        Args:
            analysis_id: ID da análise
            poll_count: Contador interno de tentativas
            max_polls: Máximo de tentativas antes de timeout
        
        Returns:
            DocumentAnalysisResult final
        """
        
        if poll_count >= max_polls:
            result = cls._analyses.get(analysis_id)
            if result:
                result.status = AnalysisStatus.TIMEOUT
            logger.warning(f"Polling expirou para análise: {analysis_id}")
            return result
        
        result = await cls.get_analysis_status(analysis_id)
        
        if result and result.status not in [
            AnalysisStatus.PROCESSING,
            AnalysisStatus.PENDING
        ]:
            # Completou
            return result
        
        # Continua polling
        await asyncio.sleep(cls._polling_interval)
        return await cls.poll_and_update(analysis_id, poll_count + 1, max_polls)
    
    @classmethod
    def normalize_output(
        cls,
        raw_result: DocumentAnalysisResult
    ) -> DocumentAnalysisResult:
        """
        Normaliza output do DocAI para formato padrão.
        
        Args:
            raw_result: Resultado bruto do DocAI
        
        Returns:
            Resultado normalizado
        """
        
        # Remove duplicatas de confiança
        if not raw_result.confidence:
            raw_result.confidence = cls._calculate_average_confidence(
                raw_result.field_confidences
            )
        
        # Valida campos obrigatórios foram extraídos
        for doc_type in DocumentType:
            if raw_result.document_type == doc_type:
                # Aqui verificaríamos campos obrigatórios por tipo
                pass
        
        # Detecta se precisa review manual
        cls._check_manual_review_needed(raw_result)
        
        logger.info(f"Output normalizado: {raw_result.analysis_id} "
                   f"(confidence={raw_result.confidence:.2f})")
        
        return raw_result
    
    @classmethod
    def _calculate_average_confidence(
        cls,
        field_confidences: Dict[str, float]
    ) -> float:
        """Calcula confiança média dos campos."""
        if not field_confidences:
            return 0.0
        
        total = sum(field_confidences.values())
        return total / len(field_confidences)
    
    @classmethod
    def _check_manual_review_needed(cls, result: DocumentAnalysisResult):
        """Verifica se análise precisa de review manual."""
        # Confiança muito baixa
        if result.confidence < 0.75:
            result.needs_manual_review = True
            result.manual_review_reason = "Confiança baixa na extração"
            return
        
        # Campos críticos com baixa confiança
        critical_fields = {
            # Compatível com extrações reais existentes e fixtures de teste.
            DocumentType.INVOICE: ["total", "issuer"],
            DocumentType.BALANCE_SHEET: ["total_assets", "total_liabilities"],
            DocumentType.BANK_STATEMENT: ["opening_balance", "closing_balance"],
        }
        
        critical = critical_fields.get(result.document_type, [])
        for field in critical:
            # Se o campo foi extraído mas não trouxe confiança por campo,
            # assumimos confiança herdada do documento para evitar falso positivo.
            field_present = field in (result.extracted_data or {}) or field in (result.entities or {})
            conf = result.field_confidences.get(field)
            if conf is None:
                conf = result.confidence if field_present else 0.0
            if conf < 0.80:
                result.needs_manual_review = True
                result.manual_review_reason = f"Confiança baixa no campo crítico: {field}"
                return
        
        # Warnings detectados
        if result.warnings:
            result.needs_manual_review = True
            result.manual_review_reason = f"Warnings detectados: {', '.join(result.warnings[:2])}"
    
    @classmethod
    async def process_document_end_to_end(
        cls,
        analysis_id: str,
        case_id: str,
        document_path: str,
        document_type: DocumentType,
        correlation_id: str
    ) -> DocumentAnalysisResult:
        """
        Fluxo completo: submit -> wait -> normalize.
        
        Args:
            analysis_id: ID da análise
            case_id: Case ID
            document_path: Path do documento
            document_type: Tipo de documento
            correlation_id: Correlation ID
        
        Returns:
            Resultado final normalizado
        """
        
        logger.info(f"Iniciando análise completa de documento: "
                   f"{analysis_id} ({document_type.value})")
        
        try:
            # Step 1: Submit
            result = await cls.submit_document(
                analysis_id=analysis_id,
                case_id=case_id,
                document_path=document_path,
                document_type=document_type,
                correlation_id=correlation_id
            )
            
            # Step 2: Wait for completion
            result, is_timeout = await cls.wait_for_completion(analysis_id)
            
            if is_timeout:
                await cls._emit_document_analysis_timeout(analysis_id, case_id)
                return result
            
            if result.status == AnalysisStatus.FAILED:
                await cls._emit_document_analysis_failed(analysis_id, case_id)
                return result
            
            # Step 3: Normalize
            result = cls.normalize_output(result)
            
            # Step 4: Emit completion event
            await cls._emit_document_analysis_completed(result)
            
            logger.info(f"Análise de documento completada: {analysis_id}")
            
            return result
        
        except Exception as e:
            logger.error(f"Erro no fluxo de análise: {str(e)}", exc_info=True)
            raise
    
    @classmethod
    async def _emit_document_submitted_event(
        cls,
        analysis_id: str,
        case_id: str
    ):
        """Emite evento de documento submetido."""
        event = {
            "event_type": "docai.document.submitted",
            "source": "docai_adapter",
            "payload": {
                "analysis_id": analysis_id,
                "case_id": case_id
            }
        }
        logger.info(f"Evento emitido: {event['event_type']}")
    
    @classmethod
    async def _emit_document_analysis_completed(
        cls,
        result: DocumentAnalysisResult
    ):
        """Emite evento de análise completada."""
        event = {
            "event_type": "docai.analysis.completed",
            "source": "docai_adapter",
            "payload": result.to_dict()
        }
        logger.info(f"Evento emitido: {event['event_type']}")
    
    @classmethod
    async def _emit_document_analysis_failed(
        cls,
        analysis_id: str,
        case_id: str
    ):
        """Emite evento de análise falhada."""
        event = {
            "event_type": "docai.analysis.failed",
            "source": "docai_adapter",
            "payload": {
                "analysis_id": analysis_id,
                "case_id": case_id
            }
        }
        logger.info(f"Evento emitido: {event['event_type']}")
    
    @classmethod
    async def _emit_document_analysis_timeout(
        cls,
        analysis_id: str,
        case_id: str
    ):
        """Emite evento de timeout."""
        event = {
            "event_type": "docai.analysis.timeout",
            "source": "docai_adapter",
            "payload": {
                "analysis_id": analysis_id,
                "case_id": case_id
            }
        }
        logger.info(f"Evento emitido: {event['event_type']}")
