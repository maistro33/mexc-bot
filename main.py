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

# --- [AYARLAR] ---
CONFIG = {
    'trade_amount': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
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

# --- [SMC ANALİZ MOTORU] ---
def get_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]

        # Görüntü 2 - Adım 1: Likidite Seviyesi
        r_high = max(highs[-20:-5])
        r_low = min(lows[-20:-5])

        # Görüntü 2 - Adım 2 & 3: Sweep ve MSS
        # SHORT İÇİN
        if highs[-2] > r_high and closes[-2] < r_high: # Sweep
            if closes[-1] < min(lows[-10:-2]): # MSS
                if ohlcv[-3][3] > ohlcv[-1][2]: # FVG
                    return 'sell', closes[-1]

        # LONG İÇİN
        if lows[-2] < r_low and closes[-2] > r_low: # Sweep
            if closes[-1] > max(highs[-10:-2]): # MSS
                if ohlcv[-3][2] < ohlcv[-1][3]: # FVG
                    return 'buy', closes[-1]

        return None, None
    except:
        return None, None

# --- [ANA DÖNGÜ] ---
def scanner():
    print("📡 Sadık Bey, 30 koinlik SMC radarı başlatıldı!")
    while True:
        for symbol in CONFIG['symbols']:
            side, price = get_smc_signal(symbol)
            if side:
                try:
                    ex.set_leverage(CONFIG['leverage'], symbol)
                    order = ex.create_market_order(symbol, side, CONFIG['trade_amount'])
                    msg = (f"🎯 **İŞLEM AÇILDI!**\n🪙 {symbol}\n↕️ Yön: {side.upper()}\n💰 Giriş: {price}\n🛡️ SMC Stratejisi Onaylı!")
                    bot.send_message(MY_CHAT_ID, msg)
                    time.sleep(10)
                except Exception as e:
                    print(f"Hata: {e}")
            time.sleep(1.5)
        time.sleep(30)

@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        bot.reply_to(message, f"💰 Bakiye: {balance['total']['USDT']:.2f} USDT\n📡 30 Koin İzleniyor...")
    except:
        bot.reply_to(message, "❌ Borsa bağlantısı yok!")

if __name__ == "__main__":
    threading.Thread(target=scanner, daemon=True).start()
    bot.infinity_polling()
