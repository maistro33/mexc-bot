import ccxt
import telebot
import time
import os
import threading

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

# --- [2. AYARLAR - SADIK BEY ÖZEL] ---
CONFIG = {
    'leverage': 10,
    'tp1_ratio': 0.75,          # İlk hedefte %75 Kar Al
    'max_active_trades': 4,      # Risk yönetimi
    'min_volume_24h': 10_000_000 # En az 10M$ hacimli (Likit) coinler
}

active_trades = {}

# --- [3. YARDIMCI FONKSİYONLAR] ---
def get_balance():
    """72 USDT bakiyeyi korumak için otomatik miktar ayarlar."""
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        free = float(bal['USDT']['free'])
        # Bakiyeyi 4'e böl (Örn: 72/4 = 18 USDT giriş)
        return free / 4 if free > 15 else 10
    except: return 0

def check_mtf_trend(symbol):
    """1G, 4S ve 1S Trend Onayı (En büyük balina koruması)"""
    try:
        for tf in ['1d', '4h', '1h']:
            bars = ex.fetch_ohlcv(symbol, timeframe=tf, limit=20)
            closes = [b[4] for b in bars]
            ma = sum(closes) / len(closes)
            if closes[-1] <= ma: # Eğer fiyat ortalamanın altındaysa LONG girmek intihardır.
                return False
        return True
    except: return False

# --- [4. STRATEJİ MOTORU (SMC + FVG)] ---
def analyze_market(symbol):
    try:
        # 1. Trend Kontrolü (Zaman kaybını önlemek için en başta)
        if not check_mtf_trend(symbol): return None, None, None

        # 2. 15 Dakikalık Veri Analizi
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 3. LİKİDİTE ALIMI (Balinaların stop patlattığı yer)
        liq_taken = l[-1] < min(l[-15:-1]) and c[-1] > min(l[-15:-1])
        
        # 4. MSS (Gövde Kapanışıyla Market Kırılımı - İğnelere kanmaz!)
        mss_ok = c[-1] > max(h[-10:-1])
        
        # 5. FVG (Boşluk - Giriş Bölgesi)
        fvg_ok = h[-3] < l[-1]
        entry_price = h[-3] # FVG başlangıcı

        # 6. HACİM (Gerçek Displacement)
        avg_vol = sum(v[-20:]) / 20
        vol_ok = v[-1] > (avg_vol * 1.5)

        if liq_taken and mss_ok and fvg_ok and vol_ok:
            if c[-1] <= entry_price * 1.003: # FVG'ye geri çekilme onayı
                stop_loss = min(l[-5:]) # En yakın swing low stop
                return 'buy', entry_price, stop_loss
        return None, None, None
    except: return None, None, None

# --- [5. EMİR SİSTEMİ - BİTGET GARANTİLİ] ---
def execute_order(symbol, side, entry, stop):
    try:
        val = get_balance()
        if val <= 0: return
        
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (val * CONFIG['leverage']) / entry
        
        # 1:2 RR (Risk/Ödül) Oranı
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * 2.5)

        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ ONAYLANDI: {symbol}**\n📍 Giriş: {entry:.4f}\n🛡️ Trend: 1G-4S-1S ONAYLI ✅")
        ex.create_market_order(symbol, side, amount)
        time.sleep(1)

        # Stop-Loss ve TP Emirleri (Trigger Limit)
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        ex.create_order(symbol, 'limit', 'sell', amount * CONFIG['tp1_ratio'], tp1, {'reduceOnly': True})
        ex.create_order(symbol, 'limit', 'sell', amount * (1-CONFIG['tp1_ratio']), tp2, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🛡️ Stop: {stop:.4f}\n🎯 TP1 (%75): {tp1:.4f}")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası ({symbol}): {str(e)}")

# --- [6. RADAR VE RAPORLAMA] ---
def radar_worker():
    bot.send_message(MY_CHAT_ID, "🦅 **SMC RADAR BAŞLADI: TÜM BORSA TARANIYOR**")
    while True:
        try:
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            
            # 1. Piyasa Raporu (Hangi Meme/Volatil Coinler Hareketli?)
            report = "📡 **RADAR ANALİZ RAPORU**\n"
            top_movers = sorted(all_symbols, key=lambda x: abs(markets[x]['percentage']), reverse=True)[:8]
            for s in top_movers:
                m = markets[s]
                report += f"{'🔥' if m['percentage'] > 0 else '🧊'} {s.split(':')[0]}: %{m['percentage']:.2f}\n"
            bot.send_message(MY_CHAT_ID, report)

            # 2. Tüm Borsayı Tara
            for sym in all_symbols:
                if sym in active_trades: continue
                # Hacim Filtresi (Likit olmayan coin balina tuzağıdır)
                if markets[sym]['quoteVolume'] < CONFIG['min_volume_24h']: continue 

                signal, entry, stop = analyze_market(sym)
                if signal and len(active_trades) < CONFIG['max_active_trades']:
                    execute_order(sym, signal, entry, stop)
                time.sleep(0.1) # API limit koruması

            time.sleep(600) # 10 dakikada bir tur
        except Exception as e:
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=radar_worker, daemon=True)
    t.start()
    bot.infinity_polling()
