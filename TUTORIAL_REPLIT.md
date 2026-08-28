🚀 GUIA COMPLETO - BOT NA NUVEM (REPLIT)
⚡ O QUE É REPLIT?
Replit é uma plataforma que permite rodar código Python 24/7 na nuvem (com plano grátis e opções pagas).

✅ Sem instalar nada no seu PC

✅ Sem usar GitHub Actions

✅ Interface simples

✅ Permite usar variáveis ​​de ambiente (segredos)

🎯 PASSO A PASSO COMPLETO
FASE 1: Criar Conta no Replit (2 minutos)
Acesse: https://replit.com

Clique em "Inscrever-se"

Escolha uma opção (Google / GitHub / Email)

Confirme o e-mail, se necessário

FASE 2: Importar o Projeto (3 minutos)
Vá para: https://replit.com/new

Escolha "Importar do GitHub"

Cole a URL do seu repositório, por exemplo:

texto
https://github.com/seu-usuario/bot-defensoria-render
Clique em "Importar"

FASE 3: Configurar Variáveis ​​(5 minutos)
Dentro do Replit:

Clique no ícone de "Segredos" (🔐 cadenciado) na barra esquerda

Adicione cada variável (NÃO use tokens reais em documentação pública):

texto
Nome: PAINEL_PASSWORD
Valor: sua_senha_forte_aqui
texto
Nome: FLASK_SECRET_KEY
Valor: saída do comando: python -c "import secrets; print(secrets.token_hex(32))"
texto
Nome: TELEGRAM_BOT_TOKEN
Valor: token do bot criado no @BotFather
texto
Nome: TELEGRAM_CANAIS
Valor: -1001234567890,-1009876543210   # Exemplo
texto
Nome: TELEGRAM_GRUPOS
Valor: -1009876543210                  # Exemplo
texto
Nome: RSS_FEED_URL
Valor: https://www.promobit.com.br/feed/
texto
Nome: AFFILIATE_TAG_AMAZON
Valor: seu-codigo-20
texto
Nome: AFFILIATE_TAG_OUTROS
Valor: seu-codigo-ml
Clique em “Adicionar Segredo” após cada variável

Importante: nunca coloque um token real em tutoriais, README ou prints públicos.

FASE 4: Executar o Bot (1 minuto)
No Replit, abra o arquivobot_cloud.py

Clique no botão verde "Run" (ou pressione F5)

O bot iniciará e você verá logs semelhantes a:

texto
[2026-01-01 10:30:45] [INFO] Núcleo do Bot ativado em background.
[2026-01-01 10:30:45] [INFO] Ciclo de processamento concluído.
A URL do seu projeto será algo como:

texto
https://seu-projeto.seu-usuario.repl.co
FASE 5: Manter o Bot Rodando 24/7
Por padrão, Replit pausa projetos grátis após um tempo de inatividade.

Opção A: Replit 24/7 (Plano pago)
Bot roda continuamente

Menos necessidade de "keep alive"

Opção B: Uptimerobot (Grátis)
Acesse: https://uptimerobot.com

Crie uma conta grátis

Crie um novo Monitor HTTP(s)

Use uma URL do seu Replit ( https://seu-projeto.seu-usuario.repl.co)

Intervalo: 5 minutos

Nome: "Bot Ofertas"

Isso fará com que sejam feitas requisições periódicas, mantendo o projeto ativo.

FASE 6: Verifique se está funcionando
Testando como:

No Telegram, vá ao canal/grupo configurado

Aguarde o intervalo configurado ou clique em "FORÇAR RASPAGEM" no painel

Você deve ver mensagens como:

texto
🎁 PROMOÇÃO

Título da oferta

🔗 Ver Oferta
Se não chegou nada:

Verifique os logs no Replit

Confirme o token e os IDs dos chats

Verifique se o bot é admin no grupo/canal

⚙️ CONFIGURAÇÕES AVANÇADAS
Mudar a Frequência de Verificação
No painel web, ajuste o campo DELAY DE RASPAGEM (MINUTOS) para o valor desejado (ex.: 30, 60, 120).

Adicionar novos feeds RSS
No momento, o código usa uma única URL ( rss_urlna configuração). Para feeds múltiplos, você pode adaptar a função executar_ciclopara iterar sobre uma lista de URLs.

🔐 Boas Práticas de Segurança
Gere um token novo no @BotFather se suspeitar de vazamento

Nunca exponha valores reais de TELEGRAM_BOT_TOKENREADME, tutoriais ou prints públicos

Use senhas fortes para o painel ( PAINEL_PASSWORD)

Não compartilhe capturas de tela mostrando o painel com dados sensíveis
