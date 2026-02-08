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

# --- [2. AYARLAR - SİZİN İSTEKLERİNİZ] ---
CONFIG = {
    'trade_amount_usdt': 20.0,      # Giriş tutarı
    'leverage': 10,                 # Kaldıraç
    'tp1_ratio': 0.75,              # %75 Satış
    'tp1_target': 0.015,            # %1.5 Kâr (Masraflar dahil)
    'tp2_extra_usdt': 1.0,          # +1 USDT ekstra kâr hedefi
    'trailing_callback': 0.01,      # %1 Takip eden stop
    'max_coins': 30,                # Taranacak en aktif koin sayısı
    'timeframe': '15m'              # Analiz periyodu
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA] ---
def get_safe_balance():
    try:
        balance_info = ex.fetch_balance()
        return float(balance_info['total'].get('USDT', 0))
    except:
        return 0.0

@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Güncel Bakiye:** {total:.2f} USDT")

# --- [4. SMC & LİKİDİTE ANALİZİ (RESİMDEKİ STRATEJİ)] ---
def get_smc_analysis(symbol):
    try:
        # A. Günlük Swing Kontrolü (Balina Koruması)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_high = d_bars[0][2]
        swing_low = d_bars[0][3]

        # B. 15M Detaylı Analiz
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # C. Likidite Alındı mı? (Önemli Seviye Temizliği)
        liq_taken = last_price > swing_high or last_price < swing_low
        
        # D. MSS (Market Structure Shift) Onayı
        prev_highs = [b[2] for b in bars[-15:-2]]
        mss_ok = last_price > max(prev_highs)
        
        # E. FVG (Fair Value Gap) Oluşumu
        fvg = bars[-3][2] < bars[-1][3]
        
        # F. Hacim Onayı
        vols = [b[5] for b in bars]
        vol_ok = vols[-1] > (sum(vols[-15:])/15 * 1.1)

        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', "✅ STRATEJİ ONAYLANDI"
        
        # Radar simgeleri
        status_txt = f"{'✅' if fvg else '❌'} FVG | {'✅' if mss_ok else '❌'} MSS | {'📈' if vol_ok else '📉'} Vol"
        return None, f"{symbol}: {status_txt}"
    except:
        return None, f"{symbol}: ⚠️ Veri Hatası"

# --- [5. İŞLEM YÖNETİMİ] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🔥 **HYPE AVCI TETİKLENDİ!**\n🪙 {symbol}\n💰 Giriş: {price}")
        
        # 1. Market Giriş
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # 2. TP1 (%75)
        tp1_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 & Trailing Stop (+1 USDT Hedefi)
        rem_amount = amount - tp1_amount
        tp2_price = tp1_price + (CONFIG['tp2_extra_usdt']/rem_amount) if side == 'buy' else tp1_price - (CONFIG['tp2_extra_usdt']/rem_amount)
        
        params = {
            'reduceOnly': True, 
            'triggerPrice': tp2_price, 
            'callbackRate': CONFIG['trailing_callback']
        }
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', rem_amount, None, params)
        
        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **HEDEFLER KURULDU**\n🎯 TP1 (%75): {tp1_price:.4f}\n📈 Takip Başlangıcı: {tp2_price:.4f}")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [6. ANA ÇALIŞMA DÖNGÜSÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 **GHOST SMC BOT AKTİF!**\nBakiye, Radar ve Balina Savar Sistemi devrede.")
    
    while True:
        try:
            total_bal = get_safe_balance()
            markets = ex.fetch_tickers()
            # Borsanın en hacimli 30 koinini tara (HYPE işlemini bu hacim filtresi yakalamıştı)
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            report = f"📡 **SMC RADAR RAPORU**\n💰 Bakiye: {total_bal:.2f} USDT\n" + "-"*20 + "\n"
            
            for sym in symbols:
                signal, status = get_smc_analysis(sym)
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                    report += f"{sym}: ✅ GİRİLDİ\n"
                else:
                    report += f"{status}\n"
                time.sleep(1.2)

            bot.send_message(MY_CHAT_ID, report)
            time.sleep(900)
        except:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
