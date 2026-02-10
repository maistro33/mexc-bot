import ccxt
import telebot
import time
import os
import math
import threading

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
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLARINIZ] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,   # %75 Kar Al (TP1)
    'max_active_trades': 3,
    'timeframe': '5m'
}

active_trades = {}

# --- [3. YARDIMCI FONKSİYONLAR] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

@bot.message_handler(commands=['durum', 'bakiye'])
def send_status(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance.get('USDT', {}).get('free', 0)
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt_free:.2f} USDT\n🦅 Radar Aktif (150 Parite)")
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {str(e)}")

# --- [4. ANA STRATEJİ VE DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🦅 **BOT SIFIRLANDI VE BAŞLADI**\nYazım hatası giderildi, borsa modu otomatik uyumda!")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s and (markets[s]['quoteVolume'] or 0) > 1000000]
            
            for sym in symbols[:150]:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                
                # Market Analizi (Anti-Manipülasyon: Gövde Kapanış)
                bars = ex.fetch_ohlcv(sym, timeframe=CONFIG['timeframe'], limit=30)
                c = [b[4] for b in bars]
                h = [b[2] for b in bars]
                l = [b[3] for b in bars]
                
                recent_high, recent_low = max(h[-15:-1]), min(l[-15:-1])
                
                side = None
                if c[-1] > recent_high: side = 'buy'
                elif c[-1] < recent_low: side = 'sell'

                if side:
                    # Borsa Moduna Göre Ayarla (Hedge/One-way hatasını otomatik çözer)
                    pos_mode = ex.fetch_position_mode(sym)
                    is_hedge = pos_mode['hedge']
                    
                    ex.set_leverage(CONFIG['leverage'], sym)
                    entry = c[-1]
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    # Giriş Emri
                    params = {'posSide': 'long' if side == 'buy' else 'short'} if is_hedge else {}
                    ex.create_market_order(sym, side, amount, params=params)
                    time.sleep(1)

                    # Stop Loss ve %75 TP
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    risk = entry * 0.01 
                    stop = entry - risk if side == 'buy' else entry + risk
                    tp1 = entry + (risk * 1.5) if side == 'buy' else entry - (risk * 1.5)

                    close_params = {'stopPrice': stop, 'reduceOnly': True}
                    if is_hedge: close_params['posSide'] = 'long' if side == 'buy' else 'short'
                    
                    # Emirleri Diz
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params=close_params) # Stop
                    
                    tp_params = close_params.copy()
                    tp_params['stopPrice'] = tp1
                    tp_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp_qty, params=tp_params) # %75 TP

                    active_trades[sym] = True
                    bot.send_message(MY_CHAT_ID, f"🎯 **İşlem Açıldı:** {sym}\nStop ve %75 TP1 dizildi.")
                
                time.sleep(0.1)
            time.sleep(15)
        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    # Telegram dinlemeyi başlat (daemon=True ile çökme önlenir)
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    ex.load_markets()
    main_loop()
