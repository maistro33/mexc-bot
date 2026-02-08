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

# Bitget Swap (Vadeli) Bağlantısı
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR - %100 SADIK BEY KONFİGÜRASYONU] ---
CONFIG = {
    'trade_amount_usdt': 20.0,      # Giriş miktarı
    'leverage': 10,                 # Kaldıraç
    'stop_loss_ratio': 0.02,        # %2 Zarar Kes (Net)
    'tp1_ratio': 0.75,              # İlk hedefte %75 satış (Kritik)
    'tp1_target': 0.018,            # %1.8 (Komisyon sonrası net %1.5 kâr)
    'tp2_target': 0.035,            # %3.5 (Net %3.0 kâr)
    'tp3_target': 0.055,            # %5.5 (Net %5.0 kâr)
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA - GARANTİLİ YÖNTEM] ---
def get_safe_balance():
    try:
        balance_info = ex.fetch_balance({'type': 'swap'})
        # Doğrudan kullanılabilir USDT bakiyesine erişim
        available = float(balance_info.get('USDT', {}).get('free', 0))
        if available == 0 and 'info' in balance_info:
            for item in balance_info['info']:
                if item.get('marginAsset') == 'USDT':
                    available = float(item.get('available', 0))
                    break
        return available
    except:
        return 0.0

@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Kullanılabilir Bakiye:** {total:.2f} USDT")

# --- [4. HYPE SMC ANALİZİ - (LİKTİDİTE + MSS + FVG + VOL)] ---
def get_smc_analysis(symbol):
    try:
        # Hata veren pariteleri baştan ele
        if any(x in symbol for x in ["XAU", "XAG", "USDC", "EUR", "GBP"]): return None, None
        
        # Mum verilerini çek
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # A. Likidite Alımı (Daily Low Kontrolü)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_low = d_bars[0][3]
        liq_taken = bars[-1][3] < swing_low and last_price > swing_low
        
        # B. MSS (Market Structure Shift) - Gövde Kapanış Onayı
        recent_highs = [b[2] for b in bars[-15:-1]]
        mss_ok = last_price > max(recent_highs)
        
        # C. FVG (Fair Value Gap)
        fvg = bars[-3][2] < bars[-1][3]
        
        # D. Hacim Onayı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        vol_ok = vols[-1] > (avg_vol * 1.25) # %25 hacim artışı şartı

        # Rapor formatı (Özlediğiniz o liste)
        status = f"{symbol}: {'✅' if fvg else '❌'} FVG | {'✅' if mss_ok else '❌'} MSS | {'📈' if vol_ok else '📉'} Vol"
        
        # Tüm şartlar sağlandığında 'buy' sinyali
        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', status
        return None, status
    except:
        return None, None

# --- [5. İŞLEM VE EMİR DİZME - ZIRHLI ZİNCİR] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **HYPE SİNYALİ YAKALANDI!**\n🪙 {symbol}\n💰 Giriş: {price}")
        
        # 1. Market Giriş Emri
        ex.create_market_order(symbol, side, amount)
        time.sleep(2) # Borsanın işlemesi için kısa bekleme
        
        # 2. STOP-LOSS (%100 Miktar)
        sl_p = price * (1 - CONFIG['stop_loss_ratio'])
        ex.create_order(symbol, 'stop', 'sell', amount, None, {'reduceOnly': True, 'stopPrice': sl_p})
        
        # 3. TP1 (%75 Miktar) - Limit Emir
        tp1_p = price * (1 + CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell', amount * CONFIG['tp1_ratio'], tp1_p, {'reduceOnly': True})
        
        # 4. TP2 (%12.5 Miktar)
        tp2_p = price * (1 + CONFIG['tp2_target'])
        ex.create_order(symbol, 'limit', 'sell', amount * 0.125, tp2_p, {'reduceOnly': True})

        # 5. TP3 (%12.5 Miktar)
        tp3_p = price * (1 + CONFIG['tp3_target'])
        ex.create_order(symbol, 'limit', 'sell', amount * 0.125, tp3_p, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🛡️ SL: {sl_p:.4f}\n🎯 TP1 (%75): {tp1_p:.4f}\n🎯 TP2-3 Aktif.")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ Emir Dizme Hatası: {str(e)}")

# --- [6. ANA DÖNGÜ - RADAR VE RAPORLAMA] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🦅 **GHOST SMC RADAR BAŞLATILDI**\nHYPE ayarları ve tüm borsa taraması aktif.")
    while True:
        try:
            total_bal = get_safe_balance()
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            
            # En hacimli 10 coin için rapor hazırlığı
            top_symbols = sorted(all_symbols, key=lambda x: markets[x]['quoteVolume'], reverse=True)[:10]
            report = f"📡 **SMC RADAR ANALİZİ**\n💰 Bakiye: {total_bal:.2f} USDT\n" + "-"*20 + "\n"
            
            for sym in all_symbols:
                signal, status = get_smc_analysis(sym)
                
                # Sadece en hacimli 10 tanesini rapora ekle (mesaj sınırı için)
                if sym in top_symbols:
                    report += f"{status}\n"
                
                # Sinyal varsa işleme gir
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                
                time.sleep(0.05) # API koruma
            
            # Tur sonunda raporu gönder
            bot.send_message(MY_CHAT_ID, report)
            time.sleep(900) # 15 dakika bekle ve tekrarla
        except Exception as e:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
