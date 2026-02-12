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
    'Close_Percentage_TP1': 0.75, # İstediğin %75 TP1
    'rr_target': 1.1,
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

# --- [3. İZLEME: İŞLEM KAPANDI MESAJI İÇİN] ---
def monitor_trade(symbol):
    """Pozisyon kapandığında Telegram'a haber verir."""
    while symbol in active_trades:
        try:
            time.sleep(15)
            pos = ex.fetch_positions([symbol])
            # Pozisyonun kontrat sayısı 0 ise kapanmıştır
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM KAPANDI: {symbol}**\nHedef ulaşıldı veya Stop olundu.")
                break
        except Exception as e:
            print(f"İzleme hatası: {e}")
            break

# --- [4. ANALİZ: GÖVDE ONAYLI] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        o, h, l, c, v = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        avg_vol = sum(v[-11:-1]) / 10
        if v[-1] < (avg_vol * 1.1): return None, None, None

        recent_high = max(h[-10:-2])
        recent_low = min(l[-10:-2])

        # GÖVDE ONAYI ŞARTI
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
        pos_side = 'long' if side == 'buy' else 'short'
        exit_side = 'sell' if side == 'buy' else 'buy'
        
        # 1. Market Giriş
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # 2. SL ve TP1 Hesaplama
        dist = abs(entry - stop)
        tp1_price = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])

        # 3. Stop Loss
        ex.create_order(symbol, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})

        # 4. %75 Kar Al (TP1)
        tp1_qty = round_amount(symbol, amount * CONFIG['Close_Percentage_TP1'])
        ex.create_order(symbol, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1_price, 'reduceOnly': True, 'posSide': pos_side})

        # Telegram Mesajı
        msg = f"🚀 **YENİ İŞLEM AÇILDI**\n💎 {symbol} | {side.upper()}\n💰 Giriş: {entry}\n🛑 SL: {stop}\n🎯 TP1 (%75): {tp1_price}"
        bot.send_message(MY_CHAT_ID, msg)

        # İzlemeyi başlat (İşlem kapandığında haber vermesi için)
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ Emir Hatası: {e}")

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            sorted_symbols = sorted([s for s in markets if '/USDT:USDT' in s], key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:60]
            for sym in sorted_symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                side, entry, stop = analyze_smc_strategy(sym)
                if side: execute_trade(sym, side, entry, stop)
            time.sleep(5)
        except: time.sleep(10)

# --- [7. BAŞLATMA] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "🛡️ **SMC Bulut Botu Hazır!**\nMesaj bildirimleri ve gövde onayı aktif.")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
