Esse é o `bot_cloud.py` completo e já corrigido para substituir a versão antiga que estava truncada no repositório. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/124023683/b741cf92-c2fa-4aba-b742-66e65b0f4bba/bot_cloud.py?AWSAccessKeyId=ASIA2F3EMEYEXXQKXPLX&Signature=ydxAObQrK%2Fg0CN5FANrEMn2hh7Q%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIj%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCM%2FNE1%2Fr2U1fP3ff82zuOZz%2BcnANca6ESIYixJKL8x6wIgY5vRafM6PMFl8mJopAXxLsnEowxrGDSKjCo12lgVTEQq8wQIUBABGgw2OTk3NTMzMDk3MDUiDH%2FZ6A07U0P%2BimSbhirQBMinaJaVYVQK1QCjqtj5JT4q6phvzxzxfxpXrlLav3hZpSLSLHPIKMlX8oTAT%2FViPaKJ3nXVsf3mUPHLg%2BOgEgOFpFTC6hKWMwz9z5i%2BJytvlLyVYqlJ%2FT5R1HPZBXKFLY46GT7kxEP06G65zV8yYVyKk8P%2FeyMgZsIGTiApRQdafbmddlJwg%2BKpoHTPyUmxC9qvXB8tHUFOewcaFE34oI4kXyrYBeFgItGZgMwmWvhbDXpHo0AOPRW1DG%2BcASWTTLdBYhqJaJZ2oefsJ2Rmzucw5OLqtYh0QHpUcTh4nRQdLJ0xftbakJI7PvecGe6jbtdEYvE9MQRKET85n7zgJdP92j5l9MxNM%2Bd4JYu8oaPifuc0jtuxxmTEV9iIbnH%2BRp%2FnmEuTCBSD64v0OcYctYNxGmvf9%2FY9HP%2B4zioTfFgKvcKnGtF76rKdSatvOTb5sf8oGHrX12UvcEUu4D1OgwfwSXNvnSnSWYa%2BEz6svzjpoUU1C89xOIDMmy410MRG6%2Ba0L1KZi7ZMYhVG6BDxmE8yNHlXyTX9ulrZ%2FUMJlVWqeZ8GO%2FKQ5oYhTJX%2FpInN93%2FovNAnzbAJ4u8Ehhc1ry8u5vbwnjPy9lldZcUZELRQyi3wK0ilY0JGaTseW5Zr%2Bm8niHNyX8KljGOhMS1tlNHFQcoSVpVYFwXwzUqeYa662BM5y2AqGGcyuyhoEeDsRlirPnycilRzXpEnYsrX3e9Nqx%2FmuBTHuxenUkISk57alBOnrI0953UShBbg00ePfOfPu61aMZXruOhoVy8IDT4wgs3G1AY6mAEd9FDRmkdoKDeqPb%2F%2FpScQFkaTy%2FT2W3xMlEzzSbS2GxMqmp2ltl0Ip352Ui9Rk5qNS%2BF08KmI%2FEVtdGQR7u9deomXrYxagOIcLeFwgYMvn6x4pbr04OgD0dFB8hro0Y55SMBH%2Bx4xFotzthsXNqxZBF90xtg2jqJJcnEcPYXW%2BU9tybf8uj1WEirle0EatXKflpDE1g2B3Q%3D%3D&Expires=1787933781)

```python
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

        if any(
            hostname == d or hostname.endswith(f".{d}")
            for d in ["amazon.com.br", "amazon.com"]
        ):
            tag = config.get("amazon_tag")
            if tag:
                q = parse_qs(parsed.query)
                q["tag"] = [tag]
                return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

        elif any(
            hostname == d or hostname.endswith(f".{d}")
            for d in ["mercadolivre.com.br", "mercadolivre.com"]
        ):
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
    chat_ids = list(
        dict.fromkeys([d.strip() for d in raw_destinos.split(",") if d.strip()])
    )

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
                            {
                                "chat_id": chat_id,
                                "message_id": data["result"]["message_id"],
                            }
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


def extrair_desconto(titulo: str) -> int:
    """Tenta extrair um número de % de desconto do título.

    Ex.: 'TV 55\" 40% OFF' -> 40
    """
    if not titulo:
        return 0
    m = re.search(r"(\d{1,3})\s*%", titulo)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def parse_lojas_prioridade(config: dict) -> dict[str, int]:
    """Converte string 'dominio:peso,dominio2:peso2' em dict."""
    mapping: dict[str, int] = {}
    raw = config.get("lojas_prioridade", "") or ""
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            dom, peso = item.split(":", 1)
            dom = dom.strip().lower()
            try:
                mapping[dom] = int(peso.strip())
            except ValueError:
                continue
        else:
            mapping[item.lower()] = 1
    return mapping


def peso_por_dominio(link: str, lojas_map: dict[str, int]) -> int:
    """Retorna o peso configurado para o domínio da oferta."""
    try:
        host = urlparse(link).netloc.lower()
    except Exception:
        return 0
    for dom, peso in lojas_map.items():
        if host == dom or host.endswith("." + dom):
            return peso
    return 0


def scrape_cupons_mercado_livre() -> list[dict]:
    """Raspa cupons do Mercado Livre (melhor esforço)."""
    cupons: list[dict] = []
    try:
        log_message("Buscando cupons do Mercado Livre...", "INFO")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(
            "https://www.mercadolivre.com.br/cupons", headers=headers, timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml")
            elementos = soup.find_all(
                class_=lambda x: bool(x and "coupon" in x.lower())
            )

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
# MÓDULO AUTO-CLEAN (Teste de links mortos) -- somente link limpo
# ============================================================================


def verificar_links_mortos(config: dict) -> None:
    """Varre as mensagens ativas e marca ofertas mortas, usando apenas o link limpo.

    Nunca chama URL de afiliado, apenas o link original da loja, evitando
    qualquer possibilidade de cookie stuffing.
    """
    global is_cleaning_links

    with clean_lock:
        if is_cleaning_links:
            log_message(
                "Varredura abortada: já existe uma limpeza em andamento.", "WARN"
            )
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
        sobreviventes: list[dict] = []
        headers = {"User-Agent": "Mozilla/5.0"}
        url_edit = f"https://api.telegram.org/bot{bot_token}/editMessageText"

        for item in ativas:
            link = item.get("link", "")
            if not link.startswith("http"):
                sobreviventes.append(item)
                continue

            is_dead = False
            try:
                resp = requests.get(
                    link, headers=headers, timeout=10, allow_redirects=True
                )
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
                                "Rate limit 429 ao editar mensagem. "
                                f"Aguardando {retry_after}s...",
                                "WARN",
                            )
                            time.sleep(retry_after)
                            requests.post(url_edit, json=payload, timeout=10)
                        elif resp_edit.status_code != 200:
                            log_message(
                                f"Falha ao editar mensagem morta: {resp_edit.text}",
                                "ERROR",
                            )
                        time.sleep(1)
                    except Exception as exc:
                        log_message(f"Erro ao editar mensagem: {exc}", "ERROR")
            else:
                sobreviventes.append(item)

        save_active_msgs(sobreviventes)
        bot_status["status"] = "Sistema Operacional"
        log_message("Varredura de estoque finalizada.", "INFO")
    finally:
        with clean_lock:
            is_cleaning_links = False


# ============================================================================
# EXECUÇÃO DO CICLO PRINCIPAL (raspagem -> fila de pendentes)
# ============================================================================


def executar_ciclo(config: dict) -> None:
    bot_status["status"] = "Raspando dados..."
    log_message("Iniciando varredura de RSS e Cupons", "INFO")

    posted_ids = load_posted_ids(POSTED_FILE)
    cupons_ids = load_posted_ids(CUPONS_FILE)
    active_msgs = load_active_msgs()
    pending = load_pending_offers()

    rss_raw = config.get("rss_url", "").strip()
    rss_urls = [u.strip() for u in rss_raw.split(",") if u.strip()]

    lojas_map = parse_lojas_prioridade(config)
    try:
        min_desconto = int(config.get("min_desconto", 0))
    except (TypeError, ValueError):
        min_desconto = 0

    ofertas_novas: list[tuple[int, str, str, str]] = []  # (score, id, titulo, link)

    # 1) Ofertas via RSS -> fila de pendentes
    if rss_urls:
        for rss_url in rss_urls:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(rss_url, headers=headers, timeout=15)
                feed = feedparser.parse(resp.content)

                for entry in reversed(feed.entries):
                    raw_title = entry.get("title", "Oferta")
                    link = entry.get("link", "").strip()
                    entry_id = entry.get("id") or link
                    unique_id = generate_unique_id(raw_title, entry_id)

                    if unique_id in posted_ids or not link.startswith("http"):
                        continue

                    if not pass_filters(raw_title, config):
                        posted_ids.append(unique_id)
                        continue

                    desconto = extrair_desconto(raw_title)
                    if desconto < min_desconto:
                        posted_ids.append(unique_id)
                        continue

                    peso_loja = peso_por_dominio(link, lojas_map) if lojas_map else 0
                    score = peso_loja * 100 + desconto

                    ofertas_novas.append((score, unique_id, raw_title, link))
            except Exception as exc:
                log_message(f"Falha na busca de RSS em {rss_url}: {exc}", "ERROR")

    if ofertas_novas:
        for score, unique_id, raw_title, link in sorted(
            ofertas_novas, key=lambda x: x[0], reverse=True
        ):
            if any(o.get("id") == unique_id for o in pending):
                continue
            pending.append(
                {
                    "id": unique_id,
                    "titulo": raw_title,
                    "link": link,
                    "score": score,
                    "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            posted_ids.append(unique_id)
            log_message(f"Oferta enfileirada para moderação: {raw_title}", "INFO")

    # 2) Cupons ML (mantidos como envio direto; se quiser, pode migrar para fila também)
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
    save_pending_offers(pending)
    save_active_msgs(active_msgs)

    bot_status["ultima_execucao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot_status["status"] = "Sistema Operacional"
    log_message("Ciclo de processamento concluído.", "INFO")


def loop_principal() -> None:
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
# TEMPLATES HTML (Painel + Moderação)
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
        {% if erro %}<div class="alert alert-danger" style="background: rgba(255,0,60,0.2); border-color: var(--neon-red); color: #fff;">{{ erro }}</div>{% endif %}
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
            <div class="d-flex gap-2">
                <a href="/moderation" class="btn btn-cyber btn-sm">MODERAÇÃO</a>
                <a href="/logout" class="btn btn-cyber-danger btn-sm">DESCONECTAR</a>
            </div>
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
                            <div class="col-4 border-end border-secondary">
                                <span class="text-muted d-block" style="font-size: 0.8rem; letter-spacing: 1px;">ÚLTIMA SINCRONIZAÇÃO</span>
                                <strong id="lbl-ultima" style="font-size: 1.2rem; color: #fff;">--</strong>
                            </div>
                            <div class="col-4 border-end border-secondary">
                                <span class="text-muted d-block" style="font-size: 0.8rem; letter-spacing: 1px;">TRANSMISSÕES HOJE</span>
                                <strong id="lbl-ofertas" style="font-size: 1.2rem; color: var(--neon-cyan);">--</strong>
                            </div>
                            <div class="col-4">
                                <span class="text-muted d-block" style="font-size: 0.8rem; letter-spacing: 1px;">PENDENTES</span>
                                <strong id="lbl-pendentes" style="font-size: 1.2rem; color: var(--neon-yellow);">--</strong>
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
                                <input type="password" class="form-control" name="telegram_token" value="{{ config.telegram_token }}" placeholder="[ PROTEGIDO ]">
                            </div>
                            <div class="mb-4">
                                <label class="form-label">IDs DE DESTINO (CHATS)</label>
                                <input type="text" class="form-control" name="destinos_telegram" value="{{ config.destinos_telegram }}" placeholder="-100..., -100...">
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// PARAMETRIZAÇÃO</h6>
                            <div class="mb-3 d-flex align-items-center">
                                <label class="form-label me-3 mb-0">DELAY (MIN)</label>
                                <input type="number" class="form-control w-25 text-center" name="intervalo" value="{{ config.intervalo }}">
                            </div>
                            <div class="mb-4 d-flex align-items-center">
                                <label class="form-label me-3 mb-0">% DESCONTO MÍN</label>
                                <input type="number" class="form-control w-25 text-center" name="min_desconto" value="{{ config.min_desconto }}">
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// ROTAS DE AFILIADO</h6>
                            <div class="row mb-4">
                                <div class="col-6">
                                    <label class="form-label">AMAZON TAG</label>
                                    <input type="text" class="form-control" name="amazon_tag" value="{{ config.amazon_tag }}">
                                </div>
                                <div class="col-6">
                                    <label class="form-label">MERCADO LIVRE (UTM)</label>
                                    <input type="text" class="form-control" name="mercado_livre_tag" value="{{ config.mercado_livre_tag }}">
                                </div>
                            </div>

                            <h6 class="text-muted mb-3" style="letter-spacing: 1px;">// ALGORITMO DE FILTRAGEM</h6>
                            <div class="mb-3">
                                <label class="form-label" style="color: var(--neon-red);">BLACKLIST (DESCARTAR)</label>
                                <input type="text" class="form-control" name="blacklist" value="{{ config.blacklist }}" placeholder="ex: internacional, usado">
                            </div>
                            <div class="mb-3">
                                <label class="form-label" style="color: var(--neon-green);">WHITELIST (REQUERIDO)</label>
                                <input type="text" class="form-control" name="whitelist" value="{{ config.whitelist }}" placeholder="[ DEIXE VAZIO PARA DESATIVAR ]">
                            </div>
                            <div class="mb-4">
                                <label class="form-label">LOJAS PRIORITÁRIAS (dominio:peso)</label>
                                <input type="text" class="form-control" name="lojas_prioridade" value="{{ config.lojas_prioridade }}" placeholder="amazon.com.br:3,mercadolivre.com.br:2">
                            </div>

                            <button type="submit" class="btn btn-cyber-success w-100 py-2 mt-2">GRAVAR PARÂMETROS</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function fetchStatus() {
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('lbl-ultima').innerText = data.status.ultima_execucao;
                    document.getElementById('lbl-ofertas').innerText = data.status.ofertas_enviadas_hoje;
                    document.getElementById('lbl-pendentes').innerText = data.pendentes || 0;

                    const btnPause = document.getElementById('btn-pause');
                    if(data.status.is_paused) {
                        btnPause.innerText = "▶ INICIAR SISTEMA";
                        btnPause.className = "btn btn-cyber px-4";
                        document.getElementById('badge-status').innerText = "SISTEMA PAUSADO";
                        document.getElementById('badge-status').className = "badge badge-glow-warning";
                    } else {
                        btnPause.innerText = "⏸ PAUSAR SISTEMA";
                        btnPause.className = "btn btn-cyber-warning px-4";
                        document.getElementById('badge-status').innerText = data.status.status.toUpperCase();
                        document.getElementById('badge-status').className = "badge badge-glow-success";
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

MODERATION_HTML = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>MODERAÇÃO // Ofertas Pendentes</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    {GLOBAL_CSS}
</head>
<body>
    <nav class="navbar navbar-dark navbar-cyber mb-4 py-3">
        <div class="container-fluid px-4">
            <span class="navbar-brand mb-0 h1">QUEUE.MOD // PENDENTES</span>
            <div class="d-flex gap-2">
                <a href="/" class="btn btn-cyber btn-sm">PAINEL</a>
                <a href="/logout" class="btn btn-cyber-danger btn-sm">DESCONECTAR</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="glass-card">
            <div class="glass-header">
                FILA DE APROVAÇÃO MANUAL
            </div>
            <div class="card-body p-4">
                {% if pendentes %}
                <div class="table-responsive">
                    <table class="table table-dark table-striped align-middle">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Título</th>
                                <th>Link</th>
                                <th>Score</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for o in pendentes %}
                            <tr>
                                <td style="font-size: 0.75rem;">{{ o.id }}</td>
                                <td>{{ o.titulo }}</td>
                                <td style="font-size: 0.75rem;">{{ o.link }}</td>
                                <td>{{ o.score }}</td>
                                <td class="d-flex flex-wrap gap-2">
                                    <a href="{{ o.link }}" target="_blank" class="btn btn-sm btn-cyber">Ver Oferta</a>
                                    <form method="POST" action="/moderation/approve/{{ o.id }}">
                                        <button class="btn btn-sm btn-cyber-success" type="submit">Aprovar &amp; Publicar</button>
                                    </form>
                                    <form method="POST" action="/moderation/reject/{{ o.id }}">
                                        <button class="btn btn-sm btn-cyber-danger" type="submit">Rejeitar</button>
                                    </form>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-muted mb-0">Nenhuma oferta pendente no momento.</p>
                {% endif %}
            </div>
        </div>
    </div>
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


@app.route("/moderation")
@login_required
def moderation_view() -> str:
    pendentes = load_pending_offers()
    return render_template_string(MODERATION_HTML, pendentes=pendentes)


@app.route("/moderation/approve/<oferta_id>", methods=["POST"])
@login_required
def moderation_approve(oferta_id: str):
    config = load_dynamic_config()
    pendentes = load_pending_offers()
    active_msgs = load_active_msgs()
    posted_ids = load_posted_ids(POSTED_FILE)

    restantes = []
    aprovadas = []

    for o in pendentes:
        if o.get("id") == oferta_id:
            aprovadas.append(o)
        else:
            restantes.append(o)

    base_url = request.url_root.rstrip("/")

    for oferta in aprovadas:
        raw_title = oferta.get("titulo", "Oferta")
        link = oferta.get("link", "")
        if not link.startswith("http"):
            continue

        safe_title = safe_tg_html(raw_title)
        redirect_url = f"{base_url}/r/{oferta_id}"
        safe_url = safe_tg_html(redirect_url)

        msg_html = (
            "🎁 <b>PROMOÇÃO</b>\n\n" f"<b>{safe_title}</b>\n\n" f"🔗 <a href='{safe_url}'>Ver Oferta</a>"
        )

        env, falhas, msg_data = send_telegram_message(msg_html, config)
        if env > 0:
            if oferta_id not in posted_ids:
                posted_ids.append(oferta_id)
            bot_status["ofertas_enviadas_hoje"] += 1
            log_message(f"Oferta aprovada e publicada: {raw_title}", "INFO")
            active_msgs.append(
                {
                    "id": oferta_id,
                    "link": link,  # link LIMPO
                    "original_text": msg_html,
                    "tg_msgs": msg_data,
                }
            )
        elif falhas > 0:
            log_message(f"Falha ao publicar oferta aprovada: {raw_title}", "ERROR")

    save_pending_offers(restantes)
    save_active_msgs(active_msgs)
    save_posted_ids(posted_ids, POSTED_FILE)
    return redirect("/moderation")


@app.route("/moderation/reject/<oferta_id>", methods=["POST"])
@login_required
def moderation_reject(oferta_id: str):
    pendentes = load_pending_offers()
    restantes = [o for o in pendentes if o.get("id") != oferta_id]
    save_pending_offers(restantes)
    log_message(f"Oferta rejeitada manualmente. ID={oferta_id}", "WARN")
    return redirect("/moderation")


@app.route("/r/<oferta_id>")
def redirect_oferta(oferta_id: str):
    """Rota de redirecionamento segura.

    - Usa somente clique do usuário para chegar ao link de afiliado.
    - Registra estatísticas de clique antes de redirecionar.
    """
    active = load_active_msgs()
    oferta = next((o for o in active if o.get("id") == oferta_id), None)

    if not oferta:
        log_message(f"Clique em oferta desconhecida: {oferta_id}", "WARN")
        return redirect("https://www.google.com")

    link_limpo = oferta.get("link", "")
    if not link_limpo.startswith("http"):
        log_message(f"Link inválido em oferta {oferta_id}: {link_limpo}", "ERROR")
        return redirect("https://www.google.com")

    config = load_dynamic_config()
    affiliate_link = convert_to_affiliate_link(link_limpo, config)

    stats = load_click_stats()
    hoje = datetime.now().strftime("%Y-%m-%d")
    host = urlparse(link_limpo).netloc.lower()

    oferta_stats = stats.get(oferta_id) or {
        "id": oferta_id,
        "titulo": oferta.get("original_text", "")[:120],
        "link": link_limpo,
        "dominio": host,
        "total_cliques": 0,
        "cliques_por_dia": {},
    }

    oferta_stats["total_cliques"] = oferta_stats.get("total_cliques", 0) + 1
    por_dia = oferta_stats.get("cliques_por_dia", {})
    por_dia[hoje] = por_dia.get(hoje, 0) + 1
    oferta_stats["cliques_por_dia"] = por_dia

    stats[oferta_id] = oferta_stats
    save_click_stats(stats)

    log_message(f"Clique registrado em oferta {oferta_id} ({host})", "INFO")

    return redirect(affiliate_link, code=302)


@app.route("/api/data")
@login_required
def api_data():
    with logs_lock:
        logs_copia = list(app_logs)
    pendentes = load_pending_offers()
    return jsonify({"status": bot_status, "logs": logs_copia, "pendentes": len(pendentes)})


@app.route("/update_config", methods=["POST"])
@login_required
def update_config():
    try:
        novo_intervalo = int(request.form.get("intervalo", 120))
    except (TypeError, ValueError):
        novo_intervalo = 120

    try:
        novo_min_desc = int(request.form.get("min_desconto", 0))
    except (TypeError, ValueError):
        novo_min_desc = 0

    novo_config = {
        "telegram_token": request.form.get("telegram_token", "").strip(),
        "destinos_telegram": request.form.get("destinos_telegram", "").strip(),
        "intervalo": novo_intervalo,
        "min_desconto": novo_min_desc,
        "amazon_tag": request.form.get("amazon_tag", "").strip(),
        "mercado_livre_tag": request.form.get("mercado_livre_tag", "").strip(),
        "blacklist": request.form.get("blacklist", "").strip(),
        "whitelist": request.form.get("whitelist", "").strip(),
        "lojas_prioridade": request.form.get("lojas_prioridade", "").strip(),
    }
    atual = load_dynamic_config()
    novo_config["rss_url"] = atual.get(
        "rss_url", "https://www.promobit.com.br/feed/"
    )

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
        threading.Thread(
            target=verificar_links_mortos, args=(config,), daemon=True
        ).start()

    return redirect("/")


@app.route("/health")
def health():
    return jsonify({"status": "online", "bot_paused": bot_status["is_paused"]})


if __name__ == "__main__":
    thread_bot = threading.Thread(target=loop_principal, daemon=True)
    thread_bot.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
```
