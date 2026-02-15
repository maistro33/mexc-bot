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

# --- [STRATEJİ VE KARTOPU AYARLARI] ---
BASE_ENTRY_USDT = 10.0   
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 4    # Geniş tarama olduğu için aynı anda 4 işleme izin veriyoruz
RR_RATIO = 2.0          # 1:2 Risk-Ödül
TP1_PERCENT = 0.8       # %0.8 karda Risk-Free (Kasa Koruma)
BE_PLUS_RATIO = 1.001   

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_current_balance():
    try: return float(ex.fetch_balance()['total']['USDT'])
    except: return 0.0

# --- [SMC MOTORU: LİKİDİTE + FVG + ONAY] ---
def check_smc_signal(symbol):
    try:
        if symbol in active_trades: return None
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=60)
        if len(ohlcv) < 50: return None
        
        # Likidite Bölgesi (Son 25 mum)
        recent = ohlcv[-25:-5]
        max_h = max([x[2] for x in recent])
        min_l = min([x[3] for x in recent])
        
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        
        # LONG: Likidite süpürüldü ve sert displacement (FVG oluşumu)
        if m2[3] < min_l and m1[4] > m2[2]:
            if m1[3] > m3[2]: # Bullish FVG
                fvg_mid = (m1[3] + m3[2]) / 2
                return {'side': 'long', 'entry': fvg_mid, 'sl': m2[3]}

        # SHORT: Likidite süpürüldü ve sert aşağı kırılım
        if m2[2] > max_h and m1[4] < m2[3]:
            if m1[2] < m3[3]: # Bearish FVG
                fvg_mid = (m1[2] + m3[3]) / 2
                return {'side': 'short', 'entry': fvg_mid, 'sl': m2[2]}
                
        return None
    except: return None

# --- [TELEGRAM GEVEZE MODU] ---
@bot.message_handler(commands=['bakiye'])
def cmd_bakiye(m):
    b = get_current_balance()
    bot.reply_to(m, f"💰 **Kartopu Kasası:** {round(b, 2)} USDT")

@bot.message_handler(commands=['durum'])
def cmd_durum(m):
    if not active_trades:
        bot.reply_to(m, "📡 200 coin taranıyor, SMC yapısı bekleniyor...")
        return
    txt = "📊 **Aktif Avlar:**\n"
    for s, t in active_trades.items():
        txt += f"\n🔹 {s} | {t['side'].upper()} | PNL: %{t['pnl']}"
    bot.reply_to(m, txt)

# --- [İŞLEM YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                ticker = ex.fetch_ticker(symbol)
                curr_p = ticker['last']
                
                diff = (curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)
                pnl = round((diff / t['entry']) * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl

                # 1. Hızlı TP1 (Sermaye Kalkanı)
                if not t['tp1_done'] and pnl >= TP1_PERCENT:
                    side_close = 'sell' if t['side'] == 'long' else 'buy'
                    ex.create_order(symbol, 'market', side_close, t['amt'] * 0.5, params={'posSide': t['side'], 'reduceOnly': True})
                    active_trades[symbol]['tp1_done'] = True
                    active_trades[symbol]['amt'] *= 0.5
                    active_trades[symbol]['sl'] = t['entry'] * (BE_PLUS_RATIO if t['side'] == 'long' else (2 - BE_PLUS_RATIO))
                    send_msg(f"✅ **{symbol} TP1 ALINDI!**\nKalan miktar için stop girişe çekildi. 🛡️")

                # 2. Final Çıkış (RR 1:2)
                hit_tp = (curr_p >= t['tp']) if t['side'] == 'long' else (curr_p <= t['tp'])
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])

                if hit_tp or hit_sl:
                    side_close = 'sell' if t['side'] == 'long' else 'buy'
                    ex.create_order(symbol, 'market', side_close, active_trades[symbol]['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    msg = "🎯 HEDEF VURULDU" if hit_tp else "🛡️ STOP/BE+ KAPANDI"
                    send_msg(f"🏁 **{symbol} {msg}!**\nPNL: %{pnl}")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(5)

# --- [GENİŞ RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg("🕵️ **SMC 200 COIN RADARI AKTİF!**\nLikidite + FVG stratejisiyle tüm borsa taranıyor.")
    while True:
        if len(active_trades) < MAX_ACTIVE_TRADES:
            tickers = ex.fetch_tickers()
            # En yüksek hacimli 200 coini listeler
            pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:200]
            
            for symbol in pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                sig = check_smc_signal(symbol)
                if sig:
                    kasa = get_current_balance()
                    # Kartopu: Kasa büyüdükçe giriş de büyür (Kasanın 1/5'i)
                    trade_size = max(BASE_ENTRY_USDT, kasa / 5)
                    
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (trade_size * LEVERAGE) / price
                    
                    # 1:2 RR Hesapla
                    risk = abs(price - sig['sl'])
                    tp_price = price + (risk * RR_RATIO) if sig['side'] == 'long' else price - (risk * RR_RATIO)
                    
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                    
                    active_trades[symbol] = {
                        'side': sig['side'], 'entry': price, 'amt': amt, 
                        'sl': sig['sl'], 'tp': tp_price, 'tp1_done': False, 'pnl': 0
                    }
                    send_msg(f"🚀 **SMC SİNYALİ BULUNDU!**\n💎 {symbol}\n📊 Giriş: {round(price, 5)}\n🛡️ Stop: {round(sig['sl'], 5)}\n🏁 Hedef: {round(tp_price, 5)}")
                    time.sleep(2)
        time.sleep(15) # Taramayı hızlandırdım

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
