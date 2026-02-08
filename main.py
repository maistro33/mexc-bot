import ccxt
import telebot
import time
import os
import threading
from datetime import datetime

# --- [BAĞLANTILAR] ---
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Borsaya Bağlan (Vadeli İşlemler)
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [SADIK BEY ÖZEL AYARLAR] ---
CONFIG = {
    'trade_amount_usdt': 20.0,      # İşlem tutarı
    'leverage': 10,                 # Kaldıraç
    'tp1_ratio': 0.75,              # TP1'de %75 kapat
    'tp1_target': 0.015,            # %1.5 kar hedefi
    'min_volume_mult': 1.5,         # Hacim onayı kalkanı
    'symbols': [
        'FARTCOIN/USDT:USDT', 'PNUT/USDT:USDT', 'MOODENG/USDT:USDT', 'GOAT/USDT:USDT',
        'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'SOL/USDT:USDT', 'SUI/USDT:USDT'
    ]
}

# --- [ANTI-MANIPULATION ANALİZ MOTORU] ---
def get_smc_signal(symbol):
    try:
        # 15 Dakikalık Veri Analizi
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]
        volumes = [x[5] for x in ohlcv]

        # 1. Hacim Onaylı MSS (Manipülasyon Kalkanı)
        avg_vol = sum(volumes[-6:-1]) / 5
        vol_ok = volumes[-1] > (avg_vol * CONFIG['min_volume_mult'])

        # 2. Likidite Süpürme (Gövde Kapanış Onayı)
        r_high = max(highs[-25:-5])
        r_low = min(lows[-25:-5])
        
        # AYI (SHORT) - Gövde Onaylı
        if highs[-2] > r_high and closes[-2] < r_high:
            if closes[-1] < min(lows[-10:-2]) and vol_ok:
                return 'sell', closes[-1]

        # BOĞA (LONG) - Gövde Onaylı
        if lows[-2] < r_low and closes[-2] > r_low:
            if closes[-1] > max(highs[-10:-2]) and vol_ok:
                return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [MEXC ÖZEL İŞLEM MOTORU] ---
def execute_trade(symbol, side, price):
    try:
        # MEXC Hata Düzeltmesi (openType 1: Isolated, positionType 1: Long / 2: Short)
        pos_type = 1 if side == 'buy' else 2
        ex.set_leverage(CONFIG['leverage'], symbol, {
            'openType': 1, 
            'positionType': pos_type
        })
        
        # Miktar ve Market Emir
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        ex.create_market_order(symbol, side, amount)
        
        # TP1 Emri: %75 Kar Al
        tp_side = 'sell' if side == 'buy' else 'buy'
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', tp_side, amount * CONFIG['tp1_ratio'], tp_price)

        bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI!**\n\n🪙 {symbol}\n↕️ {side.upper()}\n🚜 %75 TP1: {tp_price}")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ **İşlem Hatası:** {str(e)}")

# --- [ANA DÖNGÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, Bot Tüm Kalkanlarla Railway Üzerinden Aktif!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                execute_trade(symbol, side, price)
                time.sleep(600) # Aynı koin için 10 dk bekle
            time.sleep(1.5)
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
