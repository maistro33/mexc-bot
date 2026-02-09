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

# --- [2. AYARLAR - EKSİKLER EKLENDİ] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # %75 TP1
    'rr_targets': [1.3, 2.2, 3.5], # 3 TP için RR seviyeleri
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'timeframe': '5m'            
}

active_trades = {}

# --- [GELİŞMİŞ YUVARLAMA FONKSİYONU - DÜZELTİLDİ] ---
def get_precision_and_amount(symbol, usdt_amount, price):
    try:
        market = ex.market(symbol)
        amount_precision = market['precision']['amount']
        contract_size = market.get('contractSize', 1)
        raw_amount = (usdt_amount * CONFIG['leverage']) / price
        qty_in_contracts = raw_amount / contract_size
        
        if isinstance(amount_precision, int):
            amount = math.floor(qty_in_contracts * (10**amount_precision)) / (10**amount_precision)
        else:
            amount = (qty_in_contracts // amount_precision) * amount_precision
        return amount
    except:
        return round((usdt_amount * CONFIG['leverage'] / price), 1)

# --- [3. ÇİFT YÖNLÜ SMC MOTORU - AYNI BIRAKILDI] ---
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
                return 'buy', c[-1], min(l[-5:]), "LONG"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT"
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP SİSTEMİ - 3 TP VE 1 USDT KASA KURALI EKLENDİ] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- TP1: %75 KAPAT + STOPU GİRİŞE ÇEK ---
            if stage == 0 and ((price >= tp1 if side == 'buy' else price <= tp1)):
                qty_to_close = amount * CONFIG['tp1_ratio']
                ex.create_market_order(symbol, exit_side, qty_to_close, params={'reduceOnly': True})
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                remaining = amount - qty_to_close
                # Stopu Girişe Çek (Garantili Parametreler)
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'triggerPrice': entry, 'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 ALINDI (%75)!\nStop girişe çekildi.")
                stage = 1

            # --- TP2: 1 USDT KÂR AL VE KASAYA KOY ---
            elif stage == 1 and ((price >= tp2 if side == 'buy' else price <= tp2)):
                qty_1_usdt = get_precision_and_amount(symbol, 1.0, price)
                if qty_1_usdt and qty_1_usdt > 0:
                    ex.create_market_order(symbol, exit_side, qty_1_usdt, params={'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2: 1 USDT kasaya eklendi.")
                stage = 2

            # --- TP3: FİNAL KAPANIŞ ---
            elif stage == 2 and ((price >= tp3 if side == 'buy' else price <= tp3)):
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3 FİNAL: Kâr alındı ve işlem bitti.")
                break

            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                ex.cancel_all_orders(symbol)
                break
            time.sleep(15)
        except: time.sleep(5)

# --- [5. ANA DÖNGÜ - STOP VE MESAJ EKSİKLERİ DÜZELTİLDİ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 BOT AKTİF: 3 TP ve Stop Garantisi Devrede!")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    try:
                        ex.set_leverage(CONFIG['leverage'], sym)
                        amount = get_precision_and_amount(sym, CONFIG['entry_usdt'], entry)
                        if not amount: continue

                        # 3 TP Fiyatlarını Hesapla
                        risk = abs(entry - stop)
                        targets = [entry + (risk * r) if side == 'buy' else entry - (risk * r) for r in CONFIG['rr_targets']]
                        exit_side = 'sell' if side == 'buy' else 'buy'

                        # 1. POZİSYONU AÇ
                        ex.create_market_order(sym, side, amount)
                        active_trades[sym] = True
                        
                        # 2. STOP LOSS GARANTİSİ (Bitget v2 standartı)
                        time.sleep(1.5)
                        ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'triggerPrice': stop, 'reduceOnly': True})
                        
                        # 3. TELEGRAM MESAJI (İşlem açılınca)
                        msg = (f"🎯 **İŞLEM AÇILDI ({direction})**\nKoin: {sym}\n"
                               f"Giriş: {entry:.4f}\nStop: {stop:.4f}\n"
                               f"TP1: {targets[0]:.4f} | TP2: {targets[1]:.4f} | TP3: {targets[2]:.4f}")
                        bot.send_message(MY_CHAT_ID, msg)

                        threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                    except Exception as e:
                        print(f"Hata: {e}")
                
                time.sleep(0.1)
            time.sleep(30)
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
