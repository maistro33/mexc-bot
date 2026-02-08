import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Bitget Swap (Vadeli İşlemler) Bağlantısı
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [STRATEJİ AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,  # İşlem miktarı
    'leverage': 10,             # Kaldıraç
    'tp1_ratio': 0.75,          # %75 Kar Al (Sadık Bey Ayarı)
    'tp1_target': 0.015,        # %1.5 karda ilk satış
    'symbols': ['SOL/USDT:USDT', 'PNUT/USDT:USDT', 'FARTCOIN/USDT:USDT']
}

# --- [GÖVDE KAPANIŞ VE HACİM KONTROLÜ] ---
def get_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        # Anti-Manipülasyon: Hacim Onayı (Son mum hacmi ortalamanın üstünde mi?)
        volumes = [b[5] for b in bars]
        avg_vol = sum(volumes[-10:]) / 10
        current_vol = volumes[-1]
        
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-20:-1]])
        
        # 1. Kalkan: Gövde Kapanış Onayı (Sadece iğne değil, mum üstünde kapandı mı?)
        if last_close > prev_high and current_vol > avg_vol:
            return 'buy'
        return None
    except:
        return None

def execute_trade(symbol, side):
    try:
        # 1. Kaldıraç ve İzole Mod Ayarı
        ex.set_leverage(CONFIG['leverage'], symbol)
        
        # 2. Miktar Hesapla
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        # 3. Market Emri ile Giriş
        order = ex.create_market_order(symbol, side, amount)
        bot.send_message(MY_CHAT_ID, f"🚀 **İŞLEM AÇILDI!**\n\n🪙 Koin: {symbol}\n↕️ Yön: {side.upper()}\n💰 Giriş: {price}")
        
        # 4. %75 Kar Al (TP1) Emrini Yerleştir
        tp_side = 'sell' if side == 'buy' else 'buy'
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        
        ex.create_order(symbol, 'limit', tp_side, amount * CONFIG['tp1_ratio'], tp_price, {'reduceOnly': True})
        bot.send_message(MY_CHAT_ID, f"🎯 **TP1 SET EDİLDİ!**\n💰 Hedef: {tp_price}\n📦 Miktar: %75")
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [BOT DÖNGÜSÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 Sadık Bey, Bitget Botu SMC Kalkanlarıyla Aktif!")
    while True:
        for symbol in CONFIG['symbols']:
            signal = get_signal(symbol)
            if signal:
                execute_trade(symbol, signal)
            time.sleep(5)
        time.sleep(60)

@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 **Bitget Güncel Kasa:** {usdt:.2f} USDT")
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {str(e)}")

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
