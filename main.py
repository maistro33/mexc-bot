import ccxt
import telebot
import time
import os
import threading

# --- [1. BAĞLANTILAR] ---
# Railway Variables kısmına bu isimleri girdiğinizden emin olun
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
    'leverage': 10,
    'tp1_ratio': 0.75,          # Sizin %75 Kar Al kuralınız
    'max_active_trades': 4,
    'min_vol_24h': 10000000
}

active_trades = {}

# --- [3. TELEGRAM KOMUTLARI - BAKİYE SORUNUNU ÇÖZER] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance = ex.fetch_balance({'type': 'swap'})
        free_usdt = balance['USDT']['free']
        total_usdt = balance['USDT']['total']
        msg = f"💰 **GÜNCEL BAKİYE RAPORU**\n\n💵 Kullanılabilir: {free_usdt:.2f} USDT\n🏦 Toplam: {total_usdt:.2f} USDT"
        bot.reply_to(message, msg)
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {str(e)}")

# --- [4. STRATEJİ MOTORU - 5 ADIMLI SMC] ---
def analyze_smc_strategy(symbol):
    try:
        # 1G - 4S - 1S Trend Onayı
        for tf in ['1d', '4h', '1h']:
            bars = ex.fetch_ohlcv(symbol, timeframe=tf, limit=20)
            if bars[-1][4] <= (sum([b[4] for b in bars]) / 20): return None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # 1- Likidite Seviyesi Alımı
        liq_taken = l[-1] < min(l[-15:-1]) and c[-1] > min(l[-15:-1])
        # 2- Ters Yön Displacement & 3- MSS (Gövde Kapanış)
        mss_ok = c[-1] > max(h[-10:-1])
        # 4- FVG Girişi
        fvg_ok = h[-3] < l[-1]
        entry_p = h[-3]
        
        if liq_taken and mss_ok and fvg_ok:
            if c[-1] <= entry_p * 1.003:
                stop_loss = min(l[-5:]) # En son swing noktası
                return 'buy', entry_p, stop_loss
        return None, None, None
    except: return None, None, None

# --- [5. EMİR SİSTEMİ - STOP VE TP GARANTİLİ] ---
def execute_trade(symbol, side, entry, stop):
    try:
        balance = ex.fetch_balance({'type': 'swap'})
        free_usdt = float(balance['USDT']['free'])
        trade_val = free_usdt / 4  # Bakiyeyi 4'e bölerek risk yönetimi

        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (trade_val * CONFIG['leverage']) / entry
        
        # 1:2 RR Hedefleme (Resimdeki 6. madde)
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * 2.0) # Tam 1:2 RR

        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ ONAYLANDI: {symbol}**\n📍 Giriş: {entry:.4f}\n🛡️ Stop: {stop:.4f}")
        
        # Market Giriş
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)

        # Stop Loss (Trigger Limit)
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, stop, {'stopPrice': stop, 'reduceOnly': True})
        # TP1 (%75 Kapatma)
        ex.create_order(symbol, 'limit', 'sell', amount * 0.75, tp1, {'reduceOnly': True})
        # TP2 (%25 Kapatma - 1:2 RR)
        ex.create_order(symbol, 'limit', 'sell', amount * 0.25, tp2, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🎯 TP1: {tp1:.4f}\n🎯 TP2 (1:2 RR): {tp2:.4f}")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Hatası: {str(e)}")

# --- [6. RADAR DÖNGÜSÜ] ---
def main_radar():
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            # Radar Analiz Raporu Gönder (Her turda)
            report = "📡 **RADAR ANALİZ**\n"
            movers = sorted(symbols, key=lambda x: abs(markets[x]['percentage']), reverse=True)[:5]
            for s in movers:
                report += f"🔥 {s.split(':')[0]}: %{markets[s]['percentage']:.2f}\n"
            bot.send_message(MY_CHAT_ID, report)

            for sym in symbols:
                if sym in active_trades: continue
                if markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue

                signal, entry, stop = analyze_smc_strategy(sym)
                if signal and len(active_trades) < CONFIG['max_active_trades']:
                    execute_trade(sym, signal, entry, stop)
                time.sleep(0.2)

            time.sleep(600) # 10 Dakikada bir tur
        except: time.sleep(30)

if __name__ == "__main__":
    # Telegram ve Radar'ı aynı anda çalıştırır
    threading.Thread(target=main_radar, daemon=True).start()
    bot.infinity_polling()
