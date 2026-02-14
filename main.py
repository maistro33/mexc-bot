import ccxt
import time
import telebot
import os
import threading

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. SERT SMC AYARLARI] ---
CONFIG = {
    'entry_usdt': 10.0,    # Sabit 10 USDT
    'leverage': 10,
    'rr_ratio': 2.0,       # 1:2 Hedef Oranı
    'sl_pct': 0.015,       # %1.5 Stop
    'vol_threshold': 2.2,  # Displacement için hacim şartı
    'max_active_trades': 1,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']
}

# --- [3. YARDIMCI FONKSİYONLAR] ---
def send_msg(text):
    """Log hatasını önlemek için en üstte tanımlandı"""
    try: 
        bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Mesaj gönderme hatası: {e}")

# --- [4. RESİMDEKİ SMC MOTORU] ---
def get_smc_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        h, l, c, v, o = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars], [b[1] for b in bars]
        
        # Likidite Süpürme (Sweep)
        prev_high, prev_low = max(h[-40:-5]), min(l[-40:-5])
        avg_v = sum(v[-20:-5]) / 15
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])

        # SHORT: Tepe süpürüldü, sert hacimli düşüş (MSS)
        if vol_ok and h[-2] > prev_high and c[-1] < prev_low:
            return 'short', c[-1]

        # LONG: Dip süpürüldü, sert hacimli yükseliş (MSS)
        if vol_ok and l[-2] < prev_low and c[-1] > prev_high:
            return 'long', c[-1]

        return None, None
    except: return None, None

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **V40 SMC PRO YÜKLENDİ**\nLog hatası giderildi, sniper pusuya yattı.")
    while True:
        try:
            # Sadece en hacimli koinleri tara
            tickers = ex.fetch_tickers()
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']], 
                            key=lambda x: tickers[x]['quoteVolume'] if tickers[x]['quoteVolume'] else 0, reverse=True)[:50]
            
            # Açık pozisyon kontrolü
            pos = ex.fetch_positions()
            active = [p['symbol'] for p in pos if float(p['contracts']) > 0]

            if len(active) < CONFIG['max_active_trades']:
                for s in symbols:
                    signal, price = get_smc_signal(s)
                    if signal and s not in active:
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
                        sl = price * (1 + CONFIG['sl_pct']) if signal == 'short' else price * (1 - CONFIG['sl_pct'])
                        tp = price * (1 - (CONFIG['sl_pct'] * CONFIG['rr_ratio'])) if signal == 'short' else price * (1 + (CONFIG['sl_pct'] * CONFIG['rr_ratio']))

                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            # Market Giriş
                            ex.create_order(s, 'market', 'sell' if signal == 'short' else 'buy', amt, params={'posSide': signal})
                            # Hard Stop ve TP
                            ex.create_order(s, 'market', 'buy' if signal == 'short' else 'sell', amt, 
                                            params={'posSide': signal, 'stopLossPrice': sl, 'takeProfitPrice': tp})
                            
                            send_msg(f"🎯 **SMC SNIPER GİRİŞ!**\nKoin: {s}\nYön: {signal.upper()}\n💰 Giriş: {price}\n🛑 SL: {sl:.4f}\n✅ TP: {tp:.4f}")
                            break 
                        except: pass
            time.sleep(20)
        except: time.sleep(30)

# --- [6. KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Bakiye:** {usdt:.2f} USDT")
    except: bot.reply_to(message, "API Hatası.")

@bot.message_handler(commands=['durum'])
def cmd_status(message):
    try:
        pos = ex.fetch_positions()
        active = [p['symbol'] for p in pos if float(p['contracts']) > 0]
        bot.reply_to(message, f"🟢 Aktif İşlem: {active if active else 'Yok'}")
    except: bot.reply_to(message, "Durum Hatası.")

if __name__ == "__main__":
    # Döngüyü başlat
    t = threading.Thread(target=main_loop)
    t.daemon = True
    t.start()
    bot.infinity_polling()
