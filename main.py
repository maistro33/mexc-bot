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

# Borsa bağlantısını hata yönetimiyle kur
try:
    ex = ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
    bot = telebot.TeleBot(TELE_TOKEN)
except Exception as e:
    print(f"Bağlantı Hatası: {e}")

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.035, # %3.5 Kar [cite: 2026-02-12]
    'sl_target': 0.018, # %1.8 Zarar [cite: 2026-02-12]
    'max_active_trades': 2,
    'vol_threshold': 1.4,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    """Çökme korumalı mesaj gönderme fonksiyonu."""
    try: 
        bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram Gönderim Hatası: {e}")

# --- [3. ANALİZ VE GİZLİ TAKİP] ---
def is_perfect_setup(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        if not bars: return False
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]
        
        # SMC & FVG Onayları
        liq_taken = l[-1] < min(l[-20:-5])
        mss_confirmed = c[-1] > max(c[-5:-1])
        vol_ok = v[-1] > (sum(v[-10:-1]) / 9 * CONFIG['vol_threshold'])
        
        return liq_taken and mss_confirmed and vol_ok
    except: return False

def monitor(symbol, entry, amount):
    tp, sl = entry * (1 + CONFIG['tp_target']), entry * (1 - CONFIG['sl_target'])
    while symbol in active_trades:
        try:
            time.sleep(2)
            ticker = ex.fetch_ticker(symbol)
            curr = float(ticker['last'])
            
            if curr >= tp or curr <= sl:
                ex.create_market_sell_order(symbol, amount)
                msg = "💰 **KAR ALINDI!**" if curr >= tp else "🛑 **STOP OLDU.**"
                send_msg(f"{msg}\nKoin: {symbol}\nBakiye Güncellendi.") [cite: 2026-02-12]
                if symbol in active_trades: del active_trades[symbol]
                break
        except Exception as e:
            print(f"Takip Hatası ({symbol}): {e}")
            break

# --- [4. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **SNIPER V17 AKTİF**\nÇökme koruması devreye girdi. 300+ radar taranıyor.") [cite: 2026-02-12]
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']], 
                            key=lambda x: tickers[x]['quoteVolume'] if tickers[x]['quoteVolume'] else 0, reverse=True)[:300]
            
            for s in symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    if is_perfect_setup(s):
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            ex.create_market_buy_order(s, amt)
                            active_trades[s] = True
                            send_msg(f"🔥 **İŞLEM AÇILDI!**\nKoin: {s}\nGiriş: {p}") [cite: 2026-02-12]
                            threading.Thread(target=monitor, args=(s, p, amt), daemon=True).start()
                        except Exception as e:
                            print(f"Emir Hatası ({s}): {e}")
                time.sleep(0.05)
            time.sleep(10)
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(15)

# --- [5. KOMUTLAR VE BAŞLATMA] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        total = bal['total']['USDT']
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {total:.2f} USDT") [cite: 2026-02-12]
    except: pass

@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, f"📡 **Radar:** 300+ Coin Taranıyor\n📈 **Aktif:** {len(active_trades)} işlem") [cite: 2026-02-12]

if __name__ == "__main__":
    try:
        ex.load_markets()
        threading.Thread(target=main_loop, daemon=True).start()
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Kritik Başlatma Hatası: {e}")
        time.sleep(10)
