import ccxt
import time
import telebot
import os
import threading

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. SERT VE GÜVENLİ AYARLAR] ---
CONFIG = {
    'entry_usdt': 10.0,    # Senin istediğin sabit 10 USDT
    'leverage': 10,
    'rr_ratio': 2.0,       # Resimdeki 1:2 Hedef Oranı
    'sl_pct': 0.015,       # %1.5 Stop (Dar stop)
    'vol_threshold': 2.5,  # Hacim 2.5 katı olmalı (Gerçek kırılım)
    'max_active_trades': 1, # Hata payını sıfırlamak için tek işlem
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']
}

# --- [3. RESİMDEKİ SMC MOTORU] ---
def get_smc_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        h, l, c, v, o = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars], [b[1] for b in bars]
        
        # 1. Likidite Süpürme (Sweep)
        prev_high, prev_low = max(h[-40:-5]), min(l[-40:-5])
        
        # 2. Hacim Onayı (Displacement)
        avg_v = sum(v[-20:-5]) / 15
        vol_ok = v[-1] > (avg_v * CONFIG['vol_threshold'])

        # SHORT: Tepe süpürüldü, sert hacimli kırmızı mum geldi
        if vol_ok and h[-2] > prev_high and c[-1] < prev_low and c[-1] < o[-1]:
            return 'short', c[-1]

        # LONG: Dip süpürüldü, sert hacimli yeşil mum geldi
        if vol_ok and l[-2] < prev_low and c[-1] > prev_high and c[-1] > o[-1]:
            return 'long', c[-1]

        return None, None
    except: return None, None

# --- [4. ANA DÖNGÜ & BORSAYA EMİR GÖNDERİMİ] ---
def main_loop():
    send_msg("🚀 **V39 SMC PRO AKTİF**\nHard Stop & 10 USDT Sabitlendi.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = [s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']]
            
            # Açık pozisyon kontrolü (Borsadan direkt sorgu)
            positions = ex.fetch_positions()
            active_symbols = [p['symbol'] for p in positions if float(p['contracts']) > 0]

            if len(active_symbols) < CONFIG['max_active_trades']:
                for s in symbols[:80]: # İlk 80 en hacimli koin
                    signal, price = get_smc_signal(s)
                    if signal and s not in active_symbols:
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
                        sl = price * (1 + CONFIG['sl_pct']) if signal == 'short' else price * (1 - CONFIG['sl_pct'])
                        tp = price * (1 - (CONFIG['sl_pct'] * CONFIG['rr_ratio'])) if signal == 'short' else price * (1 + (CONFIG['sl_pct'] * CONFIG['rr_ratio']))

                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            # 1. ANA MARKET GİRİŞİ
                            ex.create_order(s, 'market', 'sell' if signal == 'short' else 'buy', amt, params={'posSide': signal})
                            # 2. BORSAYA STOP VE TP YAZIMI (AYRI EMİR)
                            ex.create_order(s, 'market', 'buy' if signal == 'short' else 'sell', amt, 
                                            params={'posSide': signal, 'stopLossPrice': sl, 'takeProfitPrice': tp})
                            
                            send_msg(f"🎯 **SMC SNIPER GİRİŞ!**\nKoin: {s}\nYön: {signal.upper()}\n💰 Giriş: {price}\n🛑 SL: {sl:.4f}\n✅ TP: {tp:.4f}")
                            time.sleep(5) # Emirler işlensin
                            break 
                        except Exception as e:
                            print(f"Emir hatası: {e}")
            time.sleep(15)
        except Exception as e:
            time.sleep(20)

# --- [5. KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Bakiye:** {usdt:.2f} USDT")
    except: bot.reply_to(message, "⚠️ API Bağlantı Hatası!")

@bot.message_handler(commands=['durum'])
def get_status(message):
    try:
        pos = ex.fetch_positions()
        active = [p['symbol'] for p in pos if float(p['contracts']) > 0]
        msg = "🟢 Radar Aktif\n"
        msg += f"📈 Aktif İşlem: {active if active else 'Yok'}"
        bot.reply_to(message, msg)
    except: bot.reply_to(message, "⚠️ Durum çekilemedi.")

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
