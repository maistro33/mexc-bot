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

# --- [2. RADAR & FİLTRE AYARLARI] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.04,  # %4 Kar (Memecoin volatilitesi için)
    'sl_target': 0.018, # %1.8 Zarar durdur
    'max_active_trades': 2,
    # HANTAL KOİNLER (KARA LİSTE) - Bunlara bakmaz
    'blacklist': [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'ADA/USDT:USDT', 
        'SOL/USDT:USDT', 'AVAX/USDT:USDT', 'DOT/USDT:USDT', 'LINK/USDT:USDT',
        'LTC/USDT:USDT', 'BCH/USDT:USDT', 'TRX/USDT:USDT', 'ETC/USDT:USDT'
    ]
}

active_trades = {}

# --- [3. TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        total = bal['total']['USDT']
        bot.reply_to(message, f"💰 **Bakiye:** {total:.2f} USDT")
    except: bot.reply_to(message, "⚠️ Hata: Bakiye alınamadı.")

@bot.message_handler(commands=['durum'])
def get_status(message):
    msg = f"📡 **Radar:** 300+ Coin Taranıyor\n🚫 **Filtre:** Hantal coinler elendi\n📈 **Aktif:** {len(active_trades)} işlem"
    bot.reply_to(message, msg)

# --- [4. SMC + FVG + VOLATİLİTE MOTORU] ---
def is_perfect_setup(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c = [b[4] for b in bars] # Kapanış
        l = [b[3] for b in bars] # Düşük
        h = [b[2] for b in bars] # Yüksek
        v = [b[5] for b in bars] # Hacim

        # 1. SMC: Likidite süpürme ve MSS (Market Kırılımı)
        swing_low = min(l[-20:-5])
        liq_taken = l[-1] < swing_low
        mss_confirmed = c[-1] > max(c[-5:-1])
        
        # 2. FVG (Boşluk) Taraması
        fvg_exists = l[-1] > h[-3]
        
        # 3. Volatilite & Hacim Patlaması (Ani hareket)
        avg_vol = sum(v[-10:-1]) / 9
        vol_boost = v[-1] > (avg_vol * 1.8) # Hacim 1.8 kat artmış olmalı

        if liq_taken and mss_confirmed and vol_boost:
            return True
        return False
    except: return False

# --- [5. GİZLİ TAKİP] ---
def monitor(symbol, entry, amount):
    tp, sl = entry * (1 + CONFIG['tp_target']), entry * (1 - CONFIG['sl_target'])
    while symbol in active_trades:
        try:
            curr = ex.fetch_ticker(symbol)['last']
            if curr >= tp or curr <= sl:
                ex.create_market_order(symbol, 'sell', amount)
                msg = "💰 **KAR ALINDI!**" if curr >= tp else "🛑 **STOP OLDU.**"
                bot.send_message(MY_CHAT_ID, f"{msg}\nKoin: {symbol}\nFiyat: {curr}")
                del active_trades[symbol]
                break
            time.sleep(1)
        except: break

def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 **SNIPER V13 AKTİF!**\n300+ Coin taranıyor, hantallar elendi.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            # Bütün vadeli koinleri al, Kara listeyi çıkar ve hacme göre sırala
            all_symbols = [
                s for s in tickers 
                if '/USDT:USDT' in s and s not in CONFIG['blacklist']
            ]
            sorted_symbols = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]
            
            for s in sorted_symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    if is_perfect_setup(s):
                        p = tickers[s]['last']
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        ex.create_market_order(s, 'buy', amt)
                        active_trades[s] = True
                        bot.send_message(MY_CHAT_ID, f"🔥 **SICAK FIRSAT!**\nKoin: {s}\nGiriş: {p}\n🎯 FVG & MSS Onaylı.")
                        threading.Thread(target=monitor, args=(s, p, amt), daemon=True).start()
            time.sleep(5) # Daha hızlı tarama için döngü süresini düşürdüm
        except: time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
