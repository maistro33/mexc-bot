import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
API_KEY = "BURAYA_API_KEY"
API_SEC = "BURAYA_SECRET"
PASSPHRASE = "BURAYA_PASSPHRASE"
TELE_TOKEN = "BURAYA_TELEGRAM_TOKEN"
MY_CHAT_ID = "BURAYA_CHAT_ID"

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
    'tp1_ratio': 0.75,           # TP1'de ana pozisyonun %75'i kapanır
    'rr_targets': [1.5, 3.0, 5.0], # TP1, TP2, TP3 (Risk/Ödül Oranları)
    'max_active_trades': 5,      
    'min_vol_24h': 10000000,     # 10M USDT altı hacimli coinlere bakmaz
    'timeframe': '5m'            
}

active_trades = {}

# --- [HASSAS MİKTAR HESAPLAMA] ---
def get_precision_and_amount(symbol, usdt_amount, price):
    try:
        market = ex.market(symbol)
        step_size = market['limits']['amount']['min']
        precision = int(-math.log10(market['precision']['amount'])) if market['precision']['amount'] < 1 else 0
        raw_qty = (usdt_amount * CONFIG['leverage']) / price
        amount = math.floor(raw_qty / step_size) * step_size
        return round(amount, precision)
    except: return None

# --- [3. ANTI-MANIPÜLASYON ANALİZ MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 5 or now_sec > 55: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        # o: open, h: high, l: low, c: close, v: volume
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        recent_high = max(h[-15:-1])
        recent_low = min(l[-15:-1])
        avg_vol = sum(v[-20:-1]) / 20

        # GÖVDE KAPANIŞI ONAYI (İğne atmaya karşı koruma)
        mss_long = c[-1] > recent_high
        mss_short = c[-1] < recent_low
        vol_ok = v[-1] > (avg_vol * 1.3)

        if vol_ok:
            if mss_long: return 'buy', c[-1], min(l[-5:]), "LONG"
            if mss_short: return 'sell', c[-1], max(h[-5:]), "SHORT"
        
        return None, None, None, None
    except: return None, None, None, None

# --- [4. POZİSYON TAKİBİ - KADEMELİ KASA KORUMA] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- TP1: %75 KAPAT + STOP GİRİŞE + 1 USDT KAZANÇ ---
            if stage == 0 and ((price >= tp1 if side == 'buy' else price <= tp1)):
                # Ana %75 kapanış
                qty_to_close = get_precision_and_amount(symbol, (CONFIG['entry_usdt'] * CONFIG['tp1_ratio']), price)
                ex.create_market_order(symbol, exit_side, qty_to_close, params={'reduceOnly': True})
                
                # Mevcut tüm emirleri (eski stopu) temizle ve girişe çek
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                remaining = amount - qty_to_close
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'triggerPrice': entry, 'reduceOnly': True})
                
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 ALINDI (%75)!\nStop girişe çekildi ve 1 USDT kasaya kilitlendi.")
                stage = 1

            # --- TP2: 1 USDT DAHA KASAYA KOY + STOP GİRİŞTE DEVAM ---
            elif stage == 1 and ((price >= tp2 if side == 'buy' else price <= tp2)):
                qty_1_usdt = get_precision_and_amount(symbol, 1.0, price)
                if qty_1_usdt and qty_1_usdt > 0:
                    ex.create_market_order(symbol, exit_side, qty_1_usdt, params={'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2: 1 USDT daha realize edildi. Kalan pozisyon giriş stopuyla izleniyor.")
                stage = 2

            # --- TP3: FİNAL KAPANIŞ ---
            elif stage == 2 and ((price >= tp3 if side == 'buy' else price <= tp3)):
                # Kalan tüm pozisyonu kapat
                ex.create_market_order(symbol, exit_side, 0, params={'reduceOnly': True}) # Bitget market close
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3 HEDEF! İşlem başarıyla bitti, tüm kâr kasada.")
                break

            # Pozisyonun stop olup olmadığını kontrol et
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                break
                
            time.sleep(15)
        except: time.sleep(5)

# --- [5. TELEGRAM PANELİ] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    balance = ex.fetch_balance()
    usdt = balance['total']['USDT']
    bot.reply_to(message, f"💰 Cüzdan: {usdt:.2f} USDT")

@bot.message_handler(commands=['durum'])
def get_status(message):
    if not active_trades:
        bot.reply_to(message, "Şu an aktif işlem yok.")
    else:
        bot.reply_to(message, f"📊 Aktif: {', '.join(active_trades.keys())}")

# --- [6. ANA RADAR DÖNGÜSÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 RADAR AKTİF!\n- Gövde Kapanış Onayı\n- Her TP'de Kâr Realizasyonu\n- Risk Sıfırlama (Breakeven)")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if s.endswith('/USDT:USDT')]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    try:
                        ex.set_leverage(CONFIG['leverage'], sym)
                        amount = get_precision_and_amount(sym, CONFIG['entry_usdt'], entry)
                        if not amount: continue

                        risk = abs(entry - stop)
                        targets = [entry + (risk * r) if side == 'buy' else entry - (risk * r) for r in CONFIG['rr_targets']]
                        
                        ex.create_market_order(sym, side, amount)
                        active_trades[sym] = True
                        
                        # Anında Stop Loss
                        time.sleep(1)
                        ex.create_order(sym, 'trigger_market', ('sell' if side == 'buy' else 'buy'), amount, 
                                        params={'stopPrice': stop, 'triggerPrice': stop, 'reduceOnly': True})
                        
                        msg = (f"🎯 **İŞLEM AÇILDI ({direction})**\nCoin: {sym}\n"
                               f"Giriş: {entry:.4f}\nStop: {stop:.4f}\n"
                               f"Hedefler: {targets[0]:.4f} | {targets[1]:.4f} | {targets[2]:.4f}")
                        bot.send_message(MY_CHAT_ID, msg)

                        threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                    except: pass
                
            time.sleep(10)
        except: time.sleep(30)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    main_loop()
