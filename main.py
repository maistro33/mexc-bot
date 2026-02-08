import ccxt
import telebot
import time
import os
import threading

# --- [1. BAĞLANTILAR VE KİMLİK DOĞRULAMA] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Bitget Bağlantısı (Swap Modu Aktif)
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. KONFİGÜRASYON VE STRATEJİ AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,      # İşleme giriş miktarı
    'leverage': 10,                 # Kaldıraç
    'tp1_ratio': 0.75,              # İlk hedefte %75 satılacak
    'tp1_target': 0.015,            # %1.5 kâr hedefi (TP1)
    'tp2_extra_usdt': 1.0,          # TP1'den sonra +1 USDT daha kâr görünce trailing başlar
    'trailing_callback': 0.01,      # %1 geri çekilmede stop olur
    'max_coins': 15,                # Taranacak koin sayısı
    'timeframe': '15m'              # Analiz periyodu
}

# Aktif işlemleri hafızada tutma (Çakışmayı önlemek için)
active_trades = {}

# --- [3. YARDIMCI FONKSİYONLAR: BAKİYE VE ANALİZ] ---

def get_safe_balance():
    """Bakiye verisini güvenli şekilde çeker"""
    try:
        balance_info = ex.fetch_balance()
        # Bitget'te toplam USDT bakiyesi
        return float(balance_info['total'].get('USDT', 0))
    except Exception as e:
        print(f"Bakiye Hatası: {e}")
        return 0.0

@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Güncel Bakiyeniz:** {total:.2f} USDT")

def get_smc_analysis(symbol):
    """SMC ve Likidite Stratejisi Kontrolü"""
    try:
        # A. Günlük Swing High/Low (Balina Koruması)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_high = d_bars[0][2]
        swing_low = d_bars[0][3]

        # B. 15 Dakikalık Mum Verileri
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # C. Likidite Kontrolü: Fiyat dünkü tepenin üstünde mi veya dibin altında mı?
        liq_taken = last_price > swing_high or last_price < swing_low
        
        # D. MSS (Market Yapısı Kırılımı): Son 15 mumun tepesini geçti mi?
        prev_highs = [b[2] for b in bars[-15:-2]]
        mss_ok = last_price > max(prev_highs)
        
        # E. FVG (Boşluk Onayı)
        fvg = bars[-3][2] < bars[-1][3]
        
        # F. Hacim Onayı (Ortalama üstü mü?)
        vols = [b[5] for b in bars]
        vol_ok = vols[-1] > (sum(vols[-15:])/15 * 1.1)

        # Karar Mekanizması
        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', "✅ ONAYLANDI"
        
        # Raporlama için durum simgesi
        status_icon = "🚨" if liq_taken else "⏳"
        return None, f"{symbol}: {status_icon} Beklemede"
    except:
        return None, f"{symbol}: ⚠️ Veri Hatası"

# --- [4. İŞLEM YÖNETİMİ: GİRİŞ, TP1 VE TRAILING STOP] ---

def execute_trade(symbol, side):
    try:
        # Kaldıraç ayarla
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        
        # Miktar hesapla (Kaldıraç dahil)
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ TETİKLENDİ!**\n🪙 {symbol}\n💰 Giriş: {price}")
        
        # 1. Market Giriş Emri
        ex.create_market_order(symbol, side, amount)
        time.sleep(2) # Borsanın işlemesi için bekleme
        
        # 2. TP1 (%75) Sabit Limit Emir
        tp1_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 VE TRAILING STOP (Kalan %25 için)
        rem_amount = amount - tp1_amount
        # +1 USDT kâr için gereken fiyat mesafe hesabı
        tp2_price = tp1_price + (CONFIG['tp2_extra_usdt']/rem_amount) if side == 'buy' else tp1_price - (CONFIG['tp2_extra_usdt']/rem_amount)
        
        params = {
            'reduceOnly': True, 
            'triggerPrice': tp2_price, 
            'callbackRate': CONFIG['trailing_callback']
        }
        # Bitget API Trailing Stop Market emri
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', rem_amount, None, params)
        
        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🎯 TP1 (%75): {tp1_price:.4f}\n📈 Trailing Aktifleşme (+1 USDT): {tp2_price:.4f}")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [5. ANA DÖNGÜ VE RAPORLAMA] ---

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: NİHAİ MOD AKTİF**\nBakiye kontrolü ve Balina Savar Radar başladı.")
    
    while True:
        try:
            total_bal = get_safe_balance()
            markets = ex.fetch_tickers()
            # Hacme göre en iyi koinleri seç
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            report = f"📡 **SMC RADAR ANALİZİ**\n💰 Bakiye: {total_bal:.2f} USDT\n" + "-"*20 + "\n"
            
            for sym in symbols:
                signal, status = get_smc_analysis(sym)
                
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                    report += f"{sym}: ✅ İŞLEM AÇILDI\n"
                else:
                    report += f"{status}\n"
                time.sleep(1.2) # Rate limit koruması

            bot.send_message(MY_CHAT_ID, report)
            time.sleep(900) # 15 dakikalık bekleme
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    # Botu başlat
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
