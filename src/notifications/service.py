"""
Notification Service - Sistema multi-canal de notificações.

Responsabilidades:
- Enviar notificações por email
- Logs estruturados
- Webhooks
- Preparado para WhatsApp/Telegram
- Retry com fallback
- Rastreamento de status
- Templates dinâmicos
"""

import logging
import asyncio
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Canais de notificação disponíveis."""
    EMAIL = "email"
    LOG = "log"
    WEBHOOK = "webhook"
    WHATSAPP = "whatsapp"  # Coming Sprint 2
    TELEGRAM = "telegram"  # Coming Sprint 2
    DASHBOARD = "dashboard"  # Coming Sprint 3


class NotificationStatus(str, Enum):
    """Status de uma notificação."""
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    FAILED_FALLBACK = "failed_fallback"
    RETRY = "retry"


@dataclass
class NotificationTemplate:
    """Template de notificação."""
    
    subject: str
    body: str
    variables: Dict[str, str]  # {var_name: tipo}
    
    def render(self, context: Dict[str, Any]) -> tuple[str, str]:
        """Renderiza subject e body com contexto."""
        subject = self.subject
        body = self.body
        
        for var_name, value in context.items():
            placeholder = "{{" + var_name + "}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))
        
        return subject, body


@dataclass
class Notification:
    """Uma notificação a ser enviada."""
    
    notification_id: str
    case_id: str
    channel: NotificationChannel
    recipient: str  # email, phone, webhook_url, etc
    subject: str
    message: str
    
    # Metadados
    priority: str = "normal"  # critical, high, normal, low
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    
    # Status
    status: NotificationStatus = NotificationStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    
    # Histórico
    attempts: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        
        if self.attempts is None:
            self.attempts = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "notification_id": self.notification_id,
            "case_id": self.case_id,
            "channel": self.channel.value,
            "recipient": self.recipient,
            "subject": self.subject,
            "message": self.message,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error": self.error,
            "attempts": self.attempts
        }


class NotificationService:
    """Serviço de notificações multi-canal."""
    
    # Configuração
    _notifications: Dict[str, Notification] = {}
    _templates: Dict[str, NotificationTemplate] = {}
    
    # SMTP Config (configurar com env vars em produção)
    _smtp_server: str = "smtp.gmail.com"
    _smtp_port: int = 587
    _smtp_user: str = "noreply@company.com"
    _smtp_password: str = "***"  # Usar env var
    
    # Webhooks
    _webhook_timeout: int = 10
    
    @classmethod
    def register_template(
        cls,
        template_name: str,
        template: NotificationTemplate
    ):
        """Registra um template de notificação."""
        cls._templates[template_name] = template
        logger.info(f"Template registrado: {template_name}")
    
    @classmethod
    def get_template(cls, template_name: str) -> Optional[NotificationTemplate]:
        """Recupera um template."""
        return cls._templates.get(template_name)
    
    @classmethod
    async def send_notification(
        cls,
        notification_id: str,
        case_id: str,
        channel: NotificationChannel,
        recipient: str,
        template_name: Optional[str] = None,
        subject: str = "",
        message: str = "",
        context: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> Notification:
        """
        Cria e envia uma notificação.
        
        Args:
            notification_id: ID único
            case_id: Case relacionado
            channel: Canal de envio
            recipient: Destinatário (email, phone, etc)
            template_name: Nome do template (alternativa)
            subject: Subject direto (se sem template)
            message: Mensagem direta (se sem template)
            context: Contexto para renderizar template
            priority: Prioridade
        
        Returns:
            Notification enviado
        """
        
        logger.info(
            f"Enviando notificação: {notification_id} "
            f"(channel={channel.value}, recipient={recipient})"
        )
        
        # Renderiza template se fornecido
        if template_name:
            template = cls.get_template(template_name)
            if template and context:
                subject, message = template.render(context)
            else:
                logger.warning(f"Template não encontrado: {template_name}")
        
        # Cria notification
        notification = Notification(
            notification_id=notification_id,
            case_id=case_id,
            channel=channel,
            recipient=recipient,
            subject=subject,
            message=message,
            priority=priority
        )
        
        cls._notifications[notification_id] = notification
        
        # Tenta enviar
        for attempt in range(notification.max_retries):
            try:
                notification.status = NotificationStatus.SENDING
                notification.retry_count = attempt
                
                success = await cls._send_by_channel(
                    notification=notification,
                    attempt=attempt
                )
                
                if success:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.utcnow()
                    logger.info(f"Notificação enviada: {notification_id}")
                    await cls._emit_notification_sent_event(notification)
                    return notification
                
                elif attempt < notification.max_retries - 1:
                    # Retry
                    notification.status = NotificationStatus.RETRY
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Erro no envio, retrying em {wait_time}s: {notification_id}"
                    )
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                notification.error = str(e)
                logger.error(
                    f"Erro ao enviar notificação: {str(e)}", exc_info=True
                )
        
        # Esgotou tentativas
        notification.status = NotificationStatus.FAILED
        logger.error(f"Falha final ao enviar notificação: {notification_id}")
        await cls._emit_notification_failed_event(notification)
        
        return notification
    
    @classmethod
    async def _send_by_channel(
        cls,
        notification: Notification,
        attempt: int
    ) -> bool:
        """Envia por canal específico."""
        
        try:
            if notification.channel == NotificationChannel.EMAIL:
                return await cls._send_email(notification)
            
            elif notification.channel == NotificationChannel.LOG:
                return await cls._send_log(notification)
            
            elif notification.channel == NotificationChannel.WEBHOOK:
                return await cls._send_webhook(notification)
            
            elif notification.channel == NotificationChannel.WHATSAPP:
                # Placeholder para Sprint 2
                logger.warning("WhatsApp ainda não implementado")
                return False
            
            elif notification.channel == NotificationChannel.TELEGRAM:
                # Placeholder para Sprint 2
                logger.warning("Telegram ainda não implementado")
                return False
            
            elif notification.channel == NotificationChannel.DASHBOARD:
                # Armazena para exibição no dashboard
                return await cls._store_for_dashboard(notification)
            
            else:
                logger.error(f"Canal desconhecido: {notification.channel.value}")
                return False
        
        except Exception as e:
            logger.error(f"Erro no envio por {notification.channel.value}: {str(e)}")
            notification.error = str(e)
            
            # Tenta fallback
            return await cls._try_fallback(notification, attempt)
    
    @classmethod
    async def _send_email(cls, notification: Notification) -> bool:
        """Envia notificação por email."""
        
        try:
            # Cria mensagem
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notification.subject
            msg["From"] = cls._smtp_user
            msg["To"] = notification.recipient
            
            # Body em HTML
            html_body = f"""
            <html>
              <body>
                <h2>{notification.subject}</h2>
                <p>{notification.message}</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                  Case ID: {notification.case_id}<br>
                  Notification ID: {notification.notification_id}
                </p>
              </body>
            </html>
            """
            
            msg.attach(MIMEText(html_body, "html"))
            
            # Mock: em produção, enviaria via SMTP
            logger.info(f"Email enviado (mock): {notification.recipient}")
            logger.debug(f"Subject: {notification.subject}")
            logger.debug(f"Message: {notification.message[:100]}...")
            
            # Simulação de envio bem-sucedido
            return True
        
        except Exception as e:
            logger.error(f"Erro ao enviar email: {str(e)}")
            return False
    
    @classmethod
    async def _send_log(cls, notification: Notification) -> bool:
        """Envia como log estruturado."""
        
        try:
            log_entry = {
                "notification_id": notification.notification_id,
                "case_id": notification.case_id,
                "channel": notification.channel.value,
                "recipient": notification.recipient,
                "subject": notification.subject,
                "message": notification.message,
                "priority": notification.priority,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Log estruturado
            logger.info(f"Notificação: {json.dumps(log_entry)}")
            
            return True
        
        except Exception as e:
            logger.error(f"Erro ao registrar log: {str(e)}")
            return False
    
    @classmethod
    async def _send_webhook(cls, notification: Notification) -> bool:
        """Envia para webhook."""
        
        try:
            webhook_url = notification.recipient  # URL do webhook
            
            payload = notification.to_dict()
            
            # Mock: em produção, faria POST HTTP
            logger.info(f"Webhook enviado (mock): {webhook_url}")
            logger.debug(f"Payload: {json.dumps(payload, default=str)}")
            
            # Simula envio bem-sucedido
            return True
        
        except Exception as e:
            logger.error(f"Erro ao enviar webhook: {str(e)}")
            return False
    
    @classmethod
    async def _store_for_dashboard(cls, notification: Notification) -> bool:
        """Armazena notificação para exibição no dashboard."""
        
        try:
            # Em produção, seria persistido em DB ou cache
            logger.info(f"Notificação armazenada para dashboard: {notification.notification_id}")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao armazenar para dashboard: {str(e)}")
            return False
    
    @classmethod
    async def _try_fallback(
        cls,
        notification: Notification,
        attempt: int
    ) -> bool:
        """Tenta canal de fallback quando falha."""
        
        fallback_channel = None
        
        # Estratégia de fallback
        if notification.channel == NotificationChannel.EMAIL:
            fallback_channel = NotificationChannel.LOG
        elif notification.channel == NotificationChannel.WEBHOOK:
            fallback_channel = NotificationChannel.LOG
        else:
            return False  # Sem fallback
        
        logger.warning(
            f"Tentando fallback para {fallback_channel.value} "
            f"(original: {notification.channel.value})"
        )
        
        # Muda canal e tenta
        original_channel = notification.channel
        notification.channel = fallback_channel
        
        try:
            success = await cls._send_by_channel(notification, attempt)
            
            if success:
                notification.status = NotificationStatus.FAILED_FALLBACK
                logger.info(f"Envio por fallback bem-sucedido: {notification.notification_id}")
            else:
                notification.channel = original_channel
            
            return success
        
        except Exception as e:
            notification.channel = original_channel
            logger.error(f"Fallback também falhou: {str(e)}")
            return False
    
    @classmethod
    def get_notification(cls, notification_id: str) -> Optional[Notification]:
        """Recupera notificação por ID."""
        return cls._notifications.get(notification_id)
    
    @classmethod
    def list_notifications(
        cls,
        case_id: Optional[str] = None,
        channel: Optional[NotificationChannel] = None,
        status: Optional[NotificationStatus] = None
    ) -> List[Notification]:
        """Lista notificações com filtros."""
        
        notifications = list(cls._notifications.values())
        
        if case_id:
            notifications = [n for n in notifications if n.case_id == case_id]
        
        if channel:
            notifications = [n for n in notifications if n.channel == channel]
        
        if status:
            notifications = [n for n in notifications if n.status == status]
        
        return sorted(notifications, key=lambda n: n.created_at, reverse=True)
    
    @classmethod
    async def _emit_notification_sent_event(cls, notification: Notification):
        """Emite evento de notificação enviada."""
        event = {
            "event_type": "notification.sent",
            "source": "notification_service",
            "payload": notification.to_dict()
        }
        logger.info(f"Evento emitido: {event['event_type']}")
    
    @classmethod
    async def _emit_notification_failed_event(cls, notification: Notification):
        """Emite evento de notificação falhada."""
        event = {
            "event_type": "notification.failed",
            "source": "notification_service",
            "payload": notification.to_dict()
        }
        logger.warning(f"Evento emitido: {event['event_type']}")


# =============================================================================
# TEMPLATES PADRÃO
# =============================================================================

def initialize_notification_templates():
    """Inicializa templates padrão de notificação."""
    
    # Template: Aprovação solicitada
    approval_requested = NotificationTemplate(
        subject="Aprovação Solicitada - {{case_id}}",
        body="""
Olá,

Uma aprovação foi solicitada para o case {{case_id}}.

Ação: {{action}}
Agente: {{agent_name}}
Deadline: {{deadline}}

Campos a aprovar:
{{fields}}

Por favor, revise e tome uma decisão.

Link: {{approval_link}}

Obrigado,
Sistema de Orquestração
        """,
        variables={
            "case_id": "string",
            "action": "string",
            "agent_name": "string",
            "deadline": "string",
            "fields": "string",
            "approval_link": "string"
        }
    )
    NotificationService.register_template("approval_requested", approval_requested)
    
    # Template: Proposta gerada
    proposal_generated = NotificationTemplate(
        subject="Proposta Gerada - {{company_name}}",
        body="""
Olá {{sales_rep_name}},

Uma proposta foi gerada com sucesso para {{company_name}}.

Case: {{case_id}}
Valor: {{proposal_value}}
Prazo Válidade: {{validity_date}}

Próximos passos:
1. Revisar proposta
2. Enviar para cliente
3. Agendar follow-up

Link da Proposta: {{proposal_link}}

Boa sorte!
Jarvis
        """,
        variables={
            "sales_rep_name": "string",
            "company_name": "string",
            "case_id": "string",
            "proposal_value": "string",
            "validity_date": "string",
            "proposal_link": "string"
        }
    )
    NotificationService.register_template("proposal_generated", proposal_generated)
    
    # Template: Análise completada
    analysis_completed = NotificationTemplate(
        subject="Análise Completada - {{document_type}}",
        body="""
Análise de documento completada!

Tipo: {{document_type}}
Case: {{case_id}}
Confiança: {{confidence}}%
Status: {{status}}

{{analysis_summary}}

Próximos passos: {{next_steps}}
        """,
        variables={
            "document_type": "string",
            "case_id": "string",
            "confidence": "string",
            "status": "string",
            "analysis_summary": "string",
            "next_steps": "string"
        }
    )
    NotificationService.register_template("analysis_completed", analysis_completed)


# Inicializa templates padrão
initialize_notification_templates()
