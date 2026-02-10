import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
# Railway ortam değişkenlerinden veya doğrudan buraya yazarak doldurun
API_KEY = os.getenv('BITGET_API') or 'BURAYA_API_KEY'
API_SEC = os.getenv('BITGET_SEC') or 'BURAYA_SECRET'
PASSPHRASE = os.getenv('BITGET_PASSPHRASE') or 'BURAYA_PASSWORD'
TELE_TOKEN = os.getenv('TELE_TOKEN') or 'BURAYA_TOKEN'
MY_CHAT_ID = os.getenv('MY_CHAT_ID') or 'BURAYA_CHAT_ID'

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {
        'defaultType': 'swap',
        'positionMode': True 
    },
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AGRESİF AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,          # 20 USDT Giriş
    'leverage': 10,              # 10x Kaldıraç
    'tp1_ratio': 0.75,           # %75 Kâr Al (Sizin istediğiniz)
    'max_active_trades': 5,      # Aynı anda 5 işleme kadar izin (Agresif)
    'min_vol_24h': 1000000,      # Hacim alt sınırını düşürdüm (Daha çok coin taranır)
    'rr_target': 1.2,            # Kâr hedefini biraz yakına çektim (Hızlı çıkış)
    'timeframe': '5m'            # 5 Dakikalık periyot
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

# --- [3. SMC ANALİZ MOTORU - AGRESİF MOD] ---
def analyze_smc_strategy(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # LİKİDİTE ALIMI (Agresif: Son 10 muma bakıyoruz)
        swing_low = min(l[-10:-1])
        liq_taken_long = l[-1] < swing_low
        
        # MSS (Market Yapısı Kırılımı) - Agresif: Son 5 mumun en yükseği
        recent_high = max(h[-5:-1])
        mss_long = c[-1] > recent_high 
        
        swing_high = max(h[-10:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-5:-1])
        mss_short = c[-1] < recent_low 

        # AGRESİF HACİM ONAYI (%10 Artış yeterli)
        avg_vol = sum(v[-6:-1]) / 5
        vol_ok = v[-1] > (avg_vol * 1.1)
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-3:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-3:]), "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP VE RAPORLAMA] ---
def report_loop():
    while True:
        try:
            time.sleep(600) # 10 dakikada bir rapor
            if scanned_list:
                msg = f"📡 **SMC AGRESİF RADAR**\n"
                msg += f"🔍 {len(scanned_list)} coin taranıyor.\n"
                msg += f"📈 Aktif İşlem: {len(active_trades)}"
                bot.send_message(MY_CHAT_ID, msg)
        except: pass

def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(20)
            pos = ex.fetch_positions([symbol])
            # Pozisyon kapandıysa listeden çıkar
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                break
        except: break

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    global scanned_list
    while True:
        try:
            markets = ex.fetch_tickers()
            # Hacmi 1M USDT üzerindeki coinleri tara
            sorted_symbols = [
                s for s in markets if '/USDT:USDT' in s 
                and (markets[s]['quoteVolume'] if markets[s]['quoteVolume'] else 0) > CONFIG['min_vol_24h']
            ]
            
            scanned_list = sorted_symbols[:150]
            
            for sym in scanned_list:
                if sym in active_trades: continue
                side, entry, stop, msg_type = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    # Kaldıraç ve Mod Ayarı
                    try:
                        ex.set_leverage(CONFIG['leverage'], sym)
                        ex.set_position_mode(True, sym)
                    except: pass

                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    pos_side = 'long' if side == 'buy' else 'short'
                    
                    # TP ve Stop Hesaplama
                    risk = abs(entry - stop)
                    tp1 = entry + (risk * CONFIG['rr_target']) if side == 'buy' else entry - (risk * CONFIG['rr_target'])

                    # 1. Giriş Emri
                    ex.create_market_order(sym, side, amount, params={'posSide': pos_side})
                    active_trades[sym] = True
                    time.sleep(1)

                    # 2. Stop Loss
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})
                    
                    # 3. TP1 (%75)
                    tp1_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': pos_side})

                    bot.send_message(MY_CHAT_ID, f"⚡ **AGRESİF İŞLEM AÇILDI**\n{sym}\nYön: {side.upper()}\nGiriş: {entry}\nTP1 (%75): {tp1}\nStop: {stop}")
                    threading.Thread(target=monitor_trade, args=(sym,), daemon=True).start()
                
                time.sleep(0.05) # Tarama hızını artırdım
            time.sleep(10) 
        except Exception as e:
            time.sleep(10)

# Telegram Komutları
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Kasa: {bal['total']['USDT']:.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    try:
        msg = f"📡 **Agresif Mod: AKTİF**\n🔍 Taranan: {len(scanned_list)} Coin\n📈 Aktif: {len(active_trades)}"
        bot.reply_to(message, msg)
    except: pass

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=report_loop, daemon=True).start()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
