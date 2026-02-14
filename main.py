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
    'entry_usdt': 15.0, # 42 USDT kasan için ideal giriş [cite: 2026-02-12]
    'leverage': 10,
    'tp_target': 0.035,
    'sl_target': 0.018,
    'max_active_trades': 2,
    'vol_threshold': 1.4,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. ANALİZ VE TAKİP MOTORU] ---
def get_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]
        vol_ok = v[-1] > (sum(v[-10:-1]) / 9 * CONFIG['vol_threshold']) [cite: 2026-02-05]
        
        long_setup = l[-1] < min(l[-20:-5]) and c[-1] > max(c[-5:-1]) # SMC BoS/MSS [cite: 2026-02-05]
        short_setup = h[-1] > max(h[-20:-5]) and c[-1] < min(c[-5:-1])

        if vol_ok and long_setup: return 'long'
        if vol_ok and short_setup: return 'short'
        return None
    except: return None

def monitor(symbol, entry, amount, side):
    while symbol in active_trades:
        try:
            time.sleep(2)
            curr = float(ex.fetch_ticker(symbol)['last'])
            tp = entry * (1 + CONFIG['tp_target']) if side == 'long' else entry * (1 - CONFIG['tp_target'])
            sl = entry * (1 - CONFIG['sl_target']) if side == 'long' else entry * (1 + CONFIG['sl_target'])
            
            if (side == 'long' and (curr >= tp or curr <= sl)) or (side == 'short' and (curr <= tp or curr >= sl)):
                pos_side = 'long' if side == 'long' else 'short'
                exit_side = 'sell' if side == 'long' else 'buy'
                ex.create_order(symbol, 'market', exit_side, amount, params={'posSide': pos_side}) [cite: 2026-02-12]
                send_msg(f"✅ İşlem Kapatıldı: {symbol}\nSonuç alındı.")
                del active_trades[symbol]
                break
        except: break

# --- [4. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **V26 AKTİF**\nRadar sorunsuz çalışıyor. İlk sinyal bekleniyor.") [cite: 2026-02-12]
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = [s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']]
            
            for s in symbols[:200]: # Hız için ilk 200 hacimli coin
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal = get_signal(s)
                    if signal:
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            side = 'buy' if signal == 'long' else 'sell'
                            # Hata veren unilateral/position çakışmasını bu parametreler çözer
                            ex.create_order(symbol=s, type='market', side=side, amount=amt, 
                                            params={'posSide': signal, 'tdMode': 'isolated'})
                            
                            active_trades[s] = True
                            send_msg(f"🔥 **YENİ İŞLEM**\nKoin: {s}\nYön: {signal.upper()}") [cite: 2026-02-12]
                            threading.Thread(target=monitor, args=(s, p, amt, signal), daemon=True).start()
                        except: pass
                time.sleep(0.1)
            time.sleep(10)
        except: time.sleep(15)

# --- [5. BAŞLATICI] ---
@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, f"📡 Radar Aktif\n📈 Aktif İşlem: {len(active_trades)}")

if __name__ == "__main__":
    # main_loop artık her zaman erişilebilir
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
