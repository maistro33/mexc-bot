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

# --- [2. PROFESYONEL SMC AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,    # Senin istediğin giriş miktarı
    'leverage': 10,        # Risk yönetimi için 10x
    'tp_target': 0.045,    # %4.5 Kar (Kaliteli işlem meyvesi)
    'sl_target': 0.018,    # %1.8 Stop (Dar stop, yüksek R/R)
    'max_active_trades': 2, # Sadece en kaliteli 2 fırsat
    'vol_threshold': 1.8,  # Normalin 1.8 katı hacim (Para girişi şartı)
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. KESKİN NİŞANCI ANALİZ MOTORU] ---
def get_sniper_signal(symbol):
    try:
        # 5 Dakikalık mumlar: Sniper girişler için en dengeli zaman dilimi
        bars = ex.fetch_ohlcv(symbol, timeframe='5m', limit=40)
        o = [b[1] for b in bars] # Open
        h = [b[2] for b in bars] # High
        l = [b[3] for b in bars] # Low
        c = [b[4] for b in bars] # Close
        v = [b[5] for b in bars] # Volume
        
        # Likidite Bölgeleri (Son 30 mumun en yükseği ve en düşüğü)
        prev_high = max(h[-30:-1])
        prev_low = min(l[-30:-1])
        
        # Hacim Onayı (Kurumsal para girişi var mı?)
        avg_v = sum(v[-20:-1]) / 19
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])

        # --- [AYI TUZAĞI & BULLISH MSS (LONG)] ---
        # 1. Fiyat eski dibin altına iğne attı (Likidite süpürdü)
        # 2. AMA mumun gövdesi eski dibin ÜZERİNDE kapandı (Gövde Kapanış Onayı)
        # 3. Mevcut mum yeşil ve hacimli
        if vol_ok and l[-1] < prev_low and c[-1] > prev_low:
            if c[-1] > o[-1]: # Yeşil gövde
                return 'long'

        # --- [BOĞA TUZAĞI & BEARISH MSS (SHORT)] ---
        # 1. Fiyat eski tepenin üstüne iğne attı (Stopları patlattı)
        # 2. AMA mumun gövdesi eski tepenin ALTINDA kapandı (Manipülasyon Kalkanı)
        # 3. Mevcut mum kırmızı ve hacimli
        if vol_ok and h[-1] > prev_high and c[-1] < prev_high:
            if c[-1] < o[-1]: # Kırmızı gövde
                return 'short'

        return None
    except: return None

# --- [4. HAYALET TAKİP MOTORU] ---
def monitor(symbol, entry, amount, side):
    while symbol in active_trades:
        try:
            time.sleep(3)
            ticker = ex.fetch_ticker(symbol)
            curr = float(ticker['last'])
            
            # Kar Al ve Stop Seviyeleri (Hafızada gizli)
            tp = entry * (1 + CONFIG['tp_target']) if side == 'long' else entry * (1 - CONFIG['tp_target'])
            sl = entry * (1 - CONFIG['sl_target']) if side == 'long' else entry * (1 + CONFIG['sl_target'])
            
            hit_tp = (side == 'long' and curr >= tp) or (side == 'short' and curr <= tp)
            hit_sl = (side == 'long' and curr <= sl) or (side == 'short' and curr >= sl)

            if hit_tp or hit_sl:
                # Hedge Mod çıkış emri (Borsanın istediği formatta)
                exit_side = 'sell' if side == 'long' else 'buy'
                ex.create_order(symbol, 'market', exit_side, amount, params={'posSide': side})
                
                status = "💰 **KAR ALINDI**" if hit_tp else "🛑 **STOP OLUNDU**"
                send_msg(f"{status}\nKoin: {symbol}\nKâr/Zarar: %{CONFIG['tp_target']*100 if hit_tp else -CONFIG['sl_target']*100}")
                del active_trades[symbol]
                break
        except: break

# --- [5. ANA RADAR DÖNGÜSÜ] ---
def main_loop():
    send_msg("🎯 **SNIPER RADAR V36 AKTİF**\nSadece garantili SMC sinyalleri taranıyor...")
    while True:
        try:
            tickers = ex.fetch_tickers()
            # Saçma coinleri ele: Sadece hacmi yüksek ilk 100 coin
            symbols = sorted([s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']], 
                            key=lambda x: tickers[x]['quoteVolume'] if tickers[x]['quoteVolume'] else 0, reverse=True)[:100]
            
            for s in symbols:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal = get_sniper_signal(s)
                    if signal:
                        p = float(tickers[s]['last'])
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / p
                        try:
                            # İşlem Öncesi Son Hazırlık
                            ex.set_leverage(CONFIG['leverage'], s)
                            # Emir Gönderimi (Hedge Mode uyumlu)
                            side = 'buy' if signal == 'long' else 'sell'
                            ex.create_order(symbol=s, type='market', side=side, amount=amt, params={'posSide': signal})
                            
                            active_trades[s] = True
                            send_msg(f"🎯 **SNIPER GİRİŞİ YAPILDI!**\nKoin: {s}\nYön: {signal.upper()}\nAnaliz: Likidite Süpürme + Gövde Onayı")
                            threading.Thread(target=monitor, args=(s, p, amt, signal), daemon=True).start()
                        except: pass
                time.sleep(0.1)
            time.sleep(10)
        except: time.sleep(15)

# --- [6. TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Net Bakiye:** {usdt:.2f} USDT")
    except:
        bot.reply_to(message, "⚠️ Bakiye şu an çekilemedi.")

@bot.message_handler(commands=['durum'])
def get_status(message):
    bot.reply_to(message, f"📡 **Radar Durumu:** Aktif\n🎯 **Açık Sniper:** {len(active_trades)}")

if __name__ == "__main__":
    # Çakışma hatasını önlemek için (Conflict 409)
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
