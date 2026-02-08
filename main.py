import ccxt
import telebot
import time
import os
import threading
from datetime import datetime

# --- [BAĞLANTILAR] ---
# API ve Token bilgilerinizi buraya girebilir veya ortam değişkeni olarak tanımlayabilirsiniz.
MEXC_API = os.getenv('MEXC_API', 'API_KEY_BURAYA')
MEXC_SEC = os.getenv('MEXC_SEC', 'SECRET_KEY_BURAYA')
TELE_TOKEN = os.getenv('TELE_TOKEN', 'TELEGRAM_TOKEN_BURAYA')
MY_CHAT_ID = os.getenv('MY_CHAT_ID', 'CHAT_ID_BURAYA')

# Borsaya Bağlan (Futures/Vadeli İşlemler Modu)
ex = ccxt.mexc({
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [SADIK BEY ÖZEL KONFİGÜRASYON] ---
CONFIG = {
    'trade_amount_usdt': 20.0,       # İşlem başına risk (USDT)
    'leverage': 10,                 # Kaldıraç oranı
    'tp1_close_ratio': 0.75,        # TP1'de pozisyonun %75'ini kapat (Önemli!)
    'tp1_target_pct': 0.015,        # %1.5 karda TP1 tetiklensin
    'min_volume_mult': 1.5,         # Anti-Manipülasyon: Hacim ortalamanın 1.5 katı olmalı
    'symbols': [
        'FARTCOIN/USDT:USDT', 'PNUT/USDT:USDT', 'MOODENG/USDT:USDT', 'GOAT/USDT:USDT',
        'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'POPCAT/USDT:USDT', 'BONK/USDT:USDT',
        'SOL/USDT:USDT', 'SUI/USDT:USDT', 'AVAX/USDT:USDT', 'FET/USDT:USDT'
    ]
}

# --- [SMC ANALİZ VE ANTİ-MANİPÜLASYON MOTORU] ---
def get_smc_signal(symbol):
    try:
        # 15 Dakikalık Mum Verisi (SMC için ideal zaman dilimi)
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]
        volumes = [x[5] for x in ohlcv]

        # 1. ZAMAN FİLTRESİ: Mum açılış ve kapanış saniyelerinde temkinli duruş
        now_sec = datetime.now().second
        if now_sec > 55 or now_sec < 5:
            return None, None

        # 2. HACİM ONAYLI MSS: Manipülatif iğneleri eler
        avg_vol = sum(volumes[-6:-1]) / 5
        vol_confirmed = volumes[-1] > (avg_vol * CONFIG['min_volume_mult'])

        # 3. LİKİDİTE SÜPÜRME (Sweep) & GÖVDE KAPANIŞI
        r_high = max(highs[-25:-5])
        r_low = min(lows[-25:-5])
        
        # AYI (SHORT) KURULUMU
        if highs[-2] > r_high and closes[-2] < r_high:
            # MSS Onayı ve Hacim Kalkanı
            if closes[-1] < min(lows[-10:-2]) and vol_confirmed:
                return 'sell', closes[-1]

        # BOĞA (LONG) KURULUMU
        if lows[-2] < r_low and closes[-2] > r_low:
            # MSS Onayı ve Hacim Kalkanı
            if closes[-1] > max(highs[-10:-2]) and vol_confirmed:
                return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [GELİŞMİŞ İŞLEM YÖNETİMİ] ---
def execute_trade(symbol, side, entry_price):
    try:
        # MEXC HATA FİLTRESİ: Kaldıraç, İzole Marjin ve Yön Belirleme
        # openType: 1 (Isolated), positionType: 1 (Long) / 2 (Short)
        pos_type_code = 1 if side == 'buy' else 2
        ex.set_leverage(CONFIG['leverage'], symbol, {
            'openType': 1, 
            'positionType': pos_type_code
        })
        
        # Miktar Hesaplama
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / entry_price
        
        # 1. MARKET EMRİ İLE GİRİŞ
        order = ex.create_market_order(symbol, side, amount)
        
        # 2. KADEMELİ KAR AL (TP1 - %75 KAPATMA)
        tp_side = 'sell' if side == 'buy' else 'buy'
        tp1_price = entry_price * (1 + CONFIG['tp1_target_pct']) if side == 'buy' else entry_price * (1 - CONFIG['tp1_target_pct'])
        tp1_amount = amount * CONFIG['tp1_close_ratio']
        
        # Limit Kar Al Emrini Borsaya Gönder
        ex.create_order(symbol, 'limit', tp_side, tp1_amount, tp1_price)

        # Telegram Bilgilendirme
        msg = (f"🎯 **SADIK BEY, İŞLEM AÇILDI!**\n\n"
               f"🪙 **Koin:** {symbol}\n"
               f"↕️ **Yön:** {side.upper()}\n"
               f"💰 **Giriş:** {entry_price}\n"
               f"📈 **TP1 Hedefi:** {tp1_price:.4f}\n"
               f"🚜 **Durum:** %75 Pozisyon Kapanış Emri Verildi.")
        bot.send_message(MY_CHAT_ID, msg)
        
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg:
            bot.send_message(MY_CHAT_ID, "⚠️ **YETKİ HATASI:** MEXC API 'Trade' yetkisi hala aktif değil veya IP engelli.")
        else:
            bot.send_message(MY_CHAT_ID, f"❌ **İşlem Hatası:** {error_msg}")

# --- [ANA DÖNGÜ VE BOT KOMUTLARI] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, SMC Botu Tüm Kalkanlarla Yayında!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                execute_trade(symbol, side, price)
                time.sleep(900) # Aynı koinde 15 dk yeni işlem açma
            time.sleep(1.5) # API limit koruması
        time.sleep(10)

@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Güncel Kasa:** {usdt:.2f} USDT")
    except:
        bot.reply_to(message, "⚠️ Borsa bağlantı hatası.")

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
