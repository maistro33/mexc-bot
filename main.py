import ccxt
import telebot
import time
import os
import threading
from datetime import datetime
from math import floor

# --- [1. BAĞLANTILAR] ---
# Buradaki bilgileri kendi anahtarlarınla doldur
API_KEY = 'BURAYA_API_KEY_YAZ'
API_SEC = 'BURAYA_SECRET_YAZ'
PASSPHRASE = 'BURAYA_PASSPHRASE_YAZ'
TELE_TOKEN = 'BURAYA_TELEGRAM_TOKEN_YAZ'
MY_CHAT_ID = 'BURAYA_CHAT_ID_YAZ'

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
    'tp1_ratio': 0.75,           # %75 Kar Al
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'rr_target': 1.3,            
    'timeframe': '5m'            
}

active_trades = {}

# --- [MİKTAR VE HASSASİYET MOTORU] ---
def get_bitget_amount(symbol, usdt_amount, price):
    try:
        market = ex.market(symbol)
        # Bitget'in o koin için istediği minimum adım (0.1, 1, 0.001 vb.)
        precision = market['precision']['amount']
        raw_amount = (usdt_amount * CONFIG['leverage']) / price
        
        if precision is not None:
            # Adım miktarına göre tam yuvarlama yapar (Emrin reddedilmesini engeller)
            amount = floor(raw_amount / precision) * precision
            return float(f"{amount:.8f}".rstrip('0').rstrip('.'))
        return round(raw_amount, 2)
    except Exception as e:
        print(f"Hassasiyet hatası: {e}")
        return None

# --- [3. ÇİFT YÖNLÜ SMC STRATEJİSİ (LONG & SHORT)] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi: Mum açılış/kapanış saniyelerinde temkinli ol
        now_sec = datetime.now().second
        if now_sec < 2 or now_sec > 58: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # LİQUİDİTY & MSS (LONG)
        swing_low = min(l[-15:-1])
        liq_taken_long = l[-1] < swing_low
        recent_high = max(h[-8:-1])
        mss_long = c[-1] > recent_high # GÖVDE KAPANIŞ ONAYI
        
        # LİQUİDİTY & MSS (SHORT)
        swing_high = max(h[-15:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-8:-1])
        mss_short = c[-1] < recent_low # GÖVDE KAPANIŞ ONAYI

        # HACİM ONAYI
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
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # TP1 KONTROLÜ
            condition_tp1 = (price >= tp1) if side == 'buy' else (price <= tp1)
            
            if stage == 0 and condition_tp1:
                bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP1 Hedefine Ulaştı! %75 kapatılıyor ve stop girişe çekiliyor.")
                # TP1 zaten limit emirle borsada kapanmış olmalı, biz stopu güncelliyoruz
                try:
                    ex.cancel_all_orders(symbol) # Eski stopu iptal et
                    time.sleep(1)
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    remaining_qty = amount * (1 - CONFIG['tp1_ratio'])
                    # STOPU GİRİŞE ÇEK
                    ex.create_order(symbol, 'trigger_market', exit_side, remaining_qty, params={'stopPrice': entry, 'reduceOnly': True})
                    stage = 1
                except: pass

            # POZİSYON BİTTİ Mİ?
            pos = ex.fetch_positions([symbol])
            has_pos = False
            for p in pos:
                if p['symbol'] == symbol and float(p['contracts']) != 0:
                    has_pos = True
                    break
            
            if not has_pos:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} işlemi tamamen kapandı.")
                break
            time.sleep(15)
        except: time.sleep(10)

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 RADAR AKTİF! Hem LONG hem SHORT fırsatlar kollanıyor.")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, label = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    try:
                        ex.set_leverage(CONFIG['leverage'], sym)
                        amount = get_bitget_amount(sym, CONFIG['entry_usdt'], entry)
                        if not amount: continue
                        
                        # TP Hesaplama
                        if side == 'buy':
                            tp1 = entry + ((entry - stop) * CONFIG['rr_target'])
                            exit_side = 'sell'
                        else:
                            tp1 = entry - ((stop - entry) * CONFIG['rr_target'])
                            exit_side = 'buy'

                        # 1. MARKET GİRİŞ
                        ex.create_market_order(sym, side, amount)
                        active_trades[sym] = True
                        
                        # 2. STOP LOSS (Planlı Emir)
                        time.sleep(1)
                        ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True})
                        
                        # 3. TAKE PROFIT %75 (Limit Emir)
                        tp1_qty = get_bitget_amount(sym, (CONFIG['entry_usdt'] * CONFIG['tp1_ratio']), tp1)
                        ex.create_order(sym, 'limit', exit_side, tp1_qty, tp1, {'reduceOnly': True})

                        # 4. TELEGRAM BİLGİ
                        msg = f"🎯 **YENİ {label} İŞLEMİ**\nKoin: {sym}\nGiriş: {entry}\nTP1 (%75): {tp1:.4f}\nStop: {stop:.4f}"
                        bot.send_message(MY_CHAT_ID, msg)
                        
                        threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, tp1, amount), daemon=True).start()
                    except Exception as e:
                        print(f"Emir hatası ({sym}): {e}")
                
                time.sleep(0.1)
            time.sleep(60)
        except: time.sleep(10)

# --- KOMUTLAR ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Güncel Bakiye: {bal['total']['USDT']:.2f} USDT")
    except: bot.reply_to(message, "Bakiye alınamadı.")

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades:
        bot.reply_to(message, "🔎 Radar açık, şu an uygun işlem aranıyor...")
    else:
        txt = "📊 Aktif Takipteki İşlemler:\n"
        for s in active_trades.keys(): txt += f"• {s}\n"
        bot.reply_to(message, txt)

if __name__ == "__main__":
    print("Bot başlatılıyor...")
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
