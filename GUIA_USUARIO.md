# 📊 Guia de Atualização - Mega Deals Bot v2.0

## ✨ O que mudou?

Sua interface e bot agora têm muito mais funcionalidades! Aqui está um resumo visual:

### 🎨 Interface - Antes vs Depois

#### ANTES (v1.0)
```
┌─────────────────────────────────┐
│ Login // Mega Deals             │
├─────────────────────────────────┤
│                                 │
│ Senha: [_____________]          │
│ [Entrar]                        │
│                                 │
└─────────────────────────────────┘

Dashboard simples com:
- Status básico
- Logs
- Configurações em um único formulário
```

#### DEPOIS (v2.0)
```
┌──────────────────────────────────────────────────────────┐
│ ⚡ Mega Deals // Console             [Relógio] [Sair]  │
├──────────────────────────────────────────────────────────┤
│
│ ┌────────────┬────────────┬────────────┬────────────┐
│ │ ❤️ Status   │ 🎁 Ofertas │ ⏰ Execução │ 📡 Fontes  │
│ │  Ativo     │  42 hoje   │  2h atrás  │  6 ativas  │
│ └────────────┴────────────┴────────────┴────────────┘
│
│ [⏸️ Pausar] [▶️ Executar] [🗑️ Limpar]
│
│ ├─ 📋 Básico  ├─ 📡 Fontes  ├─ 🔍 Filtros  ├─ 🔗 Afiliados
│ │ Token       │ ✓ Promobit  │ Blacklist     │ Amazon Tag
│ │ Destinos    │ ✓ Amazon    │ Whitelist     │ UTM ML
│ │ Intervalo   │ ✓ ML        │ Preço Min/Max │
│ │ Desconto    │ ✓ Kabum     │ Desconto Min  │
│ │             │ ✓ Terabyte  │               │
│ │             │ ✓ Shopee    │               │
│
│ 📊 Logs em tempo real
│ [12:34:56] [INFO] Ciclo concluído...
│ [12:35:02] [INFO] Oferta enviada...
```

---

## 🎯 Novas Funcionalidades

### 1️⃣ **Múltiplas Fontes de Desconto**

Agora você pode buscar descontos em:
- 🔥 **Promobit** - Grandes promoções
- 🛒 **Mercado Livre** - Marketplace
- 📦 **Amazon** - E-commerce
- 🎮 **Kabum** - Eletrônicos e games
- 💻 **Terabyte Shop** - Componentes
- 🛍️ **Shopee** - Produtos variados

**Como usar:**
1. Clique na aba "📡 Fontes RSS"
2. Marque as lojas que deseja acompanhar
3. Clique em "Salvar Fontes"

### 2️⃣ **Filtros Avançados**

Customize sua busca com:

```
Blacklist (Excluir)
┌─────────────────────────────────────┐
│ internacional, usado, reembalado... │  ← Evita esses produtos
└─────────────────────────────────────┘

Whitelist (Obrigatório)
┌─────────────────────────────────────┐
│ PlayStation, Xbox, Nintendo...      │  ← Só esses produtos
└─────────────────────────────────────┘

Preço
┌──────────┐     ┌──────────┐
│ Mín: 50  │ até │ Máx: 500 │  (em R$)
└──────────┘     └──────────┘

Desconto
┌──────────┐
│ Mín: 20% │  ← Apenas ofertas com 20% off ou mais
└──────────┘
```

### 3️⃣ **Limpeza de Histórico**

Novo botão [🗑️ Limpar Histórico] para:
- Resetar ofertas já enviadas
- Reenviar ofertas antigas com novas configurações
- Recomeçar do zero

### 4️⃣ **Painel Mais Visual**

- ✅ Cards com gradientes modernos
- ✅ Ícones visuais (Font Awesome)
- ✅ Cores consistentes
- ✅ Animações suaves
- ✅ Responsive (funciona em mobile!)
- ✅ Relógio em tempo real

---

## 🚀 Primeiros Passos

### Passo 1: Configurações Básicas
1. Acesse o painel
2. Clique em "📋 Básico"
3. Preencha:
   - Token Telegram
   - IDs dos chats/canais
   - Intervalo (minutos)
   - Desconto mínimo desejado

### Passo 2: Escolha as Fontes
1. Clique em "📡 Fontes RSS"
2. Marque as lojas que deseja:
   ```
   ☑️ Promobit
   ☑️ Mercado Livre
   ☑️ Amazon
   ```
3. Salve

### Passo 3: Configure Filtros
1. Clique em "🔍 Filtros"
2. Blacklist: `internacional, usado, danificado`
3. Preço: R$ 100 a R$ 5000
4. Salve

### Passo 4: Configure Afiliados (Opcional)
1. Clique em "🔗 Afiliados"
2. Cole seu código Amazon
3. Cole seu UTM do ML
4. Salve para ganhar comissões! 💰

### Passo 5: Teste
1. Clique em "▶️ Executar Agora"
2. Verifique os logs abaixo
3. Confira as mensagens no Telegram

---

## 📋 Exemplos de Uso

### 🎮 Exemplo 1: Buscar Ofertas de Games
```
Fontes: Kabum, Terabyte, Amazon
Whitelist: PS5, Xbox, Nintendo Switch, Steam
Blacklist: importado, danificado
Preço: R$ 50 - R$ 3000
Desconto: 15% mínimo
```

### 📱 Exemplo 2: Acompanhar Smartphones
```
Fontes: Mercado Livre, Amazon, Shopee
Whitelist: iPhone, Samsung, Xiaomi, Google Pixel
Blacklist: usado, desbloqueado, internacional
Preço: R$ 500 - R$ 5000
Desconto: 10% mínimo
```

### 🏠 Exemplo 3: Eletrônicos para Casa
```
Fontes: Promobit, Amazon, Mercado Livre
Whitelist: geladeira, fogão, micro-ondas, ar condicionado
Blacklist: usado, restituído, pequeno dano
Preço: R$ 1000 - R$ 10000
Desconto: 20% mínimo
```

---

## 🎨 Estrutura do Dashboard

```
┌─ Dashboard Principal
│  ├─ 4 Cards de Estatísticas
│  │  ├─ Status (Ativo/Pausado)
│  │  ├─ Ofertas Enviadas Hoje
│  │  ├─ Última Execução
│  │  └─ Fontes RSS Ativas
│  │
│  ├─ Controles Rápidos
│  │  ├─ ⏸️ Pausar/Iniciar
│  │  ├─ ▶️ Executar Agora
│  │  └─ 🗑️ Limpar Histórico
│  │
│  ├─ Sistema de Abas
│  │  ├─ Tab 1: 📋 Configurações Básicas
│  │  ├─ Tab 2: 📡 Fontes RSS
│  │  ├─ Tab 3: 🔍 Filtros Avançados
│  │  └─ Tab 4: 🔗 Programa de Afiliados
│  │
│  └─ Logs em Tempo Real
│     └─ Atualiza a cada 3 segundos
```

---

## 🔧 Para Desenvolvedores

### Novas Variáveis de Config (config.json)
```json
{
  "desconto_minimo": 10,         // Novo! Desconto mínimo %
  "preco_minimo": 0,             // Novo! Preço mínimo R$
  "preco_maximo": 99999,         // Novo! Preço máximo R$
  "sources": "promobit,amazon"   // Novo! Fontes selecionadas
}
```

### Novas Rotas Flask
- `POST /update_sources` - Salvar fontes RSS
- `POST /update_filters` - Salvar filtros avançados
- `POST /action/control?action=clear_history` - Limpar histórico

### Função Nova
```python
def get_rss_urls(config):
    """Retorna lista de URLs RSS baseado nas fontes selecionadas"""
    # Mapeia strings para URLs reais
```

---

## ⚠️ Pontos Importantes

1. **Compatibilidade**: 100% compatível com versão anterior
2. **Sem Novos Requisitos**: Nenhuma nova biblioteca necessária
3. **Dados Preservados**: Seu config.json atual funciona normalmente
4. **Auto-atualização**: Novos campos são adicionados automaticamente

---

## 🚀 Como Fazer Deploy (Render/Railway)

1. Faça commit das mudanças:
```bash
git add bot_cloud.py MELHORIAS.md
git commit -m "feat: interface redesenhada e múltiplas fontes RSS"
git push
```

2. A plataforma (Render/Railway) fará redeploy automaticamente
3. Pronto! Acesse seu painel com o novo design

---

## 💡 Dicas

- 📌 Comece com poucas fontes e filtros, adicione conforme necessário
- 📌 Use whitelist quando quiser ser mais específico
- 📌 Ajuste o intervalo baseado em quantos emails/mensagens recebe
- 📌 Teste os filtros com "Executar Agora" antes de deixar automático
- 📌 Coloque códigos afiliados para ganhar comissões!

---

## 🆘 Dúvidas Frequentes

**P: Posso usar múltiplas fontes?**
R: Sim! Marque quantas quiser na aba "Fontes RSS".

**P: Qual é a diferença entre Blacklist e Whitelist?**
R: 
- Blacklist: Exclui produtos com essas palavras
- Whitelist: Só inclui produtos com essas palavras

**P: Como ganho comissões?**
R: Configure seus códigos de afiliado na aba "Afiliados".

**P: Posso alterar a senha do painel?**
R: Simples! Logout e login novamente, aparecerá opção de redefinir.

---

**Divirta-se explorando as novas funcionalidades! 🎉**
