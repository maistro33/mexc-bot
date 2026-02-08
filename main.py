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

# --- [GERÇEK PARA AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,      # Pozisyonun %75'ini kapat
    'tp1_target': 0.015,    # %1.5 Kar Hedefi (Scalp için ideal)
    'max_coins': 12,        # En hacimli 12 koin radarda
    'timeframe': '15m'      
}

def get_radar_analysis(symbol):
    """Koinin FVG ve MSS durumunu kontrol eder ve rapor döner"""
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        if len(bars) < 40: return None, "⚠️ Veri Eksik"
        
        # FVG Kontrolü
        fvg = bars[-3][2] < bars[-1][3]
        fvg_status = "✅ FVG" if fvg else "❌ FVG"
        
        # MSS Kontrolü (Gövde Kapanışı)
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-15:-2]])
        mss = last_close > prev_high
        mss_status = "✅ MSS" if mss else "❌ MSS"
        
        # Hacim Kontrolü
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        vol_ok = vols[-1] > (avg_vol * 1.1)
        vol_status = "📈 Vol" if vol_ok else "📉 Vol"

        full_status = f"{symbol}: {fvg_status} | {mss_status} | {vol_status}"
        
        if fvg and mss and vol_ok:
            return 'buy', full_status
        return None, full_status
    except:
        return None, f"{symbol}: ⚠️ Hata"

def main_worker():
    bot.send_message(MY_CHAT_ID, "🚀 **GHOST SMC BOT AKTİF!**\nGerçek para moduna geçildi. Radar taraması başlıyor...")
    
    while True:
        try:
            # Bakiyeyi kontrol et (Telegram'a raporla)
            balance_info = ex.fetch_balance()
            total_usdt = balance_info.get('USDT', {}).get('total', 0)
            
            # En hacimli koinleri radara al
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            radar_report = f"📡 **RADAR ANALİZ RAPORU**\n💰 Bakiye: {total_usdt:.2f} USDT\n"
            radar_report += "----------------------------\n"
            
            signals_to_act = []
            for sym in symbols:
                signal, status_msg = get_radar_analysis(sym)
                radar_report += status_msg + "\n"
                if signal:
                    signals_to_act.append((sym, signal))
                time.sleep(1.5)

            # Radarı Telegram'a gönder
            bot.send_message(MY_CHAT_ID, radar_report)

            # Onaylanan sinyaller için tetiğe bas
            for sym, side in signals_to_act:
                execute_trade(sym, side)

            time.sleep(600) # 10 dakikada bir yeni radar raporu ve tarama
            
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🔥 **İŞLEM AÇILIYOR!**\n🪙 {symbol}\n↕️ Yön: {side.upper()}\n💰 Fiyat: {price}")
        
        # Market Giriş
        ex.create_market_order(symbol, side, amount)
        
        # %75 Kar Al Emri (TP1)
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        time.sleep(2) # Borsanın emri işlemesi için bekleme
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * CONFIG['tp1_ratio'], tp_price, {'reduceOnly': True})
        
        bot.send_message(MY_CHAT_ID, f"✅ **HEDEFLER DİZİLDİ:** %75 Kar Al emri {tp_price:.4f} seviyesine yerleştirildi.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ **İŞLEM HATASI:** {str(e)}")

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
