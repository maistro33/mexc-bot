import ccxt
import os
import telebot
import time

# --- [BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

def test_run():
    bot.send_message(MY_CHAT_ID, "🧪 **DENEME 3:** TP/SL doğrudan pozisyonun içine yükleniyor...")
    
    try:
        tickers = ex.fetch_tickers()
        symbol = [s for s in tickers if '/USDT:USDT' in s and 'BTC' not in s][:1][0]
        
        price = tickers[symbol]['last']
        amt = (5.0 * 10) / price 
        
        sl = round(price * 0.99, 4)  # %1 Stop
        tp = round(price * 1.02, 4)  # %2 TP
        
        ex.set_leverage(10, symbol)
        
        # 1. POZİSYONU AÇ (MARKET BUY)
        print(f"{symbol} için pozisyon açılıyor...")
        ex.create_order(symbol, 'market', 'buy', amt, params={'posSide': 'long'})
        
        time.sleep(2) # Borsanın pozisyonu kaydetmesi için süre tanıyalım

        # 2. TP/SL'Yİ POZİSYONUN İÇİNE GÖM (set_margin_mode yerine set_trading_layer gibi)
        # Bitget'te bu işlem için özel bir metod kullanılır:
        try:
            ex.private_post_mix_v1_order_modify_tpsl({
                'symbol': symbol.replace('/USDT:USDT', '_UMCBL'), # Bitget API formatı
                'marginCoin': 'USDT',
                'orderId': None, # Pozisyona bağlamak için
                'stopLoss': str(sl),
                'takeProfit': str(tp),
                'holdSide': 'long'
            })
        except:
            # Eğer yukarıdaki özel metod çalışmazsa standart ccxt metodunu zorlayalım:
            ex.edit_order(None, symbol, 'market', 'buy', amt, price, params={
                'stopLossPrice': sl,
                'takeProfitPrice': tp,
                'posSide': 'long'
            })
        
        bot.send_message(MY_CHAT_ID, f"🎯 **BAŞARILI!**\nKoin: {symbol}\nŞimdi pozisyonun içine bak, TP: {tp} ve SL: {sl} olarak yüklenmiş olmalı.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ HATA: {e}")

if __name__ == "__main__":
    test_run()
