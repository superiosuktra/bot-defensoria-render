🤖 Robô de Ofertas e Cupons - MEGA OFERTAS
Robô automático que busca ofertas e cupons em tempo real e envio para o Telegram, com painel web para controle total e auto-clean de ofertas esgotadas.

✨ Recursos
Busca Automática : RSS feeds de promoções

Cupons : Extração automática de cupons do Mercado Livre

Telegram : Envio para canais e grupos

Dashboard Web : Controle via navegador (pausa, forçar ciclo, limpeza automática)

Auto-Clean : Verifica ofertas ativas e marcas como encerradas no Telegram

Deduplicação : Não envie a mesma oferta 2 vezes

Afiliados Dinâmicos : Cadastre qualquer loja nova pelo painel (domínio + parâmetro + código) — o bot passa a aplicar automaticamente, sem precisar mexer no código

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

🏪 Adicionando uma loja de afiliado nova (sem tocar no código)
No painel web, seção CONFIG_DINÂMICA → LOJAS DE AFILIADO (DINÂMICO):

Clique em + ADICIONAR LOJA

Preencha:

Nome: só um rótulo (ex: "Shopee")

Domínio: domínio do site, sem https:// (ex: shopee.com.br)

Parâmetro: nome do parâmetro de URL que a loja usa para rastrear afiliados (ex: tag, utm_source, af_id — cada loja tem o seu, veja no seu link de afiliado gerado pela própria loja)

Código: o valor do seu código de afiliado

Clique em GRAVAR PARÂMETROS

A partir do próximo ciclo, qualquer link de oferta cujo domínio bata com o cadastrado recebe automaticamente o parâmetro de afiliado. Pode cadastrar quantas lojas quiser, remover com o ✕, tudo fica salvo em config.json.

🔐 Segurança
Segredos apenas em variáveis ​​de ambiente ( .env) ou em config.json (nunca versionado — veja .gitignore)

Painel protegido por senha (comparação resistente a timing attack) e sessão Flask

Rate limiting: após 5 tentativas de login erradas, o IP fica bloqueado por 5 minutos

Proteção CSRF em todos os formulários que alteram estado (login, config, controles do bot)

Token do Telegram nunca é reexibido no HTML do painel (campo fica em branco; só é alterado se você digitar um novo valor)

Proteção contra SSRF: antes de o bot verificar se um link de oferta "morreu", o domínio é resolvido e IPs privados/locais/metadata (127.0.0.1, 192.168.x.x, 169.254.169.254 etc.) são bloqueados — impede que um feed RSS malicioso force o servidor a acessar sua própria rede interna

Headers de segurança (X-Frame-Options, Content-Security-Policy, X-Content-Type-Options) contra clickjacking e MIME sniffing

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
