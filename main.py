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

# --- [2. PRO SNIPER & TRAILING AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp_target': 0.05,       # %5 Ana Hedef
    'sl_target': 0.018,      # %1.8 Başlangıç Stopu
    'trailing_activation': 0.02, # %2 kâra geçince Trailing aktif olur
    'max_active_trades': 2,
    'vol_threshold': 1.8,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. ANALİZ MOTORU (V36 İLE AYNI - GÜVENLİ)] ---
def get_sniper_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='5m', limit=40)
        o, h, l, c, v = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]
        prev_high, prev_low = max(h[-30:-1]), min(l[-30:-1])
        avg_v = sum(v[-20:-1]) / 19
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])

        if vol_ok and l[-1] < prev_low and c[-1] > prev_low and c[-1] > o[-1]: return 'long'
        if vol_ok and h[-1] > prev_high and c[-1] < prev_high and c[-1] < o[-1]: return 'short'
        return None
    except: return None

# --- [4. GELİŞMİŞ TAKİP MOTORU (TRAILING STOP)] ---
def monitor(symbol, entry, amount, side):
    # Başlangıç stop seviyesi
    current_sl = entry * (1 - CONFIG['sl_target']) if side == 'long' else entry * (1 + CONFIG['sl_target'])
    trailing_active = False
    
    while symbol in active_trades:
        try:
            time.sleep(3)
            ticker = ex.fetch_ticker(symbol)
            curr = float(ticker['last'])
            
            pnl = (curr - entry) / entry if side == 'long' else (entry - curr) / entry

            # 1. Trailing Stop Aktivasyonu & Breakeven
            if not trailing_active and pnl >= CONFIG['trailing_activation']:
                trailing_active = True
                current_sl = entry  # Stopu giriş seviyesine çek (Risk-Free)
                send_msg(f"🛡️ **GÜVENLİ MOD:** {symbol} kârda! Stop giriş seviyesine çekildi (Breakeven).")

            # 2. Dinamik Stop Güncelleme (Fiyat ilerledikçe stopu taşı)
            if trailing_active:
                if side == 'long':
                    new_sl = curr * (1 - 0.015) # Fiyatın %1.5 arkasından takip et
                    if new_sl > current_sl: current_sl = new_sl
                else:
                    new_sl = curr * (1 + 0.015)
                    if new_sl < current_sl: current_sl = new_sl

            # 3. Çıkış Kontrolleri
            hit_tp = pnl >= CONFIG['tp_target']
            hit_sl = (side == 'long' and curr <= current_sl) or (side == 'short' and curr >= current_sl)

            if hit_tp or hit_sl:
                exit_side = 'sell' if side == 'long' else 'buy'
                ex.create_order(symbol, 'market', exit_side, amount, params={'posSide': side})
                
                msg = "💰 **KÂR ALINDI**" if hit_tp else "🛡️ **TAKİP EDEN STOP TETİKLENDİ**"
                send_msg(f"{msg}\nKoin: {symbol}\nÇıkış Fiyatı: {curr}")
                del active_trades[symbol]
                break
        except: break

# --- [5. ANA DÖNGÜ & BAŞLATICI] ---
def main_loop():
    send_msg("🎯 **V37 PRO SNIPER AKTİF**\nTrailing Stop & Breakeven devrede.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']], 
                            key=lambda x: tickers[x]['quoteVolume'] if tickers[x]['quoteVolume'] else 0, reverse=True)[:100]
            for s in symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal = get_sniper_signal(s)
                    if signal:
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            ex.create_order(symbol=s, type='market', side='buy' if signal == 'long' else 'sell', 
                                            amount=amt, params={'posSide': signal})
                            active_trades[s] = True
                            send_msg(f"🎯 **SNIPER GİRİŞİ!**\nKoin: {s}\nYön: {signal.upper()}")
                            threading.Thread(target=monitor, args=(s, p, amt, signal), daemon=True).start()
                        except: pass
                time.sleep(0.1)
            time.sleep(10)
        except: time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
