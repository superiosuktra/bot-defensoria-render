#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import hashlib
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, redirect, jsonify, session
from functools import wraps

load_dotenv()

# ============================================================================
# CONFIGURAÇÕES FIXAS E FLASK
# ============================================================================

# O Token do Telegram foi removido daqui e agora é dinâmico!
PAINEL_PASSWORD = os.getenv("PAINEL_PASSWORD", "admin123")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "chave_secreta_padrao_123")

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
DADOS_SITE = "dados.json"
CONFIG_FILE = "config.json"
MAX_IDS_HISTORICO = 5000

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Estado Global do Bot
bot_status = {
    "status": "Iniciando...",
    "is_paused": False,
    "force_run": False,
    "ultima_execucao": "N/A",
    "ofertas_enviadas_hoje": 0,
}

app_logs = []
time_since_last_run = 0

# ============================================================================
# GERENCIADOR DE CONFIGURAÇÃO (Agora Multicanais)
# ============================================================================

def load_dynamic_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    # Configuração Padrão inicial
    default_config = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""), # Migra o token antigo se existir
        "destinos_telegram": os.getenv("TELEGRAM_CANAIS", "") + "," + os.getenv("TELEGRAM_GRUPOS", ""),
        "amazon_tag": os.getenv("AFFILIATE_TAG_AMAZON", ""),
        "mercado_livre_tag": os.getenv("AFFILIATE_TAG_OUTROS", ""),
        "rss_url": os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/"),
        "intervalo": 120,
        "blacklist": "internacional, usado, reembalado",
        "whitelist": ""
    }
    save_dynamic_config(default_config)
    return default_config

def save_dynamic_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)

# ============================================================================
# FUNÇÕES DO BOT E REGRAS DE NEGÓCIO
# ============================================================================

def log_message(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_str = f"[{timestamp}] [{level}] {message}"
    print(log_str)
    
    app_logs.append(log_str)
    if len(app_logs) > 100:
        app_logs.pop(0)

def safe_tg_html(text: str) -> str:
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def pass_filters(titulo: str, config: dict) -> bool:
    t_lower = titulo.lower()
    
    blacklist = [w.strip().lower() for w in config.get("blacklist", "").split(",") if w.strip()]
    if any(b in t_lower for b in blacklist):
        log_message(f"Ignorada pela Blacklist: {titulo}", "INFO")
        return False
        
    whitelist = [w.strip().lower() for w in config.get("whitelist", "").split(",") if w.strip()]
    if whitelist and not any(w in t_lower for w in whitelist):
        log_message(f"Ignorada pela Whitelist: {titulo}", "INFO")
        return False
        
    return True

def load_posted_ids(filename: str) -> list:
    if not os.path.exists(filename): return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(ids))
    except Exception: return []

def save_posted_ids(ids: list, filename: str):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for item_id in ids[-MAX_IDS_HISTORICO:]:
                f.write(f"{item_id}\n")
    except Exception: pass

def generate_unique_id(text: str, url: str) -> str:
    return hashlib.sha256(f"{text.strip()}|{url.strip()}".lower().encode("utf-8")).hexdigest()[:16]

def convert_to_affiliate_link(url: str, config: dict) -> str:
    if not url or not isinstance(url, str): return url
    try:
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower()

        if any(hostname == d or hostname.endswith(f".{d}") for d in ["amazon.com.br", "amazon.com"]):
            if config.get("amazon_tag"):
                q = parse_qs(parsed.query)
                q["tag"] = [config["amazon_tag"]]
                return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

        elif any(hostname == d or hostname.endswith(f".{d}") for d in ["mercadolivre.com.br", "mercadolivre.com"]):
            if config.get("mercado_livre_tag"):
                q = parse_qs(parsed.query)
                q["utm_source"] = [config["mercado_livre_tag"]]
                return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

        return url
    except Exception: return url

def send_telegram_message(text_html: str, config: dict) -> tuple:
    # LÊ O TOKEN DIRETAMENTE DA CONFIGURAÇÃO DINÂMICA
    bot_token = config.get("telegram_token", "").strip()
    raw_destinos = config.get("destinos_telegram", "")
    chat_ids = list(dict.fromkeys([d.strip() for d in raw_destinos.split(",") if d.strip()]))
    
    if not bot_token:
        log_message("Token do Telegram não configurado no painel.", "WARN")
        return (0, 0)
        
    if not chat_ids:
        return (0, 0)
        
    enviados, falhas = 0, 0
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for chat_id in chat_ids:
        try:
            payload = {"chat_id": chat_id, "text": text_html, "parse_mode": "HTML"}
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                enviados += 1
            elif resp.status_code == 429:
                time.sleep(resp.json().get("parameters", {}).get("retry_after", 5))
                requests.post(url, json=payload, timeout=15)
            else:
                falhas += 1
                log_message(f"Falha Telegram ({chat_id}): {resp.text}", "ERROR")
            time.sleep(1)
        except Exception as e:
            log_message(f"Erro Telegram: {e}", "ERROR")
            falhas += 1
    return (enviados, falhas)

def executar_ciclo(config):
    bot_status["status"] = "Buscando ofertas..."
    log_message("=== Iniciando raspagem de ofertas ===")
    
    posted_ids = load_posted_ids(POSTED_FILE)
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(config.get("rss_url", ""), headers=headers, timeout=15)
        feed = feedparser.parse(resp.content)
        
        for entry in reversed(feed.entries):
            raw_title = entry.get("title", "Oferta")
            link = entry.get("link", "").strip()
            entry_id = entry.get("id") or link
            unique_id = generate_unique_id(raw_title, entry_id)

            if unique_id not in posted_ids and link.startswith("http"):
                if not pass_filters(raw_title, config):
                    posted_ids.append(unique_id)
                    continue

                affiliate_link = convert_to_affiliate_link(link, config)
                msg = f"🎁 <b>PROMOÇÃO</b>\n\n<b>{safe_tg_html(raw_title)}</b>\n\n🔗 <a href='{affiliate_link}'>Ver Oferta</a>"
                
                env, _ = send_telegram_message(msg, config)
                if env > 0:
                    posted_ids.append(unique_id)
                    bot_status["ofertas_enviadas_hoje"] += 1
                    log_message(f"Enviada: {raw_title}")
                    
    except Exception as e:
        log_message(f"Erro no ciclo: {e}", "ERROR")

    save_posted_ids(posted_ids, POSTED_FILE)
    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = "Ocioso (Aguardando)"
    log_message("=== Fim do ciclo ===")

def loop_principal():
    global time_since_last_run
    log_message("Bot iniciado em background.")
    
    while True:
        config = load_dynamic_config()
        intervalo_segundos = int(config.get("intervalo", 120)) * 60
        
        if bot_status["force_run"]:
            bot_status["force_run"] = False
            if not bot_status["is_paused"]:
                executar_ciclo(config)
                time_since_last_run = 0
                
        elif not bot_status["is_paused"]:
            if time_since_last_run >= intervalo_segundos:
                executar_ciclo(config)
                time_since_last_run = 0
                
        time.sleep(1)
        
        if not bot_status["is_paused"]:
            time_since_last_run += 1

# ============================================================================
# TEMPLATES HTML
# ============================================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - Mega Deals Console</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex align-items-center justify-content-center" style="height: 100vh;">
    <div class="card p-4 shadow" style="width: 350px;">
        <h3 class="text-center mb-4">🔐 Login</h3>
        {% if erro %}<div class="alert alert-danger">{{ erro }}</div>{% endif %}
        <form method="POST">
            <input type="password" name="senha" class="form-control mb-3" placeholder="Senha de Acesso" required>
            <button class="btn btn-primary w-100" type="submit">Entrar</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Painel de Controle</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .terminal { background-color: #1e1e1e; color: #00ff00; font-family: monospace; height: 350px; overflow-y: auto; padding: 10px; border-radius: 5px; }
        .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
</head>
<body class="bg-light pb-5">
    <nav class="navbar navbar-dark bg-dark mb-4">
        <div class="container">
            <a class="navbar-brand" href="#">🤖 Mega Deals Bot Console</a>
            <a href="/logout" class="btn btn-sm btn-outline-light">Sair</a>
        </div>
    </nav>

    <div class="container">
        <div class="row">
            <!-- COLUNA ESQUERDA: CONTROLES E TERMINAL -->
            <div class="col-md-7">
                
                <div class="card">
                    <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                        Controles de Execução
                        <span id="badge-status" class="badge bg-light text-dark">Carregando...</span>
                    </div>
                    <div class="card-body text-center">
                        <p>Última execução: <strong id="lbl-ultima">--</strong> | Ofertas enviadas hoje: <strong id="lbl-ofertas">--</strong></p>
                        <form action="/action/control" method="POST" class="d-inline">
                            <button name="action" value="toggle_pause" class="btn btn-warning me-2" id="btn-pause">Pausar Bot</button>
                            <button name="action" value="force_run" class="btn btn-danger">▶️ Forçar Raspagem Agora</button>
                        </form>
                    </div>
                </div>

                <div class="card bg-dark">
                    <div class="card-header text-white border-secondary">Terminal de Logs (Ao Vivo)</div>
                    <div class="card-body p-0">
                        <div id="terminal" class="terminal">Carregando logs...</div>
                    </div>
                </div>
            </div>

            <!-- COLUNA DIREITA: CONFIGURAÇÕES -->
            <div class="col-md-5">
                <div class="card">
                    <div class="card-header bg-success text-white">⚙️ Configurações Dinâmicas</div>
                    <div class="card-body">
                        <form action="/update_config" method="POST">
                            
                            <h6 class="border-bottom pb-2 text-primary">Plataformas & APIs</h6>
                            <div class="mb-2">
                                <label class="form-label small fw-bold">Token do Bot (Telegram)</label>
                                <input type="password" class="form-control form-control-sm" name="telegram_token" value="{{ config.telegram_token }}" placeholder="Insira o Token do BotFather">
                            </div>
                            <div class="mb-3">
                                <label class="form-label small fw-bold">IDs de Destino (Telegram)</label>
                                <input type="text" class="form-control form-control-sm" name="destinos_telegram" value="{{ config.destinos_telegram }}" placeholder="-100..., -100...">
                                <small class="text-muted" style="font-size: 0.75rem;">Separe múltiplos IDs por vírgula</small>
                            </div>

                            <h6 class="border-bottom pb-2 mt-4 text-primary">Frequência</h6>
                            <div class="mb-3 d-flex align-items-center">
                                <label class="form-label small me-2 mb-0 fw-bold">Intervalo de Busca (Minutos):</label>
                                <input type="number" class="form-control form-control-sm w-25" name="intervalo" value="{{ config.intervalo }}">
                            </div>

                            <h6 class="border-bottom pb-2 mt-4 text-primary">Tags de Afiliado</h6>
                            <div class="mb-2">
                                <label class="form-label small fw-bold">Amazon (Tag)</label>
                                <input type="text" class="form-control form-control-sm" name="amazon_tag" value="{{ config.amazon_tag }}">
                            </div>
                            <div class="mb-3">
                                <label class="form-label small fw-bold">Mercado Livre (UTM Source)</label>
                                <input type="text" class="form-control form-control-sm" name="mercado_livre_tag" value="{{ config.mercado_livre_tag }}">
                            </div>

                            <h6 class="border-bottom pb-2 mt-4 text-primary">Filtros Inteligentes</h6>
                            <div class="mb-2">
                                <label class="form-label small text-danger fw-bold">Blacklist (Ignorar ofertas com:)</label>
                                <input type="text" class="form-control form-control-sm" name="blacklist" value="{{ config.blacklist }}" placeholder="ex: usado, internacional">
                            </div>
                            <div class="mb-4">
                                <label class="form-label small text-success fw-bold">Whitelist (Obrigatório conter:)</label>
                                <input type="text" class="form-control form-control-sm" name="whitelist" value="{{ config.whitelist }}" placeholder="Deixe em branco para desativar">
                            </div>

                            <button type="submit" class="btn btn-success w-100">💾 Salvar Configurações</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- SCRIPT DE ATUALIZAÇÃO EM TEMPO REAL -->
    <script>
        function fetchStatus() {
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('lbl-ultima').innerText = data.status.ultima_execucao;
                    document.getElementById('lbl-ofertas').innerText = data.status.ofertas_enviadas_hoje;
                    
                    const btnPause = document.getElementById('btn-pause');
                    if(data.status.is_paused) {
                        btnPause.innerText = "▶ Retomar Bot";
                        btnPause.classList.replace('btn-warning', 'btn-success');
                        document.getElementById('badge-status').innerText = "PAUSADO";
                        document.getElementById('badge-status').className = "badge bg-warning text-dark";
                    } else {
                        btnPause.innerText = "⏸ Pausar Bot";
                        btnPause.classList.replace('btn-success', 'btn-warning');
                        document.getElementById('badge-status').innerText = data.status.status;
                        document.getElementById('badge-status').className = "badge bg-info text-dark";
                    }

                    const term = document.getElementById('terminal');
                    const isScrolledToBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 1;
                    
                    term.innerHTML = data.logs.join('<br>');
                    
                    if(isScrolledToBottom) {
                        term.scrollTop = term.scrollHeight;
                    }
                });
        }
        setInterval(fetchStatus, 2000);
        fetchStatus();
    </script>
</body>
</html>
"""

# ============================================================================
# ROTAS DO FLASK
# ============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("senha") == PAINEL_PASSWORD:
            session['logged_in'] = True
            log_message("Login efetuado no painel.")
            return redirect("/")
        else:
            return render_template_string(LOGIN_HTML, erro="Senha incorreta.")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect("/login")

@app.route("/")
@login_required
def index():
    config = load_dynamic_config()
    return render_template_string(DASHBOARD_HTML, config=config)

@app.route("/api/data")
@login_required
def api_data():
    return jsonify({
        "status": bot_status,
        "logs": app_logs
    })

@app.route("/update_config", methods=["POST"])
@login_required
def update_config():
    novo_config = {
        "telegram_token": request.form.get("telegram_token", "").strip(),
        "destinos_telegram": request.form.get("destinos_telegram", "").strip(),
        "intervalo": int(request.form.get("intervalo", 120)),
        "amazon_tag": request.form.get("amazon_tag", "").strip(),
        "mercado_livre_tag": request.form.get("mercado_livre_tag", "").strip(),
        "blacklist": request.form.get("blacklist", "").strip(),
        "whitelist": request.form.get("whitelist", "").strip()
    }
    
    atual = load_dynamic_config()
    novo_config["rss_url"] = atual.get("rss_url", "")
    
    save_dynamic_config(novo_config)
    log_message("Configurações atualizadas via painel.")
    return redirect("/")

@app.route("/action/control", methods=["POST"])
@login_required
def bot_control():
    action = request.form.get("action")
    if action == "toggle_pause":
        bot_status["is_paused"] = not bot_status["is_paused"]
        estado = "PAUSADO" if bot_status["is_paused"] else "RETOMADO"
        log_message(f"Sistema {estado} manualmente.")
    elif action == "force_run":
        bot_status["force_run"] = True
        log_message("Raspagem forçada pelo usuário.")
        
    return redirect("/")

@app.route("/health")
def health():
    return jsonify({"status": "online", "bot_paused": bot_status["is_paused"]})

if __name__ == "__main__":
    thread_bot = threading.Thread(target=loop_principal, daemon=True)
    thread_bot.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
