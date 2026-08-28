🤖 Robô de Ofertas e Cupons - MEGA OFERTAS
Robô automático que busca ofertas e cupons em tempo real e envio para o Telegram, com painel web para controle total e auto-clean de ofertas esgotadas.

✨ Recursos
Busca Automática : RSS feeds de promoções

Cupons : Extração automática de cupons do Mercado Livre

Telegram : Envio para canais e grupos

Dashboard Web : Controle via navegador (pausa, forçar ciclo, limpeza automática)

Auto-Clean : Verifica ofertas ativas e marcas como encerradas no Telegram

Deduplicação : Não envie a mesma oferta 2 vezes

Afiliados : Suporte a links de afiliados (Amazon, Mercado Livre)

Filtros : Blacklist e whitelist personalizáveis

🚀 Início Rápido
1️⃣ Criar Bot no Telegram
Telegram →@BotFather

Envie:/newbot

Escolha nome e nome de usuário

Copie o TOKEN gerado

2️⃣ Preparar IDs do Telegram
Crie um grupo/canal privado

” o bot como admin

Envie uma mensagem qualquer

Abra:https://api.telegram.org/bot<TOKEN>/getUpdates

Procure por "chat"→"id"

3️⃣ Configurar Ambiente
Copie file.env.examplepara.env

apêndice com seus valores:

PAINEL_PASSWORD: senha forte para o dashboard

FLASK_SECRET_KEY: gere compython -c "import secrets; print(secrets.token_hex(32))"

TELEGRAM_BOT_TOKEN: token do BotFather

TELEGRAM_CANAIS, TELEGRAM_GRUPOS: IDs dos chats (separados por vírgula)

RSS_FEED_URL, AFFILIATE_TAG_AMAZON, AFFILIATE_TAG_OUTROS(opcional)

NUNCA dê commit não .envnão Git

4️⃣ Instalar Dependências
bash
pip install -r requirements.txt
5️⃣ Executar Localmente
bash
python bot_cloud.py
acesse o painel em:http://localhost:8080

🔐 Segurança
Segredos apenas em variáveis ​​de ambiente ( .env)

Painel protegido por senha e sessão Flask duradoura

Cookies de sessão marcada como HttpOnlye SameSite=Laxpor padrão

SESSION_COOKIE_SECUREativo quandoFLASK_ENV=production

📦 Estrutura Simplificada
texto
bot-defensoria-render/
├── bot_cloud.py          # Bot + painel Flask
├── requirements.txt      # Dependências Python
├── file.env.example      # Template de variáveis (.env)
├── file.gitignore        # Gitignore sugerido
├── README.md             # Este arquivo
├── TUTORIAL_REPLIT.md    # Guia para rodar na nuvem (Replit)
└── mensagens_ativas.json # Gerado em runtime (não versionar)
🧹 Limpeza automática
O botão LIMPAR ESGOTADOS executa uma varredura nas ofertas ativas:

Carregamensagens_ativas.json

Para cada link, faça GETcom timeout curto

Se encontrar 404/410 ou texto de esgotado/indisponível, edite a mensagem no Telegram com um banner de oferta encerrada

⚠️ Aviso Importante
Nunca compartilhe seus TELEGRAM_BOT_TOKENtutoriais, prints ou repositórios públicos. Gere um novo token sempre que suspeitar de vazamento.
