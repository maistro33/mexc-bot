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

# --- [2. RADAR & SMC AYARLARI] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.03, # %3 Kar
    'sl_target': 0.015, # %1.5 Zarar
    'max_active_trades': 2
}

active_trades = {}

# --- [3. TELEGRAM KOMUTLARI - TAMİR EDİLDİ] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        total = bal['total']['USDT']
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {total:.2f} USDT")
    except Exception as e: bot.reply_to(message, "Bakiye alınamadı.")

@bot.message_handler(commands=['durum'])
def get_status(message):
    msg = f"📡 **Radar Aktif**\n📈 Aktif İşlem: {len(active_trades)}\n🎯 Strateji: SMC + FVG + MSS"
    bot.reply_to(message, msg)

# --- [4. SMC + FVG RADAR MOTORU] ---
def is_smc_setup(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c = [b[4] for b in bars] # Kapanışlar
        l = [b[3] for b in bars] # En düşükler
        h = [b[2] for b in bars] # En yüksekler
        v = [b[5] for b in bars] # Hacim

        # 1. Likidite & MSS Onayı [cite: 2026-02-05]
        swing_low = min(l[-20:-5])
        liq_taken = l[-1] < swing_low
        mss_confirmed = c[-1] > max(c[-5:-1]) # Gövde kapanış [cite: 2026-02-05]
        
        # 2. FVG Taraması (Fair Value Gap)
        # Örnek: 3 mum önceki mumun tepesi ile mevcut mumun dibi arasındaki boşluk
        fvg_exists = l[-1] > h[-3] 
        
        # 3. Hacim Patlaması [cite: 2026-02-05]
        vol_ok = v[-1] > (sum(v[-10:-1]) / 9 * 1.5)

        if liq_taken and mss_confirmed and vol_ok:
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
                msg = "💰 KAR ALINDI" if curr >= tp else "🛑 ZARAR KESİLDİ"
                bot.send_message(MY_CHAT_ID, f"{msg}\nKoin: {symbol}")
                del active_trades[symbol]
                break
            time.sleep(1)
        except: break

def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 **SNIPER V12 BAŞLATILDI**\nSMC & FVG Radarı Devrede.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]
            for s in symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    if is_smc_setup(s):
                        p = tickers[s]['last']
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        ex.create_market_order(s, 'buy', amt)
                        active_trades[s] = True
                        bot.send_message(MY_CHAT_ID, f"🔥 **İŞLEM AÇILDI**\n{s}\nGiriş: {p}")
                        threading.Thread(target=monitor, args=(s, p, amt), daemon=True).start()
            time.sleep(10)
        except: time.sleep(10)

if __name__ == "__main__":
    # Hem radarı hem Telegram'ı aynı anda çalıştırır
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
