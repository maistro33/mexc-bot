import ccxt
import telebot
import time
import os
import math

# --- [1. BAĞLANTILAR VE DEĞİŞKENLER] ---
# Railway Variables kısmına girdiğiniz isimlerle aynı olmalı
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        step = market['precision']['amount']
        return round(math.floor(amount / step) * step, 4)
    except: return round(amount, 3)

# --- [2. ANA STRATEJİ FONKSİYONU] ---
def run_sadik_bey_bot(symbol='BTC/USDT:USDT'):
    bot.send_message(MY_CHAT_ID, f"🦅 **STRATEJİ AKTİF: {symbol}**\nBakiye: 20 USDT | Kaldıraç: 10x | TP1: %75")
    
    try:
        ex.load_markets()
        
        # Kaldıraç ayarını bot üzerinden de teyit ediyoruz
        ex.set_leverage(10, symbol)
        
        ticker = ex.fetch_ticker(symbol)
        last_price = ticker['last']
        
        # --- HESAPLAMA (20 USDT GİRİŞ) ---
        # Formül: (İstenen USDT * Kaldıraç) / Güncel Fiyat
        entry_amount_usdt = 20.0
        leverage = 10
        btc_qty = round_amount(symbol, (entry_amount_usdt * leverage) / last_price)
        
        # Hedef Seviyeler (%1.0 mesafe)
        stop_price = round(last_price * 0.99, 1) # %1 Zarar Durdur
        tp1_price = round(last_price * 1.01, 1)  # %1 Kâr Al
        
        # --- 1. ADIM: POZİSYON AÇILIŞI (LONG) ---
        # Not: 'posSide': 'long' parametresi Hedge modunda şarttır.
        ex.create_market_buy_order(symbol, btc_qty, params={'posSide': 'long'})
        bot.send_message(MY_CHAT_ID, f"✅ Pozisyon Açıldı!\nGiriş: {last_price}\nMiktar: {btc_qty} BTC")
        time.sleep(2)

        # --- 2. ADIM: STOP LOSS KURULUMU (Tüm Pozisyon) ---
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': symbol.replace('/', '').replace(':USDT', '_UMCBL'),
            'marginCoin': 'USDT',
            'size': str(btc_qty),
            'triggerPrice': str(stop_price),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'posSide': 'long',
            'reduceOnly': 'true'
        })
        bot.send_message(MY_CHAT_ID, f"🛑 Stop Loss Dizildi: {stop_price}")

        # --- 3. ADIM: %75 KADEMELİ KÂR AL (TP1) ---
        # Sizin isteğiniz: Pozisyonun %75'ini ilk hedefte kapat.
        tp_qty = round_amount(symbol, btc_qty * 0.75)
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': symbol.replace('/', '').replace(':USDT', '_UMCBL'),
            'marginCoin': 'USDT',
            'size': str(tp_qty),
            'triggerPrice': str(tp1_price),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'posSide': 'long',
            'reduceOnly': 'true'
        })
        bot.send_message(MY_CHAT_ID, f"💰 %75 Kâr Al (TP1) Dizildi: {tp1_price}")

        bot.send_message(MY_CHAT_ID, "🏁 **İŞLEM BAŞARIYLA TAMAMLANDI.**\nEmirleri 'Planlı Emirler' sekmesinden takip edebilirsin.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ HATA OLUŞTU: {str(e)}")

if __name__ == "__main__":
    run_sadik_bey_bot()
