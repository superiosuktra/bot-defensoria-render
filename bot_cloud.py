#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Bot de ofertas/cupons com painel Flask simples.

import os
import time
import json
import threading
import hashlib
from datetime import datetime
from collections import deque
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import secrets
import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, redirect, jsonify, session
from functools import wraps

# ======================================================================
# CONFIGURAÇÃO
# ======================================================================

load_dotenv()

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    FLASK_SECRET_KEY = secrets.token_hex(32)

CONFIG_FILE = "config.json"
POSTED_FILE = "postados.txt"
MAX_IDS_HISTORICO = 5000

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

is_prod = os.getenv("FLASK_ENV") == "production"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=is_prod,
)

bot_status = {
    "status": "Iniciando Sistema...",
    "is_paused": False,
    "force_run": False,
    "ultima_execucao": "N/A",
    "ofertas_enviadas_hoje": 0,
}

app_logs = deque(maxlen=200)
time_since_last_run = 0
file_lock = threading.Lock()
logs_lock = threading.Lock()

# ======================================================================
# UTIL
# ======================================================================


def log_message(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = "#00ff41"
    if level == "ERROR":
        color = "#ff003c"
    elif level == "WARN":
        color = "#ffea00"
    line = "[%s] <span style='color:%s'>[%s] %s</span>" % (ts, color, level, message)
    print("[%s] [%s] %s" % (ts, level, message))
    with logs_lock:
        app_logs.append(line)


def safe_tg_html(text):
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log_message("Falha ao ler config.json, recriando: %s" % exc, "WARN")
            data = {}
    else:
        data = {}

    data.setdefault("telegram_token", "")
    data.setdefault("destinos_telegram", "")
    data.setdefault("rss_url", "https://www.promobit.com.br/feed/")
    data.setdefault("intervalo", 120)
    data.setdefault("blacklist", "internacional, usado, reembalado")
    data.setdefault("whitelist", "")
    data.setdefault("panel_password", "")
    data.setdefault("amazon_tag", "")
    data.setdefault("mercado_livre_tag", "")
    data.setdefault("desconto_minimo", 10)
    data.setdefault("preco_minimo", 0)
    data.setdefault("preco_maximo", 99999)
    data.setdefault("sources", "promobit")
    return data


def save_config(cfg):
    with file_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)


def load_posted_ids():
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(ids))
    except Exception as exc:
        log_message("Falha ao ler %s: %s" % (POSTED_FILE, exc), "WARN")
        return []


def save_posted_ids(ids):
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            for item_id in ids[-MAX_IDS_HISTORICO:]:
                f.write(item_id + "\n")
    except Exception as exc:
        log_message("Falha ao salvar %s: %s" % (POSTED_FILE, exc), "WARN")


def generate_unique_id(text, url):
    base = (text.strip() + "|" + url.strip()).lower().encode("utf-8")
    return hashlib.sha256(base).hexdigest()[:16]


def pass_filters(titulo, config):
    t_lower = titulo.lower()
    blacklist = [
        w.strip().lower() for w in config.get("blacklist", "").split(",") if w.strip()
    ]
    if any(b in t_lower for b in blacklist):
        log_message("Bloqueado pela blacklist: %s" % titulo, "WARN")
        return False
    whitelist = [
        w.strip().lower() for w in config.get("whitelist", "").split(",") if w.strip()
    ]
    if whitelist and not any(w in t_lower for w in whitelist):
        log_message("Ignorado (fora da whitelist): %s" % titulo, "WARN")
        return False
    return True


def get_rss_urls(config):
    """Retorna lista de URLs RSS baseado nas fontes selecionadas"""
    rss_custom = config.get("rss_url", "").strip()
    if rss_custom and rss_custom != "https://www.promobit.com.br/feed/":
        return [rss_custom]
    
    sources = [s.strip() for s in config.get("sources", "promobit").split(",") if s.strip()]
    urls = []
    
    rss_map = {
        "promobit": "https://www.promobit.com.br/feed/",
        "mercadolivre": "https://www.mercadolivre.com.br/",
        "amazon": "https://www.amazon.com.br/",
        "kabum": "https://www.kabum.com.br/feed",
        "terabyteshop": "https://www.terabyteshop.com.br/feed",
        "shopee": "https://shopee.com.br/",
    }
    
    for source in sources:
        if source in rss_map:
            urls.append(rss_map[source])
    
    return urls if urls else [rss_map.get("promobit")]


def convert_to_affiliate_link(url, config):
    if not url or not isinstance(url, str):
        return url
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        q = parse_qs(parsed.query)
        if "amazon.com" in host or "amazon.com.br" in host:
            tag = config.get("amazon_tag", "")
            if tag:
                q["tag"] = [tag]
        if "mercadolivre.com" in host or "mercadolivre.com.br" in host:
            utm = config.get("mercado_livre_tag", "")
            if utm:
                q["utm_source"] = [utm]
        return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))
    except Exception as exc:
        log_message("Erro ao converter link afiliado: %s" % exc, "WARN")
        return url


def send_telegram_message(text_html, config):
    token = config.get("telegram_token", "").strip()
    raw_destinos = config.get("destinos_telegram", "")
    chat_ids = [d.strip() for d in raw_destinos.split(",") if d.strip()]
    if not token or not chat_ids:
        log_message("Envio abortado: token ou destinos vazios.", "WARN")
        return 0, 0
    enviados, falhas = 0, 0
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    for chat_id in chat_ids:
        try:
            payload = {
                "chat_id": chat_id,
                "text": text_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                enviados += 1
                log_message("Mensagem enviada com sucesso para %s" % chat_id, "INFO")
            else:
                falhas += 1
                log_message(
                    "Falha Telegram (%s - Status %d): %s" % (chat_id, resp.status_code, resp.text),
                    "ERROR",
                )
            time.sleep(0.5)
        except Exception as exc:
            falhas += 1
            log_message(
                "Erro de conexão Telegram (%s): %s" % (chat_id, exc),
                "ERROR",
            )
    return enviados, falhas


# ======================================================================
# CICLO DO BOT
# ======================================================================


def executar_ciclo():
    cfg = load_config()
    rss_urls = get_rss_urls(cfg)
    
    if not rss_urls:
        log_message("Nenhuma URL RSS configurada, ciclo abortado.", "WARN")
        return

    bot_status["status"] = "Raspando RSS..."
    posted_ids = load_posted_ids()
    
    total_novos = 0
    total_bloqueadas = 0
    total_ja_postadas = 0

    for rss_url in rss_urls:
        if not rss_url.strip():
            continue
            
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(rss_url, headers=headers, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:
            log_message("Falha ao buscar RSS (%s): %s" % (rss_url, exc), "ERROR")
            continue

        if not hasattr(feed, 'entries') or not feed.entries:
            log_message("Feed vazio ou inválido (%s). Nenhuma entrada encontrada." % rss_url, "WARN")
            continue

        log_message("Feed encontrado (%s) com %d entradas." % (rss_url, len(feed.entries)), "INFO")
        novos = 0
        bloqueadas = 0
        ja_postadas = 0

        for entry in reversed(feed.entries):
            titulo = entry.get("title", "Oferta")
            link = entry.get("link", "").strip()
            entry_id = entry.get("id") or link
            uid = generate_unique_id(titulo, entry_id)

            if uid in posted_ids:
                ja_postadas += 1
                continue
            if not link.startswith("http"):
                log_message("Link inválido ignorado: %s" % link, "WARN")
                bloqueadas += 1
                continue
            if not pass_filters(titulo, cfg):
                bloqueadas += 1
                posted_ids.append(uid)
                continue

            afiliado = convert_to_affiliate_link(link, cfg)
            safe_title = safe_tg_html(titulo)
            safe_link = safe_tg_html(afiliado)
            msg = (
                "🎁 <b>PROMOÇÃO</b>\n\n"
                "<b>%s</b>\n\n"
                "🔗 <a href='%s'>Ver Oferta</a>" % (safe_title, safe_link)
            )

            enviados, _ = send_telegram_message(msg, cfg)
            if enviados > 0:
                posted_ids.append(uid)
                bot_status["ofertas_enviadas_hoje"] += enviados
                novos += enviados
                log_message("Oferta enviada: %s" % titulo, "INFO")
            else:
                log_message("Falha ao enviar: %s" % titulo, "ERROR")
                bloqueadas += 1

        total_novos += novos
        total_bloqueadas += bloqueadas
        total_ja_postadas += ja_postadas

    save_posted_ids(posted_ids)
    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = "Sistema Operacional"
    log_message(
        "Ciclo concluído. Enviadas: %d, Bloqueadas: %d, Já postadas: %d" % (total_novos, total_bloqueadas, total_ja_postadas),
        "INFO",
    )


def loop_principal():
    global time_since_last_run
    log_message("Núcleo do bot iniciado.", "INFO")
    while True:
        cfg = load_config()
        try:
            intervalo = int(cfg.get("intervalo", 120)) * 60
        except (TypeError, ValueError):
            intervalo = 120 * 60
        if bot_status["force_run"]:
            bot_status["force_run"] = False
            if not bot_status["is_paused"]:
                executar_ciclo()
                time_since_last_run = 0
        elif not bot_status["is_paused"] and time_since_last_run >= intervalo:
            executar_ciclo()
            time_since_last_run = 0
        time.sleep(1)
        if not bot_status["is_paused"]:
            time_since_last_run += 1


# ======================================================================
# HTML (LOGIN + CONSOLE)
# ======================================================================

LOGIN_HTML = '''
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Login // Mega Deals</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    body {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
    }
    .card {
      border: none;
      border-radius: 15px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.3);
      animation: slideIn 0.5s ease-out;
    }
    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(-30px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .card-body {
      padding: 2.5rem;
    }
    .form-control {
      border-radius: 8px;
      border: 2px solid transparent;
      padding: 12px;
      transition: all 0.3s;
    }
    .form-control:focus {
      border-color: #667eea;
      box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
    }
    .btn-primary {
      border-radius: 8px;
      padding: 12px;
      font-weight: 600;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      border: none;
      transition: all 0.3s;
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
    }
    .logo {
      font-size: 2.5rem;
      margin-bottom: 1rem;
      text-align: center;
    }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center">
  <div class="card bg-white text-dark" style="min-width:380px; max-width:420px;">
    <div class="card-body">
      <div class="logo">
        <i class="fas fa-bolt"></i>
      </div>
      <h3 class="card-title mb-1 text-center">Mega Deals</h3>
      <p class="text-center text-muted mb-4">Painel de Controle</p>
      {% if setup %}
        <p class="text-info small mb-3"><i class="fas fa-info-circle"></i> Defina a senha de acesso ao painel</p>
      {% endif %}
      {% if error %}
        <div class="alert alert-danger alert-dismissible fade show"><i class="fas fa-exclamation-circle"></i> {{ error }}</div>
      {% endif %}
      <form method="post">
        {% if setup %}
          <div class="mb-3">
            <label class="form-label fw-600">Nova Senha</label>
            <input type="password" name="senha_nova" class="form-control" placeholder="Digite sua senha" required>
          </div>
          <div class="mb-3">
            <label class="form-label fw-600">Confirmar Senha</label>
            <input type="password" name="senha_conf" class="form-control" placeholder="Confirme sua senha" required>
          </div>
        {% else %}
          <div class="mb-3">
            <label class="form-label fw-600">Senha</label>
            <input type="password" name="senha" class="form-control" placeholder="Digite sua senha" required>
          </div>
        {% endif %}
        <button class="btn btn-primary w-100 mt-4" type="submit">
          <i class="fas fa-sign-in-alt"></i> {{ 'Definir Senha' if setup else 'Entrar' }}
        </button>
      </form>
    </div>
  </div>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Console // Mega Deals</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.css" rel="stylesheet">
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .navbar {
      background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
      box-shadow: 0 5px 20px rgba(0,0,0,0.2);
    }
    .navbar-brand {
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: 0.5px;
    }
    .container-fluid {
      padding: 2rem 1rem;
    }
    .card {
      border: none;
      border-radius: 12px;
      box-shadow: 0 5px 20px rgba(0,0,0,0.1);
      transition: all 0.3s ease;
      background: #fff;
    }
    .card:hover {
      box-shadow: 0 10px 30px rgba(0,0,0,0.15);
      transform: translateY(-2px);
    }
    .card-header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border-radius: 12px 12px 0 0;
      padding: 1.25rem;
      font-weight: 600;
      border: none;
    }
    .card-body {
      padding: 1.5rem;
    }
    .stat-card {
      text-align: center;
      padding: 1.5rem;
      background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
      border-radius: 10px;
      margin-bottom: 1rem;
    }
    .stat-value {
      font-size: 2rem;
      font-weight: 700;
      color: #667eea;
      margin: 0.5rem 0;
    }
    .stat-label {
      color: #666;
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .btn-warning, .btn-primary, .btn-success, .btn-danger {
      border-radius: 8px;
      padding: 10px 20px;
      font-weight: 600;
      transition: all 0.3s;
      border: none;
    }
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    .form-label {
      font-weight: 600;
      color: #333;
      margin-bottom: 0.5rem;
    }
    .form-control, .form-select {
      border-radius: 8px;
      border: 2px solid #e0e0e0;
      padding: 10px 12px;
      transition: all 0.3s;
    }
    .form-control:focus, .form-select:focus {
      border-color: #667eea;
      box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
    }
    #logs-box {
      background: #f8f9fa;
      border-radius: 8px;
      padding: 1rem;
      font-family: 'Courier New', monospace;
      font-size: 0.85rem;
      line-height: 1.5;
    }
    .log-line {
      margin: 0.25rem 0;
    }
    .status-badge {
      display: inline-block;
      padding: 0.5rem 1rem;
      border-radius: 20px;
      font-weight: 600;
      font-size: 0.9rem;
    }
    .status-active {
      background-color: #d4edda;
      color: #155724;
    }
    .status-paused {
      background-color: #fff3cd;
      color: #856404;
    }
    .section-title {
      font-size: 1.3rem;
      font-weight: 700;
      color: #333;
      margin-bottom: 1.5rem;
      padding-bottom: 0.5rem;
      border-bottom: 3px solid #667eea;
    }
    .tabs-container {
      margin-top: 1.5rem;
    }
    .nav-tabs {
      border: none;
      gap: 0.5rem;
    }
    .nav-link {
      border: none;
      border-radius: 8px 8px 0 0;
      color: #666;
      font-weight: 600;
      transition: all 0.3s;
      background-color: #f0f0f0;
    }
    .nav-link.active {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
    }
    .source-badge {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: 600;
      background: #667eea15;
      color: #667eea;
      margin-right: 0.5rem;
      margin-bottom: 0.5rem;
    }
  </style>
</head>
<body>
<nav class="navbar navbar-expand navbar-dark mb-4">
  <div class="container-fluid">
    <span class="navbar-brand"><i class="fas fa-bolt"></i> Mega Deals // Console</span>
    <div class="d-flex gap-2 align-items-center">
      <span class="text-light" id="clock"></span>
      <a href="/logout" class="btn btn-sm btn-outline-light"><i class="fas fa-sign-out-alt"></i> Sair</a>
    </div>
  </div>
</nav>

<div class="container-fluid">
  <div class="row g-4">
    <!-- Status Cards -->
    <div class="col-lg-3 col-md-6">
      <div class="stat-card">
        <div class="stat-label"><i class="fas fa-heartbeat"></i> Status</div>
        <div class="stat-value"><span id="st-status-badge" class="status-badge status-active">Ativo</span></div>
        <small class="text-muted" id="st-status-text">Aguardando...</small>
      </div>
    </div>
    <div class="col-lg-3 col-md-6">
      <div class="stat-card">
        <div class="stat-label"><i class="fas fa-gift"></i> Ofertas Hoje</div>
        <div class="stat-value" id="st-ofertas">0</div>
        <small class="text-muted">Enviadas via Telegram</small>
      </div>
    </div>
    <div class="col-lg-3 col-md-6">
      <div class="stat-card">
        <div class="stat-label"><i class="fas fa-clock"></i> Última Execução</div>
        <div style="font-size: 1rem; color: #666; margin-top: 0.5rem;" id="st-ultima">N/A</div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6">
      <div class="stat-card">
        <div class="stat-label"><i class="fas fa-rss"></i> Fontes Ativas</div>
        <div class="stat-value" id="st-sources">1</div>
        <small class="text-muted">Feeds RSS</small>
      </div>
    </div>
  </div>

  <!-- Controles -->
  <div class="row g-4 mt-2">
    <div class="col-lg-12">
      <div class="card">
        <div class="card-header"><i class="fas fa-sliders-h"></i> Controles Rápidos</div>
        <div class="card-body">
          <div class="d-flex flex-wrap gap-2">
            <form method="post" action="/action/control" style="display: inline;">
              <button name="action" value="toggle_pause" class="btn btn-warning">
                <i class="fas fa-pause-circle"></i> Pausar/Iniciar
              </button>
            </form>
            <form method="post" action="/action/control" style="display: inline;">
              <button name="action" value="force_run" class="btn btn-primary">
                <i class="fas fa-play-circle"></i> Executar Agora
              </button>
            </form>
            <form method="post" action="/action/control" style="display: inline;">
              <button name="action" value="clear_history" class="btn btn-danger">
                <i class="fas fa-trash-alt"></i> Limpar Histórico
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Tabs de Configuração -->
  <div class="row g-4 mt-2">
    <div class="col-lg-12">
      <div class="card">
        <div class="card-header"><i class="fas fa-cog"></i> Configurações</div>
        <div class="card-body">
          <ul class="nav nav-tabs" role="tablist">
            <li class="nav-item" role="presentation">
              <button class="nav-link active" id="tab-basico" data-bs-toggle="tab" data-bs-target="#content-basico" type="button" role="tab">
                <i class="fas fa-sliders-h"></i> Básico
              </button>
            </li>
            <li class="nav-item" role="presentation">
              <button class="nav-link" id="tab-fontes" data-bs-toggle="tab" data-bs-target="#content-fontes" type="button" role="tab">
                <i class="fas fa-rss"></i> Fontes RSS
              </button>
            </li>
            <li class="nav-item" role="presentation">
              <button class="nav-link" id="tab-filtros" data-bs-toggle="tab" data-bs-target="#content-filtros" type="button" role="tab">
                <i class="fas fa-filter"></i> Filtros Avançados
              </button>
            </li>
            <li class="nav-item" role="presentation">
              <button class="nav-link" id="tab-afiliados" data-bs-toggle="tab" data-bs-target="#content-afiliados" type="button" role="tab">
                <i class="fas fa-link"></i> Afiliados
              </button>
            </li>
          </ul>

          <div class="tab-content mt-4">
            <!-- TAB 1: BÁSICO -->
            <div class="tab-pane fade show active" id="content-basico" role="tabpanel">
              <form method="post" action="/update_config">
                <div class="row g-3">
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-key"></i> BOT TOKEN (Telegram)</label>
                    <input type="password" name="telegram_token" class="form-control" value="{{ cfg.telegram_token }}" placeholder="Seu token do BotFather">
                  </div>
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-users"></i> Destinos (IDs separados por vírgula)</label>
                    <input type="text" name="destinos_telegram" class="form-control" value="{{ cfg.destinos_telegram }}" placeholder="-4302126760, 123456789">
                  </div>
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-clock"></i> Intervalo (minutos)</label>
                    <input type="number" name="intervalo" class="form-control" value="{{ cfg.intervalo }}" min="5" max="1440">
                  </div>
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-exclamation-circle"></i> Desconto Mínimo (%)</label>
                    <input type="number" name="desconto_minimo" class="form-control" value="{{ cfg.get('desconto_minimo', 10) }}" min="0" max="100">
                  </div>
                  <div class="col-12">
                    <button class="btn btn-success" type="submit"><i class="fas fa-save"></i> Salvar Configurações</button>
                  </div>
                </div>
              </form>
            </div>

            <!-- TAB 2: FONTES RSS -->
            <div class="tab-pane fade" id="content-fontes" role="tabpanel">
              <form method="post" action="/update_sources">
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-rss"></i> Selecione as Fontes de Desconto</label>
                  <div class="row g-3">
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="promobit" id="src-promobit" {{ 'checked' if 'promobit' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-promobit">
                          <i class="fas fa-percentage"></i> Promobit (Promoções em geral)
                        </label>
                      </div>
                    </div>
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="mercadolivre" id="src-mercadolivre" {{ 'checked' if 'mercadolivre' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-mercadolivre">
                          <i class="fas fa-shopping-cart"></i> Mercado Livre
                        </label>
                      </div>
                    </div>
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="amazon" id="src-amazon" {{ 'checked' if 'amazon' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-amazon">
                          <i class="fas fa-mug-hot"></i> Amazon
                        </label>
                      </div>
                    </div>
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="kabum" id="src-kabum" {{ 'checked' if 'kabum' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-kabum">
                          <i class="fas fa-microchip"></i> Kabum (Eletrônicos)
                        </label>
                      </div>
                    </div>
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="terabyteshop" id="src-terabyte" {{ 'checked' if 'terabyteshop' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-terabyte">
                          <i class="fas fa-laptop"></i> Terabyte (Eletrônicos)
                        </label>
                      </div>
                    </div>
                    <div class="col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="sources" value="shopee" id="src-shopee" {{ 'checked' if 'shopee' in cfg.get('sources', '').split(',') else '' }}>
                        <label class="form-check-label" for="src-shopee">
                          <i class="fas fa-bag-shopping"></i> Shopee
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-link"></i> RSS URL Customizada</label>
                  <input type="text" name="rss_url" class="form-control" value="{{ cfg.rss_url }}" placeholder="https://www.promobit.com.br/feed/">
                  <small class="text-muted">Deixe em branco para usar as fontes pré-configuradas acima</small>
                </div>
                <button class="btn btn-success" type="submit"><i class="fas fa-save"></i> Salvar Fontes</button>
              </form>
            </div>

            <!-- TAB 3: FILTROS AVANÇADOS -->
            <div class="tab-pane fade" id="content-filtros" role="tabpanel">
              <form method="post" action="/update_filters">
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-ban"></i> Blacklist (Palavras a evitar)</label>
                  <textarea name="blacklist" class="form-control" rows="3" placeholder="internacional, usado, reembalado, defeituoso">{{ cfg.blacklist }}</textarea>
                  <small class="text-muted">Separadas por vírgula. Produtos com essas palavras serão ignorados.</small>
                </div>
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-check-circle"></i> Whitelist (Palavras obrigatórias)</label>
                  <textarea name="whitelist" class="form-control" rows="3" placeholder="PlayStation, Xbox, Nintendo">{{ cfg.whitelist }}</textarea>
                  <small class="text-muted">Separadas por vírgula. Se preenchido, apenas produtos com essas palavras serão enviados.</small>
                </div>
                <div class="row g-3">
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-dollar-sign"></i> Preço Mínimo (R$)</label>
                    <input type="number" name="preco_minimo" class="form-control" value="{{ cfg.get('preco_minimo', '0') }}" min="0" step="0.01">
                  </div>
                  <div class="col-md-6">
                    <label class="form-label"><i class="fas fa-dollar-sign"></i> Preço Máximo (R$)</label>
                    <input type="number" name="preco_maximo" class="form-control" value="{{ cfg.get('preco_maximo', '99999') }}" min="0" step="0.01">
                  </div>
                </div>
                <div class="mt-3">
                  <button class="btn btn-success" type="submit"><i class="fas fa-save"></i> Salvar Filtros</button>
                </div>
              </form>
            </div>

            <!-- TAB 4: AFILIADOS -->
            <div class="tab-pane fade" id="content-afiliados" role="tabpanel">
              <form method="post" action="/update_config">
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-link"></i> Código Afiliado Amazon</label>
                  <input type="text" name="amazon_tag" class="form-control" value="{{ cfg.amazon_tag }}" placeholder="seu-codigo-afiliado-01">
                  <small class="text-muted">Seu código de afiliado da Amazon para ganhar comissões</small>
                </div>
                <div class="mb-3">
                  <label class="form-label"><i class="fas fa-link"></i> UTM do Mercado Livre</label>
                  <input type="text" name="mercado_livre_tag" class="form-control" value="{{ cfg.mercado_livre_tag }}" placeholder="seu-utm-ml">
                  <small class="text-muted">Parâmetro UTM do Mercado Livre para rastreamento</small>
                </div>
                <button class="btn btn-success" type="submit"><i class="fas fa-save"></i> Salvar Afiliados</button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Logs -->
  <div class="row g-4 mt-2">
    <div class="col-lg-12">
      <div class="card">
        <div class="card-header"><i class="fas fa-terminal"></i> Logs do Sistema</div>
        <div class="card-body" style="max-height:400px; overflow-y:auto;" id="logs-box">
          <div class="text-center text-muted">Carregando logs...</div>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
function updateClock() {
  const now = new Date();
  document.getElementById('clock').innerText = now.toLocaleTimeString('pt-BR');
}

function atualizarStatus(){
  fetch('/api/data').then(r=>r.json()).then(d=>{
    document.getElementById('st-status-text').innerText = d.status.status;
    const badge = document.getElementById('st-status-badge');
    if (d.status.is_paused) {
      badge.textContent = 'Pausado';
      badge.className = 'status-badge status-paused';
    } else {
      badge.textContent = 'Ativo';
      badge.className = 'status-badge status-active';
    }
    document.getElementById('st-ultima').innerText = d.status.ultima_execucao;
    document.getElementById('st-ofertas').innerText = d.status.ofertas_enviadas_hoje;
    const box = document.getElementById('logs-box');
    box.innerHTML = d.logs.map((log, i) => '<div class="log-line" style="border-left:2px solid #667eea; padding-left:0.5rem;">' + log + '</div>').join('');
    box.scrollTop = box.scrollHeight;
  }).catch(e=>{
    console.error('Erro ao atualizar:', e);
  });
}

setInterval(updateClock, 1000);
updateClock();
setInterval(atualizarStatus, 3000);
atualizarStatus();
</script>
</body>
</html>
'''

# ======================================================================
# ROTAS FLASK
# ======================================================================


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = load_config()
    panel_password = cfg.get("panel_password", "")
    setup = not bool(panel_password)
    error = None

    if request.method == "POST":
        if setup:
            nova = request.form.get("senha_nova", "")
            conf = request.form.get("senha_conf", "")
            if not nova or nova != conf:
                error = "Senhas não conferem."
            else:
                cfg["panel_password"] = nova
                save_config(cfg)
                session.clear()
                session["logged_in"] = True
                log_message("Senha do painel definida.", "INFO")
                return redirect("/")
        else:
            senha = request.form.get("senha", "")
            if senha == panel_password:
                session.clear()
                session["logged_in"] = True
                log_message("Login autorizado.", "INFO")
                return redirect("/")
            else:
                error = "Senha incorreta."

    return render_template_string(LOGIN_HTML, setup=setup, error=error)


@app.route("/")
@login_required
def index():
    cfg = load_config()
    return render_template_string(DASHBOARD_HTML, cfg=cfg)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/data")
@login_required
def api_data():
    with logs_lock:
        logs_copy = list(app_logs)
    return jsonify({"status": bot_status, "logs": logs_copy})


@app.route("/update_config", methods=["POST"])
@login_required
def update_config():
    cfg = load_config()
    cfg["telegram_token"] = request.form.get("telegram_token", "").strip()
    cfg["destinos_telegram"] = request.form.get("destinos_telegram", "").strip()
    rss_url = request.form.get("rss_url", "").strip()
    if rss_url:
        cfg["rss_url"] = rss_url
    try:
        cfg["intervalo"] = int(request.form.get("intervalo", cfg["intervalo"]))
    except (TypeError, ValueError):
        pass
    try:
        cfg["desconto_minimo"] = int(request.form.get("desconto_minimo", 10))
    except (TypeError, ValueError):
        pass
    save_config(cfg)
    log_message("Configuração atualizada.", "INFO")
    return redirect("/")


@app.route("/update_sources", methods=["POST"])
@login_required
def update_sources():
    cfg = load_config()
    sources = request.form.getlist("sources")
    cfg["sources"] = ",".join(sources) if sources else "promobit"
    rss_url = request.form.get("rss_url", "").strip()
    if rss_url:
        cfg["rss_url"] = rss_url
    save_config(cfg)
    log_message("Fontes RSS atualizadas: %s" % cfg["sources"], "INFO")
    return redirect("/")


@app.route("/update_filters", methods=["POST"])
@login_required
def update_filters():
    cfg = load_config()
    cfg["blacklist"] = request.form.get("blacklist", "").strip()
    cfg["whitelist"] = request.form.get("whitelist", "").strip()
    try:
        cfg["preco_minimo"] = float(request.form.get("preco_minimo", 0))
    except (TypeError, ValueError):
        cfg["preco_minimo"] = 0
    try:
        cfg["preco_maximo"] = float(request.form.get("preco_maximo", 99999))
    except (TypeError, ValueError):
        cfg["preco_maximo"] = 99999
    save_config(cfg)
    log_message("Filtros avançados atualizados.", "INFO")
    return redirect("/")


@app.route("/action/control", methods=["POST"])
@login_required
def action_control():
    action = request.form.get("action")
    if action == "toggle_pause":
        bot_status["is_paused"] = not bot_status["is_paused"]
        estado = "Pausado" if bot_status["is_paused"] else "Ativo"
        log_message("Bot agora está: %s." % estado, "INFO")
    elif action == "force_run":
        bot_status["force_run"] = True
        log_message("Ciclo forçado solicitado.", "INFO")
    elif action == "clear_history":
        try:
            save_posted_ids([])
            log_message("Histórico de ofertas limpo com sucesso!", "INFO")
        except Exception as exc:
            log_message("Erro ao limpar histórico: %s" % exc, "ERROR")
    return redirect("/")


@app.route("/health")
def health():
    return jsonify({"status": "online", "bot_paused": bot_status["is_paused"]})


# ======================================================================
# MAIN
# ======================================================================

if __name__ == "__main__":
    t = threading.Thread(target=loop_principal, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
