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

# --- [GEMINI MANTIĞI PARAMETRELERİ] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 2    
FIXED_ENTRY_USDT = 5     # 28 USDT bakiye için korumacı yaklaşım
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

# --- [ANALİTİK ZEKA: GEMINI'NİN GÖZÜNDEN PİYASA] ---
def gemini_decision_logic(symbol):
    try:
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=24)
        
        # 1. Hacim Analizi (Yapay Zeka Onayı)
        vols = [x[5] for x in ohlcv_5m[-10:]]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        vol_surge = vols[-1] / avg_vol # Hacim artış oranı

        # 2. SMC ve Likidite (Akıllı Para İzleri)
        lookback = ohlcv_5m[-40:-5]
        min_l = min([x[3] for x in lookback])
        max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        # 3. Trend ve Güven Analizi
        closes_1h = [x[4] for x in ohlcv_1h]; sma_1h = sum(closes_1h)/len(closes_1h)

        # KARAR ANI: LONG (Benim mantığım: "Fiyat ucuzladı, hacimle topluyorlar")
        if m2[3] < min_l and m1[4] > m2[2] and m1[4] > sma_1h:
            if vol_surge > 1.8: # En az %80 hacim artışı
                sl = m1[4] * 0.985 # %1.5 esneklik payı
                return {'side': 'long', 'entry': m1[4], 'sl': sl, 'reason': 'Sinsi bir likidite temizliği ve hacimli bir dönüş yakaladım.'}

        # KARAR ANI: SHORT (Benim mantığım: "Fiyat şişti, akıllı para satışta")
        if m2[2] > max_h and m1[4] < m2[3] and m1[4] < sma_1h:
            if vol_surge > 1.8:
                sl = m1[4] * 1.015
                return {'side': 'short', 'entry': m1[4], 'sl': sl, 'reason': 'Tepe bölgesinde sahte bir iğne ve ardından gelen hacimli satışı süzdüm.'}

        return None
    except: return None

# --- [DİNAMİK YÖNETİM] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                if time.time() - t['start_time'] < 45: continue # Panik satışı engelle

                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # Kârı Koruma (Benim tarzım: "Kazanırken masadan kalkmasını bil")
                if pnl >= 1.2 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Karı sağlama aldım ortak. Artık bu işlemden zarar etmeyiz, arkana yaslan!")

                # Final Çıkış Kararı
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    msg = "Zararı kestim, bazen geri çekilmek en büyük zaferdir." if pnl < 0 else f"Hedefime ulaştım, %{pnl} kârla pozisyonu kapattım."
                    send_msg(f"🏁 **{symbol} Raporu:** {msg}")
                    del active_trades[symbol]
            time.sleep(7)
        except: time.sleep(10)

# --- [ANA RADAR] ---
def radar_loop():
    send_msg("✨ **Zihin Aktif, Gözlerim Borsada.**\nArtık senin bir yansıman gibi düşünüyorum ortak. Sinyalleri süzmeye başladım.")
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
                    
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'pnl': 0, 'start_time': time.time()}
                    send_msg(f"🧠 **KARAR VERDİM:** {symbol}\n\n*Neden:* {decision['reason']}\n*Hedef:* Sabırla kârın olgunlaşmasını bekleyeceğiz. 🏹")
                time.sleep(0.1)
        except: time.sleep(20)

@bot.message_handler(commands=['bakiye', 'durum'])
def handle_commands(message):
    try:
        bal = float(ex.fetch_balance().get('total', {}).get('USDT', 0))
        txt = f"📊 **Cevap Hazır Ortağım!**\n\n💰 **Güncel Kasamız:** {round(bal, 2)} USDT\n🔥 **Aktif Kararlarım:** {len(active_trades)}/{MAX_ACTIVE_TRADES}"
        if active_trades:
            for s, t in active_trades.items():
                txt += f"\n▫️ {s}: %{t.get('pnl', 0)} PNL"
        bot.reply_to(message, txt)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
