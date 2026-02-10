import ccxt
import telebot
import time
import os
import math

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

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        step = market['precision']['amount']
        return round(math.floor(amount / step) * step, 4)
    except: return round(amount, 3)

# --- [2. ANA STRATEJİ: TEK YÖNLÜ UYUMLU] ---
def run_bypass_bot(symbol='BTC/USDT:USDT'):
    bot.send_message(MY_CHAT_ID, "🛡️ **BYPASS SİSTEMİ DEVREDE**\nBorsanın inatçı hata kodu (40774) aşılıyor...")
    
    try:
        ex.load_markets()
        ex.set_leverage(10, symbol)
        
        ticker = ex.fetch_ticker(symbol)
        last_price = ticker['last']
        
        # 20 USDT Giriş Hesaplaması
        amount = round_amount(symbol, (20.0 * 10) / last_price)
        
        # Seviyeler (%1 mesafe)
        stop_price = round(last_price * 0.99, 1) 
        tp1_price = round(last_price * 1.01, 1)
        
        # --- 1. ADIM: GİRİŞ ---
        # Hata veren 'posSide' parametresini tamamen kaldırarak gönderiyoruz
        ex.create_market_buy_order(symbol, amount)
        bot.send_message(MY_CHAT_ID, f"✅ Giriş Başarılı: {last_price}\nMiktar: {amount} BTC")
        time.sleep(2)

        # --- 2. ADIM: STOP LOSS & TP ---
        # Tetikleyici fiyatları borsanın beklediği formata göre ayarlıyoruz
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': 'BTCUSDT_UMCBL',
            'marginCoin': 'USDT',
            'size': str(amount),
            'triggerPrice': str(stop_price),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'reduceOnly': 'true' # Tek yönlü modda Hedge yerine bu kullanılır
        })
        bot.send_message(MY_CHAT_ID, f"🛑 Zarar Kes Dizildi: {stop_price}")

        tp_qty = round_amount(symbol, amount * 0.75)
        ex.privatePostMixOrderPlacePlanOrder({
            'symbol': 'BTCUSDT_UMCBL',
            'marginCoin': 'USDT',
            'size': str(tp_qty),
            'triggerPrice': str(tp1_price),
            'triggerType': 'market_price',
            'side': 'sell',
            'orderType': 'market',
            'reduceOnly': 'true'
        })
        bot.send_message(MY_CHAT_ID, f"💰 %75 Kâr Al Dizildi: {tp1_price}")

        bot.send_message(MY_CHAT_ID, "🏁 **TÜM ENGELLER AŞILDI, BOT AKTİF!**")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ SON DURUM ANALİZİ: {str(e)}")

if __name__ == "__main__":
    run_bypass_bot()
