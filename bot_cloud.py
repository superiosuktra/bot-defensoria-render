#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bot de ofertas/cupons com painel Flask e foco em Compliance.

Principais cuidados:
- Nenhuma oferta vai direto para o Telegram: tudo passa por FILA DE MODERAÇÃO.
- Clique do usuário passa pela rota /r/<id>, que registra estatísticas e só então
  redireciona para o link de afiliado (cookie apenas após clique humano).
- O verificador de links mortos usa apenas o link limpo da loja, nunca URLs de
  afiliado, evitando qualquer risco de cookie stuffing.
"""

import os
import re
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
from flask import (
    Flask,
    request,
    render_template_string,
    redirect,
    jsonify,
    session,
)
from functools import wraps

load_dotenv()

# ============================================================================
# CONFIGURAÇÕES FIXAS E FLASK
# ============================================================================

PAINEL_PASSWORD = os.getenv("PAINEL_PASSWORD")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

if not PAINEL_PASSWORD or not FLASK_SECRET_KEY:
    raise RuntimeError(
        "PAINEL_PASSWORD e FLASK_SECRET_KEY são obrigatórios. "
        "Defina-os no .env ou nas variáveis de ambiente."
    )

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
CONFIG_FILE = "config.json"
ACTIVE_MSGS_FILE = "mensagens_ativas.json"
PENDING_FILE = "pendentes.json"
CLICK_STATS_FILE = "click_stats.json"
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
                data.setdefault(
                    "rss_url",
                    os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/"),
                )
                data.setdefault("intervalo", 120)
                data.setdefault("blacklist", "internacional, usado, reembalado")
                data.setdefault("whitelist", "")
                data.setdefault("lojas_prioridade", "")
                data.setdefault("min_desconto", 0)
                return data
        except Exception as exc:
            log_message(f"Falha ao ler config.json, recriando: {exc}", "WARN")

    default_config = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "destinos_telegram": (
            (os.getenv("TELEGRAM_CANAIS", "") + "," + os.getenv("TELEGRAM_GRUPOS", ""))
            .strip(",")
        ),
        "amazon_tag": os.getenv("AFFILIATE_TAG_AMAZON", ""),
        "mercado_livre_tag": os.getenv("AFFILIATE_TAG_OUTROS", ""),
        "rss_url": os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/"),
        "intervalo": 120,
        "blacklist": "internacional, usado, reembalado",
        "whitelist": "",
        # priorização por loja e desconto
        "lojas_prioridade": "amazon.com.br:3,mercadolivre.com.br:2,magazineluiza.com.br:2,shopee.com.br:2,aliexpress.com:1",
        "min_desconto": 0,
    }
    save_dynamic_config(default_config)
    return default_config


def save_dynamic_config(config_data: dict) -> None:
    with file_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)


def load_active_msgs() -> list[dict]:
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
    with file_lock:
        try:
            with open(ACTIVE_MSGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data[-100:], f, indent=4, ensure_ascii=False)
        except Exception as exc:
            log_message(f"Erro ao salvar mensagens ativas: {exc}", "ERROR")


def load_pending_offers() -> list[dict]:
    with file_lock:
        if os.path.exists(PENDING_FILE):
            try:
                with open(PENDING_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as exc:
                log_message(f"Falha ao ler {PENDING_FILE}: {exc}", "WARN")
        return []


def save_pending_offers(data: list[dict]) -> None:
    with file_lock:
        try:
            with open(PENDING_FILE, "w", encoding="utf-8") as f:
                json.dump(data[-500:], f, indent=4, ensure_ascii=False)
        except Exception as exc:
            log_message(f"Erro ao salvar pendentes: {exc}", "ERROR")


def load_click_stats() -> dict:
    with file_lock:
        if os.path.exists(CLICK_STATS_FILE):
            try:
                with open(CLICK_STATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                log_message(f"Falha ao ler {CLICK_STATS_FILE}: {exc}", "WARN")
        return {}


def save_click_stats(data: dict) -> None:
    with file_lock:
        try:
            with open(CLICK_STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as exc:
            log_message(f"Erro ao salvar estatísticas de clique: {exc}", "ERROR")


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

# ============================================================================
# FUNÇÕES DO BOT E REGRAS DE NEGÓCIO
# ============================================================================

def log_message(message: str, level: str = "INFO") -> None:
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
    """Escapa HTML básico para mensagens em parse_mode=HTML."""
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

    blacklist = [
        w.strip().lower() for w in config.get("blacklist", "").split(",") if w.strip()
    ]
    if any(b in t_lower for b in blacklist):
        log_message(f"Bloqueado pela Blacklist: {titulo}", "WARN")
        return False

    whitelist = [
        w.strip().lower() for w in config.get("whitelist", "").split(",") if w.strip()
    ]
    if whitelist and not any(w in t_lower for w in whitelist):
        log_message(f"Ignorado (Fora da Whitelist): {titulo}", "WARN")
        return False
    return True


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
