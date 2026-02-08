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

ex = ccxt.mexc({
    'apiKey': MEXC_API, 'secret': MEXC_SEC,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [AYARLAR VE VOLATİL 30 KOİN] ---
CONFIG = {
    'trade_amount': 20.0,       # 20 USDT Giriş
    'leverage': 10,             # 10x Kaldıraç
    'tp1_close_ratio': 0.75,    # %75 Kâr Al (Sadık Bey Ayarı)
    'symbols': [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
        'AVAX/USDT:USDT', 'DOGE/USDT:USDT', 'LINK/USDT:USDT', 'NEAR/USDT:USDT',
        'APT/USDT:USDT', 'OP/USDT:USDT', 'ARB/USDT:USDT', 'TIA/USDT:USDT',
        'SEI/USDT:USDT', 'FET/USDT:USDT', 'RNDR/USDT:USDT', 'PEPE/USDT:USDT',
        'SUI/USDT:USDT', 'INJ/USDT:USDT', 'WLD/USDT:USDT', 'ORDI/USDT:USDT',
        'BONK/USDT:USDT', 'JUP/USDT:USDT', 'PYTH/USDT:USDT', 'STX/USDT:USDT',
        'BEAM/USDT:USDT', 'IMX/USDT:USDT', 'FIL/USDT:USDT', 'ICP/USDT:USDT',
        'LDO/USDT:USDT', 'PENDLE/USDT:USDT'
    ]
}

# --- [TEKNİK ANALİZ VE GARANTİ GİRİŞ MOTORU] ---
def get_signals(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=10)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        
        # Swing High/Low Belirleme
        swing_high = max(highs[-5:-2])
        swing_low = min(lows[-5:-2])
        current_close = ohlcv[-1][4]
        
        # 1. Trend Dönüş Onayı (MSS)
        is_bullish_mss = current_close > swing_high
        is_bearish_mss = current_close < swing_low
        
        # 2. FVG (Fair Value Gap) Analizi
        fvg_status = "YOK"
        if ohlcv[-3][2] < ohlcv[-1][3]: fvg_status = "BOĞA FVG ✅"
        if ohlcv[-3][3] > ohlcv[-1][2]: fvg_status = "AYI FVG ✅"
        
        return is_bullish_mss, is_bearish_mss, fvg_status, current_close
    except:
        return False, False, "YOK", 0

def market_scanner():
    print(f"📡 {len(CONFIG['symbols'])} Hareketli Koin Üzerinde 'Garanti Av' Başladı...")
    while True:
        for symbol in CONFIG['symbols']:
            is_up, is_down, fvg, price = get_signals(symbol)
            
            # Üçlü Onay Mekanizması
            if (is_up and "BOĞA" in fvg) or (is_down and "AYI" in fvg):
                yon = "📈 YUKARI (LONG)" if is_up else "📉 AŞAĞI (SHORT)"
                msg = (f"🎯 **SADIK BEY, FIRSAT YAKALANDI!**\n\n"
                       f"🪙 **Koin:** {symbol}\n"
                       f"🔄 **Trend Dönüşü (MSS):** ONAYLANDI\n"
                       f"🕳️ **Boşluk Analizi (FVG):** {fvg}\n"
                       f"📊 **Yön:** {yon}\n"
                       f"💰 **Fiyat:** {price}\n"
                       f"🛡️ **Strateji:** 20 USDT | 10x | %75 TP1")
                
                bot.send_message(MY_CHAT_ID, msg)
                time.sleep(10) # Aynı koin için üst üste mesajı engeller
        time.sleep(30) # 30 saniyede bir tüm listeyi tekrar tara

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 Bakiye: {usdt:.2f} USDT\n📡 30 Volatil Koin (Swing+FVG) İzleniyor!")
    except:
        bot.reply_to(message, "❌ Borsa bağlantısı sağlanamadı.")

if __name__ == "__main__":
    threading.Thread(target=market_scanner, daemon=True).start()
    bot.infinity_polling()
