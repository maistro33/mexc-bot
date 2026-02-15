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

# --- [PROFESYONEL KASA KORUMA AYARLARI] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    # 34 USDT bakiyen için en güvenli miktar
TRAIL_ACTIVATE_PNL = 1.2 # %1.2 kâra ulaşmadan takip başlamaz (Masraf koruması)
TRAIL_DISTANCE = 0.008   # %0.8 geriden takip (Fiyatın nefes alması için)
MIN_DISPLACEMENT = 0.005 # %0.5'lik sert mum şartı (Kaliteli giriş)

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
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback])
        min_l = min([x[3] for x in lookback])
        
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # LONG: Likidite süpürme + Sert mum + FVG
        if m2[3] < min_l and m1[4] > m2[2] and move_size >= MIN_DISPLACEMENT:
            if m1[3] > m3[2]:
                return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        
        # SHORT: Likidite süpürme + Sert mum + FVG
        if m2[2] > max_h and m1[4] < m2[3] and move_size >= MIN_DISPLACEMENT:
            if m1[2] < m3[3]:
                return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        return None
    except: return None

# --- [GELİŞMİŞ TRAILING VE KOMİSYON KALKANI] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                
                # 🛡️ 1. ADIM: KOMİSYON KALKANI (BE+)
                # PNL %0.8 olduğunda stopu girişe (ve azıcık üzerine) çek
                if pnl >= 0.8 and not t.get('be_active', False):
                    # Girişin %0.2 önüne koy ki borsa masrafı çıksın
                    offset = 0.002 
                    new_sl = t['entry'] * (1 + offset) if t['side'] == 'long' else t['entry'] * (1 - offset)
                    active_trades[symbol]['sl'] = new_sl
                    active_trades[symbol]['be_active'] = True
                    send_msg(f"🛡️ **{symbol} KOMİSYON KALKANI AKTİF!**\nStop girişe (BE+) çekildi. Artık bu işlemden zarar etmeyeceksin.")

                # 🏃 2. ADIM: GERÇEK TRAILING
                if pnl >= TRAIL_ACTIVATE_PNL:
                    if t['side'] == 'long':
                        potential_sl = curr_p * (1 - TRAIL_DISTANCE)
                        if potential_sl > t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            active_trades[symbol]['trailing_active'] = True
                    else:
                        potential_sl = curr_p * (1 + TRAIL_DISTANCE)
                        if potential_sl < t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            active_trades[symbol]['trailing_active'] = True
                
                # 🏁 3. ADIM: KAPANIŞ KONTROLÜ
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])
                if hit_sl:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    status = "✅ KÂRLI TAKİP" if t.get('trailing_active') else "🛡️ KOMİSYON KORUMALI KAPANIŞ"
                    if pnl < 0 and not t.get('be_active'): status = "🛑 STOP"
                    
                    send_msg(f"{status}\n**{symbol}**\nFinal PNL: %{pnl}\nKasa süpürüldü. ✅")
                    del active_trades[symbol]
            time.sleep(6)
        except: time.sleep(6)

# --- [RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg(f"🕵️ **Keskin Nişancı Radar Aktif!**\nBakiye: {get_free_balance()} USDT\nMod: Kasa Koruma + Trailing")
    while True:
        if len(active_trades) < MAX_ACTIVE_TRADES:
            tickers = ex.fetch_tickers()
            # Hacmi yüksek olan ilk 100 coin (SMC buralarda çalışır)
            pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:100]
            
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
                        
                        active_trades[symbol] = {
                            'side': sig['side'], 'entry': price, 'amt': amt, 
                            'sl': sig['sl'], 'trailing_active': False, 'be_active': False
                        }
                        send_msg(f"🏹 **YENİ AV: {symbol}**\n💰 10 USDT dalış yapıldı.\n🛡️ İlk SL: {round(sig['sl'], 5)}\n🚀 Kasa koruma sistemi devrede!")
                        time.sleep(2)
                    except: pass
        time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
