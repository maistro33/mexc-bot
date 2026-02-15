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

# --- [AYARLAR VE HAFIZA] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
consecutive_losses = 0   
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_total_balance():
    try:
        bal = ex.fetch_balance()
        # Bitget'te vadeli bakiye genellikle 'total' altındaki 'USDT'dir
        return float(bal.get('total', {}).get('USDT', 0))
    except: return 0.0

# --- [TELEGRAM KOMUTLARI - ARTIK ÇALIŞIYOR] ---
@bot.message_handler(commands=['bakiye', 'durum', 'status'])
def send_status(message):
    try:
        current_bal = get_total_balance()
        status_text = f"💰 **YAPAY ZEKA ANALİZ RAPORU**\n\n"
        status_text += f"💵 **Toplam Bakiye:** {round(current_bal, 2)} USDT\n"
        status_text += f"🧠 **Hata Payı Modu:** {'Temkinli 🛡️' if consecutive_losses > 0 else 'Normal 🦅'}\n"
        status_text += f"📊 **Aktif İşlemler:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
        status_text += "━━━━━━━━━━━━━━\n"
        
        if active_trades:
            for sym, t in active_trades.items():
                pnl = t.get('pnl', 0)
                icon = "🟢" if pnl >= 0 else "🔴"
                status_text += f"{icon} **{sym}** | PNL: %{pnl}\n"
        else:
            status_text += "😴 Şu an uygun fırsat bekliyorum."
            
        bot.reply_to(message, status_text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"⚠️ Hata: {str(e)}")

# --- [ZEKA KATMANI: PİYASA ANALİZİ] ---
def is_market_healthy(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        closes = [x[4] for x in ohlcv]
        volatility = np.std(closes) / np.mean(closes)
        
        if volatility > 0.05: return False, "Aşırı oynaklık."
        if volatility < 0.002: return False, "Durgun piyasa."
        return True, "Uygun."
    except: return False, "Veri hatası."

def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback]); min_l = min([x[3] for x in lookback])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # Zeka Faktörü: Kayıp varsa onayı zorlaştır
        confirm_mult = 1.002 if consecutive_losses > 1 else 1.0
        
        if m2[3] < min_l and m1[4] > m2[2] * confirm_mult and move_size >= 0.005:
            return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        if m2[2] > max_h and m1[4] < m2[3] / confirm_mult and move_size >= 0.005:
            return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
        return None
    except: return None

# --- [İŞLEM YÖNETİMİ] ---
def manage_trades():
    global active_trades, consecutive_losses
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                if pnl >= 0.8 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kar kilitlendi (BE+).")

                if pnl >= 1.2:
                    dist = 0.007 if pnl < 3 else 0.012
                    pot_sl = curr_p * (1 - dist) if t['side'] == 'long' else curr_p * (1 + dist)
                    if (t['side'] == 'long' and pot_sl > t['sl']) or (t['side'] == 'short' and pot_sl < t['sl']):
                        t['sl'] = pot_sl; t['trailing_active'] = True

                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    if pnl < 0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    send_msg(f"🏁 **{symbol} Kapandı.**\nPNL: %{pnl}\nBakiye: {get_total_balance()} USDT")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

def radar_loop():
    send_msg("🤖 **Yapay Zeka Karar Motoru Başladı!**\nKomutlar aktif: `/bakiye`, `/durum` yazabilirsin.")
    while True:
        try:
            if len(active_trades) < MAX_ACTIVE_TRADES:
                tickers = ex.fetch_tickers()
                pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x].get('quoteVolume', 0) or 0, reverse=True)[:60]
                for symbol in pairs:
                    if len(active_trades) >= MAX_ACTIVE_TRADES: break
                    if is_market_healthy(symbol)[0]:
                        sig = check_smc_signal(symbol)
                        if sig:
                            price = ex.fetch_ticker(symbol)['last']
                            amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                            ex.set_leverage(LEVERAGE, symbol)
                            ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                            active_trades[symbol] = {'side': sig['side'], 'entry': price, 'amt': amt, 'sl': sig['sl'], 'pnl': 0}
                            send_msg(f"🏹 **AV BAŞLADI:** {symbol}\nKendi kararımla işleme girdim.")
            time.sleep(15)
        except: time.sleep(20)

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    # ÖNEMLİ: Polling'i ayrı bir thread'de başlatıyoruz
    t1 = threading.Thread(target=lambda: bot.infinity_polling())
    t1.daemon = True
    t1.start()
    
    # İşlem yönetimini başlat
    t2 = threading.Thread(target=manage_trades)
    t2.daemon = True
    t2.start()
    
    # Radar ana döngüde çalışır
    radar_loop()
