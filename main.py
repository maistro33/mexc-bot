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

# --- [AYARLAR] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,      # %75 Kar Al (Sadık Bey Ayarı)
    'tp1_target': 0.015,    # %1.5 karda ilk satış
    'max_coins': 15         # Hız için en hacimli 15 koin
}

def check_fvg_and_mss(symbol):
    """Koin analizini yapar ve detaylı rapor döner"""
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        if len(bars) < 50: return None, "Veri yetersiz"
        
        # 1. FVG Kontrolü (İmbalance)
        # Boğa FVG: 1. mumun yükseği < 3. mumun düşüğü
        fvg_found = False
        if bars[-3][2] < bars[-1][1]:
            fvg_found = True
            
        # 2. MSS (Gövde Kapanışlı Kırılım)
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-20:-5]]) # Önceki tepe
        mss_confirmed = last_close > prev_high
        
        # 3. Hacim Onayı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-10:]) / 10
        current_vol = vols[-1]
        vol_ok = current_vol > (avg_vol * 1.1)

        status_msg = f"🔍 {symbol}: "
        if fvg_found: status_msg += "✅ FVG var "
        else: status_msg += "❌ FVG yok "
        
        if mss_confirmed: status_msg += "| ✅ MSS Onaylı"
        else: status_msg += "| ❌ MSS Yok"

        if fvg_found and mss_confirmed and vol_ok:
            return 'buy', status_msg
        return None, status_msg
    except:
        return None, f"⚠️ {symbol}: Analiz hatası"

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛰️ Akıllı Tarama ve Simülasyon Başladı!\n(Para gelene kadar 'Yetersiz Bakiye' hatası verecektir)")
    
    while True:
        try:
            # En hacimli koinleri çek
            markets = ex.fetch_tickers()
            symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'],
                reverse=True
            )[:CONFIG['max_coins']]

            report = "📊 **TARAMA RAPORU**\n"
            signals_to_act = []

            for sym in symbols:
                signal, status = check_fvg_and_mss(sym)
                report += status + "\n"
                if signal:
                    signals_to_act.append((sym, signal))
                time.sleep(1)

            # Raporu gönder (Çok uzun olmasın diye sınırlı)
            bot.send_message(MY_CHAT_ID, report)

            # Sinyal varsa işleme girmeye çalış
            for sym, side in signals_to_act:
                execute_trade(sym, side)

        except Exception as e:
            print(f"Döngü hatası: {e}")
        
        time.sleep(300) # 5 dakikada bir tarama raporu atar

def execute_trade(symbol, side):
    try:
        # Bakiye 0 olsa bile burayı deneyecek
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"⚡ **{symbol} için İŞLEM DENENİYOR!**\nSinyal: {side.upper()}")
        
        # Bu satır bakiye 0 olduğu için hata verecek ve biz botun çalıştığını anlayacağız
        order = ex.create_market_order(symbol, side, amount)
        
        # Eğer para olsaydı buraya geçecekti
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.75, tp_price, {'reduceOnly': True})
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"🔔 **Bakiye Durumu:** İşlem açma aşamasına gelindi ancak borsa şunu dedi:\n`{str(e)}`")

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
