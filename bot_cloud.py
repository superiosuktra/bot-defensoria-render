#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

PAINEL_PASSWORD = os.getenv("PAINEL_PASSWORD", "admin123")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "chave_secreta_padrao_123")

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
CONFIG_FILE = "config.json"
ACTIVE_MSGS_FILE = "mensagens_ativas.json"
MAX_IDS_HISTORICO = 5000

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

bot_status = {
    "status": "Iniciando Sistema...",
    "is_paused": False,
    "force_run": False,
    "ultima_execucao": "N/A",
    "ofertas_enviadas_hoje": 0,
}

app_logs = deque(maxlen=100)
time_since_last_run = 0

file_lock = threading.Lock()
logs_lock = threading.Lock()
clean_lock = threading.Lock()
is_cleaning_links = False

# ============================================================================
# GERENCIADORES DE DADOS
# ============================================================================

def load_dynamic_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    default_config = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
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
    with file_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)


def load_active_msgs():
    with file_lock:
        if os.path.exists(ACTIVE_MSGS_FILE):
            try:
                with open(ACTIVE_MSGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []


def save_active_msgs(data):
    with file_lock:
        try:
            with open(ACTIVE_MSGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log_message(f"Erro ao salvar mensagens ativas: {e}", "ERROR")

# ============================================================================
# FUNÇÕES DO BOT E REGRAS DE NEGÓCIO
# ============================================================================

def log_message(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = "#00ff41"
    if level == "ERROR":
        color = "#ff003c"
    elif level == "WARN":
        color = "#ffea00"

    log_str = f"[{timestamp}] <span style='color:{color}'>[{level}] {message}</span>"
    print(f"[{timestamp}] [{level}] {message}")

    with logs_lock:
        app_logs.append(log_str)


def safe_tg_html(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pass_filters(titulo: str, config: dict) -> bool:
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


def load_posted_ids(filename: str) -> list:
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(ids))
    except Exception:
        return []


def save_posted_ids(ids: list, filename: str):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for item_id in ids[-MAX_IDS_HISTORICO:]:
                f.write(f"{item_id}\n")
    except Exception:
        pass


def generate_unique_id(text: str, url: str) -> str:
    return hashlib.sha256(f"{text.strip()}|{url.strip()}".lower().encode("utf-8")).hexdigest()[:16]


def convert_to_affiliate_link(url: str, config: dict) -> str:
    if not url or not isinstance(url, str):
        return url
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
    except Exception:
        return url


def send_telegram_message(text_html: str, config: dict) -> tuple:
    bot_token = config.get("telegram_token", "").strip()
    raw_destinos = config.get("destinos_telegram", "")
    chat_ids = list(dict.fromkeys([d.strip() for d in raw_destinos.split(",") if d.strip()]))

    if not bot_token or not chat_ids:
        return (0, 0, [])

    enviados, falhas = 0, 0
    mensagens_enviadas = []
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for chat_id in chat_ids:
        try:
            payload = {"chat_id": chat_id, "text": text_html, "parse_mode": "HTML"}
            resp = requests.post(url, json=payload, timeout=15)

            if resp.status_code == 200:
                enviados += 1
                msg_data = resp.json()
                mensagens_enviadas.append({"chat_id": chat_id, "message_id": msg_data["result"]["message_id"]})
            elif resp.status_code == 429:
                time.sleep(resp.json().get("parameters", {}).get("retry_after", 5))
                resp_retry = requests.post(url, json=payload, timeout=15)
                if resp_retry.status_code == 200:
                    enviados += 1
                    mensagens_enviadas.append({"chat_id": chat_id, "message_id": resp_retry.json()["result"]["message_id"]})
                else:
                    falhas += 1
                    log_message(f"Falha API Telegram após retry ({chat_id}): {resp_retry.text}", "ERROR")
            else:
                falhas += 1
                log_message(f"Falha API Telegram ({chat_id}): {resp.text}", "ERROR")
            time.sleep(1)
        except Exception as e:
            log_message(f"Erro de Conexão Telegram: {e}", "ERROR")
            falhas += 1

    return (enviados, falhas, mensagens_enviadas)


def scrape_cupons_mercado_livre() -> list:
    cupons = []
    try:
        log_message("Buscando cupons do Mercado Livre...", "INFO")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get("https://www.mercadolivre.com.br/cupons", headers=headers, timeout=15)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml")
            elementos = soup.find_all(class_=lambda x: bool(x and "coupon" in x.lower()))

            for elem in elementos[:10]:
                texto = elem.get_text(separator=" ", strip=True)
                if texto:
                    cupons.append({
                        "titulo": texto[:120],
                        "loja": "Mercado Livre",
                        "link": "https://www.mercadolivre.com.br/cupons"
                    })
    except Exception as e:
        log_message(f"Falha ao raspar cupons do ML: {e}", "WARN")

    return cupons

# ============================================================================
# MÓDULO AUTO-CLEAN
# ============================================================================

def verificar_links_mortos(config):
    global is_cleaning_links

    with clean_lock:
        if is_cleaning_links:
            log_message("Varredura abortada: Já existe uma limpeza em andamento.", "WARN")
            return
        is_cleaning_links = True

    bot_token = config.get("telegram_token", "").strip()
    if not bot_token:
        log_message("Auto-Clean abortado: Sem token.", "WARN")
        with clean_lock:
            is_cleaning_links = False
        return

    try:
        bot_status["status"] = "Verificando links mortos..."
        log_message("Iniciando varredura de estoque...")

        ativas = load_active_msgs()
        ativas_para_manter = []
        headers = {"User-Agent": "Mozilla/5.0"}

        for item in ativas:
            link = item["link"]
            is_dead = False

            try:
                resp = requests.get(link, headers=headers, timeout=10, allow_redirects=True)
                if resp.status_code in [404, 410]:
                    is_dead = True
                elif resp.status_code == 200:
                    html_lower = resp.text.lower()
                    if any(p in html_low
