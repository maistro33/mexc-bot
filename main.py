import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR & DEĞİŞKENLER] ---
# Railway panelinde Variables kısmına bunları eklediğinden emin ol
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
        'positionMode': True  # Hedge Mode Hatasını Çözer
    },
    'enableRateLimit': True
})

bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR - SENİN PARAMETRELERİN] ---
CONFIG = {
    'entry_usdt': 20.0,           # İşlem başına 20 USDT
    'leverage': 10,               # 10x Kaldıraç
    'Close_Percentage_TP1': 0.75,  # %75 Kâr Al (TP1)
    'max_active_trades': 3,       # Aynı anda maks 3 işlem
    'rr_target': 1.2,             # Risk Ödül Oranı (Scalp için ideal)
    'timeframe': '1m'             # 1 Dakikalık Scalp
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

# --- [3. ANTİ-MANİPÜLASYON ANALİZ MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi (Mum açılış/kapanış saniyeleri)
        now_sec = datetime.now().second
        if now_sec < 2 or now_sec > 58: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=30)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1. Hacim Onayı (Önceki 10 mumun ortalamasının 1.1 katı)
        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.1)

        if not vol_ok: return None, None, None, None

        # 2. Likidite Alımı + Gövde Kapanış Onayı (SMC)
        swing_low = min(l[-12:-1])
        liq_taken_long = l[-1] < swing_low and c[-1] > swing_low # İğne attı, içeride kapattı

        swing_high = max(h[-12:-1])
        liq_taken_short = h[-1] > swing_high and c[-1] < swing_high

        # Sinyal Kararı
        if liq_taken_long and c[-1] > h[-2]:
            return 'buy', c[-1], l[-1], "LONG_SMC"
        if liq_taken_short and c[-1] < l[-2]:
            return 'sell', c[-1], h[-1], "SHORT_SMC"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. İŞLEM TAKİP VE TELEGRAM MESAJLARI] ---
def monitor_trade(symbol, side, entry, stop, tp1, amount):
    try:
        msg = f"🚀 **YENİ İŞLEM AÇILDI**\n💎 Sembol: {symbol}\n📈 Yön: {side.upper()}\n💰 Giriş: {entry}\n🛑 Stop: {stop}\n🎯 TP1 (%75): {tp1}"
        bot.send_message(MY_CHAT_ID, msg)
        
        while symbol in active_trades:
            time.sleep(20)
            pos = ex.fetch_positions([symbol])
            # Pozisyon kapandıysa (kontrat sayısı 0 ise)
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM KAPANDI**\n{symbol} pozisyonu başarıyla tamamlandı veya stop oldu.")
                break
    except: pass

# --- [5. ANA DÖNGÜ (RADAR)] ---
def main_loop():
    while True:
        try:
            markets = ex.fetch_tickers()
            # En hacimli 80 coini tara (Hız için)
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'] if markets[x]['quoteVolume'] else 0,
                reverse=True
            )[:80]

            for sym in sorted_symbols:
                if sym in active_trades: continue
                if len(active_trades) >= CONFIG['max_active_trades']: break

                side, entry, stop, msg_type = analyze_smc_strategy(sym)
                
                if side:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    pos_side = 'long' if side == 'buy' else 'short'
                    
                    # Hedef Hesaplama
                    dist = abs(entry - stop)
                    tp1 = entry + (dist * CONFIG['rr_target']) if side == 'buy' else entry - (dist * CONFIG['rr_target'])

                    # 1. MARKET GİRİŞ
                    ex.create_market_order(sym, side, amount, params={'posSide': pos_side})
                    active_trades[sym] = True
                    time.sleep(1)

                    # 2. STOP LOSS
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})

                    # 3. KADEMELİ KAR AL (%75)
                    tp1_qty = round_amount(sym, amount * CONFIG['Close_Percentage_TP1'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp1_qty, params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': pos_side})

                    # İzleme Thread'ini Başlat
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, tp1, amount), daemon=True).start()
                
            time.sleep(2) # Tarama döngüsü arası kısa bekleme
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(10)

# --- [6. TELEGRAM KOMUTLARI & BAŞLATMA] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        usdt = bal['total']['USDT']
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt:.2f} USDT")
    except Exception as e:
        bot.reply_to(message, f"Bakiye alınamadı: {e}")

if __name__ == "__main__":
    ex.load_markets()
    bot.send_message(MY_CHAT_ID, "✅ **Railway Bulut Scalper Yayında!**\nSMC Stratejisi ve %75 TP Aktif.")
    
    # Telegram'ı ayrı kolda çalıştır (Donmayı önler)
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    # Ana döngüyü başlat
    main_loop()
