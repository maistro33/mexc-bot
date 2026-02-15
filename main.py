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

# --- [STRATEJİ AYARLARI] ---
ENTRY_USDT = 10.0       # Her işlem girişi
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3   # Aynı anda 3 farklı coin
TP1_PERCENT = 1.2       # %1.2 karda yarısını sat
TRAILING_DIST = 0.008   # %0.8 Sıkı takip mesafesi
BE_PLUS = 1.002         # Girişin %0.20 üstü (Risk-Free)

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

# --- [SİNYAL MOTORU: MSS + HACİM + BODY CLOSE] ---
def check_signals(symbol):
    try:
        if symbol in active_trades: return None
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        if len(ohlcv) < 30: return None
        
        # Gövde ve Hacim Analizi
        last = ohlcv[-1] # [zam, aç, yü, dü, kap, hac]
        prev = ohlcv[-2]
        past_20 = ohlcv[-21:-1]
        
        curr_close = last[4]
        curr_vol = last[5]
        avg_vol = sum(x[5] for x in past_20) / 20
        
        max_high = max(x[2] for x in past_20)
        min_low = min(x[3] for x in past_20)

        # Anti-Manipülasyon Filtresi
        if curr_close > max_high and curr_vol > (avg_vol * 1.5):
            return 'long'
        elif curr_close < min_low and curr_vol > (avg_vol * 1.5):
            return 'short'
        return None
    except: return None

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def show_bal(m):
    try:
        b = ex.fetch_balance()['total']['USDT']
        bot.reply_to(m, f"💰 **Kasa:** {round(b, 2)} USDT\n📡 Aktif İşlem: {len(active_trades)}")
    except: pass

@bot.message_handler(commands=['durum'])
def show_status(m):
    if not active_trades:
        bot.reply_to(m, "💤 Borsa taranıyor, henüz onaylı sinyal yok.")
        return
    rep = "📊 **Radar Durumu:**\n"
    for s, t in active_trades.items():
        rep += f"\n🔸 {s} | {t['side'].upper()} | PNL: %{t['pnl']}"
    bot.reply_to(m, rep)

# --- [İŞLEM YÖNETİMİ] ---
def manage_loop():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                
                # PNL Hesapla
                diff = (curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)
                pnl = round((diff / t['entry']) * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl

                # TP1 ve Risk-Free Onayı
                if not t['tp1_done'] and pnl >= TP1_PERCENT:
                    side_close = 'sell' if t['side'] == 'long' else 'buy'
                    ex.create_order(symbol, 'market', side_close, t['amt'] * 0.5, params={'posSide': t['side'], 'reduceOnly': True})
                    active_trades[symbol]['tp1_done'] = True
                    active_trades[symbol]['amt'] *= 0.5
                    # Stopu BE+'ya çek
                    active_trades[symbol]['trailing_sl'] = t['entry'] * (BE_PLUS if t['side'] == 'long' else (2 - BE_PLUS))
                    send_msg(f"✅ **{symbol} TP1 ALINDI!**\nKârın %50'si kasada. Stop girişe (BE+) çekildi. Bu işlem artık RİSKSİZ! 🛡️")

                # Trailing Güncelleme (Sıkı Takip)
                if t['tp1_done']:
                    if t['side'] == 'long':
                        new_sl = curr_p * (1 - TRAILING_DIST)
                        if new_sl > t['trailing_sl']: 
                            active_trades[symbol]['trailing_sl'] = round(new_sl, 6)
                            send_msg(f"🔄 **{symbol} Trailing Yükseldi:** {active_trades[symbol]['trailing_sl']}")
                    else:
                        new_sl = curr_p * (1 + TRAILING_DIST)
                        if new_sl < t['trailing_sl']: 
                            active_trades[symbol]['trailing_sl'] = round(new_sl, 6)
                            send_msg(f"🔄 **{symbol} Trailing Düştü:** {active_trades[symbol]['trailing_sl']}")

                # Stop/Exit Kontrolü
                exit_now = (curr_p <= t['trailing_sl']) if t['side'] == 'long' else (curr_p >= t['trailing_sl'])
                if exit_now:
                    side_close = 'sell' if t['side'] == 'long' else 'buy'
                    ex.create_order(symbol, 'market', side_close, active_trades[symbol]['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol} Kapatıldı.**\nSon PNL: %{pnl}\nKasa bir sonraki av için hazır! 💰")
                    del active_trades[symbol]
            
            time.sleep(5)
        except: time.sleep(5)

def radar_loop():
    send_msg("📡 **Geveze Radar V4 Başlatıldı!**\nBütün borsa 7/24 taranıyor. Manipülasyon kalkanları devrede.")
    while True:
        if len(active_trades) < MAX_ACTIVE_TRADES:
            tickers = ex.fetch_tickers()
            pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:200]
            
            for symbol in pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                sig = check_signals(symbol)
                if sig:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if sig=='long' else 'sell', amt, params={'posSide': 'long' if sig=='long' else 'short'})
                    
                    active_trades[symbol] = {
                        'side': 'long' if sig=='long' else 'short', 'entry': price, 
                        'amt': amt, 'tp1_done': False, 'pnl': 0, 
                        'trailing_sl': price * (0.985 if sig=='long' else 1.015)
                    }
                    send_msg(f"🚀 **FIRSAT BULUNDU!**\n💎 Coin: {symbol}\n📈 Yön: {sig.upper()}\n📊 Giriş: {price}\nHacim ve Gövde onayı alındı! 🛡️")
                    time.sleep(2)
        time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_loop).start()
    radar_loop()
