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

# --- [2. AYARLAR - SADIK BEY ÖZEL] ---
CONFIG = {
    'leverage': 10,
    'tp1_ratio': 0.75,          # %75 TP1 Kuralı
    'max_active_trades': 4,      # 72 USDT / 4 = 18 USDT per trade
    'min_vol_24h': 10000000      # 10M$ altı hacimsiz coinlere bakmaz
}

active_trades = {}

# --- [3. CANLI BAKİYE VE EMİR KONTROLÜ] ---
def get_live_balance():
    """Bakiye hatasını çözen dinamik bakiye çekici"""
    try:
        balance = ex.fetch_balance({'type': 'swap'})
        free_usdt = float(balance['USDT']['free'])
        # Bakiyeyi 4'e bölerek risk yönetimi yapar
        trade_amount = free_usdt / (CONFIG['max_active_trades'] - len(active_trades) + 1)
        return trade_amount if trade_amount > 10 else 10 # Min 10 USDT
    except: return 0

def check_mtf_trend(symbol):
    """1G-4S-1S Onay Mekanizması"""
    try:
        for tf in ['1d', '4h', '1h']:
            bars = ex.fetch_ohlcv(symbol, timeframe=tf, limit=20)
            ma = sum([b[4] for b in bars]) / len(bars)
            if bars[-1][4] <= ma: return False
        return True
    except: return False

# --- [4. STRATEJİ: LİKİDİTE + MSS + FVG] ---
def analyze_smc(symbol):
    try:
        if not check_mtf_trend(symbol): return None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # Strateji Kuralları
        liq_taken = l[-1] < min(l[-15:-1]) and c[-1] > min(l[-15:-1])
        mss_ok = c[-1] > max(h[-10:-1])
        fvg_ok = h[-3] < l[-1]
        entry_p = h[-3]
        vol_ok = v[-1] > (sum(v[-20:])/20 * 1.5)

        if liq_taken and mss_ok and fvg_ok and vol_ok:
            if c[-1] <= entry_p * 1.003:
                stop_loss = min(l[-5:])
                return 'buy', entry_p, stop_loss
        return None, None, None
    except: return None, None, None

# --- [5. EMİR DİZME ÜSTADIDIR - HATA YAPMAZ] ---
def execute_trade(symbol, side, entry, stop):
    try:
        amount_usdt = get_live_balance()
        if amount_usdt <= 0: return

        ex.set_leverage(CONFIG['leverage'], symbol)
        amount = (amount_usdt * CONFIG['leverage']) / entry
        
        # 1:2.5 Risk-Ödül Planı
        risk = entry - stop
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * 3.0)

        bot.send_message(MY_CHAT_ID, f"🚀 **HYPE SİNYALİ: {symbol}**\n💰 Giriş: {entry:.4f}\n💸 Miktar: {amount_usdt:.2f} USDT")
        
        # 1. Market Alış
        ex.create_market_order(symbol, side, amount)
        time.sleep(2) # Borsanın işlemesi için süre ver

        # 2. STOP LOSS (Trigger Limit - En Güvenlisi)
        # stopPrice: Tetiklenme fiyatı, price: Emrin gönderileceği fiyat
        ex.create_order(symbol, 'trigger_limit', 'sell', amount, stop, {
            'stopPrice': stop, 
            'reduceOnly': True
        })
        
        # 3. TP1 (%75 Kapatma)
        ex.create_order(symbol, 'limit', 'sell', amount * CONFIG['tp1_ratio'], tp1, {
            'reduceOnly': True
        })
        
        # 4. TP2 (Kalan %25)
        ex.create_order(symbol, 'limit', 'sell', amount * (1-CONFIG['tp1_ratio']), tp2, {
            'reduceOnly': True
        })

        active_trades[symbol] = True
        bot.send_message(MY_CHAT_ID, f"✅ **EMİRLER BAŞARIYLA DİZİLDİ**\n🛡️ SL: {stop:.4f}\n🎯 TP1 (%75): {tp1:.4f}\n🎯 TP2: {tp2:.4f}")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ Emir Dizme Hatası ({symbol}): {str(e)}")

# --- [6. RADAR VE RAPORLAMA] ---
def main_radar():
    bot.send_message(MY_CHAT_ID, "🦅 **SMC RADAR NİHAİ MOD: AKTİF**\nBakiye ve tüm borsa kontrol altında.")
    while True:
        try:
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            
            # Piyasa Raporu
            report = "📡 **RADAR ANALİZ**\n"
            movers = sorted(all_symbols, key=lambda x: abs(markets[x]['percentage']), reverse=True)[:5]
            for s in movers:
                report += f"🔥 {s.split(':')[0]}: %{markets[s]['percentage']:.2f}\n"
            bot.send_message(MY_CHAT_ID, report)

            # Tarama
            for sym in all_symbols:
                if sym in active_trades: continue
                if markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue

                signal, entry, stop = analyze_smc(sym)
                if signal and len(active_trades) < CONFIG['max_active_trades']:
                    execute_trade(sym, signal, entry, stop)
                time.sleep(0.1) # Hız ve Limit dengesi

            time.sleep(600)
        except Exception as e:
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=main_radar, daemon=True)
    t.start()
    bot.infinity_polling()
