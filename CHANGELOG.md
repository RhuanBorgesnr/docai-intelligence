# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2026-04-02

### Adicionado
- Upload e gestão de documentos (PDF)
- Extração automática de indicadores financeiros de DREs
- Análise de cláusulas contratuais com IA
- Chat inteligente com documentos usando Groq/Llama 3
- Alertas de vencimento por e-mail e WhatsApp
- Gráficos interativos de evolução financeira
- Comparativo entre períodos
- Geração de relatórios em PDF
- Busca semântica com embeddings
- API REST documentada com Swagger/OpenAPI
- Autenticação JWT
- Multi-tenancy (isolamento por empresa)
- Docker Compose para desenvolvimento e produção

### Tecnologias
- Backend: Django 5.0 + Django REST Framework
- IA: Groq (Llama 3 70B) + Sentence Transformers
- Banco de dados: PostgreSQL + pgvector
- Cache/Queue: Redis + Celery
- Frontend: React 18 + Recharts
- PDF: PyMuPDF + ReportLab

---

## [Unreleased]

### Planejado
- OCR para documentos escaneados
- Integração com ERPs (SAP, TOTVS)
- App mobile (React Native)
- Multi-idioma (EN, ES)
- Exportação para Excel
- API de Webhooks
