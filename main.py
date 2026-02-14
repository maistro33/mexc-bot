import ccxt
import time
import telebot
import os
import threading

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 15.0, # 42 USDT bakiye için korumalı giriş [cite: 2026-02-12]
    'leverage': 10,
    'tp_target': 0.035, # %3.5 Kar [cite: 2026-02-12]
    'sl_target': 0.018, # %1.8 Zarar [cite: 2026-02-12]
    'max_active_trades': 2,
    'vol_threshold': 1.4, # Hacim patlaması onayı [cite: 2026-02-05]
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. ANALİZ MOTORU - SMC + FVG] ---
def is_perfect_setup(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]
        # SMC & FVG Onayları
        liq_taken = l[-1] < min(l[-20:-5])
        mss_confirmed = c[-1] > max(c[-5:-1]) # Gövde kapanış onayı [cite: 2026-02-05]
        vol_ok = v[-1] > (sum(v[-10:-1]) / 9 * CONFIG['vol_threshold'])
        return liq_taken and mss_confirmed and vol_ok
    except: return False

# --- [4. HEDGE MODE TAKİP VE KAPATMA] ---
def monitor(symbol, entry, amount):
    tp, sl = entry * (1 + CONFIG['tp_target']), entry * (1 - CONFIG['sl_target'])
    while symbol in active_trades:
        try:
            time.sleep(1)
            curr = float(ex.fetch_ticker(symbol)['last'])
            if curr >= tp or curr <= sl:
                # HEDGE MODE KAPATMA: posSide='long' ve side='sell' (Long'u kapatır)
                ex.create_order(symbol, 'market', 'sell', amount, params={'posSide': 'long'})
                msg = "💰 **KAR ALINDI!**" if curr >= tp else "🛑 **STOP OLDU.**"
                send_msg(f"{msg}\nKoin: {symbol}\nKâr Hedefi Gerçekleşti.") [cite: 2026-02-12]
                del active_trades[symbol]
                break
        except: break

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **V21 AKTİF - HEDGE MOD UYUMU**\nBorsa ayarları Hedge olsa bile bot çalışacak.")
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
                            # HEDGE MODE GİRİŞ: side='buy' ve posSide='long'
                            ex.create_order(
                                symbol=s,
                                type='market',
                                side='buy',
                                amount=amt,
                                params={'posSide': 'long', 'tdMode': 'isolated'}
                            )
                            active_trades[s] = True
                            send_msg(f"🔥 **İŞLEM AÇILDI!**\nKoin: {s}\nGiriş: {p}") [cite: 2026-02-12]
                            threading.Thread(target=monitor, args=(s, p, amt), daemon=True).start()
                        except Exception as e:
                            print(f"Borsa Emri Reddedildi: {e}")
                time.sleep(0.05)
            time.sleep(5)
        except: time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
