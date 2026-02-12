import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True},
    'enableRateLimit': True
})

bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 15.0,           # Bakiye hatasını önlemek için 15 USDT
    'leverage': 10,               # 10x Kaldıraç
    'rr_target': 1.5,             # Kar hedefi (Risk/Ödül 1.5)
    'max_active_trades': 2,       # Aynı anda max 2 işlem
    'timeframe': '1m'
}

active_trades = {}

# --- [3. YUVARLAMA VE HASSASİYET ARAÇLARI] ---
def round_step(value, step):
    if not step or step == 0: return float(value)
    return math.floor(value / step) * step

def get_precision(symbol):
    market = ex.market(symbol)
    return market['precision']['amount'], market['precision']['price']

# --- [4. ANALİZ MOTORU: GÖVDE ONAYLI] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=35)
        o, h, l, c = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        
        # Gövde Kapanış Seviyeleri
        recent_high = max(h[-10:-2])
        recent_low = min(l[-10:-2])

        # LONG Onayı: Önceki tepenin üstünde yeşil gövde kapattı
        if c[-1] > recent_high and c[-1] > o[-1]:
            return 'buy', c[-1], min(l[-3:])
        
        # SHORT Onayı: Önceki dibin altında kırmızı gövde kapattı
        if c[-1] < recent_low and c[-1] < o[-1]:
            return 'sell', c[-1], max(h[-3:])
            
        return None, None, None
    except: return None, None, None

# --- [5. EMİR YÖNETİMİ: MARKET GİRİŞ + TEK SL + TEK TP] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amt_step, price_step = get_precision(symbol)
        
        # Miktar hesapla ve yuvarla
        amount = round_step((CONFIG['entry_usdt'] * CONFIG['leverage']) / entry, amt_step)
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        # 1. MARKET GİRİŞ
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # 2. HEDEF VE STOP HESAPLA
        dist = abs(entry - stop)
        tp_raw = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])
        
        # Fiyatları borsa hassasiyetine göre yuvarla
        sl_price = round_step(stop, price_step)
        tp_price = round_step(tp_raw, price_step)

        # 3. STOP LOSS (Tüm Pozisyonu Kapatır)
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={
            'stopPrice': sl_price, 'reduceOnly': True, 'posSide': pos_side
        })
        time.sleep(1)

        # 4. TAKE PROFIT (Tüm Pozisyonu Kapatır)
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={
            'stopPrice': tp_price, 'reduceOnly': True, 'posSide': pos_side
        })

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI: {symbol}**\nYön: {side.upper()}\nSL: {sl_price}\nTP (%100): {tp_price}")

        # Pozisyonu izle (kapandığında listemden sil)
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası: {str(e)[:100]}")

def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(30)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM SONLANDI: {symbol}**")
                break
        except: break

# --- [6. ANA DÖNGÜ VE TELEGRAM] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            # En hacimli 40 coini tara
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:40]
            
            for sym in symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                side, entry, stop = analyze_smc_strategy(sym)
                if side: execute_trade(sym, side, entry, stop)
            
            time.sleep(15)
        except: time.sleep(20)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "🛡️ **Sadeleştirilmiş SMC Botu Yayında!**\nSadece SL ve %100 TP aktif.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
