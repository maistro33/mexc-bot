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

# --- [GÜNCEL 15M AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,      # %75 Kar Al (Sadık Bey Ayarı)
    'tp1_target': 0.018,    # 15M için ideal %1.8 kar hedefi
    'max_coins': 15,        
    'timeframe': '15m'      # Sizin istediğiniz 15 dakikalık periyot
}

def check_15m_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        if len(bars) < 40: return None
        
        # 1. 15M FVG Kontrolü (Daha sağlam boşluk)
        fvg_found = bars[-3][2] < bars[-1][3]
        
        # 2. 15M MSS (Gövde Kapanışlı Yapı Kırılımı)
        last_close = bars[-1][4]
        # Son 15 mumun en yükseğini kırıyor mu?
        prev_high = max([b[2] for b in bars[-15:-2]])
        mss_confirmed = last_close > prev_high
        
        # 3. Hacim Onayı (Manipülasyon Kalkanı)
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        vol_ok = vols[-1] > (avg_vol * 1.2) # Ortalama hacmin %20 üzerinde

        if fvg_found and mss_confirmed and vol_ok:
            return 'buy'
        return None
    except:
        return None

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ Sadık Bey, 15 Dakikalık 'Garanti Scalp' Modu Aktif!\nDaha sağlam ve kaliteli sinyaller taranıyor...")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            # En hacimli ve hareketli 15 koin
            active_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'],
                reverse=True
            )[:CONFIG['max_coins']]

            for sym in active_symbols:
                signal = check_15m_signal(sym)
                if signal:
                    execute_trade(sym, signal)
                time.sleep(2) # Borsa limiti için küçük mola
            
            # 15 dakikalık mum kapanışlarını beklemek için 5 dakika mola
            time.sleep(300)
            
        except Exception as e:
            time.sleep(60)

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🎯 **15M GÜÇLÜ SİNYAL!**\n🪙 {symbol}\n✅ FVG + MSS + HACİM Onaylı\nİşlem deneniyor...")
        
        ex.create_market_order(symbol, side, amount)
        
        # TP1 Ayarı (%75 Kapama)
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * CONFIG['tp1_ratio'], tp_price, {'reduceOnly': True})
        
    except Exception as e:
        if "insufficient balance" in str(e).lower() or "amount exceeds the balance" in str(e).lower():
            bot.send_message(MY_CHAT_ID, f"🔔 **Bakiye Bekleniyor (15m):** {symbol} için kaliteli sinyal geldi ama kasa boş.")
        else:
            print(f"İşlem Hatası: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
