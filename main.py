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

# --- [AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

# --- [EKSTRA ANALİZ GÖZÜ: BTC DURUMU] ---
def get_btc_bias():
    try:
        btc = ex.fetch_ohlcv('BTC/USDT:USDT', timeframe='5m', limit=5)
        # Son 5 mumda %0.5'ten fazla düşüş varsa 'tehlikeli' kabul et
        change = (btc[-1][4] - btc[0][1]) / btc[0][1]
        return "SAFE" if change > -0.005 else "DANGER"
    except: return "SAFE"

# --- [GELİŞMİŞ OTONOM KARAR MOTORU] ---
def autonomous_decision(symbol):
    try:
        # 5M ve 1H Verileri
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=24)
        
        # 1. Hacim Analizi (Ortalama hacmin en az 1.5 katı olmalı)
        vols = [x[5] for x in ohlcv_5m[-10:]]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        current_vol = vols[-1]
        
        # 2. SMC ve Gövde Kapanışı
        lookback = ohlcv_5m[-40:-5]
        min_l = min([x[3] for x in lookback])
        max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        # BTC Kalkanı
        btc_status = get_btc_bias()

        # LONG KARARI (Likidite alımı + Gövde kapanışı + Hacim + BTC onayı)
        if m2[3] < min_l and m1[4] > m2[2]: # İğne sonrası kapanış onayı
            if current_vol > (avg_vol * 1.5) and btc_status == "SAFE":
                return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        
        # SHORT KARARI
        if m2[2] > max_h and m1[4] < m2[3]:
            if current_vol > (avg_vol * 1.5):
                return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
                
        return None
    except: return None

# --- [İŞLEM VE KASA YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # %0.75 karda stopu girişe çek (TP1 Koruması)
                if pnl >= 0.75 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kârı kilitledim. Bu işlemden artık zarar etmeyiz ortak!")

                # Pozisyon Kapatma (SL veya TP)
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol}**: Kararımı verdim ve çıktım. Sonuç: %{pnl}")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

# --- [ANA RADAR] ---
def radar_loop():
    send_msg("🚀 **Otonom Zihin Güncellendi!**\nArtık sadece iğnelere bakmıyorum; hacim ve BTC onayını da arıyorum. Borsayı taramaya başladım.")
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
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'pnl': 0}
                    send_msg(f"🧠 **YENİ KARAR:** {symbol}\nBu sefer her şey kitabına uygun! Hacim ve mum kapanışı onaylı işleme daldım. 🏹")
                time.sleep(0.1)
        except: time.sleep(20)

@bot.message_handler(commands=['bakiye', 'durum'])
def handle_commands(message):
    try:
        bal = float(ex.fetch_balance().get('total', {}).get('USDT', 0))
        txt = f"💰 **Kasa:** {round(bal, 2)} USDT\n🔥 **İşlemler:** {len(active_trades)}/{MAX_ACTIVE_TRADES}"
        bot.reply_to(message, txt)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
