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
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.035, 
    'sl_target': 0.018, 
    'max_active_trades': 3,
    'vol_threshold': 1.4,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. ANALİZ MOTORU - LONG & SHORT] ---
def get_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]
        avg_v = sum(v[-10:-1]) / 9
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])
        
        # LONG: Likidite süpürme (dip) + yukarı kırılım
        long_setup = l[-1] < min(l[-20:-5]) and c[-1] > max(c[-5:-1])
        # SHORT: Likidite süpürme (tepe) + aşağı kırılım
        short_setup = h[-1] > max(h[-20:-5]) and c[-1] < min(c[-5:-1])

        if vol_ok and long_setup: return 'long'
        if vol_ok and short_setup: return 'short'
        return None
    except: return None

# --- [4. TAKİP MOTORU] ---
def monitor(symbol, entry, amount, side):
    while symbol in active_trades:
        try:
            time.sleep(1)
            curr = float(ex.fetch_ticker(symbol)['last'])
            # Kar/Zarar hesaplama (Side'a göre)
            tp = entry * (1 + CONFIG['tp_target']) if side == 'long' else entry * (1 - CONFIG['tp_target'])
            sl = entry * (1 - CONFIG['sl_target']) if side == 'long' else entry * (1 + CONFIG['sl_target'])
            
            hit_tp = (side == 'long' and curr >= tp) or (side == 'short' and curr <= tp)
            hit_sl = (side == 'long' and curr <= sl) or (side == 'short' and curr >= sl)

            if hit_tp or hit_sl:
                # Kapatırken Hedge Mode parametresine dikkat
                pos_side = 'long' if side == 'long' else 'short'
                exit_side = 'sell' if side == 'long' else 'buy'
                ex.create_order(symbol, 'market', exit_side, amount, params={'posSide': pos_side})
                
                status = "💰 KÂR ALINDI" if hit_tp else "🛑 STOP OLDU"
                send_msg(f"{status}\nKoin: {symbol}\nYön: {side.upper()}")
                del active_trades[symbol]
                break
        except: break

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **V22 AKTİF: LONG & SHORT RADARI**\n300+ Coin çift yönlü taranıyor.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']], 
                            key=lambda x: tickers[x]['quoteVolume'] if tickers[x]['quoteVolume'] else 0, reverse=True)[:300]
            
            for s in symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal = get_signal(s)
                    if signal:
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            # HEDGE VE ONE-WAY UYUMLU EMİR
                            side = 'buy' if signal == 'long' else 'sell'
                            ex.create_order(symbol=s, type='market', side=side, amount=amt, 
                                            params={'posSide': signal, 'tdMode': 'isolated'})
                            
                            active_trades[s] = True
                            send_msg(f"🔥 **İŞLEM AÇILDI!**\nKoin: {s}\nYön: {signal.upper()}\nFiyat: {p}")
                            threading.Thread(target=monitor, args=(s, p, amt, signal), daemon=True).start()
                        except: pass
                time.sleep(0.05)
            time.sleep(5)
        except: time.sleep(10)

# --- [6. BAŞLATICI] ---
@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, f"📡 Radar Aktif\n📈 İşlem: {len(active_trades)}\nYön: Long & Short")

if __name__ == "__main__":
    # main_loop artık burada tanımlı ve erişilebilir
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
@bot.message_handler(commands=['bakiye'])

@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        # 1. Yol: Standart bakiye
        usdt = bal.get('USDT', {}).get('total', 0)
        
        # 2. Yol: Eğer yukarıdaki boşsa 'total' sözlüğünden çek
        if usdt == 0:
            usdt = bal.get('total', {}).get('USDT', 0)
            
        # 3. Yol: Eğer hala 0 ise (V2 vadeli hesaplar için)
        if usdt == 0 and 'info' in bal:
            for item in bal['info'].get('data', []):
                if item.get('marginCoin') == 'USDT':
                    usdt = float(item.get('available', 0))
                    break

        bot.reply_to(message, f"💰 **Güncel Bakiyen:** {usdt:.2f} USDT")
    except Exception as e:
        print(f"Bakiye Hatası: {e}")
        bot.reply_to(message, "⚠️ Bakiye şu an borsadan alınamadı.")
O def get_balance(message):
    try:
        # Senin 'ex' bağlantını kullanarak bakiye çekiyoruz
        bal = ex.fetch_balance()
        # USDT miktarını en güvenli yoldan alıyoruz
        usdt = bal['total']['USDT'] if 'USDT' in bal['total'] else 0
        bot.reply_to(message, f"💰 **Güncel Bakiyen:** {usdt:.2f} USDT")
    except Exception as e:
        bot.reply_to(message, "⚠️ Bakiye şu an çekilemedi, lütfen tekrar dene.")
