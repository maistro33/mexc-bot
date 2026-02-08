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

# --- [2. AYARLAR - KESİN KONFİGÜRASYON] ---
CONFIG = {
    'trade_amount_usdt': 20.0,      # Giriş miktarı
    'leverage': 10,                 # Kaldıraç
    'tp1_ratio': 0.75,              # İlk hedefte %75 satış
    'tp1_target': 0.015,            # %1.5 Kâr (TP1)
    'stop_loss_ratio': 0.02,        # %2 Zararda tam stop (Zırhlı Koruma)
    'trailing_activation': 0.02,    # %2 karda trailing başlar
    'trailing_callback': 0.01,      # %1 geri çekilmede sat
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA - %100 FİX] ---
def get_safe_balance():
    try:
        balance_info = ex.fetch_balance({'type': 'swap'})
        available = float(balance_info.get('USDT', {}).get('free', 0))
        if available == 0:
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

# --- [4. SMC ANALİZİ - GÖRSELDEKİ STRATEJİ] ---
def get_smc_analysis(symbol):
    try:
        # Altın/Gümüş (XAU/XAG) gibi hatalı pariteleri ele
        if "XAU" in symbol or "XAG" in symbol: return None, None

        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_high, swing_low = d_bars[0][2], d_bars[0][3]
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        liq_taken = last_price > swing_high or last_price < swing_low
        prev_highs = [b[2] for b in bars[-15:-2]]
        mss_ok = last_price > max(prev_highs)
        fvg = bars[-3][2] < bars[-1][3]
        vols = [b[5] for b in bars]
        vol_ok = vols[-1] > (sum(vols[-15:])/15 * 1.1)

        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', "✅ ONAYLANDI"
        
        status_txt = f"{'✅' if fvg else '❌'} FVG | {'✅' if mss_ok else '❌'} MSS | {'📈' if vol_ok else '📉'} Vol"
        return None, f"{symbol}: {status_txt}"
    except:
        return None, None

# --- [5. İŞLEM VE EMİR YÖNETİMİ - ZIRHLI] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ TETİKLENDİ!**\n🪙 {symbol}\n💰 Giriş: {price}")
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # A. Stop-Loss (Tüm Pozisyon İçin)
        sl_p = price * (1 - CONFIG['stop_loss_ratio']) if side == 'buy' else price * (1 + CONFIG['stop_loss_ratio'])
        ex.create_order(symbol, 'stop', 'sell' if side == 'buy' else 'buy', amount, None, {'reduceOnly': True, 'stopPrice': sl_p})
        
        # B. TP1 (%75 Kâr Al)
        tp1_p = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        tp1_a = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_a, tp1_p, {'reduceOnly': True})
        
        # C. Trailing Stop (Kalan %25 İçin - Hata Korumalı)
        rem_a = amount - tp1_a
        trig_p = price * (1 + CONFIG['trailing_activation']) if side == 'buy' else price * (1 - CONFIG['trailing_activation'])
        
        try:
            params = {'reduceOnly': True, 'triggerPrice': trig_p, 'callbackRate': CONFIG['trailing_callback']}
            ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', rem_a, None, params)
        except:
            # Illegal Order hatası alınırsa (SKY gibi) otomatik TP2 Limit koyar
            tp2_p = price * 1.05 if side == 'buy' else price * 0.95
            ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', rem_a, tp2_p, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🎯 TP1 (%75): {tp1_p:.4f}\n🛡️ Stop-Loss: {sl_p:.4f}\n📈 Trailing: Aktif")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [6. ANA DÖNGÜ - BÜYÜK RADAR] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: NİHAİ MOD AKTİF**\nBorsanın tamamı taranıyor...")
    while True:
        try:
            total_bal = get_safe_balance()
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            top_symbols = sorted(all_symbols, key=lambda x: markets[x]['quoteVolume'], reverse=True)[:15]

            report = f"📡 **SMC RADAR ANALİZİ**\n💰 Bakiye: {total_bal:.2f} USDT\n" + "-"*20 + "\n"
            for sym in all_symbols:
                signal, status = get_smc_analysis(sym)
                if sym in top_symbols and status: report += f"{status}\n"
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
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
