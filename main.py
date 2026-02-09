import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

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
    'entry_usdt': 20.0,          # İşlem başı miktar
    'leverage': 10,              # Kaldıraç
    'tp1_ratio': 0.75,           # TP1'de %75 kapanış
    'max_active_trades': 4,      
    'min_vol_24h': 10000000,     # Minimum 10M hacim
    'rr_target': 1.5             # Risk/Ödül oranı
}

active_trades = {}

# --- [YARDIMCI: HASSASİYET AYARI] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        if precision < 1:
            step = int(-math.log10(precision))
            return round(amount, step)
        return int(amount)
    except: return round(amount, 2)

# --- [3. ANALİZ MOTORU (RADAR)] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 5 or now_sec > 55: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        # Anti-Manipülasyon: Gövde Kapanış ve Hacim Onayı
        swing_low = min(l[-15:-1])
        liq_taken = l[-1] < swing_low
        recent_high = max(h[-10:-1])
        mss_ok = c[-1] > recent_high # Gövde kapanış onayı
        avg_vol = sum(v[-6:-1]) / 5
        
        if liq_taken and mss_ok and v[-1] > avg_vol:
            return 'LONG', c[-1], min(l[-5:]), "SMC_Hacimli_Onay"
        return None, None, None, None
    except: return None, None, None, None

# --- [4. POZİSYON TAKİP (TP1 -> BE, TP2/3 -> KASAYA KAR)] ---
def monitor_trade(symbol, entry, stop, tp1, amount):
    stage = 0 
    # 1 USDT net kar için gereken fiyat hareketini hesaplar
    price_step = 1.0 / (amount / CONFIG['leverage']) 
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # --- STAGE 0: TP1 (%75) ALINDI, STOP GİRİŞE ---
            if stage == 0 and price >= tp1:
                ex.cancel_all_orders(symbol) # Eski stopu sil
                time.sleep(1)
                pos = ex.fetch_positions([symbol])
                if pos and float(pos[0]['contracts']) > 0:
                    rem_qty = round_amount(symbol, float(pos[0]['contracts']))
                    # Yeni Stop: Giriş Seviyesi (Break Even)
                    ex.create_order(symbol, 'trigger_market', 'sell', rem_qty, params={'stopPrice': entry, 'reduceOnly': True})
                    bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 (%75) Alındı.\nStop girişe ({entry}) çekildi.")
                    stage = 1

            # --- STAGE 1 & 2: KADEMELİ 1 USDT KAR KİLİTLEME ---
            elif stage in [1, 2] and price >= (tp1 + (price_step * stage)):
                sell_qty = round_amount(symbol, (1.0 * CONFIG['leverage']) / price)
                ex.create_market_order(symbol, 'sell', sell_qty, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP{stage+1}: 1 USDT kar kasaya atıldı. Stop girişte devam.")
                stage += 1

            # Pozisyon kontrol (Kapandıysa döngüden çık)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) <= 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} İşlemi bitti.")
                break
                
            time.sleep(20)
        except Exception as e:
            time.sleep(10)

# --- [5. TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        usdt = bal['total']['USDT']
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt:.2f} USDT")
    except Exception as e:
        bot.reply_to(message, "⚠️ Bakiye çekilemedi.")

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades:
        bot.reply_to(message, "🔍 Şu an aktif işlem yok. Radar çalışıyor...")
    else:
        txt = "📊 **Aktif Pozisyonlar:**\n"
        for s in active_trades: txt += f"- {s}\n"
        bot.reply_to(message, txt)

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🚀 Bot Başlatıldı.\nRadar: Aktif 📡\nTP1: %75 + Stop Girişe\nTP2/3: +1 USDT Kâr Kilidi")
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in symbols:
                if sym in active_trades: continue
                if markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, fvg = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    # İşlemi İcra Et
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    tp1 = entry + ((entry - stop) * CONFIG['rr_target'])

                    ex.create_market_order(sym, 'buy', amount)
                    active_trades[sym] = True
                    
                    # İlk Stop ve Limit TP1
                    ex.create_order(sym, 'trigger_market', 'sell', amount, params={'stopPrice': stop, 'reduceOnly': True})
                    ex.create_order(sym, 'limit', 'sell', round_amount(sym, amount * CONFIG['tp1_ratio']), tp1, {'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI: {sym}**\nGiriş: {entry:.4f}\nTP1 (%75): {tp1:.4f}\nStop: {stop:.4f}")
                    
                    threading.Thread(target=monitor_trade, args=(sym, entry, stop, tp1, amount), daemon=True).start()
                
                time.sleep(0.1)
            time.sleep(300) 
        except Exception as e:
            time.sleep(30)

if __name__ == "__main__":
    # Borsayı önceden yükle
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
