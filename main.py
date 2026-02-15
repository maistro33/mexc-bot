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

# --- [KARAR VE KASA PARAMETRELERİ] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 2    
FIXED_ENTRY_USDT = 5     
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_balance():
    try:
        bal = ex.fetch_balance()
        return round(float(bal.get('total', {}).get('USDT', 0)), 2)
    except: return "Bilinmiyor"

# --- [GEMINI KARAR MANTIĞI] ---
def gemini_decision_logic(symbol):
    try:
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        vols = [x[5] for x in ohlcv_5m[-10:]]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        vol_surge = vols[-1] / avg_vol

        lookback = ohlcv_5m[-40:-5]
        min_l = min([x[3] for x in lookback])
        max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        # Komisyonu kurtaracak güçlü sinyal (Hacim > 2.2x)
        if m2[3] < min_l and m1[4] > m2[2] and vol_surge > 2.2:
            return {'side': 'long', 'entry': m1[4], 'sl': m1[4] * 0.98, 'reason': 'Alt tarafta likiditeyi süpürdüler, şimdi hacimle yukarı sürüyorlar. Giriyorum!'}

        if m2[2] > max_h and m1[4] < m2[3] and vol_surge > 2.2:
            return {'side': 'short', 'entry': m1[4], 'sl': m1[4] * 1.02, 'reason': 'Tepedeki alıcıları tuzağa düşürdüler, büyük bir satış baskısı seziyorum.'}

        return None
    except: return None

# --- [İŞLEM VE KASA YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                ticker = ex.fetch_ticker(symbol)
                curr_p = ticker['last']
                
                price_diff = ((curr_p - t['entry']) / t['entry'] * 100) if t['side'] == 'long' else ((t['entry'] - curr_p) / t['entry'] * 100)
                pnl = round(price_diff * LEVERAGE, 2)
                elapsed = (time.time() - t['start_time']) / 60

                # Masrafları koruma (En az 3 dk veya %3 PNL hareketi bekle)
                if elapsed < 3 and abs(pnl) < 3.0: continue 

                # Kârı ve komisyonu kilitle
                if pnl >= 5.0 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.003 if t['side'] == 'long' else 0.997)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Komisyonu ve kârı sağlama aldım ortak. Rahatız!")

                # Çıkış
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol} Raporu:** Pozisyonu kapattım. Net PNL: %{pnl}\nKasa: {get_balance()} USDT")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(10)

# --- [ANA RADAR] ---
def radar_loop():
    send_msg(f"✨ **Gemini Zihni Devreye Girdi!**\n\n💰 **Başlangıç Bakiyemiz:** {get_balance()} USDT\n🚀 Artık senin bir yansıman gibi karar veriyorum. Piyasayı süzmeye başladım.")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                decision = gemini_decision_logic(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'start_time': time.time()}
                    send_msg(f"🧠 **KARAR VERDİM:** {symbol}\n\n*Neden:* {decision['reason']}\n*Miktar:* {FIXED_ENTRY_USDT} USDT (10x)\n\nİzlemeye devam ediyorum ortak!")
                time.sleep(0.1)
        except: time.sleep(20)

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye', 'durum', 'start'])
def handle_commands(message):
    try:
        bal = get_balance()
        txt = f"📊 **Durum Raporu Hazır Ortağım!**\n\n💰 **Kasada Ne Var?** {bal} USDT\n🔥 **Aktif Kararlar:** {len(active_trades)}/{MAX_ACTIVE_TRADES}"
        if active_trades:
            for s, t in active_trades.items():
                txt += f"\n▫️ {s}: %{t.get('pnl', 'Hesaplanıyor...')}"
        bot.reply_to(message, txt)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
