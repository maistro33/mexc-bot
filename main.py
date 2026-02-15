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

# --- [STRATEJİK AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
TRAIL_ACTIVATE_PNL = 1.2 
TRAIL_DISTANCE = 0.008   
MIN_DISPLACEMENT = 0.005 

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_total_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal['total']['USDT'])
    except: return 0.0

# --- [HTF: 1S VE 4S TREND ANALİZİ] ---
def get_market_bias(symbol):
    """Büyük resim onayı: 1H ve 4H trendlerini kontrol eder."""
    try:
        # 1 Saatlik Onay
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=20)
        sma_1h = sum([x[4] for x in ohlcv_1h]) / 20
        # 4 Saatlik Onay
        ohlcv_4h = ex.fetch_ohlcv(symbol, timeframe='4h', limit=20)
        sma_4h = sum([x[4] for x in ohlcv_4h]) / 20
        
        curr_p = ohlcv_1h[-1][4]
        
        if curr_p > sma_1h and curr_p > sma_4h: return 'LONG_ONLY'
        if curr_p < sma_1h and curr_p < sma_4h: return 'SHORT_ONLY'
        return 'NEUTRAL'
    except: return 'NEUTRAL'

# --- [SMC ANALİZ: 5M] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback])
        min_l = min([x[3] for x in lookback])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        if m2[3] < min_l and m1[4] > m2[2] and move_size >= MIN_DISPLACEMENT:
            if m1[3] > m3[2]: return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        if m2[2] > max_h and m1[4] < m2[3] and move_size >= MIN_DISPLACEMENT:
            if m1[2] < m3[3]: return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        return None
    except: return None

# --- [KOMUT VE DURUM RAPORLAMA] ---
@bot.message_handler(commands=['bakiye', 'durum', 'status'])
def send_status(message):
    try:
        bal = get_total_balance()
        txt = f"💰 **KASA DURUMU:** {round(bal, 2)} USDT\n"
        txt += f"📊 **AKTİF AVLAR:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
        if active_trades:
            for s, t in active_trades.items():
                txt += f"\n🔸 **{s}**: %{t.get('pnl', 0)} ({'🛡️ Korumada' if t.get('be_active') else '⏳ Takipte'})"
        else: txt += "\n😴 Radar temiz."
        bot.reply_to(message, txt, parse_mode='Markdown')
    except: pass

# --- [SANAL TAKİP VE İŞLEM YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # 🛡️ KOMİSYON KALKANI
                if pnl >= 0.8 and not t.get('be_active', False):
                    offset = 0.002
                    active_trades[symbol]['sl'] = t['entry'] * (1 + offset) if t['side'] == 'long' else t['entry'] * (1 - offset)
                    active_trades[symbol]['be_active'] = True
                    send_msg(f"🛡️ **{symbol} Kalkanı Devreye Girdi!**\nMasraflar kilitlendi, bu işlem artık zarar yazmaz.")

                # 🏃 TRAILING
                if pnl >= TRAIL_ACTIVATE_PNL:
                    pot_sl = curr_p * (1 - TRAIL_DISTANCE) if t['side'] == 'long' else curr_p * (1 + TRAIL_DISTANCE)
                    if (t['side'] == 'long' and pot_sl > t['sl']) or (t['side'] == 'short' and pot_sl < t['sl']):
                        active_trades[symbol]['sl'] = pot_sl
                        active_trades[symbol]['trailing_active'] = True

                # 🏁 KAPANIŞ
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    bal = get_total_balance()
                    send_msg(f"🏁 **İŞLEM KAPANDI**\n**Coin:** {symbol}\n**Final PNL:** %{pnl}\n**Yeni Bakiye:** {round(bal, 2)} USDT")
                    del active_trades[symbol]
            time.sleep(6)
        except: time.sleep(10)

# --- [RADAR - 1S & 4S ONAYLI] ---
def radar_loop():
    send_msg("🦅 **EKSİKSİZ RADAR AKTİF!**\n1S/4S Trend Onayı ve Komisyon Kalkanı devrede.\n`/bakiye` ile beni sorgulayabilirsin.")
    while True:
        try:
            if len(active_trades) < MAX_ACTIVE_TRADES:
                tickers = ex.fetch_tickers()
                pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:100]
                
                for symbol in pairs:
                    if len(active_trades) >= MAX_ACTIVE_TRADES: break
                    if symbol in active_trades: continue
                    
                    bias = get_market_bias(symbol) # HTF ONAYI
                    sig = check_smc_signal(symbol) # 5M SİNYALİ
                    
                    if sig and ((sig['side'] == 'long' and bias == 'LONG_ONLY') or (sig['side'] == 'short' and bias == 'SHORT_ONLY')):
                        bal = ex.fetch_balance()
                        if float(bal['free']['USDT']) < FIXED_ENTRY_USDT: continue 
                        
                        price = ex.fetch_ticker(symbol)['last']
                        amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                        ex.set_leverage(LEVERAGE, symbol)
                        ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                        
                        active_trades[symbol] = {
                            'side': sig['side'], 'entry': price, 'amt': amt, 
                            'sl': sig['sl'], 'be_active': False, 'pnl': 0
                        }
                        send_msg(f"🏹 **AV BAŞLADI:** {symbol}\nBüyük Resim (1H/4H) onayladı! ✅")
            time.sleep(20)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
