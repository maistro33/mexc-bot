import ccxt
import telebot
import time
import os
import math

# --- [BAĞLANTILAR] ---
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

# --- [AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'max_active_trades': 3,
    'timeframe': '5m'
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

def analyze_market(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]
        recent_high, recent_low = max(h[-15:-1]), min(l[-15:-1])
        avg_vol = sum(v[-10:-1]) / 10
        if v[-1] > (avg_vol * 1.2):
            if c[-1] > recent_high: return 'buy', c[-1], min(l[-5:]), "LONG"
            if c[-1] < recent_low: return 'sell', c[-1], max(h[-5:]), "SHORT"
        return None, None, None, None
    except: return None, None, None, None

def main_loop():
    bot.send_message(MY_CHAT_ID, "🦅 **SMC BOT GÜNCELLENDİ**\nBorsa moduna tam uyum sağlandı. Av başlıyor!")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s and (markets[s]['quoteVolume'] or 0) > 1000000]
            
            for sym in symbols[:150]:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                
                side, entry, stop, label = analyze_market(sym)
                if side:
                    # 1. ADIM: Borsanın modunu anlık öğren
                    pos_mode = ex.fetch_position_mode(sym)
                    is_hedge = pos_mode['hedge'] # True ise Hedge, False ise One-way
                    
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    # 2. ADIM: Giriş Emri (Moda göre parametre ekle)
                    params = {'posSide': 'long' if side == 'buy' else 'short'} if is_hedge else {}
                    ex.create_market_order(sym, side, amount, params=params)
                    time.sleep(1)

                    # 3. ADIM: Stop Loss ve TP (%75)
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    close_params = {'stopPrice': stop, 'reduceOnly': True}
                    if is_hedge: close_params['posSide'] = 'long' if side == 'buy' else 'short'
                    
                    # Stop Loss
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params=close_params)
                    
                    # TP (%75)
                    tp_params = close_params.copy()
                    risk = abs(entry - stop)
                    tp_params['stopPrice'] = entry + (risk * 1.5) if side == 'buy' else entry - (risk * 1.5)
                    ex.create_order(sym, 'trigger_market', exit_side, round_amount(sym, amount * CONFIG['tp1_ratio']), params=tp_params)

                    active_trades[sym] = True
                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI** ({'Hedge' if is_hedge else 'Tek Yönlü'})\n{sym}\nTP1 (%75) ve Stop dizildi.")
                
                time.sleep(0.05)
            time.sleep(10)
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    main_loop()
