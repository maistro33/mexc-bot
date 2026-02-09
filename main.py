import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
# Orijinal yapındaki gibi sistemden çekmeye devam ediyor
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
    'rr_targets': [1.3, 2.5, 4.5], # TP1, TP2, TP3 RR Hedefleri
    'timeframe': '5m'            
}

active_trades = {}
last_scanned_symbols = [] # 5 Dakikalık rapor için

# --- [HASSASİYET MOTORU] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        if precision < 1:
            step = int(-math.log10(precision))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. ÇİFT YÖNLÜ SMC MOTORU (ANTI-MANIPULASYON)] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi: Mum açılış/kapanış saniyelerinde temkinli duruş
        now_sec = datetime.now().second
        if now_sec < 5 or now_sec > 55: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=100)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # Gövde Kapanış Onayı (Body Close)
        recent_high = max(h[-15:-1])
        recent_low = min(l[-15:-1])
        
        # Hacim Onayı (Gerçek para girişini doğrula)
        avg_vol = sum(v[-20:-1]) / 20
        vol_ok = v[-1] > (avg_vol * 1.5) 

        mss_long = c[-1] > recent_high 
        mss_short = c[-1] < recent_low

        # Likidite Alımı (Stop Hunting Kalkanı)
        liq_taken_long = any(low < min(l[-30:-15]) for low in l[-15:-1])
        liq_taken_short = any(high > max(h[-30:-15]) for high in h[-15:-1])
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP SİSTEMİ - 3 TP VE KESİN STOP] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- TP1: %75 KAPAT + STOP GİRİŞE (KESİN) ---
            if stage == 0 and ((price >= tp1 if side == 'buy' else price <= tp1)):
                qty_tp1 = round_amount(symbol, amount * CONFIG['tp1_ratio'])
                ex.create_market_order(symbol, exit_side, qty_tp1, params={'reduceOnly': True})
                
                ex.cancel_all_orders(symbol) # Eski stopu iptal et
                time.sleep(2)
                remaining = round_amount(symbol, amount - qty_tp1)
                
                # Kesin Stop: Girişe Taşıma Emri (Borsa Sistemine Kayıtlı)
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'reduceOnly': True})
                
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 (%75) Tamam!\nKâr realize edildi, kalan işlem için stop girişe ({entry}) çekildi.")
                stage = 1

            # --- TP2 ---
            elif stage == 1 and ((price >= tp2 if side == 'buy' else price <= tp2)):
                qty_tp2 = round_amount(symbol, amount * 0.15)
                ex.create_market_order(symbol, exit_side, qty_tp2, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2 Hedefine ulaşıldı.")
                stage = 2

            # --- TP3: FİNAL KAPANIŞ (TAMAMINI KAPAT) ---
            elif stage == 2 and ((price >= tp3 if side == 'buy' else price <= tp3)):
                ex.create_market_order(symbol, exit_side, 0, params={'reduceOnly': True, 'closeAll': True})
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3: İşlem başarıyla bitti, tüm kâr kasada!")
                if symbol in active_trades: del active_trades[symbol]
                break

            # Stop Kontrolü (Borsa pozisyonu kapattı mı?)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"ℹ️ {symbol} işlemi stop seviyesinde veya manuel kapandı.")
                break
            time.sleep(20)
        except: time.sleep(10)

# --- [5. 5 DAKİKALIK RAPORLAMA] ---
def report_loop():
    while True:
        try:
            time.sleep(300) # 5 Dakikada bir
            if last_scanned_symbols:
                msg = "📊 **TARAMA RAPORU (5 DK)**\n\n🔍 Taranan Coinler (İlk 20):\n"
                msg += ", ".join(last_scanned_symbols[:20])
                msg += f"\n\n✅ Aktif İşlem Sayısı: {len(active_trades)}\nSMC kalkanları aktif, sinyal aranıyor..."
                bot.send_message(MY_CHAT_ID, msg)
        except: pass

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    global last_scanned_symbols
    bot.send_message(MY_CHAT_ID, "🚀 RADAR BAŞLATILDI!\nAnti-Manipülasyon, %75 TP1 ve Kesin Stop aktif.")
    while True:
        try:
            markets = ex.fetch_tickers()
            # Hacme göre sırala
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True
            )
            last_scanned_symbols = [s.split('/')[0] for s in sorted_symbols]
            
            for sym in sorted_symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    risk = abs(entry - stop)
                    targets = [entry + (risk * r) if side == 'buy' else entry - (risk * r) for r in CONFIG['rr_targets']]
                    
                    # Giriş Emri
                    ex.create_market_order(sym, side, amount)
                    active_trades[sym] = True
                    
                    # İlk Kesin Stop Emri (Borsaya Kayıtlı)
                    time.sleep(2)
                    ex.create_order(sym, 'trigger_market', ('sell' if side == 'buy' else 'buy'), amount, 
                                    params={'stopPrice': stop, 'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI ({direction})**\nKoin: {sym}\nGiriş: {entry:.4f}\nTP1: {targets[0]:.4f}\nStop: {stop:.4f}")
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                
            time.sleep(30)
        except: time.sleep(15)

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance()
        bot.reply_to(message, f"💰 Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades: bot.reply_to(message, "🔍 Radar açık, şu an işlem yok.")
    else: bot.reply_to(message, f"📊 Aktif: {', '.join(active_trades.keys())}")

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=report_loop, daemon=True).start()
    bot.infinity_polling()
