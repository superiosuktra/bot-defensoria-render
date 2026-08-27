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
from flask import Flask, request, render_template_string, redirect, jsonify

load_dotenv()

# ============================================================================
# CONFIGURAÇÕES FIXAS E FLASK
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CANAIS = [c.strip() for c in os.getenv("TELEGRAM_CANAIS", "").split(",") if c.strip()]
TELEGRAM_GRUPOS = [g.strip() for g in os.getenv("TELEGRAM_GRUPOS", "").split(",") if g.strip()]
TODOS_DESTINOS = list(dict.fromkeys(TELEGRAM_CANAIS + TELEGRAM_GRUPOS))

RSS_FEED_URL = os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/").strip()
INTERVALO_VERIFICACAO = int(os.getenv("INTERVALO_VERIFICACAO", "120"))

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
DADOS_SITE = "dados.json"
CONFIG_FILE = "config.json"
MAX_IDS_HISTORICO = 5000

app = Flask(__name__)

# Status Global do Bot para o Dashboard
bot_status = {
    "status": "Iniciando...",
    "ultima_execucao": "N/A",
    "ofertas_enviadas_hoje": 0,
    "erros_recentes": []
}

# ============================================================================
# GERENCIADOR DE CONFIGURAÇÃO DINÂMICA (AFILIADOS)
# ============================================================================

def load_dynamic_config():
    """Carrega as tags de afiliado do JSON. Se não existir, usa as do .env como fallback inicial."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    # Configuração padrão (Fallback)
    default_config = {
        "amazon_tag": os.getenv("AFFILIATE_TAG_AMAZON", ""),
        "mercado_livre_tag": os.getenv("AFFILIATE_TAG_OUTROS", "")
    }
    save_dynamic_config(default_config)
    return default_config

def save_dynamic_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)

# ============================================================================
# FUNÇÕES DO BOT (Lógica de Extração e Envio)
# ============================================================================

def log_message(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_str = f"[{timestamp}] [{level}] {message}"
    print(log_str)
    
    if level == "ERROR":
        bot_status["erros_recentes"].insert(0, log_str)
        bot_status["erros_recentes"] = bot_status["erros_recentes"][:5]

def safe_tg_html(text: str) -> str:
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def load_posted_ids(filename: str) -> list:
    if not os.path.exists(filename): return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(ids))
    except Exception: return []

def save_posted_ids(ids: list, filename: str):
    try:
        trimmed_ids = ids[-MAX_IDS_HISTORICO:]
        with open(filename, "w", encoding="utf-8") as f:
            for item_id in trimmed_ids:
                f.write(f"{item_id}\n")
    except Exception: pass

def generate_unique_id(text: str, url: str) -> str:
    combined = f"{text.strip()}|{url.strip()}".lower()
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

def convert_to_affiliate_link(url: str, config: dict) -> str:
    if not url or not isinstance(url, str): return url
    try:
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower()

        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in ["amazon.com.br", "amazon.com"]):
            if config.get("amazon_tag"):
                query_params = parse_qs(parsed.query)
                query_params["tag"] = [config["amazon_tag"]]
                return urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))

        elif any(hostname == domain or hostname.endswith(f".{domain}") for domain in ["mercadolivre.com.br", "mercadolivre.com"]):
            if config.get("mercado_livre_tag"):
                query_params = parse_qs(parsed.query)
                query_params["utm_source"] = [config["mercado_livre_tag"]]
                return urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))

        return url
    except Exception: return url

def send_telegram_message(text_html: str, chat_ids: list) -> tuple:
    if not TELEGRAM_BOT_TOKEN or not chat_ids: return (0, 0)
    enviados, falhas = 0, 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in chat_ids:
        try:
            payload = {"chat_id": chat_id, "text": text_html, "parse_mode": "HTML"}
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                enviados += 1
            elif response.status_code == 429:
                time.sleep(response.json().get("parameters", {}).get("retry_after", 5))
                requests.post(url, json=payload, timeout=15)
            time.sleep(1)
        except Exception as e:
            log_message(f"Erro Telegram: {e}", "ERROR")
            falhas += 1
    return (enviados, falhas)

def executar_ciclo():
    bot_status["status"] = "Buscando ofertas..."
    config = load_dynamic_config() # Lê as tags mais recentes configuradas no painel
    
    posted_ids = load_posted_ids(POSTED_FILE)
    cupons_ids = load_posted_ids(CUPONS_FILE)
    
    # Processar Ofertas RSS
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(RSS_FEED_URL, headers=headers, timeout=15)
        feed = feedparser.parse(resp.content)
        
        for entry in reversed(feed.entries):
            raw_title = entry.get("title", "Oferta")
            link = entry.get("link", "").strip()
            entry_id = entry.get("id") or link
            unique_id = generate_unique_id(raw_title, entry_id)

            if unique_id not in posted_ids and link.startswith("http"):
                affiliate_link = convert_to_affiliate_link(link, config)
                msg = f"🎁 <b>PROMOÇÃO</b>\n\n<b>{safe_tg_html(raw_title)}</b>\n\n🔗 <a href='{affiliate_link}'>Ver Oferta</a>"
                env, _ = send_telegram_message(msg, TODOS_DESTINOS)
                if env > 0:
                    posted_ids.append(unique_id)
                    bot_status["ofertas_enviadas_hoje"] += 1
    except Exception as e:
        log_message(f"Erro no feed: {e}", "ERROR")

    save_posted_ids(posted_ids, POSTED_FILE)
    
    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = f"Aguardando ({INTERVALO_VERIFICACAO} min)..."

def loop_principal():
    log_message("Thread do bot iniciada.")
    while True:
        try:
            executar_ciclo()
            time.sleep(INTERVALO_VERIFICACAO * 60)
        except Exception as e:
            log_message(f"Erro no loop principal: {e}", "ERROR")
            time.sleep(60)

# ============================================================================
# FLASK WEB INTERFACE (Dashboard)
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel de Controle - Bot Defensoria</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; padding-top: 20px; }
        .card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .status-badge { font-size: 1.1em; }
    </style>
</head>
<body>
    <div class="container">
        <h2 class="mb-4">🤖 Painel do Bot de Ofertas</h2>
        
        <!-- Status do Bot -->
        <div class="card">
            <div class="card-header bg-dark text-white">Status do Sistema</div>
            <div class="card-body">
                <p><strong>Status Atual:</strong> <span class="badge bg-primary status-badge">{{ status.status }}</span></p>
                <p><strong>Última Execução:</strong> {{ status.ultima_execucao }}</p>
                <p><strong>Ofertas Enviadas Hoje:</strong> {{ status.ofertas_enviadas_hoje }}</p>
            </div>
        </div>

        <!-- Configuração de Afiliados -->
        <div class="card">
            <div class="card-header bg-success text-white">Links de Afiliado</div>
            <div class="card-body">
                <form action="/update_tags" method="POST">
                    <div class="mb-3">
                        <label class="form-label">Tag Amazon</label>
                        <input type="text" class="form-control" name="amazon_tag" value="{{ config.amazon_tag }}" placeholder="ex: seucodigo-20">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">UTM Source Mercado Livre (Outros)</label>
                        <input type="text" class="form-control" name="mercado_livre_tag" value="{{ config.mercado_livre_tag }}" placeholder="ex: robo_ofertas">
                    </div>
                    <button type="submit" class="btn btn-success">Salvar Configurações</button>
                </form>
            </div>
        </div>

        <!-- Logs e Erros -->
        <div class="card border-danger">
            <div class="card-header bg-danger text-white">Últimos Erros (Logs)</div>
            <div class="card-body">
                <ul class="list-group">
                    {% for erro in status.erros_recentes %}
                        <li class="list-group-item text-danger">{{ erro }}</li>
                    {% else %}
                        <li class="list-group-item text-muted">Nenhum erro registrado recentemente.</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    config = load_dynamic_config()
    return render_template_string(HTML_TEMPLATE, config=config, status=bot_status)

@app.route("/update_tags", methods=["POST"])
def update_tags():
    novo_config = {
        "amazon_tag": request.form.get("amazon_tag", "").strip(),
        "mercado_livre_tag": request.form.get("mercado_livre_tag", "").strip()
    }
    save_dynamic_config(novo_config)
    return redirect("/")

@app.route("/health")
def health():
    """Endpoint limpo para o UptimeRobot bater"""
    return jsonify({"status": "online", "uptime": "ok"})

if __name__ == "__main__":
    # Inicia a rotina de postagem em uma thread separada
    thread_bot = threading.Thread(target=loop_principal, daemon=True)
    thread_bot.start()

    # Inicia o servidor web Dashboard na thread principal
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
