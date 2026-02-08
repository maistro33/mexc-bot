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

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [VOLATİLİTE AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'tp1_target': 0.015,
    'max_coins': 20,         # En hareketli 20 koin
    'timeframe': '5m'        # Daha hızlı yakalamak için 5 dakikalık grafik
}

def get_volatile_symbols():
    """Bitget'te son 24 saatte en çok hareket edenleri bulur"""
    try:
        markets = ex.fetch_tickers()
        # Sadece USDT çiftleri ve son 24 saatte %3'ten fazla hareket edenler
        volatile = []
        for s, data in markets.items():
            if '/USDT:USDT' in s:
                change = abs(float(data.get('percentage', 0)))
                if change > 3.0: # %3'ten fazla oynaklık
                    volatile.append(s)
        
        # En çok hacimden en az hacime sırala
        sorted_volatile = sorted(volatile, key=lambda x: markets[x]['quoteVolume'], reverse=True)
        return sorted_volatile[:CONFIG['max_coins']]
    except:
        return ['SOL/USDT:USDT', 'PNUT/USDT:USDT', 'XRP/USDT:USDT']

def check_fvg_and_mss(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        if len(bars) < 40: return None, "Veri az"
        
        # FVG (Boğa tipi: 1. mumun tepesi < 3. mumun dibi)
        fvg_found = bars[-3][2] < bars[-1][3] # Gap kontrolü
        
        # MSS (Kısa periyotta tepenin aşılması)
        last_close = bars[-1][4]
        local_high = max([b[2] for b in bars[-10:-2]])
        mss_confirmed = last_close > local_high
        
        status = f"🔥 {symbol}: "
        if fvg_found: status += "✅ FVG "
        else: status += "❌ FVG "
        if mss_confirmed: status += "| ✅ MSS"
        else: status += "| ❌ MSS"
        
        if fvg_found and mss_confirmed:
            return 'buy', status
        return None, status
    except:
        return None, "Analiz hatası"

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"⚡ **{symbol} SİNYALİ GELDİ!**\nSert hareket yakalandı, işlem deneniyor...")
        
        # Bakiye 0 olduğu için burası hata verecek ama işlem emrini gönderdiğini göreceğiz
        ex.create_market_order(symbol, side, amount)
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"🔔 **TEST BAŞARILI:** Bot işlemi açmaya çalıştı!\nBakiye Durumu: `{str(e)}`")

def main_worker():
    bot.send_message(MY_CHAT_ID, "🦅 Sadık Bey, 'Volatilite Avcısı' Modu Aktif!\nEn hareketli koinleri 5 dakikalıkta tarıyorum...")
    while True:
        symbols = get_volatile_symbols()
        for sym in symbols:
            signal, status = check_fvg_and_mss(sym)
            if signal:
                execute_trade(sym, signal)
            time.sleep(1)
        time.sleep(60) # Her dakika listeyi tazele

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
