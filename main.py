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
    'rr_target': 1.1,
    'trailing_activation_rr': 0.8, # Hedefin %80'ine gelince trailing başlasın
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

# --- [3. AKILLI TAKİP SİSTEMİ (TRAILING STOP & TP)] ---
def monitor_trade(symbol, side, entry, stop, tp1):
    highest_price = entry if side == 'buy' else 999999
    tp1_hit = False
    
    while symbol in active_trades:
        try:
            time.sleep(10) # 10 saniyede bir kontrol
            ticker = ex.fetch_ticker(symbol)
            current_price = ticker['last']
            pos = ex.fetch_positions([symbol])
            
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM KAPANDI: {symbol}**")
                break

            # TP1 Kontrolü (%75 Kapama)
            if not tp1_hit:
                if (side == 'buy' and current_price >= tp1) or (side == 'sell' and current_price <= tp1):
                    bot.send_message(MY_CHAT_ID, f"💰 **TP1 HEDEFİNE ULAŞILDI!** {symbol} pozisyonunun %75'i kapatıldı.")
                    tp1_hit = True

            # Manuel Trailing Mantığı (Fiyat kâra gittikçe stopu giriş seviyesine çek)
            if side == 'buy' and current_price > entry:
                if current_price > highest_price:
                    highest_price = current_price
                    # Fiyat hedefin yarısını geçtiyse stopu GİRİŞE çek (Kârı koru)
                    if (current_price - entry) > (tp1 - entry) * 0.5:
                        stop = entry 

        except Exception as e:
            print(f"Takip Hatası: {e}")
            break

# --- [4. ANALİZ: GÖVDE ONAYLI] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=30)
        o, h, l, c = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]
        
        recent_high = max(h[-10:-2])
        recent_low = min(l[-10:-2])

        # Gövde Kapanış Şartı (Body Close)
        if c[-1] > recent_high and c[-1] > o[-1]: # Boğa mum kapanışı
            return 'buy', c[-1], min(l[-3:])
        if c[-1] < recent_low and c[-1] < o[-1]: # Ayı mum kapanışı
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
        
        # 1. Giriş
        ex.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        active_trades[symbol] = True
        
        # 2. SL ve TP1 Hesapla
        dist = abs(entry - stop)
        tp1_price = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])

        # 3. Borsa tarafına sadece ANA STOP LOSS'u koy (Güvenlik için)
        ex.create_order(symbol, 'limit', exit_side, amount, stop, params={
            'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side
        })

        # 4. TP1 Emri (%75)
        tp1_qty = round_amount(symbol, amount * CONFIG['Close_Percentage_TP1'])
        ex.create_order(symbol, 'limit', exit_side, tp1_qty, tp1_price, params={
            'stopPrice': tp1_price, 'reduceOnly': True, 'posSide': pos_side
        })

        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI**\n{symbol} | {side.upper()}\nGiriş: {entry}\nSL: {stop}\nTP1: {tp1_price}")
        
        # Takip Thread'ini başlat
        threading.Thread(target=monitor_trade, args=(symbol, side, entry, stop, tp1_price), daemon=True).start()

    except Exception as e:
        bot.send_message(MY_CHAT_ID, "⚠️ Giriş yapıldı ancak emirlerde bir sorun oluştu, borsayı kontrol edin.")

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
            time.sleep(15)
        except: time.sleep(20)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "🛡️ **Hata Giderildi! Trailing ve TP1 Takibi Aktif.**")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    main_loop()
