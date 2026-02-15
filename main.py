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

# --- [KARAR PARAMETRELERİ] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 2    
FIXED_ENTRY_USDT = 5     
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

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
        
        # Daha sıkı bir hacim ve mum onayı (Komisyon boşa gitmesin)
        if m2[3] < min_l and m1[4] > m2[2] and vol_surge > 2.2:
            sl = m1[4] * 0.982 # %1.8 stop mesafesi (Nefes alanı)
            return {'side': 'long', 'entry': m1[4], 'sl': sl, 'reason': 'Güçlü bir hacim patlaması ve likidite alımı gördüm. Komisyona değer!'}

        if m2[2] > max_h and m1[4] < m2[3] and vol_surge > 2.2:
            sl = m1[4] * 1.018
            return {'side': 'short', 'entry': m1[4], 'sl': sl, 'reason': 'Tepede büyük bir satış baskısı yakaladım, düşüş potansiyeli yüksek.'}

        return None
    except: return None

def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                ticker = ex.fetch_ticker(symbol)
                curr_p = ticker['last']
                
                # Fiyat farkı yüzdesi (kaldıraçsız)
                price_diff_pct = ((curr_p - t['entry']) / t['entry'] * 100) if t['side'] == 'long' else ((t['entry'] - curr_p) / t['entry'] * 100)
                pnl = round(price_diff_pct * LEVERAGE, 2)
                
                elapsed_time = (time.time() - t['start_time']) / 60 # Dakika cinsinden

                # --- [KOMİSYON KORUMASI VE SABIR] ---
                # 1. En az 3 dakika geçmeden ve fiyat komisyonu kurtarmadan (%0.3 spot / %3 PNL) panik çıkışı yapma
                if elapsed_time < 3 and pnl < 3.0 and pnl > -3.0:
                    continue 

                # 2. Kârı koruma eşiği: PNL %5'e ulaşınca stopu girişe çek
                if pnl >= 5.0 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.003 if t['side'] == 'long' else 0.997) # Komisyonu da kurtaracak şekilde
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Komisyonu ve girişi kurtardık, artık bu işlem bizim için bedava!")

                # 3. Çıkış Kararı (SL veya manuel ters hareket)
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol}**: İşlem sonuçlandı. PNL: %{pnl}")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(10)

def radar_loop():
    send_msg("🚀 **Sabır Filtresi Aktif!**\nArtık borsa komisyonlarını korumadan erkenden kaçmıyorum. Kaliteli fırsat bekliyorum.")
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
                    send_msg(f"🧠 **KARAR:** {symbol}\n{decision['reason']}\n\n*Harcayacağımız komisyona değecek bir hareket bekliyorum.*")
                time.sleep(0.1)
        except: time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
