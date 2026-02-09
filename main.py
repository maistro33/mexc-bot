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

# --- [2. AYARLAR & PANEL] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # %75 Kar Al kuralı (İsteğin üzerine)
    'max_active_trades': 4,      
    'min_vol_24h': 10000000,     
    'rr_target': 2.0             # 1:2 RR hedefi
}

active_trades = {}

# --- [3. LİKİDİTE & TREND MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi: Mum açılış/kapanış saniyelerinde işlem yapmaz
        now_sec = datetime.now().second
        if 0 <= now_sec <= 5 or 55 <= now_sec <= 59: return None, None, None, None

        # --- [HTF - ÜST ZAMAN DİLİMİ KONTROLÜ] ---
        # 1 Günlük, 4 Saatlik ve 1 Saatlik Trend Onayı (Tepeden almamak için)
        for tf in ['1d', '4h', '1h']:
            bars_tf = ex.fetch_ohlcv(symbol, timeframe=tf, limit=20)
            close_prices = [b[4] for b in bars_tf]
            sma_20 = sum(close_prices) / 20
            if close_prices[-1] < sma_20: # Fiyat ortalamanın altındaysa LONG açmaz
                return None, None, None, None

        # --- [LTF - 15 DAKİKALIK GİRİŞ ANALİZİ] ---
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1- Likidite Alımı (Stop Hunting Koruması)
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low and c[-1] > swing_low

        # 2 & 3- MSS & Gövde Kapanış Onayı (Market Structure Shift)
        recent_high = max(h[-10:-1])
        mss_ok = c[-1] > recent_high
        
        # 4- Hacim ve FVG Onayı (Fair Value Gap)
        avg_vol = sum(v[-6:-1]) / 5
        fvg_ok = h[-3] < l[-1]
        entry_price = h[-3] # FVG başlangıcından giriş
        
        if liq_taken and mss_ok and v[-1] > avg_vol and fvg_ok:
            if c[-1] <= entry_price * 1.005:
                # 5- Stop FVG sonuna veya en son swing noktasına
                stop_loss = min(l[-5:])
                return 'LONG', c[-1], stop_loss, "BOĞA FVG"
        
        return None, None, None, None
    except: return None, None, None, None

# --- [4. MESAJ FORMATI] ---
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
        
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * CONFIG['rr_target'])

        send_telegram_signal(symbol, side, entry, fvg_type)

        # Giriş emri
        ex.create_market_order(symbol, 'buy', amount)
        time.sleep(1)

        # Stop Loss (Görsel Madde 5 - Borsaya iletilir)
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        
        # TP1 (%75 Kapatma - Senin Kuralın)
        ex.create_order(symbol, 'limit', 'sell', amount * CONFIG['tp1_ratio'], tp1, {'reduceOnly': True})
        
        # TP2 (%25 Kapatma - 1:2 RR)
        ex.create_order(symbol, 'limit', 'sell', amount * (1 - CONFIG['tp1_ratio']), tp2, {'reduceOnly': True})

        active_trades[symbol] = True
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası: {str(e)}")

# --- [6. EK KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        balance = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 **BAKİYE:** {balance['USDT']['free']:.2f} USDT")
    except: bot.reply_to(message, "❌ Bakiye çekilemedi.")

# --- [7. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 Radar ve Trend Onay Filtreleri Aktif. Taramaya başlıyorum...")
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
            time.sleep(300) 
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
