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

# --- [AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3   
TRAIL_ACTIVATE_PNL = 0.8  # Takip %0.8 kârda başlar
TRAIL_DISTANCE = 0.005     # Fiyatı %0.5 geriden takip eder (Esneklik payı)
BE_COMMISSION_OFFSET = 0.0015 # Komisyon kalkanı

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_free_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal['free']['USDT'])
    except: return 0.0

# --- [SMC MOTORU] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=60)
        recent = ohlcv[-25:-5]
        max_h = max([x[2] for x in recent])
        min_l = min([x[3] for x in recent])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        
        if m2[3] < min_l and m1[4] > m2[2] and m1[3] > m3[2]:
            return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        if m2[2] > max_h and m1[4] < m2[3] and m1[2] < m3[3]:
            return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        return None
    except: return None

# --- [GERÇEK TRAILING YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl

                # 1. Trailing Aktivasyonu ve Stop Güncelleme
                if pnl >= TRAIL_ACTIVATE_PNL:
                    if t['side'] == 'long':
                        potential_sl = curr_p * (1 - TRAIL_DISTANCE)
                        # Stopu sadece yukarı taşır, asla aşağı çekmez
                        if potential_sl > t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            if not t['trailing_active']:
                                active_trades[symbol]['trailing_active'] = True
                                send_msg(f"🏃 **{symbol} TAKİP BAŞLADI!**\nFiyat yükseldikçe stop arkasından gelecek. Hedef sınırı kaldırıldı.")
                    else: # Short
                        potential_sl = curr_p * (1 + TRAIL_DISTANCE)
                        if potential_sl < t['sl']:
                            active_trades[symbol]['sl'] = potential_sl
                            if not t['trailing_active']:
                                active_trades[symbol]['trailing_active'] = True
                                send_msg(f"🏃 **{symbol} TAKİP BAŞLADI!**")

                # 2. Stop Kapanış Kontrolü
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])

                if hit_sl:
                    side_close = 'sell' if t['side'] == 'long' else 'buy'
                    ex.create_order(symbol, 'market', side_close, t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    
                    status = "🛡️ TRAILING STOP KAPANDI" if t['trailing_active'] else "🛑 STOPLANDI"
                    send_msg(f"🏁 **{symbol} KAPATILDI**\nSonuç: {status}\nFinal PNL: %{pnl}\nKasa süpürüldü. ✅")
                    del active_trades[symbol]
            time.sleep(8) # Daha sık kontrol
        except: time.sleep(8)

# --- [RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg("🕵️ **SMC Gerçek Trailing Radar Aktif!**\nSınır yok, fiyat nereye stop oraya.")
    while True:
        if len(active_trades) < MAX_ACTIVE_TRADES:
            tickers = ex.fetch_tickers()
            pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:200]
            
            for symbol in pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                sig = check_smc_signal(symbol)
                if sig:
                    free_bal = get_free_balance()
                    entry_usdt = free_bal * 0.2 
                    if entry_usdt < 5: continue 
                    
                    try:
                        price = ex.fetch_ticker(symbol)['last']
                        amt = (entry_usdt * LEVERAGE) / price
                        
                        ex.set_leverage(LEVERAGE, symbol)
                        ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                        
                        active_trades[symbol] = {
                            'side': sig['side'], 'entry': price, 'amt': amt, 
                            'sl': sig['sl'], 'trailing_active': False, 'pnl': 0
                        }
                        
                        report = (f"🚀 **YENİ AV BAŞLADI!**\n\n"
                                  f"💎 **Coin:** {symbol}\n"
                                  f"💰 **Giriş:** {round(price, 5)}\n"
                                  f"🛡️ **İlk SL:** {round(sig['sl'], 5)}\n"
                                  f"━━━━━━━━━━━━━━\n"
                                  f"🏃 **Mod:** Gerçek Trailing (Sınırsız Takip)")
                        send_msg(report)
                        time.sleep(2)
                    except: pass
        time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
