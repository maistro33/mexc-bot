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

# --- [ADIMLI KÂR STRATEJİSİ] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,         # %75 Sat
    'tp1_target': 0.015,       # %1.5 Kar
    'tp2_extra_usdt': 1.0,     # TP1'den sonra +1 USDT daha kar görünce çalışır
    'trailing_callback': 0.01, # %1 geri çekilirse takip eden stop patlar
    'max_coins': 12,
    'timeframe': '15m'
}

active_trades = {}

def check_trade_updates():
    """Pozisyonları izler ve TP mesajı atar"""
    while True:
        try:
            for symbol in list(active_trades.keys()):
                pos = ex.fetch_position(symbol)
                size = float(pos['contracts']) if pos else 0
                
                # Eğer pozisyon tamamen kapandıysa
                if size == 0:
                    bot.send_message(MY_CHAT_ID, f"🏁 **İŞLEM TAMAMLANDI:** {symbol} pozisyonu tüm hedeflere ulaştı veya stop oldu.")
                    del active_trades[symbol]
            time.sleep(60)
        except:
            time.sleep(60)

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        entry_price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / entry_price
        
        bot.send_message(MY_CHAT_ID, f"🔥 **AV BAŞLADI!**\n🪙 {symbol}\n💰 Giriş: {entry_price}")
        
        # 1. MARKET GİRİŞ
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # 2. TP1: %75 Limit Satış
        tp1_price = entry_price * (1 + CONFIG['tp1_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 & TRAILING STOP (Kalan %25 için)
        # 1 USDT kâr eklenmiş fiyatı hesapla
        extra_price_dist = CONFIG['tp2_extra_usdt'] / (amount * 0.25)
        tp2_activation_price = tp1_price + extra_price_dist if side == 'buy' else tp1_price - extra_price_dist
        
        # Bitget Trailing Stop Emri (Kalan miktar için)
        remaining_amount = amount - tp1_amount
        params = {
            'reduceOnly': True,
            'triggerPrice': tp2_activation_price, # Bu fiyata gelince takip başlar
            'callbackRate': CONFIG['trailing_callback'] # %1 geri çekilirse sat
        }
        
        # Bitget API üzerinden takip eden stop gönderimi
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', remaining_amount, None, params)
        
        active_trades[symbol] = {'entry': entry_price}
        bot.send_message(MY_CHAT_ID, f"✅ **HEDEFLER KURULDU:**\n- %75 TP1: {tp1_price:.4f}\n- Kalan %25: Trailing Stop (Aktifleşme: {tp2_activation_price:.4f})")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ **EMİR HATASI:** {str(e)}")

def main_worker():
    threading.Thread(target=check_trade_updates, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "🦅 **SÜPER AVCI AKTİF!**\n%75 Kâr Al + Kalan %25 Trailing Stop devrede.")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            for sym in symbols:
                # Sinyal tarama fonksiyonunuz (FVG/MSS) buraya gelecek
                # ... (check_radar_analysis çağrısı)
                pass # (Mevcut mantık devam ediyor)
            
            time.sleep(900)
        except:
            time.sleep(60)

# (get_radar_analysis ve if __name__ kısımları aynı kalacak)
