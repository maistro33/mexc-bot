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

# --- [2. AYARLAR - SENİN PARAMETRELERİN] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'Close_Percentage_TP1': 0.75, # %75 TP1'de kapanır
    'rr_tp1': 1.1,                 # İlk hedef (Risk/Ödül 1.1)
    'rr_tp2': 2.0,                 # İkinci hedef (Kalan %25 için)
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

# --- [3. İZLEME: MESAJLAR İÇİN] ---
def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(20)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM KAPANDI: {symbol}**\nHedeften veya stoptan çıkış yapıldı.")
                break
        except: break

# --- [4. ANALİZ: GÖVDE ONAYLI SMC] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=35)
        o, h, l, c, v = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        avg_vol = sum(v[-11:-1]) / 10
        if v[-1] < (avg_vol * 1.1): return None, None, None

        recent_high = max(h[-10:-2])
        recent_low = min(l[-10:-2])

        # Gövde Kapanış (Body Close) Onayı
        if c[-1] > recent_high and c[-1] > o[-1]:
            return 'buy', c[-1], min(l[-3:])
        if c[-1] < recent_low and c[-1] < o[-1]:
            return 'sell', c[-1], max(h[-3:])
        return None, None, None
    except: return None, None, None

# --- [5. EMİR YÖNETİMİ - TP1 & TP2] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = round_amount(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        # 1. Market Giriş
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # 2. Hedef Hesaplamaları
        dist = abs(entry - stop)
        tp1_price = entry + (dist * CONFIG['rr_tp1']) if side == 'buy' else entry - (dist * CONFIG['rr_tp1'])
        tp2_price = entry + (dist * CONFIG['rr_tp2']) if side == 'buy' else entry - (dist * CONFIG['rr_tp2'])

        # 3. STOP LOSS (Tüm Pozisyon İçin)
        ex.create_order(symbol, 'limit', exit_side, amount, stop, params={
            'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side
        })

        # 4. TP1 (%75)
        tp1_qty = round_amount(symbol, amount * CONFIG['Close_Percentage_TP1'])
        ex.create_order(symbol, 'limit', exit_side, tp1_qty, tp1_price, params={
            'stopPrice': tp1_price, 'reduceOnly': True, 'posSide': pos_side
        })

        # 5. TP2 (Kalan %25)
        tp2_qty = round_amount(symbol, amount - tp1_qty)
        ex.create_order(symbol, 'limit', exit_side, tp2_qty, tp2_price, params={
            'stopPrice': tp2_price, 'reduceOnly': True, 'posSide': pos_side
        })

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI: {symbol}**\nYön: {side.upper()}\nSL: {stop}\nTP1(%75): {tp1_price}\nTP2(%25): {tp2_price}")
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, "⚠️ Emirlerde sorun oluştu. Borsa limitlerini kontrol edin.")

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
        bot.reply_to(message, f"💰 Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "✅ **Yeni Sistem Aktif!**\nTP1 (%75) - TP2 (%25) - Sabit SL yayında.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
