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

# --- [YENİ NESİL HAREKETLİ LİSTE VE AYARLAR] ---
CONFIG = {
    'trade_amount': 20.0,           # İşlem tutarı (USDT)
    'leverage': 10,                 # Kaldıraç
    'tp1_close_ratio': 0.75,        # TP1'de pozisyonun %75'ini kapat (Sadık Bey Ayarı)
    'symbols': [
        # --- Hızlı ve Kar Bırakan Meme/Yeni Nesil ---
        'FARTCOIN/USDT:USDT', 'PNUT/USDT:USDT', 'MOODENG/USDT:USDT', 'GOAT/USDT:USDT',
        'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'POPCAT/USDT:USDT', 'BONK/USDT:USDT',
        'NEIRO/USDT:USDT', 'TURBO/USDT:USDT', 'FLOKI/USDT:USDT', 'MEME/USDT:USDT',
        # --- Volatilitesi Yüksek Hareketli Koinler ---
        'SOL/USDT:USDT', 'SUI/USDT:USDT', 'AVAX/USDT:USDT', 'FET/USDT:USDT',
        'WLD/USDT:USDT', 'SEI/USDT:USDT', 'APT/USDT:USDT', 'TIA/USDT:USDT',
        'NEAR/USDT:USDT', 'INJ/USDT:USDT', 'ORDI/USDT:USDT', 'JUP/USDT:USDT',
        'PYTH/USDT:USDT', 'PENDLE/USDT:USDT', 'TAO/USDT:USDT', 'RENDER/USDT:USDT',
        'STX/USDT:USDT', 'ARKM/USDT:USDT'
    ]
}

# --- [SMC ANALİZ MOTORU - GÖRÜNTÜ 2 ŞEMASI] ---
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
        
        # AYI (SHORT) KURULUMU
        if highs[-2] > r_high and closes[-2] < r_high:
            bot.send_message(MY_CHAT_ID, f"🔍 **RADAR:** {symbol} likiditeyi süpürdü! (Short onayı bekleniyor... ⏳)")
            # 3. MSS (Karakter Değişimi)
            if closes[-1] < min(lows[-10:-2]):
                # 4. FVG (Boşluk) Onayı
                if ohlcv[-3][3] > ohlcv[-1][2]:
                    return 'sell', closes[-1]

        # BOĞA (LONG) KURULUMU
        if lows[-2] < r_low and closes[-2] > r_low:
            bot.send_message(MY_CHAT_ID, f"🔍 **RADAR:** {symbol} likiditeyi süpürdü! (Long onayı bekleniyor... ⏳)")
            # 3. MSS (Karakter Değişimi)
            if closes[-1] > max(highs[-10:-2]):
                # 4. FVG (Boşluk) Onayı
                if ohlcv[-3][2] < ohlcv[-1][3]:
                    return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [ANA ÇALIŞMA DÖNGÜSÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, Hızlı Koin Radarı ve SMC Avcısı Devrede!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                try:
                    # Kaldıraç Ayarla ve İşlem Aç
                    ex.set_leverage(CONFIG['leverage'], symbol)
                    ex.create_market_order(symbol, side, CONFIG['trade_amount'])
                    
                    msg = (f"🎯 **SADIK BEY, İŞLEM AÇILDI!**\n\n"
                           f"🪙 **Koin:** {symbol}\n"
                           f"↕️ **Yön:** {side.upper()}\n"
                           f"💰 **Giriş:** {price}\n"
                           f"🚜 **Durum:** %75 TP1 ve Trailing Stop Aktif!")
                    bot.send_message(MY_CHAT_ID, msg)
                    time.sleep(600) # Aynı koin için 10 dk bekle
                except Exception as e:
                    print(f"Hata: {e}")
            time.sleep(1.2) # Hızlı koinler için tarama hızı artırıldı
        time.sleep(20)

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Kasa:** {usdt:.2f} USDT\n📡 {len(CONFIG['symbols'])} Hareketli Koin İzleniyor.")
    except:
        bot.reply_to(message, "⚠️ Borsa bağlantısı kurulamadı.")

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
