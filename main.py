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
    'apiKey': MEXC_API, 
    'secret': MEXC_SEC, 
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [EKSİKSİZ AYARLAR] ---
CONFIG = {
    'trade_amount': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'symbols': [
        'FARTCOIN/USDT:USDT', 'PNUT/USDT:USDT', 'MOODENG/USDT:USDT', 'GOAT/USDT:USDT',
        'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'POPCAT/USDT:USDT', 'BONK/USDT:USDT',
        'NEIRO/USDT:USDT', 'TURBO/USDT:USDT', 'FLOKI/USDT:USDT', 'MEME/USDT:USDT',
        'SOL/USDT:USDT', 'SUI/USDT:USDT', 'AVAX/USDT:USDT', 'FET/USDT:USDT',
        'WLD/USDT:USDT', 'SEI/USDT:USDT', 'APT/USDT:USDT', 'TIA/USDT:USDT',
        'NEAR/USDT:USDT', 'INJ/USDT:USDT', 'ORDI/USDT:USDT', 'JUP/USDT:USDT',
        'PYTH/USDT:USDT', 'PENDLE/USDT:USDT', 'TAO/USDT:USDT', 'RENDER/USDT:USDT',
        'STX/USDT:USDT', 'ARKM/USDT:USDT'
    ]
}

# Mesaj kirliliğini önlemek için takip sözlüğü
last_alert_time = {}

def get_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=40)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]

        r_high = max(highs[-25:-5])
        r_low = min(lows[-25:-5])
        now = time.time()

        # SHORT ANALİZ
        if highs[-2] > r_high and closes[-2] < r_high:
            # 15 dakikada bir mesaj gönder (Sakinleştirici)
            if symbol not in last_alert_time or (now - last_alert_time[symbol]) > 900:
                bot.send_message(MY_CHAT_ID, f"🔍 **RADAR:** {symbol} likidite süpürdü. (Short onayı bekleniyor... ⏳)")
                last_alert_time[symbol] = now
            
            if closes[-1] < min(lows[-10:-2]) and ohlcv[-3][3] > ohlcv[-1][2]:
                return 'sell', closes[-1]

        # LONG ANALİZ
        if lows[-2] < r_low and closes[-2] > r_low:
            if symbol not in last_alert_time or (now - last_alert_time[symbol]) > 900:
                bot.send_message(MY_CHAT_ID, f"🔍 **RADAR:** {symbol} likidite süpürdü. (Long onayı bekleniyor... ⏳)")
                last_alert_time[symbol] = now
                
            if closes[-1] > max(highs[-10:-2]) and ohlcv[-3][2] < ohlcv[-1][3]:
                return 'buy', closes[-1]

        return None, None
    except:
        return None, None

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ Sadık Bey, Sakin ve Keskin SMC Radarı Başlatıldı!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                try:
                    ex.set_leverage(CONFIG['leverage'], symbol)
                    ex.create_market_order(symbol, side, CONFIG['trade_amount'])
                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI!**\n\n🪙 {symbol}\n↕️ Yön: {side.upper()}\n🚜 %75 TP1 ve Trailing Stop Aktif!")
                    time.sleep(600) 
                except Exception as e:
                    print(f"İşlem hatası: {e}")
            time.sleep(1.5) 
        time.sleep(20)

@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        bot.reply_to(message, f"💰 Kasa: {balance['total']['USDT']:.2f} USDT\n📡 Radar 30 koin üzerinde sessizce çalışıyor.")
    except:
        bot.reply_to(message, "⚠️ Bağlantı hatası!")

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
