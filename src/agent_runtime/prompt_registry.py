"""
Prompt Registry - Sistema versionado e centralizado de prompts para agentes.

Responsabilidades:
- Armazenar prompts versionados por agente
- Suportar templates dinâmicos com injeção de contexto
- Validar schemas de output esperados
- Manter políticas e constraints por agente
- Permitir rollback de versões
"""

from typing import Any, Dict, Optional
from enum import Enum
from dataclasses import dataclass, asdict
import json


class AgentType(str, Enum):
    """Tipos de agentes no sistema."""
    JARVIS = "jarvis"  # Orquestrador executivo
    INTAKE = "intake"  # Recebe leads e informa
    SDR = "sdr"  # Sales Development Rep - qualifica
    SALES = "sales"  # Closer - propõe
    DOCAI_OPERATOR = "docai_operator"  # Coordena com DocAI
    SUPPORT = "support"  # Suporte e churn prevention
    ANALYST = "analyst"  # Análise de dados


@dataclass
class OutputSchema:
    """Define o schema esperado da saída de um agente."""
    
    properties: Dict[str, Any]  # JSON schema properties
    required: list  # Campos obrigatórios
    type: str = "object"
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Converte para JSON schema válido."""
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required,
            "additionalProperties": False
        }
    
    def validate(self, output: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Valida output contra o schema."""
        # Verifica campos obrigatórios
        for required_field in self.required:
            if required_field not in output:
                return False, f"Campo obrigatório ausente: {required_field}"
        
        # Verifica propriedades conhecidas
        for key in output.keys():
            if key not in self.properties:
                return False, f"Propriedade desconhecida: {key}"
        
        return True, None


@dataclass
class PromptTemplate:
    """Template dinâmico com suporte a variáveis."""
    
    content: str
    variables: Dict[str, str]  # {nome_var: tipo}
    
    def render(self, context: Dict[str, Any]) -> str:
        """Renderiza template com contexto."""
        rendered = self.content
        
        for var_name in self.variables.keys():
            if var_name not in context:
                raise ValueError(f"Variável obrigatória ausente: {var_name}")
            
            value = context[var_name]
            rendered = rendered.replace(f"{{{{{var_name}}}}}", str(value))
        
        return rendered


class PromptPolicy:
    """Políticas e constraints de um agente."""
    
    def __init__(self):
        self.max_tokens: int = 1000
        self.temperature: float = 0.7
        self.top_p: float = 0.9
        self.frequency_penalty: float = 0.0
        self.presence_penalty: float = 0.0
        self.stop_sequences: list = []
        
        # Constraints
        self.requires_approval: bool = False
        self.approval_fields: list = []  # Quais campos precisam aprovação?
        self.allowed_tools: list = []  # Quais tools pode usar?
        self.timeout_seconds: int = 30
        self.max_retries: int = 3
        
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stop_sequences": self.stop_sequences,
            "requires_approval": self.requires_approval,
            "approval_fields": self.approval_fields,
            "allowed_tools": self.allowed_tools,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


class PromptRegistry:
    """Registry centralizado de prompts com versionamento."""
    
    # Em produção, isso seria persistido em DB
    # Por enquanto, usamos in-memory com fallback para JSON
    _prompts: Dict[AgentType, Dict[int, 'PromptVersion']] = {}
    _policies: Dict[AgentType, PromptPolicy] = {}
    _schemas: Dict[AgentType, OutputSchema] = {}
    
    @classmethod
    def register_prompt(
        cls,
        agent_type: AgentType,
        content: str,
        variables: Optional[Dict[str, str]] = None,
        version: int = 1,
        description: str = ""
    ) -> 'PromptVersion':
        """Registra um novo prompt para um agente."""
        
        if agent_type not in cls._prompts:
            cls._prompts[agent_type] = {}
        
        prompt = PromptVersion(
            agent_type=agent_type,
            content=content,
            variables=variables or {},
            version=version,
            description=description
        )
        
        cls._prompts[agent_type][version] = prompt
        return prompt
    
    @classmethod
    def register_policy(
        cls,
        agent_type: AgentType,
        policy: PromptPolicy
    ):
        """Registra política para um agente."""
        cls._policies[agent_type] = policy
    
    @classmethod
    def register_schema(
        cls,
        agent_type: AgentType,
        schema: OutputSchema
    ):
        """Registra schema esperado para outputs do agente."""
        cls._schemas[agent_type] = schema
    
    @classmethod
    def get_prompt(
        cls,
        agent_type: AgentType,
        version: Optional[int] = None
    ) -> Optional['PromptVersion']:
        """Recupera prompt mais recente ou versão específica."""
        
        if agent_type not in cls._prompts:
            return None
        
        prompts = cls._prompts[agent_type]
        if not prompts:
            return None
        
        if version is None:
            # Retorna versão mais alta
            version = max(prompts.keys())
        
        return prompts.get(version)
    
    @classmethod
    def get_policy(cls, agent_type: AgentType) -> Optional[PromptPolicy]:
        """Recupera política do agente."""
        return cls._policies.get(agent_type)
    
    @classmethod
    def get_schema(cls, agent_type: AgentType) -> Optional[OutputSchema]:
        """Recupera schema esperado para outputs."""
        return cls._schemas.get(agent_type)
    
    @classmethod
    def list_versions(cls, agent_type: AgentType) -> list:
        """Lista todas as versões de um agente."""
        if agent_type not in cls._prompts:
            return []
        return sorted(cls._prompts[agent_type].keys(), reverse=True)
    
    @classmethod
    def rollback_to_version(
        cls,
        agent_type: AgentType,
        version: int
    ) -> bool:
        """Rollback para versão anterior (marca como ativa)."""
        prompt = cls.get_prompt(agent_type, version)
        if not prompt:
            return False
        
        # Em implementação real, isso seria um flag no DB
        # Por enquanto, apenas retornamos o prompt
        return True
    
    @classmethod
    def export_to_json(cls) -> Dict[str, Any]:
        """Exporta todos os prompts para JSON (backup/version control)."""
        export = {}
        
        for agent_type, versions in cls._prompts.items():
            export[agent_type.value] = {}
            for version, prompt in versions.items():
                export[agent_type.value][str(version)] = {
                    "content": prompt.content,
                    "variables": prompt.variables,
                    "description": prompt.description,
                    "created_at": prompt.created_at.isoformat() if prompt.created_at else None
                }
        
        return export


@dataclass
class PromptVersion:
    """Uma versão específica de um prompt."""
    
    agent_type: AgentType
    content: str
    variables: Dict[str, str]
    version: int
    description: str
    created_at: Optional[Any] = None
    
    def render(self, context: Dict[str, Any]) -> str:
        """Renderiza o prompt com contexto."""
        template = PromptTemplate(self.content, self.variables)
        return template.render(context)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "agent_type": self.agent_type.value,
            "content": self.content,
            "variables": self.variables,
            "version": self.version,
            "description": self.description,
        }


# ============================================================================
# PROMPT REGISTRY PADRÃO - Prompts iniciais para cada agente
# ============================================================================

def initialize_default_prompts():
    """Inicializa os prompts padrão para cada agente."""
    
    # ========== JARVIS - Orquestrador Executivo ==========
    jarvis_policy = PromptPolicy()
    jarvis_policy.max_tokens = 2000
    jarvis_policy.temperature = 0.5  # Mais determinístico
    jarvis_policy.requires_approval = False
    jarvis_policy.allowed_tools = [
        "list_pending_approvals",
        "get_case_summary",
        "view_metrics",
        "send_notification"
    ]
    jarvis_policy.timeout_seconds = 60
    
    PromptRegistry.register_prompt(
        AgentType.JARVIS,
        content="""Você é Jarvis, o orquestrador executivo do sistema DocAI.

Sua responsabilidade é:
- Coordenar outros agentes
- Tomar decisões estratégicas
- Escalar bloqueios
- Gerar briefings diários

Contexto atual:
{{contexto}}

Métricas:
{{metricas}}

Próximas ações:
{{proximas_acoes}}

Tome a melhor decisão com base no contexto. Use tools quando necessário.
Sempre priorize compliance e aprovação humana para decisões críticas.""",
        variables={
            "contexto": "string",
            "metricas": "object",
            "proximas_acoes": "array"
        },
        version=1,
        description="System prompt para Jarvis - orquestrador executivo"
    )
    
    PromptRegistry.register_policy(AgentType.JARVIS, jarvis_policy)
    
    jarvis_schema = OutputSchema(
        properties={
            "decision": {"type": "string", "enum": ["approve", "reject", "delegate", "escalate"]},
            "reasoning": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {"type": "object"}
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        required=["decision", "reasoning", "actions", "confidence"]
    )
    PromptRegistry.register_schema(AgentType.JARVIS, jarvis_schema)
    
    # ========== INTAKE - Recebe e informa leads ==========
    intake_policy = PromptPolicy()
    intake_policy.max_tokens = 1500
    intake_policy.temperature = 0.7
    intake_policy.requires_approval = False
    intake_policy.allowed_tools = ["extract_info", "validate_email", "classify_lead"]
    intake_policy.timeout_seconds = 30
    
    PromptRegistry.register_prompt(
        AgentType.INTAKE,
        content="""Você é o agente de Intake - responsável por receber e processar leads.

Lead recebido:
{{lead_data}}

Sua tarefa:
1. Extrair informações principais
2. Classificar qualidade do lead (quente, morno, frio)
3. Identificar gaps de informação
4. Recomendar próximo passo

Sempre seja profissional e acolhedor.""",
        variables={
            "lead_data": "object"
        },
        version=1,
        description="System prompt para Intake - processamento de leads"
    )
    
    PromptRegistry.register_policy(AgentType.INTAKE, intake_policy)
    
    intake_schema = OutputSchema(
        properties={
            "lead_quality": {"type": "string", "enum": ["hot", "warm", "cold"]},
            "extracted_info": {"type": "object"},
            "missing_fields": {"type": "array", "items": {"type": "string"}},
            "next_step": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        required=["lead_quality", "extracted_info", "next_step", "confidence"]
    )
    PromptRegistry.register_schema(AgentType.INTAKE, intake_schema)
    
    # ========== SDR - Sales Development Rep ==========
    sdr_policy = PromptPolicy()
    sdr_policy.max_tokens = 1500
    sdr_policy.temperature = 0.8  # Mais criativo
    sdr_policy.requires_approval = False
    sdr_policy.allowed_tools = ["research_company", "draft_email", "check_availability"]
    sdr_policy.timeout_seconds = 45
    
    PromptRegistry.register_prompt(
        AgentType.SDR,
        content="""Você é um Sales Development Rep (SDR) especializado em qualificação de leads B2B.

Lead a qualificar:
{{lead_profile}}

Histórico de interações:
{{interaction_history}}

Sua tarefa:
1. Qualificar o lead (MQL -> SQL)
2. Identificar decision maker
3. Sugerir próxima ação (agendar demo/call)
4. Preparar contexto para Closer

Responda SEMPRE em JSON válido com esta estrutura:
{
  "qualified": true/false,
  "confidence": 0.0 a 1.0,
  "next_action": "descrição da próxima ação",
  "decision_maker": {"name": "...", "role": "..."},
  "meeting_scheduled": false,
  "reason": "justificativa da decisão"
}

Seja objetivo e baseado nos dados fornecidos.""",
        variables={
            "lead_profile": "object",
            "interaction_history": "array"
        },
        version=1,
        description="System prompt para SDR - qualificação de leads"
    )
    
    PromptRegistry.register_policy(AgentType.SDR, sdr_policy)
    
    sdr_schema = OutputSchema(
        properties={
            "qualified": {"type": "boolean"},
            "decision_maker": {"type": "object"},
            "next_action": {"type": "string"},
            "meeting_scheduled": {"type": "boolean"},
            "confidence": {"type": "number"}
        },
        required=["qualified", "next_action", "confidence"]
    )
    PromptRegistry.register_schema(AgentType.SDR, sdr_schema)
    
    # ========== SALES - Closer ==========
    sales_policy = PromptPolicy()
    sales_policy.max_tokens = 2000
    sales_policy.temperature = 0.8
    sales_policy.requires_approval = True  # Precisa de aprovação para descontos/modificações
    sales_policy.approval_fields = ["discount", "custom_terms", "special_conditions"]
    sales_policy.allowed_tools = ["get_pricing", "check_inventory", "generate_proposal"]
    sales_policy.timeout_seconds = 60
    
    PromptRegistry.register_prompt(
        AgentType.SALES,
        content="""Você é um Closer de vendas especializado em fechar deals.

Oportunidade:
{{opportunity}}

Análise de DocAI:
{{docai_analysis}}

Histórico de negociação:
{{negotiation_history}}

Sua tarefa:
1. Preparar proposta personalizada
2. Antecipar objeções
3. Negociar termos
4. Garantir fechamento

Foque em value, não em preço.""",
        variables={
            "opportunity": "object",
            "docai_analysis": "object",
            "negotiation_history": "array"
        },
        version=1,
        description="System prompt para Sales - fechamento de deals"
    )
    
    PromptRegistry.register_policy(AgentType.SALES, sales_policy)
    
    sales_schema = OutputSchema(
        properties={
            "proposal": {"type": "object"},
            "discount": {"type": "number", "minimum": 0, "maximum": 100},
            "custom_terms": {"type": "object"},
            "win_probability": {"type": "number", "minimum": 0, "maximum": 1},
            "next_steps": {"type": "array"}
        },
        required=["proposal", "win_probability"]
    )
    PromptRegistry.register_schema(AgentType.SALES, sales_schema)
    
    # ========== DOCAI OPERATOR ==========
    docai_policy = PromptPolicy()
    docai_policy.max_tokens = 2000
    docai_policy.temperature = 0.3  # Muito determinístico
    docai_policy.requires_approval = False
    docai_policy.allowed_tools = ["submit_to_docai", "parse_results", "validate_confidence"]
    docai_policy.timeout_seconds = 120  # DocAI pode ser lento
    
    PromptRegistry.register_prompt(
        AgentType.DOCAI_OPERATOR,
        content="""Você é o operador DocAI - coordena análise de documentos.

Documento a analisar:
{{document_info}}

Análises anteriores (se houver):
{{previous_analyses}}

Sua tarefa:
1. Submeter documento ao DocAI
2. Monitorar progresso
3. Normalizar output
4. Validar qualidade de análise

Sempre capture confiança e limitações.""",
        variables={
            "document_info": "object",
            "previous_analyses": "array"
        },
        version=1,
        description="System prompt para DocAI Operator - orquestração de análises"
    )
    
    PromptRegistry.register_policy(AgentType.DOCAI_OPERATOR, docai_policy)
    
    docai_schema = OutputSchema(
        properties={
            "analysis_status": {"type": "string", "enum": ["pending", "processing", "complete"]},
            "extracted_data": {"type": "object"},
            "confidence": {"type": "number"},
            "document_type": {"type": "string"},
            "needs_manual_review": {"type": "boolean"}
        },
        required=["analysis_status", "confidence"]
    )
    PromptRegistry.register_schema(AgentType.DOCAI_OPERATOR, docai_schema)

    # ========== ANALYST - Gerador de insights comerciais ==========
    analyst_policy = PromptPolicy()
    analyst_policy.max_tokens = 2500
    analyst_policy.temperature = 0.6
    analyst_policy.requires_approval = False
    analyst_policy.allowed_tools = ["semantic_search", "get_case_context"]
    analyst_policy.timeout_seconds = 90

    PromptRegistry.register_prompt(
        AgentType.ANALYST,
        content="""Você é o Analista Comercial do DocAI — transforma análises de documentos em insights acionáveis para vendedores.

Perfil do lead:
{{lead_profile}}

Análise do DocAI (dados extraídos do documento):
{{docai_analysis}}

Resumo do documento:
{{document_summary}}

Contexto adicional (RAG — documentos similares e precedentes):
{{rag_context}}

SUA TAREFA:
1. Gerar de 3 a 5 insights COMERCIAIS priorizados por impacto.
2. Para cada insight, classifique o tipo: "opportunity" (oportunidade de venda), "pain" (dor detectada), "risk" (risco que justifica o DocAI), "value" (valor percebido), "compliance" (questão regulatória).
3. Para cada insight, inclua:
   - title: título curto e direto
   - evidence: dado concreto do documento que sustenta o insight
   - action: próxima ação sugerida para o vendedor (não genérica)
   - score: 0-100 (impacto comercial estimado)
4. Gere um "summary" em português, com 3-5 frases, pronto para o vendedor usar em uma demo ou follow-up. O tom deve ser consultivo, não genérico.
5. Identifique "automations": lista de automações que o DocAI pode oferecer para este tipo de documento/empresa.

REGRAS:
- Nunca invente dados. Se não há evidência, diga "não identificado".
- Priorize dores reais e valor percebido sobre features.
- O vendedor precisa USAR este output diretamente. Seja específico.
- Responda SEMPRE em português brasileiro.""",
        variables={
            "lead_profile": "object",
            "docai_analysis": "object",
            "document_summary": "object",
            "rag_context": "string",
        },
        version=1,
        description="System prompt para Analyst - geração de insights comerciais a partir de análises DocAI"
    )

    PromptRegistry.register_policy(AgentType.ANALYST, analyst_policy)

    analyst_schema = OutputSchema(
        properties={
            "insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["opportunity", "pain", "risk", "value", "compliance"]},
                        "title": {"type": "string"},
                        "evidence": {"type": "string"},
                        "action": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 100},
                    },
                },
            },
            "summary": {"type": "string"},
            "automations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        required=["insights", "summary", "confidence"]
    )
    PromptRegistry.register_schema(AgentType.ANALYST, analyst_schema)


# Inicializa os prompts padrão ao importar
initialize_default_prompts()
