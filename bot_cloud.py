#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bot de ofertas e cupons com painel Flask.

Principais recursos:
- Raspa ofertas via RSS e cupons do Mercado Livre.
- Envia promoções para canais/grupos do Telegram.
- Painel web para monitorar status, logs e configurar:
  - Token do Telegram
  - IDs de destino
  - Tags de afiliado (Amazon / Mercado Livre)
  - Blacklist / Whitelist
  - Intervalo de raspagem
- Auto-clean: verifica links de ofertas ativas e marca como encerradas
  no Telegram quando esgotadas ou com erro 404/410.

Segurança:
- Credenciais apenas via variáveis de ambiente / config.json.
- Painel protegido por senha e sessão Flask.
- Locks para evitar race conditions em arquivos e logs.
"""

import os
import time
import json
import hashlib
import threading
from datetime import datetime
from collections import deque
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

# Para produção, preencha PAINEL_PASSWORD e FLASK_SECRET_KEY no .env.
PAINEL_PASSWORD = os.getenv("PAINEL_PASSWORD")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

if not PAINEL_PASSWORD or not FLASK_SECRET_KEY:
    raise RuntimeError(
        "PAINEL_PASSWORD e FLASK_SECRET_KEY são obrigatórios. "
        "Configure-os no .env ou nas variáveis de ambiente."
    )

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
CONFIG_FILE = "config.json"
ACTIVE_MSGS_FILE = "mensagens_ativas.json"
MAX_IDS_HISTORICO = 5000

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Endurecer cookies de sessão (melhor segurança, especialmente em HTTPS)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") == "production",
)

bot_status = {
    "status": "Iniciando Sistema...",
    "is_paused": False,
    "force_run": False,
    "ultima_execucao": "N/A",
    "ofertas_enviadas_hoje": 0,
}

app_logs: deque[str] = deque(maxlen=100)
time_since_last_run = 0

file_lock = threading.Lock()
logs_lock = threading.Lock()
clean_lock = threading.Lock()
is_cleaning_links = False

# ============================================================================
# GERENCIADORES DE DADOS
# ============================================================================

def load_dynamic_config() -> dict:
    """Carrega config dinâmica do painel.

    Se não existir, cria a partir das variáveis de ambiente.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Garante chaves mínimas mesmo em arquivos antigos
                data.setdefault("telegram_token", "")
                data.setdefault("destinos_telegram", "")
                data.setdefault("amazon_tag", "")
                data.setdefault("mercado_livre_tag", "")
                data.setdefault("rss_url", os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/"))
                data.setdefault("intervalo", 120)
                data.setdefault("blacklist", "internacional, usado, reembalado")
                data.setdefault("whitelist", "")
                return data
        except Exception as exc:
            log_message(f"Falha ao ler config.json, recriando: {exc}", "WARN")

    default_config = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "destinos_telegram": (
            os.getenv("TELEGRAM_CANAIS", "") + "," + os.getenv("TELEGRAM_GRUPOS", "")
        ).strip(","),
        "amazon_tag": os.getenv("AFFILIATE_TAG_AMAZON", ""),
        "mercado_livre_tag": os.getenv("AFFILIATE_TAG_OUTROS", ""),
        "rss_url": os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/"),
        "intervalo": 120,
        "blacklist": "internacional, usado, reembalado",
        "whitelist": "",
    }
    save_dynamic_config(default_config)
    return default_config


def save_dynamic_config(config_data: dict) -> None:
    """Salva config no disco de forma thread-safe."""
    with file_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)


def load_active_msgs() -> list[dict]:
    """Carrega memória das mensagens ativas para auto-clean."""
    with file_lock:
        if os.path.exists(ACTIVE_MSGS_FILE):
            try:
                with open(ACTIVE_MSGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as exc:
                log_message(f"Falha ao ler mensagens_ativas.json: {exc}", "WARN")
        return []


def save_active_msgs(data: list[dict]) -> None:
    """Salva memória de mensagens ativas (últimos 100 itens)."""
    with file_lock:
        try:
            with open(ACTIVE_MSGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data[-100:], f, indent=4, ensure_ascii=False)
        except Exception as exc:
            log_message(f"Erro ao salvar mensagens ativas: {exc}", "ERROR")

# ============================================================================
# FUNÇÕES DO BOT E REGRAS DE NEGÓCIO
# ============================================================================

def log_message(message: str, level: str = "INFO") -> None:
    """Loga mensagem no console e no terminal do painel."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = "#00ff41"  # verde
    if level == "ERROR":
        color = "#ff003c"  # vermelho
    elif level == "WARN":
        color = "#ffea00"  # amarelo

    html_str = f"[{timestamp}] <span style='color:{color}'>[{level}] {message}</span>"
    print(f"[{timestamp}] [{level}] {message}")

    with logs_lock:
        app_logs.append(html_str)


def safe_tg_html(text: str) -> str:
    """Escapa HTML para mensagens com parse_mode=HTML no Telegram."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def pass_filters(titulo: str, config: dict) -> bool:
    """Aplica blacklist/whitelist sobre o título."""
    t_lower = titulo.lower()

    blacklist = [w.strip().lower() for w in config.get("blacklist", "").split(",") if w.strip()]
    if any(b in t_lower for b in blacklist):
        log_message(f"Bloqueado pela Blacklist: {titulo}", "WARN")
        return False

    whitelist = [w.strip().lower() for w in config.get("whitelist", "").split(",") if w.strip()]
    if whitelist and not any(w in t_lower for w in whitelist):
        log_message(f"Ignorado (Fora da Whitelist): {titulo}", "WARN")
        return False
    return True


def load_posted_ids(filename: str) -> list[str]:
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(ids))
    except Exception as exc:
        log_message(f"Falha ao ler {filename}: {exc}", "WARN")
        return []


def save_posted_ids(ids: list[str], filename: str) -> None:
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for item_id in ids[-MAX_IDS_HISTORICO:]:
                f.write(f"{item_id}\n")
    except Exception as exc:
        log_message(f"Falha ao salvar {filename}: {exc}", "WARN")


def generate_unique_id(text: str, url: str) -> str:
    base = f"{text.strip()}|{url.strip()}".lower().encode("utf-8")
    return hashlib.sha256(base).hexdigest()[:16]


def convert_to_affiliate_link(url: str, config: dict) -> str:
    """Adiciona tags de afiliado para Amazon / Mercado Livre quando aplicável."""
    if not url or not isinstance(url, str):
        return url
    try:
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower()

        if any(hostname == d or hostname.endswith(f".{d}") for d in ["amazon.com.br", "amazon.com"]):
            tag = config.get("amazon_tag")
            if tag:
                q = parse_qs(parsed.query)
                q["tag"] = [tag]
                return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

        elif any(hostname == d or hostname.endswith(f".{d}") for d in ["mercadolivre.com.br", "mercadolivre.com"]):
            utm = config.get("mercado_livre_tag")
            if utm:
                q = parse_qs(parsed.query)
                q["utm_source"] = [utm]
                return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

        return url
    except Exception as exc:
        log_message(f"Erro ao converter link de afiliado: {exc}", "WARN")
        return url


def send_telegram_message(text_html: str, config: dict) -> tuple[int, int, list[dict]]:
    """Envia mensagem HTML para todos os destinos configurados.

    Retorna (enviados, falhas, lista_de_mensagens_enviadas).
    """
    bot_token = config.get("telegram_token", "").strip()
    raw_destinos = config.get("destinos_telegram", "")
    chat_ids = list(dict.fromkeys([d.strip() for d in raw_destinos.split(",") if d.strip()]))

    if not bot_token or not chat_ids:
        log_message("Envio abortado: token ou destinos não configurados.", "WARN")
        return (0, 0, [])

    enviados = 0
    falhas = 0
    mensagens_enviadas: list[dict] = []
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

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
                data = resp.json()
                if "result" in data and "message_id" in data["result"]:
                    mensagens_enviadas.append(
                        {"chat_id": chat_id, "message_id": data["result"]["message_id"]}
                    )
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                log_message(f"Rate limit Telegram 429. Aguardando {retry_after}s...", "WARN")
                time.sleep(retry_after)
                resp_retry = requests.post(url, json=payload, timeout=15)
                if resp_retry.status_code == 200:
                    enviados += 1
                    data = resp_retry.json()
                    if "result" in data and "message_id" in data["result"]:
                        mensagens_enviadas.append(
                            {"chat_id": chat_id, "message_id": data["result"]["message_id"]}
                        )
                else:
                    falhas += 1
                    log_message(
                        f"Falha Telegram após retry ({chat_id}): {resp_retry.text}", "ERROR"
                    )
            else:
                falhas += 1
                log_message(f"Falha Telegram ({chat_id}): {resp.text}", "ERROR")
            time.sleep(1)
        except Exception as exc:
            falhas += 1
            log_message(f"Erro de conexão com Telegram ({chat_id}): {exc}", "ERROR")

    return enviados, falhas, mensagens_enviadas


def scrape_cupons_mercado_livre() -> list[dict]:
    """Raspa cupons do Mercado Livre (melhor esforço)."""
    cupons: list[dict] = []
    try:
        log_message("Buscando cupons do Mercado Livre...", "INFO")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get("https://www.mercadolivre.com.br/cupons", headers=headers, timeout=15)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml")
            elementos = soup.find_all(class_=lambda x: bool(x and "coupon" in x.lower()))

            for elem in elementos[:10]:
                texto = elem.get_text(separator=" ", strip=True)
                if texto:
                    cupons.append(
                        {
                            "titulo": texto[:120],
                            "loja": "Mercado Livre",
                            "link": "https://www.mercadolivre.com.br/cupons",
                        }
                    )
    except Exception as exc:
        log_message(f"Falha ao raspar cupons do ML: {exc}", "WARN")

    return cupons

# ============================================================================
# MÓDULO AUTO-CLEAN
# ============================================================================

def verificar_links_mortos(config: dict) -> None:
    """Varre as mensagens ativas e marca ofertas mortas como encerradas no Telegram."""
    global is_cleaning_links

    with clean_lock:
        if is_cleaning_links:
            log_message("Varredura abortada: já existe limpeza em andamento.", "WARN")
            return
        is_cleaning_links = True

    bot_token = config.get("telegram_token", "").strip()
    if not bot_token:
        log_message("Auto-Clean abortado: token não configurado.", "WARN")
        with clean_lock:
            is_cleaning_links = False
        return

    try:
        bot_status["status"] = "Verificando links mortos..."
        log_message("Iniciando varredura de estoque (auto-clean)...", "INFO")

        ativas = load_active_msgs()
        ativas_para_manter: list[dict] = []
        headers = {"User-Agent": "Mozilla/5.0"}
        url_edit = f"https://api.telegram.org/bot{bot_token}/editMessageText"

        for item in ativas:
            link = item.get("link", "")
            is_dead = False

            if not link.startswith("http"):
                ativas_para_manter.append(item)
                continue

            try:
                resp = requests.get(link, headers=headers, timeout=10, allow_redirects=True)
                if resp.status_code in (404, 410):
                    is_dead = True
                elif resp.status_code == 200:
                    html_lower = resp.text.lower()
                    if any(
                        p in html_lower
                        for p in [
                            "esgotado",
                            "indisponível",
                            "indisponivel",
                            "não está mais disponível",
                            "produto não encontrado",
                        ]
                    ):
                        is_dead = True
            except Exception as exc:
                log_message(f"Timeout ao checar link: {link} ({exc})", "WARN")

            if is_dead:
                log_message(f"Oferta morta detectada: {link}", "ERROR")
                original = item.get("original_text", "")
                novo_texto = (
                    "❌ <b>[ OFERTA ENCERRADA / ESGOTADA ]</b> ❌\n\n" f"{original}"
                )

                for tg_msg in item.get("tg_msgs", []):
                    payload = {
                        "chat_id": tg_msg.get("chat_id"),
                        "message_id": tg_msg.get("message_id"),
                        "text": novo_texto,
                        "parse_mode": "HTML",
                    }
                    try:
                        resp_edit = requests.post(url_edit, json=payload, timeout=10)
                        if resp_edit.status_code == 429:
                            retry_after = resp_edit.json().get("parameters", {}).get(
                                "retry_after", 5
                            )
                            log_message(
                                f"Rate limit 429 ao editar mensagem. Aguardando {retry_after}s...",
                                "WARN",
                            )
                            time.sleep(retry_after)
                            requests.post(url_edit, json=payload, timeout=10)
                        elif resp_edit.status_code != 200:
                            log_message(
                                f"Falha ao editar mensagem morta: {resp_edit.text}", "ERROR"
                            )
                        time.sleep(1)
                    except Exception as exc:
                        log_message(f"Erro ao editar mensagem: {exc}", "ERROR")
            else:
                ativas_para_manter.append(item)

        save_active_msgs(ativas_para_manter)
        bot_status["status"] = "Sistema Operacional"
        log_message("Varredura de estoque finalizada.", "INFO")
    finally:
        with clean_lock:
            is_cleaning_links = False


def executar_ciclo(config: dict) -> None:
    bot_status["status"] = "Raspando dados..."
    log_message("Iniciando varredura de RSS e Cupons", "INFO")

    posted_ids = load_posted_ids(POSTED_FILE)
    cupons_ids = load_posted_ids(CUPONS_FILE)
    active_msgs = load_active_msgs()
    rss_url = config.get("rss_url", "").strip()

    # 1) Ofertas via RSS
    if rss_url:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(rss_url, headers=headers, timeout=15)
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
                    safe_title = safe_tg_html(raw_title)
                    safe_url = safe_tg_html(affiliate_link)

                    msg_html = (
                        "🎁 <b>PROMOÇÃO</b>\n\n" f"<b>{safe_title}</b>\n\n" f"🔗 <a href='{safe_url}'>Ver Oferta</a>"
                    )

                    env, falhas, msg_data = send_telegram_message(msg_html, config)
                    if env > 0:
                        posted_ids.append(unique_id)
                        bot_status["ofertas_enviadas_hoje"] += 1
                        log_message(f"Transmissão concluída: {raw_title}", "INFO")
                        active_msgs.append(
                            {
                                "id": unique_id,
                                "link": link,
                                "original_text": msg_html,
                                "tg_msgs": msg_data,
                            }
                        )
                    elif falhas > 0:
                        log_message(f"Falha ao transmitir: {raw_title}", "ERROR")
        except Exception as exc:
            log_message(f"Falha na busca de RSS: {exc}", "ERROR")

    # 2) Cupons ML
    cupons = scrape_cupons_mercado_livre()
    for cupom in reversed(cupons):
        try:
            raw_titulo = cupom.get("titulo", "")
            raw_link = cupom.get("link", "")
            cupom_id = generate_unique_id(raw_titulo, raw_link)

            if cupom_id not in cupons_ids:
                safe_titulo = safe_tg_html(raw_titulo)
                affiliate_cupom_link = convert_to_affiliate_link(raw_link, config)
                safe_url = safe_tg_html(affiliate_cupom_link)

                msg = (
                    "🎟️ <b>CUPOM DISPONÍVEL</b>\n\n"
                    "🏪 <b>Loja:</b> Mercado Livre\n"
                    f"<b>Descrição:</b> {safe_titulo}\n\n"
                    f"🔗 <a href='{safe_url}'>Acessar Cupons</a>"
                )

                env, _, _ = send_telegram_message(msg, config)
                if env > 0:
                    cupons_ids.append(cupom_id)
                    bot_status["ofertas_enviadas_hoje"] += 1
                    log_message(f"Cupom enviado: {raw_titulo}", "INFO")
        except Exception as exc:
            log_message(f"Erro ao processar cupom: {exc}", "ERROR")

    save_posted_ids(posted_ids, POSTED_FILE)
    save_posted_ids(cupons_ids, CUPONS_FILE)
    save_active_msgs(active_msgs)

    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = "Sistema Operacional"
    log_message("Ciclo de processamento concluído.", "INFO")


def loop_principal() -> None:
    """Loop principal em thread separada.

    Lê config dinâmica e executa o ciclo conforme intervalo.
    """
    global time_since_last_run
    log_message("Núcleo do Bot ativado em background.", "INFO")

    while True:
        config = load_dynamic_config()
        try:
            intervalo_segundos = int(config.get("intervalo", 120)) * 60
        except (TypeError, ValueError):
            intervalo_segundos = 120 * 60

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
# TEMPLATES HTML (CYBERPUNK/FUTURISTA)
# ============================================================================

GLOBAL_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');

    :root {
        --bg-dark: #0a0a12;
        --glass-bg: rgba(16, 16, 28, 0.75);
        --neon-cyan: #00f3ff;
        --neon-green: #00ff41;
        --neon-red: #ff003c;
        --neon-yellow: #ffea00;
        --text-muted: #8b8b9f;
    }

    body {
        background-color: var(--bg-dark);
        background-image: radial-gradient(circle at 50% 0%, #1a1a2e 0%, var(--bg-dark) 100%);
        color: #e0e0e0;
        font-family: 'Rajdhani', sans-serif;
        min-height: 100vh;
    }

    .glass-card {
        background: var(--glass-bg);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(0, 243, 255, 0.15);
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(0, 243, 255, 0.02);
        margin-bottom: 24px;
        overflow: hidden;
    }

    .glass-header {
        background: rgba(0, 243, 255, 0.08);
        border-bottom: 1px solid rgba(0, 243, 255, 0.15);
        color: var(--neon-cyan);
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        padding: 15px 20px;
        font-size: 1.1rem;
    }

    .form-control {
        background: rgba(0, 0, 0, 0.5) !important;
        border: 1px solid rgba(0, 243, 255, 0.2) !important;
        color: var(--neon-cyan) !important;
        font-family: 'Fira Code', monospace;
        font-size: 0.9rem;
    }
    .form-control:focus {
        background: rgba(0, 0, 0, 0.8) !important;
        border-color: var(--neon-cyan) !important;
        box-shadow: 0 0 12px rgba(0, 243, 255, 0.3) !important;
    }
    .form-control::placeholder { color: rgba(0, 243, 255, 0.3) !important; }
    .form-label { color: #a1a1b5; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; font-size: 0.8rem;}

    .btn-cyber {
        background: transparent;
        color: var(--neon-cyan);
        border: 1px solid var(--neon-cyan);
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 1px;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    .btn-cyber:hover { background: var(--neon-cyan); color: #000; box-shadow: 0 0 15px var(--neon-cyan); }

    .btn-cyber-success { color: var(--neon-green); border-color: var(--neon-green); background: transparent; }
    .btn-cyber-success:hover { background: var(--neon-green); color: #000; box-shadow: 0 0 15px var(--neon-green); }

    .btn-cyber-danger { color: var(--neon-red); border-color: var(--neon-red); background: transparent; }
    .btn-cyber-danger:hover { background: var(--neon-red); color: #fff; box-shadow: 0 0 15px var(--neon-red); }

    .btn-cyber-warning { color: var(--neon-yellow); border-color: var(--neon-yellow); background: transparent; }
    .btn-cyber-warning:hover { background: var(--neon-yellow); color: #000; box-shadow: 0 0 15px var(--neon-yellow); }

    .badge-glow-success { background: rgba(0,255,65,0.15); border: 1px solid var(--neon-green); color: var(--neon-green); box-shadow: 0 0 10px rgba(0,255,65,0.3); font-weight: 600; letter-spacing: 1px;}
    .badge-glow-warning { background: rgba(255,234,0,0.15); border: 1px solid var(--neon-yellow); color: var(--neon-yellow); box-shadow: 0 0 10px rgba(255,234,0,0.3); font-weight: 600; letter-spacing: 1px;}

    .terminal {
        background-color: #030305;
        font-family: 'Fira Code', monospace;
        font-size: 0.85rem;
        height: 380px;
        overflow-y: auto;
        padding: 15px;
        line-height: 1.5;
        box-shadow: inset 0 0 20px rgba(0, 243, 255, 0.05);
    }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.5); }
    ::-webkit-scrollbar-thumb { background: rgba(0, 243, 255, 0.4); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0, 243, 255, 0.8); }

    .navbar-cyber {
        background: rgba(10, 10, 18, 0.9);
        border-bottom: 1px solid rgba(0, 243, 255, 0.3);
        box-shadow: 0 4px 20px rgba(0, 243, 255, 0.1);
    }
    .navbar-brand { font-weight: 700; color: var(--neon-cyan) !important; letter-spacing: 2px; text-shadow: 0 0 8px rgba(0,243,255,0.5); }
</style>
"""

LOGIN_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <title>SYS.LOGIN // MEGA DEALS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    {GLOBAL_CSS}
</head>
<body class="d-flex align-items-center justify-content-center">
    <div class="glass-card p-4" style="width: 380px;">
        <h3 class="text-center mb-4" style="color: var(--neon-cyan); text-shadow: 0 0 10px rgba(0,243,255,0.5); font-weight: 700;">SYS.LOGIN</h3>
        {{% if erro %}}<div class="alert alert-danger" style="background: rgba(255,0,60,0.2); border-color: var(--neon-red); color: #fff;">{{{{ erro }}}}</div>{{% endif %}}
        <form method="POST">
            <input type="password" name="senha" class="form-control mb-4 py-2" placeholder="[ INSIRA A SENHA DE ACESSO ]" required>
            <button class="btn btn-cyber w-100 py-2" type="submit">AUTENTICAR</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>SYSTEM.CONSOLE // Mega Deals</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    {GLOBAL_CSS}
</head>
<body>
    <nav class="navbar navbar-dark navbar-cyber mb-4 py-3">
        <div class="container-fluid px-4">
            <span class="navbar-brand mb-0 h1">CORE.CONSOLE // OFERTAS</span>
            <a href="/logout" class="btn btn-cyber-danger btn-sm">DESCONECTAR</a>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="row">
            <div class="col-lg-7">
                <div class="glass-card">
                    <div class="glass-header d-flex justify-content-between align-items-center">
                        <div><span style="color: #fff;">MÓDULO:</span> CONTROLE_EXECUÇÃO</div>
                        <span id="badge-status" class="badge badge-glow-success">CARREGANDO...</span>
                    </div>
                    <div class="card-body p-4">
                        <div class="row text-center mb-4">
                            <div class="col-6 border-end border-secondary">
                                <span class="text-muted d-block" style="font-size: 0.8rem; letter-spacing: 1px;">ÚLTIMA SINCRONIZAÇÃO</span>
                                <strong id="lbl-ultima" style="font-size: 1.2rem; color: #fff;">--</strong>
                            </div>
                            <div class="col-6">
                                <span class="text-muted d-block" style="font-size: 0.8rem; letter-spacing: 1px;">TRANSMISSÕES HOJE</span>
                                <strong id="lbl-ofertas" style="font-size: 1.2rem; color: var(--neon-cyan);">--</strong>
                            </div>
                        </div>
                        <form action="/action/control" method="POST" class="d-flex justify-content-center gap-3 flex-wrap">
                            <button name="action" value="toggle_pause" class="btn btn-cyber-warning px-4" id="btn-pause">⏸ PAUSAR SISTEMA</button>
                            <button name="action" value="force_run" class="btn btn-cyber px-4">▶ FORÇAR RASPAGEM</button>
                            <button name="action" value="check_dead_links" class="btn btn-cyber-danger px-4">🧹 LIMPAR ESGOTADOS</button>
                        </form>
                    </div>
                </div>

                <div class="glass-card">
                    <div class="glass-header">
                        <span style="color: #fff;">OUTPUT:</span> TERMINAL_DE_LOGS
                    </div>
                    <div id="terminal" class="terminal">Aguardando conexão com o núcleo...</div>
                </div>
            </div>

            <div class="col-lg-5">
                <div class="glass-card">
                    <div class="glass-header text-success" style="border-bottom-color: rgba(0,255,65,0.2); background: rgba(0,255,65,0.05); color: var(--neon-green) !important;">
                        <span style="color: #fff;">MÓDULO:</span> CONFIG_DINÂMICA
                    </div>
                    <div class="card-body p-4">
                        <form action="/update_config" method="POST">
                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// REDE TELEGRAM</h6>
                            <div class="mb-3">
                                <label class="form-label">BOT TOKEN (API KEY)</label>
                                <input type="password" class="form-control" name="telegram_token" value="{{{{ config.telegram_token }}}}" placeholder="[ PROTEGIDO ]">
                            </div>
                            <div class="mb-4">
                                <label class="form-label">IDs DE DESTINO (CHATS)</label>
                                <input type="text" class="form-control" name="destinos_telegram" value="{{{{ config.destinos_telegram }}}}" placeholder="-100..., -100...">
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// PARAMETRIZAÇÃO</h6>
                            <div class="mb-4 d-flex align-items-center">
                                <label class="form-label me-3 mb-0">DELAY DE RASPAGEM (MINUTOS)</label>
                                <input type="number" class="form-control w-25 text-center" name="intervalo" value="{{{{ config.intervalo }}}}">
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// ROTAS DE AFILIADO</h6>
                            <div class="row mb-4">
                                <div class="col-6">
                                    <label class="form-label">AMAZON TAG</label>
                                    <input type="text" class="form-control" name="amazon_tag" value="{{{{ config.amazon_tag }}}}">
                                </div>
                                <div class="col-6">
                                    <label class="form-label">MERCADO LIVRE (UTM)</label>
                                    <input type="text" class="form-control" name="mercado_livre_tag" value="{{{{ config.mercado_livre_tag }}}}">
                                </div>
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// ALGORITMO DE FILTRAGEM</h6>
                            <div class="mb-3">
                                <label class="form-label" style="color: var(--neon-red);">BLACKLIST (DESCARTAR)</label>
                                <input type="text" class="form-control" name="blacklist" value="{{{{ config.blacklist }}}}" placeholder="ex: internacional, usado">
                            </div>
                            <div class="mb-4">
                                <label class="form-label" style="color: var(--neon-green);">WHITELIST (REQUERIDO)</label>
                                <input type="text" class="form-control" name="whitelist" value="{{{{ config.whitelist }}}}" placeholder="[ DEIXE VAZIO PARA DESATIVAR ]">
                            </div>

                            <button type="submit" class="btn btn-cyber-success w-100 py-2 mt-2">GRAVAR PARÂMETROS</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function fetchStatus() {{
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {{
                    document.getElementById('lbl-ultima').innerText = data.status.ultima_execucao;
                    document.getElementById('lbl-ofertas').innerText = data.status.ofertas_enviadas_hoje;

                    const btnPause = document.getElementById('btn-pause');
                    if(data.status.is_paused) {{
                        btnPause.innerText = "▶ INICIAR SISTEMA";
                        btnPause.className = "btn btn-cyber px-4";
                        document.getElementById('badge-status').innerText = "SISTEMA PAUSADO";
                        document.getElementById('badge-status').className = "badge badge-glow-warning";
                    }} else {{
                        btnPause.innerText = "⏸ PAUSAR SISTEMA";
                        btnPause.className = "btn btn-cyber-warning px-4";
                        document.getElementById('badge-status').innerText = data.status.status.toUpperCase();
                        document.getElementById('badge-status').className = "badge badge-glow-success";
                    }}

                    const term = document.getElementById('terminal');
                    const isScrolledToBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 1;
                    term.innerHTML = data.logs.join('<br>');
                    if(isScrolledToBottom) {{
                        term.scrollTop = term.scrollHeight;
                    }}
                }});
        }}
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
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if request.method == "POST":
        senha = request.form.get("senha", "")
        if senha == PAINEL_PASSWORD:
            # Regenera sessão para evitar fixation
            session.clear()
            session["logged_in"] = True
            log_message("Acesso autorizado ao painel de controle.", "INFO")
            return redirect("/")
        log_message("Tentativa de acesso não autorizada.", "WARN")
        return render_template_string(LOGIN_HTML, erro="ACESSO NEGADO: SENHA INCORRETA")
    return render_template_string(LOGIN_HTML)


@app.route("/logout")
def logout() -> str:
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def index() -> str:
    config = load_dynamic_config()
    return render_template_string(DASHBOARD_HTML, config=config)


@app.route("/api/data")
@login_required
def api_data():
    with logs_lock:
        logs_copia = list(app_logs)

    return jsonify({"status": bot_status, "logs": logs_copia})


@app.route("/update_config", methods=["POST"])
@login_required
def update_config():
    try:
        novo_intervalo = int(request.form.get("intervalo", 120))
    except (TypeError, ValueError):
        novo_intervalo = 120

    novo_config = {
        "telegram_token": request.form.get("telegram_token", "").strip(),
        "destinos_telegram": request.form.get("destinos_telegram", "").strip(),
        "intervalo": novo_intervalo,
        "amazon_tag": request.form.get("amazon_tag", "").strip(),
        "mercado_livre_tag": request.form.get("mercado_livre_tag", "").strip(),
        "blacklist": request.form.get("blacklist", "").strip(),
        "whitelist": request.form.get("whitelist", "").strip(),
    }
    atual = load_dynamic_config()
    novo_config["rss_url"] = atual.get("rss_url", "https://www.promobit.com.br/feed/")

    save_dynamic_config(novo_config)
    log_message("Parâmetros do sistema reconfigurados com sucesso.", "INFO")
    return redirect("/")


@app.route("/action/control", methods=["POST"])
@login_required
def bot_control():
    action = request.form.get("action")
    if action == "toggle_pause":
        bot_status["is_paused"] = not bot_status["is_paused"]
        estado = "Pausado" if bot_status["is_paused"] else "Retomado"
        log_message(
            f"Sistema Operacional: {estado}.",
            "WARN" if bot_status["is_paused"] else "INFO",
        )
    elif action == "force_run":
        bot_status["force_run"] = True
        log_message("Protocolo de raspagem forçada ativado pelo usuário.", "INFO")
    elif action == "check_dead_links":
        config = load_dynamic_config()
        threading.Thread(target=verificar_links_mortos, args=(config,), daemon=True).start()

    return redirect("/")


@app.route("/health")
def health():
    return jsonify({"status": "online", "bot_paused": bot_status["is_paused"]})


if __name__ == "__main__":
    # Thread do núcleo do bot
    thread_bot = threading.Thread(target=loop_principal, daemon=True)
    thread_bot.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
