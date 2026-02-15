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

# --- [PROFESYONEL AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    # Sayıyı azalttık, öze odaklandık
FIXED_ENTRY_USDT = 10    
TRAIL_ACTIVATE_PNL = 1.0 # Takip %1.0 kârda başlar (Daha garantici)
TRAIL_DISTANCE = 0.007   # %0.7 geriden takip (İğnelerden korunmak için esnettik)
MIN_DISPLACEMENT = 0.004 # Mumun en az %0.4 boyunda olması şart (Güç göstergesi)

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_free_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal['free']['USDT'])
    except: return 0.0

# --- [GELİŞMİŞ SMC MOTORU] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        # Likidite alanı için daha geniş bakıyoruz (Son 40 mum)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback])
        min_l = min([x[3] for x in lookback])
        
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        
        # Hareketin sertliği (Displacement) hesaplama
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # LONG: Likidite süpürülmüş mü? + Mum yeterince sert mi? + FVG var mı?
        if m2[3] < min_l and m1[4] > m2[2] and move_size >= MIN_DISPLACEMENT:
            if m1[3] > m3[2]: # Net FVG boşluğu
                return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        
        # SHORT
        if m2[2] > max_h and m1[4] < m2[3] and move_size >= MIN_DISPLACEMENT:
            if m1[2] < m3[3]: # Net FVG boşluğu
                return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        
        return None
    except: return None

# --- [GELİŞMİŞ TRAILING YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                
                # Trailing Güncelleme
                if pnl >= TRAIL_ACTIVATE_PNL:
                    if t['side'] == 'long':
                        potential_sl = curr_p * (1 - TRAIL_DISTANCE)
                        if potential_sl > t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            if not t['trailing_active']:
                                active_trades[symbol]['trailing_active'] = True
                                send_msg(f"🎯 **{symbol} HEDEFE KİLİTLENDİ!**\nSert hareket yakalandı, iz süren stop devrede.")
                    else:
                        potential_sl = curr_p * (1 + TRAIL_DISTANCE)
                        if potential_sl < t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            if not t['trailing_active']:
                                active_trades[symbol]['trailing_active'] = True
                
                # Çıkış
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])
                if hit_sl:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    msg = "✅ **KÂRLI TAKİP SONLANDI**" if t['trailing_active'] else "🛑 **STRATEJİ STOP**"
                    send_msg(f"{msg}\n**{symbol}**\nPNL: %{pnl}\nKasa süpürüldü. ✅")
                    del active_trades[symbol]
            time.sleep(7)
        except: time.sleep(7)

# --- [RADAR] ---
def radar_loop():
    send_msg("🦅 **KESKİN NİŞANCI SMC RADARI AKTİF!**\nSadece en sert ve hacimli dönüşler taranıyor.")
    while True:
        if len(active_trades) < MAX_ACTIVE_TRADES:
            tickers = ex.fetch_tickers()
            # İlk 75 en hacimli (Güvenli Liman)
            pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:75]
            
            for symbol in pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                sig = check_smc_signal(symbol)
                if sig:
                    if get_free_balance() < FIXED_ENTRY_USDT: continue 
                    try:
                        price = ex.fetch_ticker(symbol)['last']
                        amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                        ex.set_leverage(LEVERAGE, symbol)
                        ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                        
                        active_trades[symbol] = {'side': sig['side'], 'entry': price, 'amt': amt, 'sl': sig['sl'], 'trailing_active': False}
                        send_msg(f"🏹 **YENİ AV YAKALANDI!**\n\n💎 **Coin:** {symbol}\n💰 **Miktar:** 10 USDT\n🛡️ **SL Seviyesi:** {round(sig['sl'], 5)}\n🚀 Sert hareket onaylandı!")
                        time.sleep(2)
                    except: pass
        time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
