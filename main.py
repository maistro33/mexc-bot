import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
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

# --- [2. AYARLAR & PANEL] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # TP1'de %75 kapanış kuralı
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'rr_target': 1.3,            # Scalp için hızlı hedef
    'timeframe': '5m'            # 5 Dakikalık scalp modu
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        if precision < 1:
            step = int(-math.log10(precision))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. SMC STRATEJİ MOTORU] ---
def analyze_smc_strategy(symbol):
    try:
        # Zaman Filtresi: Mum kapanışına çok yakınsa girme
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # A. Likidite Alımı (Stop Patlatma İğnesi)
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low
        
        # B. MSS & Gövde Kapanış (Anti-Manipülasyon)
        recent_high = max(h[-8:-1])
        mss_ok = c[-1] > recent_high 
        
        # C. Hacim Onaylı Kırılım
        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.2)
        
        if liq_taken and mss_ok and vol_ok:
            # Scalp için Stop: Son 5 mumun en düşüğü
            entry_price = c[-1]
            stop_loss = min(l[-5:])
            if stop_loss >= entry_price: stop_loss = entry_price * 0.995 # Emniyet kemeri
            return 'LONG', entry_price, stop_loss, "SCALP_MSS_ONAY"
            
        return None, None, None, None
    except: return None, None, None, None

# --- [4. POZİSYON VE STOP-TP YÖNETİMİ] ---
def monitor_trade(symbol, entry, stop, tp1, amount):
    stage = 0 
    price_step = 1.0 / (amount / CONFIG['leverage']) 
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- TP1 NOKTASI: %75 KAPAT VE STOPU GİRİŞE ÇEK ---
            if stage == 0 and price >= tp1:
                # 1. Bekleyen limit TP ve Stop emirlerini iptal et
                ex.cancel_all_orders(symbol)
                time.sleep(1)
                
                # 2. Kalan miktarı bul ve stopu girişe (Entry) çek
                pos = ex.fetch_positions([symbol])
                if pos and float(pos[0]['contracts']) > 0:
                    rem_qty = round_amount(symbol, float(pos[0]['contracts']))
                    # Stop Girişe (Break Even)
                    ex.create_order(symbol, 'trigger_market', 'sell', rem_qty, params={'stopPrice': entry, 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"✅ **{symbol} TP1 ALINDI!**\nPozisyonun %75'i kapandı.\nKalanlar için Stop girişe ({entry}) çekildi. Artık risk sıfır!")
                    stage = 1

            # --- TP2 & TP3: HER +1 USDT KARDA KASAYA EKLEME ---
            elif stage in [1, 2] and price >= (tp1 + (price_step * stage)):
                sell_qty = round_amount(symbol, (1.0 * CONFIG['leverage']) / price)
                ex.create_market_order(symbol, 'sell', sell_qty, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"💰 **{symbol} TP{stage+1}:** 1 USDT daha kasaya atıldı. Stop girişte bekliyor.")
                stage += 1

            # Pozisyonun kapanıp kapanmadığını kontrol et
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) <= 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 **{symbol} İşlemi Tamamlandı.**")
                break
                
            time.sleep(10)
        except Exception as e:
            time.sleep(5)

# --- [5. TELEGRAM KOMUTLARI] ---

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 **Cüzdan Bakiyesi:** {bal['total']['USDT']:.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades:
        bot.reply_to(message, "📡 Radar çalışıyor... Şu an stratejiye %100 uyan bir scalp fırsatı yok.")
    else:
        msg = "📊 **Aktif Pozisyonlar:**\n"
        for s in active_trades.keys():
            ticker = ex.fetch_ticker(s)
            msg += f"🔹 {s} | Fiyat: {ticker['last']}\n"
        bot.reply_to(message, msg)

# --- [6. İCRA VE ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 **BOT BAŞLADI (SCALP MODU)**\nZaman: 5m\nKalkanlar: AKTİF\nKademeli Kar Al: AKTİF")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, fvg_type = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    # Emir Parametreleri
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    tp1_price = entry + ((entry - stop) * CONFIG['rr_target'])

                    # 1. Market Alış
                    ex.create_market_order(sym, 'buy', amount)
                    active_trades[sym] = True
                    
                    # 2. Ana Stop Loss (Borsaya iletilir)
                    ex.create_order(sym, 'trigger_market', 'sell', amount, params={'stopPrice': stop, 'reduceOnly': True})
                    
                    # 3. TP1 Limit Satış (%75)
                    tp1_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'limit', 'sell', tp1_qty, tp1_price, {'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **YENİ SCALP İŞLEMİ**\nKoin: {sym}\nGiriş: {entry:.4f}\nTP1: {tp1_price:.4f}\nStop: {stop:.4f}\n\n%75 Kar Alınca Stop Girişe Çekilecek.")
                    
                    threading.Thread(target=monitor_trade, args=(sym, entry, stop, tp1_price, amount), daemon=True).start()
                
                time.sleep(0.05)
            time.sleep(60) 
        except: time.sleep(10)

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
