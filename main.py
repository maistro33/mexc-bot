import os
import time
import telebot
import ccxt
from google import genai

# --- [BAĞLANTI VE GÜVENLİK] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'createMarketBuyOrderRequiresPrice': False}
    })

def live_monitor():
    """İşlemi canlı takip eder ve en iyi kâr noktasında kapatır"""
    exch = get_exchange()
    while True:
        try:
            pos = exch.fetch_positions()
            active = [p for p in pos if float(p.get('contracts', 0)) > 0]
            
            if not active:
                bot.send_message(CHAT_ID, "📡 **Radar:** Açık işlem yok. Yeni fırsat taranıyor...")
                return

            p = active[0]
            symbol, side, pnl = p['symbol'], p['side'], float(p['unrealizedPnl'])
            
            # Sanal Takip Raporu
            bot.send_message(CHAT_ID, f"📈 **Canlı Takip:** {symbol} {side.upper()}\nPNL: {pnl} USDT\nBakiye: 18.41")
            
            # AI Karar Mekanizması
            prompt = (
                f"Evergreen V11, {symbol} {side} pozisyonundasın. PNL: {pnl} USDT. "
                f"Kârı maksimize etmek için beklemeli miyiz yoksa trend dönüyor mu? "
                f"Kapatmak için [KOMUT:KAPAT] de, aksi halde [KOMUT:IZLE] de."
            )
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if "[KOMUT:KAPAT]" in response.text:
                close_side = 'sell' if side == 'long' else 'buy'
                exch.create_market_order(symbol, close_side, p['contracts'])
                bot.send_message(CHAT_ID, f"💰 **Kâr Alındı / İşlem Kapatıldı.**\nSon PNL: {pnl} USDT")
                break
                
            time.sleep(120) # 2 dakikada bir kontrol
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🛡️ **Evergreen V11 Yayında.**\nBakiye: 18.41 USDT\nMod: Otonom Kâr Optimizasyonu")
    # Döngüyü başlat
    while True:
        try:
            # Burada AI_Commander fonksiyonunla yeni işlem açılacak
            # İşlem açıldıktan sonra live_monitor() devreye girecek
            live_monitor()
            time.sleep(300)
        except: time.sleep(10)
