import ccxt
import time
import telebot
import os
import threading
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'defaultMarketMode': 'one_way'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR - BİRAZ DAHA ESNEK] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.035, # %3.5 Kar
    'sl_target': 0.018, # %1.8 Stop
    'max_active_trades': 2,
    'vol_threshold': 1.4, # 1.8'den 1.4'e düşürdüm (Daha fazla işlem yakalar)
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text)
    except: pass

# --- [3. ANALİZ MOTORU] ---
def is_perfect_setup(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]

        # SMC: Likidite ve MSS
        liq_taken = l[-1] < min(l[-20:-5])
        mss_confirmed = c[-1] > max(c[-5:-1])
        
        # Volatilite Patlaması
        avg_vol = sum(v[-10:-1]) / 9
        vol_ok = v[-1] > (avg_vol * CONFIG['vol_threshold'])

        if liq_taken and mss_confirmed and vol_ok:
            return True
        return False
    except Exception as e:
        print(f"Analiz Hatası ({symbol}): {e}")
        return False

# --- [4. GİZLİ TAKİP VE EMİR GÖNDERME] ---
def monitor(symbol, entry, amount):
    tp, sl = entry * (1 + CONFIG['tp_target']), entry * (1 - CONFIG['sl_target'])
    while symbol in active_trades:
        try:
            curr = ex.fetch_ticker(symbol)['last']
            if curr >= tp or curr <= sl:
                # EMİR GÖNDERME GARANTİSİ
                order = ex.create_market_order(symbol, 'sell', amount)
                msg = "💰 KAR ALINDI!" if curr >= tp else "🛑 STOP OLDU."
                send_msg(f"{msg}\nKoin: {symbol}\nKar/Zarar Sonrası Bakiye Kontrol Ediliyor...")
                del active_trades[symbol]
                break
            time.sleep(1)
        except Exception as e:
            send_msg(f"⚠️ Kapatma Hatası ({symbol}): {e}")
            break

def main_loop():
    send_msg("🚀 **V14 BAŞLATILDI**\nEmir gönderme sistemi ve 300+ radar kontrol edildi.\nİşlem bekleniyor...")
    while True:
        try:
            tickers = ex.fetch_tickers()
            all_symbols = [s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']]
            sorted_symbols = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]
            
            for s in sorted_symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    if is_perfect_setup(s):
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        
                        # EMİR GÖNDERME VE TEYİT
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            ex.create_market_order(s, 'buy', amt)
                            active_trades[s] = True
                            send_msg(f"🔥 **İŞLEM AÇILDI!**\nKoin: {s}\nFiyat: {p}\nBorsaya emir başarıyla iletildi.")
                            threading.Thread(target=monitor, args=(s, p, amt), daemon=True).start()
                        except Exception as e:
                            send_msg(f"⚠️ **EMİR HATASI:** {s} için işlem açılamadı!\nHata: {e}")
                
                time.sleep(0.05)
            time.sleep(5)
        except Exception as e:
            print(f"Ana Döngü Hatası: {e}")
            time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
