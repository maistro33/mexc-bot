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

# --- [KARAR MOTORU HAFIZASI] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_total_balance():
    try:
        # Bakiye çekme fonksiyonunu stabilize ettik
        bal = ex.fetch_balance()
        return float(bal.get('total', {}).get('USDT', 0))
    except: return 0.0

# --- [TELEGRAM KOMUTLARI - ÖNCELİKLİ] ---
@bot.message_handler(commands=['bakiye', 'durum', 'status'])
def handle_commands(message):
    try:
        current_bal = get_total_balance()
        txt = f"🕵️ **Otonom Rapor Hazır!**\n\n"
        txt += f"💰 **Kasa:** {round(current_bal, 2)} USDT\n"
        txt += f"🔥 **Aktif İşlemler:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
        
        if active_trades:
            for sym, t in active_trades.items():
                pnl = t.get('pnl', 0)
                txt += f"🔸 {sym}: %{pnl}\n"
        else:
            txt += "💤 Şu an yeni fırsatları süzüyorum."
            
        bot.reply_to(message, txt, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"⚠️ Rapor hazırlarken hata oluştu: {str(e)}")

# --- [OTONOM ANALİZ VE İŞLEM YÖNETİMİ] ---
# (autonomous_decision ve manage_trades fonksiyonları bir öncekiyle aynı kalacak)

def autonomous_decision(symbol):
    try:
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=24)
        closes_1h = [x[4] for x in ohlcv_1h]; sma_1h = sum(closes_1h)/len(closes_1h)
        lookback = ohlcv_5m[-40:-5]; min_l = min([x[3] for x in lookback]); max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        if m2[3] < min_l and m1[4] > m2[2] and m1[4] > sma_1h:
            return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        if m2[2] > max_h and m1[4] < m2[3] and m1[4] < sma_1h:
            return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
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
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                if pnl >= 0.8 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Karı kilitledim ortak!")

                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol}**: Pozisyonu kapattım. PNL: %{pnl}")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

def radar_loop():
    send_msg("🚀 **Otonom Zihin Aktif!**\nCOMP işlemini başlattım, şimdi listeyi taramaya devam ediyorum.")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                decision = autonomous_decision(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'pnl': 0}
                    send_msg(f"🧠 **KARAR VERDİM:** {symbol}\nKârlı bir fırsat gördüm ve işleme daldım! 🏹")
                time.sleep(0.1)
        except: time.sleep(30)

if __name__ == "__main__":
    # Komutları dinlemek için polling'i ana thread'de başlatıyoruz
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    
    # Botun mesajları duyması için polling en altta ve ana döngüde olmalı
    bot.infinity_polling()
