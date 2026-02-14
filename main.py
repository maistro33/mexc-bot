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

# --- [2. SERT SMC AYARLARI] ---
CONFIG = {
    'entry_usdt': 10.0,    # Sabit 10 USDT (Senin istediğin)
    'leverage': 10,
    'rr_ratio': 2.0,       # Resimdeki 1:2 Risk-Reward oranı
    'sl_pct': 0.015,       # %1.5 Stop
    'vol_threshold': 2.0,  # Normalin 2 katı hacim (Resimdeki 'Displacement')
    'max_active_trades': 1, # Hata payını sıfırlamak için teker teker
    'blacklist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']
}

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: pass

# --- [3. RESİMDEKİ STRATEJİ MOTORU (SMC + FVG)] ---
def get_smc_signal(symbol):
    try:
        bars = ex.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]
        
        # 1. Likidite Süpürme (Liquidity Sweep)
        sweep_high = max(h[-40:-5])
        sweep_low = min(l[-40:-5])
        
        # 2. Hacim Onayı (Displacement)
        avg_v = sum(v[-20:-5]) / 15
        is_displaced = v[-1] > (avg_v * CONFIG['vol_threshold'])

        # SHORT SİNYALİ (Resimdeki Ayı Senaryosu)
        if is_displaced and h[-2] > sweep_high and c[-1] < sweep_low:
            fvg_gap = h[-3] - l[-1] # Basit FVG tespiti
            if fvg_gap > 0:
                return 'short', c[-1]

        # LONG SİNYALİ (Resimdeki Boğa Senaryosu)
        if is_displaced and l[-2] < sweep_low and c[-1] > sweep_high:
            fvg_gap = h[-1] - l[-3]
            if fvg_gap > 0:
                return 'long', c[-1]

        return None, None
    except: return None, None

# --- [4. ANA DÖNGÜ & SERT STOP SİSTEMİ] ---
def main_loop():
    send_msg("🛡️ **V38 SMC SNIPER AKTİF**\nResimdeki 1:2 RR ve Hard Stop devrede.")
    while True:
        try:
            tickers = ex.fetch_tickers()
            symbols = [s for s in tickers if '/USDT:USDT' in s and s not in CONFIG['blacklist']]
            
            for s in symbols[:100]:
                if s not in active_trades and len(active_trades) < CONFIG['max_active_trades']:
                    signal, entry_price = get_smc_signal(s)
                    if signal:
                        # Miktar Hesaplama
                        amt = (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry_price
                        
                        # Stop ve TP Hesaplama (Resimdeki 1:2 RR)
                        sl = entry_price * (1 + CONFIG['sl_pct']) if signal == 'short' else entry_price * (1 - CONFIG['sl_pct'])
                        tp = entry_price * (1 - (CONFIG['sl_pct'] * CONFIG['rr_ratio'])) if signal == 'short' else entry_price * (1 + (CONFIG['sl_pct'] * CONFIG['rr_ratio']))

                        try:
                            ex.set_leverage(CONFIG['leverage'], s)
                            
                            # ANA EMİR
                            order = ex.create_order(s, 'market', 'sell' if signal == 'short' else 'buy', amt, params={'posSide': signal})
                            
                            # BORSAYA STOP VE TP EMİRLERİNİ YAZ (HARD STOP)
                            # Bu kısım bot donsa bile paranı korur
                            ex.create_order(s, 'market', 'buy' if signal == 'short' else 'sell', amt, 
                                            params={'posSide': signal, 'stopLossPrice': sl, 'takeProfitPrice': tp})
                            
                            active_trades[s] = True
                            send_msg(f"🎯 **SMC İŞLEMİ AÇILDI!**\nKoin: {s}\nYön: {signal.upper()}\n💰 Giriş: {entry_price}\n🛑 SL: {sl:.4f}\n✅ TP: {tp:.4f}")
                        except Exception as e:
                            send_msg(f"⚠️ Emir Hatası: {e}")
            
            # Aktif işlem takibi (Hafızayı temizlemek için)
            for s in list(active_trades.keys()):
                pos = ex.fetch_position(s)
                if float(pos['entryPrice']) == 0:
                    del active_trades[s]
                    send_msg(f"ℹ️ {s} işlemi borsada kapandı.")
                    
            time.sleep(20)
        except: time.sleep(30)

# --- [5. KOMUTLAR] ---
@bot.message_handler(commands=['bakiye'])
def get_balance(message):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('total', 0)
        bot.reply_to(message, f"💰 **Net Bakiye:** {usdt:.2f} USDT")
    except: bot.reply_to(message, "⚠️ Hata.")

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
