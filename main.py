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

# --- [2. AYARLAR] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,              # %75 Kar al
    'tp1_target': 0.015,            # %1.5 Kar hedefi
    'tp2_extra_usdt': 1.0,          # +1 USDT ekstra kar
    'trailing_callback': 0.01,      # %1 Takip eden stop
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA - %100 FİX] ---
def get_safe_balance():
    try:
        # Bitget "Available" bakiyesini çekmek için 'free' parametresi kullanılır.
        balance_info = ex.fetch_balance({'type': 'swap'})
        # Hem 'free' hem de 'info' içindeki 'available' kontrol edilir.
        available = float(balance_info.get('USDT', {}).get('free', 0))
        
        # Eğer hala 0 ise direkt info içinden yakala (Bitget Unified Account Fix)
        if available == 0:
            for item in balance_info['info']:
                if item.get('symbol') == 'USDT' or item.get('marginAsset') == 'USDT':
                    available = float(item.get('available', 0))
                    break
        return available
    except:
        return 0.0

@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Kullanılabilir Bakiyeniz:** {total:.2f} USDT")

# --- [4. SMC ANALİZİ - GÖRSELDEKİ STRATEJİ] ---
def get_smc_analysis(symbol):
    try:
        # A. Likidite Kontrolü (Daily Swing)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_high = d_bars[0][2]
        swing_low = d_bars[0][3]

        # B. 15M Analiz
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # C. Şartlar
        liq_taken = last_price > swing_high or last_price < swing_low
        prev_highs = [b[2] for b in bars[-15:-2]]
        mss_ok = last_price > max(prev_highs)
        fvg = bars[-3][2] < bars[-1][3]
        vols = [b[5] for b in bars]
        vol_ok = vols[-1] > (sum(vols[-15:])/15 * 1.1)

        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', "✅ ONAYLANDI"
        
        # Radar simgeleri
        status_txt = f"{'✅' if fvg else '❌'} FVG | {'✅' if mss_ok else '❌'} MSS | {'📈' if vol_ok else '📉'} Vol"
        return None, f"{symbol}: {status_txt}"
    except:
        return None, None

# --- [5. İŞLEM YÖNETİMİ] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ TETİKLENDİ!**\n🪙 {symbol}\n💰 Giriş: {price}")
        
        # 1. Giriş
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # 2. TP1 (%75 Satış)
        tp1_price = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 + Trailing (+1 USDT Kar Kovalamaca)
        rem_amount = amount - tp1_amount
        tp2_price = tp1_price + (CONFIG['tp2_extra_usdt']/rem_amount) if side == 'buy' else tp1_price - (CONFIG['tp2_extra_usdt']/rem_amount)
        
        params = {
            'reduceOnly': True, 
            'triggerPrice': tp2_price, 
            'callbackRate': CONFIG['trailing_callback']
        }
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', rem_amount, None, params)
        
        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🎯 TP1: {tp1_price:.4f}\n📈 Trailing Başlangıcı: {tp2_price:.4f}")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [6. ANA DÖNGÜ - BORSANIN TAMAMI] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: BÜYÜK RADAR AKTİF**\nBorsadaki tüm koinler taranıyor (600+)...")
    
    while True:
        try:
            total_bal = get_safe_balance()
            markets = ex.fetch_tickers()
            # BORSANIN TAMAMI: USDT vadeli tüm çiftler
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            
            # Raporda görünecek en aktif 15 koin
            top_symbols = sorted(all_symbols, key=lambda x: markets[x]['quoteVolume'], reverse=True)[:15]

            report = f"📡 **SMC RADAR ANALİZİ**\n💰 Bakiye: {total_bal:.2f} USDT\n" + "-"*20 + "\n"
            
            for sym in all_symbols:
                signal, status = get_smc_analysis(sym)
                
                # Rapora ekle (Sadece ilk 15 için ekran kirlenmemesi adına)
                if sym in top_symbols:
                    report += f"{status}\n"
                
                # Sinyal varsa gir
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                
                # API Limitlerini korumak için küçük bekleme
                time.sleep(0.05)

            bot.send_message(MY_CHAT_ID, report)
            time.sleep(900)
        except:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
