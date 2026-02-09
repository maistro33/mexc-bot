import ccxt
import telebot
import time
import os
import threading
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
# Railway veya Terminal üzerinden bu değişkenleri tanımladığınızdan emin olun.
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
    'entry_usdt': 20.0,          # Panelden ayarlanabilir bakiye
    'leverage': 10,              # Kaldıraç ayarı
    'tp1_ratio': 0.75,           # %75 Kar Al kuralı
    'max_active_trades': 4,      # Maksimum açık işlem sayısı
    'min_vol_24h': 10000000,     # Hacim filtresi (Likidite koruması)
    'rr_target': 2.0             # 1:2 RR Hedefi (Görsel Madde 6)
}

active_trades = {}

# --- [3. LİKİDİTE & STRATEJİ MOTORU (6 MADDE)] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi: Manipülasyonun yoğun olduğu saniyelerde durur
        now_sec = datetime.now().second
        if 0 <= now_sec <= 5 or 55 <= now_sec <= 59: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1- Önemli Likidite Seviyesi Alımı (Görsel Madde 1)
        # Likidite süpürme kontrolü (Liquidity Sweep)
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low and c[-1] > swing_low

        # 2 & 3- MSS & Trend Dönüşü (Gövde Kapanış Onaylı) (Görsel Madde 2-3)
        recent_high = max(h[-10:-1])
        mss_ok = c[-1] > recent_high # Gövde kapanış onayı (Anti-Stop Hunting)
        
        # Hacim Onaylı MSS (Manipülasyon Kalkanı)
        avg_vol = sum(v[-6:-1]) / 5
        vol_ok = v[-1] > avg_vol

        # 4- Market Yapısının Değiştiği Yerdeki FVG (Görsel Madde 4)
        fvg_ok = h[-3] < l[-1] 
        entry_price = h[-3] # FVG giriş noktası
        
        if liq_taken and mss_ok and vol_ok and fvg_ok:
            if c[-1] <= entry_price * 1.005:
                # 5- Stop FVG sonuna veya en son swing noktasına (Görsel Madde 5)
                stop_loss = min(l[-5:])
                return 'LONG', c[-1], stop_loss, "BOĞA FVG"
        
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TELEGRAM MESAJ FORMATI (GÖRSEL UYUMLU)] ---
def send_telegram_signal(symbol, side, price, fvg_type):
    msg = (f"🎯 **SADIK BEY, FIRSAT YAKALANDI!**\n\n"
           f"🌚 **Koin:** {symbol.split(':')[0]}\n"
           f"🔄 **Trend Dönüşü (MSS):** ONAYLANDI\n"
           f"🕳️ **Boşluk Analizi (FVG):** {fvg_type} ✅\n"
           f"📊 **Yön:** {'📈 YUKARI (LONG)' if side == 'LONG' else '📉 AŞAĞI (SHORT)'}\n"
           f"💰 **Fiyat:** {price:.4f}\n"
           f"🛡️ **Strateji:** {CONFIG['entry_usdt']} USDT | {CONFIG['leverage']}x | %75 TP1")
    bot.send_message(MY_CHAT_ID, msg)

# --- [5. EMİR YÖNETİMİ - STOP & TP GARANTİSİ] ---
def execute_trade(symbol, side, entry, stop, fvg_type):
    try:
        # Kaldıraç ayarla
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry
        
        # RR Seviyelerini Hesapla (1:2 RR)
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * CONFIG['rr_target'])

        # Mesaj Gönder (Görseldeki gibi)
        send_telegram_signal(symbol, side, entry, fvg_type)

        # 1. Market Giriş Emri
        ex.create_market_order(symbol, 'buy' if side == 'LONG' else 'sell', amount)
        time.sleep(1)

        # 2. Stop Loss Emri (Borsaya iletilir)
        ex.create_order(symbol, 'trigger_limit', 'sell' if side == 'LONG' else 'buy', 
                         amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        
        # 3. TP1 (%75 Kapatma)
        ex.create_order(symbol, 'limit', 'sell' if side == 'LONG' else 'buy', 
                         amount * CONFIG['tp1_ratio'], tp1, {'reduceOnly': True})
        
        # 4. TP2 (%25 Kapatma)
        ex.create_order(symbol, 'limit', 'sell' if side == 'LONG' else 'buy', 
                         amount * (1 - CONFIG['tp1_ratio']), tp2, {'reduceOnly': True})

        active_trades[symbol] = True
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası ({symbol}): {str(e)}")

# --- [6. BAKİYE & RADAR KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        balance = ex.fetch_balance({'type': 'swap'})
        free_usdt = balance['USDT']['free']
        bot.reply_to(message, f"💰 **BAKİYE:** {free_usdt:.2f} USDT")
    except: bot.reply_to(message, "❌ Bakiye çekilemedi.")

@bot.message_handler(commands=['radar'])
def get_radar(message):
    tickers = ex.fetch_tickers()
    top_movers = sorted(tickers.items(), key=lambda x: abs(x[1]['percentage']), reverse=True)[:5]
    report = "📡 **RADAR ANALİZ:**\n"
    for sym, data in top_movers:
        if '/USDT:USDT' in sym:
            report += f"🔥 {sym.split(':')[0]}: %{data['percentage']:.2f}\n"
    bot.send_message(MY_CHAT_ID, report)

# --- [7. ANA DÖNGÜ (RADAR SÜREKLİ AKAR)] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 Radar Başlatıldı. Borsayı tarıyorum...")
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
                time.sleep(0.1) # Hız sınırı koruması
            
            time.sleep(300) # 5 dakikada bir tam tarama
        except: time.sleep(30)

if __name__ == "__main__":
    # Telegram ve Radar'ı aynı anda çalıştırır
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
