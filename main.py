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

# --- [BAKİYE SORGULAMA KOMUTU] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance_info = ex.fetch_balance()
        total_usdt = balance_info.get('USDT', {}).get('total', 0)
        available_usdt = balance_info.get('USDT', {}).get('free', 0)
        msg = f"💰 **Güncel Bakiye Raporu**\n\n💵 Toplam: {total_usdt:.2f} USDT\n🔓 Kullanılabilir: {available_usdt:.2f} USDT"
        bot.reply_to(message, msg)
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilirken hata oluştu: {str(e)}")

# --- [GERÇEK PARA AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'tp1_target': 0.015,
    'max_coins': 12,
    'timeframe': '15m'
}

def get_radar_analysis(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        if len(bars) < 40: return None, f"{symbol}: ⚠️ Veri Eksik"
        
        fvg = bars[-3][2] < bars[-1][3]
        fvg_status = "✅ FVG" if fvg else "❌ FVG"
        
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-15:-2]])
        mss = last_close > prev_high
        mss_status = "✅ MSS" if mss else "❌ MSS"
        
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
    bot.send_message(MY_CHAT_ID, "🚀 **GHOST SMC BOT AKTİF!**\nRadar taraması ve bakiye takibi başladı.")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            # Bakiye Bilgisi
            balance_info = ex.fetch_balance()
            total_usdt = balance_info.get('USDT', {}).get('total', 0)

            radar_report = f"📡 **RADAR ANALİZ RAPORU**\n💰 Bakiye: {total_usdt:.2f} USDT\n"
            radar_report += "----------------------------\n"
            
            signals_to_act = []
            for sym in symbols:
                signal, status_msg = get_radar_analysis(sym)
                radar_report += status_msg + "\n"
                if signal:
                    signals_to_act.append((sym, signal))
                time.sleep(1)

            bot.send_message(MY_CHAT_ID, radar_report)

            for sym, side in signals_to_act:
                execute_trade(sym, side)

            time.sleep(900) # 15 dakikalık periyot için daha uygun
            
        except Exception as e:
            time.sleep(60)

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🔥 **İŞLEM AÇILIYOR!**\n🪙 {symbol}\n↕️ Yön: {side.upper()}")
        ex.create_market_order(symbol, side, amount)
        
        tp_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        time.sleep(2)
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.75, tp_price, {'reduceOnly': True})
        
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ **İŞLEM HATASI:** {str(e)}")

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
