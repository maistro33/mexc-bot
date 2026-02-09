import ccxt
import telebot
import time
import os
import threading
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

# --- [2. GÜÇLENDİRİLMİŞ AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,          # İşlem başına USDT miktarı
    'leverage': 10,              # Kaldıraç ayarı
    'tp1_ratio': 0.75,           # %75 Kar Al kuralı
    'max_active_trades': 4,      # Aynı anda açık maksimum işlem
    'min_vol_24h': 10000000,     # Hacimsiz coinlerden uzak durur
    'rr_target': 2.0             # 1:2 RR hedefi (Görsel Madde 6)
}

active_trades = {}

# --- [3. SMC STRATEJİ MOTORU (Görseldeki 6 Madde)] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi (Manipülasyon Koruması)
        now_sec = datetime.now().second
        if 0 <= now_sec <= 5 or 55 <= now_sec <= 59: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1- Önemli Likidite Seviyesi Alımı (Görsel Madde 1)
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low and c[-1] > swing_low

        # 2 & 3- MSS & Displacement (Gövde Kapanış Onaylı) (Görsel Madde 2-3)
        recent_high = max(h[-10:-1])
        mss_ok = c[-1] > recent_high # Sadece gövde kapanışı (Anti-stop hunting)
        
        # Hacim Onayı (Ekstra Kalkan)
        avg_vol = sum(v[-6:-1]) / 5
        vol_ok = v[-1] > avg_vol

        # 4- Market Yapısının Değiştiği Yerdeki FVG (Görsel Madde 4)
        fvg_ok = h[-3] < l[-1] 
        entry_price = h[-3] # FVG başlangıç seviyesi
        
        if liq_taken and mss_ok and vol_ok and fvg_ok:
            if c[-1] <= entry_price * 1.005: # Çok kaçmadıysa gir
                # 5- Stop Seviyesi (En Son Swing Noktası) (Görsel Madde 5)
                stop_loss = min(l[-5:])
                return 'LONG', c[-1], stop_loss, "BOĞA FVG"
        
        return None, None, None, None
    except: return None, None, None, None

# --- [4. MESAJ FORMATI (Görsel Uyumu)] ---
def send_telegram_signal(symbol, side, price, fvg_type):
    msg = (f"🎯 **SADIK BEY, FIRSAT YAKALANDI!**\n\n"
           f"🌚 **Koin:** {symbol.split(':')[0]}\n"
           f"🔄 **Trend Dönüşü (MSS):** ONAYLANDI\n"
           f"🕳️ **Boşluk Analizi (FVG):** {fvg_type} ✅\n"
           f"📊 **Yön:** {'📈 YUKARI (LONG)' if side == 'LONG' else '📉 AŞAĞI (SHORT)'}\n"
           f"💰 **Fiyat:** {price:.4f}\n"
           f"🛡️ **Strateji:** {CONFIG['entry_usdt']} USDT | {CONFIG['leverage']}x | %75 TP1")
    bot.send_message(MY_CHAT_ID, msg)

# --- [5. EMİR YÖNETİMİ] ---
def execute_trade(symbol, side, entry, stop, fvg_type):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry
        
        # RR Hesaplama
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * CONFIG['rr_target'])

        send_telegram_signal(symbol, side, entry, fvg_type)

        # Giriş
        ex.create_market_order(symbol, 'buy' if side == 'LONG' else 'sell', amount)
        time.sleep(1)

        # Stop Loss
        ex.create_order(symbol, 'trigger_limit', 'sell' if side == 'LONG' else 'buy', 
                         amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        
        # TP1 (%75)
        ex.create_order(symbol, 'limit', 'sell' if side == 'LONG' else 'buy', 
                         amount * CONFIG['tp1_ratio'], tp1, {'reduceOnly': True})
        
        # TP2 (%25)
        ex.create_order(symbol, 'limit', 'sell' if side == 'LONG' else 'buy', 
                         amount * (1 - CONFIG['tp1_ratio']), tp2, {'reduceOnly': True})

        active_trades[symbol] = True
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası: {str(e)}")

# --- [6. EKSTRA KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    balance = ex.fetch_balance({'type': 'swap'})
    bot.reply_to(message, f"💰 **BAKİYE:** {balance['USDT']['free']:.2f} USDT")

@bot.message_handler(commands=['radar'])
def get_radar(message):
    tickers = ex.fetch_tickers()
    report = "📡 **RADAR:** " + ", ".join([s.split(':')[0] for s in list(tickers.keys())[:5]])
    bot.send_message(MY_CHAT_ID, report)

# --- [7. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 Bot Başlatıldı. Borsayı tarıyorum...")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades: continue
                if markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue

                side, entry, stop, fvg = analyze_smc_strategy(sym)
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    execute_trade(sym, side, entry, stop, fvg)
                time.sleep(0.1)
            time.sleep(300) # 5 dakikada bir tarama
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
