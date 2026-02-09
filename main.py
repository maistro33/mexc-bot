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

# --- [2. SCALP AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      # Scalp için hacim eşiğini 5M'e çektik (Fırsat artması için)
    'rr_target': 1.3,            # Scalp'ta daha hızlı TP (1.3 Risk/Ödül)
    'timeframe': '5m'            # Vur-kaç modu: 5 Dakika
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

# --- [3. SCALP ANALİZ MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1. Likidite Alımı (5m'de son 15 mum)
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low
        
        # 2. MSS & Gövde Kapanış (Direnç üstü kapanış)
        recent_high = max(h[-8:-1])
        mss_ok = c[-1] > recent_high 
        
        # 3. Hacim Onayı (Son mumun hacmi, son 10 mumun ortalamasını %20 geçmeli)
        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.2)
        
        if liq_taken and mss_ok and vol_ok:
            # Entry: Mevcut fiyat, Stop: Son 5 mumun en düşüğü
            return 'LONG', c[-1], min(l[-5:]), "SCALP_5M_MSS"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. SCALP TAKİP SİSTEMİ] ---
def monitor_trade(symbol, entry, stop, tp1, amount):
    stage = 0 
    price_step = 1.0 / (amount / CONFIG['leverage']) 
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # STAGE 0 -> TP1 & STOP GİRİŞE
            if stage == 0 and price >= tp1:
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                pos = ex.fetch_positions([symbol])
                if pos and float(pos[0]['contracts']) > 0:
                    rem_qty = round_amount(symbol, float(pos[0]['contracts']))
                    ex.create_order(symbol, 'trigger_market', 'sell', rem_qty, params={'stopPrice': entry, 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"⚡ SCALP TP1! {symbol}\nKalan miktar için stop girişe çekildi.")
                    stage = 1

            # STAGE 1 & 2 -> 1 USDT Kâr Kilitleme
            elif stage in [1, 2] and price >= (tp1 + (price_step * stage)):
                sell_qty = round_amount(symbol, (1.0 * CONFIG['leverage']) / price)
                ex.create_market_order(symbol, 'sell', sell_qty, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"💰 SCALP TP{stage+1}: 1 USDT Kasada! ({symbol})")
                stage += 1

            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) <= 0:
                if symbol in active_trades: del active_trades[symbol]
                break
                
            time.sleep(10) # Scalp'ta daha sık kontrol (10 sn)
        except:
            time.sleep(5)

# --- [5. ANA DÖNGÜ & KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: pass

def main_loop():
    bot.send_message(MY_CHAT_ID, "🏃 SCALP MODU AKTİF! (5 Dakikalık Radar)\nTP1: %75 + Stop Giriş\nHacim & Gövde Onayı devrede.")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades: continue
                if markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, fvg = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    tp1 = entry + ((entry - stop) * CONFIG['rr_target'])

                    ex.create_market_order(sym, 'buy', amount)
                    active_trades[sym] = True
                    
                    ex.create_order(sym, 'trigger_market', 'sell', amount, params={'stopPrice': stop, 'reduceOnly': True})
                    ex.create_order(sym, 'limit', 'sell', round_amount(sym, amount * CONFIG['tp1_ratio']), tp1, {'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🚀 **VUR-KAÇ BAŞLADI: {sym}**\nEntry: {entry:.4f}\nTP1: {tp1:.4f}\nStop: {stop:.4f}")
                    threading.Thread(target=monitor_trade, args=(sym, entry, stop, tp1, amount), daemon=True).start()
                
                time.sleep(0.05)
            time.sleep(60) # Scalp için 1 dakika bekle ve yeniden tara
        except: time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
