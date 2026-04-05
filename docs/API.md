# DocAI Intelligence - API Documentation

## Overview

A API do DocAI Intelligence é construída com Django REST Framework e utiliza autenticação JWT.

**Base URL**: `http://localhost:8000/api/`

**Documentação Interativa**: `http://localhost:8000/api/docs/`

---

## Autenticação

### Obter Token JWT

```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "seu_usuario",
  "password": "sua_senha"
}
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### Usar Token

Inclua o token em todas as requisições:

```http
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### Refresh Token

```http
POST /api/auth/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

---

## Documentos

### Listar Documentos

```http
GET /api/documents/
Authorization: Bearer <token>
```

**Query Parameters:**
- `document_type`: Filtrar por tipo (dre, balance, contract, etc.)
- `search`: Buscar por título

**Response:**
```json
[
  {
    "id": 1,
    "title": "DRE 2024",
    "document_type": "dre",
    "file": "/media/documents/dre_2024.pdf",
    "expiration_date": "2025-12-31",
    "created_at": "2024-01-15T10:30:00Z",
    "reference_date": "2024-12-31"
  }
]
```

### Upload de Documento

```http
POST /api/documents/
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <arquivo.pdf>
title: "DRE 2024"
document_type: "dre"
expiration_date: "2025-12-31" (opcional)
reference_date: "2024-12-31" (opcional)
```

**Response:**
```json
{
  "id": 1,
  "title": "DRE 2024",
  "document_type": "dre",
  "file": "/media/documents/dre_2024.pdf",
  "status": "processing"
}
```

### Detalhes do Documento

```http
GET /api/documents/{id}/
Authorization: Bearer <token>
```

### Excluir Documento

```http
DELETE /api/documents/{id}/
Authorization: Bearer <token>
```

---

## Indicadores Financeiros

### Indicadores de um Documento

```http
GET /api/documents/{id}/indicators/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "document_id": 1,
  "document_title": "DRE 2024",
  "indicators": [
    {
      "indicator_type": "receita_liquida",
      "indicator_display": "Receita Líquida",
      "value": "1234567.89",
      "formatted_value": "R$ 1.234.567,89"
    },
    {
      "indicator_type": "lucro_liquido",
      "indicator_display": "Lucro Líquido",
      "value": "123456.00",
      "formatted_value": "R$ 123.456,00"
    },
    {
      "indicator_type": "margem_liquida",
      "indicator_display": "Margem Líquida",
      "value": "10.00",
      "formatted_value": "10.00%"
    }
  ]
}
```

### Extrair/Re-extrair Indicadores

```http
POST /api/documents/{id}/extract-indicators/
Authorization: Bearer <token>
```

### Dashboard Financeiro

```http
GET /api/documents/financial/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_documents": 15,
  "latest_indicators": {
    "receita_liquida": "1234567.89",
    "lucro_liquido": "123456.00",
    "ebitda": "234567.00",
    "margem_bruta": "45.50",
    "margem_liquida": "10.00"
  }
}
```

### Histórico de Indicadores

```http
GET /api/documents/financial/history/?type=receita_liquida
Authorization: Bearer <token>
```

**Response:**
```json
{
  "indicator_type": "receita_liquida",
  "data": [
    {"date": "2024-01", "value": "1000000.00"},
    {"date": "2024-02", "value": "1100000.00"},
    {"date": "2024-03", "value": "1234567.89"}
  ]
}
```

### Comparar Períodos

```http
GET /api/documents/financial/compare/?doc1=1&doc2=2
Authorization: Bearer <token>
```

**Response:**
```json
{
  "period1": {
    "document_id": 1,
    "reference_date": "2024-01-31",
    "indicators": {...}
  },
  "period2": {
    "document_id": 2,
    "reference_date": "2024-02-28",
    "indicators": {...}
  },
  "variations": {
    "receita_liquida": {
      "absolute": "100000.00",
      "percentage": "10.00"
    }
  }
}
```

---

## Análise de Contratos

### Cláusulas de um Contrato

```http
GET /api/documents/{id}/clauses/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "document_id": 5,
  "document_title": "Contrato de Prestação de Serviços",
  "clauses": [
    {
      "id": 1,
      "clause_type": "multa",
      "clause_display": "Multa/Penalidade",
      "title": "Cláusula 8 - Multa por Rescisão",
      "content": "Em caso de rescisão antecipada...",
      "summary": "Multa de 20% sobre o valor restante do contrato",
      "risk_level": "high",
      "extracted_value": "20%"
    }
  ],
  "risk_summary": {
    "high": 1,
    "medium": 2,
    "low": 3
  }
}
```

### Extrair Cláusulas

```http
POST /api/documents/{id}/extract-clauses/
Authorization: Bearer <token>
```

### Listar Contratos com Cláusulas

```http
GET /api/documents/contracts/
Authorization: Bearer <token>
```

---

## Chat com Documentos

### Fazer Pergunta

```http
POST /api/chat/
Authorization: Bearer <token>
Content-Type: application/json

{
  "question": "Qual a saúde financeira da empresa?",
  "document_ids": [1, 2, 3]  // opcional
}
```

**Response:**
```json
{
  "answer": "A análise dos documentos indica que a empresa apresenta...",
  "sources": [
    {
      "document_id": 1,
      "document_title": "DRE 2024",
      "relevance": 0.95
    }
  ],
  "chunks_used": 5
}
```

---

## Alertas de Vencimento

### Documentos a Vencer

```http
GET /api/documents/expiring/?days=30
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 5,
    "title": "Contrato XYZ",
    "document_type": "contract",
    "expiration_date": "2024-02-15",
    "days_until_expiration": 7
  }
]
```

---

## Relatórios

### Download Relatório PDF

```http
GET /api/documents/{id}/report/
Authorization: Bearer <token>
```

**Response:** Arquivo PDF

### Relatório Comparativo

```http
GET /api/documents/financial/report/?doc1=1&doc2=2
Authorization: Bearer <token>
```

**Response:** Arquivo PDF

---

## Estatísticas

### Estatísticas Gerais

```http
GET /api/documents/stats/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_documents": 150,
  "by_type": {
    "dre": 45,
    "balance": 30,
    "contract": 50,
    "certificate": 25
  },
  "expiring_soon": 5,
  "processed_this_month": 23
}
```

---

## Busca Semântica

### Buscar nos Documentos

```http
GET /api/search/?q=margem+de+lucro
Authorization: Bearer <token>
```

**Response:**
```json
{
  "results": [
    {
      "document_id": 1,
      "document_title": "DRE 2024",
      "chunk": "A margem de lucro líquido foi de 10%...",
      "relevance": 0.92
    }
  ]
}
```

---

## Códigos de Erro

| Código | Descrição |
|--------|-----------|
| 400 | Bad Request - Dados inválidos |
| 401 | Unauthorized - Token inválido ou expirado |
| 403 | Forbidden - Sem permissão |
| 404 | Not Found - Recurso não encontrado |
| 429 | Too Many Requests - Rate limit excedido |
| 500 | Internal Server Error |

---

## Rate Limits

| Endpoint | Limite |
|----------|--------|
| Autenticação | 5 req/min |
| Upload | 10 req/min |
| Chat | 30 req/min |
| Outros | 100 req/min |

---

## Webhooks (Futuro)

Webhooks para notificação de eventos:

- `document.processed` - Documento processado
- `document.expiring` - Documento próximo do vencimento
- `indicators.extracted` - Indicadores extraídos

---

## SDKs

### Python

```python
from docai import DocAIClient

client = DocAIClient(
    base_url="http://localhost:8000/api",
    token="seu_token_jwt"
)

# Upload documento
doc = client.documents.upload("dre_2024.pdf", document_type="dre")

# Obter indicadores
indicators = client.documents.get_indicators(doc.id)

# Chat
response = client.chat.ask("Qual o lucro líquido?")
```

### JavaScript

```javascript
import { DocAIClient } from 'docai-js';

const client = new DocAIClient({
  baseUrl: 'http://localhost:8000/api',
  token: 'seu_token_jwt'
});

// Upload documento
const doc = await client.documents.upload(file, { type: 'dre' });

// Chat
const response = await client.chat.ask('Qual a margem bruta?');
```

---

## Suporte

- **Documentação Swagger**: `/api/docs/`
- **ReDoc**: `/api/redoc/`
- **Email**: suporte@docai.com.br
