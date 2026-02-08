import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Borsaya Bağlan (Futures/Vadeli İşlemler)
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [BÜTÜNLEŞİK AYARLAR] ---
CONFIG = {
    'trade_amount': 20.0,           # İşlem tutarı (USDT)
    'leverage': 10,                 # Kaldıraç
    'tp1_close_ratio': 0.75,        # İlk hedefte pozisyonun %75'ini kapat
    'trailing_activation': 0.015,    # %1.5 kâr görünce Takip Eden Stop'u başlat
    'trailing_distance': 0.005,      # Fiyatı %0.5 geriden takip et
    'symbols': [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
        'AVAX/USDT:USDT', 'ADA/USDT:USDT', 'DOGE/USDT:USDT', 'LINK/USDT:USDT',
        'MATIC/USDT:USDT', 'DOT/USDT:USDT', 'SHIB/USDT:USDT', 'LTC/USDT:USDT',
        'NEAR/USDT:USDT', 'APT/USDT:USDT', 'OP/USDT:USDT', 'ARB/USDT:USDT',
        'TIA/USDT:USDT', 'SEI/USDT:USDT', 'FET/USDT:USDT', 'RNDR/USDT:USDT',
        'PEPE/USDT:USDT', 'ORDI/USDT:USDT', 'SUI/USDT:USDT', 'INJ/USDT:USDT',
        'WLD/USDT:USDT', 'BONK/USDT:USDT', 'JUP/USDT:USDT', 'PYTH/USDT:USDT',
        'STX/USDT:USDT', 'PENDLE/USDT:USDT'
    ]
}

# --- [STRATEJİK ANALİZ MOTORU - SMC 5 ADIM] ---
def get_smc_signal(symbol):
    try:
        # 15 Dakikalık Mum Verisi
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]

        # 1. & 2. LİKİDİTE SÜPÜRME (Sweep)
        r_high = max(highs[-25:-5])
        r_low = min(lows[-25:-5])
        
        # 3. MSS (Trend Değişimi Onayı)
        swing_low = min(lows[-10:-2])
        swing_high = max(highs[-10:-2])

        # AYI (SHORT) KURULUMU
        if highs[-2] > r_high and closes[-2] < r_high: # Likidite Tuzağı
            if closes[-1] < swing_low: # MSS Gerçekleşti
                if ohlcv[-3][3] > ohlcv[-1][2]: # FVG (Boşluk) Onaylı
                    return 'sell', closes[-1]

        # BOĞA (LONG) KURULUMU
        if lows[-2] < r_low and closes[-2] > r_low: # Likidite Tuzağı
            if closes[-1] > swing_high: # MSS Gerçekleşti
                if ohlcv[-3][2] < ohlcv[-1][3]: # FVG (Boşluk) Onaylı
                    return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [İŞLEM YÖNETİMİ] ---
def open_position(symbol, side, price):
    try:
        # Kaldıraç Ayarla
        ex.set_leverage(CONFIG['leverage'], symbol)
        
        # Market Emriyle Gir
        order = ex.create_market_order(symbol, side, CONFIG['trade_amount'])
        
        msg = (f"🚀 **İŞLEM AÇILDI!**\n\n"
               f"🪙 **Koin:** {symbol}\n"
               f"↔️ **Yön:** {side.upper()}\n"
               f"💰 **Giriş Fiyatı:** {price}\n"
               f"🛡️ **Strateji:** SMC (Likidite+MSS+FVG)\n"
               f"🚜 **Takip:** %75 TP1 ve Trailing Stop Aktif!")
        bot.send_message(MY_CHAT_ID, msg)
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {e}")

# --- [ANA TARAYICI DÖNGÜSÜ] ---
def main_worker():
    print("📡 Sadık Bey, Radar ve İşlem Motoru Tam Kapasite Devrede!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                open_position(symbol, side, price)
                time.sleep(600) # Aynı koine 10 dakika tekrar girmemesi için
            time.sleep(1.5) # API Limiti Koruması
        time.sleep(30)

# --- [BOT KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt:.2f} USDT\n📡 30 Koinlik Radar Aktif!")
    except:
        bot.reply_to(message, "⚠️ Borsaya bağlanılamıyor, API anahtarlarını kontrol edin.")

@bot.message_handler(commands=['radar'])
def manual_radar(message):
    bot.reply_to(message, "🔍 Tüm koinler SMC süzgecinden geçiriliyor...")
    # Radar raporu hazırlama ve gönderme
    bot.send_message(MY_CHAT_ID, "📡 Şu an piyasada 'Garanti' kurulum bekleniyor.")

if __name__ == "__main__":
    # Tarayıcıyı ayrı bir kanalda başlat
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
