import ccxt
import telebot
import time
import os
import threading
from datetime import datetime

# --- [BAĞLANTILAR & DOĞRULAMA] ---
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Borsaya Bağlan (Futures/Vadeli İşlemler)
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [AYARLAR - SADIK BEY ÖZEL] ---
CONFIG = {
    'trade_amount_usdt': 20.0,       # İşlem tutarı (USDT)
    'leverage': 10,                 # Kaldıraç
    'tp1_ratio': 0.75,              # TP1'de pozisyonun %75'ini kapat
    'tp1_target': 0.015,            # %1.5 karda ilk satış (Ayarlanabilir)
    'min_volume_mult': 1.5,         # Hacim Onayı (Ortalamanın 1.5 katı)
    'symbols': [
        'FARTCOIN/USDT:USDT', 'PNUT/USDT:USDT', 'MOODENG/USDT:USDT', 'GOAT/USDT:USDT',
        'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'POPCAT/USDT:USDT', 'BONK/USDT:USDT',
        'NEIRO/USDT:USDT', 'TURBO/USDT:USDT', 'FLOKI/USDT:USDT', 'MEME/USDT:USDT',
        'SOL/USDT:USDT', 'SUI/USDT:USDT', 'AVAX/USDT:USDT', 'FET/USDT:USDT',
        'WLD/USDT:USDT', 'SEI/USDT:USDT', 'APT/USDT:USDT', 'TIA/USDT:USDT'
    ]
}

# --- [GELİŞMİŞ ANALİZ MOTORU - ANTI-MANIPULATION] ---
def get_smc_signal(symbol):
    try:
        # 15 Dakikalık Mum Verisi
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]
        volumes = [x[5] for x in ohlcv]

        # 1. Zaman Filtresi: Mum kapanışına çok yakınsa manipülasyon riski için bekle
        now_sec = datetime.now().second
        if now_sec > 55 or now_sec < 5:
            return None, None

        # 2. Hacim Onayı
        avg_vol = sum(volumes[-6:-1]) / 5
        current_vol = volumes[-1]
        vol_ok = current_vol > (avg_vol * CONFIG['min_volume_mult'])

        # 3. Likidite Süpürme (Gövde Kapanış Onayı ile)
        r_high = max(highs[-25:-5])
        r_low = min(lows[-25:-5])
        
        # AYI (SHORT) - Sadece iğne yukarıda, gövde aşağıda kalmalı
        if highs[-2] > r_high and closes[-2] < r_high:
            if closes[-1] < min(lows[-10:-2]) and vol_ok:
                return 'sell', closes[-1]

        # BOĞA (LONG) - Sadece iğne aşağıda, gövde yukarıda kalmalı
        if lows[-2] < r_low and closes[-2] > r_low:
            if closes[-1] > max(highs[-10:-2]) and vol_ok:
                return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [İŞLEM YÖNETİMİ] ---
def execute_trade(symbol, side, price):
    try:
        # MEXC Hata Düzeltmeli Kaldıraç Ayarı (openType 1: Isolated)
        pos_type = 1 if side == 'buy' else 2
        ex.set_leverage(CONFIG['leverage'], symbol, {'openType': 1, 'positionType': pos_type})
        
        # Miktar Hesapla
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        # 1. Ana İşlemi Aç (Market)
        order = ex.create_market_order(symbol, side, amount)
        
        # 2. %75 Kar Al Emri (TP1)
        tp_side = 'sell' if side == 'buy' else 'buy'
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        tp_amount = amount * CONFIG['tp1_ratio']
        
        ex.create_order(symbol, 'limit', tp_side, tp1_amount, tp_price)

        msg = (f"🎯 **İŞLEM AÇILDI!**\n\n"
               f"🪙 **Koin:** {symbol}\n"
               f"↕️ **Yön:** {side.upper()}\n"
               f"💰 **Giriş:** {price}\n"
               f"🛡️ **Kalkan:** Hacim ve Gövde Onaylı\n"
               f"🚜 **TP1:** {tp_price} (%75 Kapatılacak)")
        bot.send_message(MY_CHAT_ID, msg)
        
    except Exception as e:
        print(f"İşlem Hatası: {e}")
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [ANA DÖNGÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, Bot Full Kapasite ve Korumalarla Devrede!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                execute_trade(symbol, side, price)
                time.sleep(600) # Aynı koin için 10 dk mola
            time.sleep(1.5)
        time.sleep(10)

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Kasa:** {usdt:.2f} USDT")
    except:
        bot.reply_to(message, "⚠️ Borsa bağlantısı kurulamadı.")

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
