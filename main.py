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
RR_RATIO = 2.0          
TP1_PERCENT = 0.8       
BE_PLUS_RATIO = 1.001   

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_free_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal['free']['USDT'])
    except: return 0.0

# --- [STRATEJİ MOTORU] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=60)
        recent = ohlcv[-25:-5]
        max_h = max([x[2] for x in recent])
        min_l = min([x[3] for x in recent])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        
        # Long
        if m2[3] < min_l and m1[4] > m2[2] and m1[3] > m3[2]:
            return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        # Short
        if m2[2] > max_h and m1[4] < m2[3] and m1[2] < m3[3]:
            return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        return None
    except: return None

# --- [İŞLEM VE TAKİP YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl

                # TP1 & Risk-Free
                if not t['tp1_done'] and pnl >= TP1_PERCENT:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'] * 0.5, params={'posSide': t['side'], 'reduceOnly': True})
                    active_trades[symbol].update({
                        'tp1_done': True, 'amt': t['amt'] * 0.5, 
                        'sl': t['entry'] * (BE_PLUS_RATIO if t['side'] == 'long' else (2 - BE_PLUS_RATIO))
                    })
                    send_msg(f"🛡️ **{symbol} TP1 ALINDI!**\nKârın yarısı kasada. Stop girişe çekildi, takip devam ediyor... 📈")

                # Çıkış Kontrolü
                hit_tp = (curr_p >= t['tp']) if t['side'] == 'long' else (curr_p <= t['tp'])
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])

                if hit_tp or hit_sl:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', active_trades[symbol]['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    res = "✅ HEDEF GELDİ" if hit_tp else "🛑 STOP/BE+ KAPANDI"
                    send_msg(f"🏁 **{symbol} {res}!**\nFinal PNL: %{pnl}")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(10)

# --- [RADAR VE RAPORLAMA] ---
def radar_loop():
    send_msg("🕵️ **SMC Ultimate Radar Yayında!**\n200 coin taranıyor, detaylı raporlama aktif.")
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
                        risk = abs(price - sig['sl'])
                        tp_price = price + (risk * RR_RATIO) if sig['side'] == 'long' else price - (risk * RR_RATIO)
                        
                        ex.set_leverage(LEVERAGE, symbol)
                        ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                        
                        active_trades[symbol] = {
                            'side': sig['side'], 'entry': price, 'amt': amt, 
                            'sl': sig['sl'], 'tp': tp_price, 'tp1_done': False, 'pnl': 0
                        }
                        
                        # Detaylı Giriş Mesajı (Dünkü gibi)
                        report = (f"🚀 **YENİ İŞLEM AÇILDI!**\n\n"
                                  f"💎 **Coin:** {symbol}\n"
                                  f"↕️ **Yön:** {sig['side'].upper()}\n"
                                  f"💰 **Giriş:** {round(price, 5)}\n"
                                  f"🎯 **Hedef (TP):** {round(tp_price, 5)}\n"
                                  f"🛡️ **Stop (SL):** {round(sig['sl'], 5)}\n"
                                  f"━━━━━━━━━━━━━━\n"
                                  f"🛰️ **Takip:** Sanal Takip Başlatıldı.")
                        send_msg(report)
                        time.sleep(2)
                    except: pass
        time.sleep(20)

@bot.message_handler(commands=['bakiye'])
def cmd_bakiye(m):
    b = get_free_balance()
    bot.reply_to(m, f"💰 **Kasa:** {round(b, 2)} USDT")

@bot.message_handler(commands=['durum'])
def cmd_durum(m):
    if not active_trades: bot.reply_to(m, "💤 Pusuya devam..."); return
    txt = "📊 **Aktif Avlar:**\n"
    for s, t in active_trades.items(): txt += f"\n🔹 {s} | {t['side'].upper()} | %{t['pnl']}"
    bot.reply_to(m, txt)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
