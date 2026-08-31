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
    data.setdefault("panel_users", {})
    data.setdefault("amazon_tag", "")
    data.setdefault("mercado_livre_tag", "")
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


def get_panel_users(config):
    users = config.get("panel_users", {})
    clean_users = {}
    if isinstance(users, dict):
        for username, password in users.items():
            uname = str(username).strip()
            passwd = str(password)
            if uname and passwd:
                clean_users[uname] = passwd
    legacy_password = str(config.get("panel_password", "")).strip()
    if legacy_password and "admin" not in clean_users:
        clean_users["admin"] = legacy_password
    return clean_users


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
            else:
                falhas += 1
                log_message(
                    "Falha Telegram (%s): %s" % (chat_id, resp.text),
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
    rss_url = cfg.get("rss_url", "").strip()
    if not rss_url:
        log_message("RSS URL vazio, ciclo abortado.", "WARN")
        return

    bot_status["status"] = "Raspando RSS..."
    posted_ids = load_posted_ids()

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(rss_url, headers=headers, timeout=20)
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        log_message("Falha ao buscar RSS: %s" % exc, "ERROR")
        bot_status["status"] = "Sistema Operacional"
        return

    novos = 0

    for entry in reversed(feed.entries):
        titulo = entry.get("title", "Oferta")
        link = entry.get("link", "").strip()
        entry_id = entry.get("id") or link
        uid = generate_unique_id(titulo, entry_id)

        if uid in posted_ids or not link.startswith("http"):
            continue
        if not pass_filters(titulo, cfg):
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

    save_posted_ids(posted_ids)
    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = "Sistema Operacional"
    log_message(
        "Ciclo concluído. Novas ofertas enviadas: %d" % novos,
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
</head>
<body class="bg-dark text-light d-flex align-items-center justify-content-center" style="min-height:100vh;">
  <div class="card bg-secondary" style="min-width:360px;">
    <div class="card-body">
      <h4 class="card-title mb-3">Painel Mega Deals</h4>
      {% if setup %}
        <p class="text-warning">Defina a senha de acesso ao painel. Ela será salva em config.json.</p>
      {% endif %}
      {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
      {% endif %}
      <form method="post">
        {% if setup %}
          <div class="mb-3">
            <label class="form-label">Usuário administrador</label>
            <input type="text" name="usuario_novo" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Nova senha</label>
            <input type="password" name="senha_nova" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Confirmar senha</label>
            <input type="password" name="senha_conf" class="form-control" required>
          </div>
        {% else %}
          <div class="mb-3">
            <label class="form-label">Usuário</label>
            <input type="text" name="usuario" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Senha</label>
            <input type="password" name="senha" class="form-control" required>
          </div>
        {% endif %}
        <button class="btn btn-primary w-100" type="submit">
          {{ 'Definir senha' if setup else 'Entrar' }}
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
</head>
<body class="bg-dark text-light">
<nav class="navbar navbar-expand navbar-dark bg-secondary mb-4">
  <div class="container-fluid">
    <span class="navbar-brand">Mega Deals // Console</span>
    <div class="d-flex gap-2">
      <span class="navbar-text">Usuário: {{ current_user }}</span>
      <a href="/logout" class="btn btn-sm btn-outline-light">Sair</a>
    </div>
  </div>
</nav>
<div class="container-fluid">
  <div class="row">
    <div class="col-lg-6 mb-4">
      <div class="card bg-secondary">
        <div class="card-header">Status</div>
        <div class="card-body">
          <p><strong>Situação:</strong> <span id="st-status">...</span></p>
          <p><strong>Última execução:</strong> <span id="st-ultima">...</span></p>
          <p><strong>Ofertas enviadas hoje:</strong> <span id="st-ofertas">...</span></p>
          <form method="post" action="/action/control" class="mt-3 d-flex flex-wrap gap-2">
            <button name="action" value="toggle_pause" class="btn btn-warning">Pausar/Iniciar</button>
            <button name="action" value="force_run" class="btn btn-primary">Forçar ciclo</button>
          </form>
        </div>
      </div>
      <div class="card bg-secondary mt-4">
        <div class="card-header">Logs</div>
        <div class="card-body" style="max-height:300px; overflow-y:auto;" id="logs-box">
          Carregando...
        </div>
      </div>
    </div>
    <div class="col-lg-6 mb-4">
      <div class="card bg-secondary">
        <div class="card-header">Configuração</div>
        <div class="card-body">
          <form method="post" action="/update_config">
            <div class="mb-3">
              <label class="form-label">BOT TOKEN (Telegram)</label>
              <input type="text" name="telegram_token" class="form-control" value="{{ cfg.telegram_token }}">
            </div>
            <div class="mb-3">
              <label class="form-label">Destinos (IDs separados por vírgula)</label>
              <input type="text" name="destinos_telegram" class="form-control" value="{{ cfg.destinos_telegram }}">
            </div>
            <div class="mb-3">
              <label class="form-label">RSS URL</label>
              <input type="text" name="rss_url" class="form-control" value="{{ cfg.rss_url }}">
            </div>
            <div class="mb-3">
              <label class="form-label">Intervalo (minutos)</label>
              <input type="number" name="intervalo" class="form-control" value="{{ cfg.intervalo }}">
            </div>
            <button class="btn btn-success" type="submit">Salvar</button>
          </form>
        </div>
      </div>
      <div class="card bg-secondary mt-4">
        <div class="card-header">Acesso do painel</div>
        <div class="card-body">
          <form method="post" action="/manage_users">
            <input type="hidden" name="action" value="add_or_update">
            <div class="mb-3">
              <label class="form-label">Usuário</label>
              <input type="text" name="username" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label">Senha</label>
              <input type="password" name="password" class="form-control" required>
            </div>
            <button class="btn btn-info" type="submit">Adicionar/Atualizar usuário</button>
          </form>
          <hr>
          <p class="mb-2"><strong>Usuários cadastrados:</strong></p>
          {% for user in panel_users %}
            <form method="post" action="/manage_users" class="d-flex justify-content-between align-items-center mb-2">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="username" value="{{ user }}">
              <span>{{ user }}</span>
              {% if user == current_user %}
                <button class="btn btn-sm btn-outline-light" type="button" disabled>Usuário atual</button>
              {% elif panel_users|length == 1 %}
                <button class="btn btn-sm btn-outline-light" type="button" disabled>Último usuário</button>
              {% else %}
                <button class="btn btn-sm btn-danger" type="submit">Remover</button>
              {% endif %}
            </form>
          {% endfor %}
        </div>
      </div>
    </div>
  </div>
</div>
<script>
function atualizarStatus(){
  fetch('/api/data').then(r=>r.json()).then(d=>{
    document.getElementById('st-status').innerText = d.status.status;
    document.getElementById('st-ultima').innerText = d.status.ultima_execucao;
    document.getElementById('st-ofertas').innerText = d.status.ofertas_enviadas_hoje;
    const box = document.getElementById('logs-box');
    box.innerHTML = d.logs.join('<br>');
    box.scrollTop = box.scrollHeight;
  }).catch(e=>{});
}
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
    panel_users = get_panel_users(cfg)
    setup = not bool(panel_users)
    error = None

    if request.method == "POST":
        if setup:
            usuario_novo = request.form.get("usuario_novo", "").strip()
            nova = request.form.get("senha_nova", "")
            conf = request.form.get("senha_conf", "")
            if not usuario_novo:
                error = "Usuário é obrigatório."
            elif not nova or nova != conf:
                error = "Senhas não conferem."
            else:
                cfg["panel_users"] = {usuario_novo: nova}
                cfg["panel_password"] = ""
                save_config(cfg)
                session.clear()
                session["logged_in"] = True
                session["username"] = usuario_novo
                log_message("Senha do painel definida.", "INFO")
                return redirect("/")
        else:
            usuario = request.form.get("usuario", "").strip()
            senha = request.form.get("senha", "")
            senha_salva = panel_users.get(usuario)
            if senha_salva and secrets.compare_digest(str(senha), str(senha_salva)):
                if not cfg.get("panel_users"):
                    cfg["panel_users"] = panel_users
                    cfg["panel_password"] = ""
                    save_config(cfg)
                session.clear()
                session["logged_in"] = True
                session["username"] = usuario
                log_message("Login autorizado.", "INFO")
                return redirect("/")
            else:
                error = "Usuário ou senha incorretos."

    return render_template_string(LOGIN_HTML, setup=setup, error=error)


@app.route("/")
@login_required
def index():
    cfg = load_config()
    panel_users = sorted(get_panel_users(cfg).keys())
    return render_template_string(
        DASHBOARD_HTML,
        cfg=cfg,
        panel_users=panel_users,
        current_user=session.get("username", "desconhecido"),
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/manage_users", methods=["POST"])
@login_required
def manage_users():
    cfg = load_config()
    panel_users = get_panel_users(cfg)
    action = request.form.get("action", "")
    if action == "add_or_update":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username and password:
            panel_users[username] = password
            cfg["panel_users"] = panel_users
            cfg["panel_password"] = ""
            save_config(cfg)
            log_message("Usuário do painel adicionado/atualizado: %s" % username, "INFO")
    elif action == "delete":
        username = request.form.get("username", "").strip()
        current_user = session.get("username", "")
        if username and username in panel_users:
            if username == current_user:
                log_message("Remoção bloqueada: usuário atual.", "WARN")
            elif len(panel_users) <= 1:
                log_message("Remoção bloqueada: é necessário manter ao menos 1 usuário.", "WARN")
            else:
                panel_users.pop(username, None)
                cfg["panel_users"] = panel_users
                cfg["panel_password"] = ""
                save_config(cfg)
                log_message("Usuário do painel removido: %s" % username, "INFO")
    return redirect("/")


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
    save_config(cfg)
    log_message("Configuração atualizada.", "INFO")
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
