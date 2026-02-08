import ccxt
import telebot
import time
import os
import threading

# --- [BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [STRATEJİ AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 15.0,      # Kalan 72 USDT bakiyeyi korumak için
    'leverage': 10,
    'tp1_ratio': 0.75,              # Sizin %75 Kar Al kuralınız
    'rr_ratio': 2.0                 # 1:2 Risk Ödül Oranı
}

active_trades = {}

def get_mtf_trend(symbol):
    """1 Günlük ve 4 Saatlik Trend Onayı"""
    try:
        d1 = ex.fetch_ohlcv(symbol, timeframe='1d', limit=20)
        h4 = ex.fetch_ohlcv(symbol, timeframe='4h', limit=20)
        d1_trend = "UP" if d1[-1][4] > sum([b[4] for b in d1])/20 else "DOWN"
        h4_trend = "UP" if h4[-1][4] > sum([b[4] for b in h4])/20 else "DOWN"
        return d1_trend, h4_trend
    except: return "UNKNOWN", "UNKNOWN"

def get_smc_analysis(symbol):
    try:
        d1_t, h4_t = get_mtf_trend(symbol)
        if d1_t != "UP" or h4_t != "UP": return None, None, None # Sadece Trend Yönüne!

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1. Önemli Likidite Seviyesi Alınacak
        liq_taken = l[-1] < min(l[-20:-1]) and c[-1] > min(l[-20:-1])
        
        # 2. Ters Yöne Displacement (Sert Hacim)
        vol_ok = v[-1] > (sum(v[-20:])/20 * 1.8)

        # 3. Market Yapısının Değişmesi (MSS - Gövde Kapanışı)
        recent_high = max(h[-15:-1])
        mss_ok = c[-1] > recent_high

        # 4. FVG Tespiti ve Giriş Noktası
        fvg_detected = h[-3] < l[-1]
        entry_price = h[-3] # FVG başlangıcı giriş seviyemiz

        if liq_taken and vol_ok and mss_ok and fvg_detected:
            # Fiyat FVG'ye geri dönerse gir
            if c[-1] <= entry_price * 1.002:
                stop_loss = min(l[-5:]) # En son swing noktası
                return 'buy', entry_price, stop_loss
        return None, None, None
    except: return None, None, None

def execute_trade(symbol, side, entry, stop):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / entry
        
        # 1:2 RR Hesaplama
        risk = entry - stop
        tp1 = entry + (risk * 1.5) # Güvenli çıkış
        tp2 = entry + (risk * 2.0) # 1:2 RR Hedefi

        bot.send_message(MY_CHAT_ID, f"🎯 **STRATEJİ ONAYLANDI: {symbol}**\n📍 Giriş: {entry}\n🛡️ Stop: {stop}\n🎯 Hedef: 1:2 RR")
        
        # Giriş Emri
        ex.create_limit_buy_order(symbol, amount, entry)
        time.sleep(2)

        # STOP ve TP (Bitget Garantili Trigger Limit)
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        ex.create_order(symbol, 'limit', 'sell', amount * CONFIG['tp1_ratio'], tp1, {'reduceOnly': True})
        ex.create_order(symbol, 'limit', 'sell', amount * (1-CONFIG['tp1_ratio']), tp2, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, "✅ **TÜM EMİRLER VE STOPLAR DİZİLDİ.**")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Dizme Hatası: {str(e)}")

def main_worker():
    bot.send_message(MY_CHAT_ID, "🦅 **SADIK BEY ÖZEL: STRATEJİ MUHAFIZI BAŞLADI**")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols[:15]: # En hacimli 15 pariteye odaklan (Hız ve doğruluk için)
                signal, entry, stop = get_smc_analysis(sym)
                if signal and sym not in active_trades:
                    execute_trade(sym, signal, entry, stop)
                time.sleep(0.5)
            
            # Hayattayım Mesajı (15 Dakikada bir)
            bot.send_message(MY_CHAT_ID, f"📡 Tarama Tamamlandı. Aktif Takip: {len(active_trades)}")
            time.sleep(600)
        except: time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker, daemon=True)
    t.start()
    bot.infinity_polling()
