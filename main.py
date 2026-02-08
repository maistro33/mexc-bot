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

# --- [2. AYARLAR - KESİN KONTROL] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'stop_loss_ratio': 0.02,        # %2 Net Stop
    'tp1_target': 0.018,            # Masraf dahil %1.5 net
    'tp2_target': 0.035,            # Masraf dahil %3.0 net
    'tp3_target': 0.055,            # Masraf dahil %5.0 net
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA] ---
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

# --- [4. KESKİN SMC ANALİZİ - GÜNCELLENDİ] ---
def get_smc_analysis(symbol):
    try:
        if any(x in symbol for x in ["XAU", "XAG", "USDC", "EUR"]): return None, None
        
        # 1. 15 Dakikalık Veri
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        if len(bars) < 50: return None, None
        
        last_price = bars[-1][4]      # Kapanış Fiyatı
        prev_close = bars[-2][4]      # Bir önceki mum kapanışı
        
        # A. LİKİDİTE ALIMI (Daily Swing Low Altında Kapanış Değil, İğne Sonrası Dönüş)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_low = d_bars[0][3]
        
        # Fiyat dünün en düşüğünün altına iğne atmış ama üzerinde kapatmış olmalı (BOS/MSS hazırlığı)
        liq_grab = bars[-1][3] < swing_low and last_price > swing_low

        # B. MSS (Market Structure Shift) - En Önemli Kontrol
        # Son 15 mumun en yüksek seviyesini "Gövde Kapanışı" ile kırmalı (Tepeden girmeyi önler)
        recent_highs = [b[2] for b in bars[-15:-1]]
        mss_threshold = max(recent_highs)
        mss_ok = last_price > mss_threshold

        # C. FVG (Fair Value Gap) - Destek Bölgesi
        fvg_exists = bars[-3][2] < bars[-1][3]

        # D. HACİM ONAYI (Gerçek Kırılım)
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:-1]) / 14
        vol_ok = vols[-1] > (avg_vol * 1.3) # Hacim %30 daha yüksek olmalı

        # LONG STRATEJİSİ: Likidite alınmış olmalı + Yapı yukarı kırılmış olmalı + Hacim desteklemeli
        if liq_grab and mss_ok and vol_ok:
            return 'buy', f"✅ KESKİN ONAY: {symbol}"
        
        return None, None
    except:
        return None, None

# --- [5. İŞLEM YÖNETİMİ] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ TETİKLENDİ (KESKİN NİŞANCI)**\n🪙 {symbol}\n💰 Giriş: {price}")
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # Emirleri Diz (Sırasıyla: SL, TP1, TP2, TP3)
        sl_p = price * (1 - CONFIG['stop_loss_ratio']) if side == 'buy' else price * (1 + CONFIG['stop_loss_ratio'])
        ex.create_order(symbol, 'stop', 'sell' if side == 'buy' else 'buy', amount, None, {'reduceOnly': True, 'stopPrice': sl_p})
        
        tp1_p = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.50, tp1_p, {'reduceOnly': True})
        
        tp2_p = price * (1 + CONFIG['tp2_target']) if side == 'buy' else price * (1 - CONFIG['tp2_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.25, tp2_p, {'reduceOnly': True})

        tp3_p = price * (1 + CONFIG['tp3_target']) if side == 'buy' else price * (1 - CONFIG['tp3_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.25, tp3_p, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **KADEMELİ EMİRLER KURULDU**\n🛡️ SL: {sl_p:.4f}\n🎯 TP1-2-3 Aktif")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [6. ANA DÖNGÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: KESKİN NİŞANCI MODU AKTİF**")
    while True:
        try:
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            for sym in all_symbols:
                signal, _ = get_smc_analysis(sym)
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                time.sleep(0.05)
            time.sleep(900)
        except:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
