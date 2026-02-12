import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR & ENV VARIABLES] ---
# Railway panelinde bu isimlerle değişkenleri tanımlamayı unutma!
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {
        'defaultType': 'swap',
        'positionMode': True  # Hedge Modu Hatasını Çözen Ayar
    },
    'enableRateLimit': True
})

bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR - SENİN İSTEDİĞİN GİBİ] ---
CONFIG = {
    'entry_usdt': 20.0,          # 20 USDT Giriş
    'leverage': 10,              # 10x Kaldıraç
    'Close_Percentage_TP1': 0.75, # %75 Kâr Al (Senin isteğin)
    'max_active_trades': 3,      # Maksimum 3 eş zamanlı işlem
    'rr_target': 1.1,            # Scalp için Risk Ödül Oranı
    'timeframe': '1m'            # Scalp için 1 dakikalık grafik
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

# --- [3. ANTİ-MANİPÜLASYON MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        # 1. Zaman Filtresi (Manipülasyonun yoğun olduğu saniyeler)
        now_sec = datetime.now().second
        if now_sec < 2 or now_sec > 58: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=30)
        h = [b[2] for b in bars]
        l = [b[3] for b in bars]
        c = [b[4] for b in bars]
        v = [b[5] for b in bars]

        # 2. Gövde Kapanış Onayı (Body Close)
        # Sadece iğne (wick) değil, mumun o seviyenin dışında kapanması
        swing_low = min(l[-10:-1])
        liq_taken_long = l[-1] < swing_low and c[-1] > swing_low # İğne attı geri topladı

        # 3. Hacim Onaylı MSS (Market Structure Shift)
        avg_vol = sum(v[-10:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.1) # 1.1x Hacim onayı

        # Long Sinyali
        if vol_ok and liq_taken_long and c[-1] > h[-2]:
            return 'buy', c[-1], l[-1], "LONG_SMC"
            
        # Short Sinyali
        swing_high = max(h[-10:-1])
        liq_taken_short = h[-1] > swing_high and c[-1] < swing_high
        if vol_ok and liq_taken_short and c[-1] < l[-2]:
            return 'sell', c[-1], h[-1], "SHORT_SMC"

        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP VE RAPORLAMA] ---
def monitor_trade(symbol, side, entry, stop, tp1, amount):
    bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM BAŞLADI**\n{symbol} | {side.upper()}\nGiriş: {entry}\nStop: {stop}\nTP1: {tp1}")
    while symbol in active_trades:
        try:
            time.sleep(10)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM KAPANDI**\n{symbol} hedefe ulaştı veya stop oldu.")
                break
        except: break

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            # Hacmi en yüksek 100 coini tara
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'] if markets[x]['quoteVolume'] else 0,
                reverse=True
            )[:100]

            for sym in sorted_symbols:
                if sym in active_trades: continue
                side, entry, stop, msg_type = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    pos_side = 'long' if side == 'buy' else 'short'
                    
                    # Risk Ödül Hesaplama
                    dist = abs(entry - stop)
                    tp1 = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])

                    # 1. MARKET GİRİŞ
                    ex.create_market_order(sym, side, amount, params={'posSide': pos_side})
                    active_trades[sym] = True
                    time.sleep(1)

                    # 2. STOP LOSS (Trigger Market)
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})

                    # 3. KADEMELİ KAR AL (TP1 %75)
                    tp1_qty = round_amount(sym, amount * CONFIG['Close_Percentage_TP1'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': pos_side})

                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, tp1, amount), daemon=True).start()
                
            time.sleep(5) # Tarama hızı
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID, "✅ **Railway Bulut Scalper Yayında!**\nManipülasyon kalkanları aktif.")
    main_loop()
