# DocAI Intelligence — Contexto Completo do Projeto

## O Que É

**DocAI Intelligence** é uma plataforma SaaS de inteligência documental com IA que transforma documentos corporativos em decisões acionáveis. O produto combina NLP, ML e IA generativa para automatizar análise de documentos (balanços, certidões, notas fiscais, contratos).

**Theo/OpenClaw (Jarvis)** é a camada operacional INTERNA da empresa que vende e opera o DocAI. Os agentes trabalham PARA a empresa (pipeline comercial, operações, CS), NÃO são assistentes do usuário final do SaaS.

## Stack Técnica

- **Backend:** Django 6.0 + Django REST Framework + drf-spectacular (OpenAPI)
- **Async/Workers:** Celery + Redis 7 (broker) + Celery Beat (scheduler)
- **Banco:** PostgreSQL 16 + pgvector (embeddings 384 dims, all-MiniLM-L6-v2)
- **Frontend:** React 18 + Vite 5 + Tailwind CSS 3.4 + React Router 6
- **3D/Viz:** Three.js + @react-three/fiber + @react-three/drei + Recharts
- **Auth:** JWT (SimpleJWT)
- **LLM:** Groq (default, free - Llama 3 70B) / OpenAI / Anthropic (configurável via `LLM_PROVIDER`)
- **Deploy:** Docker Compose (dev) + Docker Compose prod + Vercel (frontend)
- **Testes:** pytest + pytest-django + pytest-asyncio

## Estrutura do Projeto

```
src/                          # Backend Django
├── core/                     # Settings, URLs, Celery config, tenants, governance
├── orchestrator/             # Workflow engine, state machine, events, dashboard, Jarvis agent
├── agent_runtime/            # Agent runner, prompt registry, inter-agent bus, charter, routines, metrics
├── approvals/                # Human-in-the-loop approval gateway
├── notifications/            # Multi-channel (email, WhatsApp, webhook) + circuit breaker
├── memory/                   # Context snapshots
├── audit/                    # Append-only audit trail
├── commercial/               # Pipeline comercial (leads, scoring, opportunities, follow-ups, webhooks)
├── search/                   # Semantic search + RAG (pgvector embeddings)
├── ai/                       # LLM integration, embeddings, RAG engine
├── documents/                # Document Intelligence core (extração/análise)
├── companies/                # Multi-tenant companies
├── accounts/                 # Auth, users
├── tests/                    # Integration tests (181+ passando)
│   └── integration/
│       ├── test_orchestrator_sprint1.py
│       ├── test_sprint2_integration.py
│       ├── test_sprint3_*.py
│       └── test_sprint4_*.py
└── manage.py

frontend/                     # React SPA
├── src/
│   ├── pages/                # Operations, JarvisPanel, Pipeline, Leads, OpsAgentTeam
│   ├── components/           # operations/ (3D agent topology), UI components
│   ├── hooks/                # useAgentStatus, useJarvis
│   ├── services/             # API clients (commercial.js, etc.)
│   └── App.jsx               # Router + Nav
└── package.json

docker/                       # Docker configs
docker-compose.yml            # Dev environment (postgres, redis, web, celery, beat)
```

## Arquitetura

```
Frontend (React) → Django DRF API → PostgreSQL 16 + pgvector
                                  → Redis 7 (Celery broker)
                                  → Celery Workers (async tasks)
                                  → Celery Beat (scheduled routines)
                                  → LLM APIs (Groq/OpenAI/Anthropic)
```

### Padrões Centrais

1. **Event-driven state machine** — Cases transitam estados via eventos idempotentes
2. **Approval-first** — Ações sensíveis requerem aprovação humana antes de executar
3. **Durable events** — Outbox/Inbox pattern para garantia de entrega
4. **Row-level locking** — `select_for_update` para evitar race conditions
5. **Append-only audit** — Trilha de auditoria nunca modificada/deletada
6. **Circuit breaker** — Providers degradados são isolados automaticamente
7. **Idempotency keys** — Todas as ingestões são seguras para retry

## State Machine (Pipeline Comercial)

```
NEW → TRIAGE → QUALIFIED → WAITING_DOC_SAMPLE → DOC_SENT_TO_DOCAI → 
ANALYSIS_READY → PROPOSAL_DRAFT_READY → WAITING_HUMAN_APPROVAL → 
APPROVED_TO_SEND → FOLLOWUP_SCHEDULED → WON/LOST
```

## Agentes do Sistema (Digital Team)

| Agente | Emoji | Papel |
|--------|-------|-------|
| Jarvis | 🧠 | Executivo — orquestra, prioriza, briefing diário, escalation |
| SDR | 🎯 | Pré-vendas — qualifica leads, ICP scoring, escala quentes |
| Sales | 💼 | Closer — follow-ups, propostas, demos, pipeline |
| DocAI Operator | 📄 | Opera o DocAI para gerar demos/insights vendáveis |
| Analyst | 📊 | Analisa documentos enviados, gera relatórios |
| CS (Customer Success) | 🤝 | Onboarding, retenção, satisfação |
| Growth | 📈 | Marketing, conteúdo, campanhas, conversão |

## APIs Principais

- `POST /api/orchestrator/events/` — Ingestão de eventos
- `GET /api/orchestrator/cases/` — Listar cases
- `GET /api/orchestrator/cases/{id}/` — Detalhe do case
- `GET /api/orchestrator/dashboard/*` — Métricas operacionais
- `POST /api/orchestrator/jarvis/ask/` — Perguntar ao Jarvis
- `GET /api/orchestrator/jarvis/briefing/` — Briefing executivo
- `POST /api/commercial/leads/ingest/` — Capturar lead
- `POST /api/commercial/leads/webhook/<source>/` — Webhook (Typeform/HubSpot/RD/Meta)
- `GET /api/commercial/leads/hot/` — Leads quentes
- `POST /api/commercial/leads/{id}/qualify/` — Qualificar lead
- `GET /api/commercial/pipeline/` — Pipeline de oportunidades
- `POST /api/auth/token/` — JWT token

## Sprints Entregues

### Sprint 1 — Orchestration Foundation ✅
- 6 Django apps, 10 modelos, state machine, event ingestion, audit trail, 5 endpoints

### Sprint 2 — Multi-Agent Runtime ✅
- Agent Runner (LLM real), Prompt Registry (5 agentes), Approval Gateway, DocAI Adapter, Notification Service, Inter-Agent Bus, Observabilidade (tracing + metrics)

### Sprint 2.5 — Distributed Hardening ✅
- Estado persistente (não mais em memória), Durable Events (Outbox/Inbox), claim distribuído com `skip_locked`, Circuit Breaker durável, Rate Limiting, Prompt versioning com canary

### Sprint 3 — Intelligence Layer ✅
- Notification Providers (Email/WhatsApp/Webhook), Semantic Memory & RAG (pgvector), Dashboard Operacional + Visualização 3D, Jarvis Executive Agent (routing + tools + briefing), UX Polish + Documentação
- 87 testes novos, 181 total passando, 12 endpoints API novos

### Sprint 4 — Commercial Operations ✅
- **Phase 1:** App `commercial/` completo (Lead, Scoring, Opportunity, FollowUp), SDR Agent, DocAI Operator, Executive Signals, Pipeline/Leads frontend, Governance & Multi-tenant
- **Phase 2:** Webhooks genéricos (Typeform/HubSpot/RD/Meta/Google), Demo scheduler
- **Phase 3:** Agent Charter Registry (7 agentes com KPIs/rotinas/autonomia), Celery Beat routines, Agent Metrics live, OpsAgentTeam dashboard
- 48 testes Sprint 4

## Decisões Técnicas Importantes

- **Groq como LLM default** (free tier, Llama 3 70B) — configurável via env `LLM_PROVIDER`
- **pgvector** para embeddings — modelo `all-MiniLM-L6-v2` (384 dims)
- **Celery Beat** para rotinas proativas dos agentes (qualify leads, stale checks, pipeline monitoring)
- **Approval-first para ações de impacto** — follow-ups, propostas, desqualificação de leads de alto valor
- **Tenant interno** (`docai_internal`) separa operações internas de clientes
- **Event sourcing light** — CaseEvents como fonte de verdade + snapshots
- **WebGL com fallback 2D** — Dashboard 3D detecta suporte e degrada graciosamente

## Convenções de Código

- Python: Django patterns, type hints, docstrings
- Services em `services.py`, tasks Celery em `tasks.py`, views DRF em `views.py`
- Testes em `src/tests/integration/`
- Frontend: componentes funcionais React, hooks customizados, Tailwind utility classes
- Commits: mensagens em português ou inglês (consistente dentro do PR)
- Novos apps sempre aditivos — nunca breaking changes nos existentes

## Comandos Úteis

```bash
# Dev environment
docker-compose up -d
cd src && python manage.py runserver
cd frontend && npm run dev

# Testes
pytest src/tests/integration/ -v
pytest src/tests/integration/test_sprint4_commercial.py -v

# Migrations
cd src && python manage.py makemigrations && python manage.py migrate

# Criar superuser
cd src && python manage.py createsuperuser
```

## Riscos Operacionais Conhecidos

- Alguns serviços Sprint 2 ainda emitem eventos via logger (não broker durável) — hardening parcial no Sprint 2.5
- 8 testes pré-existentes falhando (regexes/parsers de extração do DocAI core)
- Runtime protection e cost tracker existem mas não estão integrados no fluxo principal ainda

## Próximos Passos Planejados

- LLM real no Jarvis Ask (substituir intent detection determinístico)
- WebSocket para real-time (Django Channels)
- CI/CD com testes automatizados
- Integração Slack/Teams para alertas do Jarvis
- Mobile responsive para Operations e Jarvis
- WhatsApp/Telegram integration (notifications bidirecional)

## Público-Alvo do Produto DocAI

- Escritórios de Contabilidade e BPO Financeiro
- Consultorias de Planejamento Estratégico e Financeiro
- Departamentos Financeiros e de Controladoria
- Escritórios de Advocacia e Compliance

## Princípio de Decisão

> "Isso opera a EMPRESA DocAI ou serve o usuário do produto DocAI?"
> - Se opera a empresa → prioridade alta (Jarvis/agents)
> - Se serve o usuário do produto → entra no roadmap do DocAI core
