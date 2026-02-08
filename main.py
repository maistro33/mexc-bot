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

# --- [STRATEJİ AYARLARI] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,              # %75 Sat
    'tp1_target': 0.015,            # %1.5 Kar (Komisyonlar dahil net kar odaklı)
    'tp2_extra_usdt': 1.0,          # TP1'den sonra kasaya +1 USDT daha koy
    'trailing_callback': 0.01,      # %1 geri çekilirse takip eden stop patlar
    'max_coins': 20,
    'timeframe': '15m'
}

active_trades = {}

def get_smc_analysis(symbol):
    try:
        # 1. Günlük Likidite Kontrolü (Balina Tuzağından Korunma)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_high = d_bars[0][2]
        swing_low = d_bars[0][3]

        # 2. 15 Dakikalık Analiz
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # Likidite Alımı Kontrolü
        liq_taken = last_price > swing_high or last_price < swing_low
        
        # Market Yapısı Kırılımı (MSS) - Gövde Kapanış Onaylı
        prev_highs = [b[2] for b in bars[-15:-2]]
        mss_ok = last_price > max(prev_highs)
        
        # FVG (Fiyat Boşluğu)
        fvg = bars[-3][2] < bars[-1][3]
        
        # Hacim Onayı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        vol_ok = vols[-1] > (avg_vol * 1.1)

        if liq_taken and mss_ok and fvg and vol_ok:
            return 'buy', "✅ BALİNA ONAYLI SİNYAL"
        return None, None
    except:
        return None, None

def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        entry_price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / entry_price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **BALİNA TAKİBİNDE İŞLEM AÇILDI!**\n🪙 {symbol}\n💰 Giriş: {entry_price}")
        
        # 1. Market Giriş
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # 2. TP1: %75 Limit Satış
        tp1_price = entry_price * (1 + CONFIG['tp1_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp1_target'])
        tp1_amount = amount * CONFIG['tp1_ratio']
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', tp1_amount, tp1_price, {'reduceOnly': True})
        
        # 3. TP2 & Trailing Stop (+1 USDT Hedefi)
        remaining_amount = amount - tp1_amount
        # Kalan miktar üzerinden +1 USDT kâr için gereken fiyat farkı
        extra_dist = CONFIG['tp2_extra_usdt'] / remaining_amount
        tp2_activation_price = tp1_price + extra_dist if side == 'buy' else tp1_price - extra_dist
        
        params = {
            'reduceOnly': True,
            'triggerPrice': tp2_activation_price,
            'callbackRate': CONFIG['trailing_callback']
        }
        
        ex.create_order(symbol, 'trailing_stop_market', 'sell' if side == 'buy' else 'buy', remaining_amount, None, params)
        
        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **HEDEFLER ONAYLANDI:**\n- TP1 (%75): {tp1_price:.4f}\n- Kalan için +1 USDT Kâr & Trailing Stop Aktif.")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: BALİNA SAVAR AKTİF!**\nLikidite takibi, TP1 (%75) ve TP2 (+1 USDT Trailing) devrede.")
    
    while True:
        try:
            balance = ex.fetch_balance().get('USDT', {}).get('total', 0)
            markets = ex.fetch_tickers()
            symbols = sorted([s for s in markets if '/USDT:USDT' in s], 
                             key=lambda x: markets[x]['quoteVolume'], reverse=True)[:CONFIG['max_coins']]

            report = f"📡 **SMC RADAR RAPORU**\n💰 Bakiye: {balance:.2f} USDT\n" + "-"*20 + "\n"
            
            for sym in symbols:
                signal, status = get_smc_analysis(sym)
                # Sadece önemli aşamadaki koinleri raporla ki ekran kirlenmesin
                if signal:
                    execute_trade(sym, signal)
                    report += f"{sym}: ✅ İŞLEME GİRİLDİ\n"
                else:
                    report += f"{sym}: ⏳ Fırsat Bekleniyor\n"
                time.sleep(1)

            bot.send_message(MY_CHAT_ID, report)
            time.sleep(900)
        except:
            time.sleep(60)

if __name__ == "__main__":
    main_worker()
