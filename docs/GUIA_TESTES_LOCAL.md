# DocAI Intelligence - Guia de Testes Local

## Sumario

1. [Pre-requisitos](#1-pre-requisitos)
2. [Setup Inicial](#2-setup-inicial)
3. [Iniciando o Sistema](#3-iniciando-o-sistema)
4. [Testes do Fluxo Completo](#4-testes-do-fluxo-completo)
5. [Testes por Funcionalidade](#5-testes-por-funcionalidade)
6. [Checklist de Demonstracao](#6-checklist-de-demonstracao)
7. [Solucao de Problemas](#7-solucao-de-problemas)

---

## 1. Pre-requisitos

### Software Necessario

| Software | Versao Minima | Download |
|----------|---------------|----------|
| Python | 3.10+ | https://python.org |
| Node.js | 18+ | https://nodejs.org |
| Git | 2.0+ | https://git-scm.com |

### Verificar Instalacao

```bash
python --version   # ou py --version
node --version
npm --version
git --version
```

---

## 2. Setup Inicial

### Opcao A: Script Automatico (Recomendado)

```bash
# Navegar para pasta do projeto
cd c:\Users\rbden\projects\plataforma_inteligencia_docs

# Executar setup
.\scripts\setup_demo.bat
```

### Opcao B: Manual

```bash
# 1. Criar ambiente virtual
python -m venv venv
.\venv\Scripts\activate

# 2. Instalar dependencias backend
pip install -r src\requirements.txt

# 3. Configurar banco de dados
cd src
python manage.py migrate

# 4. Criar usuario admin
python manage.py createsuperuser
# Usuario: admin
# Email: admin@docai.com
# Senha: admin123

# 5. Instalar dependencias frontend
cd ..\frontend
npm install
```

---

## 3. Iniciando o Sistema

### Opcao A: Script Automatico

```bash
.\scripts\start_demo.bat
```

### Opcao B: Manual (2 terminais)

**Terminal 1 - Backend:**
```bash
cd src
..\venv\Scripts\activate
python manage.py runserver
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### URLs do Sistema

| Servico | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000/api/ |
| Documentacao API | http://localhost:8000/api/docs/ |
| Admin Django | http://localhost:8000/admin/ |

---

## 4. Testes do Fluxo Completo

### Fluxo 1: Registro e Login

| Passo | Acao | Resultado Esperado |
|-------|------|-------------------|
| 1.1 | Acessar http://localhost:5173 | Tela de login aparece |
| 1.2 | Clicar em "Registrar" | Formulario de registro |
| 1.3 | Preencher dados e submeter | Conta criada, redireciona para login |
| 1.4 | Fazer login com credenciais | Dashboard principal aparece |

**Credenciais de Teste:**
- Usuario: `admin`
- Senha: `admin123`

---

### Fluxo 2: Upload de Documento

| Passo | Acao | Resultado Esperado |
|-------|------|-------------------|
| 2.1 | Clicar em "Novo Documento" | Modal de upload abre |
| 2.2 | Selecionar arquivo PDF/TXT | Arquivo selecionado |
| 2.3 | Escolher tipo (ex: "Nota Fiscal") | Tipo selecionado |
| 2.4 | Clicar "Enviar" | Upload inicia |
| 2.5 | Aguardar processamento | Status: "Processando" -> "Concluido" |

**Arquivos de Teste:**
```
test_documents/
├── nota_fiscal_teste.txt
├── certidao_negativa_teste.txt
└── balanco_patrimonial_teste.txt
```

---

### Fluxo 3: Visualizar Documento Processado

| Passo | Acao | Resultado Esperado |
|-------|------|-------------------|
| 3.1 | Clicar no documento na lista | Abre detalhes do documento |
| 3.2 | Verificar "Dados Extraidos" | Campos extraidos aparecem |
| 3.3 | Verificar indicadores (se financeiro) | Metricas calculadas |

**Campos Esperados por Tipo:**

| Tipo | Campos Extraidos |
|------|------------------|
| Nota Fiscal | CNPJ, Valor Total, Data Emissao, Chave Acesso |
| Certidao | Tipo, Status, Data Validade, CNPJ |
| Balanco | Ativo Total, Passivo Total, Patrimonio Liquido |

---

### Fluxo 4: Chat com Documento

| Passo | Acao | Resultado Esperado |
|-------|------|-------------------|
| 4.1 | Abrir documento | Pagina de detalhes |
| 4.2 | Clicar em "Chat" ou area de perguntas | Campo de input aparece |
| 4.3 | Digitar pergunta (ex: "Qual o valor total?") | Resposta baseada no documento |

**Perguntas de Teste:**
- "Qual e o CNPJ do emitente?"
- "Qual e o valor total da nota?"
- "Quando vence este documento?"
- "Resuma este documento"

---

### Fluxo 5: Dashboard e Alertas

| Passo | Acao | Resultado Esperado |
|-------|------|-------------------|
| 5.1 | Acessar Dashboard | Graficos e metricas |
| 5.2 | Verificar "Documentos Vencendo" | Lista de alertas |
| 5.3 | Clicar em alerta | Abre documento relacionado |

---

## 5. Testes por Funcionalidade

### 5.1 API - Testes via Swagger

Acessar: http://localhost:8000/api/docs/

| Endpoint | Metodo | Teste |
|----------|--------|-------|
| `/api/auth/login/` | POST | Login com credenciais |
| `/api/accounts/register/` | POST | Criar nova conta |
| `/api/documents/` | GET | Listar documentos |
| `/api/documents/` | POST | Upload de documento |
| `/api/documents/{id}/` | GET | Detalhes do documento |
| `/api/chat/` | POST | Pergunta ao documento |

### 5.2 Extratores - Testar Cada Tipo

```
POST /api/documents/
Content-Type: multipart/form-data

file: [arquivo]
title: "Teste Nota Fiscal"
document_type: "invoice"  # ou "certificate", "balance", "report"
```

### 5.3 Testes Automatizados

```bash
cd src
python -m pytest tests/ -v
```

---

## 6. Checklist de Demonstracao

### Antes da Demo

- [ ] Executar `setup_demo.bat`
- [ ] Verificar se backend esta rodando (http://localhost:8000/api/health/)
- [ ] Verificar se frontend esta rodando (http://localhost:5173)
- [ ] Preparar documentos de exemplo do cliente
- [ ] Testar login com usuario admin

### Durante a Demo

- [ ] **Login** - Mostrar autenticacao
- [ ] **Upload** - Subir documento do cliente
- [ ] **Extracao** - Mostrar dados extraidos automaticamente
- [ ] **Chat** - Fazer perguntas sobre o documento
- [ ] **Dashboard** - Mostrar visao geral
- [ ] **Alertas** - Mostrar controle de vencimentos

### Pontos a Destacar

1. **Velocidade** - Extracao em segundos
2. **Precisao** - Dados extraidos corretamente
3. **Facilidade** - Interface intuitiva
4. **Inteligencia** - Respostas contextuais no chat

---

## 7. Solucao de Problemas

### Erro: "Python nao encontrado"

```bash
# Windows - usar py em vez de python
py --version
py -m pip install -r requirements.txt
```

### Erro: "Porta 8000 em uso"

```bash
# Encontrar processo
netstat -ano | findstr :8000

# Matar processo (substituir PID)
taskkill /PID [PID] /F
```

### Erro: "Module not found"

```bash
# Reinstalar dependencias
pip install -r src/requirements.txt --force-reinstall
```

### Erro: "CORS blocked"

Verificar se backend e frontend estao nas portas corretas:
- Backend: 8000
- Frontend: 5173

### Erro: "Database locked"

```bash
# Deletar banco e recriar
del src\db.sqlite3
cd src
python manage.py migrate
```

### Frontend nao carrega

```bash
cd frontend
rm -rf node_modules
npm install
npm run dev
```

---

## Contato

**DocAI Intelligence**
Suporte Tecnico: suporte@docai.com
Documentacao: https://docs.docai.com

---

*Ultima atualizacao: Abril 2026*
