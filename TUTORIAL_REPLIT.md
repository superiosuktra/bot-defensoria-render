# 🚀 GUIA COMPLETO - BOT NA NUVEM (REPLIT)

## ⚡ O QUE É REPLIT?

**Replit** é uma plataforma que permite rodar código Python **24/7 na nuvem GRÁTIS!**

- ✅ Sem instalar nada no seu PC
- ✅ Sem usar GitHub Actions
- ✅ Sem limite de tempo
- ✅ Interface super simples
- ✅ Você apenas clica e ativa

---

## 🎯 PASSO A PASSO COMPLETO

### **FASE 1: Criar Conta no Replit (2 minutos)**

1. **Acesse**: https://replit.com
2. **Clique em "Sign up"** (Inscrever-se)
3. **Escolha uma opção**:
   - ✅ Recomendado: Google
   - ✅ Alternativa: GitHub
   - ✅ Email simples
4. **Confirme o email** (se necessário)
5. ✅ Pronto! Você tem uma conta

---

### **FASE 2: Importar o Projeto (3 minutos)**

1. **Vá para**: https://replit.com/new
2. **Escolha "Import from GitHub"**
3. **Cole a URL do seu repositório**:
   ```
   https://github.com/superiosuktra/bot-defensoria-render
   ```
4. **Clique em "Import"**
5. ✅ Seu projeto aparecerá no Replit

---

### **FASE 3: Configurar Variáveis (5 minutos)**

Dentro do Replit:

1. **Clique no ícone de "Secrets"** (🔐 cadeado)
   - Fica na barra esquerda
   
2. **Adicione cada variável**:
   
   ```
   Nome: TELEGRAM_BOT_TOKEN
   Valor: 8976579916:AAFFsWwOWxruQHLhvo39Ik9uhboakAXukNg
   ```
   
   ```
   Nome: TELEGRAM_CANAIS
   Valor: -1001234567890,-1009876543210
   ```
   
   ```
   Nome: TELEGRAM_GRUPOS
   Valor: -1009876543210
   ```
   
   ```
   Nome: RSS_FEED_URL
   Valor: https://www.promobit.com.br/feed/
   ```
   
   ```
   Nome: AFFILIATE_TAG_AMAZON
   Valor: seu-codigo-20
   ```
   
   ```
   Nome: AFFILIATE_TAG_OUTROS
   Valor: seu-codigo-ml
   ```

3. ✅ Clique "Add Secret" após cada um

---

### **FASE 4: Executar o Bot (1 minuto)**

1. **No Replit, procure pelo arquivo**: `bot_cloud.py`
2. **Clique no botão verde "Run"** (ou pressione F5)
3. ✅ O bot começará a rodar!

Você verá logs como:
```
[2024-01-15 10:30:45] [INFO] 🚀 BOT INICIADO - RODANDO 24/7 NA NUVEM!
[2024-01-15 10:30:45] [INFO] ⏳ Aguardando 120 minutos para próxima execução...
```

---

### **FASE 5: Manter o Bot Rodando 24/7 (IMPORTANTE!)**

Por padrão, Replit desativa projetos após 1 hora de inatividade.

**Solução: Use um "keep alive"**

#### Opção A: Usar Replit 24/7 Premium (Pago)
- Custa ~$7/mês
- Bot roda infinitamente
- Mais seguro e confiável

#### Opção B: Usar Uptimer (Grátis) ⭐ Recomendado

1. **Acesse**: https://uptimerobot.com
2. **Sign up** (grátis)
3. **Crie um novo "Monitor"**:
   - Tipo: HTTP(s)
   - URL: `https://seu-replit-url.repl.co`
   - Intervalo: 5 minutos
   - Nome: "Bot Ofertas"
4. **Clique em "Create Monitor"**
5. ✅ Pronto! Ele vai acessar seu bot a cada 5 min (mantendo ativo)

**Como obter a URL do Replit:**
- Seu projeto fica em: `https://[nome-do-seu-projeto].repl.co`
- Clique no botão "Run" → barra superior aparece a URL

---

### **FASE 6: Verificar se Está Funcionando**

**Testando as Ofertas:**

1. **Telegram**: Vá ao seu canal/grupo
2. **Aguarde 5 segundos** após iniciar
3. **Você deve ver**: 
   ```
   🎁 PROMOÇÃO
   
   Título da oferta
   
   🔗 Ver Oferta
   ```

**Se não chegou nada em 1 minuto:**
- Verifique os logs no Replit
- Procure por mensagens de erro (com ❌)
- Verifique se o Token está correto

---

## 📱 ACESSAR SEU SITE

Após o bot rodar pela primeira vez:

**URL do Site:**
```
https://seu-usuario.github.io/bot-defensoria-render/
```

Ele vai mostrar todas as ofertas e cupons!

---

## 🛠️ TROUBLESHOOTING

### ❌ Erro: "Token inválido"
**Solução**: Revogue o token antigo no BotFather e crie um novo

### ❌ Erro: "Chat not found"
**Solução**: Verifique os IDs dos chats (TELEGRAM_CANAIS, TELEGRAM_GRUPOS)

### ❌ Bot parou de funcionar
**Solução**: Replit pausou. Clique no botão "Run" novamente

### ❌ RSS feed não carrega
**Solução**: Teste a URL em seu navegador. Se funcionar, aguarde mais de 1 minuto

### ❌ Não recebe notificações
**Solução**: Verifique se o bot é admin do grupo/canal

---

## 🔄 COMO FAZER ATUALIZAÇÕES

Se quiser mudar algo no código:

1. **No seu GitHub**: Edite o arquivo
2. **No Replit**: Clique em **"Pull"** (sincronizar com GitHub)
3. **Clique em "Run"** novamente
4. ✅ Pronto! Bot atualizado

---

## 📊 MONITORAR O BOT

**Para ver os logs em tempo real:**

1. No Replit, o painel da direita mostra tudo
2. Procure por:
   - ✅ "Ciclo concluído" = funcionando
   - ❌ "Erro" = algo deu errado
   - 🎁 "Nova oferta enviada" = nova promoção

---

## ⚙️ CONFIGURAÇÕES AVANÇADAS

### Mudar Frequência de Verificação

Edite `bot_cloud.py`:

```python
INTERVALO_VERIFICACAO = 120  # Mude este número
```

Valores em **minutos**:
- `60` = a cada 1 hora
- `120` = a cada 2 horas (padrão)
- `30` = a cada 30 minutos
- `1440` = a cada 1 dia

### Adicionar Novo Feed RSS

No `bot_cloud.py`, modifique:

```python
RSS_FEED_URL = os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/")
```

Para múltiplos feeds, edite a função `executar_ciclo()`:

```python
feeds = [
    "https://www.promobit.com.br/feed/",
    "https://www.pelando.com.br/rss",
]

for feed_url in feeds:
    entries = fetch_rss_feed(feed_url)
    # ... processar
```

---

## 🎯 RESUMO RÁPIDO

| Passo | Tempo | O que fazer |
|-------|-------|----------|
| 1 | 2 min | Criar conta Replit |
| 2 | 3 min | Importar projeto GitHub |
| 3 | 5 min | Adicionar Secrets |
| 4 | 1 min | Clicar "Run" |
| 5 | - | (Opcional) Configurar Uptimer |
| 6 | - | ✅ Pronto! Bot rodando! |

---

## 🚀 FLUXO AUTOMÁTICO

```
1️⃣ Bot inicia no Replit
2️⃣ A cada 120 minutos:
   - Busca RSS feed
   - Busca cupons
   - Envia para Telegram
   - Salva no arquivo de controle
   - Atualiza JSON do site
3️⃣ Website atualiza automaticamente
4️⃣ Tudo 24/7, sem você fazer nada!
```

---

## 💡 DICAS IMPORTANTES

✅ **Sempre que iniciar o Replit**, o bot roda automaticamente  
✅ **Não pode fechar a aba** se quiser que continue rodando  
✅ **Use Uptimer** para manter sempre ativo  
✅ **Verifique logs** regularmente para detectar erros  
✅ **Atualize o token** se o anterior vazar  

---

## 📞 SUPORTE RÁPIDO

**Bot não envia mensagens?**
1. Verifique Secrets
2. Teste o token: `https://api.telegram.org/botTOKEN/getMe`
3. Verifique IDs dos chats

**Replit pausou?**
1. Clique "Run" novamente
2. Configure Uptimer para manter ativo

**Código não funciona?**
1. Verifique os logs (lado direito)
2. Procure por ❌ ou ERROR
3. Copie a mensagem de erro

---

**Tudo pronto! Seu bot agora roda 24/7 na nuvem! 🎉**
