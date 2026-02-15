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

# --- [KARAR MOTORU AYARLARI] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
consecutive_losses = 0   # Botun kendi hatalarını takip etmesi için

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_total_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal['total']['USDT'])
    except: return 0.0

# --- [ZEKA KATMANI: PİYASA ANALİZİ] ---
def is_market_healthy(symbol):
    """Botun 'Şu an işlem yapmak mantıklı mı?' sorusuna cevap verdiği yer."""
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        closes = [x[4] for x in ohlcv]
        # Volatilite kontrolü (Standart Sapma)
        volatility = np.std(closes) / np.mean(closes)
        
        # Karar 1: Eğer piyasa aşırı durgunsa veya aşırı çalkantılıysa 'Girme' der.
        if volatility > 0.05: # Çok riskli/manipülatif ortam
            return False, "⚠️ Aşırı oynaklık var, risk almıyorum."
        if volatility < 0.002: # Çok ölü piyasa
            return False, "💤 Piyasa çok durgun, hacim bekliyorum."
            
        return True, "✅ Piyasa koşulları uygun."
    except: return False, "❌ Veri alınamadı."

# --- [SMC ANALİZ MOTORU - 5M] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback]); min_l = min([x[3] for x in lookback])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # Adaptif Onay: Eğer bot son zamanlarda kaybettiyse, m1[4] (kapanış) şartını daha sert ister.
        extra_confirm = 1.002 if consecutive_losses > 1 else 1.0
        
        if m2[3] < min_l and m1[4] > m2[2] * extra_confirm and move_size >= 0.005:
            if m1[3] > m3[2]: return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        if m2[2] > max_h and m1[4] < m2[3] / extra_confirm and move_size >= 0.005:
            if m1[2] < m3[3]: return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
        return None
    except: return None

# --- [İŞLEM VE KOMUT SİSTEMİ] ---
active_trades = {}

def manage_trades():
    global active_trades, consecutive_losses
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # Karar: Dinamik Koruma
                if pnl >= 0.7 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kârı kilitledim, gerisini piyasa düşünsün.")

                # Trailing
                if pnl >= 1.2:
                    dist = 0.007 if pnl < 3 else 0.012 # Kâr büyüdükçe nefes alanı bırak
                    pot_sl = curr_p * (1 - dist) if t['side'] == 'long' else curr_p * (1 + dist)
                    if (t['side'] == 'long' and pot_sl > t['sl']) or (t['side'] == 'short' and pot_sl < t['sl']):
                        t['sl'] = pot_sl; t['trailing_active'] = True

                # Kapanış
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    if pnl < 0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    send_msg(f"🏁 **{symbol} Kapandı.** PNL: %{pnl}\nKayıp Serisi: {consecutive_losses}")
                    del active_trades[symbol]
            time.sleep(6)
        except: time.sleep(10)

def radar_loop():
    send_msg("🦅 **Karar Veren Bot (Decision Engine) Aktif!**\nArtık sadece grafiklere değil, piyasanın sağlığına da bakıyorum.")
    while True:
        try:
            if len(active_trades) < MAX_ACTIVE_TRADES:
                tickers = ex.fetch_tickers()
                pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:60]
                for symbol in pairs:
                    if len(active_trades) >= MAX_ACTIVE_TRADES: break
                    
                    # KRİTİK KARAR ANI
                    healthy, reason = is_market_healthy(symbol)
                    if not healthy: continue 
                    
                    sig = check_smc_signal(symbol)
                    if sig:
                        price = ex.fetch_ticker(symbol)['last']
                        amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                        ex.set_leverage(LEVERAGE, symbol)
                        ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                        active_trades[symbol] = {'side': sig['side'], 'entry': price, 'amt': amt, 'sl': sig['sl'], 'pnl': 0}
                        send_msg(f"🏹 **AV BAŞLADI:** {symbol}\nKendi analizimle girmeye karar verdim! ✅")
            time.sleep(20)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=manage_trades).start()
    radar_loop()
