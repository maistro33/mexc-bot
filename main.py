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

# --- [2. AYARLAR - RİSKSİZ & TEK HEDEF] ---
CONFIG = {
    'entry_usdt': 15.0,           
    'leverage': 5,                # Risk için kaldıracı 5'e düşürdüm
    'rr_target': 1.5,             # Daha kârlı hedef (Risk/Ödül 1.5)
    'max_active_trades': 1,       # Tek seferde sadece 1 işlem (En güvenlisi)
    'timeframe': '1m'
}

active_trades = {}

def round_step(value, step):
    if not step or step == 0: return float(value)
    return math.floor(value / step) * step

def get_precision(symbol):
    market = ex.market(symbol)
    return market['precision']['amount'], market['precision']['price']

# --- [3. ANALİZ: SEÇİCİ VE YAVAŞ] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        o, h, l, c, v = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # Güçlü Hacim Onayı (Fake hareketleri eler)
        avg_vol = sum(v[-21:-1]) / 20
        if v[-1] < (avg_vol * 1.5): return None, None, None

        recent_high, recent_low = max(h[-15:-2]), min(l[-15:-2])

        # Sadece çok net Gövde Kapanışı varsa girer
        if c[-1] > recent_high and c[-1] > o[-1]:
            return 'buy', c[-1], min(l[-5:])
        if c[-1] < recent_low and c[-1] < o[-1]:
            return 'sell', c[-1], max(h[-5:])
            
        return None, None, None
    except: return None, None, None

# --- [4. EMİR VE TAKİP] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amt_step, price_step = get_precision(symbol)
        
        amount = round_step((CONFIG['entry_usdt'] * CONFIG['leverage']) / entry, amt_step)
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        dist = abs(entry - stop)
        tp_price = round_step(entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target']), price_step)
        sl_price = round_step(stop, price_step)

        # Tek SL ve Tek TP (%100)
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={'stopPrice': sl_price, 'reduceOnly': True, 'posSide': pos_side})
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={'stopPrice': tp_price, 'reduceOnly': True, 'posSide': pos_side})

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI**\n{symbol} | {side.upper()}\nKâr Hedefi: {tp_price}\nZarar Durdur: {sl_price}")
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Hata: {str(e)[:50]}")

def monitor_trade(symbol):
    while symbol in active_trades:
        time.sleep(30)
        pos = ex.fetch_positions([symbol])
        if not pos or float(pos[0]['contracts']) == 0:
            if symbol in active_trades: del active_trades[symbol]
            bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM TAMAMLANDI: {symbol}**")
            break

# --- [5. RADAR VE BAKİYE RAPORU] ---
def radar_report():
    while True:
        try:
            time.sleep(900) # 15 Dakikada bir rapor verir
            status = "İşlemde" if active_trades else "Pusu Bekliyor 🏹"
            bal = ex.fetch_balance({'type': 'swap'})['total']['USDT']
            bot.send_message(MY_CHAT_ID, f"📡 **RADAR DURUMU**\nDurum: {status}\n💰 Güncel Kasa: {bal:.2f} USDT")
        except: pass

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    threading.Thread(target=radar_report, daemon=True).start()
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:30]
            for sym in symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                side, entry, stop = analyze_smc_strategy(sym)
                if side: execute_trade(sym, side, entry, stop)
            time.sleep(20)
        except: time.sleep(30)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    bal = ex.fetch_balance({'type': 'swap'})['total']['USDT']
    bot.reply_to(message, f"💰 Kasa: {bal:.2f} USDT")

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "✅ **Güvenli Scalper Yayında!**\nRadar aktif, sadece tek hedefli kârlı işlemler.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
