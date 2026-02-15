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

# --- [GLOBAL HAFIZA VE AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    
FIXED_ENTRY_USDT = 10    
consecutive_losses = 0   
active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: print("Telegram Hatası")

def get_total_balance():
    try:
        bal = ex.fetch_balance()
        return float(bal.get('total', {}).get('USDT', 0))
    except: return 0.0

# --- [ZEKA KATMANI: PİYASA VE TREND ANALİZİ] ---
def market_decision_engine(symbol):
    """Botun 'Bu coine girilir mi?' sorusuna verdiği uzman cevabı."""
    try:
        # 1. Büyük Resim Kontrolü (HTF)
        ohlcv_1h = ex.fetch_ohlcv(symbol, timeframe='1h', limit=30)
        ohlcv_4h = ex.fetch_ohlcv(symbol, timeframe='4h', limit=30)
        sma_1h = sum([x[4] for x in ohlcv_1h[-20:]]) / 20
        sma_4h = sum([x[4] for x in ohlcv_4h[-20:]]) / 20
        curr_p = ohlcv_1h[-1][4]
        
        # 2. Oynaklık (Volatilite) Kontrolü
        v_closes = [x[4] for x in ohlcv_1h]
        volatility = np.std(v_closes) / np.mean(v_closes)
        
        if volatility > 0.04: return "WAIT", "Piyasa çok hırçın, fırtınanın dinmesini bekliyorum."
        
        if curr_p > sma_1h and curr_p > sma_4h: bias = "LONG"
        elif curr_p < sma_1h and curr_p < sma_4h: bias = "SHORT"
        else: return "WAIT", "1S ve 4S trendleri çelişkili, kararsızım."
        
        return bias, "Trend onaylı, pusuya yatıyorum."
    except: return "WAIT", "Veri akışında sorun var."

# --- [SMC STRATEJİ MOTORU] ---
def check_smc_signal(symbol, bias):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback]); min_l = min([x[3] for x in lookback])
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # Boşluk (FVG) ve Sert Mum Kontrolü
        if bias == "LONG" and m2[3] < min_l and m1[4] > m2[2] and move_size >= 0.005:
            if m1[3] > m3[2]: return {'side': 'long', 'entry': m1[4], 'sl': m2[3]}
        if bias == "SHORT" and m2[2] > max_h and m1[4] < m2[3] and move_size >= 0.005:
            if m1[2] < m3[3]: return {'side': 'short', 'entry': m1[4], 'sl': m2[2]}
        return None
    except: return None

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye', 'durum'])
def send_status(message):
    bal = get_total_balance()
    txt = f"🕵️ **Ortak, İşte Son Rapor:**\n\n💰 **Kasa:** {round(bal, 2)} USDT\n🔥 **Aktif Avlar:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
    if active_trades:
        for s, t in active_trades.items():
            txt += f"\n🔸 {s}: %{t.get('pnl', 0)} ({'🛡️ Korumada' if t.get('be_active') else '🎯 Hedefte'})"
    bot.reply_to(message, txt)

# --- [İŞLEM VE KASA YÖNETİMİ] ---
def manage_trades():
    global active_trades, consecutive_losses
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # Komisyon Kalkanı (BE+)
                if pnl >= 0.8 and not t.get('be_active', False):
                    t['sl'] = t['entry'] * (1.002 if t['side'] == 'long' else 0.998)
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol}**: Kârı kilitledim. Artık bu işlemden zarar etmeyiz ortak!")

                # Dinamik Trailing (Zekice Takip)
                if pnl >= 1.2:
                    dist = 0.007 if pnl < 3 else 0.012 # Kâr arttıkça nefes alanı bırak
                    pot_sl = curr_p * (1 - dist) if t['side'] == 'long' else curr_p * (1 + dist)
                    if (t['side'] == 'long' and pot_sl > t['sl']) or (t['side'] == 'short' and pot_sl < t['sl']):
                        t['sl'] = pot_sl; t['trailing_active'] = True

                # Kapanış Şartı
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    if pnl < 0: consecutive_losses += 1
                    else: consecutive_losses = 0
                    send_msg(f"🏁 **{symbol} macerası bitti.**\nNet sonuç: %{pnl}\nGüncel bakiye: {round(get_total_balance(), 2)} USDT")
                    del active_trades[symbol]
            time.sleep(5)
        except: time.sleep(10)

# --- [RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg("🚀 **Yapay Zeka Ortak Göreve Başladı!**\nBüyük resme bakıp, en güvenli avları senin için seçeceğim. Yolumuz açık olsun!")
    while True:
        try:
            if len(active_trades) < MAX_ACTIVE_TRADES:
                tickers = ex.fetch_tickers()
                # En yüksek hacimli 60 coini süzgece al
                pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x].get('quoteVolume', 0) or 0, reverse=True)[:60]
                
                for symbol in pairs:
                    if len(active_trades) >= MAX_ACTIVE_TRADES: break
                    if symbol in active_trades: continue
                    
                    bias, reason = market_decision_engine(symbol)
                    if bias in ["LONG", "SHORT"]:
                        sig = check_smc_signal(symbol, bias)
                        if sig:
                            # Giriş İşlemi
                            price = ex.fetch_ticker(symbol)['last']
                            amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                            ex.set_leverage(LEVERAGE, symbol)
                            ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                            active_trades[symbol] = {'side': sig['side'], 'entry': price, 'amt': amt, 'sl': sig['sl'], 'pnl': 0}
                            send_msg(f"🏹 **YENİ AV YAKALADIM!**\n\n**Coin:** {symbol}\n**Neden:** {reason}\n**Miktar:** 10 USDT\n🛡️ Arkana yaslan, ben takipteyim.")
            time.sleep(20)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(30)

# --- [BAŞLATICI] ---
if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    threading.Thread(target=manage_trades).start()
    radar_loop()
