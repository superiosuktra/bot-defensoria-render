#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ROBÔ DE OFERTAS E CUPONS - VERSÃO DEFENSIVA REVISADA
"""

import os
import time
import json
import hashlib
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CANAIS = [c.strip() for c in os.getenv("TELEGRAM_CANAIS", "").split(",") if c.strip()]
TELEGRAM_GRUPOS = [g.strip() for g in os.getenv("TELEGRAM_GRUPOS", "").split(",") if g.strip()]
TODOS_DESTINOS = list(dict.fromkeys(TELEGRAM_CANAIS + TELEGRAM_GRUPOS))

RSS_FEED_URL = os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/").strip()
AFFILIATE_TAG_AMAZON = os.getenv("AFFILIATE_TAG_AMAZON", "").strip()
AFFILIATE_TAG_OUTROS = os.getenv("AFFILIATE_TAG_OUTROS", "").strip()

INTERVALO_VERIFICACAO = int(os.getenv("INTERVALO_VERIFICACAO", "120"))  # Em minutos

REQUEST_TIMEOUT = 15
TELEGRAM_TIMEOUT = 15

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
DADOS_SITE = "dados.json"
MAX_IDS_HISTORICO = 5000 

# ============================================================================
# SERVIDOR KEEP-ALIVE PARA REPLIT E UPTIMEROBOT
# ============================================================================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")
    
    def log_message(self, format, *args):
        # Silencia logs HTTP para não poluir o terminal
        pass

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    log_message("Servidor Keep-Alive iniciado.")

# ============================================================================
# FUNÇÕES AUXILIARES E DE SEGURANÇA
# ============================================================================

def log_message(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def safe_tg_html(text: str) -> str:
    """Escapa apenas o estritamente necessário para o Telegram não quebrar o HTML."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def load_posted_ids(filename: str) -> list:
    """Carrega os IDs mantendo a ordem de inserção (cronológica)."""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
            # Remove duplicatas preservando a ordem
            ids = list(dict.fromkeys(ids))
            log_message(f"Carregados {len(ids)} IDs de {filename}")
            return ids
    except Exception as e:
        log_message(f"Erro ao ler {filename}: {e}", "ERROR")
        return []

def save_posted_ids(ids: list, filename: str):
    """Salva a lista mantendo apenas os mais recentes com fatiamento seguro."""
    try:
        trimmed_ids = ids[-MAX_IDS_HISTORICO:]
        with open(filename, "w", encoding="utf-8") as f:
            for item_id in trimmed_ids:
                f.write(f"{item_id}\n")
    except Exception as e:
        log_message(f"Erro ao salvar histórico em {filename}: {e}", "ERROR")

def generate_unique_id(text: str, url: str) -> str:
    combined = f"{text.strip()}|{url.strip()}".lower()
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

def convert_to_affiliate_link(url: str) -> str:
    if not url or not isinstance(url, str):
        return url
    try:
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower()

        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in ["amazon.com.br", "amazon.com"]):
            if AFFILIATE_TAG_AMAZON:
                query_params = parse_qs(parsed.query)
                query_params["tag"] = [AFFILIATE_TAG_AMAZON]
                new_query = urlencode(query_params, doseq=True)
                return urlunparse(parsed._replace(query=new_query))

        elif any(hostname == domain or hostname.endswith(f".{domain}") for domain in ["mercadolivre.com.br", "mercadolivre.com"]):
            if AFFILIATE_TAG_OUTROS:
                query_params = parse_qs(parsed.query)
                query_params["utm_source"] = ["robo_ofertas"]
                new_query = urlencode(query_params, doseq=True)
                return urlunparse(parsed._replace(query=new_query))

        return url
    except Exception as e:
        log_message(f"Erro ao processar URL para afiliado: {e}", "ERROR")
        return url

def send_telegram_message(text_html: str, chat_ids: list) -> tuple:
    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        return (0, 0)

    enviados, falhas = 0, 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in chat_ids:
        try:
            payload = {
                "chat_id": chat_id,
                "text": text_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)

            if response.status_code == 200:
                enviados += 1
                log_message(f"Mensagem enviada com sucesso para {chat_id}")
            elif response.status_code == 429:
                falhas += 1
                retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                log_message(f"Rate limit atingido. Aguardando {retry_after}s...", "WARN")
                time.sleep(retry_after)
                # Tenta enviar novamente após aguardar
                requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
            else:
                falhas += 1
                log_message(f"Falha ao enviar para {chat_id}: status {response.status_code} - {response.text}", "ERROR")

            time.sleep(1) # Limite seguro do Telegram: ~1 msg por segundo por chat

        except requests.exceptions.RequestException as e:
            falhas += 1
            log_message(f"Erro de conexão ao enviar para {chat_id}: {e}", "ERROR")

    return (enviados, falhas)

# ============================================================================
# EXTRAÇÃO E SCRAPING
# ============================================================================

def fetch_rss_feed(url: str) -> list:
    try:
        log_message(f"Buscando feed RSS: {url}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        feed = feedparser.parse(response.content)
        log_message(f"Feed carregado: {len(feed.entries)} entradas")
        return feed.entries
    except Exception as e:
        log_message(f"Erro ao obter feed RSS: {e}", "ERROR")
        return []

def scrape_cupons_mercado_livre() -> list:
    cupons = []
    try:
        log_message("Buscando cupons do Mercado Livre...")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get("https://www.mercadolivre.com.br/cupons", headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "lxml")
        elementos = soup.find_all(class_=lambda x: bool(x and "coupon" in x.lower()))

        for elem in elementos[:10]:
            texto = elem.get_text(separator=" ", strip=True)
            if not texto:
                continue

            cupons.append({
                "titulo": texto[:120],
                "codigo": "",
                "loja": "Mercado Livre",
                "link": "https://www.mercadolivre.com.br/cupons",
                "desconto": ""
            })

        log_message(f"Encontrados {len(cupons)} elementos de cupom")
    except Exception as e:
        log_message(f"Falha ao raspar cupons do ML: {e}", "WARN")

    return cupons

# ============================================================================
# PERSISTÊNCIA DOS DADOS DO SITE
# ============================================================================

def load_site_data() -> dict:
    if os.path.exists(DADOS_SITE):
        try:
            with open(DADOS_SITE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ofertas": [], "cupons": [], "atualizado_em": ""}

def save_site_data(ofertas: list, cupons: list):
    try:
        dados = {
            "ofertas": ofertas[:50],
            "cupons": cupons[:50],
            "atualizado_em": datetime.now().isoformat(),
            "total_ofertas": len(ofertas),
            "total_cupons": len(cupons)
        }
        with open(DADOS_SITE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        log_message(f"Dados atualizados salvos em {DADOS_SITE}")
    except Exception as e:
        log_message(f"Erro ao salvar {DADOS_SITE}: {e}", "ERROR")

# ============================================================================
# CICLO PRINCIPAL
# ============================================================================

def executar_ciclo():
    log_message("=== Iniciando ciclo de verificação ===")

    posted_ids = load_posted_ids(POSTED_FILE)
    cupons_ids = load_posted_ids(CUPONS_FILE)
    site_data = load_site_data()

    ofertas_lista = site_data.get("ofertas", [])
    cupons_lista = site_data.get("cupons", [])

    # 1. Processar Ofertas RSS
    entries = fetch_rss_feed(RSS_FEED_URL)
    
    # Processamos em reverso para que as mais antigas entrem primeiro e as mais novas fiquem no topo
    for entry in reversed(entries):
        try:
            raw_title = entry.get("title", "Oferta sem título")
            link = entry.get("link", "").strip()
            entry_id = entry.get("id") or entry.get("guid") or link

            if not entry_id or not link.startswith("http"):
                continue

            unique_id = generate_unique_id(raw_title, entry_id)

            if unique_id not in posted_ids:
                affiliate_link = convert_to_affiliate_link(link)

                safe_title = safe_tg_html(raw_title)
                safe_link = affiliate_link

                msg = (
                    f"🎁 <b>PROMOÇÃO</b>\n\n"
                    f"<b>{safe_title}</b>\n\n"
                    f"🔗 <a href='{safe_link}'>Ver Oferta</a>"
                )

                enviados, _ = send_telegram_message(msg, TODOS_DESTINOS)
                if enviados > 0:
                    posted_ids.append(unique_id)
                    ofertas_lista.insert(0, {
                        "id": unique_id,
                        "titulo": raw_title,
                        "link": affiliate_link,
                        "data": datetime.now().isoformat(),
                        "fonte": "RSS Feed"
                    })
        except Exception as e:
            log_message(f"Erro ao processar item do RSS: {e}", "ERROR")

    # 2. Processar Cupons
    cupons = scrape_cupons_mercado_livre()
    for cupom in reversed(cupons):
        try:
            raw_titulo = cupom.get("titulo", "")
            raw_loja = cupom.get("loja", "Loja")
            raw_link = cupom.get("link", "")
            cupom_id = generate_unique_id(raw_titulo, raw_link)

            if cupom_id not in cupons_ids:
                safe_titulo = safe_tg_html(raw_titulo)
                safe_loja = safe_tg_html(raw_loja)
                safe_link = raw_link

                msg = (
                    f"🎟️ <b>CUPOM DISPONÍVEL</b>\n\n"
                    f"🏪 <b>Loja:</b> {safe_loja}\n"
                    f"<b>Descrição:</b> {safe_titulo}\n\n"
                    f"🔗 <a href='{safe_link}'>Acessar Cupons</a>"
                )

                enviados, _ = send_telegram_message(msg, TODOS_DESTINOS)
                if enviados > 0:
                    cupons_ids.append(cupom_id)
                    cupons_lista.insert(0, {
                        "id": cupom_id,
                        "titulo": raw_titulo,
                        "loja": raw_loja,
                        "link": raw_link,
                        "data": datetime.now().isoformat()
                    })
        except Exception as e:
            log_message(f"Erro ao processar cupom: {e}", "ERROR")

    # Persistência
    save_posted_ids(posted_ids, POSTED_FILE)
    save_posted_ids(cupons_ids, CUPONS_FILE)
    save_site_data(ofertas_lista, cupons_lista)

    log_message("=== Ciclo finalizado ===")


def loop_principal():
    log_message("Bot iniciado.")
    keep_alive() # Inicia o servidor HTTP em background
    
    while True:
        try:
            executar_ciclo()
            log_message(f"Aguardando {INTERVALO_VERIFICACAO} minutos...")
            time.sleep(INTERVALO_VERIFICACAO * 60)
        except KeyboardInterrupt:
            log_message("Encerrado manualmente.")
            break
        except Exception as e:
            log_message(f"Erro no loop de execução: {e}", "ERROR")
            time.sleep(60)

if __name__ == "__main__":
    loop_principal()
