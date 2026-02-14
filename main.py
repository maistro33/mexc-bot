import ccxt
import time
import telebot
import os
import threading
import math
from datetime import datetime

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
    'options': {'defaultType': 'swap', 'defaultMarketMode': 'one_way'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AGRESİF SCALP AYARLARI] ---
CONFIG = {
    'entry_usdt': 15.0,          # 42 USDT bakiye için ideal giriş [cite: 2026-02-05]
    'leverage': 10,              # Memecoin oynaklığı için 10x güvenlidir [cite: 2026-02-05]
    'max_active_trades': 2,      # Bakiyeyi bölerek riski dağıtıyoruz [cite: 2026-02-12]
    'volatility_threshold': 1.5, # Hacim patlaması (Ortalamanın 1.5 katı) [cite: 2026-02-05]
    'tp_target': 0.03,           # %3 Kâr hedefi (Hızlı çıkış) [cite: 2026-02-12]
    'sl_target': 0.015,          # %1.5 Zarar durdur (Kasa koruması) [cite: 2026-02-12]
    'timeframe': '1m'            # En hızlı tepki için 1 dakikalık grafik
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        step = int(-math.log10(precision)) if precision < 1 else 0
        return round(amount, step) if step > 0 else int(amount)
    except: return round(amount, 2)

# --- [3. MEMECOIN & VOLATİLİTE RADARI] ---
def is_high_potential(symbol):
    try:
        # Zaman Filtresi: Manipülasyon koruması [cite: 2026-02-05]
        now_sec = datetime.now().second
        if now_sec < 2 or now_sec > 58: return False

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=20)
        v = [b[5] for b in bars] # Hacim verileri
        c = [b[4] for b in bars] # Kapanış verileri

        avg_vol = sum(v[-11:-1]) / 10
        # 1. Hacim Patlaması Onayı [cite: 2026-02-05]
        vol_ok = v[-1] > (avg_vol * CONFIG['volatility_threshold'])
        
        # 2. SMC Kuralı: Likidite sonrası güçlü gövde kapanışı [cite: 2026-02-05]
        is_bullish = c[-1] > max(c[-5:-1]) 
        
        return vol_ok and is_bullish
    except: return False

# --- [4. GİZLİ TAKİP MOTORU] ---
def hidden_monitor(symbol, side, entry, amount):
    """Borsaya emir göndermeden saniyelik takip yapar [cite: 2026-02-12]"""
    tp_price = entry * (1 + CONFIG['tp_target'])
    sl_price = entry * (1 - CONFIG['sl_target'])
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            curr_p = ticker['last']
            
            # Gizli Kar Al: %3 gördüğü an kaçar [cite: 2026-02-12]
            if curr_p >= tp_price:
                ex.create_market_order(symbol, 'sell', amount)
                bot.send_message(MY_CHAT_ID, f"💰 **KAR ALINDI!**\n{symbol}\nKâr: %3\nBakiye Büyüyor!")
                del active_trades[symbol]
                break
                
            # Gizli Stop: %1.5 düştüğü an korur [cite: 2026-02-05]
            if curr_p <= sl_price:
                ex.create_market_order(symbol, 'sell', amount)
                bot.send_message(MY_CHAT_ID, f"🛑 **ZARAR KESİLDİ**\n{symbol}\nKasa Korumaya Alındı.")
                del active_trades[symbol]
                break
                
            time.sleep(1) # Memecoinler için 1 saniyelik takip
        except: break

def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 **SNIPER V11 AKTİF**\n🎯 Hedef: Yeni & Hareketli Memecoinler\n🕵️ Mod: Gizli Hızlı Scalp")
    while True:
        try:
            markets = ex.fetch_tickers()
            # En yüksek hacimli ilk 50 koin (Memecoinler genelde buradadır)
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'] if markets[x]['quoteVolume'] else 0,
                reverse=True
            )[:50]
            
            for sym in sorted_symbols:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                
                if is_high_potential(sym):
                    price = markets[sym]['last']
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / price)
                    
                    # Giriş (Tek Yönlü Mod) [cite: 2026-02-12]
                    ex.create_market_order(sym, 'buy', amount)
                    active_trades[sym] = True
                    
                    bot.send_message(MY_CHAT_ID, f"🔥 **SICAK FIRSAT YAKALANDI**\nKoin: {sym}\nGiriş: {price}\n🚀 Hızlı Kâr Bekleniyor...")
                    threading.Thread(target=hidden_monitor, args=(sym, 'buy', price, amount), daemon=True).start()
                
            time.sleep(10) 
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    main_loop()
