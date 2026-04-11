# Findocia

**Plataforma de Inteligência Documental com IA**

[![CI](https://github.com/RhuanBorgesnr/docai-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/RhuanBorgesnr/docai-intelligence/actions/workflows/ci.yml)
[![CD](https://github.com/RhuanBorgesnr/docai-intelligence/actions/workflows/cd.yml/badge.svg)](https://github.com/RhuanBorgesnr/docai-intelligence/actions/workflows/cd.yml)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.0-green.svg)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![codecov](https://codecov.io/gh/RhuanBorgesnr/docai-intelligence/branch/main/graph/badge.svg)](https://codecov.io/gh/RhuanBorgesnr/docai-intelligence)

---

## Sobre o Projeto

O **Findocia** é uma plataforma que utiliza Inteligência Artificial para automatizar a análise de documentos empresariais, incluindo DREs, Balanços Patrimoniais, Contratos e Certidões.

### Principais Funcionalidades

- **Extração Automática de Indicadores Financeiros** - Processa DREs e Balanços automaticamente
- **Análise de Contratos com IA** - Identifica cláusulas críticas e classifica riscos
- **Chat Inteligente** - Faça perguntas sobre seus documentos em linguagem natural
- **Alertas de Vencimento** - Notificações por e-mail e WhatsApp
- **Gráficos e Comparativos** - Visualize a evolução financeira
- **Relatórios em PDF** - Geração automática de relatórios profissionais
- **Busca Semântica** - Encontre informações por contexto, não apenas palavras-chave

---

## Tecnologias

### Backend
- **Python 3.12** - Linguagem principal
- **Django 5.0** - Framework web
- **Django REST Framework** - API REST
- **Celery** - Processamento assíncrono
- **PostgreSQL + pgvector** - Banco de dados com busca vetorial
- **Redis** - Cache e message broker

### Inteligência Artificial
- **Groq (Llama 3 70B)** - IA generativa para análise avançada
- **Sentence Transformers** - Embeddings para busca semântica
- **PyMuPDF** - Extração de texto de PDFs

### Frontend
- **React 18** - Interface do usuário
- **Recharts** - Gráficos interativos
- **Tailwind CSS** - Estilização

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
└─────────────────────────────┬───────────────────────────────┘
                              │ REST API
┌─────────────────────────────▼───────────────────────────────┐
│                     Django REST Framework                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Auth JWT  │  │  Documents  │  │  Financial Analysis │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐    ┌────────▼────────┐   ┌───────▼───────┐
│  PostgreSQL   │    │     Celery      │   │     Redis     │
│  + pgvector   │    │    Workers      │   │    Cache      │
└───────────────┘    └────────┬────────┘   └───────────────┘
                              │
                     ┌────────▼────────┐
                     │    Groq API     │
                     │  (Llama 3 70B)  │
                     └─────────────────┘
```

---

## Instalação

### Pré-requisitos

- Docker e Docker Compose
- Node.js 18+ (para desenvolvimento frontend)
- Git

### Setup Rápido (Docker)

1. **Clone o repositório**
```bash
git clone https://github.com/seu-usuario/docai-intelligence.git
cd docai-intelligence
```

2. **Configure as variáveis de ambiente**
```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

3. **Inicie os serviços**
```bash
docker-compose up -d
```

4. **Execute as migrações**
```bash
docker-compose exec web python manage.py migrate
```

5. **Crie um superusuário**
```bash
docker-compose exec web python manage.py createsuperuser
```

6. **Acesse a aplicação**
- Backend API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/api/docs/
- Frontend: http://localhost:5173

### Setup de Desenvolvimento (Local)

#### Backend

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env

# Executar migrações
cd src
python manage.py migrate

# Iniciar servidor
python manage.py runserver
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

#### Celery Worker

```bash
cd src
celery -A core worker -l info
```

---

## Configuração

### Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `SECRET_KEY` | Chave secreta do Django | Sim |
| `DEBUG` | Modo debug (True/False) | Sim |
| `DATABASE_URL` | URL de conexão PostgreSQL | Sim |
| `REDIS_URL` | URL de conexão Redis | Sim |
| `GROQ_API_KEY` | Chave da API Groq | Sim |
| `TWILIO_ACCOUNT_SID` | SID da conta Twilio | Não |
| `TWILIO_AUTH_TOKEN` | Token de autenticação Twilio | Não |
| `EMAIL_HOST` | Servidor SMTP | Não |

Veja o arquivo `.env.example` para a lista completa.

---

## API

### Autenticação

A API utiliza JWT (JSON Web Tokens) para autenticação.

```bash
# Obter token
POST /api/auth/token/
{
  "username": "usuario",
  "password": "senha"
}

# Usar token
Authorization: Bearer <token>
```

### Endpoints Principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/documents/` | Upload de documento |
| `GET` | `/api/documents/` | Listar documentos |
| `GET` | `/api/documents/{id}/` | Detalhes do documento |
| `POST` | `/api/documents/{id}/chat/` | Chat com o documento |
| `GET` | `/api/documents/{id}/indicators/` | Indicadores financeiros |
| `GET` | `/api/documents/{id}/clauses/` | Cláusulas contratuais |
| `GET` | `/api/documents/financial/` | Dashboard financeiro |
| `GET` | `/api/documents/expiring/` | Documentos a vencer |

### Documentação Interativa

Acesse a documentação Swagger em: `http://localhost:8000/api/docs/`

---

## Estrutura do Projeto

```
plataforma_inteligencia_docs/
├── src/                      # Backend Django
│   ├── accounts/             # Autenticação e usuários
│   ├── companies/            # Multi-tenancy
│   ├── documents/            # Gestão de documentos
│   │   ├── models.py         # Modelos de dados
│   │   ├── views.py          # Endpoints da API
│   │   ├── tasks.py          # Tarefas Celery
│   │   ├── notifications.py  # Serviço de e-mail
│   │   ├── whatsapp.py       # Integração WhatsApp
│   │   └── reports.py        # Geração de PDFs
│   ├── ai/                   # Módulos de IA
│   │   ├── embeddings.py     # Geração de embeddings
│   │   ├── rag.py            # Retrieval Augmented Generation
│   │   ├── groq_client.py    # Cliente Groq/Llama 3
│   │   ├── financial_extraction.py  # Extração de indicadores
│   │   └── clause_extraction.py     # Extração de cláusulas
│   └── core/                 # Configurações Django
│       ├── settings.py
│       ├── urls.py
│       └── celery.py
├── frontend/                 # Frontend React
│   ├── src/
│   │   ├── components/       # Componentes reutilizáveis
│   │   ├── pages/            # Páginas da aplicação
│   │   ├── services/         # Chamadas à API
│   │   └── App.jsx           # Componente principal
│   └── package.json
├── docker/                   # Configurações Docker
├── docker-compose.yml        # Desenvolvimento
├── docker-compose.prod.yml   # Produção
├── requirements.txt          # Dependências Python
└── README.md
```

---

## Funcionalidades Detalhadas

### Extração de Indicadores Financeiros

O sistema utiliza uma estratégia em camadas:

1. **Regex Otimizado** - Padrões para formatos contábeis brasileiros
2. **Groq/Llama 3** - IA para documentos complexos
3. **Flan-T5 (fallback)** - Modelo local como backup

Indicadores extraídos automaticamente:
- Receita Bruta e Líquida
- Custos (CMV, CPV, CSV)
- Lucro Bruto, Operacional e Líquido
- EBITDA
- Margens (%)
- Ativos e Passivos
- Patrimônio Líquido

### Análise de Contratos

Cláusulas identificadas:
- Multas e Penalidades
- Reajustes (IPCA, IGP-M)
- Vigência e Prazos
- Condições de Rescisão
- Garantias
- Confidencialidade

Classificação de risco automática (Alto, Médio, Baixo).

### Chat com IA

Perguntas em linguagem natural sobre os documentos:
- "Qual a saúde financeira dessa empresa?"
- "Compare os últimos 3 meses"
- "Quais os riscos deste contrato?"

---

## Testes

```bash
# Executar todos os testes
cd src
python manage.py test

# Com cobertura
coverage run manage.py test
coverage report
```

---

## Deploy

### Produção com Docker

```bash
# Build e deploy
docker-compose -f docker-compose.prod.yml up -d --build

# Ver logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Checklist de Produção

- [ ] Configurar `DEBUG=False`
- [ ] Definir `SECRET_KEY` segura
- [ ] Configurar HTTPS/SSL
- [ ] Configurar backup do banco de dados
- [ ] Configurar monitoramento (Sentry, etc.)
- [ ] Configurar CDN para arquivos estáticos

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para detalhes sobre como contribuir.

---

## Licença

Este projeto está licenciado sob a licença MIT - veja [LICENSE](LICENSE) para detalhes.

---

## Suporte

- **Documentação**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/seu-usuario/docai-intelligence/issues)
- **E-mail**: suporte@docai.com.br

---

## Roadmap

- [x] Extração de indicadores financeiros
- [x] Análise de contratos com IA
- [x] Chat inteligente com documentos
- [x] Alertas de vencimento
- [x] Integração WhatsApp
- [x] Relatórios PDF
- [ ] OCR para documentos escaneados
- [ ] Integração com ERPs
- [ ] App mobile
- [ ] Multi-idioma

---

**Desenvolvido com por DocAI Intelligence**
