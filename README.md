# 🤖 Robô de Ofertas e Cupons - MEGA DEALS

Robô automático que busca ofertas e cupons em tempo real e envia para o Telegram. Funciona 24/7 na nuvem com painel web integrado para controle total.

## ✨ Features

- **Busca Automática**: RSS feeds de promoções
- **Cupons**: Extração automática de cupons
- **Telegram**: Envio para canais e grupos
- **Dashboard Web**: Controle completo via navegador
- **Auto-Clean**: Detecção e edição de ofertas esgotadas
- **Deduplicação**: Não envia a mesma oferta 2 vezes
- **Afiliados**: Suporte a links de afiliados (Amazon, ML)
- **Filtros**: Blacklist e whitelist personalizáveis

## 🚀 Quick Start

### 1️⃣ Criar Bot no Telegram

1. Telegram → @BotFather
2. Envie: `/newbot`
3. Escolha nome e username
4. Copie o TOKEN gerado

### 2️⃣ Preparar IDs do Telegram

1. Crie um grupo/canal privado
2. Adicione o bot como admin
3. Envie uma mensagem
4. Abra: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Procure por `"chat"` → `"id"`

### 3️⃣ Configurar Ambiente

1. Copie `.env.example` para `.env`
2. Preencha com seus valores:
   - `PAINEL_PASSWORD`: senha forte para o dashboard
   - `FLASK_SECRET_KEY`: gere com `python -c "import secrets; print(secrets.token_hex(32))"`
   - `TELEGRAM_BOT_TOKEN`: token do BotFather
   - `TELEGRAM_CANAIS`, `TELEGRAM_GRUPOS`: IDs dos chats
3. **NUNCA commit o `.env` no Git**

### 4️⃣ Instalar Dependências

```bash
pip install -r requirements.txt
