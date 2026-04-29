# DocAI Intelligence - Referencia Rapida para Demos

## Comandos Rapidos

```bash
# Setup (primeira vez)
.\scripts\setup_demo.bat

# Iniciar sistema
.\scripts\start_demo.bat

# Parar sistema
.\scripts\stop_demo.bat
```

## URLs

| Servico | URL |
|---------|-----|
| App | http://localhost:5173 |
| API Docs | http://localhost:8000/api/docs/ |
| Admin | http://localhost:8000/admin/ |

## Credenciais

```
Usuario: admin
Senha:   admin123
```

## Documentos de Teste

```
test_documents/
├── nota_fiscal_teste.txt      -> Tipo: Invoice
├── certidao_negativa_teste.txt -> Tipo: Certificate  
└── balanco_patrimonial_teste.txt -> Tipo: Balance
```

## Roteiro de Demo (5 min)

1. **Login** (30s)
   - Acessar localhost:5173
   - Logar com admin/admin123

2. **Upload** (1 min)
   - Clicar "Novo Documento"
   - Selecionar arquivo do cliente
   - Escolher tipo
   - Enviar

3. **Extracao** (1 min)
   - Mostrar dados extraidos
   - Destacar precisao

4. **Chat** (1.5 min)
   - Perguntar "Qual o valor total?"
   - Perguntar "Resuma este documento"
   - Mostrar respostas inteligentes

5. **Dashboard** (1 min)
   - Mostrar visao geral
   - Mostrar alertas de vencimento

## Perguntas Frequentes na Demo

**"Funciona com qualquer PDF?"**
> Sim, extraimos texto de qualquer PDF. A precisao depende da qualidade do documento.

**"Quanto tempo demora?"**
> Documentos simples: 5-10 segundos. Complexos: ate 30 segundos.

**"Os dados ficam seguros?"**
> Sim, criptografia em transito e repouso. Servidor dedicado por cliente.

**"Integra com meu sistema?"**
> Sim, temos API REST completa. Documentacao em /api/docs/

## Se Algo Der Errado

```bash
# Reiniciar tudo
.\scripts\stop_demo.bat
.\scripts\start_demo.bat
```
