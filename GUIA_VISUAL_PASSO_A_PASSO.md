# 🎬 Guia Visual Passo a Passo

## 📺 Tela 1: Login

```
┌────────────────────────────────────────────┐
│                                            │
│            ⚡ Mega Deals                    │
│        Painel de Controle                  │
│                                            │
│  Senha: [_____________________]            │
│                                            │
│  [Entrar]                                  │
│                                            │
└────────────────────────────────────────────┘

Ações:
1. Insira sua senha
2. Clique "Entrar"
3. Próximo: Dashboard
```

---

## 📺 Tela 2: Dashboard Principal

```
┌─────────────────────────────────────────────────────┐
│ ⚡ Mega Deals // Console    [12:34:56] [Sair]      │
├─────────────────────────────────────────────────────┤

┌──────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐
│ ❤️ Status │ │ 🎁 Hoje │ │ ⏰ Exec │ │ 📡 Font │
│ Ativo ✓   │ │  42    │ │ 2h atrás│ │  6    │
└──────────┘ └─────────┘ └────────┘ └─────────┘

[⏸️ Pausar] [▶️ Executar] [🗑️ Limpar]

Configurações
├─ 📋 │ 📡 │ 🔍 │ 🔗
│Básico│Font│Filt│Afil

Logs
┌──────────────────────────────┐
│ [12:34:56] ✓ Ciclo iniciado  │
│ [12:35:02] ✓ Oferta enviada  │
│ [12:36:00] ✓ Ciclo concluído │
└──────────────────────────────┘

Ações Disponíveis:
1. Ver status do bot
2. Clicar em uma ABA para configurar
3. Usar botões de controle rápido
4. Monitorar logs em tempo real
```

---

## 📺 Configuração 1️⃣: Básico

```
┌──────────────────────────────────────────┐
│ 📋 CONFIGURAÇÕES BÁSICAS                  │
├──────────────────────────────────────────┤

🔑 BOT TOKEN (Telegram)
[________________________________]
 Exemplo: 8976579916:AAHDKgqm...

👥 DESTINOS
[________________________________]
 Exemplo: -4302126760, 123456789

⏱️ INTERVALO (minutos)
[120]

📊 DESCONTO MÍNIMO (%)
[10]

[💾 Salvar Configurações]
└──────────────────────────────────────────┘

Guia:
1. Coloque seu token do BotFather
2. Adicione IDs de grupos/canais (separados por vírgula)
3. Defina intervalo em minutos (120 = 2 horas)
4. Desconto mínimo desejado (10 = só ofertas com 10%+ off)
5. Clique Salvar
```

---

## 📺 Configuração 2️⃣: Fontes RSS

```
┌──────────────────────────────────────────┐
│ 📡 SELECIONE FONTES DE DESCONTO           │
├──────────────────────────────────────────┤

Marque as fontes que deseja:

☑️ Promobit
   Promoções gerais

☑️ Mercado Livre
   Marketplace

☑️ Amazon
   E-commerce

☑️ Kabum
   Eletrônicos e games

☑️ Terabyte Shop
   Componentes e periféricos

☐ Shopee
   Produtos variados

🔗 RSS URL Customizada
[________________________________]
 (Deixe em branco para usar as acima)

[💾 Salvar Fontes]
└──────────────────────────────────────────┘

Dicas:
1. Marque pelo menos 1 fonte
2. Múltiplas fontes = mais ofertas
3. Menos fontes = menos emails
4. URL customizada substitui seleção acima
```

---

## 📺 Configuração 3️⃣: Filtros Avançados

```
┌──────────────────────────────────────────┐
│ 🔍 FILTROS AVANÇADOS                      │
├──────────────────────────────────────────┤

❌ BLACKLIST (Evitar)
[________________________________]
 Exemplo: internacional, usado, quebrado

 Separe por vírgula. Ofertas com essas
 palavras serão ignoradas.

✅ WHITELIST (Obrigatório)
[________________________________]
 Exemplo: PlayStation, Xbox, Nintendo

 Separe por vírgula. Se preenchido, apenas
 ofertas com essas palavras serão enviadas.

💰 PREÇO MÍNIMO
[0] R$

💰 PREÇO MÁXIMO  
[99999] R$

[💾 Salvar Filtros]
└──────────────────────────────────────────┘

Exemplos:
• Buscar PS5: Whitelist "PlayStation 5, PS5"
• Evitar importado: Blacklist "importado, internacional"
• Preço: Min 1000, Max 5000
```

---

## 📺 Configuração 4️⃣: Afiliados

```
┌──────────────────────────────────────────┐
│ 🔗 PROGRAMA DE AFILIADOS                  │
├──────────────────────────────────────────┤

☕ CÓDIGO AFILIADO AMAZON
[________________________________]
 Exemplo: seu-codigo-afiliado-01

 Se preenchido, links Amazon terão seu
 código de afiliado (você ganha comissão!)

📊 UTM DO MERCADO LIVRE
[________________________________]
 Exemplo: seu-utm-ml

 Se preenchido, links ML serão rastreados
 com seu UTM para analytics

[💾 Salvar Afiliados]
└──────────────────────────────────────────┘

Como funciona:
1. Configure seu código de afiliado Amazon
2. Configure seu UTM do Mercado Livre
3. Quando ofertas forem enviadas, terão seus códigos
4. Você ganha comissão de cada clique!
```

---

## 🎯 Cenários de Uso

### Cenário 1: Iniciante
```
Passo 1: Aba "Básico"
- Token: seu_token_aqui
- Destinos: seu_id_aqui
- Intervalo: 120 (2h)
- Desconto: 10%

Passo 2: Aba "Fontes"
- Marcar: Promobit
- Clicar Salvar

Passo 3: Aba "Filtros"
- Deixar em branco (sem filtros)
- Clicar Salvar

Passo 4: Dashboard
- Clique "▶️ Executar Agora"
- Aguarde 30 segundos
- Verifique logs abaixo
- Confira Telegram
```

### Cenário 2: Foco em Eletrônicos
```
Passo 1: Básico
- Token, Destinos, Intervalo, Desconto

Passo 2: Fontes RSS
☑ Kabum
☑ Terabyte
☑ Amazon
☑ Mercado Livre

Passo 3: Filtros Avançados
- Whitelist: "monitor, processador, placa mãe"
- Blacklist: "internacional, usado"
- Preço Min: 500
- Preço Max: 5000

Passo 4: Executar!
```

### Cenário 3: Ganhar Comissões
```
Passo 1: Afiliados
- Amazon Tag: seu-codigo
- UTM ML: seu-utm

Passo 2: Fontes
☑ Amazon
☑ Mercado Livre
☑ Shopee

Passo 3: Filtros
- Whitelist: "iPhone, Samsung, Xiaomi"
- Preço: 500 - 3000

Passo 4: Executar e ganhar! 💰
```

---

## 🎮 Controles Rápidos

### Botão: ⏸️ Pausar/Iniciar
```
Função: Pausa o bot automaticamente
Uso: Quando não quer receber ofertas
Depois clique novamente para retomar
```

### Botão: ▶️ Executar Agora
```
Função: Força uma busca imediata
Uso: Testar configurações
Resultado aparece nos logs abaixo
```

### Botão: 🗑️ Limpar Histórico
```
Função: Remove todas as ofertas já enviadas
Uso: Resetar para receber ofertas antigas
Cuidado: Irá reenviar TODAS as ofertas!
```

---

## 📊 Lendo os Logs

```
[12:34:56] ✓ [INFO] Ciclo iniciado
└─ Significa: Busca começou

[12:34:57] ✓ [INFO] Feed encontrado com 50 entradas
└─ Significa: Conectou à fonte e encontrou 50 ofertas

[12:35:02] ✓ [INFO] Oferta enviada: Samsung 55"
└─ Significa: Uma oferta foi enviada para o Telegram

[12:35:15] ⚠️ [WARN] Bloqueado pela blacklist: iPhone usado
└─ Significa: Oferta foi filtrada pela blacklist

[12:35:30] ✗ [ERRO] Falha ao buscar RSS
└─ Significa: Erro na conexão, verifique internet

[12:36:00] ✓ [INFO] Ciclo concluído. Enviadas: 5
└─ Significa: Ciclo terminou, 5 ofertas enviadas
```

---

## ⏱️ Cronograma de Execução

```
Intervalo = 120 minutos (2 horas)

12:00 - Execução 1
12:05 - Ofertas começam a chegar
12:15 - Ofertas chegam mais devagar
12:30 - Ofertas esgotadas

14:00 - Execução 2 (próximo ciclo)
14:05 - Novas ofertas chegam!
```

---

## 🚨 Solução de Problemas

### Problema: Login não funciona
```
Solução:
1. Verificar se digita a senha corretamente
2. Primeira vez? Use logout e tente novamente
3. Senha é case-sensitive
```

### Problema: Ofertas não chegam
```
Solução:
1. Clicar "▶️ Executar Agora" para testar
2. Verificar Token do Telegram
3. Verificar IDs de destino
4. Verificar logs para erros
5. Checar se Bot é admin no grupo
```

### Problema: Muitas/poucas ofertas
```
Solução:
1. Aumentar/diminuir Desconto Mínimo
2. Usar Whitelist para filtrar por tipo
3. Adicionar/remover fontes RSS
4. Usar Filtro de Preço
```

### Problema: Interface quebrada
```
Solução:
1. Limpar cache: Ctrl+Shift+Delete
2. Recarregar página: F5
3. Tentar outro navegador
4. Verificar se mobile (responsivo)?
```

---

## ✅ Checklist: Tudo Pronto?

Antes de usar, verifique:
- [ ] Token do Telegram obtido
- [ ] ID do chat/canal coletado
- [ ] Pelo menos 1 fonte selecionada
- [ ] Intervalo configurado
- [ ] Clicou "Salvar" em cada aba
- [ ] "▶️ Executar Agora" testado
- [ ] Ofertas chegam no Telegram
- [ ] Logs mostram sucesso

---

## 🎉 Resultado Esperado

Após seguir todos os passos:

1. **No Telegram** 📱
   - Mensagens com ofertas chegam
   - Links são clicáveis
   - Imagens aparecem (se RSS tem)

2. **No Painel** 🎛️
   - Status mostra "Ativo"
   - Contador de ofertas aumenta
   - Logs mostram "Ciclo concluído"

3. **Automático** 🤖
   - Ofertas chegam periodicamente
   - Sem precisar fazer nada
   - Ganhar dinheiro com afiliados!

---

**Parabéns! Você agora entende como usar a nova interface!** 🎉

Próximo passo: Comece a ganhar dinheiro com suas ofertas! 💰
