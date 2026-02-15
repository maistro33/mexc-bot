import ccxt
import os
import telebot
import time
import threading

# --- [BAĞLANTILAR] ---
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [GEMINI ANA AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 1    # 25 USDT için tek odak, tam isabet.
FIXED_ENTRY_USDT = 5     # Risk yönetimi için 5 USDT giriş.
MIN_VOLUME_24H = 100000000 # 100M+ Hacim şartı.

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_balance():
    try:
        bal = ex.fetch_balance()
        return round(float(bal.get('total', {}).get('USDT', 0)), 2)
    except: return 0

# --- [ANALİTİK ZEKA: TREND VE HACİM SÜZGECİ] ---
def gemini_advanced_logic(symbol):
    try:
        ticker = ex.fetch_ticker(symbol)
        if float(ticker.get('quoteVolume', 0)) < MIN_VOLUME_24H: return None

        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=200)
        closes = [x[4] for x in ohlcv]
        
        # Trend Onayı: EMA 200
        ema200 = sum(closes) / len(closes)
        cp = closes[-1]
        
        # RSI Hesaplama
        def get_rsi(prices, n=14):
            deltas = [prices[i+1]-prices[i] for i in range(len(prices)-1)]
            up = sum([d for d in deltas[-n:] if d > 0]) / n
            down = sum([-d for d in deltas[-n:] if d < 0]) / n
            if down == 0: return 100
            return 100 - (100 / (1 + (up/down)))

        rsi = get_rsi(closes)

        # KARAR MEKANİZMASI
        # Trend Üstü + RSI Dip = Güçlü Alış
        if cp > ema200 and rsi < 32:
            return {'side': 'long', 'sl': cp * 0.982, 'reason': 'Trend pozitif, RSI aşırı satımda. Kurumsal destek bekliyorum.'}

        # Trend Altı + RSI Tepe = Güçlü Satış
        if cp < ema200 and rsi > 68:
            return {'side': 'short', 'sl': cp * 1.018, 'reason': 'Trend negatif, RSI şişmiş. Satış baskısı ağır basıyor.'}

        return None
    except: return None

# --- [DINAMIK YÖNETİM: TRAILING & KOMİSYON] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                
                diff = ((curr_p - t['entry']) / t['entry'] * 100) if t['side'] == 'long' else ((t['entry'] - curr_p) / t['entry'] * 100)
                pnl = round(diff * LEVERAGE, 2)
                elapsed = (time.time() - t['start_time']) / 60

                # 1. Trailing Stop & Break-Even
                if pnl >= 3.0 and not t.get('be_active', False):
                    # Stopu girişe ve komisyonun bir tık üstüne taşı
                    t['sl'] = t['entry'] * (1.004 if t['side'] == 'long' else 0.996)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Komisyon kalkanı devrede, artık bu işlem güvenli limanda!")

                # 2. İz Süren Stop (Kâr büyüdükçe stopu taşı)
                if pnl >= 8.0:
                    new_sl = t['entry'] * (1 + (pnl-4)/100 if t['side'] == 'long' else 1 - (pnl-4)/100)
                    if (t['side'] == 'long' and new_sl > t['sl']) or (t['side'] == 'short' and new_sl < t['sl']):
                        t['sl'] = new_sl

                # 3. Akıllı Çıkış
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']) or pnl >= 25.0:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol} Kapandı.** PNL: %{pnl}\nGüncel Bakiye: {get_balance()} USDT")
                    del active_trades[symbol]
            time.sleep(8)
        except: time.sleep(15)

def radar_loop():
    send_msg(f"🦅 **Gemini Recovery Pro Başlatıldı!**\n\n💰 Bakiye: {get_balance()} USDT\n🎯 Odak: Hacimli Devler & Trend Onayı\n\nSabırla en doğru fırsatı bekliyorum ortağım.")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                decision = gemini_advanced_logic(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'start_time': time.time()}
                    send_msg(f"🧠 **STRATEJİK GİRİŞ:** {symbol}\n\n*Neden:* {decision['reason']}\n*Hacim:* Onaylandı ✅\n*Trend:* Onaylandı ✅")
                time.sleep(0.2)
        except: time.sleep(30)

@bot.message_handler(commands=['durum', 'bakiye'])
def report(message):
    try:
        bal = get_balance()
        msg = f"📊 **Gemini Raporu:**\n💰 Kasa: {bal} USDT\n🔥 Aktif Takip: {len(active_trades)}"
        if active_trades:
            for s, t in active_trades.items():
                msg += f"\n▫️ {s} işleminde kâr/zarar süzülüyor..."
        bot.reply_to(message, msg)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
