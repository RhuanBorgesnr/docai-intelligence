# Deploy em Produção

Guia completo para deploy da Plataforma de Inteligência de Documentos.

## Pré-requisitos

- Docker e Docker Compose instalados
- Domínio configurado apontando para o servidor
- Certificado SSL (Let's Encrypt ou similar)
- Mínimo 4GB RAM, 2 vCPUs

## 1. Preparação do Servidor

```bash
# Clonar o repositório
git clone <repo-url> /opt/plataforma
cd /opt/plataforma

# Criar diretórios necessários
mkdir -p docker/nginx/ssl backups
```

## 2. Configuração do Ambiente

```bash
# Copiar e editar arquivo de configuração
cp .env.example .env
nano .env
```

### Variáveis Obrigatórias para Produção

```env
# IMPORTANTE: Altere estes valores!
DEBUG=False
SECRET_KEY=<gere-uma-chave-segura>
ALLOWED_HOSTS=seudominio.com,www.seudominio.com

# Banco de dados (use senha forte!)
DB_PASSWORD=<senha-segura>

# AI
HF_API_TOKEN=<seu-token-huggingface>

# Email (para notificações)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<email>
EMAIL_HOST_PASSWORD=<senha-de-app>
DEFAULT_FROM_EMAIL=Plataforma <noreply@seudominio.com>

# CORS/CSRF
CORS_ALLOWED_ORIGINS=https://seudominio.com
CSRF_TRUSTED_ORIGINS=https://seudominio.com
```

### Gerar SECRET_KEY

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 3. Certificados SSL

### Opção A: Let's Encrypt (recomendado)

```bash
# Instalar certbot
apt install certbot

# Gerar certificado (pare o nginx primeiro se estiver rodando)
certbot certonly --standalone -d seudominio.com -d www.seudominio.com

# Copiar certificados
cp /etc/letsencrypt/live/seudominio.com/fullchain.pem docker/nginx/ssl/
cp /etc/letsencrypt/live/seudominio.com/privkey.pem docker/nginx/ssl/
```

### Opção B: Certificado Self-Signed (apenas para teste)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout docker/nginx/ssl/privkey.pem \
  -out docker/nginx/ssl/fullchain.pem \
  -subj "/CN=localhost"
```

## 4. Deploy

```bash
# Build e iniciar serviços
docker-compose -f docker-compose.prod.yml up -d --build

# Verificar status
docker-compose -f docker-compose.prod.yml ps

# Ver logs
docker-compose -f docker-compose.prod.yml logs -f
```

## 5. Criar Superusuário

```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

## 6. Backup Automático

Adicione ao crontab:

```bash
# Backup diário às 3h da manhã
0 3 * * * cd /opt/plataforma && docker-compose -f docker-compose.prod.yml exec -T postgres /backups/backup.sh
```

### Backup Manual

```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py dumpdata > backup.json
```

## 7. Monitoramento

### Health Check

```bash
curl https://seudominio.com/api/health/
```

### Logs

```bash
# Todos os serviços
docker-compose -f docker-compose.prod.yml logs -f

# Serviço específico
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f celery
```

## 8. Atualizações

```bash
# Parar serviços
docker-compose -f docker-compose.prod.yml down

# Atualizar código
git pull

# Rebuild e iniciar
docker-compose -f docker-compose.prod.yml up -d --build

# Aplicar migrações
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate
```

## 9. WhatsApp (Opcional)

1. Criar conta no [Twilio](https://www.twilio.com)
2. Ativar WhatsApp Sandbox
3. Configurar variáveis no `.env`:

```env
WHATSAPP_ENABLED=True
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

## Troubleshooting

### Erro de conexão com banco

```bash
# Verificar se postgres está rodando
docker-compose -f docker-compose.prod.yml ps postgres

# Ver logs do postgres
docker-compose -f docker-compose.prod.yml logs postgres
```

### Erro de permissão em arquivos

```bash
# Corrigir permissões
docker-compose -f docker-compose.prod.yml exec web chown -R appuser:appuser /app/media
```

### Celery não processa tarefas

```bash
# Verificar conexão com Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# Reiniciar Celery
docker-compose -f docker-compose.prod.yml restart celery celery-beat
```

## Arquitetura

```
                    ┌─────────────┐
                    │   Nginx     │ :80/:443
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────┴─────┐ ┌────┴────┐ ┌─────┴─────┐
        │  Static   │ │  Media  │ │   API     │
        │  Files    │ │  Files  │ │  (Django) │
        └───────────┘ └─────────┘ └─────┬─────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              ┌─────┴─────┐       ┌─────┴─────┐       ┌─────┴─────┐
              │ PostgreSQL│       │   Redis   │       │  Celery   │
              │ + pgvector│       │           │       │  Workers  │
              └───────────┘       └───────────┘       └───────────┘
```

## Suporte

Em caso de problemas, verifique:
1. Logs dos containers
2. Health check endpoint
3. Conexão com banco de dados
4. Conexão com Redis
