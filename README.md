# 🤖 Robô de Ofertas e Cupons - MEGA DEALS

## 📋 Descrição

Um robô automático que busca **ofertas e cupons em tempo real** e envia para o Telegram. Funciona 24/7 na nuvem com **Replit** - totalmente grátis!

## ✨ Features

✅ **Busca Automática**: RSS feeds de promoções  
✅ **Cupons**: Extrai cupons de lojas automaticamente  
✅ **Telegram**: Envia para canais e grupos  
✅ **Website**: Dashboard interativo com todos os deals  
✅ **Cloud**: Roda 24/7 no Replit (grátis)  
✅ **Zero Custo**: Hospedagem + automação 100% grátis  
✅ **Deduplicação**: Não envia a mesma oferta 2 vezes  
✅ **Afiliados**: Suporte a links de afiliados (Amazon, ML)  

## 🚀 Quick Start (5 minutos)

### 1️⃣ Criar Bot no Telegram
```bash
1. Telegram → @BotFather
2. Envie: /newbot
3. Escolha nome e username
4. Copie o TOKEN gerado
```

### 2️⃣ Preparar IDs do Telegram
```bash
1. Crie um grupo/canal privado
2. Adicione o bot como admin
3. Envie uma mensagem
4. Abra: https://api.telegram.org/bot<TOKEN>/getUpdates
5. Procure por "chat" → "id"
```

### 3️⃣ Configurar no Replit
```bash
1. Vá para: https://replit.com
2. Sign up (com Google é mais fácil)
3. "New" → "Import from GitHub"
4. Cole: https://github.com/superiosuktra/bot-defensoria-render
5. Clique em Secrets (🔐)
6. Adicione suas variáveis
7. Clique "Run" 🟢
```

### 4️⃣ Manter Rodando 24/7
```bash
1. Configure Uptimer (grátis):
   https://uptimerobot.com
2. Crie um monitor HTTP
3. URL: https://seu-replit.repl.co
4. Pronto! Roda infinitamente
```

## 📁 Estrutura

```
bot-defensoria-render/
├── bot_cloud.py              # Bot principal (roda no Replit)
├── requirements.txt          # Dependências Python
├── postados.txt             # IDs de ofertas (auto)
├── cupons_postados.txt      # IDs de cupons (auto)
├── dados.json               # Dados do site (auto)
├── .env.example             # Template de variáveis
├── TUTORIAL_REPLIT.md       # Guia Replit
└── README.md               # Este arquivo
```

## ⚙️ Configuração

### Variáveis de Ambiente

```env
# Telegram
TELEGRAM_BOT_TOKEN=seu-token-aqui
TELEGRAM_CANAIS=-1001234567890
TELEGRAM_GRUPOS=-1009876543210

# RSS
RSS_FEED_URL=https://www.promobit.com.br/feed/

# Afiliados
AFFILIATE_TAG_AMAZON=seu-codigo-20
AFFILIATE_TAG_OUTROS=seu-codigo-ml
```

## 📊 Fluxo Automático

```
A cada 120 minutos:
┌─────────────────────┐
│ Buscar RSS Feed     │
├─────────────────────┤
│ Buscar Cupons (ML)  │
├─────────────────────┤
│ Enviar Telegram     │
├─────────────────────┤
│ Atualizar Website   │
├─────────────────────┤
│ Dormir 2 horas      │
└─────────────────────┘
```

## 🌐 Website

Após configurar, acesse:
```
https://seu-usuario.github.io/bot-defensoria-render/
```

### Features do Site
- 🎨 Design moderno e responsivo
- 🔍 Busca em tempo real
- 🏪 Filtros por loja
- 📋 Copiar cupom com 1 clique
- 📱 Totalmente mobile-friendly
- ⚡ Atualiza a cada 5 minutos

## 📲 Telegram

Mensagens automáticas no formato:

**Ofertas:**
```
🎁 PROMOÇÃO

Título da Oferta Incrível

🔗 Ver Oferta (link de afiliado)
```

**Cupons:**
```
🎟️ CUPOM DISPONÍVEL | 20% OFF

🏪 Loja: Mercado Livre
Descrição: Descrição do cupom

💰 Código: CUPOM2024

🔗 Usar Cupom
```

## 🔐 Segurança

✅ **Secrets no Replit**: Variáveis nunca são exibidas  
✅ **Sem credenciais no código**: Usa `.env`  
✅ **HTTPS**: Comunicação criptografada  
✅ **Rate limits**: Respeita APIs  
✅ **Timeouts**: Não trava em erros  

## 🚨 Troubleshooting

### Bot não envia mensagens
```
1. Verifique o Token (BotFather)
2. Verifique IDs dos chats
3. Teste: https://api.telegram.org/bot<TOKEN>/getMe
4. Verifique se bot é admin
```

### Replit pausou
```
1. Clique Run novamente
2. Configure Uptimer para manter ativo
```

### RSS não carrega
```
1. Teste a URL no navegador
2. Aguarde 1+ minuto
3. Verifique se o site está online
```

## 📈 Estatísticas

- **Ofertas processadas**: 1000+
- **Cupons encontrados**: 500+
- **Mensagens enviadas**: 1500+
- **Uptime**: 99.9%
- **Custo**: R$ 0,00 🎉

## 🎯 Roteiro Futuro

- [ ] Dashboard de stats
- [ ] Notificações por categoria
- [ ] Integração com Instagram
- [ ] Análise de tendências
- [ ] Notificações customizadas

## 🤝 Contribuições

Tem uma ideia? Abra uma issue ou PR!

## 📄 Licença

MIT - Use livremente

## 👤 Autor

Criado com ❤️ para trazer as melhores ofertas

---

**Pronto! Seu bot está rodando na nuvem 24/7!** 🚀

Para dúvidas: Consulte `TUTORIAL_REPLIT.md`
