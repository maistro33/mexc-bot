import ccxt
import os
import telebot
import time
import threading

# --- [BAGLANTILAR] ---
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 1    
FIXED_ENTRY_USDT = 10    # Her islemde 10 USDT bakiye kullanir
MIN_VOLUME_24H = 100000000 

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_balance():
    try: 
        bal = ex.fetch_balance()
        return round(float(bal.get('total', {}).get('USDT', 0)), 2)
    except: return 0

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['durum', 'bakiye'])
def handle_commands(message):
    try:
        balance = get_balance()
        if not active_trades:
            resp = f"📊 **GEMINI RAPORU**\n\n💰 Bakiye: `{balance} USDT` \n🔍 Pusuya yatıldı, temiz bir trend bekleniyor."
        else:
            resp = f"📊 **GEMINI RAPORU**\n\n💰 Bakiye: `{balance} USDT` \n🔥 Aktif İşlem Var!\n"
            for s, t in active_trades.items():
                p_now = ex.fetch_ticker(s)['last']
                pnl = round(((p_now - t['entry'])/t['entry']*100*LEVERAGE) if t['side']=='long' else ((t['entry'] - p_now)/t['entry']*100*LEVERAGE), 2)
                resp += f"\n🔸 **{s}** ({t['side'].upper()})\n   - Giriş: `{t['entry']}`\n   - Anlık PNL: `%{pnl}`\n   - Aktif Stop: `{t['sl']}`"
        bot.reply_to(message, resp, parse_mode='Markdown')
    except: pass

# --- [TREND ANALIZI] ---
def gemini_logic(symbol):
    try:
        ticker = ex.fetch_ticker(symbol)
        if float(ticker.get('quoteVolume', 0)) < MIN_VOLUME_24H: return None
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        closes = [x[4] for x in ohlcv]
        ema20 = sum(closes[-20:]) / 20
        ema50 = sum(closes[-50:]) / 50
        cp = closes[-1]
        
        if cp > ema20 and ema20 > ema50:
            return {'side': 'long', 'sl': cp * 0.982, 'msg': 'Yükseliş trendi güçleniyor.'}
        if cp < ema20 and ema20 < ema50:
            return {'side': 'short', 'sl': cp * 1.018, 'msg': 'Düşüş trendi netleşti.'}
        return None
    except: return None

# --- [ISLEM YONETIMI] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                diff = ((curr_p - t['entry']) / t['entry'] * 100) if t['side'] == 'long' else ((t['entry'] - curr_p) / t['entry'] * 100)
                pnl = round(diff * LEVERAGE, 2)

                # 1. Aşama: %5 Kârda Komisyon Kalkanı (Girişin %0.3 ilerisi)
                if pnl >= 5.0 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.003 if t['side'] == 'long' else 0.997)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kâr %5 oldu. Stop, komisyonu kurtaracak şekilde kâr bölgesine çekildi: `{t['sl']}`")

                # 2. Aşama: %10 Kârda İz Süren Stop (Trailing)
                if pnl >= 10.0:
                    potential_sl = curr_p * 0.985 if t['side'] == 'long' else curr_p * 1.015
                    if (t['side'] == 'long' and potential_sl > t['sl']) or (t['side'] == 'short' and potential_sl < t['sl']):
                        t['sl'] = round(potential_sl, 6)
                        if pnl > t.get('last_pnl', 0) + 5:
                            send_msg(f"📈 **{symbol}**: Trend takibi devam ediyor. PNL: %{pnl}, Yeni Stop: `{t['sl']}`")
                            t['last_pnl'] = pnl

                # Kapanış Kontrolü
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    res = "💰 KÂRLI KAPANDI" if pnl > 0 else "🛡️ STOP OLDU (KASAYI KORUDUK)"
                    send_msg(f"{res}\n\nSembol: {symbol}\nPNL: %{pnl}\nYeni Bakiye: {get_balance()} USDT")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

def radar():
    send_msg("🚀 **Gemini V3-Elite Aktif!**\nSöz verdiğimiz gibi; kasa büyüyecek, risk azalacak.\nKomutlar: /durum, /bakiye")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                decision = gemini_logic(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'last_pnl': 0}
                    send_msg(f"🎯 **YENİ İŞLEM:** {symbol}\n\nGiriş: `{price}`\nİlk Stop: `{round(decision['sl'], 6)}`\nNeden: {decision['msg']}")
                time.sleep(0.5)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar, daemon=True).start()
    bot.infinity_polling()
