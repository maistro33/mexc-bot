import ccxt
import os
import telebot
import time
import threading
import numpy as np

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

# --- [KARAR MOTORU PARAMETRELERİ] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 2    # Daha kaliteli işlemler için 2'ye odaklandık
FIXED_ENTRY_USDT = 5     # 31 USDT bakiye için en güvenli giriş tutarı
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_total_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal.get('total', {}).get('USDT', 0))
    except: return 0.0

# --- [GELİŞMİŞ OTONOM ANALİZ] ---
def autonomous_decision(symbol):
    try:
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=24)
        
        # 1. Hacim Onayı (Gerçek para girişi var mı?)
        vols = [x[5] for x in ohlcv_5m[-10:]]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        if vols[-1] < (avg_vol * 2.0): return None 

        # 2. SMC ve Likidite Kontrolü
        lookback = ohlcv_5m[-40:-5]
        min_l = min([x[3] for x in lookback])
        max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        # 3. Trend Filtresi (1 Saatlik SMA)
        closes_1h = [x[4] for x in ohlcv_1h]
        sma_1h = sum(closes_1h) / len(closes_1h)

        # Karar: LONG (Likidite alımı + SMA üstü + Hacim)
        if m2[3] < min_l and m1[4] > m2[2]:
            if m1[4] > sma_1h:
                sl_price = m1[4] * 0.985 # %1.5 nefes alanı
                return {'side': 'long', 'entry': m1[4], 'sl': sl_price}

        # Karar: SHORT (Likidite alımı + SMA altı + Hacim)
        if m2[2] > max_h and m1[4] < m2[3]:
            if m1[4] < sma_1h:
                sl_price = m1[4] * 1.015 # %1.5 nefes alanı
                return {'side': 'short', 'entry': m1[4], 'sl': sl_price}

        return None
    except: return None

# --- [İŞLEM YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                
                # Saniyeler içinde stop olmayı engellemek için 60 saniye bekle
                if time.time() - t['start_time'] < 60: continue

                ticker = ex.fetch_ticker(symbol)
                curr_p = ticker['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # %1.25 kar görünce stopu girişe çek (BE+)
                if pnl >= 1.25 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kârı kilitledim ortak, bu işlem artık güvenli!")

                # Pozisyon Kapatma
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol}**: Karar verdim ve çıktım. Sonuç: %{pnl}")
                    del active_trades[symbol]
            time.sleep(8)
        except: time.sleep(10)

# --- [RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg("🚀 **Otonom Zihin 2.0 Yayında!**\nArtık daha sabırlı ve hacim odaklıyım. Borsayı taramaya başlıyorum.")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                decision = autonomous_decision(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    
                    active_trades[symbol] = {
                        'side': decision['side'], 'entry': price, 'amt': amt, 
                        'sl': decision['sl'], 'pnl': 0, 'start_time': time.time()
                    }
                    send_msg(f"🧠 **YENİ KARAR:** {symbol}\nHacimli ve kurumsal bir iz buldum, daldım! 🏹")
                time.sleep(0.1)
        except: time.sleep(20)

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye', 'durum'])
def handle_commands(message):
    try:
        current_bal = get_total_balance()
        txt = f"💰 **Kasa:** {round(current_bal, 2)} USDT\n🔥 **İşlemler:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
        if active_trades:
            for s, t in active_trades.items():
                txt += f"\n🔸 {s}: %{t.get('pnl', 0)}"
        bot.reply_to(message, txt)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
