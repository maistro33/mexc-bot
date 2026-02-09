import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
# Çevre değişkenlerinden çekemezsen direkt tırnak içine yazabilirsin
API_KEY = os.getenv('BITGET_API', 'BURAYA_API_KEY')
API_SEC = os.getenv('BITGET_SEC', 'BURAYA_SECRET')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE', 'BURAYA_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN', 'BURAYA_TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID', 'BURAYA_CHAT_ID')

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
    'rr_targets': [1.3, 2.5, 4.0], # TP1, TP2, TP3 RR Seviyeleri
    'timeframe': '5m'            
}

active_trades = {}

# --- [HASSASİYET MOTORU] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        step_size = market['limits']['amount']['min']
        precision = int(-math.log10(market['precision']['amount'])) if market['precision']['amount'] < 1 else 0
        rounded = math.floor(amount / step_size) * step_size
        return round(rounded, precision)
    except: return round(amount, 2)

# --- [3. SMC MOTORU (GÖVDE VE HACİM ONAYLI)] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 5 or now_sec > 55: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # LONG ANALİZİ
        swing_low = min(l[-15:-1])
        liq_taken_long = l[-1] < swing_low
        recent_high = max(h[-10:-1])
        # Gövde Kapanış Onayı: Kapanış fiyatı son zirvenin üstünde mi?
        mss_long = c[-1] > recent_high 
        
        # SHORT ANALİZİ
        swing_high = max(h[-15:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-10:-1])
        mss_short = c[-1] < recent_low

        avg_vol = sum(v[-15:-1]) / 15
        vol_ok = v[-1] > (avg_vol * 1.3)
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP SİSTEMİ - 3 TP VE GİRİŞE STOP] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- TP1: %75 KAPAT + STOP GİRİŞE ---
            if stage == 0 and ((price >= tp1 if side == 'buy' else price <= tp1)):
                qty_tp1 = round_amount(symbol, amount * CONFIG['tp1_ratio'])
                ex.create_market_order(symbol, exit_side, qty_tp1, params={'reduceOnly': True})
                
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                remaining = round_amount(symbol, amount - qty_tp1)
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'triggerPrice': entry, 'reduceOnly': True})
                
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 (%75) Tamam!\nStop girişe ({entry}) çekildi.")
                stage = 1

            # --- TP2: 1 USDT KAZANÇ KASAYA ---
            elif stage == 1 and ((price >= tp2 if side == 'buy' else price <= tp2)):
                qty_1_usdt = round_amount(symbol, 1.0 / (price / CONFIG['leverage']))
                if qty_1_usdt > 0:
                    ex.create_market_order(symbol, exit_side, qty_1_usdt, params={'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2: 1 USDT kâr realize edildi.")
                stage = 2

            # --- TP3: FİNAL ---
            elif stage == 2 and ((price >= tp3 if side == 'buy' else price <= tp3)):
                ex.create_market_order(symbol, exit_side, 0, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3: İşlem başarıyla bitti.")
                break

            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                break
            time.sleep(15)
        except: time.sleep(5)

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 RADAR BAŞLADI!\nÇift yönlü SMC ve Kademeli TP aktif.")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    risk = abs(entry - stop)
                    targets = [entry + (risk * r) if side == 'buy' else entry - (risk * r) for r in CONFIG['rr_targets']]
                    
                    # İşlemi Başlat
                    ex.create_market_order(sym, side, amount)
                    active_trades[sym] = True
                    
                    # Stop Loss Koy (Tetikleyici Emir)
                    time.sleep(1.5)
                    ex.create_order(sym, 'trigger_market', ('sell' if side == 'buy' else 'buy'), amount, 
                                    params={'stopPrice': stop, 'triggerPrice': stop, 'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI ({direction})**\nKoin: {sym}\nGiriş: {entry:.4f}\nTP1: {targets[0]:.4f}\nStop: {stop:.4f}")
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                
            time.sleep(15)
        except: time.sleep(10)

# Telegram Komutları
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance()
        bot.reply_to(message, f"💰 Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades: bot.reply_to(message, "🔍 Radar açık, işlem yok.")
    else: bot.reply_to(message, f"📊 Aktif: {', '.join(active_trades.keys())}")

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
