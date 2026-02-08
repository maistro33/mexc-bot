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

# Bitget Bağlantısı (En Sağlam Yapı)
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. STRATEJİK AYARLAR] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'stop_loss_ratio': 0.02,        # %2 Net Zarar Kes
    'tp1_ratio': 0.75,              # İlk hedefte %75 sat (Sadık Bey Ayarı)
    'tp1_target': 0.018,            # %1.8 (Komisyon sonrası net %1.5 kâr)
    'tp2_target': 0.035,            # %3.5 (Net %3.0 kâr)
    'tp3_target': 0.055,            # %5.5 (Net %5.0 kâr)
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA - ÇALIŞAN ESKİ MANTIK] ---
def get_safe_balance():
    try:
        balance = ex.fetch_balance()
        # Bitget Vadeli (USDT-M) bakiyesini okuyan en garanti satır
        usdt_bal = balance['total'].get('USDT', 0)
        if usdt_bal == 0:
            usdt_bal = float(balance['info'][0]['available']) if 'info' in balance else 0
        return usdt_bal
    except:
        return 0.0

@bot.message_handler(commands=['bakiye'])
def check_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Güncel Kasa (Bitget):** {total:.2f} USDT")

# --- [4. SMC STRATEJİSİ - FABRİKA AYARLARI] ---
def get_signal(symbol):
    try:
        if any(x in symbol for x in ["XAU", "XAG"]): return None
        
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        # 1. Gövde Kapanış Onayı: Son 20 mumun en yükseğini kırmalı
        last_close = bars[-1][4]
        prev_high = max([b[2] for b in bars[-21:-1]])
        
        # 2. Hacim Onayı: Hacim ortalamanın üstünde olmalı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:]) / 15
        current_vol = vols[-1]

        # Strateji: Önceki tepe üstünde kapanış + Yüksek Hacim
        if last_close > prev_high and current_vol > (avg_vol * 1.2):
            return 'buy'
        return None
    except:
        return None

# --- [5. İŞLEM YÖNETİMİ - KESİN KADEMELİ] ---
def execute_trade(symbol, side):
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
        
        bot.send_message(MY_CHAT_ID, f"🚀 **STRATEJİ TETİKLENDİ!**\n🪙 {symbol}\n💰 Giriş: {price}")
        ex.create_market_order(symbol, side, amount)
        time.sleep(2)
        
        # A. Stop-Loss (%100)
        sl_p = price * (1 - CONFIG['stop_loss_ratio']) if side == 'buy' else price * (1 + CONFIG['stop_loss_ratio'])
        ex.create_order(symbol, 'stop', 'sell' if side == 'buy' else 'buy', amount, None, {'reduceOnly': True, 'stopPrice': sl_p})
        
        # B. TP1 (%75 Kar Al - Sizin Ayarınız)
        tp1_p = price * (1 + CONFIG['tp1_target']) if side == 'buy' else price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * CONFIG['tp1_ratio'], tp1_p, {'reduceOnly': True})
        
        # C. TP2 (Kalanın Yarısı)
        tp2_p = price * (1 + CONFIG['tp2_target']) if side == 'buy' else price * (1 - CONFIG['tp2_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.125, tp2_p, {'reduceOnly': True})

        # D. TP3 (Son Kalan)
        tp3_p = price * (1 + CONFIG['tp3_target']) if side == 'buy' else price * (1 - CONFIG['tp3_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.125, tp3_p, {'reduceOnly': True})

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER DİZİLDİ**\n🛡️ SL: {sl_p:.4f}\n🎯 TP1 (%75): {tp1_p:.4f}\n🎯 TP2-3 Aktif.")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# --- [6. ANA DÖNGÜ] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ Sadık Bey, Bot Tam Kapasite Yayında!")
    while True:
        try:
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            for sym in all_symbols:
                signal = get_signal(sym)
                if signal and sym not in active_trades:
                    execute_trade(sym, signal)
                time.sleep(0.1)
            time.sleep(600)
        except:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
