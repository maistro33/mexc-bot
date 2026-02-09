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

# --- [2. AYARLAR & KASA YÖNETİMİ] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # İlk hedefte %75 kasa güvenliği
    'rr_targets': [1.3, 2.2, 3.5], # TP1, TP2, TP3 (RR Çarpanları)
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'timeframe': '5m'            
}

active_trades = {}

# --- [HASSASİYET VE MİKTAR HESABI] ---
def get_precision_and_amount(symbol, usdt_amount, price):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        contract_size = market.get('contractSize', 1)
        raw_qty = (usdt_amount * CONFIG['leverage']) / price
        qty_in_contracts = raw_qty / contract_size
        if isinstance(precision, int):
            return math.floor(qty_in_contracts * (10**precision)) / (10**precision)
        return (qty_in_contracts // precision) * precision
    except: return None

# --- [3. ANTİ-MANİPÜLASYON ANALİZİ] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 2 or now_sec > 58: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # Gövde Kapanış Onayı (Manipülasyon Kalkanı 1)
        swing_low, swing_high = min(l[-15:-1]), max(h[-15:-1])
        mss_long = c[-1] > max(h[-8:-1]) 
        mss_short = c[-1] < min(l[-8:-1])

        # Hacim Onayı (Manipülasyon Kalkanı 2 - Spoofing Engelleyici)
        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.3)
        
        if vol_ok:
            if l[-1] < swing_low and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG"
            if h[-1] > swing_high and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT"
    except: pass
    return None, None, None, None

# --- [4. KASAYA KÂR EKLEYEREK TAKİP SİSTEMİ] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            curr_price = ticker['last']
            
            # --- TP1: %75 KAPAT + STOPU GİRİŞE ÇEK ---
            if stage == 0 and ((curr_price >= tp1 if side == 'buy' else curr_price <= tp1)):
                qty_to_close = amount * CONFIG['tp1_ratio']
                ex.create_market_order(symbol, exit_side, qty_to_close, params={'reduceOnly': True})
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                # Kalan miktar için stop girişe
                remaining = amount - qty_to_close
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'triggerPrice': entry, 'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 ALINDI (%75).\nKâr kasaya kitlendi, stop girişe çekildi.")
                stage = 1

            # --- TP2: 1 USDT KÂR AL VE DEVAM ET ---
            elif stage == 1 and ((curr_price >= tp2 if side == 'buy' else curr_price <= tp2)):
                # 1 USDT'lik karşılık gelen miktarı hesapla
                qty_1_usdt = get_precision_and_amount(symbol, 1.0, curr_price)
                if qty_1_usdt and qty_1_usdt > 0:
                    ex.create_market_order(symbol, exit_side, qty_1_usdt, params={'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2: 1 USDT kasaya eklendi. Kalan miktar final hedefine gidiyor.")
                stage = 2

            # --- TP3: FİNAL KAPANIŞ ---
            elif stage == 2 and ((curr_price >= tp3 if side == 'buy' else curr_price <= tp3)):
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3 FİNAL: Tüm kâr alındı, işlem kapandı.")
                # Alt kısımdaki pozisyon kontrolü trade'i silecek

            # Pozisyonun kapanma kontrolü
            pos = ex.fetch_positions([symbol])
            size = sum(float(p['contracts']) for p in pos) if pos else 0
            if size <= 0:
                if symbol in active_trades: del active_trades[symbol]
                ex.cancel_all_orders(symbol)
                break
                
            time.sleep(15)
        except Exception as e:
            print(f"Takip hatası: {e}")
            time.sleep(10)

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 BOT BAŞLADI\n- TP1: %75 Kapat\n- TP2: +1 USDT Kasa\n- TP3: Final Kâr")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s and markets[s]['quoteVolume'] > CONFIG['min_vol_24h']]
            
            for sym in symbols:
                if sym in active_trades: continue
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    try:
                        ex.set_leverage(CONFIG['leverage'], sym)
                        amount = get_precision_and_amount(sym, CONFIG['entry_usdt'], entry)
                        if not amount: continue

                        risk = abs(entry - stop)
                        targets = [
                            entry + (risk * CONFIG['rr_targets'][0]) if side == 'buy' else entry - (risk * CONFIG['rr_targets'][0]),
                            entry + (risk * CONFIG['rr_targets'][1]) if side == 'buy' else entry - (risk * CONFIG['rr_targets'][1]),
                            entry + (risk * CONFIG['rr_targets'][2]) if side == 'buy' else entry - (risk * CONFIG['rr_targets'][2])
                        ]

                        ex.create_market_order(sym, side, amount)
                        active_trades[sym] = True
                        time.sleep(1.5)
                        ex.create_order(sym, 'trigger_market', ('sell' if side == 'buy' else 'buy'), amount, params={'stopPrice': stop, 'triggerPrice': stop, 'reduceOnly': True})

                        msg = (f"🎯 **İŞLEM AÇILDI ({direction})**\nKoin: {sym}\n"
                               f"Giriş: {entry:.4f}\nStop: {stop:.4f}\n"
                               f"Hedefler: {targets[0]:.2f} | {targets[1]:.2f} | {targets[2]:.2f}")
                        bot.send_message(MY_CHAT_ID, msg)
                        
                        threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                    except Exception as e:
                        print(f"Hata: {e}")
                
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
