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
    'tp1_ratio': 0.75,           # %75 Kâr Al (Sizin isteğiniz üzerine)
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'rr_target': 1.3,            
    'timeframe': '5m'            
}

active_trades = {}
scanned_list = [] 

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        if precision < 1:
            step = int(-math.log10(precision))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. SMC ANALİZ] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        swing_low = min(l[-15:-1])
        liq_taken_long = l[-1] < swing_low
        recent_high = max(h[-8:-1])
        mss_long = c[-1] > recent_high 
        
        swing_high = max(h[-15:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-8:-1])
        mss_short = c[-1] < recent_low 

        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.2)
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. 5 DK RADAR VE TAKİP] ---
def report_loop():
    while True:
        try:
            time.sleep(300) # İsteğiniz üzerine 5 dakikaya düşürüldü
            if scanned_list:
                msg = f"📡 **SMC RADAR AKTİF**\n"
                msg += f"🔍 {len(scanned_list)} coin taranıyor.\n"
                msg += f"📈 Aktif İşlem: {len(active_trades)}"
                bot.send_message(MY_CHAT_ID, msg)
        except: pass

def monitor_trade(symbol, side, entry, stop, tp1, amount):
    stage = 0 
    while symbol in active_trades:
        try:
            time.sleep(15)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} işlemi kapandı.")
                break
        except: break

# --- [5. ANA DÖNGÜ VE EMİR SİSTEMİ] ---
def main_loop():
    global scanned_list
    while True:
        try:
            markets = ex.fetch_tickers()
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'] if markets[x]['quoteVolume'] else 0,
                reverse=True
            )[:150] 
            
            scanned_list = sorted_symbols
            
            for sym in sorted_symbols:
                if sym in active_trades: continue
                side, entry, stop, msg_type = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    if side == 'buy':
                        tp1 = entry + ((entry - stop) * CONFIG['rr_target'])
                        exit_side = 'sell'
                    else:
                        tp1 = entry - ((stop - entry) * CONFIG['rr_target'])
                        exit_side = 'buy'

                    # 1. Giriş Emri
                    ex.create_market_order(sym, side, amount)
                    active_trades[sym] = True
                    time.sleep(1)

                    # 2. Stop Loss (Trigger Market - Hedge Uyumlu)
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True})
                    
                    # 3. TP1 (Trigger Market - %75 Kar Al)
                    tp1_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🚀 **YENİ İŞLEM**\n{sym} ({side.upper()})\nGiriş: {entry}\nStop: {stop}\nTP1: {tp1}")
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, tp1, amount), daemon=True).start()
                
                time.sleep(0.1)
            time.sleep(15) 
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(10)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: pass

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=report_loop, daemon=True).start()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
