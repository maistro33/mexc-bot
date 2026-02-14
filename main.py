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

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp_target': 0.035, 
    'sl_target': 0.018, 
    'max_active_trades': 3,
    'vol_threshold': 1.4,
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. ANALİZ MOTORU] ---
def get_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        c, l, h, v = [b[4] for b in bars], [b[3] for b in bars], [b[2] for b in bars], [b[5] for b in bars]
        avg_v = sum(v[-10:-1]) / 9
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])
        long_setup = l[-1] < min(l[-20:-5]) and c[-1] > max(c[-5:-1])
        short_setup = h[-1] > max(h[-20:-5]) and c[-1] < min(c[-5:-1])
        if vol_ok and long_setup: return 'long'
        if vol_ok and short_setup: return 'short'
        return None
    except: return None

# --- [4. TEST İŞLEMİ (PARAMETRESİZ SAF EMİR)] ---
def run_startup_test():
    try:
        symbol = 'DOGE/USDT:USDT'
        ticker = ex.fetch_ticker(symbol)
        p = float(ticker['last'])
        amt = (10.0 * CONFIG['leverage']) / p
        
        ex.set_leverage(CONFIG['leverage'], symbol)
        
        # 40774 HATASI İÇİN SON ÇARE:
        # Tüm opsiyonel parametreleri (posSide, tdMode vb.) sildik.
        # Borsa emri senin paneldeki 'Tek Yönlü' ayarına göre KENDİ açacak.
        ex.create_order(symbol, 'market', 'buy', amt)
        
        send_msg(f"🧪 **TEST BAŞARILI!**\nDeneme İşlemi Açıldı: {symbol}")
    except Exception as e:
        send_msg(f"❌ Test Hatası: {e}\n⚠️ Eğer hala olmuyorsa: Bitget uygulamasında 'İşlem Tercihleri' kısmından Pozisyon Modunu bir kez 'Hedge' yapıp sonra tekrar 'Tek Yönlü' yapmayı dene.")

# --- [5. ANA DÖNGÜ] ---
def main_loop():
    send_msg("🚀 **RADAR V34 AKTİF**\nParametresiz saf emir modu devrede.")
    run_startup_test()
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = [s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']]
            for s in symbols[:150]:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal = get_signal(s)
                    if signal:
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            # Gerçek işlemlerde de parametresiz gönderiyoruz
                            ex.create_order(s, 'market', 'buy' if signal == 'long' else 'sell', amt)
                            active_trades[s] = True
                            send_msg(f"🔥 **İŞLEM AÇILDI!**\nKoin: {s}\nYön: {signal.upper()}")
                        except: pass
                time.sleep(0.05)
            time.sleep(10)
        except: time.sleep(15)

# --- [6. KOMUTLAR] ---
@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, f"📡 Radar Aktif\n📈 Aktif İşlem: {len(active_trades)}")

@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Net Bakiye:** {usdt:.2f} USDT")
    except:
        bot.reply_to(message, "⚠️ Bakiye çekilemedi.")

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
