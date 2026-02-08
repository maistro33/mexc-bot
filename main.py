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
    'trade_amount_usdt': 15.0,      
    'leverage': 10,
    'stop_loss_ratio': 0.02,
    'tp1_ratio': 0.75,              # Sadık Bey'in %75 TP1 kuralı
    'tp1_target': 0.02,             # 1:2 RR hedefi için ilk adım
    'tp2_target': 0.05              # 1:2 RR nihai hedef
}

active_trades = {}

def get_smc_analysis(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        highs = [b[2] for b in bars]
        lows = [b[3] for b in bars]
        closes = [b[4] for b in bars]
        vols = [b[5] for b in bars]

        # 1. ÖNEMLİ LİKİDİTE SEVİYESİ ALINACAK
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        daily_low = d_bars[0][3]
        liq_taken = min(lows[-5:]) < daily_low and closes[-1] > daily_low

        # 2. TERS YÖNE DISPLACEMENT (Sert Hacimli Hareket)
        avg_vol = sum(vols[-20:-1]) / 20
        displacement = vols[-1] > (avg_vol * 1.8) # %80 daha fazla hacim

        # 3. MARKET YAPISININ DEĞİŞMESİ (MSS - Gövde Kapanışıyla)
        recent_swing_high = max(highs[-20:-5])
        mss_ok = closes[-1] > recent_swing_high

        # 4. MARKET YAPISININ DEĞİŞTİĞİ YERDEKİ FVG'DEN GİRİLECEK
        # FVG Kontrolü: 3 mum öncesinin tepesi, son mumun dibinden küçükse GAP vardır.
        fvg_detected = highs[-3] < lows[-1]
        fvg_entry_price = highs[-3] # Giriş seviyemiz tam FVG başlangıcı

        status = f"{symbol}: {'✅' if mss_ok else '❌'} MSS | {'📈' if displacement else '📉'} Vol | {'🌊' if liq_taken else '⌛'} Liq"

        if liq_taken and displacement and mss_ok and fvg_detected:
            # Sadece fiyat FVG bölgesine (fvg_entry_price) geri çekilirse girer
            if closes[-1] <= fvg_entry_price * 1.002: 
                return 'buy', status, fvg_entry_price
        return None, status, None
    except: return None, None, None

def execute_trade(symbol, side, entry_p):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / entry_p
        
        bot.send_message(MY_CHAT_ID, f"🎯 **STRATEJİ ONAYLANDI: {symbol}**\n📍 FVG Giriş: {entry_p}\n🛡️ RR Hedefi: 1:2")
        
        # Limit Emirle FVG'den Giriş
        ex.create_limit_buy_order(symbol, amount, entry_p)
        time.sleep(2)

        # Stop ve TP (Sizin görseldeki 1:2 RR kuralına göre)
        sl_p = entry_p * 0.98 # En son swing noktası veya %2
        tp1_p = entry_p * 1.02
        tp2_p = entry_p * 1.05

        # Bitget Garantili Emirler
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, sl_p, {'stopPrice': sl_p, 'reduceOnly': True})
        ex.create_order(symbol, 'limit', 'sell', amount * 0.75, tp1_p, {'reduceOnly': True})
        
        active_trades[symbol] = True
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Hata: {str(e)}")

def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **SMC STRATEJİ BOTU: %100 ONAY MODU**")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            for sym in symbols:
                signal, status, entry_p = get_smc_analysis(sym)
                if signal and sym not in active_trades:
                    execute_trade(sym, signal, entry_p)
                time.sleep(0.05)
            time.sleep(600)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=main_worker, daemon=True).start()
    bot.infinity_polling()
