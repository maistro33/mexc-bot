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
    'entry_usdt': 20.0,
    'leverage': 10,
    'Close_Percentage_TP1': 0.75, 
    'rr_tp1': 1.1,                 # TP1 hedefi (Risk/Ödül 1.1)
    'rr_tp2': 2.2,                 # TP2 hedefi (Risk/Ödül 2.2)
    'max_active_trades': 3,
    'timeframe': '1m'
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        step = int(-math.log10(prec)) if prec < 1 else 0
        return round(amount, step)
    except: return round(amount, 2)

# --- [3. İZLEME VE MESAJLAŞMA] ---
def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(20)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM TAMAMLANDI: {symbol}**")
                break
        except: break

# --- [4. ANALİZ: GÖVDE ONAYLI] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=35)
        o, h, l, c = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        
        recent_high, recent_low = max(h[-10:-2]), min(l[-10:-2])

        if c[-1] > recent_high and c[-1] > o[-1]: # Gövde üstte kapattı
            return 'buy', c[-1], min(l[-3:])
        if c[-1] < recent_low and c[-1] < o[-1]: # Gövde altta kapattı
            return 'sell', c[-1], max(h[-3:])
        return None, None, None
    except: return None, None, None

# --- [5. EMİR YÖNETİMİ - TP1/TP2 SİSTEMİ] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = round_amount(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        # 1. MARKET GİRİŞ
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # Hedef Hesaplama
        dist = abs(entry - stop)
        tp1_price = entry + (dist * CONFIG['rr_tp1']) if side == 'buy' else entry - (dist * CONFIG['rr_tp1'])
        tp2_price = entry + (dist * CONFIG['rr_tp2']) if side == 'buy' else entry - (dist * CONFIG['rr_tp2'])

        # 2. SABİT STOP LOSS (Limit Tipi - En Garanti)
        ex.create_order(symbol, 'limit', exit_side, amount, stop, params={
            'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side
        })

        # 3. TP1 (%75)
        tp1_qty = round_amount(symbol, amount * CONFIG['Close_Percentage_TP1'])
        ex.create_order(symbol, 'limit', exit_side, tp1_qty, tp1_price, params={
            'stopPrice': tp1_price, 'reduceOnly': True, 'posSide': pos_side
        })

        # 4. TP2 (Kalan %25)
        tp2_qty = round_amount(symbol, amount - tp1_qty)
        ex.create_order(symbol, 'limit', exit_side, tp2_qty, tp2_price, params={
            'stopPrice': tp2_price, 'reduceOnly': True, 'posSide': pos_side
        })

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI: {symbol}**\nSL: {stop}\nTP1 (%75): {tp1_price}\nTP2 (%25): {tp2_price}")
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, "⚠️ Emir gönderilirken borsa reddetti, bakiyeyi kontrol edin.")

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            sorted_symbols = sorted([s for s in markets if '/USDT:USDT' in s], key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:50]
            for sym in sorted_symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                side, entry, stop = analyze_smc_strategy(sym)
                if side: execute_trade(sym, side, entry, stop)
            time.sleep(10)
        except: time.sleep(15)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Güncel Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "✅ **Sabit TP1-TP2 Sistemi Yayında!**\nTrailing kapatıldı, hatalar giderildi.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
