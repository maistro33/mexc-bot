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

# --- [ADIMLI KÂR STRATEJİSİ & AYARLAR] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,              # %75 Sat
    'tp1_target': 0.015,            # %1.5 Kar
    'tp2_extra_usdt': 1.0,          # TP1'den sonra +1 USDT daha kar görünce takip başlar
    'trailing_callback': 0.01,      # %1 geri çekilirse takip eden stop patlar
    'max_coins': 12,
    'timeframe': '15m'
}

active_trades = {}

# --- [BAKİYE KOMUTU] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance_info = ex.fetch_balance()
        total_usdt = balance_info.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {total_usdt:.2f} USDT")
    except:
        bot.reply_to(message, "❌ Bakiye çekilemedi.")

# --- [RADAR ANALİZ FONKSİYONU] ---
def get_radar_analysis(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=40)
        if len(bars) < 40: return None, f"{symbol}: ⚠️ Veri Eksik"
        
        # FVG Kontrolü
        fvg = bars[-3][2] < bars[-1][3]
        
        # MSS Kontrolü (Gövde Kapanışlı)
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-15:-2]])
        mss = last_close > prev_high
        
        # Hacim Onayı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        vol_ok = vols[-1] > (avg_vol * 1.1)

        status = f"{symbol}: {'✅' if fvg else '❌'} FVG | {'✅' if mss else '❌'} MSS | {'📈' if vol_ok else '📉'} Vol"
        
        if fvg and mss and vol_ok:
            return 'buy', status
        return None, status
    except:
        return None, f"{symbol}: ⚠️ Hata"

# --- [İŞLEM AÇMA & HEDEF BELİRLEME] ---
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
        
        # 2. TP1: %75 Limit Satış (Garanti Kâr)
        tp1_price = entry_price * (1 + CONFIG['tp1_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 & TRAILING STOP (Kalan %25 için)
        # +1 USDT kâr eklenmiş aktivasyon fiyatı
        extra_price_dist = CONFIG['tp2_extra_usdt'] / (amount * (1 - CONFIG['tp1_ratio']))
        tp2_activation_price = tp1_price + extra_price_dist if side == 'buy' else tp1_price - extra_price_dist
        
        remaining_amount = amount - tp1_amount
        params = {
            'reduceOnly': True,
            'triggerPrice': tp2_activation_price,
            'callbackRate': CONFIG['trailing_callback']
        }
        
        # Bitget'e takip eden stop emrini gönderiyoruz
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', remaining_amount, None, params)
        
        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **HEDEFLER KURULDU:**\n- %75 TP1: {tp1_price:.4f}\n- Kalan %25: Trailing Stop (Aktifleşme: {tp2_activation_price:.4f})")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ **EMİR HATASI:** {str(e)}")

# --- [ANA ÇALIŞMA DÖNGÜSÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🦅 **GHOST SMC: SÜPER AVCI AKTİF!**\nRadar, Bakiye ve Gelişmiş Takip Sistemi Devrede.")
    
    while True:
        try:
            # Bakiyeyi çek
            balance_info = ex.fetch_balance()
            total_usdt = balance_info.get('USDT', {}).get('total', 0)
            
            # Piyasayı tara
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            report = f"📡 **RADAR ANALİZ RAPORU**\n💰 Bakiye: {total_usdt:.2f} USDT\n" + "-"*20 + "\n"
            
            signals_to_act = []
            for sym in symbols:
                signal, status = get_radar_analysis(sym)
                report += status + "\n"
                if signal and sym not in active_trades:
                    signals_to_act.append((sym, signal))
                time.sleep(1.5)

            bot.send_message(MY_CHAT_ID, report)

            for sym, side in signals_to_act:
                execute_trade(sym, side)
            
            # 15 dakikalık periyot (900 saniye)
            time.sleep(900)
        except Exception as e:
            print(f"Döngü hatası: {e}")
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
