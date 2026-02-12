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
    'rr_target': 1.2,              # Kar hedefi oranı
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

# --- [3. MANUEL TAKİP MOTORU (Hata Veren Emirleri Devre Dışı Bırakır)] ---
def monitor_trade(symbol, side, entry, stop, tp1, amount):
    tp1_hit = False
    while symbol in active_trades:
        try:
            time.sleep(5) # 5 saniyede bir fiyat kontrolü
            ticker = ex.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # 1. STOP LOSS KONTROLÜ
            if (side == 'buy' and current_price <= stop) or (side == 'sell' and current_price >= stop):
                ex.create_market_order(symbol, 'sell' if side == 'buy' else 'buy', amount, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"🛑 **STOP OLUNDU: {symbol}**\nFiyat stop seviyesine geldi.")
                if symbol in active_trades: del active_trades[symbol]
                break

            # 2. TP1 KONTROLÜ (%75 Kapama)
            if not tp1_hit:
                if (side == 'buy' and current_price >= tp1) or (side == 'sell' and current_price <= tp1):
                    tp1_qty = round_amount(symbol, amount * CONFIG['Close_Percentage_TP1'])
                    ex.create_market_order(symbol, 'sell' if side == 'buy' else 'buy', tp1_qty, params={'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"🎯 **TP1 ALINDI: {symbol}**\nPozisyonun %75'i kapatıldı. Kalan takipte.")
                    tp1_hit = True
                    # TP1 sonrası stopu GİRİŞE çek (Trailing mantığı)
                    stop = entry 

            # 3. POZİSYON KONTROLÜ (Manuel kapandıysa döngüden çık)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                break

        except Exception as e:
            print(f"Takip hatası: {e}")
            time.sleep(10)

# --- [4. ANALİZ: GÖVDE ONAYLI] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=30)
        o, h, l, c = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        recent_high, recent_low = max(h[-10:-2]), min(l[-10:-2])

        if c[-1] > recent_high and c[-1] > o[-1]:
            return 'buy', c[-1], min(l[-3:])
        if c[-1] < recent_low and c[-1] < o[-1]:
            return 'sell', c[-1], max(h[-3:])
        return None, None, None
    except: return None, None, None

# --- [5. EMİR YÖNETİMİ] ---
def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = round_amount(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        
        # SADECE MARKET GİRİŞİ YAPAR (Hata riskini sıfırlar)
        ex.create_market_order(symbol, side, amount, params={'posSide': 'long' if side == 'buy' else 'short'})
        active_trades[symbol] = True
        
        dist = abs(entry - stop)
        tp1_price = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI: {symbol}**\nBot takibe başladı. TP1: {tp1_price}")
        
        # Takip işlemini başlat
        threading.Thread(target=monitor_trade, args=(symbol, side, entry, stop, tp1_price, amount), daemon=True).start()
    except Exception as e:
        print(f"Giriş hatası: {e}")

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
    bot.send_message(MY_CHAT_ID, "✅ **Hatalar Giderildi!**\nSistem artık borsadan emir onayı beklemeden kendi takibini yapıyor.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
