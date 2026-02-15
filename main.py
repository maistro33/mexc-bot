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
        bal = ex.fetch_balance()
        return float(bal.get('total', {}).get('USDT', 0))
    except: return 0.0

# --- [OTONOM ANALİZ MOTORU] ---
def autonomous_decision(symbol):
    """Botun 'Bu işleme girmeye değer mi?' diye düşündüğü yer."""
    try:
        # 1. Veri Toplama (5M ve 1H)
        ohlcv_5m = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=24)
        
        closes_1h = [x[4] for x in ohlcv_1h]
        sma_1h = sum(closes_1h) / len(closes_1h)
        curr_p = closes_1h[-1]
        
        # Otonom Filtre: Aşırı oynaklık (volatilite) kontrolü
        volatility = np.std(closes_1h) / np.mean(closes_1h)
        if volatility > 0.07: # Çok hırçın piyasa, bot uzak durur
            return None
            
        # 2. SMC Strateji Kontrolü (Likidite Süpürme)
        lookback = ohlcv_5m[-40:-5]
        min_l = min([x[3] for x in lookback])
        max_h = max([x[2] for x in lookback])
        m2, m1 = ohlcv_5m[-2], ohlcv_5m[-1]
        
        # Bot Karar Veriyor: Long mu Short mu?
        if m2[3] < min_l and m1[4] > m2[2]: # Dipten dönüş
            if curr_p > sma_1h: # Sadece 1S trendi yukarıysa (Otonom Onay)
                return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        
        if m2[2] > max_h and m1[4] < m2[3]: # Tepeden dönüş
            if curr_p < sma_1h: # Sadece 1S trendi aşağıysa
                return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
                
        return None
    except:
        return None

# --- [İŞLEM VE KASA YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # Kârı Koruma (Dinamik Karar)
                if pnl >= 0.7 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kendi kararımla kârı kilitledim. Risk bitti!")

                # Pozisyon Kapatma
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    send_msg(f"🏁 **{symbol}**: Kararımı verdim ve pozisyonu kapattım.\nSonuç: %{pnl}")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

# --- [TÜM BORSAYI TARAYAN RADAR] ---
def radar_loop():
    send_msg("🕵️‍♂️ **Otonom Zihin Başlatıldı!**\nBorsadaki tüm fırsatları stratejimize göre süzüp kararlarımı kendim vereceğim.")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                # Botun analizi ve kararı
                decision = autonomous_decision(symbol)
                
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    
                    active_trades[symbol] = {'side': decision['side'], 'entry': price, 'amt': amt, 'sl': decision['sl'], 'pnl': 0}
                    send_msg(f"🧠 **KARAR VERDİM:** {symbol}\nAnalizim sonucunda kârlı bir fırsat gördüm ve işleme daldım! 🏹")
                
                time.sleep(0.05) # Hızlı tarama
        except:
            time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
