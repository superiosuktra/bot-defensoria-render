#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🤖 ROBÔ DE OFERTAS E CUPONS - VERSÃO CLOUD (REPLIT)
Versão 4.0 - Roda 24/7 na nuvem de forma automática
Sem precisar de GitHub Actions, apenas execute e ative!
"""

import os
import requests
import feedparser
import time
import json
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import hashlib
import threading
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CANAIS = [c.strip() for c in os.getenv("TELEGRAM_CANAIS", "").split(",") if c.strip()]
TELEGRAM_GRUPOS = [g.strip() for g in os.getenv("TELEGRAM_GRUPOS", "").split(",") if g.strip()]

RSS_FEED_URL = os.getenv("RSS_FEED_URL", "https://www.promobit.com.br/feed/")
AFFILIATE_TAG_AMAZON = os.getenv("AFFILIATE_TAG_AMAZON", "")
AFFILIATE_TAG_OUTROS = os.getenv("AFFILIATE_TAG_OUTROS", "")

# Frequência de execução (em minutos)
INTERVALO_VERIFICACAO = 120  # A cada 2 horas

REQUEST_TIMEOUT = 10
TELEGRAM_TIMEOUT = 15

POSTED_FILE = "postados.txt"
CUPONS_FILE = "cupons_postados.txt"
DADOS_SITE = "dados.json"

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def log_message(message, level="INFO"):
    """Registra mensagens com timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def load_posted_ids(filename):
    """Carrega IDs já postados"""
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                ids = set(line.strip() for line in f if line.strip())
                log_message(f"✅ Carregados {len(ids)} IDs de {filename}")
                return ids
        else:
            return set()
    except Exception as e:
        log_message(f"❌ Erro ao carregar {filename}: {e}", "ERROR")
        return set()


def save_posted_id(post_id, filename):
    """Salva novo ID"""
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{post_id}\n")
    except Exception as e:
        log_message(f"❌ Erro ao salvar ID: {e}", "ERROR")


def generate_unique_id(text, url):
    """Gera ID único"""
    combined = f"{text}|{url}".lower()
    return hashlib.md5(combined.encode()).hexdigest()


def convert_to_affiliate_link(url, title=""):
    """Converte para link de afiliado"""
    try:
        if not url or not isinstance(url, str):
            return url
        
        if "amazon.com.br" in url or "amazon.com" in url:
            if AFFILIATE_TAG_AMAZON:
                separator = "&" if "?" in url else "?"
                return f"{url}{separator}tag={AFFILIATE_TAG_AMAZON}"
        
        elif "mercadolivre.com.br" in url:
            if AFFILIATE_TAG_OUTROS:
                separator = "&" if "?" in url else "?"
                return f"{url}{separator}utm_source=robo_ofertas"
        
        return url
    
    except Exception as e:
        log_message(f"❌ Erro ao converter link: {e}", "ERROR")
        return url


def fetch_rss_feed(url):
    """Busca feed RSS"""
    try:
        log_message(f"🔍 Buscando feed: {url}")
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        log_message(f"✅ Feed carregado: {len(feed.entries)} entries")
        return feed.entries
    
    except requests.exceptions.Timeout:
        log_message("❌ Timeout ao buscar RSS", "ERROR")
        return []
    except Exception as e:
        log_message(f"❌ Erro ao buscar RSS: {e}", "ERROR")
        return []


def scrape_cupons_mercado_livre():
    """Busca cupons do Mercado Livre"""
    cupons = []
    try:
        log_message("🔍 Buscando cupons do Mercado Livre...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(
            "https://www.mercadolivre.com.br/cupons",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "lxml")
        cupom_elements = soup.find_all(class_=lambda x: x and "cupon" in x.lower())
        
        for elem in cupom_elements[:10]:
            try:
                title = elem.get_text(strip=True)[:100]
                code = extract_cupom_code(title)
                
                if title and code:
                    cupom_dict = {
                        "titulo": title,
                        "codigo": code,
                        "loja": "Mercado Livre",
                        "link": "https://www.mercadolivre.com.br/cupons",
                        "desconto": extract_discount_percentage(title)
                    }
                    cupons.append(cupom_dict)
            except:
                continue
        
        log_message(f"✅ Encontrados {len(cupons)} cupons do Mercado Livre")
        
    except Exception as e:
        log_message(f"⚠️ Erro ao buscar cupons ML: {e}", "ERROR")
    
    return cupons


def extract_cupom_code(text):
    """Extrai código de cupom"""
    try:
        import re
        patterns = [r'[A-Z]{3,}[0-9]*', r'[A-Z]{3,}', r'[0-9]{4,}']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return ""
    except:
        return ""


def extract_discount_percentage(text):
    """Extrai desconto"""
    try:
        import re
        match = re.search(r'(\d{1,3})%', text)
        if match:
            return f"{match.group(1)}%"
        return ""
    except:
        return ""


def send_telegram_message(text, chat_ids, parse_mode="HTML"):
    """Envia mensagem para Telegram"""
    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        return (0, 0)
    
    enviados = 0
    falhas = 0
    
    for chat_id in chat_ids:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False
            }
            
            response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
            
            if response.status_code == 200:
                enviados += 1
                log_message(f"✅ Mensagem enviada para {chat_id}")
            else:
                falhas += 1
                log_message(f"❌ Erro ao enviar para {chat_id}: {response.status_code}", "ERROR")
        
        except Exception as e:
            falhas += 1
            log_message(f"❌ Erro ao enviar: {e}", "ERROR")
    
    return (enviados, falhas)


def load_site_data():
    """Carrega dados do site"""
    try:
        if os.path.exists(DADOS_SITE):
            with open(DADOS_SITE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {"ofertas": [], "cupons": [], "atualizado_em": ""}
    except:
        return {"ofertas": [], "cupons": [], "atualizado_em": ""}


def save_site_data(ofertas, cupons):
    """Salva dados do site"""
    try:
        dados = {
            "ofertas": ofertas[-50:],
            "cupons": cupons[-50:],
            "atualizado_em": datetime.now().isoformat(),
            "total_ofertas": len(ofertas),
            "total_cupons": len(cupons)
        }
        
        with open(DADOS_SITE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        
        log_message(f"✅ Dados salvos em {DADOS_SITE}")
    
    except Exception as e:
        log_message(f"❌ Erro ao salvar dados: {e}", "ERROR")


# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def executar_ciclo():
    """Executa um ciclo completo de busca e envio"""
    log_message("\n" + "="*80)
    log_message("🚀 INICIANDO CICLO DE BUSCA E ENVIO")
    log_message("="*80)
    
    # Carregar histórico
    posted_ids = load_posted_ids(POSTED_FILE)
    cupons_ids = load_posted_ids(CUPONS_FILE)
    site_data = load_site_data()
    
    ofertas_lista = site_data.get("ofertas", [])
    cupons_lista = site_data.get("cupons", [])
    
    ofertas_enviadas = 0
    cupons_enviados = 0
    
    # ========================================================================
    # BUSCAR OFERTAS DO RSS
    # ========================================================================
    log_message("\n📋 ETAPA 1: Buscando ofertas do RSS")
    log_message("-" * 80)
    
    entries = fetch_rss_feed(RSS_FEED_URL)
    
    if entries:
        for entry in entries:
            try:
                title = entry.get("title", "Sem título")
                link = entry.get("link", "")
                entry_id = entry.get("id", "") or entry.get("guid", "") or link
                
                if not entry_id:
                    entry_id = generate_unique_id(title, link)
                
                if entry_id not in posted_ids and link and link.startswith("http"):
                    affiliate_link = convert_to_affiliate_link(link, title)
                    
                    # Adicionar ao site
                    oferta_item = {
                        "id": entry_id,
                        "titulo": title,
                        "link": affiliate_link,
                        "data": datetime.now().isoformat(),
                        "fonte": "RSS Feed",
                        "emoji": "🎁"
                    }
                    ofertas_lista.insert(0, oferta_item)
                    
                    # Enviar para Telegram
                    telegram_message = f"🎁 <b>PROMOÇÃO</b>\n\n<b>{title}</b>\n\n🔗 <a href='{affiliate_link}'>Ver Oferta</a>"
                    enviados, _ = send_telegram_message(telegram_message, TELEGRAM_CANAIS + TELEGRAM_GRUPOS)
                    
                    if enviados > 0:
                        save_posted_id(entry_id, POSTED_FILE)
                        ofertas_enviadas += 1
                        log_message(f"🎁 Nova oferta enviada: {title[:50]}...")
            
            except Exception as e:
                log_message(f"⚠️ Erro ao processar oferta: {e}", "ERROR")
                continue
    
    # ========================================================================
    # BUSCAR CUPONS
    # ========================================================================
    log_message("\n🎟️ ETAPA 2: Buscando cupons")
    log_message("-" * 80)
    
    cupons_ml = scrape_cupons_mercado_livre()
    
    for cupom in cupons_ml:
        try:
            titulo = cupom.get("titulo", "Sem título")
            codigo = cupom.get("codigo", "")
            loja = cupom.get("loja", "")
            link = cupom.get("link", "")
            desconto = cupom.get("desconto", "")
            
            cupom_id = generate_unique_id(titulo, codigo)
            
            if cupom_id not in cupons_ids:
                cupom_item = {
                    "id": cupom_id,
                    "titulo": titulo,
                    "codigo": codigo,
                    "loja": loja,
                    "link": link,
                    "desconto": desconto,
                    "data": datetime.now().isoformat(),
                    "emoji": "🎟️"
                }
                cupons_lista.insert(0, cupom_item)
                
                desconto_text = f" | <b>{desconto} OFF</b>" if desconto else ""
                codigo_text = f"\n💰 <b>Código:</b> <code>{codigo}</code>" if codigo else ""
                
                telegram_message = (
                    f"🎟️ <b>CUPOM DISPONÍVEL</b>{desconto_text}\n\n"
                    f"🏪 <b>Loja:</b> {loja}\n"
                    f"<b>Descrição:</b> {titulo}"
                    f"{codigo_text}\n\n"
                    f"🔗 <a href='{link}'>Usar Cupom</a>"
                )
                
                enviados, _ = send_telegram_message(telegram_message, TELEGRAM_CANAIS + TELEGRAM_GRUPOS)
                
                if enviados > 0:
                    save_posted_id(cupom_id, CUPONS_FILE)
                    cupons_enviados += 1
                    log_message(f"🎟️ Novo cupom enviado: {titulo[:50]}...")
        
        except Exception as e:
            log_message(f"⚠️ Erro ao processar cupom: {e}", "ERROR")
            continue
    
    # ========================================================================
    # SALVAR DADOS DO SITE
    # ========================================================================
    log_message("\n💾 ETAPA 3: Salvando dados")
    log_message("-" * 80)
    
    save_site_data(ofertas_lista, cupons_lista)
    
    # ========================================================================
    # RESUMO
    # ========================================================================
    log_message("\n" + "="*80)
    log_message("✅ CICLO CONCLUÍDO")
    log_message("="*80)
    log_message(f"📊 Ofertas enviadas: {ofertas_enviadas}")
    log_message(f"📊 Cupons enviados: {cupons_enviados}")
    log_message(f"📊 Total ofertas (site): {len(ofertas_lista)}")
    log_message(f"📊 Total cupons (site): {len(cupons_lista)}")
    log_message(f"⏰ Próxima execução: {INTERVALO_VERIFICACAO} minutos")
    log_message("="*80 + "\n")


def loop_infinito():
    """Roda em loop infinito"""
    log_message("\n" + "🌟" * 40)
    log_message("🤖 BOT INICIADO - RODANDO 24/7 NA NUVEM!")
    log_message("🌟" * 40 + "\n")
    
    # Executar uma vez ao iniciar
    executar_ciclo()
    
    # Loop infinito
    while True:
        try:
            log_message(f"⏳ Aguardando {INTERVALO_VERIFICACAO} minutos para próxima execução...")
            time.sleep(INTERVALO_VERIFICACAO * 60)
            executar_ciclo()
        except KeyboardInterrupt:
            log_message("\n🛑 Bot finalizado pelo usuário")
            break
        except Exception as e:
            log_message(f"❌ Erro no loop: {e}", "ERROR")
            time.sleep(60)  # Aguarda 1 minuto antes de tentar novamente


if __name__ == "__main__":
    loop_infinito()
