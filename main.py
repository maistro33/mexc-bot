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
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # %75 Kar Al (TP1)
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'rr_target': 1.3,            
    'timeframe': '5m'            
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        if precision < 1:
            step = int(-math.log10(precision))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. ÇİFT YÖNLÜ SMC MOTORU (LONG & SHORT)] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # --- LONG ANALİZİ ---
        swing_low = min(l[-15:-1])
        liq_taken_long = l[-1] < swing_low
        recent_high = max(h[-8:-1])
        mss_long = c[-1] > recent_high 
        
        # --- SHORT ANALİZİ ---
        swing_high = max(h[-15:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-8:-1])
        mss_short = c[-1] < recent_low

        # Hacim Onayı (Her iki yön için)
        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.2)
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP VE KAPANIŞ SİSTEMİ] ---
def monitor_trade(symbol, side, entry, stop, tp1, amount):
    stage = 0 
    price_step = 1.0 / (amount / CONFIG['leverage']) 
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # Kar Al - Stopu Girişe Çek
            condition_tp1 = (price >= tp1) if side == 'buy' else (price <= tp1)
            
            if stage == 0 and condition_tp1:
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                pos = ex.fetch_positions([symbol])
                if pos and float(pos[0]['contracts']) != 0:
                    rem_qty = round_amount(symbol, abs(float(pos[0]['contracts'])))
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    ex.create_order(symbol, 'trigger_market', exit_side, rem_qty, params={'stopPrice': entry, 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"✅ {symbol} {side.upper()} TP1! %75 kapandı, stop girişe ({entry}) çekildi.")
                    stage = 1

            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} {side.upper()} kapandı.")
                break
            time.sleep(10)
        except: time.sleep(5)

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 ÇİFT YÖNLÜ SCALP BAŞLADI!\nArtık hem LONG hem SHORT fırsatları kollanıyor.")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, fvg = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    # Kar Al Hedefi (RR'ye göre)
                    if side == 'buy':
                        tp1 = entry + ((entry - stop) * CONFIG['rr_target'])
                        exit_side = 'sell'
                    else:
                        tp1 = entry - ((stop - entry) * CONFIG['rr_target'])
                        exit_side = 'buy'

                    # İşlemi Başlat
                    ex.create_market_order(sym, side, amount)
                    active_trades[sym] = True
                    
                    # Stop ve TP1 Emirleri
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True})
                    tp1_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'limit', exit_side, tp1_qty, tp1, {'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **YENİ {side.upper()} İŞLEMİ**\nKoin: {sym}\nGiriş: {entry:.4f}\nTP1: {tp1:.4f}\nStop: {stop:.4f}")
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, tp1, amount), daemon=True).start()
                
                time.sleep(0.05)
            time.sleep(60)
        except: time.sleep(10)

# Telegram Komutları (Bakiye/Durum)
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades: bot.reply_to(message, "🔍 İşlem yok, radar çift yönlü açık.")
    else:
        msg = "📊 Aktif İşlemler:\n"
        for s in active_trades.keys(): msg += f"🔹 {s}\n"
        bot.reply_to(message, msg)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
