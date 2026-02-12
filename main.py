import ccxt
import telebot
import time
import os
import threading
import math

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

# --- [2. AYARLAR - 58 USDT İÇİN GÜVENLİ] ---
CONFIG = {
    'entry_usdt': 15.0,           # Tek işlemde 15 USDT (Bakiye korumalı)
    'leverage': 10,               
    'rr_target': 1.5,             # Risk/Ödül oranı (Net %100 kapama)
    'max_active_trades': 2,       # Aynı anda max 2 işlem
    'timeframe': '1m'
}

active_trades = {}

def round_step(value, step):
    if not step or step == 0: return float(value)
    return math.floor(value / step) * step

def get_precision(symbol):
    market = ex.market(symbol)
    return market['precision']['amount'], market['precision']['price']

# --- [3. ANALİZ: GÖVDE KAPANIŞ ONAYI] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=30)
        o, h, l, c = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        recent_high, recent_low = max(h[-10:-2]), min(l[-10:-2])

        if c[-1] > recent_high and c[-1] > o[-1]: return 'buy', c[-1], min(l[-3:])
        if c[-1] < recent_low and c[-1] < o[-1]: return 'sell', c[-1], max(h[-3:])
        return None, None, None
    except: return None, None, None

# --- [4. EMİR YÖNETİMİ: TEK SL & TEK TP] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amt_step, price_step = get_precision(symbol)
        
        amount = round_step((CONFIG['entry_usdt'] * CONFIG['leverage']) / entry, amt_step)
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        # 1. MARKET GİRİŞ
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # 2. HESAPLA VE YUVARLA
        dist = abs(entry - stop)
        tp_raw = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])
        sl_price = round_step(stop, price_step)
        tp_price = round_step(tp_raw, price_step)

        # 3. TEK STOP LOSS (%100)
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={
            'stopPrice': sl_price, 'reduceOnly': True, 'posSide': pos_side
        })
        time.sleep(1)

        # 4. TEK KAR AL (%100)
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={
            'stopPrice': tp_price, 'reduceOnly': True, 'posSide': pos_side
        })

        bot.send_message(MY_CHAT_ID, f"🚀 **YENİ İŞLEM**\n{symbol} | {side.upper()}\nSL: {sl_price}\nTP: {tp_price}")
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir reddedildi: {str(e)[:50]}")

def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(30)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **KAPANDI: {symbol}**")
                break
        except: break

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:35]
            for sym in symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                side, entry, stop = analyze_smc_strategy(sym)
                if side: execute_trade(sym, side, entry, stop)
            time.sleep(20)
        except: time.sleep(25)

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "🛡️ **En Sade Mod Aktif!**\nSadece Tek SL ve Tek TP.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
